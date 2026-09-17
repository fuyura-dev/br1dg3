from bs4 import BeautifulSoup, Tag

Edge = tuple[str, str, str]
relation = "form_group"

FORM_CONTROLS = ["input", "select", "textarea", "button"]


def extract_form_group_edges(
        soup: BeautifulSoup,
        element_to_id: dict[Tag, str]
):
    edges: list[Edge] = []

    for fieldset in soup.find_all("fieldset"):
        fieldset_id = element_to_id.get(fieldset)
        if not fieldset_id:
            continue

        legend = fieldset.find("legend")
        if legend and legend in element_to_id:
            edges.append((fieldset_id, element_to_id[legend], relation))

        for control in fieldset.find_all(FORM_CONTROLS):
            if control in element_to_id:
                edges.append((fieldset_id, element_to_id[control], relation))

    for form in soup.find_all("form"):
        form_id = element_to_id.get(form)
        if not form_id:
            continue

        for fieldset in form.find_all("fieldset"):
            if fieldset in element_to_id:
                edges.append((form_id, element_to_id[fieldset], relation))

        for control in form.find_all(FORM_CONTROLS):
            if control.find_parent("fieldset"):
                continue

            if control in element_to_id:
                edges.append((form_id, element_to_id[control], relation))

    radio_groups: dict[str, list[Tag]] = {}
    for radio in soup.find_all("input", attrs={"type": "radio"}):
        if radio.find_parent("fieldset"):
            continue

        name = radio.get("name")
        if name and radio in element_to_id:
            radio_groups.setdefault(name, []).append(radio)

    for name, radios in radio_groups.items():
        for i in range(len(radios) - 1):
            source_id = element_to_id[radios[i]]
            target_id = element_to_id[radios[i + 1]]
            edges.append((source_id, target_id, relation))

    return edges
