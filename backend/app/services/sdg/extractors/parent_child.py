from bs4 import BeautifulSoup, Tag

Edge = tuple[str, str, str]
relation = "parent_child"
nested_relation = "nested_container"

# key:value
# parent tag name: expected child tag name
CONTAINER_RULES = {
    "ul": ["li"],
    "ol": ["li"],
    "menu": ["li"],

    "dl": ["dt", "dd"],

    "table": ["caption", "thead", "tbody", "tfoot", "tr"],
    "thead": ["tr"],
    "tbody": ["tr"],
    "tfoot": ["tr"],
    "tr": ["th", "td"],

    "select": ["optgroup", "option"],
    "optgroup": ["option"],

    "datalist": ["option"]
}

# key:value
# parent tag name: nested container tag name
NESTED_CONTAINER_RULES = {
    "li": ["ul", "ol", "menu"],
    "th": ["table"],
    "td": ["table"],
}


def _extract_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str],
        rules: dict[str, list[str]],
        relation_name: str
):
    edges: list[Edge] = []

    for parent_tag, allowed_children in rules.items():
        parents = soup.find_all(parent_tag)

        for parent in parents:
            parent_id = element_to_id.get(parent)
            if not parent_id:
                continue

            children = parent.find_all(allowed_children, recursive=False)

            for child in children:
                child_id = element_to_id.get(child)
                if child_id:
                    edges.append((parent_id, child_id, relation_name))
    return edges


def extract_parent_child_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str]
):
    edges: list[Edge] = []

    edges += _extract_edges(soup, element_to_id, CONTAINER_RULES, relation)
    edges += _extract_edges(soup, element_to_id, NESTED_CONTAINER_RULES, nested_relation)

    return edges