from bs4 import BeautifulSoup, Tag

Edge = tuple[str, str, str]
relation = "form_group"
name_relation = "name_group"

FORM_CONTROLS = ["input", "select", "textarea", "button"]

GROUPED_TYPES = {"radio", "checkbox"}


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

    # controls that share a name form a chain, per form and per type
    name_groups: dict[tuple, list[Tag]] = {}
    for control in soup.find_all("input", attrs={"type": lambda t: t and t.lower() in GROUPED_TYPES}):
        name = control.get("name")
        if name and control in element_to_id:
            container = control.find_parent(["fieldset", "form"] if control["type"].lower() == "checkbox" else "form")
            key = (id(container), control["type"].lower(), name.strip())
            name_groups.setdefault(key, []).append(control)

    for controls in name_groups.values():
        for i in range(len(controls) - 1):
            source_id = element_to_id[controls[i]]
            target_id = element_to_id[controls[i + 1]]
            edges.append((source_id, target_id, name_relation))

    return edges
