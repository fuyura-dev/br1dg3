import re
from copy import deepcopy
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, Tag
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
    status: str                                   # applied | empty_reply | no_element | tracking_rejected
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


def _attribute_index(elements, attribute):
    """Index every occurrence, including fragment roots (Tag equality is structural)."""
    owners = {}
    for root in elements:
        for element in [root, *root.find_all(True)]:
            if element.has_attr(attribute):
                owners.setdefault(element[attribute], []).append(element)
    return owners


def _marker_errors(owners, expected):
    errors = []
    for token, elements in owners.items():
        if token not in expected:
            errors.append(f"marker_unexpected:{token}")
        if len(elements) != 1:
            errors.append(f"marker_duplicate:{token}")
    return errors


def _restore_tracking(elements, expected, original_ids):
    """Validate an assembled candidate and recover missing markers only by unique ID.

    Mutates the candidate only; callers must not publish it until errors are empty.
    Existing unique HTML IDs also detect markers moved to a different element.
    Markers remain the identity anchor for elements without a unique HTML ID.
    """
    owners = _attribute_index(elements, MARKER)
    errors = _marker_errors(owners, expected)
    if errors:
        return [], errors
    candidate_ids = _attribute_index(elements, "id")
    recovered = []
    for token, original in expected.items():
        matches = owners.get(token, [])
        html_id = original.get("id")
        unique_id = bool(html_id) and len(original_ids.get(html_id, [])) == 1
        id_matches = candidate_ids.get(html_id, []) if unique_id else []
        if matches:
            if unique_id and (len(id_matches) != 1 or id_matches[0] is not matches[0]):
                errors.append(f"marker_identity_changed:{token}")
            continue
        if len(id_matches) != 1 or id_matches[0].has_attr(MARKER):
            errors.append(f"marker_lost:{token}")
            continue
        id_matches[0][MARKER] = token
        recovered.append(f"marker_recovered:{token}")
    return recovered, errors


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

    # Fast path: if every top-level reply tag directly matches an existing visible element
    # (no new wrapper tags or newly inserted sibling elements), update them in-place
    # so all original newlines, indentation, comments, and hidden tags remain untouched.
    temp_used: set[int] = set()
    direct_matches: list[tuple[Tag, Tag]] = []
    all_direct = True
    for top_reply in reply_tags:
        m = id_map.get(id(top_reply))
        if m is None:
            m = _match_real_element(top_reply, visible_pool, temp_used)
        if m is None:
            all_direct = False
            break
        temp_used.add(id(m))
        direct_matches.append((top_reply, m))

    if all_direct:
        for top_reply, m in direct_matches:
            m.name = top_reply.name
            for k, v in top_reply.attrs.items():
                if k != MARKER:
                    m[k] = v
            if not _is_placeholder(top_reply) and top_reply.find(True):
                _reconcile_container(m, top_reply)
        return

    comments_before: list[Comment] = []
    comments_after: list[Comment] = []
    seen_visible = False
    for c in list(real_container.children):
        if isinstance(c, Tag) and c.name not in HIDDEN_IN_PROMPT_TAGS:
            seen_visible = True
        elif isinstance(c, Comment):
            if seen_visible:
                comments_after.append(c.extract())
            else:
                comments_before.append(c.extract())

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
                wrapper.append("\n")
                for el in remaining:
                    wrapper.append(el.extract())
                    wrapper.append("\n")
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
        wrapper.append("\n")
        for child in child_tags:
            for hydrated in hydrate_node(child):
                wrapper.append(hydrated)
                wrapper.append("\n")
        return [wrapper]

    new_children: list[Tag] = []
    for top_reply in reply_tags:
        new_children.extend(hydrate_node(top_reply))

    # Preserve any original visible elements the LLM omitted (e.g. <link> tags) and all hidden tags (<script>, <style>, etc.)
    leftover_visible = [el.extract() for el in visible_pool if id(el) not in used_ids]
    preserved_hidden = [el.extract() for el in hidden_children]

    real_container.clear()
    real_container.append("\n")
    for el in comments_before:
        real_container.append(el)
        real_container.append("\n")
    for el in new_children + leftover_visible + preserved_hidden:
        real_container.append(el)
        real_container.append("\n")
    for el in comments_after:
        real_container.append(el)
        real_container.append("\n")


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




def _preserve_attribute_order(original_tag: Tag, replacement_tag: Tag) -> None:
    if original_tag.name == replacement_tag.name and original_tag.attrs:
        ordered_attrs = {}
        for attr in original_tag.attrs:
            if attr in replacement_tag.attrs:
                ordered_attrs[attr] = replacement_tag.attrs[attr]
        for attr, val in replacement_tag.attrs.items():
            if attr not in ordered_attrs:
                ordered_attrs[attr] = val
        replacement_tag.attrs = ordered_attrs


def apply_reply(target, reply, token):
    """Apply a reply only after tracking checks, leaving the live tree intact on rejection."""
    text = clean_reply(reply)
    if not text:
        return PatchResult(False, "empty_reply")
    elements = [c for c in BeautifulSoup(text, "html.parser").contents if isinstance(c, Tag)]
    if not elements:
        return PatchResult(False, "no_element")

    warnings = [f"elements_added:{len(elements)}"] if len(elements) > 1 else []

    document = target
    while document.parent is not None:
        document = document.parent
    original_markers = _attribute_index([target], MARKER)
    if target.get(MARKER) != token:
        return PatchResult(False, "tracking_rejected", ["target_marker_mismatch"])
    expected = {key: owners[0] for key, owners in original_markers.items()}
    # Check the original document too: an outside duplicate would make the next
    # runner lookup ambiguous even if the replacement itself had valid markers.
    document_markers = _attribute_index([document], MARKER)
    errors = [f"marker_duplicate:{key}" for key in expected if len(document_markers[key]) != 1]
    errors += _marker_errors(_attribute_index(elements, MARKER), expected)
    if errors:
        return PatchResult(False, "tracking_rejected", warnings + errors)
    original_ids = _attribute_index([document], "id")

    if target.name in {"html", "body"}:
        # The prompt collapses descendants; validate the expanded result, not
        # marker absence in that shortened reply. Work on a copy for rollback.
        candidate = deepcopy(target)
        _apply_document_patch(candidate, elements)
        recovered, errors = _restore_tracking([candidate], expected, original_ids)
        if errors:
            return PatchResult(False, "tracking_rejected", warnings + errors)
        target.replace_with(candidate)
        return PatchResult(True, "applied", warnings + recovered)

    replacement_target = _marker_owner(elements, token)
    # For an ID-less target only, a sole same-tag root identifies its slot.
    # Descendants never use this fallback: their shape/order may have changed.
    if (
        replacement_target is None and not target.get("id") and len(elements) == 1
        and elements[0].name == target.name and not elements[0].has_attr(MARKER)
    ):
        elements[0][MARKER] = token
        warnings.append("marker_readded")
    recovered, errors = _restore_tracking(elements, expected, original_ids)
    if errors:
        return PatchResult(False, "tracking_rejected", warnings + errors)
    warnings += recovered
    replacement_target = _marker_owner(elements, token)

    if replacement_target.name != target.name:
        warnings.append("tag_changed")
    else:
        _preserve_attribute_order(target, replacement_target)

    if replacement_target.get("id") != target.get("id"):
        warnings.append("id_changed")
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
