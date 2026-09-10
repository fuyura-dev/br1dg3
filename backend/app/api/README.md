# API Documentation


## 1. Scan Endpoint (`POST /api/scan`)
Scans HTML content for accessibility violations.

### Request Body
```json
{
  "html": "<html><body><img src='logo.png'><input id='search'></body></html>"
}
```

### Response Body
```json
{
  "total_issues": 1,
  "issues": [
    {
      "id": "image-alt",
      "impact": "critical",
      "tags": ["wcag2a", "wcag111"],
      "description": "Ensures <img> elements have alternate text",
      "help": "Images must have alternate text",
      "help_url": "https://dequeuniversity.com/rules/axe/4.10/image-alt",
      "html_target": "<img src='logo.png'>",
      "target": "header > img.logo"
    }
  ]
}
```

---

## 2. Repair Endpoint (`POST /api/repair`)
Repairs accessibility violations in the given HTML.

### Request Body
```json
{
  "html": "<html><body><img src='logo.png'></body></html>",
  "use_sdg": true
}
```

### Response Body
```json
{
  "fixed_html": "<html><body><img src='logo.png' alt='Company Logo'></body></html>",
  "issues_fixed": 1,
  "summary": "Added alt text to image"
}
```

---

## 3. Graph Endpoint (`POST /api/graph`)
Extracts the Semantic Dependency Graph (SDG) for visual rendering.

### Request Body
```json
{
  "html": "<html><body><form id='login-form'><label for='email'>Email</label><input id='email'></form></body></html>"
}
```

### Response Body
```json
{
  "nodes": [
    {
      "id": "n1",
      "tag": "form",
      "label": "<form id='login-form'>",
      "has_issue": false
    },
    {
      "id": "n2",
      "tag": "label",
      "label": "<label for='email'>",
      "has_issue": false
    },
    {
      "id": "n3",
      "tag": "input",
      "label": "<input id='email'>",
      "has_issue": true
    }
  ],
  "links": [
    {
      "source": "n1",
      "target": "n3",
      "relation": "parent_child"
    },
    {
      "source": "n2",
      "target": "n3",
      "relation": "label_input"
    }
  ]
}
```