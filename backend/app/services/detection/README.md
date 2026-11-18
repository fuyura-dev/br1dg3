# Detection scope and scan reports

The bundled engine is **Axe 4.10.3**. `RELEVANT_RULES` in
[`detect.py`](./detect.py) selects **39 supported rule IDs** for both repair
methods and primary effectiveness results. The removed `aria-tab-name` entry
did not exist in this engine, so removing it did not change actual coverage.

The engine runs its default enabled checks with `axe.run({})`; the allowlist
filters returned violations afterwards. Each rule's applicability depends on
the page. Nine selected rules are best practices; the others have WCAG tags.

## Selected rules

This inventory comes from the bundled engine's `axe.getRules()` metadata.
Tags are retained verbatim: `wcag2a` identifies WCAG 2.0 Level A, while
`wcag111` identifies success criterion 1.1.1.
See the [Axe API documentation](https://github.com/dequelabs/axe-core/blob/v4.10.3/doc/API.md#axe-core-tags).

| Rule ID | Check | Classification | WCAG tags |
| --- | --- | --- | --- |
| `aria-allowed-attr` | Elements must only use supported ARIA attributes | WCAG | `wcag2a`, `wcag412` |
| `aria-command-name` | ARIA commands must have an accessible name | WCAG | `wcag2a`, `wcag412` |
| `aria-hidden-focus` | ARIA hidden element must not be focusable or contain focusable elements | WCAG | `wcag2a`, `wcag412` |
| `aria-input-field-name` | ARIA input fields must have an accessible name | WCAG | `wcag2a`, `wcag412` |
| `aria-required-attr` | Required ARIA attributes must be provided | WCAG | `wcag2a`, `wcag412` |
| `aria-required-children` | Certain ARIA roles must contain particular children | WCAG | `wcag2a`, `wcag131` |
| `aria-required-parent` | Certain ARIA roles must be contained by particular parents | WCAG | `wcag2a`, `wcag131` |
| `aria-roles` | ARIA roles used must conform to valid values | WCAG | `wcag2a`, `wcag412` |
| `aria-toggle-field-name` | ARIA toggle fields must have an accessible name | WCAG | `wcag2a`, `wcag412` |
| `aria-valid-attr` | ARIA attributes must conform to valid names | WCAG | `wcag2a`, `wcag412` |
| `aria-valid-attr-value` | ARIA attributes must conform to valid values | WCAG | `wcag2a`, `wcag412` |
| `button-name` | Buttons must have discernible text | WCAG | `wcag2a`, `wcag412` |
| `document-title` | Documents must have &lt;title&gt; element to aid in navigation | WCAG | `wcag2a`, `wcag242` |
| `frame-title` | Frames must have an accessible name | WCAG | `wcag2a`, `wcag412` |
| `frame-title-unique` | Frames must have a unique title attribute | WCAG | `wcag2a`, `wcag412` |
| `html-has-lang` | &lt;html&gt; element must have a lang attribute | WCAG | `wcag2a`, `wcag311` |
| `html-lang-valid` | &lt;html&gt; element must have a valid value for the lang attribute | WCAG | `wcag2a`, `wcag311` |
| `image-alt` | Images must have alternative text | WCAG | `wcag2a`, `wcag111` |
| `input-button-name` | Input buttons must have discernible text | WCAG | `wcag2a`, `wcag412` |
| `input-image-alt` | Image buttons must have alternative text | WCAG | `wcag2a`, `wcag111`, `wcag412` |
| `label` | Form elements must have labels | WCAG | `wcag2a`, `wcag412` |
| `link-name` | Links must have discernible text | WCAG | `wcag2a`, `wcag244`, `wcag412` |
| `select-name` | Select element must have an accessible name | WCAG | `wcag2a`, `wcag412` |
| `nested-interactive` | Interactive controls must not be nested | WCAG | `wcag2a`, `wcag412` |
| `presentation-role-conflict` | Ensure elements marked as presentational are consistently ignored | Best practice | — |
| `scrollable-region-focusable` | Scrollable region must have keyboard access | WCAG | `wcag2a`, `wcag211`, `wcag213` |
| `bypass` | Page must have means to bypass repeated blocks | WCAG | `wcag2a`, `wcag241` |
| `skip-link` | The skip-link target should exist and be focusable | Best practice | — |
| `heading-order` | Heading levels should only increase by one | Best practice | — |
| `page-has-heading-one` | Page should contain a level-one heading | Best practice | — |
| `empty-heading` | Headings should not be empty | Best practice | — |
| `list` | &lt;ul&gt; and &lt;ol&gt; must only directly contain &lt;li&gt;, &lt;script&gt; or &lt;template&gt; elements | WCAG | `wcag2a`, `wcag131` |
| `listitem` | &lt;li&gt; elements must be contained in a &lt;ul&gt; or &lt;ol&gt; | WCAG | `wcag2a`, `wcag131` |
| `definition-list` | &lt;dl&gt; elements must only directly contain properly-ordered &lt;dt&gt; and &lt;dd&gt; groups, &lt;script&gt;, &lt;template&gt; or &lt;div&gt; elements | WCAG | `wcag2a`, `wcag131` |
| `dlitem` | &lt;dt&gt; and &lt;dd&gt; elements must be contained by a &lt;dl&gt; | WCAG | `wcag2a`, `wcag131` |
| `landmark-one-main` | Document should have one main landmark | Best practice | — |
| `landmark-main-is-top-level` | Main landmark should not be contained in another landmark | Best practice | — |
| `landmark-unique` | Landmarks should have a unique role or role/label/title (i.e. accessible name) combination | Best practice | — |
| `region` | All page content should be contained by landmarks | Best practice | — |

Run `node backend/tests/test_axe_rules.cjs` from the repository root to verify
the IDs, engine version, default enablement, and documented inventory. Freeze
the same rule list and engine version for both methods before collecting results.

## Scan results

`scan_with_report(html)` runs the existing scan once and returns a `ScanResult`:

- `violations`: independent copies of selected violations for repair and metrics.
- `report`: the complete report envelope described below.

`detect(html)` remains a compatibility wrapper returning only selected
violations, so graph construction and existing list-only callers keep that
interface. No additional rules, browser scans, or LLM calls are introduced.

| Report field | Meaning |
| --- | --- |
| `selected_rule_ids` | The configured primary rule list at scan time. |
| `prepared_html_sha256` | SHA-256 of the preprocessed HTML string submitted to browser loading, not the resulting browser DOM. |
| `removed_elements` | Preprocessing removes `script` and `style` elements. |
| `axe` | The unfiltered Axe result, including violations, passes, incomplete and inapplicable results, timestamp, engine version, and browser environment when supplied by Axe. |

The raw result is retained as returned; missing fields are not fabricated.
Repair-side annotations to selected violations cannot modify this evidence.

## Interpretation

- `violations`: confirmed failures; only selected rule IDs enter primary counts.
- `passes`: passed checks, retained for inspection.
- `incomplete`: results needing review, not confirmed passes or failures.
  They remain separate and do not automatically trigger repairs.
- `inapplicable`: checks with no matching content, not extra passed repairs.

The effectiveness flag `fully_fixed` means **no confirmed selected-rule
violations remain on the evaluated snapshot**, subject to the existing failure
policy. Excluded violations and incomplete results can still exist. This does
not change violation-count granularity or metric formulas.

The scan evaluates a prepared static snapshot after script/style removal.
Inline styles and linked assets do not guarantee the original rendering context.
Even the unfiltered report does not establish comprehensive accessibility,
visual/layout coverage, dynamic behavior, or live-page usability.

## API and record retention

- `/api/scan`: `scan_report`, alongside existing selected `issues`.
- `/api/repair`: `scan_reports.before` and `scan_reports.after` at the response
  level, not duplicated inside `metrics`. Cache hits reuse the original run's
  reports. With no selected violations, no repair or final scan occurs;
  `after` is null and the initial report remains available.
- `/api/evaluate`: the same before/after fields for scans actually performed.
  Caller-supplied violation lists must already use the selected-rule scope.
  Full reports are null for those lists; no evidence is invented and no
  additional scan is performed solely to obtain a report.
- A failed final scan has a null after-report. `/repair` still returns HTTP 503
  and saves the successful initial report in its existing failed-run JSON.
  New records use schema version 2; existing records are not rewritten.
  `/evaluate` retains any successful initial report alongside its existing
  no-credit effectiveness result.

For a generation fallback, `/repair` still performs its existing final scan of
the fallback. Its after-report describes that artifact, while
`metrics.evaluation.score_basis` identifies assigned no-candidate scores.
Standalone fallback evaluation skips the final scan as before.

Successful reports are available in responses and repair cache entries,
not automatically archived to disk. Save them with experimental results;
the complete experiment recorder remains separate work. Full reports increase
response and cache sizes, but add no browser scans or LLM calls.
