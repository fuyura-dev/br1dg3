from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.services.detection.preprocess import preprocess


@dataclass
class StructureResult:
    """Per-document Structural Preservation metrics."""

    tree_edit_distance: int
    original_nodes: int
    repaired_nodes: int
    max_nodes: int
    structure_similarity: float
    structure_preserved: bool
    threshold: float = 0.85
    unparseable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tree_edit_distance": self.tree_edit_distance,
            "original_nodes": self.original_nodes,
            "repaired_nodes": self.repaired_nodes,
            "max_nodes": self.max_nodes,
            "structure_similarity": self.structure_similarity,
            "structure_preserved": self.structure_preserved,
            "threshold": self.threshold,
            "unparseable": self.unparseable,
        }


class TreeNode:
    """Lightweight representation of a DOM element for Tree Edit Distance computation."""

    __slots__ = ("children", "label")

    def __init__(self, label: str, children: list["TreeNode"] | None = None):
        self.label = label
        self.children = children or []


def dom_to_tree(element: Tag) -> TreeNode:
    """Recursively convert a BeautifulSoup Tag and its element children into a TreeNode."""
    children = [dom_to_tree(c) for c in element.children if isinstance(c, Tag)]
    return TreeNode(element.name.lower(), children)


def html_to_tree(html: str | None) -> TreeNode | None:
    """Parse HTML string into a DOM TreeNode.

    Returns None if HTML cannot be parsed or contains no element nodes.
    """
    if not html or not isinstance(html, str) or not html.strip():
        return None
    try:
        soup = BeautifulSoup(preprocess(html), "html.parser")
    except Exception:  # noqa: BLE001
        return None

    elements = [c for c in soup.contents if isinstance(c, Tag)]
    if not elements:
        # Check if find_all finds any tags (e.g. if root is html)
        top = soup.find(True)
        if top is None:
            return None
        elements = [top]

    if len(elements) == 1 and elements[0].name.lower() in {"html", "[document]"}:
        return dom_to_tree(elements[0])

    # Wrap multiple top-level siblings in a common document root node
    return TreeNode("[document]", [dom_to_tree(e) for e in elements])


def count_nodes(node: TreeNode | None) -> int:
    """Return the total number of nodes in the tree |T|."""
    if node is None:
        return 0
    return 1 + sum(count_nodes(c) for c in node.children)


def zss_tree_edit_distance(root1: TreeNode | None, root2: TreeNode | None) -> int:
    """Compute Tree Edit Distance (TED) using the Zhang-Shasha (1989) algorithm.

    Unit costs:
      - Delete node: 1
      - Insert node: 1
      - Rename node: 1 if labels differ, 0 if labels match
    """
    if root1 is None and root2 is None:
        return 0
    if root1 is None:
        return count_nodes(root2)
    if root2 is None:
        return count_nodes(root1)

    nodes1: list[TreeNode] = []
    nodes2: list[TreeNode] = []

    def postorder(node: TreeNode, target: list[TreeNode]) -> None:
        for child in node.children:
            postorder(child, target)
        target.append(node)

    postorder(root1, nodes1)
    postorder(root2, nodes2)

    n1, n2 = len(nodes1), len(nodes2)
    idx1 = {node: i + 1 for i, node in enumerate(nodes1)}
    idx2 = {node: i + 1 for i, node in enumerate(nodes2)}

    def get_lld(nodes: list[TreeNode], idx_map: dict[TreeNode, int]) -> list[int]:
        lld = [0] * (len(nodes) + 1)
        for node in nodes:
            curr = node
            while curr.children:
                curr = curr.children[0]
            lld[idx_map[node]] = idx_map[curr]
        return lld

    lld1 = get_lld(nodes1, idx1)
    lld2 = get_lld(nodes2, idx2)

    def get_keyroots(nodes: list[TreeNode], lld: list[int]) -> list[int]:
        kr: list[int] = []
        seen = set()
        for i in range(len(nodes), 0, -1):
            if lld[i] not in seen:
                seen.add(lld[i])
                kr.append(i)
        kr.reverse()
        return kr

    kr1 = get_keyroots(nodes1, lld1)
    kr2 = get_keyroots(nodes2, lld2)

    labels1 = [node.label for node in nodes1]
    labels2 = [node.label for node in nodes2]

    # Pre-allocate 2D table for fast lookup without tuple dict overhead
    tree_dist = [[0] * (n2 + 1) for _ in range(n1 + 1)]

    for i_kr in kr1:
        for j_kr in kr2:
            l1 = lld1[i_kr]
            l2 = lld2[j_kr]
            m_rows = i_kr - l1 + 2
            m_cols = j_kr - l2 + 2
            fd = [[0] * m_cols for _ in range(m_rows)]

            for i in range(1, m_rows):
                fd[i][0] = i
            for j in range(1, m_cols):
                fd[0][j] = j

            for i in range(1, m_rows):
                node_i_idx = l1 + i - 1
                label_i = labels1[node_i_idx - 1]
                for j in range(1, m_cols):
                    node_j_idx = l2 + j - 1
                    cost = 0 if label_i == labels2[node_j_idx - 1] else 1
                    if lld1[node_i_idx] == l1 and lld2[node_j_idx] == l2:
                        fd[i][j] = min(
                            fd[i - 1][j] + 1,
                            fd[i][j - 1] + 1,
                            fd[i - 1][j - 1] + cost,
                        )
                        tree_dist[node_i_idx][node_j_idx] = fd[i][j]
                    else:
                        fd[i][j] = min(
                            fd[i - 1][j] + 1,
                            fd[i][j - 1] + 1,
                            fd[lld1[node_i_idx] - l1][lld2[node_j_idx] - l2] + tree_dist[node_i_idx][node_j_idx],
                        )

    return tree_dist[n1][n2]


def calculate_structural_preservation(
    html_original: str | None,
    html_repaired: str | None,
    threshold: float = 0.85,
) -> StructureResult:
    """Calculate per-document Structural Preservation.    """
    t_orig = html_to_tree(html_original)
    t_rep = html_to_tree(html_repaired)

    orig_nodes = count_nodes(t_orig)
    rep_nodes = count_nodes(t_rep)
    max_nodes = max(orig_nodes, rep_nodes)

    if t_orig is None or t_rep is None or max_nodes == 0:
        return StructureResult(
            tree_edit_distance=max_nodes,
            original_nodes=orig_nodes,
            repaired_nodes=rep_nodes,
            max_nodes=max_nodes,
            structure_similarity=0.0,
            structure_preserved=False,
            threshold=threshold,
            unparseable=True,
        )

    ted = zss_tree_edit_distance(t_orig, t_rep)
    similarity = round(max(0.0, 1.0 - (ted / max_nodes)), 4)
    preserved = similarity >= threshold

    return StructureResult(
        tree_edit_distance=ted,
        original_nodes=orig_nodes,
        repaired_nodes=rep_nodes,
        max_nodes=max_nodes,
        structure_similarity=similarity,
        structure_preserved=preserved,
        threshold=threshold,
        unparseable=False,
    )
