from dataclasses import dataclass, field

from app.services.repair.context import ContextExtractor
from app.services.repair.llm import LLMResult, generate
from app.services.repair.order import dependency_view, order_violations_by_dependency
from app.services.repair.patch import (
    MARKER,
    apply_reply,
    outer_html,
    parse_document_reply,
    strip_markers,
)
from app.services.repair.prompt import build_baseline_prompt, build_sdg_prompt
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


def _is_landmark(el) -> bool:
    """Check if an element qualifies as a WCAG/Axe landmark."""
    if not hasattr(el, "name") or el.name is None:
        return False
    name = el.name.lower()
    role = el.get("role", "").lower() if hasattr(el, "get") else ""

    # Explicit ARIA landmark roles
    if role in {"main", "navigation", "complementary", "search", "banner", "contentinfo"}:
        return True
    if role in {"region", "form"}:
        return bool(el.get("aria-label") or el.get("aria-labelledby"))

    # HTML5 tags
    if name in {"main", "nav", "aside"}:
        return True
    if name in {"header", "footer"}:
        # header and footer are landmarks (banner/contentinfo) ONLY if
        # not a descendant of article, aside, main, nav, or section
        sectioning = {"article", "aside", "main", "nav", "section"}
        return not any(getattr(p, "name", "").lower() in sectioning for p in el.parents)
    if name in {"section", "form"}:
        return bool(el.get("aria-label") or el.get("aria-labelledby"))

    return False




def _is_already_satisfied(target, rule_id: str) -> bool:
    """Check if a structural violation was fixed by a previous patch (cascade resolution)."""
    ancestors = [target] + list(target.parents)
    if rule_id == "region":
        return any(_is_landmark(el) for el in ancestors)
    elif rule_id == "listitem":
        for el in target.parents:
            if getattr(el, "name", "") in {"ul", "ol"} or getattr(el, "get", lambda k: None)("role") == "list":
                return True
        return False
    elif rule_id == "dlitem":
        for el in target.parents:
            if getattr(el, "name", "") == "dl":
                return True
        return False
    elif rule_id == "aria-hidden-focus":
        for el in ancestors:
            if getattr(el, "get", lambda k: None)("aria-hidden") == "true":
                return False
        return True
    return False


def _step(current, token, table, pending):
    """One repair step on the current document. Returns (Step, new current document)."""
    rules = [issue["id"] for issue in table[token]]
    builder = SDGBuilder(current, _pending_violations(pending, table))     # re-parse: ids are fresh
    target = builder.soup.select_one(f'[{MARKER}="{token}"]')
    if target is None:                                                     # removed by an earlier patch
        return Step(token, None, rules, "element_gone"), current

    node_id = builder.element_to_id[target]

    # Cascade resolution check
    satisfactions = {r: _is_already_satisfied(target, r) for r in rules}
    if all(satisfactions.values()):
        print(f"[CASCADE RESOLVED {token}] <{target.name}> | Rules: {rules}")
        return Step(token, target.name, rules, "cascade_resolved", node_id=node_id), current

    # If some (but not all) rules were already resolved by ancestors, filter them out
    # so the prompt only asks the LLM to repair the remaining unresolved violations.
    active_issues = [issue for issue in table[token] if not satisfactions.get(issue["id"], False)]
    if len(active_issues) < len(table[token]):
        table[token] = active_issues
        rules = [issue["id"] for issue in active_issues]

    parent_names = [getattr(p, "name", "") for p in target.parents if getattr(p, "name", None)]
    print(f"[NOT CASCADED {token}] <{target.name}> | Rules: {rules} | Satisfied: {satisfactions} | Parents: {parent_names[:4]}")

    step = Step(token, target.name, rules, "", node_id=node_id)

    ctx = ContextExtractor.from_builder(builder).extract(node_id)
    sdg_prompt = build_sdg_prompt(ctx, builder.element_to_id)
    print(
        f"[STEP {token}] Target: <{target.name}> | Rules: {rules} | "
        f"Prompt Size: {len(sdg_prompt.user) + len(sdg_prompt.system)} chars (~{(len(sdg_prompt.user) + len(sdg_prompt.system)) // 4} est tokens)"
    )

    try:
        step.llm = generate(sdg_prompt)
    except Exception as exc:                                               # noqa: BLE001
        step.status, step.error = "llm_error", f"{type(exc).__name__}: {exc}"
        print(f"[STEP {token}] LLM Error: {step.error}")
        return step, current
    if not step.llm.ok:                                                    # truncated / failed / empty
        step.status = f"llm_not_ok:{step.llm.status}"
        print(f"[STEP {token}] LLM Not OK: status={step.llm.status}")
        return step, current

    print(f"[STEP {token}] LLM Reply ({len(step.llm.text)} chars):\n{step.llm.text.strip()}")
    patch = apply_reply(target, step.llm.text, token)                      # mutates builder.soup
    step.status, step.warnings = patch.status, patch.warnings

    print(
        f"[STEP {token}] Applied: status={step.status} warnings={step.warnings} | "
        f"Tokens -> In: {step.llm.prompt_tokens}, Out: {step.llm.completion_tokens}, "
        f"Thought: {step.llm.thought_tokens}, Total: {step.llm.total_tokens}"
    )
    print("-" * 50)
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


def run_baseline(html, violations):
    """Zero-shot baseline: one call, the whole document, all violations at once."""
    if not violations:
        return RepairRun(html, [], 0)

    step = Step("baseline", None, [v.get("id") for v in violations], "")
    try:
        step.llm = generate(build_baseline_prompt(html, violations))
    except Exception as exc:                                              # noqa: BLE001
        step.status, step.error = "llm_error", f"{type(exc).__name__}: {exc}"
        return RepairRun(html, [step], 0)
    if not step.llm.ok:                                                   # truncated / failed / empty
        step.status = f"llm_not_ok:{step.llm.status}"
        return RepairRun(html, [step], 0)

    fixed_html, status = parse_document_reply(step.llm.text)
    step.status = "applied" if status == "ok" else status
    return RepairRun(fixed_html if status == "ok" else html, [step], 0)