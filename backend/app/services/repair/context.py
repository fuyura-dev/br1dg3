from bisect import bisect_left

from app.services.sdg.extractors.landmarks import _is_landmark

ID_RELATIONS = {"id_reference"}
ARIA_RELATIONS = {"aria_labelledby", "aria_describedby", "aria_controls", "aria_owns", "aria_errormessage"}
LABEL_RELATIONS = {"label_input"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
FORM_CONTAINERS = {"fieldset", "form"}


class ContextExtractor:
    def __init__(self, graph, element_ids):
        self.g = graph
        self.ids = element_ids


        heads = sorted((self._index(n), n) for n, d in graph.nodes(data=True) if d["tag"] in HEADING_TAGS)
        self.heading_index = [i for i, _ in heads]
        self.heading_ids = [n for _, n in heads]

    @classmethod
    def from_builder(cls, builder):
        return cls(builder.graph, builder.element_to_id)

    @staticmethod
    def _index(node_id):
        return int(node_id.split("_")[1])

    def _tag(self, node_id):
        return self.g.nodes[node_id]["tag"]

    def _out(self, node_id):
        return [(v, r) for _, v, r in self.g.out_edges(node_id, data="relation")]

    def _in(self, node_id):
        return [(u, r) for u, _, r in self.g.in_edges(node_id, data="relation")]

    # Rule 1-3
    def _neighbors(self, target, relations):
        return [v for v, r in self._out(target) if r in relations] + \
               [u for u, r in self._in(target) if r in relations]

    def _ancestors(self, start, relation, from_tags=None):
        found, frontier = [], [start]
        while frontier:
            next_frontier = []
            for node in frontier:
                for src, rel in self._in(node):
                    if rel != relation or src == start or src in found:
                        continue
                    if from_tags is not None and self._tag(src) not in from_tags:
                        continue
                    found.append(src)
                    next_frontier.append(src)
            frontier = next_frontier
        return found

    # Rule 4
    def _form_group(self, target):
        nodes = []
        # up to the topmost fieldset/form and each fieldset's legend
        for container in self._ancestors(target, "form_group", FORM_CONTAINERS):
            nodes.append(container)
            nodes += [v for v, r in self._out(container) if r == "form_group" and self._tag(v) == "legend"]
        # controls that share a name (radio / checkbox group): direct neighbours in the chain
        nodes += self._neighbors(target, {"name_group"})
        return nodes

    # Rule 5
    def _parent_child(self, target):
        up = self._ancestors(target, "parent_child")
        down = [v for v, r in self._out(target) if r == "parent_child"]
        return up + down

    # Rule 6 - start
    def _nearest_heading(self, target):
        if self._tag(target) in HEADING_TAGS:
            return None
        pos = bisect_left(self.heading_index, self._index(target))
        return self.heading_ids[pos - 1] if pos else None

    # Rule 7 - start
    def _enclosing_landmark(self, target):
        element = self.ids.element(target)
        if _is_landmark(element):
            return None
        for parent in element.parents:
            if parent in self.ids and _is_landmark(parent):
                return self.ids[parent]
        return None

    # Rule 8
    def _hiding_ancestor(self, target):
        for parent in self.ids.element(target).parents:
            if parent in self.ids and self._is_hiding(parent):
                return self.ids[parent]
        return None

    @staticmethod
    def _is_hiding(element):
        return (
            str(element.get("aria-hidden", "")).lower() == "true"
            or element.has_attr("hidden")
            or element.has_attr("inert")
        )

    # Rule Extra
    def _dom_parent(self, target):
        parent = self.ids.element(target).parent
        if parent is None or parent not in self.ids or parent.name in ("html", "body"):
            return None
        parent_id = self.ids[parent]
        return None if self.g.has_edge(parent_id, target) else parent_id

    # Main
    def extract(self, target):
        if target not in self.g:
            raise KeyError(target)

        heading = self._nearest_heading(target)
        landmark = self._enclosing_landmark(target)
        hidden = self._hiding_ancestor(target)
        parent = self._dom_parent(target)
        if parent in (heading, landmark, hidden):
            parent = None

        nodes = {target}
        nodes.update(self._neighbors(target, ID_RELATIONS))          # 1 ID references
        nodes.update(self._neighbors(target, ARIA_RELATIONS))        # 2 ARIA
        nodes.update(self._neighbors(target, LABEL_RELATIONS))       # 3 label-input
        nodes.update(self._form_group(target))                       # 4 form / group
        nodes.update(self._parent_child(target))                     # 5 parent-child
        nodes.update(self._neighbors(target, {"focus_order"}))       # 8 focus: previous / next

        # Rule 6-7
        heading_start = target if self._tag(target) in HEADING_TAGS else heading
        landmark_start = target if _is_landmark(self.ids.element(target)) else landmark
        for start, relation in ((heading_start, "heading_hierarchy"), (landmark_start, "landmark_structure")):
            if start:
                nodes.add(start)
                nodes.update(self._ancestors(start, relation))
        # Rule 8 and Parent context
        nodes.update(a for a in (hidden, parent) if a)

        ctx = self.g.subgraph(nodes).copy()
        for _, _, data in ctx.edges(data=True):
            data["derived"] = False

        # Connectors
        for name, anchor in (
            ("heading_context", heading),
            ("landmark_context", landmark),
            ("hidden_context", hidden),
            ("parent_context", parent),
        ):
            if anchor:
                ctx.add_edge(anchor, target, key=name, relation=name, derived=True)

        # Set target & DOM path
        for node in ctx.nodes:
            ctx.nodes[node]["is_target"] = node == target
        ctx.graph["target"] = target

        dom_chain = []
        el = self.ids.element(target)
        for ancestor in reversed(list(el.parents)):
            if ancestor in self.ids:
                anc_id = self.ids[ancestor]
                dom_chain.append(self.g.nodes[anc_id].get("label") or f"<{ancestor.name}>")
        dom_chain.append(self.g.nodes[target].get("label") or f"<{el.name}>")
        ctx.graph["dom_path"] = dom_chain

        return ctx


def context_to_dict(ctx):
    return {
        "target": ctx.graph.get("target"),
        "dom_path": ctx.graph.get("dom_path", []),
        "nodes": [
            {
                "id": n,
                "tag": d.get("tag"),
                "label": d.get("label"),
                "has_issue": d.get("has_issue"),
                "issues": d.get("issues", []),
                "is_target": d.get("is_target", False),
            }
            for n, d in ctx.nodes(data=True)
        ],
        "edges": [
            {
                "source": u,
                "target": v,
                "relation": d.get("relation"),
                "derived": d.get("derived", False),
            }
            for u, v, d in ctx.edges(data=True)
        ],
    }

