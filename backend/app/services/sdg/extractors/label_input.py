from bs4 import BeautifulSoup, Tag

relation = "label_input"
Edge = tuple[str, str, str]


def extract_label_input_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str]
):
    edges: list[Edge] = []

    for label in soup.find_all("label"):
        if label not in element_to_id:
            continue

        label_id = element_to_id[label]

        for_id = label.get("for")
        if for_id:
            target = soup.find(id=for_id)
            if target and target in element_to_id:
                target_id = element_to_id[target]
                edges.append((label_id, target_id, relation))

        for nested in label.find_all(["input", "select", "textarea"]):
            if nested in element_to_id:
                target_id = element_to_id[nested]
                edges.append((label_id, target_id, relation))

    return edges
