"""Narrow DOM evidence for skipping a scheduled rule, not an Axe revalidation."""

from bs4 import Tag

# The old name is read for historical records; new runs emit cascade_skipped.
CASCADE_SKIP_STATUSES = {"cascade_skipped", "cascade_resolved"}
_LANDMARK_TAGS = {"main", "nav", "aside", "search"}
_LANDMARK_ROLES = {"main", "navigation", "complementary", "search", "banner", "contentinfo"}


def _role(element):
    # Multiple/fallback roles and empty/unknown roles are intentionally unsupported.
    return str(element["role"]).strip() if element.has_attr("role") else None


def _simple_landmark(element):
    role = _role(element)
    if role is not None:
        return role if role in _LANDMARK_ROLES else None
    return element.name if element.name in _LANDMARK_TAGS else None


def supported_condition(target: Tag, rule: str) -> str | None:
    """Describe a supported local condition, or leave the rule scheduled.

    This deliberately supports fewer cases than Axe. Named/context-dependent
    landmarks, rendered focusability and composed/shadow DOM need more evidence.
    The graph's broader landmark context is not used as a validity checker.
    """
    chain = [target, *target.parents]
    if rule == "region":
        # Hiding content is not evidence of a repaired landmark relationship.
        if any(el.has_attr("hidden") or el.has_attr("inert")
               or el.get("aria-hidden") not in (None, "false") for el in chain):
            return None
        for el in chain:
            landmark = _simple_landmark(el)
            if landmark:
                return f"Target is within a supported {landmark} landmark with no conflicting role."
    elif rule == "listitem" and target.name == "li" and not target.has_attr("role"):
        parent = target.parent
        if parent is not None and parent.name in {"ul", "ol", "menu"} and _role(parent) in (None, "list"):
            return f"List item has a direct {parent.name} parent with native or list role."
    elif rule == "dlitem" and target.name in {"dt", "dd"} and not target.has_attr("role"):
        parent = target.parent
        if parent is not None and parent.name == "div" and not parent.has_attr("role"):
            parent = parent.parent
        if parent is not None and parent.name == "dl" and _role(parent) in (None, "list"):
            return "Description-list item has a dl parent, directly or through one plain div group."
    elif rule == "aria-hidden-focus":
        # Do not infer focusability from tabindex, CSS, disabled, or event handlers.
        if all(el.get("aria-hidden") in (None, "false") for el in chain):
            return "The target and its ancestors no longer have an ARIA hiding condition."
    return None


def infer_skips(target, rules, original_conditions, *, has_accepted_patch):
    """Require both a prior accepted patch and an original-to-current transition."""
    if not has_accepted_patch:
        return []
    skipped = []
    for rule in rules:
        # Missing baseline evidence must not be treated as an unmet condition.
        if rule not in original_conditions or original_conditions[rule] is not None:
            continue
        reason = supported_condition(target, rule)
        if reason is not None:
            skipped.append({
                "rule_id": rule, "reason": reason,
                "basis": "changed_from_original", "verification": "local_dom_only",
            })
    return skipped
