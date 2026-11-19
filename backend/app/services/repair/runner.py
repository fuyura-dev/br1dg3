from dataclasses import dataclass, field

from app.services.detection.preprocess import preprocess
from app.services.repair.cascade import (
    CASCADE_SKIP_STATUSES,
    infer_skips,
    supported_condition,
)
from app.services.repair.context import ContextExtractor
from app.services.repair.llm import LLMResult, generate
from app.services.repair.log_streamer import streamer
from app.services.repair.order import dependency_view, order_violations_by_dependency
from app.services.repair.patch import (
    MARKER,
    PatchResult,
    outer_html,
    parse_document_reply,
    strip_markers,
)
from app.services.repair.prompt import build_baseline_prompt, build_sdg_prompt
from app.services.repair.root_view import RootViewTooLarge
from app.services.repair.scope import apply_scoped_reply, parse_scoped_reply
from app.services.sdg.builder import SDGBuilder


@dataclass
class Step:
    token: str
    tag: str | None
    rules: list[str]   # original reported rules; never overwritten by local skip checks
    status: str        # applied | cascade_skipped | element_gone | llm_error | llm_not_ok:<status> | empty_reply | invalid_reply | no_element | tracking_rejected | patch_rejected | prompt_too_large
    warnings: list[str] = field(default_factory=list)
    node_id: str | None = None          # the node id AT THAT STEP (ids shift as patches are applied)
    original_node_id: str | None = None
    related_relationships: list[str] = field(default_factory=list)
    llm: LLMResult | None = None
    error: str | None = None
    candidate_html: str | None = None  # accepted reply/patch before document assembly
    requested_rules: list[str] = field(default_factory=list)  # passed to generate(), even if it raises
    skipped_rules: list[dict[str, str]] = field(default_factory=list)  # local inference, not verified repair
    edit_scope: dict | None = None     # selected input scope and limits, without live DOM objects
    reply_scope: str | None = None     # declared scope, including a subsequently rejected patch
    reply_html: str | None = None      # decoded HTML payload; raw JSON remains in llm.text


@dataclass
class RepairRun:
    fixed_html: str
    steps: list[Step]
    unmapped: int                       # Axe nodes that could not be mapped to an element (never attempted)
    candidate_html: str | None = field(init=False)
    generation_status: str = field(init=False)
    fallback_used: bool = field(init=False)

    def __post_init__(self):
        # Acceptance is tracked by steps, never inferred from HTML equality.
        accepted = any(s.status == "applied" for s in self.steps)
        self.candidate_html = self.fixed_html if accepted else None
        self.fallback_used = not accepted and bool(self.steps or self.unmapped)
        if accepted:
            self.generation_status = "partial" if self.failed_steps or self.unmapped else "accepted"
        else:
            self.generation_status = "no_candidate" if self.fallback_used else "not_needed"

    @property
    def failed_steps(self):
        return sum(
            s.status not in {"applied", "element_gone"} | CASCADE_SKIP_STATUSES
            for s in self.steps
        )

    def generation_summary(self):
        return {
            "status": self.generation_status,
            "candidate_available": self.candidate_html is not None,
            "fallback_used": self.fallback_used,
            "failed_steps": self.failed_steps,
            "unmapped": self.unmapped,
        }

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


def _step(current, token, table, pending, original_conditions, *, has_accepted_patch):
    """One repair step on the current document. Returns (Step, new current document)."""
    rules = [issue["id"] for issue in table[token]]
    builder = SDGBuilder(current, _pending_violations(pending, table))     # re-parse: ids are fresh
    target = builder.soup.select_one(f'[{MARKER}="{token}"]')
    if target is None:                                                     # removed by an earlier patch
        return Step(token, None, rules, "element_gone"), current

    node_id = builder.element_to_id[target]

    skipped = infer_skips(target, rules, original_conditions, has_accepted_patch=has_accepted_patch)
    skipped_ids = {item["rule_id"] for item in skipped}
    step = Step(token, target.name, rules, "", node_id=node_id, skipped_rules=skipped)
    if skipped_ids == set(rules):
        step.status = "cascade_skipped"
        streamer.log(f"[CASCADE SKIPPED {token}] <{target.name}> | Rules: {rules} | Local inference: {skipped}")
        return step, current

    active_issues = [issue for issue in table[token] if issue["id"] not in skipped_ids]
    active_rules = [issue["id"] for issue in active_issues]

    parent_names = [getattr(p, "name", "") for p in target.parents if getattr(p, "name", None)]
    streamer.log(f"[NOT CASCADED {token}] <{target.name}> | Requested rules: {active_rules} | Locally skipped: {skipped} | Parents: {parent_names[:4]}")

    ctx = ContextExtractor.from_builder(builder).extract(node_id)
    # Filter the actual target prompt, while retaining the original issue table.
    ctx.nodes[node_id]["issues"] = active_issues
    step.related_relationships = [
        f"{d.get('relation')}: {ctx.nodes[u].get('label', u)} -> {ctx.nodes[v].get('label', v)}"
        for u, v, d in ctx.edges(data=True)
    ]
    try:
        sdg_prompt = build_sdg_prompt(ctx, builder.element_to_id)
    except RootViewTooLarge as exc:
        step.status, step.error = "prompt_too_large", str(exc)
        streamer.log(f"[STEP {token}] Repair prompt rejected: {exc}")
        return step, current
    step.edit_scope = sdg_prompt.edit_scope.record(builder.element_to_id)
    streamer.log(
        f"[STEP {token}] Target: <{target.name}> | Rules: {active_rules} | "
        f"Prompt Size: {len(sdg_prompt.user) + len(sdg_prompt.system)} chars (~{(len(sdg_prompt.user) + len(sdg_prompt.system)) // 4} est tokens)"
    )

    try:
        step.requested_rules = active_rules
        step.llm = generate(sdg_prompt)
    except Exception as exc:                                               # noqa: BLE001
        step.status, step.error = "llm_error", f"{type(exc).__name__}: {exc}"
        streamer.log(f"[STEP {token}] LLM Error: {step.error}")
        return step, current
    if not step.llm.ok:                                                    # truncated / failed / empty
        step.status = f"llm_not_ok:{step.llm.status}"
        streamer.log(f"[STEP {token}] LLM Not OK: status={step.llm.status}")
        return step, current

    streamer.log(f"[STEP {token}] LLM Reply ({len(step.llm.text)} chars):\n{step.llm.text.strip()}")
    reply, error = parse_scoped_reply(step.llm.text)
    if error:
        patch = PatchResult(False, "empty_reply" if error == "empty_reply" else "invalid_reply", [error])
    else:
        step.reply_scope, step.reply_html = reply.scope, reply.html
        patch = apply_scoped_reply(sdg_prompt.edit_scope, reply, token)    # atomic replacement in builder.soup
    step.status, step.warnings = patch.status, patch.warnings
    if patch.applied:
        step.candidate_html = reply.html.strip()

    streamer.log(
        f"[STEP {token}] Applied: status={step.status} warnings={step.warnings} | "
        f"Tokens -> In: {step.llm.prompt_tokens}, Out: {step.llm.completion_tokens}, "
        f"Thought: {step.llm.thought_tokens}, Total: {step.llm.total_tokens}"
    )
    streamer.log("-" * 50)
    return step, (outer_html(builder.soup) if patch.applied else current)


def run_sdg(html, violations):
    """html: the document. violations: raw Axe violations (from detect())."""
    html = preprocess(html)
    builder = SDGBuilder(html, violations)          # the ONLY place Axe selectors are used
    graph = builder.graph
    units = [n for n, d in graph.nodes(data=True) if d["has_issue"]]       # one unit per element
    unmapped = sum(len(v.get("nodes", [])) for v in violations) - sum(len(graph.nodes[n]["issues"]) for n in units)
    if not units:
        return RepairRun(html, [], unmapped)

    # 1. one token per violated element, stamped into the HTML; Axe details kept by token
    tokens = {node: f"v{i}" for i, node in enumerate(units, 1)}
    orig_by_token = {token: node for node, token in tokens.items()}
    table = {}
    for node, token in tokens.items():
        builder.element_to_id.element(node)[MARKER] = token
        table[token] = graph.nodes[node]["issues"]
    current = outer_html(builder.soup)
    original_conditions = {
        token: {issue["id"]: supported_condition(builder.element_to_id.element(node), issue["id"])
                for issue in table[token]}
        for node, token in tokens.items()
    }

    # 2. Fixed initial schedule: SDG dependencies plus DOM containment, kept
    # separate from the graph used for context and semantic measurements.
    scheduling_graph = dependency_view(graph, builder.element_to_id)
    order = [tokens[n] for n in order_violations_by_dependency(scheduling_graph, units)]

    # 3. one violated element per prompt, each on the CURRENT document
    pending, steps = set(table), []
    has_accepted_patch = False
    for token in order:
        step, current = _step(
            current, token, table, pending, original_conditions[token], has_accepted_patch=has_accepted_patch,
        )
        has_accepted_patch = has_accepted_patch or step.status == "applied"
        step.original_node_id = orig_by_token.get(token)
        pending.discard(token)
        steps.append(step)

    return RepairRun(strip_markers(current), steps, unmapped)


def run_baseline(html, violations):
    """Zero-shot baseline: one call, the whole document, all violations at once."""
    html = preprocess(html)
    if not violations:
        return RepairRun(html, [], 0)

    step = Step("baseline", None, [v.get("id") for v in violations], "")
    try:
        baseline_prompt = build_baseline_prompt(html, violations)
        step.requested_rules = list(step.rules)
        step.llm = generate(baseline_prompt)
    except Exception as exc:                                              # noqa: BLE001
        step.status, step.error = "llm_error", f"{type(exc).__name__}: {exc}"
        return RepairRun(html, [step], 0)
    if not step.llm.ok:                                                   # truncated / failed / empty
        step.status = f"llm_not_ok:{step.llm.status}"
        return RepairRun(html, [step], 0)

    fixed_html, status = parse_document_reply(step.llm.text)
    step.status = "applied" if status == "ok" else status
    step.candidate_html = fixed_html
    return RepairRun(fixed_html if status == "ok" else html, [step], 0)
