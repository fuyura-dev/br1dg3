from bs4 import BeautifulSoup, Tag

Edge = tuple[str, str, str]
relation = "focus_order"

FOCUSABLE = {"button", "select", "textarea"}


def _is_focusable(tag: Tag):
    if tag.has_attr("disabled"):
        return False, None

    if tag.name == "input" and tag.get("type", "").lower() == "hidden":
        return False, None

    if tag.has_attr("tabindex"):
        val = int(tag["tabindex"])
        if val < 0:
            return False, None

        return True, val

    if tag.name in FOCUSABLE:
        return True, 0

    if tag.name == "input":
        return True, 0
    
    if tag.name == "a" and tag.has_attr("href"):
        return True, 0

    return False, None


def extract_focus_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str]
):
    edges: list[Edge] = []

    positive_tabindex: list[tuple[int, int, Tag]] = []
    default_tabindex: list[Tag] = []

    for dom_index, tag in enumerate(soup.find_all(True)):
        if tag not in element_to_id:
            continue

        focusable, tab_val = _is_focusable(tag)
        if not focusable:
            continue

        if tab_val and tab_val > 0:
            positive_tabindex.append((tab_val, dom_index, tag))
        else:
            default_tabindex.append(tag)

    positive_tabindex.sort(key=lambda item: (item[0], item[1]))

    ordered_focusable = [item[2] for item in positive_tabindex] + default_tabindex

    for i in range(len(ordered_focusable) - 1):
        source_id = element_to_id[ordered_focusable[i]]
        target_id = element_to_id[ordered_focusable[i + 1]]
        edges.append((source_id, target_id, relation))

    return edges
