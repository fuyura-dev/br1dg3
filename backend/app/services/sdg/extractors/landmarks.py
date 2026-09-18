from bs4 import BeautifulSoup, Tag

Edge = tuple[str, str, str]
relation = "landmark_structure"

LANDMARK_TAGS = {
    "header",
    "nav",
    "main",
    "aside",
    "footer",
    "search",
}


LANDMARK_ROLES = {
    "banner",
    "navigation",
    "main",
    "complementary",
    "contentinfo",
    "search",
    "region",
}


def _is_landmark(tag: Tag):
    if tag.name in LANDMARK_TAGS:
        return True
    role = tag.get("role")
    return bool(role and role.lower() in LANDMARK_ROLES)


def extract_landmark_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str]
):
    edges: list[Edge] = []

    landmarks: list[Tag] = []
    for tag in soup.find_all(True):
        if tag in element_to_id and _is_landmark(tag):
            landmarks.append(tag)

    for landmark in landmarks:
        for parent in landmark.parents:
            if parent in element_to_id and _is_landmark(parent):
                source_id = element_to_id[parent]
                target_id = element_to_id[landmark]
                edges.append((source_id, target_id, relation))
                break

    return edges

