# API Documentation

> [!NOTE]
> For the updated request and response schemas, refer to the interactive API documentation when the backend is running:
> - **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
> - **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
> docs below are not updated

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
  "use_sdg": true,
  "use_cache": true
}
```

`use_cache` defaults to `true`, so existing frontend and extension requests reuse
completed repair responses for up to five minutes. Cache entries are separated by the input HTML and `use_sdg`.

For experimental runs, send `"use_cache": false` for both repair methods. This
bypasses cache reads and writes: it neither reuses nor replaces a stored response.
Requests with no detected issues return without running a repair and are not cached.

### Response Body
```json
{
  "fixed_html": "<html><body><img src='logo.png' alt='Company Logo'></body></html>",
  "issues_before": 1,
  "issues_after": 0,
  "issues_fixed": 1,
  "summary": "Added alt text to image",
  "cache_hit": false
}
```

`cache_hit` is `true` only when a stored response is reused. Its summary, metrics,
and steps describe the original repair run, not new LLM usage for the current request.

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