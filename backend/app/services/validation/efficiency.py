from dataclasses import dataclass
from typing import Any

DEFAULT_PROMPT_PRICE_PER_M = 0.075
DEFAULT_COMPLETION_PRICE_PER_M = 0.30


@dataclass
class EfficiencyResult:
    """Per-document Repair Efficiency metrics."""

    api_calls: int
    prompt_tokens: int
    completion_tokens: int
    thought_tokens: int
    total_tokens: int
    cost_usd: float
    cascaded_count: int = 0
    patched_count: int = 0
    total_elements: int = 0
    cascade_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_calls": self.api_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "thought_tokens": self.thought_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "cascaded_count": self.cascaded_count,
            "patched_count": self.patched_count,
            "total_elements": self.total_elements,
            "cascade_rate": self.cascade_rate,
        }


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    thought_tokens: int = 0,
    price_per_m_prompt: float = DEFAULT_PROMPT_PRICE_PER_M,
    price_per_m_completion: float = DEFAULT_COMPLETION_PRICE_PER_M,
) -> float:
    """Compute monetary API cost in USD based on token counts and pricing per 1M tokens."""
    prompt_cost = (prompt_tokens / 1_000_000.0) * price_per_m_prompt
    # Thought tokens are billed at the completion output rate
    output_cost = ((completion_tokens + thought_tokens) / 1_000_000.0) * price_per_m_completion
    return round(prompt_cost + output_cost, 6)


def calculate_efficiency(
    api_calls: int,
    prompt_tokens: int,
    completion_tokens: int,
    thought_tokens: int = 0,
    cascaded_count: int = 0,
    patched_count: int = 0,
    total_elements: int = 0,
    price_per_m_prompt: float = DEFAULT_PROMPT_PRICE_PER_M,
    price_per_m_completion: float = DEFAULT_COMPLETION_PRICE_PER_M,
) -> EfficiencyResult:
    total_toks = prompt_tokens + completion_tokens + thought_tokens
    cost = compute_cost(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        thought_tokens=thought_tokens,
        price_per_m_prompt=price_per_m_prompt,
        price_per_m_completion=price_per_m_completion,
    )

    if total_elements > 0:
        cascade_rate = round((cascaded_count / total_elements) * 100, 2)
    else:
        cascade_rate = 0.0

    return EfficiencyResult(
        api_calls=max(0, api_calls),
        prompt_tokens=max(0, prompt_tokens),
        completion_tokens=max(0, completion_tokens),
        thought_tokens=max(0, thought_tokens),
        total_tokens=max(0, total_toks),
        cost_usd=cost,
        cascaded_count=max(0, cascaded_count),
        patched_count=max(0, patched_count),
        total_elements=max(0, total_elements),
        cascade_rate=cascade_rate,
    )


def calculate_efficiency_from_run(
    run: Any,
    price_per_m_prompt: float = DEFAULT_PROMPT_PRICE_PER_M,
    price_per_m_completion: float = DEFAULT_COMPLETION_PRICE_PER_M,
) -> EfficiencyResult:
    """Calculate per-document Repair Efficiency directly from a RepairRun object."""
    if run is None:
        return calculate_efficiency(0, 0, 0, 0)

    steps = getattr(run, "steps", [])
    api_calls = getattr(run, "api_calls", sum(1 for s in steps if getattr(s, "llm", None)))
    prompt_tokens = getattr(run, "prompt_tokens", sum(s.llm.prompt_tokens for s in steps if getattr(s, "llm", None)))
    completion_tokens = getattr(
        run, "completion_tokens", sum(s.llm.completion_tokens for s in steps if getattr(s, "llm", None))
    )
    thought_tokens = getattr(
        run, "thought_tokens", sum(getattr(s.llm, "thought_tokens", 0) for s in steps if getattr(s, "llm", None))
    )

    cascaded_count = sum(1 for s in steps if getattr(s, "status", "") == "cascade_resolved")
    patched_count = sum(1 for s in steps if getattr(s, "status", "") == "applied")
    total_elements = len(steps)

    return calculate_efficiency(
        api_calls=api_calls,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        thought_tokens=thought_tokens,
        cascaded_count=cascaded_count,
        patched_count=patched_count,
        total_elements=total_elements,
        price_per_m_prompt=price_per_m_prompt,
        price_per_m_completion=price_per_m_completion,
    )
