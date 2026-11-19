from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from app.services.sdg.builder import ElementIds

# Relations that are SEQUENCES (tab order, neighbours in a group), not dependencies: left out of the ordering view.
SEQUENCE_RELATIONS = {"focus_order", "name_group"}

# Reference relations are stored referrer -> referent (input -> its label, button -> its panel).
# The referent must be repaired first, so the ordering view reverses them.
REFERENCE_RELATIONS = {
    "aria_labelledby", "aria_describedby", "aria_controls", "aria_owns", "aria_errormessage",
    "id_reference",
}


def dependency_view(
    graph: nx.MultiDiGraph, element_ids: "ElementIds | None" = None,
) -> nx.DiGraph:
    """Build a separate scheduling graph with prerequisite -> dependent edges.

    When element identities are supplied, include every direct DOM parent-child
    edge. Transitive paths then order ancestors before descendants. These edges
    never enter the SDG used for prompt context or semantic measurements.
    Node insertion order must be the original document order for tie-breaking.
    """
    view = nx.DiGraph()
    view.add_nodes_from(graph.nodes)                # keeps document order for tie-breaking
    for u, v, relation in graph.edges(data="relation"):
        if relation in SEQUENCE_RELATIONS:
            continue
        if relation in REFERENCE_RELATIONS:
            u, v = v, u
        view.add_edge(u, v)

    if element_ids is not None:
        for node in graph:
            parent = element_ids.element(node).parent
            parent_id = element_ids.get(parent)
            if parent_id in view:
                view.add_edge(parent_id, node)
    return view


def order_violations_by_dependency(
    graph: nx.DiGraph,
    violated_node_ids: list[str],
) -> list[str]:
    """Order targets once, resolving dependency cycles in document order.

    Collapse strongly connected components before selecting targets, so paths
    through unaffected elements still impose ordering. Between independent
    target groups, prefer the earliest target in the original document. Inside
    a cycle, no order can satisfy every edge; use document order explicitly.
    """
    targets = set(violated_node_ids).intersection(graph)
    if not targets:
        return []

    document_order = {node: index for index, node in enumerate(graph)}
    components = nx.condensation(graph)
    mapping = components.graph["mapping"]
    groups: dict[int, list[str]] = {}
    for node in graph:
        if node in targets:
            groups.setdefault(mapping[node], []).append(node)

    # Project onto groups containing repair targets. Traverse healthy groups,
    # but stop at the next target group: its outgoing paths are handled below.
    # Healthy elements must not become tasks or delay an independent target.
    schedule = nx.DiGraph()
    schedule.add_nodes_from(groups)
    for group in groups:
        frontier = list(components.successors(group))
        seen = set()
        while frontier:
            following = frontier.pop()
            if following in seen:
                continue
            seen.add(following)
            if following in groups:
                schedule.add_edge(group, following)
            else:
                frontier.extend(components.successors(following))

    ordered_groups = nx.lexicographical_topological_sort(
        schedule, key=lambda group: document_order[groups[group][0]],
    )
    return [node for group in ordered_groups for node in groups[group]]

