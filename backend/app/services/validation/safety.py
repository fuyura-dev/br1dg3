from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup


@dataclass
class SafetyResult:
    """Per-document Repair Safety metrics as defined in Section 3 of the thesis manuscript."""

    is_valid: bool
    score: int  # S_i: 1 if valid, 0 if invalid
    reason: str  # "valid", "empty_html", "no_elements", "truncated_tag", etc.
    element_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "score": self.score,
            "reason": self.reason,
            "element_count": self.element_count,
            "warnings": self.warnings,
        }


def calculate_safety(html: str | None) -> SafetyResult:
    """Calculate per-document Repair Safety (Syntactic Validity)."""
    if not html or not isinstance(html, str) or not html.strip():
        return SafetyResult(
            is_valid=False,
            score=0,
            reason="empty_html",
            element_count=0,
            warnings=["HTML string is empty or whitespace"],
        )

    text = html.strip()
    warnings: list[str] = []

    # Check for unstripped markdown fences
    if text.startswith("```") or text.endswith("```"):
        warnings.append("contains_markdown_fences")

    # Check for truncated trailing tag bracket, e.g. `<div id="...` cut off at EOF
    last_open = text.rfind("<")
    last_close = text.rfind(">")
    if last_open > last_close:
        return SafetyResult(
            is_valid=False,
            score=0,
            reason="truncated_tag",
            element_count=0,
            warnings=["Document ends with an unclosed tag bracket '<'"],
        )

    try:
        soup = BeautifulSoup(text, "html.parser")
    except Exception as exc:  # noqa: BLE001
        return SafetyResult(
            is_valid=False,
            score=0,
            reason=f"parser_exception:{type(exc).__name__}",
            element_count=0,
            warnings=[str(exc)],
        )

    elements = soup.find_all(True)
    element_count = len(elements)

    if element_count == 0:
        return SafetyResult(
            is_valid=False,
            score=0,
            reason="no_elements",
            element_count=0,
            warnings=["No valid HTML elements found in document"],
        )

    return SafetyResult(
        is_valid=True,
        score=1,
        reason="valid",
        element_count=element_count,
        warnings=warnings,
    )
