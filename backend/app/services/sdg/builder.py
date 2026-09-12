import networkx as nx
from bs4 import BeautifulSoup, Tag

from app.services.sdg.extractors.label_input import extract_label_input_edges
from app.services.sdg.extractors.aria import extract_aria_edges

class SDGBuilder:
    def __init__(self, html: str):
        self.html = html
        self.soup = BeautifulSoup(html, "html.parser")
        self.graph = nx.DiGraph()

        self.element_to_id: dict[Tag, str] = {}

        self._build_nodes()
        self._build_edges()


    def _build_nodes(self):
        for index, tag in enumerate(self.soup.find_all(True)):

            node_id = f"node_{index}_{tag.name}"

            self.element_to_id[tag] = node_id

            display_label = f"<{tag.name}>"

            self.graph.add_node(
                node_id,
                tag=tag.name,
                label=display_label,
                has_issue=False
            )


    def _build_edges(self):
        # 1. ARIA References
        aria_edges = extract_aria_edges(self.soup, self.element_to_id)
        self._add_edges(aria_edges)

        # 2. Label-input connections
        label_edges = extract_label_input_edges(self.soup, self.element_to_id)
        self._add_edges(label_edges)


    def to_dict(self) -> dict:
        nodes = []
        for node_id, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "tag": data.get("tag"),
                "label": data.get("label"),
                "has_issue": data.get("has_issue"),
            })

        edges = []
        for source, target, data in self.graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "relation": data.get("relation")
            })

        return {
            "nodes": nodes,
            "edges": edges
        }

    def _add_edges(self, edges: list[tuple]):
        for source, target, relation in edges:
            self.graph.add_edge(source, target, relation=relation)


if __name__ == "__main__":
    sample = """
    <div>
        <label for="search-input">Search Site</label>
        <input type="text" id="search-input">
        <h2 id="modal-title">Delete Account</h2>
        <p id="modal-desc">This action is permanent.</p>
        <button id="del-btn" aria-controls="confirm-modal" aria-describedby="modal-desc">
            Delete
        </button>
        <div id="confirm-modal" role="dialog" aria-labelledby="modal-title">
            Are you sure?
        </div>
    </div>
"""

    builder = SDGBuilder(sample)
    graph_data = builder.to_dict()

    print(f"\nNODES ({len(graph_data['nodes'])})")

    for node in graph_data["nodes"]:
        print(f"  - {node['id']:<18} {node['label']}")

    print(f"\nEDGES ({len(graph_data['edges'])}):")

    for edge in graph_data["edges"]:
        print(f"  - {edge['source']:<18} --[ {edge['relation']:<18} ] -> {edge['target']}")