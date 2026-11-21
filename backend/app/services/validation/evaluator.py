from dataclasses import dataclass, field
from typing import Any

from app.services.detection.detect import DetectionError, scan_with_report
from app.services.repair.log_streamer import streamer
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
    count_nodes,
    html_to_tree,
)


class MissingInitialScanError(ValueError):
    """No pre-repair scan was supplied and automatic detection is disabled."""


@dataclass
class EvaluationReport:
    """Unified evaluation report combining all 5 core thesis metrics for a repaired document."""

    effectiveness: EffectivenessResult
    safety: SafetyResult
    structure: StructureResult
    efficiency: EfficiencyResult
    semantic: SemanticResult
    evaluation: dict[str, Any]
    scan_reports: dict[str, Any] = field(default_factory=lambda: {"before": None, "after": None})

    def to_dict(self) -> dict[str, Any]:
        return {
            "effectiveness": self.effectiveness.to_dict(),
            "safety": self.safety.to_dict(),
            "structure": self.structure.to_dict(),
            "efficiency": self.efficiency.to_dict(),
            "semantic": self.semantic.to_dict(),
            "evaluation": self.evaluation,
            "scan_reports": self.scan_reports,
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
    fallback_used: bool = False,
) -> EvaluationReport:
    """Evaluate a single HTML document repair across the 5 thesis metrics defined in Chapter 3."""
    if repair_run is not None:
        fallback_used = repair_run.fallback_used
        if repair_run.candidate_html is not None:
            html_repaired = repair_run.candidate_html
    evaluation = {
        "artifact": "no_candidate" if fallback_used else "supplied_html",
        "score_basis": "no_candidate_failure_policy" if fallback_used else "artifact_measurement",
        "fallback_used": fallback_used,
    }
    if repair_run is not None and not fallback_used:
        evaluation["artifact"] = "candidate" if repair_run.candidate_html is not None else "unchanged_input"
    # 1. Detection (if violations not pre-computed)
    scan_reports = {"before": None, "after": None}
    scan_failed = False
    if violations_before is None:
        if not run_detection_if_missing:
            raise MissingInitialScanError(
                "violations_before is required when run_detection_if_missing is false."
            )
        try:
            scan_before = scan_with_report(html_original)
            violations_before = scan_before.violations
            scan_reports["before"] = scan_before.report
        except Exception as exc:
            raise DetectionError(
                f"Pre-repair accessibility detection failed: {exc}"
            ) from exc

    if violations_after is None and run_detection_if_missing and not fallback_used:
        try:
            scan_after = scan_with_report(html_repaired)
            violations_after = scan_after.violations
            scan_reports["after"] = scan_after.report
        except Exception as exc:  # noqa: BLE001 - any failed final scan receives no credit
            streamer.log(f"[EVALUATION] Post-repair detection failed: {exc}")
            scan_failed = True
            violations_after = None

    # 1. Metric 1: Repair Effectiveness
    effectiveness = calculate_effectiveness(
        violations_before=violations_before,
        violations_after=violations_after,
        scan_failed=scan_failed,
        no_candidate=fallback_used,
    )
    streamer.log(
        f"[METRICS] 1/5 Effectiveness: {effectiveness.reduction_rate}% violation reduction "
        f"({effectiveness.violations_before} -> {effectiveness.violations_after} violations)"
    )

    # 2. Metric 2: Repair Safety (Syntactic Validity)
    safety = (
        SafetyResult(False, 0, "no_candidate", warnings=["Assigned no credit: no accepted repair candidate."])
        if fallback_used else calculate_safety(html_repaired, html_original=html_original)
    )
    status_str = (
        "Unavailable (validator_error)" if safety.is_valid is None
        else "Valid" if safety.is_valid else f"Invalid ({safety.reason})"
    )
    streamer.log(
        f"[METRICS] 2/5 Safety: Syntactic {status_str} ({safety.element_count} elements)"
    )

    # 3. Metric 3: Structural Preservation
    if fallback_used:
        # There is no candidate tree: zero is a policy score, not measured TED.
        structure = StructureResult(
            tree_edit_distance=None, original_nodes=count_nodes(html_to_tree(html_original)),
            repaired_nodes=None, max_nodes=None, structure_similarity=0.0,
            structure_preserved=False, threshold=structure_threshold,
        )
    else:
        structure = calculate_structural_preservation(
            html_original=html_original,
            html_repaired=html_repaired,
            threshold=structure_threshold,
        )
    if fallback_used:
        streamer.log("[METRICS] 3/5 Structure: no candidate; zero credit assigned, TED not measured.")
    else:
        streamer.log(
            f"[METRICS] 3/5 Structure: TED={structure.tree_edit_distance} edits on max {structure.max_nodes} DOM "
            f"({structure.structure_similarity * 100:.2f}% preserved)"
        )

    # 4. Metric 4: Repair Efficiency
    if repair_run is not None:
        efficiency = calculate_efficiency_from_run(repair_run)
    elif efficiency_data is not None:
        efficiency = calculate_efficiency(
            api_calls=efficiency_data.get("api_calls"),
            prompt_tokens=efficiency_data.get("prompt_tokens"),
            completion_tokens=efficiency_data.get("completion_tokens"),
            thought_tokens=efficiency_data.get("thought_tokens"),
            cascaded_count=efficiency_data.get("cascaded_count", 0),
            patched_count=efficiency_data.get("patched_count", 0),
            total_elements=efficiency_data.get("total_elements", 0),
            **{key: efficiency_data[key] for key in (
                "total_tokens", "requests", "known_requests", "request_count_complete",
                "reported_usage", "usage_complete", "total_tokens_source",
                "completed_response_count", "completed_response_usage",
            ) if key in efficiency_data},
        )
    else:
        efficiency = calculate_efficiency(None, None, None, None, total_tokens=None)
    cost_label = f"${efficiency.cost_usd:.4f}" if efficiency.cost_usd is not None else "unavailable"
    tokens_label = efficiency.total_tokens if efficiency.total_tokens is not None else "unavailable"
    calls_label = efficiency.api_calls if efficiency.api_calls is not None else "unavailable"
    streamer.log(
        f"[METRICS] 4/5 Efficiency: {tokens_label} tokens across {calls_label} generations "
        f"(legacy cost estimate: {cost_label})"
    )

    # 5. Metric 5: modeled SDG relationship preservation, not semantic validity.
    semantic = calculate_semantic_preservation(
        html_original=html_original,
        html_repaired=None if fallback_used else html_repaired,
        no_candidate=fallback_used,
    )
    if fallback_used:
        streamer.log("[METRICS] No accepted candidate: failure-policy scores; fallback HTML was not scored.")
    preservation = f"{semantic.preservation_rate:.2f}%" if semantic.preservation_rate is not None else "N/A"
    streamer.log(
        f"[METRICS] 5/5 SDG relationship preservation: {preservation} ({semantic.status}); "
        f"preserved={semantic.dependencies_valid}, original={semantic.dependencies_before}"
    )

    return EvaluationReport(
        effectiveness=effectiveness,
        safety=safety,
        structure=structure,
        efficiency=efficiency,
        semantic=semantic,
        evaluation=evaluation,
        scan_reports=scan_reports,
    )
