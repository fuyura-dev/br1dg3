# LLM Repair

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
not verify accessibility repair or introduce extra Axe scans, model retries or block editing. The
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
not a token limit or a cap on the complete prompt, related context, ordinary
targets, or baseline documents. If the minimum view still exceeds the cap, the
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
this root-wrapper fix. General block/subtree editing remains separate work.

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
Raw replies remain in `Step.llm.text`; `Step.candidate_html` holds the accepted,
cleaned document reply or target patch before assembly.

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
  unmapped-target count, and complete step records.
  Each available `llm` record preserves reply text, model, status, token fields,
  attempts, and latency as currently recorded. A missing LLM result remains null.

These are saved run artifacts, not validated repairs. Use `candidate_html`,
`generation_status`, and `fallback_used` to distinguish a candidate from fallback
HTML. Older records without these fields do not establish candidate availability.
Usage is preserved without recalculation, and existing usage-field limitations
still apply. Request/token/cost accounting corrections remain pending;
this recorder does not calculate a monetary cost or claim to retain the full
provider response.

Saving performs no repair generation, detection retry, or metric computation.
The API continues returning its existing HTTP 503 error and does not cache the
failed result. If storage fails, the backend logs that the record could not be
saved and preserves the original scan error. Normal write failures are cleaned
up before a final JSON file is published.

Successful repairs, cache hits, initial-scan failures, and requests outside this
`/api/repair` final-scan failure path do not create these records. This folder is
not a complete experiment logger.
