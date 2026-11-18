from dataclasses import dataclass, field
from typing import Any

import html5lib
from bs4 import BeautifulSoup, Doctype
from html5lib.constants import E as PARSE_ERROR_MESSAGES


@dataclass
class SafetyResult:
    """Per-document Repair Safety metrics as defined in Section 3 of the thesis manuscript."""

    is_valid: bool | None
    score: int | None  # S_i: 1 if valid, 0 if invalid; null if the checker failed
    reason: str
    element_count: int = 0
    warnings: list[str] = field(default_factory=list)
    parse_mode: str | None = None
    parse_errors: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "score": self.score,
            "reason": self.reason,
            "element_count": self.element_count,
            "warnings": self.warnings,
            "parser": "html5lib",
            "parser_version": html5lib.__version__,
            "parse_mode": self.parse_mode,
            "fragment_context": "div" if self.parse_mode == "fragment" else None,
            "error_count": len(self.parse_errors) if self.parse_errors is not None else None,
            "errors": self.parse_errors,
        }


def _has_document_markup(soup: BeautifulSoup) -> bool:
    # html.parser can treat literal '<html>' inside textarea/title as a tag.
    # Such text must not turn an otherwise valid fragment into a document.
    text_containers = {"script", "style", "title", "textarea", "xmp", "iframe", "noembed", "noframes", "plaintext"}
    return any(
        node.find_parent(text_containers) is None for node in soup.find_all(["html", "head", "body"])
    ) or any(
        isinstance(node, Doctype) for node in soup.contents
    )


def calculate_safety(html: str | None, *, html_original: str | None = None) -> SafetyResult:
    """Check the supplied artifact for HTML parsing errors, without rewriting it.

    Document markup in either the original or candidate selects document parsing;
    otherwise use a div-context fragment. All reported parse errors count, including
    a missing doctype in document mode. This is not a full conformance validator.
    """
    if not html or not isinstance(html, str) or not html.strip():
        return SafetyResult(
            is_valid=False,
            score=0,
            reason="empty_html",
            element_count=0,
            warnings=["HTML string is empty or whitespace"],
        )

    warnings: list[str] = []

    # Check for unstripped markdown fences
    if html.strip().startswith("```") or html.strip().endswith("```"):
        warnings.append("contains_markdown_fences")

    parse_mode = None
    try:
        # Inspect explicit markup only. BeautifulSoup's recovered tree is never
        # passed to the validator: html5lib must see the actual supplied string.
        source = BeautifulSoup(html, "html.parser")
        is_document = _has_document_markup(source)
        if html_original and not is_document:
            is_document = _has_document_markup(BeautifulSoup(html_original, "html.parser"))
        parse_mode = "document" if is_document else "fragment"
        parser = html5lib.HTMLParser(strict=False, namespaceHTMLElements=False)
        if is_document:
            tree = parser.parse(html, scripting=False)
        else:
            tree = parser.parseFragment(html, container="div", scripting=False)
        errors = [
            {
                "line": position[0], "column": position[1], "code": code,
                "message": PARSE_ERROR_MESSAGES.get(code, code) % data,
            }
            for position, code, data in parser.errors
        ]
        # Exclude comments and the synthetic DOCUMENT_FRAGMENT root.
        element_count = sum(isinstance(node.tag, str) for node in tree.iter())
        if not is_document:
            element_count -= 1
    except Exception as exc:  # noqa: BLE001
        return SafetyResult(
            is_valid=None, score=None, reason="validator_error",
            warnings=warnings + [f"{type(exc).__name__}: {exc}"], parse_mode=parse_mode,
        )

    if errors:
        reason = "parse_errors"
    elif source.find(True) is None:
        # A document parser synthesizes html/head/body even for text-only input.
        reason = "no_elements"
        warnings.append("No HTML elements found in supplied output")
    else:
        reason = "valid"

    return SafetyResult(
        is_valid=reason == "valid",
        score=int(reason == "valid"),
        reason=reason,
        element_count=element_count,
        warnings=warnings,
        parse_mode=parse_mode,
        parse_errors=errors,
    )
