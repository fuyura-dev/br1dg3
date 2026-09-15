from bs4 import BeautifulSoup, Tag

Edge = tuple[str, str, str]
relation = "heading_hierarchy"


def extract_heading_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str]
):
    edges: list[Edge] = []

    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

    stack: list[tuple[int, Tag]] = []

    for h in headings:
        if h not in element_to_id:
            continue

        level = int(h.name[1])

        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            parent_tag = stack[-1][1]
            source_id = element_to_id[parent_tag]
            target_id = element_to_id[h]

            edges.append((source_id, target_id, relation))

        stack.append((level, h))

    return edges

