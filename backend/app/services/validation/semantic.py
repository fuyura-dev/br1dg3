"""Preservation of extracted SDG edges, not validation of semantic correctness."""

from collections import Counter
from dataclasses import asdict, dataclass, field

from app.services.sdg.builder import SDGBuilder
from app.services.validation.semantic_matching import match_elements


@dataclass
class SemanticResult:
    # Legacy field names remain readable by existing API clients.
    dependencies_before: int | None
    dependencies_valid: int | None
    preservation_rate: float | None
    broken_count: int | None
    has_dependencies: bool | None
    breakdown_before: dict[str, int] = field(default_factory=dict)
    breakdown_valid: dict[str, int] = field(default_factory=dict)
    broken_examples: list[dict] = field(default_factory=list)
    metric: str = "sdg_relationship_preservation"
    metric_version: int = 2
    status: str = "measured"
    preserved_observed: int | None = None
    not_preserved_observed: int | None = None
    unresolved_count: int | None = None
    edge_outcomes: list[dict] = field(default_factory=list)
    matching: dict = field(default_factory=dict)
    error: dict | None = None

    def to_dict(self):
        result = asdict(self)
        result.update(
            relationships_before=self.dependencies_before,
            relationships_preserved=self.dependencies_valid,
            not_preserved_count=self.broken_count,
            breakdown_preserved=self.breakdown_valid,
        )
        return result


def _extract(html):
    if not isinstance(html, str):
        raise TypeError("An HTML string is required for SDG extraction.")
    builder = SDGBuilder(html)
    # Identity distinguishes repeated elements within each document.
    edges = []
    for source, target, data in builder.graph.edges(data=True):
        if builder.element_to_id.element(source) is None or builder.element_to_id.element(target) is None:
            raise ValueError("SDG edge has an unknown endpoint.")
        edges.append((data["relation"], source, target))
    return builder, sorted(set(edges))


def calculate_semantic_preservation(html_original, html_repaired, *, no_candidate=False):
    """Compatibility entry point for the version 2 relationship-preservation metric."""
    try:
        original, edges = _extract(html_original)
    except Exception as exc:  # noqa: BLE001 - retain unavailable measurement and failure evidence
        return SemanticResult(None, None, None, None, None, status="extraction_error",
                              error={"stage": "original", "type": type(exc).__name__, "message": str(exc)})

    count = len(edges)
    result = SemanticResult(count, None, None, None, bool(count),
                            breakdown_before=dict(Counter(edge[0] for edge in edges)))
    if not count:
        result.status = "no_relationships"
        result.dependencies_valid = 0
        result.broken_count = 0
        result.preserved_observed = result.not_preserved_observed = result.unresolved_count = 0
        return result
    if no_candidate:
        # Assigned credit, not measurement of the fallback or an empty candidate.
        result.status = "no_candidate_failure_policy"
        result.dependencies_valid = 0
        result.preservation_rate = 0.0
        return result

    try:
        repaired, repaired_edges = _extract(html_repaired)
        mapping, evidence = match_elements(original, repaired)
    except Exception as exc:  # noqa: BLE001 - other metrics must remain independently evaluable
        result.status = "extraction_error"
        result.error = {"stage": "candidate_or_matching", "type": type(exc).__name__, "message": str(exc)}
        return result

    result.matching = evidence
    repaired_edges = set(repaired_edges)
    observed = Counter()
    preserved_types = Counter()
    for relation, source, target in edges:
        mapped_source, mapped_target = mapping.get(source), mapping.get(target)
        if not repaired.graph.nodes:
            outcome = "not_preserved"  # An empty parsed candidate has no endpoints.
        elif mapped_source is None or mapped_target is None:
            outcome = "unresolved"
        elif (relation, mapped_source, mapped_target) in repaired_edges:
            outcome = "preserved"
            preserved_types[relation] += 1
        else:
            outcome = "not_preserved"
        observed[outcome] += 1
        record = {"relation": relation, "source": source, "target": target,
                  "matched_source": mapped_source, "matched_target": mapped_target, "outcome": outcome}
        result.edge_outcomes.append(record)
        if outcome == "not_preserved" and len(result.broken_examples) < 10:
            result.broken_examples.append(record)

    result.preserved_observed = observed["preserved"]
    result.not_preserved_observed = observed["not_preserved"]
    result.unresolved_count = observed["unresolved"]
    result.breakdown_valid = dict(preserved_types)
    if result.unresolved_count:
        result.status = "unresolved_matching"
    else:
        result.dependencies_valid = result.preserved_observed
        result.broken_count = result.not_preserved_observed
        result.preservation_rate = 100 * result.dependencies_valid / count
    return result
