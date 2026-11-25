"""Deterministic correspondence for the SDG preservation proxy.

Repair markers, graph edges and preservation scores do not guide matching.
Matches establish operational correspondence, not proof of semantic identity.
"""

import json
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import pairwise

from bs4 import Comment, Tag

# Reference changes are what the metric compares, not identity evidence.
REFERENCE_ATTRIBUTES = {
    "id", "for", "form", "headers", "list", "popovertarget", "data-br1dg3",
    "aria-labelledby", "aria-describedby", "aria-controls", "aria-owns", "aria-errormessage",
}
LABEL_ATTRIBUTES = {"aria-label", "alt", "title"}
REPAIR_ATTRIBUTES = LABEL_ATTRIBUTES | {"role", "lang", "type"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
EMPTY_FILL_TAGS = HEADING_TAGS | {"label"}


def _fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _direct_text(tag):
    return [
        " ".join(str(item).split())
        for item in tag.children
        if not isinstance(item, (Tag, Comment)) and str(item).strip()
    ]


def _index(
    builder,
    *,
    ignored_attributes=(),
    normalize_headings=False,
    drop_empty_attributes=False,
    ignore_empty_fill_text=False,
):
    nodes = list(builder.graph.nodes)
    own, subtree, children, parent_of, ids = {}, {}, defaultdict(list), {}, defaultdict(list)
    for node in nodes:
        tag = builder.element_to_id.element(node)
        parent = builder.element_to_id.get(tag.parent)
        parent_of[node] = parent
        children[parent].append(node)
        if tag.get("id"):
            ids[str(tag["id"])].append(node)
        attrs = {}
        for key, value in tag.attrs.items():
            if key in REFERENCE_ATTRIBUTES or key in ignored_attributes or key.startswith("data-br1dg3-"):
                continue
            if drop_empty_attributes and value in ("", []):
                continue
            attrs[key] = value
        if isinstance(attrs.get("href"), str) and attrs["href"].strip().startswith("#"):
            attrs["href"] = "#fragment"  # Compare the target through the extracted edge.
        name = "<heading>" if (normalize_headings and tag.name in HEADING_TAGS) else tag.name
        text = [] if (ignore_empty_fill_text and tag.name in EMPTY_FILL_TAGS) else _direct_text(tag)
        own[node] = _fingerprint((name, attrs, text))
    for node in reversed(nodes):
        tag = builder.element_to_id.element(node)
        content = []
        for item in tag.children:
            if isinstance(item, Tag):
                content.append(("element", subtree[builder.element_to_id[item]]))
            elif not isinstance(item, Comment) and str(item).strip():
                content.append(("text", " ".join(str(item).split())))
        subtree[node] = _fingerprint((own[node], content))
    return nodes, own, subtree, children, parent_of, ids


def _unique_pairs(left, right, left_key, right_key):
    a, b = defaultdict(list), defaultdict(list)
    for node in left:
        a[left_key[node]].append(node)
    for node in right:
        b[right_key[node]].append(node)
    return [(values[0], b[key][0]) for key, values in a.items() if len(values) == 1 and len(b[key]) == 1]


def match_elements(original, repaired):
    a, own_a, tree_a, children_a, parent_a, ids_a = _index(original)
    b, own_b, tree_b, children_b, parent_b, ids_b = _index(repaired)
    mapping, reverse, reasons = {}, {}, {}
    expanded = set()

    def bind(left, right, reason):
        if left in mapping or right in reverse:
            return False
        mapping[left], reverse[right], reasons[left] = right, left, reason
        return True

    def bind_tree(left, right, reason):
        if (left, right) in expanded:
            return False
        expanded.add((left, right))
        pairs, pending = [], [(left, right)]
        while pending:
            old, new = pending.pop()
            if mapping.get(old, new) != new or reverse.get(new, old) != old:
                return False
            pairs.append((old, new))
            old_children, new_children = children_a[old], children_b[new]
            if len(old_children) != len(new_children):
                return False
            pending.extend(zip(old_children, new_children, strict=True))
        changed = False
        for old, new in pairs:
            expanded.add((old, new))
            changed = bind(old, new, reason) or changed
        return changed

    def bind_unique_in_parents(parents, key_a, key_b, reason, *, predicate=None):
        changed = False
        for old_parent, new_parent in parents:
            # Include already-bound siblings when checking uniqueness.
            for old, new in _unique_pairs(children_a[old_parent], children_b[new_parent], key_a, key_b):
                if predicate is None or predicate(old, new):
                    changed = bind(old, new, reason) or changed
        return changed

    def bind_parents_from_children(key_a, key_b, reason):
        changed = False
        for old_parent in reversed(a):
            if old_parent in mapping:
                continue
            cand_parents = {parent_b[mapping[c]] for c in children_a[old_parent] if c in mapping}
            if len(cand_parents) != 1:
                continue
            new_parent = next(iter(cand_parents))
            if new_parent is None or new_parent in reverse or key_a[old_parent] != key_b[new_parent]:
                continue
            orig_parents = {parent_a[reverse[c]] for c in children_b[new_parent] if c in reverse}
            if orig_parents == {old_parent}:
                changed = bind(old_parent, new_parent, reason) or changed
        return changed

    def monotonic_gaps(old_parent, new_parent):
        old_children, new_children = children_a[old_parent], children_b[new_parent]
        new_pos = {node: idx for idx, node in enumerate(new_children)}
        anchors, last_j = [], -1
        for i, node in enumerate(old_children):
            if node in mapping:
                target = mapping[node]
                if target not in new_pos or new_pos[target] <= last_j:
                    return []
                last_j = new_pos[target]
                anchors.append((i, last_j))
        bounds = [(-1, -1), *anchors, (len(old_children), len(new_children))]
        gaps = []
        for (i0, j0), (i1, j1) in pairwise(bounds):
            slice_a, slice_b = old_children[i0 + 1 : i1], new_children[j0 + 1 : j1]
            if slice_a and slice_b and all(n not in mapping for n in slice_a) and all(n not in reverse for n in slice_b):
                gaps.append((slice_a, slice_b))
        return gaps

    def bind_monotonic_gaps(key_a, key_b, reason, *, allow_identical_multi=False):
        changed = False
        for old_parent, new_parent in list(mapping.items()):
            for gap_a, gap_b in monotonic_gaps(old_parent, new_parent):
                if len(gap_a) != len(gap_b):
                    continue
                if len(gap_a) == 1:
                    if key_a[gap_a[0]] == key_b[gap_b[0]]:
                        changed = bind(gap_a[0], gap_b[0], reason) or changed
                elif allow_identical_multi:
                    keys_a = {key_a[n] for n in gap_a}
                    keys_b = {key_b[n] for n in gap_b}
                    if len(keys_a) == 1 and keys_a == keys_b:
                        for old, new in zip(gap_a, gap_b, strict=True):
                            changed = bind(old, new, reason) or changed
        return changed

    if original.html == repaired.html:
        for old, new in zip(a, b, strict=True):
            bind(old, new, "identical_prepared_document")
    else:
        _, rel_own_a, rel_tree_a, _, _, _ = _index(original, ignored_attributes=LABEL_ATTRIBUTES)
        _, rel_own_b, rel_tree_b, _, _, _ = _index(repaired, ignored_attributes=LABEL_ATTRIBUTES)
        _, head_own_a, head_tree_a, _, _, _ = _index(
            original, ignored_attributes=LABEL_ATTRIBUTES, normalize_headings=True
        )
        _, head_own_b, head_tree_b, _, _, _ = _index(
            repaired, ignored_attributes=LABEL_ATTRIBUTES, normalize_headings=True
        )
        _, attr_own_a, attr_tree_a, _, _, _ = _index(
            original, ignored_attributes=REPAIR_ATTRIBUTES, normalize_headings=True
        )
        _, attr_own_b, attr_tree_b, _, _, _ = _index(
            repaired, ignored_attributes=REPAIR_ATTRIBUTES, normalize_headings=True
        )
        _, empty_own_a, empty_tree_a, _, _, _ = _index(
            original, ignored_attributes=REPAIR_ATTRIBUTES, normalize_headings=True, drop_empty_attributes=True
        )
        _, empty_own_b, empty_tree_b, _, _, _ = _index(
            repaired, ignored_attributes=REPAIR_ATTRIBUTES, normalize_headings=True, drop_empty_attributes=True
        )
        _, fill_own_a, _, _, _, _ = _index(
            original, ignored_attributes=REPAIR_ATTRIBUTES, drop_empty_attributes=True, ignore_empty_fill_text=True
        )
        _, fill_own_b, _, _, _, _ = _index(
            repaired, ignored_attributes=REPAIR_ATTRIBUTES, drop_empty_attributes=True, ignore_empty_fill_text=True
        )

        for value, old in ids_a.items():
            new = ids_b.get(value, [])
            if len(old) == len(new) == 1:
                bind(old[0], new[0], "unique_id")

        for old, new in _unique_pairs(a, b, tree_a, tree_b):
            if old not in mapping and new not in reverse:
                bind_tree(old, new, "unique_normalized_subtree")

        def is_empty_heading_or_label(old, _new):
            tag = original.element_to_id.element(old)
            return tag.name in EMPTY_FILL_TAGS and not _direct_text(tag)

        changed = True
        while changed:
            changed = False
            # 1. Strong top-down matching.
            for old_parent, new_parent in [(None, None), *list(mapping.items())]:
                if old_parent is not None and tree_a[old_parent] == tree_b[new_parent]:
                    changed = bind_tree(old_parent, new_parent, "subtree_in_matched_parent") or changed
                old_children, new_children = children_a[old_parent], children_b[new_parent]
                for old, new in _unique_pairs(old_children, new_children, tree_a, tree_b):
                    if old not in mapping and new not in reverse:
                        changed = bind_tree(old, new, "subtree_in_matched_parent") or changed
                for old, new in _unique_pairs(old_children, new_children, own_a, own_b):
                    changed = bind(old, new, "node_in_matched_parent") or changed
            if changed:
                continue

            # 2. Strong bottom-up parent consensus from already-matched children.
            changed = bind_parents_from_children(own_a, own_b, "parent_of_matched_children")
            if changed:
                continue

            # 3. Label-attribute relaxation (aria-label, alt, title).
            matched_parents = list(mapping.items())
            changed = bind_unique_in_parents(
                matched_parents, rel_tree_a, rel_tree_b, "label_attributes_in_matched_parent"
            )
            if changed:
                continue
            for old, new in _unique_pairs(a, b, rel_tree_a, rel_tree_b):
                changed = bind(old, new, "unique_label_relaxed_subtree") or changed
            if changed:
                continue
            changed = bind_unique_in_parents(
                matched_parents, rel_own_a, rel_own_b, "label_own_in_matched_parent"
            )
            if not changed:
                changed = bind_parents_from_children(rel_own_a, rel_own_b, "label_parent_of_matched_children")
            if changed:
                continue

            # 4. Heading-level retagging (h1-h6) for heading-order/page-has-heading-one repairs.
            changed = bind_unique_in_parents(
                matched_parents, head_tree_a, head_tree_b, "heading_level_subtree_in_matched_parent"
            )
            if not changed:
                changed = bind_unique_in_parents(
                    matched_parents, head_own_a, head_own_b, "heading_level_own_in_matched_parent"
                )
            if not changed:
                for old, new in _unique_pairs(a, b, head_tree_a, head_tree_b):
                    if original.element_to_id.element(old).name in HEADING_TAGS:
                        changed = bind(old, new, "unique_heading_level_subtree") or changed
            if changed:
                continue

            # 5. Repair/cleanup attributes (role, lang, type), deferring empty-attribute removal.
            parents_with_root = [(None, None), *matched_parents]
            changed = bind_unique_in_parents(
                parents_with_root, attr_tree_a, attr_tree_b, "repair_attributes_subtree_in_matched_parent"
            )
            if not changed:
                changed = bind_unique_in_parents(
                    parents_with_root, attr_own_a, attr_own_b, "repair_attributes_own_in_matched_parent"
                )
            if not changed:
                changed = bind_parents_from_children(
                    attr_own_a, attr_own_b, "repair_attributes_parent_of_matched_children"
                )
            if changed:
                continue
            changed = bind_unique_in_parents(
                parents_with_root, empty_tree_a, empty_tree_b, "empty_attributes_subtree_in_matched_parent"
            )
            if not changed:
                changed = bind_unique_in_parents(
                    parents_with_root, empty_own_a, empty_own_b, "empty_attributes_own_in_matched_parent"
                )
            if changed:
                continue

            # 6. Originally-empty heading or label filled with accessible text (exact tag required).
            changed = bind_unique_in_parents(
                matched_parents,
                fill_own_a,
                fill_own_b,
                "empty_heading_or_label_fill",
                predicate=is_empty_heading_or_label,
            )
            if changed:
                continue

            # 7. Monotonic sibling gaps: unique 1-to-1 gap, then exact same-count identical siblings in order.
            changed = bind_monotonic_gaps(empty_own_a, empty_own_b, "anchored_sibling_gap")
            if changed:
                continue
            changed = bind_monotonic_gaps(
                empty_tree_a, empty_tree_b, "same_gap_identical_siblings", allow_identical_multi=True
            )

    evidence = {
        "policy": "unique_ids_then_normalized_subtrees_then_matched_parent_v3",
        "fallback_ignored_attributes": sorted(REPAIR_ATTRIBUTES),
        "matched_nodes": len(mapping), "original_nodes": len(a), "candidate_nodes": len(b),
        "unmatched_original_nodes": [node for node in a if node not in mapping],
        "unmatched_candidate_nodes": [node for node in b if node not in reverse],
        "duplicate_original_ids": sorted(key for key, values in ids_a.items() if len(values) > 1),
        "duplicate_candidate_ids": sorted(key for key, values in ids_b.items() if len(values) > 1),
        "methods": dict(Counter(reasons.values())),
        "pairs": [{"original": old, "candidate": mapping[old], "basis": reasons[old]} for old in a if old in mapping],
    }
    return mapping, evidence
