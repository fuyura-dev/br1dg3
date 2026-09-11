import networkx as nx
from bs4 import BeautifulSoup


class SDGBuilder:
    def __init__(self, html: str):
        self.html = html
        self.soup = BeautifulSoup(html, "html.parser")
        self.graph = nx.DiGraph()

        self._build_nodes()
        self._build_edges()

    def _build_nodes(self):
        pass

    def _build_edges(self):
        pass

