# LLM Repair

## Editable scope and SDG replies

Before each SDG generation, `scope.py` selects the current target or its
immediate-parent subtree. Parent expansion stops after one level and excludes
the document node, `html`, `head`, and `body`. An offered parent block must fit
both **3,000 characters and 30 elements**, including the root and tracking
attributes. An oversized parent falls back to the complete target. Ordinary
targets retain their separate **8,000-character / 80-element** input limits;
reducing parent expansion does not cause larger eligible targets to be skipped.
If the target itself is oversized, `prompt_too_large` records a failed step without a model
call; the document stays in the run and later targets continue. No ordinary
markup is truncated. HTML/body targets retain the dedicated shortened root path
below, with target-only replies and its existing 8,000-character view limit.

When a block is available, the prompt shows a target locator and the complete
block once. Related SDG elements inside the scope are identified as editable;
those outside it remain read-only. Only the current target's requested rules
drive the repair, even when surrounding markup can change. Scope selection uses
the current DOM, not source line ranges or a union of disconnected graph nodes.

SDG output must be exactly one JSON object with two fields:

```json
{"scope":"target","html":"<input id=\"email\" aria-label=\"Email\">"}
```

Use `target` when only that replacement slot changes; existing support for new
wrappers/siblings around the target remains. Use `block` to return the complete
single-root parent subtree when changing existing surrounding elements. The
backend chooses the replacement slot: the model supplies no selector and cannot
expand the scope. A target-only prompt rejects `block` replies. Bare HTML,
prose, code fences, duplicate/extra JSON fields and unknown scope values are
rejected as `invalid_reply`; scope is never guessed. The baseline still requests
and parses plain full-document HTML.

Completed replies are not rejected solely for their character count, element
count or JSON-envelope length. A larger replacement can still pass the format,
scope and tracking checks below. Available generation usage and the evaluated
document's structural changes remain experimental outcomes to analyze; size
alone is not a patch failure. Removing these acceptance caps does not remove
provider limits or accept incomplete generations, and adds no generation-token cap.

Input limits are configured as `BLOCK_*` and `TARGET_*` in `scope.py` (shortened
root views in `root_view.py`). They are not provider-token, full-prompt or
document-wide budgets: instructions and related context add input, and each
scheduled generation has its own scope. The 3,000/30 parent setting is the agreed
starting configuration, not a benchmark-optimized value. Freeze the settings
before experiments. Absolute bounds do not restrict the percentage of a small
page that its parent block may contain.

Application is atomic: a rejected reply leaves the current HTML intact. Block
replacement validates all tracking markers in the chosen subtree, including
already-processed parents and pending siblings, using the existing unique-ID
recovery rules. It rejects foreign/lost/duplicate/conflicting tracking, additional
copies of IDs owned outside the selected scope, multiple block roots, unexpected
document shells, and prose/comments outside the replacement. Ordinary scopes
also retain script/style stash-comment counts and reject newly introduced
standalone `…` placeholders. Root references continue through the root assembler.
Accepted ordinary replacements apply returned content and attributes directly.

These guards enforce the selected parsed-HTML slot and tracked identity. They
do not prove that all untracked content, semantics, styling or behavior within
the editable area was preserved. In particular, blocks can overlap: a later
target may edit a previously repaired parent or sibling. The initial schedule
is unchanged, current context is rebuilt, and there is no automatic revisit or
per-patch Axe scan. Final metrics still determine the measured outcome. The
larger editable area may improve some repairs or introduce regressions; the
hybrid response saves repeated block output only when target mode is chosen,
and does not guarantee lower total token usage.

Step records include `edit_scope` (allowed modes, selected current root, sizes,
selected input limits, parent-expansion limits and selection reason),
`reply_scope`, and decoded `reply_html`. The reply-limit fields are null because
there is no size-only output rejection. The raw
JSON remains in `llm.text`/API `raw_reply`; `candidate_html` is decoded accepted
HTML, never the JSON envelope. Malformed envelopes and rejected patches retain
available usage and continue the schedule. Saved final-scan failure records
include the same fields. The frontend previews HTML and labels target/block
repairs and rejected replies separately.

Run `python -m unittest tests.test_repair_scope` for controlled selection,
envelope, scope-boundary, tracking, asset-restoration and continuation tests.

## Generation attempts and reported usage

Each step records whether generation was entered. `api_calls` now counts logical
generations attempted, including failures; a cascade skip or oversized input
does not count. `requests` counts calls made by the application's retry loop to
`client.interactions.create()`, including exhausted failures. Current clients
disable the SDK's internal retries; older records may have omitted those hidden
attempts. These remain **application attempts, not proof of billable generations**;
`request_count_basis` keeps the same meaning for current and historical records.
The shared retry policy is specified below.

`LLMResult.attempt_records` retains each observed attempt's number, status,
duration, error and available raw usage. An exhausted/non-retryable exception
still produces the existing `llm_error` step, now with its recorded result.
`latency_s` measures the last application attempt; `elapsed_s` measures the whole
generation including application backoff delays, not the document's scan and
repair duration. The API returns these records under each step's `llm`, and
final-scan failure artifacts retain them too.

Provider token fields remain separate: input, output, thought and provider total.
`raw_usage` preserves supplied fields, including cached/tool token breakdowns when
present. Missing or malformed counts become null; a reported zero remains zero.
The provider total is never replaced with a component sum. No billing overlap
or inclusion rule is inferred from these names.

At document level, a token field is null if any observed application attempt
lacks that field. `reported_usage` retains the sum of known values separately,
and `usage_complete` gives coverage for each field. For example, a failed attempt
without usage followed by a reply reporting 100 tokens yields `total_tokens:
null`, `reported_usage.total_tokens: 100`, and incomplete total-token coverage.
Coverage describes the observed application attempts, not hidden SDK retries or
proof of complete billing. `known_requests` retains a request subtotal when an
unexpected exception leaves the attempt count unknown; `requests` is then null
and `request_count_complete` false. No generation means known zero usage.
Legacy records with only final-response usage and multiple attempts retain that
reported usage, but do not establish coverage of the earlier attempts.

The frontend displays unavailable totals as N/A and partial subtotals as partial.
The existing display price constants/formula are unchanged; its cost estimate is
null if a required usage component is unknown. Experimental monetary cost will
be calculated externally in Excel using the researcher's documented prices.
The future document-level export must exclude computed monetary cost; that
export is separate work and is not implemented by this change.

### Completed-response measurement

Evaluation adds `efficiency.completed_response_count` and
`efficiency.completed_response_usage` for the experiment's completed-response
scope. The original `api_calls`, `requests`, all-attempt token summaries, display
cost and raw attempt records keep their existing meanings.

`summarize_completed_usage()` counts recorded responses whose status is
`completed`, including empty, rejected or ineffective replies. Patch acceptance
and accessibility improvement do not determine inclusion. Recorded errors and
other recognized non-completed statuses are excluded, even if they report usage.
Only the included responses supply input, output, thought and provider-total
token sums; provider totals are not reconstructed from components. No cost or
rate is calculated in this additional summary.

`completed_response_usage` includes `basis: completed_responses`, the four token
fields, `reported_usage` subtotals, per-field `usage_complete`,
`total_tokens_source: provider_reported`, `known_completed_responses`, and
`count_complete`. Missing usage on an included response makes that token total
null while retaining known subtotals. Missing/unrecognized completion status or
an incomplete attempt history makes the completed count and token totals null;
known completed responses and their reported subtotals remain available. A
legacy final-response record establishes a complete count only when it records
exactly one attempt and a recognized status. No completion is inferred from an
`applied` patch or legacy `ok` flag.

An error without usage followed by one completed response reporting 100 tokens
therefore yields completed count 1 and completed-response total 100; the existing
all-attempt total remains null. With a known history containing no completed
responses, the new count and tokens are zero **within this scope**, not proof of
zero resources consumed or zero billed cost. Standalone evaluation without
completion evidence leaves both new fields null. Replaying the complete
efficiency result through `efficiency_data` preserves the new fields.

The planned export will use these measurements and retain failure/missingness
indicators. Failed documents stay in the experiment. External spreadsheet cost
must be labeled as an estimate for completed responses; it does not establish
total expenditure.

The agreed token policy retains input, output, thought and provider-total fields
for completed responses. Use the provider-reported total for total-token
measurements; a reported thought count of zero contributes nothing, while a
missing thought count stays unknown. The shared `minimal` setting does not
guarantee zero thinking: Google describes it as near-off for most queries on the
configured model. In the Interactions API, output and thought counts are separate;
response pricing uses their sum. See Google's [thinking-level definitions](https://aistudio.google.com/docs/thinking#understanding-thinking-levels)
and [pricing explanation](https://aistudio.google.com/docs/thinking#pricing).
For the manuscript/spreadsheet, the agreed output-token quantity `C_i` combines
reply tokens and thought tokens from completed responses. Raw `completion_tokens`
continues to mean only the API's `total_output_tokens`; `thought_tokens` stays
separate. Combine these in Sheets only when both counts are available, and check
input plus combined output against the saved provider total. Investigate a
mismatch rather than overwriting the provider value or treating missing counts
as zero. This definition can preserve the manuscript's `TT = Σ(P_i + C_i)` formula.
The experiment's price schedule and any cached-input treatment still need to be
recorded when finalizing the spreadsheet; this policy does not change app prices.

Run `python -m unittest tests.test_usage_recording tests.test_efficiency` for
controlled retry, missing-data, raw usage, evaluator and saved-record tests.

## Shared controls and configuration snapshots

`controls.py` defines the same generation and retry settings for both methods:
minimal thinking, up to four application attempts (initial plus three retries),
with 1/2/4-second delays for the selected transient statuses and exception types.
Completed replies are never regenerated because they are malformed, rejected or
unsuccessful at repairing accessibility. Transport failure retries resend the
same request. A timeout cannot prove the provider did no work, so request counts
still do not establish billing or exactly-once remote execution.

SDK-internal retries are disabled through the pinned google-genai 2.24.0
Interactions resource's `sdk_configuration.retry_config = None`. Its generic
`HttpRetryOptions(attempts=0)` is normalized and still causes an extra Interactions
attempt, as reproduced by local transport tests. The SDK-specific control is
tested with actual SDK calls through `httpx.MockTransport`; rerun these tests on
an SDK upgrade. Removing the hidden retry layer reduces the previous maximum
retry effort and may affect completion rates during service outages. SDK-wrapped
timeout/connection exceptions are recognized by the application loop.

Temperature, top-p, seed and maximum-output tokens remain unspecified. The
snapshot explicitly records that these use provider defaults whose effective
values are not asserted. No new output cap, temperature setting or repeat-run
policy is introduced. Neither the requested model name nor a fixed local hash
guarantees immutable provider behavior or deterministic output.

Each runner captures `configuration`: UTC capture time, method, hashes of its
input and prepared input, and a shared `configuration_id`. The ID hashes the
local controls, requested model, installed package/Python versions, selected
rules, both system prompts, scope limits, source files, requirements and bundled
Axe asset. Method, document, timestamp and actual API cache setting are recorded
outside that shared ID so the two arms can be compared against the same settings.
The API exposes this snapshot; saved final-scan failures retain it. Cached API
responses retain their original snapshot/time. The no-issues API shortcut makes
no repair run and returns no configuration snapshot; direct empty runners do.
Manual/historical `RepairRun` objects can have null configuration.

Each generated step's `llm.request` separately records the exact application
payload (model, system/user prompt, explicit generation settings and `store`),
timestamp and request hash, including on terminal request failure. It is not a
wire-level packet capture. `response_model` records only a model string actually
returned by the provider; it can be null or an alias. API credentials, transport
headers and `.env` contents are not included. Exact prompts include document
content, so responses/failure records are larger than before.

From `backend/`, capture and check the current local setup without model/browser calls:

```bash
python -m scripts.snapshot_config --output /tmp/br1dg3-config.json
python -m scripts.snapshot_config --check /tmp/br1dg3-config.json
```

Capture creates a new file and refuses to overwrite it. Check exits unsuccessfully
if the file was modified without updating its ID or if local configuration/code
differs. This detects accidental drift, not deliberate tampering. For final
experiments, retain the snapshot with the dataset/run artifacts, use cache bypass,
and compare each run's ID. The check is explicit, not an automatic batch/API gate;
the experiment runner/export remains separate work. Source fingerprints describe
files at capture time: restart the backend after edits before capturing/running.
Hashes detect drift but do not archive source; retain the matching source version.

The final protocol freeze still follows the remaining measurement, dataset and
analysis decisions. Browser details are supplied by actual scan reports, and
dataset membership, analysis choices and external Excel prices are not covered
by this local configuration ID. This tooling does not itself freeze the entire
experiment or complete its export pipeline.

Run `python -m unittest tests.test_generation_controls` for snapshot identity,
drift detection, exact request retention and real-SDK mocked-transport checks.

## Repair ordering

`run_sdg()` computes one schedule from the prepared original document. Only
elements with mapped selected-rule violations are scheduled. Before each step,
the current HTML is parsed again and its SDG/context is rebuilt; the target
schedule is not recomputed after patches.

[`dependency_view()`](./order.py) constructs a separate scheduling graph.
Reference edges are oriented from the referenced provider to its dependent,
while existing label, heading, landmark, form and structural dependency
directions are retained. Every direct DOM parent-child relationship is added
to this view, including ordinary wrappers, so containment paths connect
ancestors to descendants. These additions do not modify the base SDG, prompt
context extraction, or semantic-metric definitions. Context-only anchors,
focus-order edges and same-name sequences are not added as prerequisites.

Mutually reachable nodes are grouped into strongly connected components.
Dependencies between groups determine their order. If several target groups
are ready, the group whose earliest affected element comes first in the
original document is selected. Within a cycle, affected elements follow
document order because no sequence can satisfy all circular dependencies.
Paths through unaffected elements still impose dependencies between targets;
those unaffected elements are not scheduled for repair. The original node
insertion order supplied by `SDGBuilder` provides the document-order key.

For example, if a container references a description and encloses an image,
and all three need repair, the schedule is description → container → image.
The scheduling change can affect later patches, cascade skips and actual call
counts. It does not establish that a skipped target has been verified as fixed.
The baseline retains its single full-document generation without this schedule.
The prompt demonstration uses the same scheduling view as the runner.

Run `python -m unittest tests.test_repair_order` from `backend/` to check
containment, reference directions, paths through unaffected nodes, cycle
handling, stable ties, graph isolation and runner integration. Generation is
mocked; these checks do not measure repair effectiveness on the benchmark.

## Local cascade skips

The runner may omit a scheduled rule only after an earlier patch was accepted
and a supported local condition is present in the current HTML but was absent
in the prepared original. It never skips the first target merely because a
local predicate disagrees with the initial scan. A failed/rejected patch does
not change the HTML used by these checks; an unchanged condition cannot justify
a skip. Conditions are checked again when the target is reached, so an earlier
temporary improvement is insufficient if a later patch removed it.

The supported conditions are deliberately narrower than Axe:

| Rule | Supported current condition |
| --- | --- |
| `region` | Target is in a native `main`, `nav`, `aside`, or `search` landmark without an explicit overriding role, or an element with the single role `main`, `navigation`, `complementary`, `search`, `banner`, or `contentinfo`. Hidden/inert/ARIA-hidden ancestry does not justify this skip. |
| `listitem` | An unroled `li` has a direct `ul`, `ol`, or `menu` parent whose role is absent or `list`. Arbitrary intervening ancestors do not qualify. |
| `dlitem` | An unroled `dt`/`dd` has a `dl` parent, directly or through one unroled `div` group. The `dl` role must be absent or `list`. |
| `aria-hidden-focus` | The original ARIA hiding condition is gone: target and ancestors have no `aria-hidden` attribute or the value `false`. The check does not infer focusability from CSS, `tabindex`, disabled controls, or event handlers. |

Named landmarks, contextual native header/footer landmarks, fallback role lists,
and unsupported cases remain scheduled. The SDG's broader landmark extractor
still supplies context; its graph edges are not used as proof of rule validity.
These checks operate on the parsed snapshot, not the rendered/composed browser
DOM. They are **local inferences, not rule-equivalent Axe checks**. Reference
material includes the pinned [Axe description-list check](https://github.com/dequelabs/axe-core/blob/v4.10.3/lib/checks/lists/dlitem-evaluate.js),
and Deque's [landmark](https://dequeuniversity.com/rules/axe/4.10/region) and
[ARIA hiding](https://dequeuniversity.com/rules/axe/4.10/aria-hidden-focus) guidance.

Each step retains its original `rules`. `skipped_rules` records the rule ID,
reason, `basis: changed_from_original`, and `verification: local_dom_only`.
`requested_rules` records rules passed to `generate()`, even if generation
raises; it is empty when no generation was attempted. When only some rules
qualify for skipping, the actual target prompt contains the remaining rules,
without altering the original issue table. The skip evidence describes the
pre-attempt state, not verification of the subsequent output.

A fully skipped target emits `cascade_skipped` and makes no model call. It is
neither a generated patch nor a failed generation. The legacy status
`cascade_resolved` remains readable for historical records, without upgrading
those old inferences to verified results. The API, saved scan-failure records,
dashboard and terminal retain this distinction. `cascaded_count` and
`cascade_rate` keep their existing field names: they count whole targets skipped
and their percentage among scheduled target elements. Partial rule suppression
does not count as a whole-target skip. Neither value measures violations fixed
or percentage cost savings. Final scan results remain the accessibility evidence.

No per-patch scans, extra repair retries, graph-definition changes or schedule
changes are introduced. The narrower policy may increase LLM usage; benchmark
improvements are not assumed. Run `python -m unittest tests.test_repair_cascade`
for controlled condition, transition, prompt-filtering, reporting and continuation
tests. Browser-level equivalence is not claimed.

## Tracking checks before patch application

`apply_reply()` checks the target and all tracked descendants before changing
the current document. Every expected marker must occur exactly once. Duplicate
markers, markers imported from outside the target, and unexpected markers reject
the patch. When a tracked element originally has a unique HTML `id`, the assembled
candidate must keep that ID on its marker owner, once; missing, duplicated or
reassigned IDs reject the patch as conflicting identity.

A missing descendant marker can be recovered only through an unchanged, nonempty
HTML `id` that is unique in the original **whole document** and the candidate.
The matching candidate element must not already carry another marker. No recovery
is inferred from descendant position, tag name or similar text. For an ID-less
target itself, a sole same-tag replacement root may retain the target's marker;
this exception does not apply to descendants. With no unique ID, preserved markers
are the identity anchor, not proof that all content or semantics were preserved.

Root `<html>`/`<body>` replies contain collapsed placeholders. The existing
reconciler expands these on a copy of the target, and tracking is checked on that
assembled result before insertion. A shortened reply need not repeat markers on
unchanged content restored from the original tree. Explicit duplicate or foreign
markers in the reply are still rejected before reconstruction.

Failure returns `tracking_rejected` with warning details, keeps the current HTML,
and continues the fixed schedule. The rejected step counts as failed, retains its
raw model reply and available usage, and has no accepted `candidate_html`. A run
with other accepted steps is partial; an all-rejected run has no candidate. The
frontend displays the rejected step as failed. Recovery is recorded as
`marker_recovered:<token>`; rejection reasons include `marker_lost`,
`marker_duplicate`, `marker_unexpected` and `marker_identity_changed`.

These are conservative tracking checks: they can reject a repair that removes or
changes a tracked element, even if that repair might otherwise be useful. They do
not verify accessibility repair or introduce extra Axe scans or model retries. The
zero-shot document parser does not use this SDG marker policy.

Run `python -m unittest tests.test_repair_tracking` from `backend/` for recovery,
ambiguity, root reconstruction rollback, child continuation and failure reporting.

## Attributes in shortened root replies

For an explicitly returned `<html>` or `<body>` tag, the patcher removes original
attributes that were shown in the shortened prompt but are absent from that tag
in the reply. Added attributes and changed values are still applied. The prompt
instructs the model to retain unchanged shown attributes and explicitly return
the corresponding root tag when changing its attributes.

The prompt and patcher share the same visibility rule: `class`, `style` and
`data-*` are hidden in shortened markup. Omission preserves these attributes;
explicit additions/updates still apply, except that internal tracking markers
are preserved by the patcher. Existing tracking checks reject conflicting IDs
or markers before publishing the candidate.

Each root is handled independently. A body-only reply keeps the HTML element's
attributes; an HTML reply without a body keeps the body's attributes. A reply
containing only a wrapper such as `<main>` does not request root-attribute removal.
This policy applies to HTML/body roots. Other matched descendants in shortened
replies merge returned attribute values and retain omitted attributes.

Run `python -m unittest tests.test_root_attributes` from `backend/` for attribute
removal, additions/updates, prompt round trips, tracking rollback, and child-context
refresh after an accepted body repair. Model replies are controlled fixtures.

## Content and document titles in root replies

The shallow root view shows short direct text. Text longer than 160 serialized
characters, comments, and hidden elements use `<!--__BR1DG3_CONTENT_...__-->`
references to original parsed nodes. Copying a reference retains that occurrence
without requiring the model to reproduce its contents. References are expanded
before publishing the candidate; they are not added to the final document.
Long leaf text at the depth limit collapses fully to `…`, rather than a shortened
prefix that could be mistaken for replacement text.

`ROOT_MARKUP_CHAR_LIMIT` and `ROOT_LITERAL_CHAR_LIMIT` in `root_view.py` configure
the limits. Root **target markup** is capped at 8,000 characters; the renderer
reduces expansion depth to fit, retaining shown HTML/body attributes. This is
not a token limit or a cap on the complete prompt, related context, or baseline
documents. Ordinary scopes have their separate limits above. If the minimum view still exceeds the cap, the
runner records `prompt_too_large` without a model call, retains current HTML, and
continues the schedule. The document remains in the run; the step counts as a
failure. Freeze these settings before experiments; they are engineering defaults,
not empirically optimal thresholds.

Related read-only snippets retain their existing length limit. Shared
preprocessing and repair serialization escape literal markup characters, so
text such as `&lt;button&gt;` remains text after another parse. This correction
applies to both repair methods and does not change script/style removal.

Container reconstruction processes text, comments and element tags. A new
collapsed wrapper carries remaining original content in order. Explicitly echoed
text/comments consume original occurrences individually, retaining the original
whitespace without duplicating the text. References can stay in their original
container or move inside a new wrapper around that content. Moving them into a
different existing container is rejected. References also retain asset-stash
comments without exposing their full contents.

Omitted content stays in its **original parent** where surviving neighbours
define a clear position. For example, wrapping a div while omitting adjacent
text leaves that text outside the wrapper. Omitted content between two children
moved into the same new wrapper has no clear position in the original parent,
so the patch is rejected. Explicitly echoed/referenced content, or a whole-content
`…` wrapper, can include that content in the wrapper. If old direct text is
omitted while unmatched new text is supplied, the patch is rejected rather than
appending both versions. Adding a heading therefore requires retaining existing
text explicitly, by reference, or through a whole-content placeholder.

Explicit element order in a reply is respected. These checks do not prove that
arbitrary DOM moves or semantic changes are correct: ambiguous ID-less
placeholders still use same-tag/document-order matching, other matched-descendant
attribute omissions still merge, and ordinary matched leaf-text edits are outside
this root-wrapper fix. The ordinary block path above uses complete markup and
direct replacement rather than this shortened-root reconstructor.

For an HTML target with `document-title`, the root markup shows existing titles
(using references for long text), and the prompt requests one title inside a head.
An unchanged reference can preserve a long title. Other head
content remains hidden/read-only. Within an explicit HTML reply, a title inside
the head replaces the existing title's text in place, with or without an ID;
missing titles and heads are inserted.
Unrelated head elements, attributes and comments are preserved. An omitted or
collapsed head/title retains the original. This handles title repair, not arbitrary
head editing.

Multiple returned titles, or an explicit title replacement when several originals
exist, return `patch_rejected` with `multiple_reply_titles` or
`ambiguous_existing_titles`. The same `patch_rejected` status covers detected
reconstruction ambiguity, with warnings `ambiguous_text_rewrite`,
`ambiguous_content_placement`, `unknown_content_reference`,
`duplicate_content_reference`, or `content_reference_scope`.
The current HTML is retained; the step counts as failed, keeps its raw
reply/available usage, and later scheduled targets continue.
The frontend shows the rejection as failed. Tracking checks still run before
publishing an assembled candidate. No extra scans or retries are performed.

Run `python -m unittest tests.test_root_content` from `backend/` for mixed content,
wrapper expansion, content references, size limits, asset-comment order, entity
round trips, title insertion/update, ambiguity rollback and runner continuation.
These tests use controlled replies and do not establish benchmark improvements.
The bounded root view and reconstruction/acceptance rules are part of the SDG
method; comparisons with whole-document zero-shot repair measure the complete
methods, not the isolated effect of semantic context.

## Candidates and fallback output

`RepairRun.fixed_html` remains the document returned by the repair pipeline.
`candidate_html` is the accepted assembled document, or null when no reply/patch
was accepted. Acceptance uses the existing reply parser and patch acceptance
rules; it does not establish HTML conformance or successful accessibility repair.
Raw replies remain in `Step.llm.text`; SDG replies are JSON envelopes.
`Step.candidate_html` holds the decoded accepted target/block HTML or cleaned
baseline document reply before assembly.

Run status is determined from accepted steps, not HTML equality:

- `accepted`: at least one accepted step, with no failed steps or unmapped targets.
- `partial`: an accepted assembled candidate plus failed steps or unmapped targets.
- `no_candidate`: repair was needed, but no step produced an accepted candidate.
  This includes all-rejected, all-unmapped, and all-skipped runs. `fallback_used`
  is true; the existing fallback output remains available to callers.
- `not_needed`: no violations required repair. No model output is claimed and
  this is not a generation failure.

`cascade_skipped` (historically `cascade_resolved`) and `element_gone` are skips,
not failed generation steps.
They alone do not create a candidate. An accepted reply identical to its input
does create a candidate and remains eligible for evaluation. Partial candidates
retain their assembled output and every step's status; one failed step does not
discard earlier accepted patches. These statuses do not verify cascade claims
or imply that all accessibility issues were repaired.

The evaluator assigns explicit no-credit scores to `no_candidate` runs instead
of measuring the fallback as generated output. Available usage is retained. See
[the failure-scoring policy](../validation/README.md#candidate-and-fallback-scoring).
For reporting, count `no_candidate` runs separately from individual failed steps
and partial runs; the complete experiment logger and aggregate failure rates
are not implemented yet.

## Failed final-scan records

When a `/api/repair` run reaches the final accessibility scan and that scan fails,
`failed_runs.py` saves one JSON record in `backend/data/failed_runs/`. The folder
is created on the first saved failure and is ignored by Git. Its path is resolved
from the backend source location, independently of the working directory.

Each file is named `<record-id>.json`. The backend log reports that ID only after
the complete JSON file has been written. The record contains:

- Schema version, record ID, UTC recording time, repair method, and failure stage.
- `original_html`: the submitted HTML, including its original scripts and styles.
- `evaluation_original_html`: the original prepared for evaluation, with scripts
  and styles stashed as placeholders by the repair API.
- The selected-rule `violations_before`, and `violations_after: null` because the
  final scan did not supply a measurement.
- `scan_reports.before`: the complete initial scan report, including unselected
  violations and review items. `scan_reports.after` is null because the final
  scan failed. These fields are available in schema version 2; old records are
  not rewritten. Direct callers that have only violation lists leave reports null.
- The scan error's type and message.
- `repair_run`: output and candidate HTML, generation/fallback status,
  unmapped-target count, configuration snapshot, and complete step records.
  Each available `llm` record preserves reply text, model, status, token fields,
  raw usage, per-attempt records, generation timing and exact request evidence.
  Request failures retain
  their collected attempt evidence; a failure without a recorded result remains null.

These are saved run artifacts, not validated repairs. Use `candidate_html`,
`generation_status`, and `fallback_used` to distinguish a candidate from fallback
HTML. Older records without these fields do not establish candidate availability.
Usage is preserved without recalculation under the coverage rules above.
Current clients disable SDK-internal retries; historical records may omit them.
Application attempts and usage do not establish billing. This recorder does not calculate a monetary cost or claim to retain
the full provider response.

Saving performs no repair generation, detection retry, or metric computation.
The API continues returning its existing HTTP 503 error and does not cache the
failed result. If storage fails, the backend logs that the record could not be
saved and preserves the original scan error. Normal write failures are cleaned
up before a final JSON file is published.

Successful repairs, cache hits, initial-scan failures, and requests outside this
`/api/repair` final-scan failure path do not create these records. This folder is
not a complete experiment logger.
