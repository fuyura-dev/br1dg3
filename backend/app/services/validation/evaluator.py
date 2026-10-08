from dataclasses import dataclass
from typing import Any

from app.services.detection.detect import detect
from app.services.validation.effectiveness import (
    EffectivenessResult,
    calculate_effectiveness,
)
from app.services.validation.efficiency import (
    EfficiencyResult,
    calculate_efficiency,
    calculate_efficiency_from_run,
)
from app.services.validation.safety import SafetyResult, calculate_safety
from app.services.validation.semantic import (
    SemanticResult,
    calculate_semantic_preservation,
)
from app.services.validation.structure import (
    StructureResult,
    calculate_structural_preservation,
)
from app.services.repair.log_streamer import streamer


@dataclass
class EvaluationReport:
    """Unified evaluation report combining all 5 core thesis metrics for a repaired document."""

    effectiveness: EffectivenessResult
    safety: SafetyResult
    structure: StructureResult
    efficiency: EfficiencyResult
    semantic: SemanticResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "effectiveness": self.effectiveness.to_dict(),
            "safety": self.safety.to_dict(),
            "structure": self.structure.to_dict(),
            "efficiency": self.efficiency.to_dict(),
            "semantic": self.semantic.to_dict(),
        }


def evaluate_repair(
    html_original: str,
    html_repaired: str,
    violations_before: list[dict] | None = None,
    violations_after: list[dict] | None = None,
    repair_run: Any = None,
    efficiency_data: dict[str, Any] | None = None,
    structure_threshold: float = 0.85,
    run_detection_if_missing: bool = True,
) -> EvaluationReport:
    """Evaluate a single HTML document repair across the 5 thesis metrics defined in Chapter 3."""
    # 1. Detection (if violations not pre-computed)
    scan_failed = False
    if violations_before is None and run_detection_if_missing:
        try:
            violations_before = detect(html_original)
        except Exception:  # noqa: BLE001
            violations_before = []

    if violations_after is None and run_detection_if_missing:
        try:
            violations_after = detect(html_repaired)
        except Exception:  # noqa: BLE001
            scan_failed = True
            violations_after = None

    # 1. Metric 1: Repair Effectiveness
    effectiveness = calculate_effectiveness(
        violations_before=violations_before or [],
        violations_after=violations_after,
        scan_failed=scan_failed,
    )
    streamer.log(
        f"[METRICS] 1/5 Effectiveness: {effectiveness.reduction_rate}% violation reduction "
        f"({effectiveness.violations_before} -> {effectiveness.violations_after} violations)"
    )

    # 2. Metric 2: Repair Safety (Syntactic Validity)
    safety = calculate_safety(html_repaired)
    status_str = "Valid" if safety.is_valid else f"Invalid ({safety.reason})"
    streamer.log(f"[METRICS] 2/5 Safety: Syntactic {status_str} ({safety.element_count} elements)")

    # 3. Metric 3: Structural Preservation
    structure = calculate_structural_preservation(
        html_original=html_original,
        html_repaired=html_repaired,
        threshold=structure_threshold,
    )
    streamer.log(
        f"[METRICS] 3/5 Structure: TED={structure.tree_edit_distance} edits on max {structure.max_nodes} DOM "
        f"({structure.structure_similarity * 100:.2f}% preserved)"
    )

    # 4. Metric 4: Repair Efficiency
    if repair_run is not None:
        efficiency = calculate_efficiency_from_run(repair_run)
    elif efficiency_data is not None:
        efficiency = calculate_efficiency(
            api_calls=efficiency_data.get("api_calls", 0),
            prompt_tokens=efficiency_data.get("prompt_tokens", 0),
            completion_tokens=efficiency_data.get("completion_tokens", 0),
            thought_tokens=efficiency_data.get("thought_tokens", 0),
            cascaded_count=efficiency_data.get("cascaded_count", 0),
            patched_count=efficiency_data.get("patched_count", 0),
            total_elements=efficiency_data.get("total_elements", 0),
        )
    else:
        efficiency = calculate_efficiency(0, 0, 0, 0)
    streamer.log(
        f"[METRICS] 4/5 Efficiency: {efficiency.total_tokens} tokens across {efficiency.api_calls} API calls "
        f"(${efficiency.cost_usd:.4f})"
    )

    # 5. Metric 5: Semantic Dependency Preservation
    semantic = calculate_semantic_preservation(
        html_original=html_original,
        html_repaired=html_repaired,
    )
    streamer.log(
        f"[METRICS] 5/5 Semantic: {semantic.dependencies_valid} of {semantic.dependencies_before} relationships intact "
        f"({semantic.preservation_rate}%)"
    )

    return EvaluationReport(
        effectiveness=effectiveness,
        safety=safety,
        structure=structure,
        efficiency=efficiency,
        semantic=semantic,
    )
