import networkx as nx

# Relations that are SEQUENCES (tab order, neighbours in a group), not dependencies: left out of the ordering view.
SEQUENCE_RELATIONS = {"focus_order", "name_group"}

# Reference relations are stored referrer -> referent (input -> its label, button -> its panel).
# The referent must be repaired first, so the ordering view reverses them.
REFERENCE_RELATIONS = {
    "aria_labelledby", "aria_describedby", "aria_controls", "aria_owns", "aria_errormessage",
    "id_reference",
}


def dependency_view(graph: nx.MultiDiGraph) -> nx.DiGraph:
    """
    A copy of the graph used ONLY to decide the repair order. Every edge means "A must be repaired
    before B"
    """
    view = nx.DiGraph()
    view.add_nodes_from(graph.nodes)                # keeps document order for tie-breaking
    for u, v, relation in graph.edges(data="relation"):
        if relation in SEQUENCE_RELATIONS:
            continue
        if relation in REFERENCE_RELATIONS:
            u, v = v, u
        view.add_edge(u, v)
    return view


def order_violations_by_dependency(
        graph: nx.DiGraph,
        violated_node_ids: list[str]
):
    if not violated_node_ids:
        return []

    valid_nodes = [nid for nid in violated_node_ids if graph.has_node(nid)]
    if not valid_nodes:
        return []

    subgraph = nx.DiGraph()
    subgraph.add_nodes_from(valid_nodes)

    for i, u in enumerate(valid_nodes):
        for v in valid_nodes[i + 1:]:
            if nx.has_path(graph, u, v):
                subgraph.add_edge(u, v)
            elif nx.has_path(graph, v, u):
                subgraph.add_edge(v, u)

    try:
        ordered = list(nx.topological_sort(subgraph))
    except nx.NetworkXUnfeasible:
        ordered = sorted(valid_nodes, key=lambda n: subgraph.in_degree(n))

    return ordered

