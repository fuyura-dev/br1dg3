import networkx as nx


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

