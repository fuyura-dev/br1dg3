import re
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from bs4.dammit import EntitySubstitution
from bs4.formatter import HTMLFormatter

from app.services.repair.root_view import (
    CONTENT_PREFIX,
    HIDDEN_ROOT_TAGS,
    RootPatchError,
    content_references,
)

MARKER = "data-br1dg3"       # temporary tracking attribute: data-br1dg3="v1", "v2", ...


class _AsWritten(HTMLFormatter):
    """Like str(tag), but keeps the attribute order and writes <input ...> instead of <input .../>."""

    def attributes(self, tag):
        return [(k, None if v == "" else v) for k, v in tag.attrs.items()]   # None -> bare attribute


_AS_WRITTEN = _AsWritten(void_element_close_prefix="", entity_substitution=EntitySubstitution.substitute_xml)


def outer_html(node):
    if isinstance(node, NavigableString):
        return node.output_ready(formatter=_AS_WRITTEN)
    return node.decode(formatter=_AS_WRITTEN)


def is_shown_in_shallow_prompt(attribute: str) -> bool:
    """Shared visibility policy for shortened root markup and context snippets."""
    return attribute not in {"class", "style"} and not attribute.startswith("data-")


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
    status: str                                   # applied | empty_reply | no_element | tracking_rejected | patch_rejected
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


HIDDEN_IN_PROMPT_TAGS = HIDDEN_ROOT_TAGS


def _resolve_content_references(target, elements):
    """Expand once on reply copies; retain source identity for reconstruction."""
    references = content_references(target)
    resolved, seen = {}, set()
    for element in elements:
        for node in list(element.descendants):
            if not isinstance(node, NavigableString) or CONTENT_PREFIX not in str(node):
                continue
            key = str(node)
            if not isinstance(node, Comment) or key not in references:
                raise RootPatchError("unknown_content_reference")
            if key in seen:
                raise RootPatchError("duplicate_content_reference")
            seen.add(key)
            reference = references[key]
            clone = deepcopy(reference.node)
            node.replace_with(clone)
            resolved[id(clone)] = reference
    return resolved


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

    # Fall back to a same-tag placeholder or matching text, in document order.
    for el in pool:
        if id(el) in used_ids or el.name != reply_el.name:
            continue
        if _is_placeholder(reply_el):
            return el
        if not _is_placeholder(reply_el) and el.get_text(strip=True) == reply_el.get_text(strip=True):
            return el

    return None


def _literal_key(node):
    # Comments are exact; formatting-only whitespace differences in an echoed
    # text node do not justify duplicating the original words.
    return type(node), str(node) if isinstance(node, Comment) else " ".join(str(node).split())


def _restore_omitted_content(container, original_children, used_ids, emitted_literals, referenced_ids):
    """Keep omitted nodes in their original parent when neighbours define a slot.

    Explicitly echoed text/comments consume one original occurrence each. Use
    the original node to retain its whitespace/entity value, without duplication.
    A wrapper does not implicitly take omitted adjacent text. Conflicting anchors
    or a mixture of unmatched old/new text reject the candidate instead of guessing.
    """
    echoes = defaultdict(deque)
    for node in emitted_literals:
        echoes[_literal_key(node)].append(node)
    for node in original_children:
        if not isinstance(node, Tag) and echoes[_literal_key(node)]:
            if id(node) in referenced_ids:
                continue
            echoes[_literal_key(node)].popleft().replace_with(node)
            used_ids.add(id(node))
    if any(id(node) in referenced_ids and echoes[_literal_key(node)] for node in original_children):
        raise RootPatchError("duplicate_content_reference")

    def meaningful_text(node):
        return isinstance(node, NavigableString) and not isinstance(node, Comment) and bool(str(node).strip())

    missing_text = any(meaningful_text(node) and id(node) not in used_ids for node in original_children)
    new_text = any(meaningful_text(node) for remaining in echoes.values() for node in remaining)
    if missing_text and new_text:
        raise RootPatchError("ambiguous_text_rewrite")

    def anchor(node):
        while node.parent is not container:
            if node.parent is None:
                raise RootPatchError("ambiguous_content_placement")
            node = node.parent
        return node

    pending, previous = [], None
    for node in original_children:
        if id(node) in used_ids:
            if pending:
                following = anchor(node)
                if previous is not None:
                    preceding = anchor(previous)
                    positions = {id(child): i for i, child in enumerate(container.contents)}
                    if positions[id(preceding)] >= positions[id(following)]:
                        raise RootPatchError("ambiguous_content_placement")
                following.insert_before(*pending)
                pending = []
            previous = node
        else:
            pending.append(node)
    if pending:
        if previous is not None:
            anchor(previous).insert_after(*pending)
        else:
            container.extend(pending)


def _reconcile_container(real_container: Tag, reply_container: Tag, resolved=None) -> None:
    """Reconcile body/section content with the LLM's reply
    by expanding '…' placeholders back to their original DOM nodes while keeping any
    new elements, wrappers, or attribute changes returned by the LLM."""
    if _is_placeholder(reply_container):
        return
    resolved = resolved or {}

    original_children = list(real_container.contents)
    real_children = [c for c in original_children if isinstance(c, Tag)]
    visible_pool = [c for c in real_children if c.name not in HIDDEN_IN_PROMPT_TAGS]

    used_ids: set[int] = set()
    reserved_ids: set[int] = set()
    emitted_literals = []
    referenced_ids = set()

    # First pass: pre-claim exact ID matches anywhere in reply_container so nested
    # elements (e.g. <div id="__nuxt">…</div> inside <main>) claim their real node.
    id_map: dict[int, Tag] = {}
    for candidate in reply_container.find_all(True):
        cid = candidate.get("id")
        if cid:
            for real_el in visible_pool:
                if id(real_el) not in reserved_ids and real_el.get("id") == cid:
                    id_map[id(candidate)] = real_el
                    reserved_ids.add(id(real_el))
                    break
    for candidate in reply_container.descendants:
        reference = resolved.get(id(candidate))
        if reference is not None and reference.parent is real_container:
            reserved_ids.add(id(reference.node))

    def hydrate_node(reply_node):
        reference = resolved.get(id(reply_node))
        if reference is not None:
            if reference.parent is not real_container:
                raise RootPatchError("content_reference_scope")
            used_ids.add(id(reference.node))
            referenced_ids.add(id(reference.node))
            return [reference.node.extract()]
        if not isinstance(reply_node, Tag):
            cloned = deepcopy(reply_node)
            emitted_literals.append(cloned)
            return [cloned]
        matched = id_map.get(id(reply_node))
        if matched is None:
            matched = _match_real_element(reply_node, visible_pool, used_ids | reserved_ids)

        if matched is not None:
            used_ids.add(id(matched))
            matched.name = reply_node.name
            for k, v in reply_node.attrs.items():
                if k != MARKER:
                    matched[k] = v
            has_reference = any(id(node) in resolved for node in reply_node.descendants)
            if not _is_placeholder(reply_node) and (reply_node.find(True) or has_reference):
                _reconcile_container(matched, reply_node, resolved)
            return [matched.extract()]

        # A new collapsed wrapper carries the remaining original content,
        # including text, comments and hidden nodes, in original order.
        if _is_placeholder(reply_node):
            remaining = [node for node in original_children if id(node) not in used_ids | reserved_ids]
            if remaining:
                wrapper = deepcopy(reply_node)
                wrapper.clear()
                wrapper.attrs.pop(MARKER, None)
                for node in remaining:
                    used_ids.add(id(node))
                    wrapper.append(node.extract())
                return [wrapper]
            return []

        # New markup retains mixed content, not just child element tags.
        wrapper = deepcopy(reply_node)
        wrapper.clear()
        wrapper.attrs.pop(MARKER, None)
        for child in reply_node.contents:
            for hydrated in hydrate_node(child):
                wrapper.append(hydrated)
        return [wrapper]

    new_children = []
    for top_reply in reply_container.contents:
        new_children.extend(hydrate_node(top_reply))

    real_container.clear()
    real_container.extend(new_children)
    _restore_omitted_content(real_container, original_children, used_ids, emitted_literals, referenced_ids)


def _reconcile_root_attributes(original: Tag, reply: Tag) -> None:
    """An explicit root reply removes omitted shown attributes, preserving hidden ones."""
    for name in list(original.attrs):
        if is_shown_in_shallow_prompt(name) and name not in reply.attrs:
            del original[name]
    for name, value in reply.attrs.items():
        if name != MARKER:
            original[name] = value


def _apply_title_patch(html: Tag, reply_head: Tag, resolved) -> str | None:
    """Update one document title without reconstructing unrelated head content."""
    titles = reply_head.find_all("title", recursive=False)
    if len(titles) > 1:
        return "multiple_reply_titles"
    if not titles or _is_placeholder(titles[0]):
        return None
    reply_title = titles[0]
    head = html.find("head", recursive=False)
    original_titles = head.find_all("title", recursive=False) if head is not None else []
    if len(original_titles) > 1:
        return "ambiguous_existing_titles"
    for node in reply_title.descendants:
        reference = resolved.get(id(node))
        if reference is not None and (not original_titles or reference.parent is not original_titles[0]):
            return "content_reference_scope"
    if head is None:
        head = BeautifulSoup("<head></head>", "html.parser").head
        body = html.find("body", recursive=False)
        if body is not None:
            body.insert_before(head)
        else:
            html.insert(0, head)
    if not original_titles:
        head.append(deepcopy(reply_title))
        return None
    title = original_titles[0]
    for name, value in reply_title.attrs.items():
        if name != MARKER:
            title[name] = value
    title.clear()
    title.extend(deepcopy(list(reply_title.contents)))
    return None


def _apply_document_patch(target: Tag, elements: list[Tag], resolved) -> str | None:
    """Reconcile an <html> or <body> reply with the live BeautifulSoup tree by expanding
    collapsed '…' placeholders back to their original DOM nodes."""
    if target.name == "html":
        reply_html = next((e for e in elements if e.name == "html"), None)
        if reply_html is not None:
            _reconcile_root_attributes(target, reply_html)
            reply_head = reply_html.find("head", recursive=False)
            if reply_head is not None:
                error = _apply_title_patch(target, reply_head, resolved)
                if error:
                    return error
            reply_body = reply_html.find("body", recursive=False)
            if reply_body is not None and target.body is not None:
                _reconcile_root_attributes(target.body, reply_body)
                _reconcile_container(target.body, reply_body, resolved)
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
        _reconcile_root_attributes(real_body, reply_body)

    _reconcile_container(real_body, reply_body, resolved)




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


def apply_reply(target, reply, token, *, clean=True):
    """Apply a reply only after tracking checks, leaving the live tree intact on rejection."""
    text = clean_reply(reply) if clean else reply.strip()
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
        try:
            resolved = _resolve_content_references(candidate, elements)
            error = _apply_document_patch(candidate, elements, resolved)
        except RootPatchError as exc:
            error = str(exc)
        if error:
            return PatchResult(False, "patch_rejected", warnings + [error])
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


def apply_block_reply(block, reply, token):
    """Replace one selected parent subtree after validating every tracked owner.

    The block root itself need not be a scheduled target. Its replacement slot
    is selected by the backend, never by a model-supplied selector or ID.
    """
    parsed = BeautifulSoup(reply, "html.parser")
    elements = [node for node in parsed.contents if isinstance(node, Tag)]
    if len(elements) != 1:
        return PatchResult(False, "patch_rejected", ["block_requires_one_root"])
    document = block
    while document.parent is not None:
        document = document.parent
    originals = _attribute_index([block], MARKER)
    if len(originals.get(token, [])) != 1:
        return PatchResult(False, "tracking_rejected", ["target_marker_mismatch"])
    expected = {key: owners[0] for key, owners in originals.items()}
    document_markers = _attribute_index([document], MARKER)
    errors = [f"marker_duplicate:{key}" for key in expected if len(document_markers[key]) != 1]
    errors += _marker_errors(_attribute_index(elements, MARKER), expected)
    if errors:
        return PatchResult(False, "tracking_rejected", errors)
    recovered, errors = _restore_tracking(elements, expected, _attribute_index([document], "id"))
    if errors:
        return PatchResult(False, "tracking_rejected", errors)
    _preserve_attribute_order(block, elements[0])
    block.replace_with(elements[0])
    return PatchResult(True, "applied", recovered)


def strip_markers(html):
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(attrs={MARKER: True}):
        del element[MARKER]
    return outer_html(soup)
