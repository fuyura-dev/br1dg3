from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from bs4 import Tag

from app.services.sdg.builder import SDGBuilder


@dataclass
class SemanticResult:
    """Per-document Semantic Dependency Preservation metrics."""

    dependencies_before: int
    dependencies_valid: int
    preservation_rate: float
    broken_count: int
    has_dependencies: bool
    breakdown_before: dict[str, int] = field(default_factory=dict)
    breakdown_valid: dict[str, int] = field(default_factory=dict)
    broken_examples: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependencies_before": self.dependencies_before,
            "dependencies_valid": self.dependencies_valid,
            "preservation_rate": self.preservation_rate,
            "broken_count": self.broken_count,
            "has_dependencies": self.has_dependencies,
            "breakdown_before": self.breakdown_before,
            "breakdown_valid": self.breakdown_valid,
            "broken_examples": self.broken_examples,
        }


def get_element_signature(tag: Tag | None) -> str:
    """Produce a stable semantic identifier for a DOM element to track relationships across repairs."""
    if not tag or not hasattr(tag, "name"):
        return "null"

    # 1. Elements with ID
    tag_id = tag.get("id")
    if tag_id:
        return f"#{tag_id.strip()}"

    # 2. Form controls with name
    tag_name = tag.get("name")
    if tag_name:
        return f"{tag.name}[name='{tag_name.strip()}']"

    # 3. Links with href
    if tag.name == "a" and tag.get("href"):
        return f"a[href='{tag['href'].strip()}']"

    # 4. Images with src
    if tag.name == "img" and tag.get("src"):
        return f"img[src='{tag['src'].strip()}']"

    # 5. Semantic text-bearing elements (headings, labels, buttons, legends)
    text = tag.get_text(strip=True)
    if (
        text
        and len(text) <= 30
        and tag.name in {"label", "h1", "h2", "h3", "h4", "h5", "h6", "button", "legend", "summary", "th", "dt", "dd"}
    ):
        return f"{tag.name}:{text}"

    # 6. Fallback structural path with sibling index
    parent = getattr(tag, "parent", None)
    parent_sig = (
        f"#{parent['id']}"
        if parent and parent.get("id")
        else (getattr(parent, "name", "") if parent else "")
    )
    idx = 0
    if parent and hasattr(parent, "find_all"):
        idx = sum(1 for sib in parent.find_all(tag.name, recursive=False) if id(sib) <= id(tag))

    classes = ".".join(tag.get("class", [])) if tag.get("class") else ""
    cls_str = f".{classes}" if classes else ""
    return f"{parent_sig}>{tag.name}{cls_str}[{idx}]"


def extract_graph_signatures(html: str | None) -> tuple[set[tuple[str, str, str]], dict[str, int]]:
    """Build SDG on HTML and extract a set of normalized relationship signatures (relation, source_sig, target_sig)."""
    if not html or not isinstance(html, str) or not html.strip():
        return set(), {}

    try:
        builder = SDGBuilder(html)
    except Exception:  # noqa: BLE001
        return set(), {}

    signatures: set[tuple[str, str, str]] = set()
    relation_counts: Counter[str] = Counter()

    for u_id, v_id, data in builder.graph.edges(data=True):
        relation = data.get("relation", "unknown")
        try:
            u_tag = builder.element_to_id.element(u_id)
            v_tag = builder.element_to_id.element(v_id)
            u_sig = get_element_signature(u_tag)
            v_sig = get_element_signature(v_tag)
            signatures.add((relation, u_sig, v_sig))
            relation_counts[relation] += 1
        except Exception:  # noqa: BLE001, S112
            continue

    return signatures, dict(relation_counts)


def calculate_semantic_preservation(
    html_original: str | None,
    html_repaired: str | None,
) -> SemanticResult:
    orig_sigs, orig_counts = extract_graph_signatures(html_original)
    d_before = len(orig_sigs)

    if d_before == 0:
        return SemanticResult(
            dependencies_before=0,
            dependencies_valid=0,
            preservation_rate=100.0,
            broken_count=0,
            has_dependencies=False,
            breakdown_before={},
            breakdown_valid={},
            broken_examples=[],
        )

    rep_sigs, _ = extract_graph_signatures(html_repaired)
    preserved_sigs = orig_sigs.intersection(rep_sigs)
    d_valid = len(preserved_sigs)
    broken_sigs = orig_sigs - rep_sigs

    valid_counts: Counter[str] = Counter(sig[0] for sig in preserved_sigs)
    rate = round((d_valid / d_before) * 100, 2)

    broken_examples = [
        {"relation": sig[0], "source": sig[1], "target": sig[2]}
        for sig in list(broken_sigs)[:10]  # Cap at 10 examples for clean logging
    ]

    return SemanticResult(
        dependencies_before=d_before,
        dependencies_valid=d_valid,
        preservation_rate=rate,
        broken_count=len(broken_sigs),
        has_dependencies=True,
        breakdown_before=orig_counts,
        breakdown_valid=dict(valid_counts),
        broken_examples=broken_examples,
    )
