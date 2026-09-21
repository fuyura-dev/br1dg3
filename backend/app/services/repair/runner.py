from dataclasses import dataclass, field

from app.services.repair.context import ContextExtractor
from app.services.repair.llm import LLMResult, generate
from app.services.repair.order import dependency_view, order_violations_by_dependency
from app.services.repair.patch import MARKER, apply_reply, outer_html, strip_markers
from app.services.repair.prompt import build_sdg_prompt
from app.services.sdg.builder import SDGBuilder


@dataclass
class Step:
    token: str
    tag: str | None
    rules: list[str]
    status: str        # applied | element_gone | llm_error | llm_not_ok:<status> | empty_reply | no_element
    warnings: list[str] = field(default_factory=list)
    node_id: str | None = None          # the node id AT THAT STEP (ids shift as patches are applied)
    llm: LLMResult | None = None
    error: str | None = None


@dataclass
class RepairRun:
    fixed_html: str
    steps: list[Step]
    unmapped: int                       # Axe nodes that could not be mapped to an element (never attempted)

    def _sum(self, name):
        return sum(getattr(s.llm, name) for s in self.steps if s.llm)

    @property
    def api_calls(self):
        return sum(1 for s in self.steps if s.llm)

    @property
    def requests(self):                 # includes retried transient errors
        return self._sum("attempts")

    @property
    def prompt_tokens(self):
        return self._sum("prompt_tokens")

    @property
    def completion_tokens(self):
        return self._sum("completion_tokens")

    @property
    def thought_tokens(self):
        return self._sum("thought_tokens")

    @property
    def total_tokens(self):
        return self._sum("total_tokens")


def _pending_violations(pending, table):
    """Axe-shaped violations for the pending tokens only, located by their marker (not by stale selectors)."""
    return [
        {
            "id": issue["id"], "impact": issue["impact"], "description": issue["description"],
            "help": issue["help"], "helpUrl": issue["help_url"],
            "nodes": [{"target": [f'[{MARKER}="{token}"]'], "html": issue["html"]}],
        }
        for token in sorted(pending) for issue in table[token]
    ]


def _step(current, token, table, pending):
    """One repair step on the current document. Returns (Step, new current document)."""
    rules = [issue["id"] for issue in table[token]]
    builder = SDGBuilder(current, _pending_violations(pending, table))     # re-parse: ids are fresh
    target = builder.soup.select_one(f'[{MARKER}="{token}"]')
    if target is None:                                                     # removed by an earlier patch
        return Step(token, None, rules, "element_gone"), current

    node_id = builder.element_to_id[target]
    step = Step(token, target.name, rules, "", node_id=node_id)

    ctx = ContextExtractor.from_builder(builder).extract(node_id)
    try:
        step.llm = generate(build_sdg_prompt(ctx, builder.element_to_id))
    except Exception as exc:                                               # noqa: BLE001
        step.status, step.error = "llm_error", f"{type(exc).__name__}: {exc}"
        return step, current
    if not step.llm.ok:                                                    # truncated / failed / empty
        step.status = f"llm_not_ok:{step.llm.status}"
        return step, current

    patch = apply_reply(target, step.llm.text, token)                      # mutates builder.soup
    step.status, step.warnings = patch.status, patch.warnings
    return step, (outer_html(builder.soup) if patch.applied else current)


def run_sdg(html, violations):
    """html: the document. violations: raw Axe violations (from detect())."""
    builder = SDGBuilder(html, violations)          # the ONLY place Axe selectors are used
    graph = builder.graph
    units = [n for n, d in graph.nodes(data=True) if d["has_issue"]]       # one unit per element
    unmapped = sum(len(v.get("nodes", [])) for v in violations) - sum(len(graph.nodes[n]["issues"]) for n in units)
    if not units:
        return RepairRun(html, [], unmapped)

    # 1. one token per violated element, stamped into the HTML; Axe details kept by token
    tokens = {node: f"v{i}" for i, node in enumerate(units, 1)}
    table = {}
    for node, token in tokens.items():
        builder.element_to_id.element(node)[MARKER] = token
        table[token] = graph.nodes[node]["issues"]
    current = outer_html(builder.soup)

    # 2. dependency order, computed once on the ORIGINAL graph's dependency view, converted to tokens
    order = [tokens[n] for n in order_violations_by_dependency(dependency_view(graph), units)]

    # 3. one violated element per prompt, each on the CURRENT document
    pending, steps = set(table), []
    for token in order:
        step, current = _step(current, token, table, pending)
        pending.discard(token)
        steps.append(step)

    return RepairRun(strip_markers(current), steps, unmapped)