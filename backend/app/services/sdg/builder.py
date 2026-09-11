import networkx as nx
from bs4 import BeautifulSoup, Tag

from app.services.sdg.extractors.label_input import extract_label_input_edges

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

