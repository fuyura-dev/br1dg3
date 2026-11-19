"""Bounds and original-content references for shortened root repair inputs."""

from dataclasses import dataclass
from hashlib import sha256

from bs4 import NavigableString, Tag

# Character limits, not model-token limits. Freeze these with experiment settings.
ROOT_MARKUP_CHAR_LIMIT = 8_000
ROOT_LITERAL_CHAR_LIMIT = 160
CONTENT_PREFIX = "__BR1DG3_CONTENT_"
HIDDEN_ROOT_TAGS = {"script", "style", "link", "meta", "noscript", "svg", "template"}


class RootViewTooLarge(ValueError):
    """Even the coarsest root view cannot fit without hiding root attributes."""


class RootPatchError(ValueError):
    """A shortened reply cannot be reconstructed unambiguously."""


@dataclass(frozen=True)
class ContentReference:
    node: Tag | NavigableString
    parent: Tag


def content_references(root: Tag) -> dict[str, ContentReference]:
    """Stable per-current-target keys; duplicate text occurrences have different keys."""
    references = {}
    for index, node in enumerate(root.descendants):
        if isinstance(node, NavigableString) or isinstance(node, Tag) and node.name in HIDDEN_ROOT_TAGS:
            value = f"{type(node).__name__}:{node}"
            digest = sha256(value.encode("utf-8")).hexdigest()[:12]
            key = f"{CONTENT_PREFIX}{index}_{digest}__"
            references[key] = ContentReference(node, node.parent)
    return references
