from bs4 import BeautifulSoup, Tag

Edge = tuple[str, str, str]
relation = "id_reference"

ID_ATRRIBUTES = [
    "list", 
    "headers",
    "form",
    "popovertarget"
]

def extract_id_reference_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str]
):
    edges: list[Edge] = []

    for attr in ID_ATRRIBUTES:
        for element in soup.find_all(attrs={attr:True}):
            if element not in element_to_id:
                continue

            attr_val = element.get(attr)
            if not attr_val:
                continue

            target_ids = attr_val if isinstance(attr_val, list) else attr_val.split()

            for target_id in target_ids:
                target_element = soup.find(id=target_id)
                if target_element and target_element in element_to_id:
                    edges.append((element_to_id[element], element_to_id[target_element], relation))

    for output in soup.find_all("output", attrs={"for": True}):
        if output not in element_to_id:
            continue

        for target_id in output["for"].split():
            target_element = soup.find(id=target_id)
            if target_element and target_element in element_to_id:
                edges.append((element_to_id[output], element_to_id[target_element], relation))

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") and len(href) > 1:
            target_id = href[1:]
            target_element = soup.find(id=target_id)
            if target_element and target_element in element_to_id:
                edges.append((element_to_id[a], element_to_id[target_element], relation))

    return edges
