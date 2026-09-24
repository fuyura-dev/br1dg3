from dataclasses import dataclass
from typing import Any


@dataclass
class EffectivenessResult:
    """Per-document Repair Effectiveness metrics."""

    violations_before: int
    violations_after: int
    violations_reduced: int
    compliance_improved: bool
    fully_fixed: bool
    reduction_rate: float
    rules_before: int = 0
    rules_after: int = 0
    scan_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations_before": self.violations_before,
            "violations_after": self.violations_after,
            "violations_reduced": self.violations_reduced,
            "compliance_improved": self.compliance_improved,
            "fully_fixed": self.fully_fixed,
            "reduction_rate": self.reduction_rate,
            "rules_before": self.rules_before,
            "rules_after": self.rules_after,
            "scan_failed": self.scan_failed,
        }


def count_violations(violations: list[dict] | None) -> int:
    """Same granularity as Axe-core and ScanResponse.total_issues: one count per violation node."""
    if not violations:
        return 0
    return sum(len(v.get("nodes", [])) for v in violations)


def count_unique_rules(violations: list[dict] | None) -> int:
    """Count of distinct Axe rule IDs violated."""
    if not violations:
        return 0
    return len({v.get("id") for v in violations if v.get("id")})


def calculate_effectiveness(
    violations_before: list[dict] | int,
    violations_after: list[dict] | int | None,
    scan_failed: bool = False,
) -> EffectivenessResult:
    """Calculate per-document Repair Effectiveness."""
    if isinstance(violations_before, list):
        v_before = count_violations(violations_before)
        r_before = count_unique_rules(violations_before)
    else:
        v_before = max(0, int(violations_before))
        r_before = 0

    if scan_failed or violations_after is None:
        return EffectivenessResult(
            violations_before=v_before,
            violations_after=v_before,
            violations_reduced=0,
            compliance_improved=False,
            fully_fixed=False,
            reduction_rate=0.0,
            rules_before=r_before,
            rules_after=r_before,
            scan_failed=True,
        )

    if isinstance(violations_after, list):
        v_after = count_violations(violations_after)
        r_after = count_unique_rules(violations_after)
    else:
        v_after = max(0, int(violations_after))
        r_after = 0

    v_reduced = v_before - v_after
    compliance_improved = v_after < v_before
    fully_fixed = (v_after == 0)

    if v_before > 0:
        reduction_rate = round((v_reduced / v_before) * 100, 2)
    else:
        reduction_rate = 100.0 if v_after == 0 else 0.0

    return EffectivenessResult(
        violations_before=v_before,
        violations_after=v_after,
        violations_reduced=v_reduced,
        compliance_improved=compliance_improved,
        fully_fixed=fully_fixed,
        reduction_rate=reduction_rate,
        rules_before=r_before,
        rules_after=r_after,
        scan_failed=False,
    )
