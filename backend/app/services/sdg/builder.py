import networkx as nx
from bs4 import BeautifulSoup, Tag

from app.services.sdg.extractors.aria import extract_aria_edges
from app.services.sdg.extractors.focus import extract_focus_edges
from app.services.sdg.extractors.forms import extract_form_group_edges
from app.services.sdg.extractors.headings import extract_heading_edges
from app.services.sdg.extractors.id_refs import extract_id_reference_edges
from app.services.sdg.extractors.label_input import extract_label_input_edges
from app.services.sdg.extractors.landmarks import extract_landmark_edges
from app.services.sdg.extractors.parent_child import extract_parent_child_edges


class ElementIds:
    def __init__(self):
        self._by_element = {}
        self._by_node = {}
    
    def __setitem__(self, tag, node_id):
        self._by_element[id(tag)] = node_id
        self._by_node[node_id] = tag

    def __getitem__(self, tag):
        return self._by_element[id(tag)]

    def __contains__(self, tag):
        return id(tag) in self._by_element

    def __len__(self):
        return len(self._by_element)

    def get(self, tag, default=None):
        return self._by_element.get(id(tag), default)

    def element(self, node_id):
        return self._by_node[node_id]


class SDGBuilder:
    def __init__(self, html: str, violations: list[dict] | None = None):
        self.html = html
        self.violations = violations or []
        self.soup = BeautifulSoup(html, "html.parser")
        self.graph = nx.MultiDiGraph()

        self.element_to_id = ElementIds()

        self._build_nodes()
        self._build_edges()
        if self.violations:
            self._mark_violations()


    def _build_nodes(self):
        for index, tag in enumerate(self.soup.find_all(True)):

            node_id = f"node_{index}_{tag.name}"

            self.element_to_id[tag] = node_id

            display_label = f"<{tag.name}>"

            self.graph.add_node(
                node_id,
                tag=tag.name,
                label=display_label,
                html=str(tag),
                has_issue=False,
                issues=[],
            )


    def _build_edges(self):
        # 1. ARIA References
        aria_edges = extract_aria_edges(self.soup, self.element_to_id)
        self._add_edges(aria_edges)

        # 2. Label-input connections
        label_edges = extract_label_input_edges(self.soup, self.element_to_id)
        self._add_edges(label_edges)

        # 3. Heading relationships
        heading_edges = extract_heading_edges(self.soup, self.element_to_id)
        self._add_edges(heading_edges)

        # 4. Landmark Structure
        landmark_edges = extract_landmark_edges(self.soup, self.element_to_id)
        self._add_edges(landmark_edges)

        # 5. Parent-child relationships
        parent_child_edges = extract_parent_child_edges(self.soup, self.element_to_id)
        self._add_edges(parent_child_edges)

        # 6. Focus related relationships
        focus_edges = extract_focus_edges(self.soup, self.element_to_id)
        self._add_edges(focus_edges)

        # 7. Form/group relationships
        form_group_edges = extract_form_group_edges(self.soup, self.element_to_id)
        self._add_edges(form_group_edges)

        # 8. ID References
        id_ref_edges = extract_id_reference_edges(self.soup, self.element_to_id)
        self._add_edges(id_ref_edges)


    def _mark_violations(self):
        for violation in self.violations:
            for node in violation.get("nodes", []):
                targets = node.get("target", [])
                matching_tag = None

                for selector in targets:
                    try:
                        matching_tag = self.soup.select_one(selector)
                        if matching_tag:
                            break
                    except Exception: # noqa: BLE001, S112
                        continue

                if matching_tag and matching_tag in self.element_to_id:
                    node_id = self.element_to_id[matching_tag]
                    self.graph.nodes[node_id]["has_issue"] = True
                    self.graph.nodes[node_id]["issues"].append({
                        "id": violation.get("id"),
                        "impact": violation.get("impact"),
                        "description": violation.get("description"),
                        "help": violation.get("help"),
                        "help_url": violation.get("helpUrl"),
                        "html": node.get("html"),
                    })


    def to_dict(self) -> dict:
        nodes = []
        for node_id, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "tag": data.get("tag"),
                "label": data.get("label"),
                "has_issue": data.get("has_issue"),
                "issues": data.get("issues", []),
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
            self.graph.add_edge(source, target, key=relation, relation=relation)


if __name__ == "__main__":
    sample = """
<header>
    <nav aria-label="Main menu">
        <ul>
            <li><a href="#content">Skip to content</a></li>
            <li>Products
                <ul>
                    <li><a href="/new">New arrivals</a></li>
                    <li><a href="/sale">On sale</a></li>
                </ul>
            </li>
        </ul>
    </nav>
</header>

<main id="content">
    <h1>Store</h1>

    <h2>Search</h2>
    <div role="search">
        <label for="q">Query</label>
        <input type="text" id="q" list="suggestions">
        <datalist id="suggestions">
            <option value="shoes">
            <option value="boots">
        </datalist>
    </div>

    <h2>Account form</h2>
    <form id="signup">
        <fieldset>
            <legend>Personal details</legend>
            <label>Name <input type="text" name="fullname"></label>
            <label id="email-label" for="email">Email</label>
            <input type="email" id="email" aria-labelledby="email-label" aria-describedby="email-hint">
            <span id="email-hint">We never share it</span>
        </fieldset>
        <input type="radio" name="plan" value="basic">
        <input type="radio" name="plan" value="pro">
        <select name="country">
            <optgroup label="Asia">
                <option value="ph">Philippines</option>
                <option value="jp">Japan</option>
            </optgroup>
        </select>
        <button type="submit" aria-controls="result">Send</button>
    </form>
    <input type="text" name="outside" form="signup">
    <div id="result">Result here</div>

    <h4>Skipped level</h4>

    <h2>Data</h2>
    <table>
        <thead>
            <tr><th id="h-item">Item</th><th id="h-qty">Qty</th></tr>
        </thead>
        <tbody>
            <tr><td headers="h-item">Apples</td><td headers="h-qty">3</td></tr>
            <tr>
                <td headers="h-item">Pears</td>
                <td><table><tr><td>Nested cell</td></tr></table></td>
            </tr>
        </tbody>
    </table>

    <dl><dt>Term</dt><dd>Definition</dd></dl>

    <aside>
        <h3>Related</h3>
        <a href="#result" aria-controls="result">Jump to result</a>
    </aside>
</main>

<footer>
    <button tabindex="2">Second</button>
    <button tabindex="1">First</button>
    <button disabled>Off</button>
    <input type="hidden" name="token">
</footer>
"""

    builder = SDGBuilder(sample)
    graph_data = builder.to_dict()

    print(f"\nNODES ({len(graph_data['nodes'])})")

    for node in graph_data["nodes"]:
        print(f"  - {node['id']:<18} {node['label']}")

    print(f"\nEDGES ({len(graph_data['edges'])}):")

    for edge in graph_data["edges"]:
        print(f"  - {edge['source']:<18} --[ {edge['relation']:<18} ] -> {edge['target']}")