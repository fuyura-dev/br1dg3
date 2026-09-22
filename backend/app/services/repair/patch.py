import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from bs4.formatter import HTMLFormatter

MARKER = "data-br1dg3"       # temporary tracking attribute: data-br1dg3="v1", "v2", ...


class _AsWritten(HTMLFormatter):
    """Like str(tag), but keeps the attribute order and writes <input ...> instead of <input .../>."""

    def attributes(self, tag):
        return [(k, None if v == "" else v) for k, v in tag.attrs.items()]   # None -> bare attribute


_AS_WRITTEN = _AsWritten(void_element_close_prefix="")


def outer_html(node):
    return node.decode(formatter=_AS_WRITTEN)


# ------------------------------------------------------------------ reading a reply
FENCE = re.compile(r"```[a-zA-Z]*\s*\n?(.*?)```", re.DOTALL)


def clean_reply(text):
    """Drop a code fence and any chatter before/after the HTML."""
    text = text or ""
    fenced = FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    text = text.strip()
    if "<" in text and ">" in text:
        text = text[text.index("<"): text.rindex(">") + 1]
    return text


@dataclass
class PatchResult:
    applied: bool
    status: str                                   # applied | empty_reply | no_element
    warnings: list[str] = field(default_factory=list)


def _marker_owner(elements, token):
    """Return the element in a reply fragment that carries `token`, if present."""
    for element in elements:
        if element.get(MARKER) == token:
            return element
        descendant = element.find(attrs={MARKER: token})
        if descendant is not None:
            return descendant
    return None


def _apply_layout_landmarks(target, elements):
    """Reconcile the LLM's structural layout decisions (renaming containers to <header>, <nav>,
    <main>, <footer>, or wrapping content sections in <main>) onto the real DOM while preserving
    all real inner contents, text, images, and data-br1dg3 tracking markers."""
    real_body = target.body if target.name == "html" else target
    if real_body is None:
        return

    # Determine reply_body from elements
    reply_body = None
    for el in elements:
        if el.name == "html":
            reply_body = el.find("body")
            break
        elif el.name == "body":
            reply_body = el
            break

    if reply_body is None:
        # Elements are layout fragments like <header>, <main>, <footer>
        reply_body = BeautifulSoup("<body></body>", "html.parser").body
        for el in elements:
            reply_body.append(el)

    print(f"[_apply_layout_landmarks] target: <{target.name}> | reply_body tags: {[c.name for c in reply_body.children if isinstance(c, Tag)]}")

    # 1. Conversions of existing elements
    for reply_el in [c for c in reply_body.children if isinstance(c, Tag)]:
        reply_id = reply_el.get("id")
        if reply_id and real_body.find(id=reply_id):
            real_el = real_body.find(id=reply_id)
            if real_el.name != reply_el.name:
                real_el.name = reply_el.name
            real_el.attrs.update(reply_el.attrs)
            print(f"[_apply_layout_landmarks] Converted element #{reply_id} -> <{real_el.name}>")

    # 2. Main landmark insertion (boundary-aware and duplicate-ID safe)
    reply_main = reply_body.find("main")
    if reply_main and not real_body.find("main"):
        reply_children = [c for c in reply_body.children if isinstance(c, Tag)]
        main_idx = reply_children.index(reply_main) if reply_main in reply_children else -1

        real_to_wrap = []
        if main_idx >= 0:
            pre_reply = reply_children[:main_idx]
            post_reply = reply_children[main_idx + 1:]

            start_el = None
            for el in reversed(pre_reply):
                match = real_body.find(id=el.get("id")) if el.get("id") else None
                if not match and el.name in {"header", "nav", "h1"}:
                    match = real_body.find(el.name)
                if match and match in real_body.find_all(recursive=False):
                    start_el = match
                    break

            end_el = None
            for el in post_reply:
                match = real_body.find(id=el.get("id")) if el.get("id") else None
                if not match and el.name in {"footer", "aside"}:
                    match = real_body.find(el.name)
                if match and match in real_body.find_all(recursive=False):
                    end_el = match
                    break

            real_direct_children = [c for c in real_body.children if isinstance(c, Tag)]
            start_idx = (real_direct_children.index(start_el) + 1) if start_el and start_el in real_direct_children else 0
            end_idx = real_direct_children.index(end_el) if end_el and end_el in real_direct_children else len(real_direct_children)
            real_to_wrap = real_direct_children[start_idx:end_idx]

        # If boundaries didn't resolve, match children with duplicate-ID tracking
        if not real_to_wrap:
            used_elements = set()
            for c in [ch for ch in reply_main.children if isinstance(ch, Tag)]:
                wid = c.get("id")
                if wid:
                    for el in real_body.find_all(id=wid, recursive=False):
                        if id(el) not in used_elements:
                            real_to_wrap.append(el)
                            used_elements.add(id(el))
                            break

        if real_to_wrap:
            new_container = real_body.new_tag("main", **reply_main.attrs)
            real_to_wrap[0].insert_before(new_container)
            for el in real_to_wrap:
                new_container.append(el.extract())
            print(f"[_apply_layout_landmarks] Inserted <main> wrapping {len(real_to_wrap)} elements!")


def apply_reply(target, reply, token):
    """Replace `target` with every element in the reply fragment, in document order."""
    text = clean_reply(reply)
    if not text:
        return PatchResult(False, "empty_reply")
    elements = [c for c in BeautifulSoup(text, "html.parser").contents if isinstance(c, Tag)]
    if not elements:
        return PatchResult(False, "no_element")

    warnings = [f"elements_added:{len(elements)}"] if len(elements) > 1 else []

    replacement_target = _marker_owner(elements, token)
    if replacement_target is None:
        same_tag = next((e for e in elements if e.name == target.name), None)
        replacement_target = same_tag or elements[0]
        replacement_target[MARKER] = token
        warnings.append("marker_readded" if same_tag else "marker_ambiguous")

    if target.name in {"html", "body"}:
        if replacement_target.name == target.name:
            target.attrs.update(replacement_target.attrs)
        _apply_layout_landmarks(target, elements)
        return PatchResult(True, "applied", warnings)

    if replacement_target.name != target.name:
        warnings.append("tag_changed")
    if replacement_target.get("id") != target.get("id"):
        warnings.append("id_changed")
    inner = [e[MARKER] for e in target.find_all(attrs={MARKER: True})]
    warnings += [f"marker_lost:{t}" for t in inner if _marker_owner(elements, t) is None]
    if len(elements) == 1 and elements[0] == target:  # same name, attributes and children
        warnings.append("unchanged")

    target.replace_with(*elements)
    return PatchResult(True, "applied", warnings)


def parse_document_reply(reply):
    """Baseline: returns (html, "ok") or (None, reason)."""
    text = clean_reply(reply)
    if not text:
        return None, "empty_reply"
    if BeautifulSoup(text, "html.parser").find(True) is None:
        return None, "not_html"
    return text, "ok"


def strip_markers(html):
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(attrs={MARKER: True}):
        del element[MARKER]
    return outer_html(soup)