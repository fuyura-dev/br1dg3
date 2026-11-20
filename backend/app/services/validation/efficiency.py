from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.repair.cascade import CASCADE_SKIP_STATUSES
from app.services.repair.usage import TOKEN_FIELDS, summarize_usage, token_count

DEFAULT_PROMPT_PRICE_PER_M = 0.075
DEFAULT_COMPLETION_PRICE_PER_M = 0.30
_UNSET = object()


@dataclass
class EfficiencyResult:
    """Per-document Repair Efficiency metrics."""

    api_calls: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    thought_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    cascaded_count: int = 0
    patched_count: int = 0
    total_elements: int = 0
    cascade_rate: float = 0.0
    requests: int | None = None
    known_requests: int = 0
    request_count_complete: bool = False
    request_count_basis: str = "application_attempts"
    reported_usage: dict[str, int] = field(default_factory=dict)
    usage_complete: dict[str, bool] = field(default_factory=dict)
    total_tokens_source: str = "supplied_components"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_cost(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    thought_tokens: int | None = 0,
    price_per_m_prompt: float = DEFAULT_PROMPT_PRICE_PER_M,
    price_per_m_completion: float = DEFAULT_COMPLETION_PRICE_PER_M,
) -> float | None:
    """Legacy display estimate; price assumptions are unchanged, unknown usage is null."""
    if any(value is None for value in (prompt_tokens, completion_tokens, thought_tokens)):
        return None
    prompt_cost = (prompt_tokens / 1_000_000.0) * price_per_m_prompt
    # Legacy display assumption, retained here; experiment pricing is external.
    output_cost = ((completion_tokens + thought_tokens) / 1_000_000.0) * price_per_m_completion
    return round(prompt_cost + output_cost, 6)


def calculate_efficiency(
    api_calls: int | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    thought_tokens: int | None = 0,
    cascaded_count: int = 0,
    patched_count: int = 0,
    total_elements: int = 0,
    price_per_m_prompt: float = DEFAULT_PROMPT_PRICE_PER_M,
    price_per_m_completion: float = DEFAULT_COMPLETION_PRICE_PER_M,
    *,
    total_tokens=_UNSET,
    requests: int | None = None,
    known_requests: int | None = None,
    request_count_complete: bool | None = None,
    reported_usage: dict | None = None,
    usage_complete: dict | None = None,
    total_tokens_source: str | None = None,
) -> EfficiencyResult:
    components = [token_count(value) for value in (prompt_tokens, completion_tokens, thought_tokens)]
    derived_total = total_tokens is _UNSET
    total_toks = (sum(components) if all(v is not None for v in components) else None) \
        if derived_total else token_count(total_tokens)
    counts = dict(zip(TOKEN_FIELDS, [*components, total_toks]))
    complete = {name: value is not None and (usage_complete or {}).get(name, True)
                for name, value in counts.items()}
    reported = {name: token_count((reported_usage or {}).get(name, value)) or 0
                for name, value in counts.items()}
    counts = {name: value if complete[name] else None for name, value in counts.items()}
    cost = compute_cost(
        prompt_tokens=counts["prompt_tokens"],
        completion_tokens=counts["completion_tokens"],
        thought_tokens=counts["thought_tokens"],
        price_per_m_prompt=price_per_m_prompt,
        price_per_m_completion=price_per_m_completion,
    )

    if total_elements > 0:
        cascade_rate = round((cascaded_count / total_elements) * 100, 2)
    else:
        cascade_rate = 0.0

    return EfficiencyResult(
        api_calls=token_count(api_calls),
        **counts,
        cost_usd=cost,
        cascaded_count=max(0, cascaded_count),
        patched_count=max(0, patched_count),
        total_elements=max(0, total_elements),
        cascade_rate=cascade_rate,
        requests=0 if requests is None and api_calls == 0 else requests,
        known_requests=known_requests if known_requests is not None else (requests or 0),
        request_count_complete=request_count_complete if request_count_complete is not None
        else (requests is not None or api_calls == 0),
        reported_usage=reported, usage_complete=complete,
        total_tokens_source=total_tokens_source or ("supplied_components" if derived_total else "supplied_total"),
    )


def calculate_efficiency_from_run(
    run: Any,
    price_per_m_prompt: float = DEFAULT_PROMPT_PRICE_PER_M,
    price_per_m_completion: float = DEFAULT_COMPLETION_PRICE_PER_M,
) -> EfficiencyResult:
    """Calculate per-document Repair Efficiency directly from a RepairRun object."""
    if run is None:
        return calculate_efficiency(None, None, None, None, total_tokens=None)

    steps = getattr(run, "steps", [])
    usage = summarize_usage(steps)
    usage.pop("request_count_basis")  # Fixed by EfficiencyResult's documented default.

    # Whole-target local skips only; neither verified repairs nor cost savings.
    cascaded_count = sum(1 for s in steps if getattr(s, "status", "") in CASCADE_SKIP_STATUSES)
    patched_count = sum(1 for s in steps if getattr(s, "status", "") == "applied")
    total_elements = len(steps)

    return calculate_efficiency(
        **usage,
        cascaded_count=cascaded_count,
        patched_count=patched_count,
        total_elements=total_elements,
        price_per_m_prompt=price_per_m_prompt,
        price_per_m_completion=price_per_m_completion,
    )
