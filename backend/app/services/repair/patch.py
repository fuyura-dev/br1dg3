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


HIDDEN_IN_PROMPT_TAGS = {"script", "style", "link", "meta", "noscript", "svg", "template"}


def _is_placeholder(tag: Tag) -> bool:
    """True when the LLM kept the prompt's '…' ellipsis for collapsed inner content."""
    return not tag.find(True) and tag.get_text(strip=True) == "…"


def _match_real_element(reply_el: Tag, pool: list[Tag], used_ids: set[int]) -> Tag | None:
    """Find the corresponding original DOM element for a reply element from `pool`."""
    rid = reply_el.get("id")
    if rid:
        for el in pool:
            if id(el) not in used_ids and el.get("id") == rid:
                return el

    # Match by same tag name + non-skipped attributes (or placeholder if original had children)
    for el in pool:
        if id(el) in used_ids or el.name != reply_el.name:
            continue
        if _is_placeholder(reply_el) and el.find(True):
            return el
        if not _is_placeholder(reply_el) and el.get_text(strip=True) == reply_el.get_text(strip=True):
            return el

    return None


def _reconcile_container(real_container: Tag, reply_container: Tag) -> None:
    """Generically reconcile a container (such as <head> or <body>) with the LLM's reply
    by expanding '…' placeholders back to their original DOM nodes while keeping any
    new elements, wrappers, or attribute changes returned by the LLM."""
    if _is_placeholder(reply_container):
        return

    real_children = [c for c in real_container.children if isinstance(c, Tag)]
    visible_pool = [c for c in real_children if c.name not in HIDDEN_IN_PROMPT_TAGS]
    hidden_children = [c for c in real_children if c.name in HIDDEN_IN_PROMPT_TAGS]

    used_ids: set[int] = set()
    reply_tags = [c for c in reply_container.children if isinstance(c, Tag)]

    # First pass: pre-claim exact ID matches anywhere in reply_container so nested
    # elements (e.g. <div id="__nuxt">…</div> inside <main>) claim their real node.
    id_map: dict[int, Tag] = {}
    for candidate in reply_container.find_all(True):
        cid = candidate.get("id")
        if cid:
            for real_el in visible_pool:
                if id(real_el) not in used_ids and real_el.get("id") == cid:
                    id_map[id(candidate)] = real_el
                    used_ids.add(id(real_el))
                    break

    def hydrate_node(reply_node: Tag) -> list[Tag]:
        matched = id_map.get(id(reply_node))
        if matched is None:
            matched = _match_real_element(reply_node, visible_pool, used_ids)
            if matched is not None:
                used_ids.add(id(matched))

        if matched is not None:
            matched.name = reply_node.name
            for k, v in reply_node.attrs.items():
                if k != MARKER:
                    matched[k] = v
            if not _is_placeholder(reply_node) and reply_node.find(True):
                _reconcile_container(matched, reply_node)
            return [matched.extract()]

        # If this is an unmatched placeholder (e.g. LLM wrote <wrapper>…</wrapper> to wrap
        # remaining visible children), wrap the remaining unused visible elements.
        if _is_placeholder(reply_node):
            remaining = [el for el in visible_pool if id(el) not in used_ids]
            if remaining:
                for el in remaining:
                    used_ids.add(id(el))
                wrapper = BeautifulSoup(f"<{reply_node.name}></{reply_node.name}>", "html.parser").find(reply_node.name)
                for k, v in reply_node.attrs.items():
                    if k != MARKER:
                        wrapper[k] = v
                for el in remaining:
                    wrapper.append(el.extract())
                return [wrapper]
            return []

        # Otherwise it is a newly introduced element or wrapper with children
        child_tags = [c for c in reply_node.children if isinstance(c, Tag)]
        if not child_tags:
            cloned = BeautifulSoup(outer_html(reply_node), "html.parser").find(True)
            if cloned is not None and MARKER in cloned.attrs:
                del cloned[MARKER]
            return [cloned] if cloned is not None else []

        wrapper = BeautifulSoup(f"<{reply_node.name}></{reply_node.name}>", "html.parser").find(reply_node.name)
        for k, v in reply_node.attrs.items():
            if k != MARKER:
                wrapper[k] = v
        for child in child_tags:
            for hydrated in hydrate_node(child):
                wrapper.append(hydrated)
        return [wrapper]

    new_children: list[Tag] = []
    for top_reply in reply_tags:
        new_children.extend(hydrate_node(top_reply))

    # Preserve any original visible elements the LLM omitted (e.g. <link> tags) and all hidden tags (<script>, <style>, etc.)
    leftover_visible = [el.extract() for el in visible_pool if id(el) not in used_ids]
    preserved_hidden = [el.extract() for el in hidden_children]

    real_container.clear()
    for el in new_children + leftover_visible + preserved_hidden:
        real_container.append(el)


def _apply_document_patch(target: Tag, elements: list[Tag]) -> None:
    """Reconcile an <html> or <body> reply with the live BeautifulSoup tree by expanding
    collapsed '…' placeholders back to their original DOM nodes."""
    if target.name == "html":
        reply_html = next((e for e in elements if e.name == "html"), None)
        if reply_html is not None:
            for k, v in reply_html.attrs.items():
                target[k] = v
            reply_head = reply_html.find("head", recursive=False)
            if reply_head is not None and target.head is not None:
                _reconcile_container(target.head, reply_head)
            reply_body = reply_html.find("body", recursive=False)
            if reply_body is not None and target.body is not None:
                for k, v in reply_body.attrs.items():
                    if k != MARKER:
                        target.body[k] = v
                _reconcile_container(target.body, reply_body)
            return

    real_body = target.body if target.name == "html" else target
    if real_body is None:
        return

    reply_body = next((e for e in elements if e.name == "body"), None)
    if reply_body is None:
        reply_body = BeautifulSoup("<body></body>", "html.parser").body
        for el in elements:
            reply_body.append(el)
    else:
        for k, v in reply_body.attrs.items():
            if k != MARKER:
                real_body[k] = v

    _reconcile_container(real_body, reply_body)




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
        _apply_document_patch(target, elements)
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