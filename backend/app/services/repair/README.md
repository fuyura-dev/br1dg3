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

`cascade_resolved` and `element_gone` are skips, not failed generation steps.
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
