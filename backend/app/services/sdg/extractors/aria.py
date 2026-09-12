from bs4 import BeautifulSoup, Tag

Edge = tuple[str, str, str]


ARIA_ATTRIBUTES = [
    "aria-labelledby",
    "aria-describedby",
    "aria-controls",
    "aria-owns",
    "aria-errormessage",
]


def extract_aria_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str]
):
    edges: list[Edge] = []

    for tag in soup.find_all(True):
        if tag not in element_to_id:
            continue

        source_id = element_to_id[tag]

        for attr in ARIA_ATTRIBUTES:
            attr_value = tag.get(attr)
            if not attr_value:
                continue

            referenced_ids = str(attr_value).split()

            for ref_id in referenced_ids:
                target = soup.find(id=ref_id)

                if target and target in element_to_id:
                    target_id = element_to_id[target]

                    relation_name = attr.replace("-", "_")
                    edges.append((source_id, target_id, relation_name))

    return edges
