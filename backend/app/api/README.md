# API Documentation

> [!NOTE]
> For the updated request and response schemas, refer to the interactive API documentation when the backend is running:
> - **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
> - **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
> Examples below show selected fields; use the interactive schemas for complete responses.

## 1. Scan Endpoint (`POST /api/scan`)
Scans prepared HTML for accessibility violations. The existing `total_issues`
and `issues` fields cover the 39 selected rules shared by both repair methods.
The [detection documentation](../services/detection/README.md) lists each rule,
its WCAG/best-practice classification, and the snapshot's limitations.

A failed scan returns HTTP 503. Axe errors and missing or malformed scan results
are failures, not successful scans with zero violations.

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

Successful `/scan` responses also include `scan_report`. It retains the complete
result of the same Axe run, including unselected violations, passes, incomplete
(needs-review) and inapplicable results, plus the engine/browser information
provided by Axe. The envelope records `selected_rule_ids`,
`prepared_html_sha256`, `removed_elements`, and the unfiltered `axe` result.
The hash identifies the preprocessed HTML input, not the resulting browser DOM.
No second scan is performed.

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

Responses include `scan_reports.before` and `scan_reports.after`, using the same
report envelope as `/scan`. They are at the response level, not duplicated inside
`metrics`. Cache hits return the original run's reports. When no selected-rule
violations are found, the initial report is retained, `after` is null, and no
repair or final scan runs. Excluded violations and review items may still exist.
`fully_fixed` means zero confirmed selected-rule violations on the evaluated
snapshot, subject to the existing failure policy; it does not establish complete
accessibility. Report retention changes neither the selected repair inputs nor
the primary metric formulas.

For a generation fallback, the after-report describes the fallback actually
scanned. The metrics remain labeled no-candidate policy scores. Successful
reports are returned and cached, not automatically archived to disk. Full
reports increase response/cache sizes but require no extra browser or LLM calls.

Responses also include `candidate_html` (the accepted assembled HTML before
script/style restoration, or null) and `generation` with `status`,
`candidate_available`, `fallback_used`, `failed_steps`, and `unmapped`.
Statuses are `accepted`, `partial`, `no_candidate`, and `not_needed`;
acceptance is not a guarantee of conformance or accessibility success.
`fixed_html` remains the restored user output. Each step adds untrimmed
`raw_reply` and accepted `candidate_html`; the older `repaired_html` field
continues to contain trimmed model reply text, including rejected replies.

When no candidate was accepted, metrics explicitly assign no repair credit and
set `metrics.evaluation.score_basis` to `no_candidate_failure_policy`.
Available usage remains recorded. Top-level `issues_after` still describes the
scan of returned runner HTML; the metric after-count is the policy assignment.
Normal caching preserves these statuses and scores. See the
[candidate/fallback rules](../services/repair/README.md#candidates-and-fallback-output)
and [metric fields](../services/validation/README.md#candidate-and-fallback-scoring).

A failed initial or final scan returns HTTP 503 and does not cache a successful
repair response. When the final scan fails, the backend saves a local JSON record
under `backend/data/failed_runs/` and logs its record ID. The HTTP status and error
detail stay the same. If saving fails, the backend logs that storage error and
still returns the original scan error. See [failed-run records](../services/repair/README.md#failed-final-scan-records)
for the saved fields and scope.

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

---

## 4. Evaluation Endpoint (`POST /api/evaluate`)

Evaluates existing original and repaired HTML without generating another repair.

```json
{
  "html_original": "<html><body><img src='logo.png'></body></html>",
  "html_repaired": "<html><body><img src='logo.png' alt='Company Logo'></body></html>",
  "run_detection_if_missing": true
}
```

Omitted scan results are detected automatically by default. To use saved results,
provide `violations_before` and `violations_after` as Axe violation lists. An
explicit empty list means a successful scan found no selected-rule violations;
an omitted or null value means the result is unavailable.

- If the initial scan fails, evaluation returns HTTP 503; it does not invent a
  starting count of zero.
- If `run_detection_if_missing` is `false`, `violations_before` is required.
  Omitting it or sending null returns HTTP 422. An explicit empty list is allowed.
- With a valid starting scan, a failed final scan (or an unavailable final result
  when detection is disabled) keeps the existing no-credit effectiveness result:
  `scan_failed: true`, `violations_after` equal to `violations_before`, zero
  reduction, and both `compliance_improved` and `fully_fixed` false. This after
  count is a policy assignment, not an observed measurement. The other metrics
  are still evaluated independently.

For saved runs with no accepted candidate, also send `"fallback_used": true`.
It defaults to false, meaning the supplied HTML is the artifact to evaluate.
The flag applies the no-candidate policy above and skips detecting the fallback
as generated output. A valid initial scan is still required. When replaying an
accepted or partial run, pass its prepared `candidate_html` as `html_repaired`.
Identical original/repaired HTML alone never implies generation failure.

Successful evaluation returns `effectiveness`, `safety`, `structure`, `efficiency`,
`semantic`, `evaluation` (artifact, score basis, and fallback flag), and
`scan_reports` with `before`/`after` entries for scans it actually performed.
Caller-supplied violation lists must already use the selected-rule scope. Their
full reports remain null: the API does not reconstruct them from filtered lists
or rescan solely to obtain a report. A failed or skipped final scan also has a
null report. Any successful initial report remains available when the final
scan fails and effectiveness receives no credit.
Safety uses html5lib 1.1 parsing errors. Its response includes parser/version,
document or fragment mode, error count, and error messages with line/column
positions. Document markup in either original or repaired HTML selects document
mode (including the doctype check); other inputs use a `div` fragment context.
An unexpected checker failure sets safety `score` and `is_valid` to null with
`reason: "validator_error"`; retry that measurement. Other metrics remain
available. The checker does not rewrite the repair output or control repair
acceptance. See the [validation rules and limitations](../services/validation/README.md#syntactic-validity).
Unlike `/api/evaluate`, `/api/repair` still returns HTTP 503 when
its final scan fails, as described above.
