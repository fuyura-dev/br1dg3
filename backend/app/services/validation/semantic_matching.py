"""Deterministic correspondence for the SDG preservation proxy.

Repair markers, graph edges and preservation scores do not guide matching.
Unmatched endpoints remain unresolved; matches do not prove semantic identity.
"""

import json
from collections import Counter, defaultdict
from hashlib import sha256

from bs4 import Comment, Tag

# Reference changes are what the metric compares, not identity evidence.
REFERENCE_ATTRIBUTES = {
    "id", "for", "form", "headers", "list", "popovertarget", "data-br1dg3",
    "aria-labelledby", "aria-describedby", "aria-controls", "aria-owns", "aria-errormessage",
}


def _fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _index(builder):
    nodes = list(builder.graph.nodes)
    own, subtree, children, ids = {}, {}, defaultdict(list), defaultdict(list)
    for node in nodes:
        tag = builder.element_to_id.element(node)
        parent = builder.element_to_id.get(tag.parent)
        children[parent].append(node)
        if tag.get("id"):
            ids[str(tag["id"])].append(node)
        attrs = {key: value for key, value in tag.attrs.items()
                 if key not in REFERENCE_ATTRIBUTES and not key.startswith("data-br1dg3-")}
        if isinstance(attrs.get("href"), str) and attrs["href"].strip().startswith("#"):
            attrs["href"] = "#fragment"  # Compare the target through the extracted edge.
        text = [" ".join(str(item).split()) for item in tag.children
                if not isinstance(item, (Tag, Comment)) and str(item).strip()]
        own[node] = _fingerprint((tag.name, attrs, text))
    for node in reversed(nodes):
        tag = builder.element_to_id.element(node)
        content = []
        for item in tag.children:
            if isinstance(item, Tag):
                content.append(("element", subtree[builder.element_to_id[item]]))
            elif not isinstance(item, Comment) and str(item).strip():
                content.append(("text", " ".join(str(item).split())))
        subtree[node] = _fingerprint((own[node], content))
    return nodes, own, subtree, children, ids


def _unique_pairs(left, right, left_key, right_key):
    a, b = defaultdict(list), defaultdict(list)
    for node in left:
        a[left_key[node]].append(node)
    for node in right:
        b[right_key[node]].append(node)
    return [(values[0], b[key][0]) for key, values in a.items() if len(values) == 1 and len(b[key]) == 1]


def match_elements(original, repaired):
    a, own_a, tree_a, children_a, ids_a = _index(original)
    b, own_b, tree_b, children_b, ids_b = _index(repaired)
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

    if original.html == repaired.html:
        for old, new in zip(a, b, strict=True):
            bind(old, new, "identical_prepared_document")
    else:
        for value, old in ids_a.items():
            new = ids_b.get(value, [])
            if len(old) == len(new) == 1:
                bind(old[0], new[0], "unique_id")

        for old, new in _unique_pairs(a, b, tree_a, tree_b):
            if old not in mapping and new not in reverse:
                bind_tree(old, new, "unique_normalized_subtree")

        changed = True
        while changed:
            changed = False
            for old_parent, new_parent in [(None, None), *list(mapping.items())]:
                if old_parent is not None and tree_a[old_parent] == tree_b[new_parent]:
                    changed = bind_tree(old_parent, new_parent, "subtree_in_matched_parent") or changed
                old_children, new_children = children_a[old_parent], children_b[new_parent]
                for old, new in _unique_pairs(old_children, new_children, tree_a, tree_b):
                    if old not in mapping and new not in reverse:
                        changed = bind_tree(old, new, "subtree_in_matched_parent") or changed
                for old, new in _unique_pairs(old_children, new_children, own_a, own_b):
                    changed = bind(old, new, "node_in_matched_parent") or changed

    evidence = {
        "policy": "unique_ids_then_normalized_subtrees_then_matched_parent_v1",
        "matched_nodes": len(mapping), "original_nodes": len(a), "candidate_nodes": len(b),
        "unmatched_original_nodes": [node for node in a if node not in mapping],
        "unmatched_candidate_nodes": [node for node in b if node not in reverse],
        "duplicate_original_ids": sorted(key for key, values in ids_a.items() if len(values) > 1),
        "duplicate_candidate_ids": sorted(key for key, values in ids_b.items() if len(values) > 1),
        "methods": dict(Counter(reasons.values())),
        "pairs": [{"original": old, "candidate": mapping[old], "basis": reasons[old]} for old in a if old in mapping],
    }
    return mapping, evidence
