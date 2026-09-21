import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from bs4.formatter import HTMLFormatter

MARKER = "data-br1dg3"       # temporary tracking attribute: data-br1dg3="v1", "v2", ...


class _AsWritten(HTMLFormatter):
    """Like str(tag), but keeps the attribute order and writes <input ...> instead of <input .../>."""

    def attributes(self, tag):
        return [(k, None if v == "" else v) for k, v in tag.attrs.items()]   # None -> bare attribute


_AS_WRITTEN = _AsWritten(void_element_close_prefix="")


def outer_html(node):
    return node.decode(formatter=_AS_WRITTEN)


# ------------------------------------------------------------------ reading a reply
FENCE = re.compile(r"```[a-zA-Z]*\s*\n?(.*?)```", re.DOTALL)


def clean_reply(text):
    """Drop a code fence and any chatter before/after the HTML."""
    text = text or ""
    fenced = FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    text = text.strip()
    if "<" in text and ">" in text:
        text = text[text.index("<"): text.rindex(">") + 1]
    return text


@dataclass
class PatchResult:
    applied: bool
    status: str                                   # applied | empty_reply | no_element | multiple_elements
    warnings: list[str] = field(default_factory=list)


def apply_reply(target, reply, token):
    """Swap the reply in for `target` (in place). The reply must be exactly ONE element."""
    text = clean_reply(reply)
    if not text:
        return PatchResult(False, "empty_reply")
    elements = [c for c in BeautifulSoup(text, "html.parser").contents if isinstance(c, Tag)]
    if not elements:
        return PatchResult(False, "no_element")
    if len(elements) > 1:
        return PatchResult(False, "multiple_elements")
    new = elements[0]

    warnings = []
    if new.name != target.name:
        warnings.append("tag_changed")
    if new.get("id") != target.get("id"):
        warnings.append("id_changed")
    if new.get(MARKER) != token:                  # dropped or altered: put the target's marker back
        new[MARKER] = token
        warnings.append("marker_readded")
    inner = [e[MARKER] for e in target.find_all(attrs={MARKER: True})]
    warnings += [f"marker_lost:{t}" for t in inner if new.find(attrs={MARKER: t}) is None]
    if new == target:                             # same name, attributes and children
        warnings.append("unchanged")

    target.replace_with(new)
    return PatchResult(True, "applied", warnings)


def parse_document_reply(reply):
    """Baseline: returns (html, "ok") or (None, reason)."""
    text = clean_reply(reply)
    if not text:
        return None, "empty_reply"
    if BeautifulSoup(text, "html.parser").find(True) is None:
        return None, "not_html"
    return text, "ok"


def strip_markers(html):
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(attrs={MARKER: True}):
        del element[MARKER]
    return outer_html(soup)