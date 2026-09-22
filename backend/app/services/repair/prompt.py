from collections import defaultdict
from dataclasses import dataclass

from app.services.repair.patch import MARKER, outer_html
from bs4 import Tag

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP_ATTRS = {"class", "style"}          # dropped from CONTEXT nodes only (also every data-* attribute)


@dataclass
class Prompt:
    system: str
    user: str


# ------------------------------------------------------------------ shared pieces
COMMON_RULES = """\
- Keep the HTML valid.
- Change only what is needed to fix the reported violation(s). Keep everything else exactly as it is (tags, attributes, text, children, order).
- Do not remove content or functionality.
- Do not add explanations, comments or code fences."""


def _violation_line(rule_id, impact, help_text, description):
    text = ". ".join(part for part in (help_text, description) if part)
    return f"{rule_id} ({impact}): {text}"


# ------------------------------------------------------------------ baseline
BASELINE_SYSTEM = f"""\
You are a web accessibility repair assistant.
You receive an HTML document and a list of accessibility violations detected in it.
Return ONLY the complete repaired HTML document.

Rules:
{COMMON_RULES}"""


def build_baseline_prompt(html, violations):
    """violations: raw Axe violations (each has id, impact, help, description, nodes[html, target])."""
    lines = []
    for i, v in enumerate(violations, 1):
        lines.append(f"{i}. " + _violation_line(v.get("id"), v.get("impact"), v.get("help"), v.get("description")))
        for node in v.get("nodes", []):
            lines.append(f"   - Affected element: {node.get('html')}")
            selector = next((t for t in node.get("target", []) if isinstance(t, str)), None)
            if selector:
                lines.append(f"     Selector: {selector}")
    user = "## Violations\n" + "\n".join(lines) + "\n\n## HTML document\n" + html + \
           "\n\nReturn only the complete repaired HTML document."
    return Prompt(BASELINE_SYSTEM, user)


# ------------------------------------------------------------------ BR1DG3 (SDG)
SDG_SYSTEM = f"""\
You are a web accessibility repair assistant.
You receive ONE target element [T] with its accessibility violation(s), and a small graph of related
elements that shows how the target connects to the rest of the page (labels, ARIA references,
headings, landmarks, form groups, parents, focus order).
Relationships are written as arrows: `[A] --relation--> [B]` means A has that relation to B, and a chain
such as `[A] --r1--> [B] --r2--> [C]` follows the arrows. The relation name describes the connection.
Return ONLY the HTML that replaces the target. Normally this is the repaired target element itself.
You may add sibling elements, or wrap the target, when the repair requires it.

Rules:
{COMMON_RULES}
- Do not change the target's id attribute; other elements refer to it.
- Keep every {MARKER} attribute exactly as it is, on the target and on any child element (internal tracking marker).
- The related elements are read-only context. Do not output them. Use them so the fix fits the page
  (for example reuse existing label or heading text, keep landmark names distinct)."""

# Relations whose edges form a path DOWN to the target. Each family is printed as ONE chain,
# root -> ... -> [T]  (e.g. h1 -> h2 -> [T]).
CHAIN_FAMILIES = [
    {"heading_hierarchy", "heading_context"},
    {"landmark_structure", "landmark_context"},
    {"parent_child", "nested_container", "parent_context"},
    {"form_group"},
]

# printing order of the remaining edges: structure, references, focus
GROUP_RANK = {
    "heading_hierarchy": 0, "heading_context": 0,
    "landmark_structure": 1, "landmark_context": 1,
    "parent_context": 2, "parent_child": 2, "nested_container": 2,
    "form_group": 3, "name_group": 3,
    "label_input": 4, "aria_labelledby": 4, "aria_describedby": 4, "aria_controls": 4,
    "aria_owns": 4, "aria_errormessage": 4, "id_reference": 4,
    "focus_order": 5, "hidden_context": 5,
}


def _index(node_id):
    return int(node_id.split("_")[1])                    # node_{index}_{tag} = document order


def _snippet(element, limit=80):
    """Shallow view of a context element: its tag + attributes + short text, children collapsed."""
    attrs = []
    for name, value in element.attrs.items():
        if name in SKIP_ATTRS or name.startswith("data-"):
            continue
        if isinstance(value, list):
            value = " ".join(value)
        attrs.append(name if value == "" else f'{name}="{value}"')
    open_tag = "<" + " ".join([element.name, *attrs]) + ">"
    if element.name in VOID_TAGS:
        return open_tag
    if element.find(True):                               # has child elements: do not expand
        return f"{open_tag}…</{element.name}>"
    text = " ".join(element.get_text().split())
    if len(text) > limit:
        text = text[:limit] + "…"
    return f"{open_tag}{text}</{element.name}>"


def _shallow_layout_tree(element, max_depth=2, current_depth=0):
    """Render a shallow view of a root/layout element (e.g. html, body) down to max_depth hops,
    collapsing deeper children with '…' so the LLM sees top-level sections without token explosions."""
    if current_depth >= max_depth:
        return _snippet(element)

    if element.name == "head":
        return "<head>…</head>"

    attrs = []
    for k, v in element.attrs.items():
        if k in SKIP_ATTRS or k.startswith("data-"):
            continue
        if isinstance(v, list):
            v = " ".join(v)
        attrs.append(k if v == "" else f'{k}="{v}"')
    open_tag = f"<{element.name}" + ((" " + " ".join(attrs)) if attrs else "") + ">"

    if element.name in VOID_TAGS:
        return open_tag

    children_tags = [
        c for c in element.children
        if isinstance(c, Tag) and c.name not in {"script", "style", "noscript", "svg", "template"}
    ]
    if not children_tags:
        return _snippet(element)

    inner = "\n".join("  " * (current_depth + 1) + _shallow_layout_tree(c, max_depth, current_depth + 1) for c in children_tags)
    return f"{open_tag}\n{inner}\n" + "  " * current_depth + f"</{element.name}>"


def _chains_to_target(ctx, target, label):
    """One chain per family: walk back from the target along that family's edges (nearest ancestor
    first), then print it root -> ... -> [T]. Returns (lines, edges already used)."""
    lines, used = [], set()
    for family in CHAIN_FAMILIES:
        path, node, seen = [], target, {target}
        while True:
            options = [(u, k, d["relation"]) for u, _, k, d in ctx.in_edges(node, keys=True, data=True)
                       if d["relation"] in family and u not in seen]
            if not options:
                break
            u, k, relation = max(options, key=lambda o: _index(o[0]))      # nearest = latest in the document
            path.append((u, relation, node))
            used.add((u, node, k))
            seen.add(u)
            node = u
        if path:
            path.reverse()
            lines.append(label[path[0][0]] + "".join(f" --{r}--> {label[v]}" for _, r, v in path))
    return lines, used


def _join_runs(edges, label):
    """Join a -> b -> c of the SAME relation into one line, but only when nothing branches in between."""
    out, inn = defaultdict(list), defaultdict(list)
    for u, v, r in edges:
        out[(u, r)].append(v)
        inn[(v, r)].append(u)

    def continues(u, r):        # is the edge leaving u just the continuation of the edge entering u?
        return len(inn[(u, r)]) == 1 and len(out[(inn[(u, r)][0], r)]) == 1 and len(out[(u, r)]) == 1

    lines, seen = [], set()
    for u, v, r in edges:
        if (u, v, r) in seen or continues(u, r):
            continue
        chain = [u, v]
        seen.add((u, v, r))
        while len(out[(chain[-1], r)]) == 1 and len(inn[(chain[-1], r)]) == 1:
            w = out[(chain[-1], r)][0]
            if (chain[-1], w, r) in seen:
                break
            seen.add((chain[-1], w, r))
            chain.append(w)
        lines.append(label[chain[0]] + "".join(f" --{r}--> {label[n]}" for n in chain[1:]))
    lines += [f"{label[u]} --{r}--> {label[v]}" for u, v, r in edges if (u, v, r) not in seen]   # e.g. cycles
    return lines


def _relationship_lines(ctx, target, label):
    lines, used = _chains_to_target(ctx, target, label)
    rest = sorted(
        ((u, v, d["relation"]) for u, v, k, d in ctx.edges(keys=True, data=True) if (u, v, k) not in used),
        key=lambda e: (GROUP_RANK.get(e[2], 6), _index(e[0]), _index(e[1])),
    )
    return lines + _join_runs(rest, label)


def build_sdg_prompt(ctx, element_ids):
    """ctx: the context graph from ContextExtractor.extract(); element_ids: the builder's ElementIds."""
    target = ctx.graph["target"]

    # labels: [T] for the target, [1], [2]... for the rest in document order
    others = sorted((n for n in ctx.nodes if n != target), key=_index)
    label = {target: "[T]", **{n: f"[{i}]" for i, n in enumerate(others, 1)}}

    issues = ctx.nodes[target].get("issues", [])
    violations = "\n".join(
        f"{i}. " + _violation_line(v.get("id"), v.get("impact"), v.get("help"), v.get("description"))
        for i, v in enumerate(issues, 1)
    ) or "(none recorded)"

    target_el = element_ids.element(target)
    if target_el.name == "html":
        target_markup = _shallow_layout_tree(target_el, max_depth=2)
    elif target_el.name == "body":
        target_markup = _shallow_layout_tree(target_el, max_depth=1)
    else:
        target_markup = outer_html(target_el)

    parts = [
        "## Violations on the target element\n" + violations,
        f"## Target element [T]\n{target_markup}",
    ]

    if others:
        lines = []
        for n in others:
            line = f"{label[n]} {_snippet(element_ids.element(n))}"
            own = [v.get("id") for v in ctx.nodes[n].get("issues", [])]
            if own:
                line += f"   (has its own violation: {', '.join(own)}; handled separately, do not change)"
            lines.append(line)
        parts.append("## Related elements (read-only)\n" + "\n".join(lines))
        parts.append("## Relationships\n" + "\n".join(_relationship_lines(ctx, target, label)))
    else:
        parts.append("## Related elements\nNone found.")

    if target_el.name in {"html", "body"}:
        parts.append(
            "Return only the HTML that replaces [T]. "
            "For layout landmarks (<main>, <header>, <footer>), wrap or convert top-level body sections. "
            "Keep inner section contents collapsed with … to keep the response concise."
        )
    else:
        parts.append("Return only the HTML that replaces [T].")
    return Prompt(SDG_SYSTEM, "\n\n".join(parts))


if __name__ == "__main__":
    import sys
    from pathlib import Path

    from app.services.repair.context import ContextExtractor
    from app.services.repair.order import order_violations_by_dependency
    from app.services.sdg.builder import SDGBuilder

    # Parse arguments
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    show_baseline = "--baseline" in flags

    # Locate HTML file (supports running from repo root or backend/)
    html_arg = args[0] if len(args) > 0 else "sample.html"
    candidates = [Path(html_arg), Path("backend") / html_arg, Path("..") / html_arg]
    html_path = next((p for p in candidates if p.is_file()), None)

    if not html_path:
        print(f"Error: Could not find HTML file '{html_arg}'.")
        sys.exit(1)

    html = html_path.read_text(encoding="utf-8")

    # 1. Run detection (axe-core) or fallback to sample violations
    violations = []
    try:
        from app.services.detection.detect import detect
        violations = detect(html)
        print(f"[*] Detected {len(violations)} rule violations via axe-core.")
    except Exception as e:  # noqa: BLE001
        print(f"[*] Axe detection unavailable ({e}). Using sample violations matching sample.html.")
        violations = [
            {
                "id": "label",
                "impact": "critical",
                "description": "Ensures every form element has a label",
                "help": "Form elements must have labels",
                "helpUrl": "https://dequeuniversity.com/rules/axe/4.4/label",
                "nodes": [
                    {
                        "target": ["input[name='plan'][value='basic']"],
                        "html": '<input type="radio" name="plan" value="basic">',
                    },
                    {
                        "target": ["input[name='outside']"],
                        "html": '<input type="text" name="outside" form="signup">',
                    },
                ],
            },
            {
                "id": "heading-order",
                "impact": "moderate",
                "description": "Heading levels should only increase by one",
                "help": "Heading levels should increase by one",
                "helpUrl": "https://dequeuniversity.com/rules/axe/4.4/heading-order",
                "nodes": [
                    {
                        "target": ["h4"],
                        "html": "<h4>Skipped level</h4>",
                    },
                ],
            },
        ]

    if show_baseline:
        prompt = build_baseline_prompt(html, violations)
        print("\n" + "=" * 60)
        print("BASELINE SYSTEM PROMPT")
        print("=" * 60)
        print(prompt.system)
        print("\n" + "=" * 60)
        print("BASELINE USER PROMPT")
        print("=" * 60)
        print(prompt.user)
    else:
        # 2. Build SDG with marked violations
        builder = SDGBuilder(html, violations=violations)

        # 3. Find all violated nodes and sort them by dependency
        violated_nodes = [n for n, d in builder.graph.nodes(data=True) if d.get("has_issue")]
        ordered_targets = order_violations_by_dependency(builder.graph, violated_nodes)

        print(f"[*] Total violated nodes found: {len(violated_nodes)}")
        if ordered_targets:
            print(f"[*] Topological dependency repair order: {' -> '.join(ordered_targets)}")

        # 4. Pick target: user-specified, or first in dependency order
        target = args[1] if len(args) > 1 else (ordered_targets[0] if ordered_targets else None)

        if not target:
            print("Error: No violated nodes found in graph.")
            sys.exit(1)

        if target not in builder.graph:
            print(f"Error: Node '{target}' not found in SDG graph.")
            print(f"Available nodes ({len(builder.graph)}): {list(builder.graph.nodes)[:10]}...")
            sys.exit(1)

        print(f"[*] Selected target for repair: {target}")

        # 5. Extract context and generate prompt
        extractor = ContextExtractor.from_builder(builder)
        ctx = extractor.extract(target)
        prompt = build_sdg_prompt(ctx, builder.element_to_id)

        print("\n" + "=" * 60)
        print(f"SDG SYSTEM PROMPT (Target: {target})")
        print("=" * 60)
        print(prompt.system)
        print("\n" + "=" * 60)
        print(f"SDG USER PROMPT (Target: {target})")
        print("=" * 60)
        print(prompt.user)
        print("\n" + "=" * 60)
        print(f"Prompt stats: {len(prompt.user)} chars | ~{len(prompt.user)//4} tokens")
        print("=" * 60)