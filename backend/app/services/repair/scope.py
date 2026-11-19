"""Bounded editable scopes and the SDG reply envelope."""

import json
from collections import Counter
from dataclasses import dataclass

from bs4 import BeautifulSoup, Comment, Doctype, NavigableString, Tag

from app.services.repair.patch import (
    PatchResult,
    apply_block_reply,
    apply_reply,
    outer_html,
)
from app.services.repair.root_view import ROOT_MARKUP_CHAR_LIMIT, RootViewTooLarge

# Input-scope settings; freeze before experiments. Parent expansion has a
# smaller budget so limiting surrounding context does not skip larger targets.
TARGET_CHAR_LIMIT = 8_000
TARGET_ELEMENT_LIMIT = 80
BLOCK_CHAR_LIMIT = 3_000
BLOCK_ELEMENT_LIMIT = 30
EXCLUDED_BLOCK_ROOTS = {"[document]", "html", "head", "body"}


@dataclass
class EditScope:
    target: Tag
    target_markup: str
    block: Tag | None
    block_markup: str | None
    reason: str

    @property
    def allowed(self):
        return ["target", "block"] if self.block is not None else ["target"]

    def contains(self, element):
        root = self.block if self.block is not None else self.target
        return element is root or any(parent is root for parent in element.parents)

    def record(self, element_ids):
        root = self.block if self.block is not None else self.target
        markup = self.block_markup if self.block is not None else self.target_markup
        shortened_root = self.target.name in {"html", "body"}
        character_limit = BLOCK_CHAR_LIMIT if self.block is not None else TARGET_CHAR_LIMIT
        element_limit = BLOCK_ELEMENT_LIMIT if self.block is not None else TARGET_ELEMENT_LIMIT
        return {
            "allowed": self.allowed, "reason": self.reason,
            "root_node_id": element_ids[root], "root_tag": root.name,
            "markup_characters": len(markup), "original_elements": 1 + len(root.find_all(True)),
            "character_limit": ROOT_MARKUP_CHAR_LIMIT if shortened_root else character_limit,
            "element_limit": None if shortened_root else element_limit,
            "parent_character_limit": BLOCK_CHAR_LIMIT, "parent_element_limit": BLOCK_ELEMENT_LIMIT,
            "reply_character_limit": None, "reply_element_limit": None,
            "max_parent_hops": 1, "shortened_root": shortened_root,
        }


def _fits(element, markup, *, character_limit, element_limit):
    return len(markup) <= character_limit and 1 + len(element.find_all(True)) <= element_limit


def select_scope(target, *, root_markup=None):
    if target.name in {"html", "body"}:
        if root_markup is None:
            raise ValueError("Root targets require their bounded shallow view.")
        return EditScope(target, root_markup, None, None, "document_root")
    markup = outer_html(target)
    if not _fits(target, markup, character_limit=TARGET_CHAR_LIMIT, element_limit=TARGET_ELEMENT_LIMIT):
        raise RootViewTooLarge(
            f"Target markup exceeds the scope limit ({len(markup)} characters, "
            f"{1 + len(target.find_all(True))} elements; limits {TARGET_CHAR_LIMIT}/{TARGET_ELEMENT_LIMIT})."
        )
    parent = target.parent
    if not isinstance(parent, Tag) or parent.name in EXCLUDED_BLOCK_ROOTS:
        return EditScope(target, markup, None, None, "no_eligible_parent")
    parent_markup = outer_html(parent)
    if not _fits(parent, parent_markup, character_limit=BLOCK_CHAR_LIMIT, element_limit=BLOCK_ELEMENT_LIMIT):
        return EditScope(target, markup, None, None, "parent_too_large")
    return EditScope(target, markup, parent, parent_markup, "immediate_parent")


@dataclass(frozen=True)
class ScopedReply:
    scope: str
    html: str


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def parse_scoped_reply(text):
    """Strict JSON only: never guess scope from bare HTML, fences or prose."""
    if not isinstance(text, str) or not text.strip():
        return None, "empty_reply"
    try:
        data = json.loads(text, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        return None, "invalid_reply_envelope"
    if not isinstance(data, dict) or set(data) != {"scope", "html"}:
        return None, "invalid_reply_envelope"
    if not isinstance(data["scope"], str) or data["scope"] not in {"target", "block"}:
        return None, "invalid_reply_scope"
    if not isinstance(data["html"], str) or not data["html"].strip():
        return None, "invalid_reply_html"
    reply = ScopedReply(data["scope"], data["html"])
    return reply, None


def apply_scoped_reply(selection, reply, token):
    if reply.scope not in selection.allowed:
        return PatchResult(False, "patch_rejected", ["scope_not_allowed"])
    parsed = BeautifulSoup(reply.html, "html.parser")
    elements = [node for node in parsed.contents if isinstance(node, Tag)]
    if not elements:
        return PatchResult(False, "no_element")
    # Do not silently discard prose or comments outside the returned replacement.
    root_target = selection.target.name in {"html", "body"}
    if any(not isinstance(node, Tag) and str(node).strip()
           and not (root_target and isinstance(node, Doctype)) for node in parsed.contents):
        return PatchResult(False, "patch_rejected", ["outside_replacement_content"])
    forbidden_shells = ["html", "body"] + ([] if selection.target.name == "head" else ["head"])
    if not root_target and parsed.find(forbidden_shells) is not None:
        return PatchResult(False, "patch_rejected", ["document_shell_outside_scope"])
    if reply.scope == "block" and len(elements) != 1:
        return PatchResult(False, "patch_rejected", ["block_requires_one_root"])

    root = selection.block if reply.scope == "block" else selection.target
    document = root
    while document.parent is not None:
        document = document.parent
    inside = {id(root), *(id(el) for el in root.find_all(True))}
    outside_ids = {el["id"] for el in document.find_all(id=True) if id(el) not in inside}
    old_ids = Counter(el.get("id") for el in [root, *root.find_all(True)] if el.has_attr("id"))
    new_ids = Counter(el["id"] for el in parsed.find_all(id=True))
    if any(new_ids[value] > old_ids[value] for value in outside_ids):
        return PatchResult(False, "patch_rejected", ["outside_id_conflict"])

    # Ordinary scopes show complete markup. Preserve asset-restoration anchors;
    # the root reconstructor separately preserves/expands shortened references.
    if not root_target:
        def placeholders(node):
            return sum(isinstance(item, NavigableString) and not isinstance(item, Comment)
                       and str(item).strip() == "…" for item in node.descendants)
        if placeholders(parsed) > placeholders(root):
            return PatchResult(False, "patch_rejected", ["unexpanded_placeholder"])

        def stash_comments(node):
            return Counter(str(item) for item in node.descendants
                           if isinstance(item, Comment) and str(item).startswith("__BR1DG3_STASH_"))
        if stash_comments(root) != stash_comments(parsed):
            return PatchResult(False, "patch_rejected", ["asset_placeholder_changed"])

    if reply.scope == "block":
        return apply_block_reply(root, reply.html, token)
    # The envelope has already been decoded and checked. Fence-like text inside
    # real HTML content must not be mistaken for a response wrapper.
    return apply_reply(root, reply.html, token, clean=False)
