# Experiment raw-data columns

Use one CSV per run, with one row per document and method. Filter `method` in
Sheets to compare `baseline` and `br1dg3`. Both rows use the same original
measurements. A complete run over 258 documents has 516 rows, including failures.

[example-results.csv](example-results.csv) contains invented values for four
documents under both methods. It illustrates the format, not experiment results.

## Columns

The 30 columns below match the example CSV order. Counts are nonnegative integers;
durations are nonnegative decimal seconds. An empty numeric cell means unavailable
or unmeasured; zero is an observed value.
Semantic N/A is recorded in `semantic_status`, with the preservation count blank.

| Column | Meaning and source |
| --- | --- |
| `run_id` | Run identifier shared by the CSV and supporting records. |
| `document_id` | Stable `Document n` identifier assigned from the original inventory order; keep it after filtering. |
| `filename` | Original filename associated with the document ID. |
| `method` | `baseline` or `br1dg3`. |
| `run_status` | Execution outcome; see statuses below. |
| `generation_status` | `RepairRun.generation_status`; blank if generation has no recorded outcome. |
| `reason` | Short explanation of failures, partial results, or unavailable measurements. |
| `violations_before` | Configured rule-element occurrences from the shared successful initial Axe scan. |
| `violations_after` | Configured rule-element occurrences from a successful final Axe scan; blank if no scan result exists. |
| `scan_status` | Final Axe scan outcome. Stylesheet warnings stay in the scan report. |
| `syntactically_valid` | Measured `safety.score`: 1 for valid or 0 for invalid. Blank for no candidate or validator failure. |
| `safety_status` | Whether syntactic validity was measured, unavailable, or not evaluated. |
| `dom_elements_before` | Shared original element-tree size, using `count_nodes(html_to_tree(prepared_html))`; also `structure.original_nodes`. |
| `dom_elements_after` | `structure.repaired_nodes`, when a candidate tree was examined. |
| `tree_edit_distance` | Exact unpruned `structure.tree_edit_distance`; blank for absent/unparseable trees or evaluation errors. |
| `structure_status` | Whether structural comparison was measured, unavailable, or not evaluated. |
| `sdg_edges_before` | Original extracted SDG relationships, from `semantic.dependencies_before` or the matching shared pretest record. |
| `sdg_edges_preserved` | `semantic.dependencies_valid` only when `semantic.status` is `measured`. |
| `semantic_status` | Semantic evaluation outcome, including N/A and unresolved matching. |
| `api_calls` | `efficiency.completed_response_count`, including completed replies whose patches were rejected. |
| `prompt_tokens` | `efficiency.completed_response_usage.prompt_tokens`. |
| `completion_tokens` | `efficiency.completed_response_usage.completion_tokens`: reply tokens only. |
| `thought_tokens` | `efficiency.completed_response_usage.thought_tokens`, kept separate from reply tokens. |
| `total_tokens` | `efficiency.completed_response_usage.total_tokens`, as reported by the provider. |
| `usage_status` | Completeness of the completed-response count and token totals. |
| `scan_before_seconds` | Elapsed initial scan time, including browser startup, stylesheet settling, Axe, and browser cleanup. |
| `repair_seconds` | Elapsed repair-stage time, including preparation, SDG/context work where used, model requests, retry waits, and patch application. |
| `scan_after_seconds` | Elapsed final scan time, using the same boundary as the initial scan. |
| `metrics_seconds` | Elapsed metric computation and report assembly, excluding both accessibility scans. |
| `structure_seconds` | Time inside the structural evaluator: tree construction, element counts, and exact TED/comparison. Included in `metrics_seconds`. |

Violation counts sum the affected nodes for each configured rule. A single
element failing two rules contributes two occurrences. Count only a successful
scan; the absence of a report is not a zero-violation result.

Syntactic validity uses html5lib 1.1: the evaluated output must be nonempty,
contain HTML elements, and have no reported parsing errors. Full documents use
document mode and fragments use fragment mode. Semantic counts measure
preservation of the extracted SDG relationships.

API calls and token totals use completed responses, including rejected, empty,
or ineffective replies. This differs from the backend's attempted-generation
counter. Export each token component only when its total is complete. Retain
known subtotals and completeness flags in the supporting usage record. Do not
reconstruct missing provider totals or infer missing thought tokens by subtraction.
The experiment runner stores this same completed-response summary under `usage`
in its saved repair record.

Backend sources: [detection](../../backend/app/services/detection/detect.py),
[generation outcomes](../../backend/app/services/repair/runner.py),
[evaluation](../../backend/app/services/validation/evaluator.py),
[safety](../../backend/app/services/validation/safety.py),
[structure](../../backend/app/services/validation/structure.py),
[semantic relationships](../../backend/app/services/validation/semantic.py), and
[completed-response usage](../../backend/app/services/repair/usage.py).

## Status values

| Column | Values |
| --- | --- |
| `run_status` | `completed`: execution finished, including a recorded no-candidate outcome; `error`: a generation/evaluation stage failed; `interrupted`: execution stopped before completion; `not_run`: no execution started. |
| `generation_status` | `accepted`, `partial`, `no_candidate`, or `not_needed`, as recorded by the backend. Blank when unknown. |
| `scan_status` | `success`, `error`, or `not_run`. |
| `safety_status` | `measured`, `validator_error`, or `not_run`. Both valid and invalid measured HTML use `measured`. |
| `structure_status` | `measured`, `unparseable`, `error`, or `not_run`. |
| `semantic_status` | `measured`, `no_relationships`, `unresolved_matching`, `extraction_error`, `no_candidate_failure_policy`, or `not_run`. |
| `usage_status` | `complete`: all five usage values are known; `partial`: some are known; `unknown`: none is established. |

`completed` and `accepted` do not mean all violations were repaired. A partially
accepted repair is evaluated on its assembled candidate. A failed measurement
leaves that measurement blank while preserving the others. Explain errors and
missing results in `reason`; keep detailed exceptions in the supporting records.

When execution stops after a model-request error, unfinished generation uses
`interrupted`. Its completed-step evidence and known usage remain in
`progress.json`; the full method's usage stays unavailable until its outcome is
established. Unstarted pairs between batches remain `not_run`.

For an unparseable candidate, retain any observed node counts and leave TED blank.
The backend's conventional distance for an unparseable tree is not measured TED.
For unresolved semantic matching, keep the complete preservation count blank;
retain observed subsets and unresolved edges in the detailed report. Original
measurements remain available even if later repair or evaluation fails.

## Timing

Measure elapsed wall time with `time.perf_counter()` around each stage. Repair
time includes model/network waiting and retry delays. Supply the scan results to
evaluation with automatic detection disabled so metrics time excludes scanning.

`structure_seconds` is a breakdown of `metrics_seconds`, not an additional phase.
For example, metrics taking 6 seconds and structure taking 5 seconds means the
structural evaluator used 5 of those 6 seconds. For complete timing records, add
the two scan times, repair time, and metrics time to obtain the recorded stage
total. Do not add structure time again. Repair time includes saving progress;
metrics time includes saving component reports. Initial input copying, shared
setup, and final CSV export are outside these stage timers.

If the initial scan is shared, repeat its time on both method rows and count it
once per document when calculating batch workload. A reused scan without recorded
timing has a blank duration; do not estimate it from a later scan.

Keep elapsed time when an attempted stage ends in an error. A stage that never
runs, or whose duration cannot be established, has a blank duration; distinguish
these cases using statuses and supporting records. A no-candidate result can
still have metrics time for usage/failure-policy computation while structure time
is blank. Preserve per-attempt timing evidence when work is resumed.

These timings are supporting runtime measurements alongside the manuscript's
API-call, token, and cost measures. The durations in the example CSV are invented.

## Spreadsheet computations

These fields supply the inputs for **Computation of Evaluation Metrics** and the
experiment paper's document tables (5A–5F, called A1–A6 in its procedure).

| Dimension / table | Inputs | Spreadsheet results |
| --- | --- | --- |
| Before repair / 5A | `violations_before`, `dom_elements_before`, `sdg_edges_before` | Initial counts and summaries; use one original record per document. |
| Effectiveness / 5B | Before/after violations and scan/generation status | AVB, AVA, AVR, CIR, FFR; reduction is before minus after, improvement means after < before, fully fixed means after = 0. |
| Safety / 5C | Measured validity and safety/generation status | SVR: percentage of documents assigned valid under the measurement and failure rules. |
| Structure / 5D | TED, both DOM sizes, and structure/generation status | SS from TED and the larger DOM size, ASS, and SPR using the unrounded 0.85 threshold. |
| Efficiency / 5E | Completed responses and token totals | TAC, TPT, TCT, TT, TC, CPF, TPF, APF using the documented price schedule. |
| Semantic preservation / 5F | Original and preserved SDG edges and semantic/generation status | SDP = preserved / original × 100; ASDP over applicable documents. |

Apply the same formulas separately to each method. The accepted dataset uses
N = 258 and N_s = 257 per method. Joining or filtering the CSV must not double
the original counts or treat 516 method rows as 516 distinct documents.

In the manuscript's token notation, P_i is `prompt_tokens` and C_i combines
`completion_tokens` plus `thought_tokens`. Compute TT from these components and
check it against provider-reported `total_tokens`; retain unknowns and investigate
disagreements. Compute costs using a recorded model/price schedule, not the
backend's legacy display-cost defaults.

Keep spreadsheet analysis columns separate from the raw CSV:

- No accepted candidate: keep post-repair measurements blank in the CSV. In
  analysis, assign after violations equal to before and zero safety, structure,
  and applicable semantic credit. Preserve API usage.
- Failed final scan: leave raw after violations blank. Apply the manuscript's
  no-improvement rule for effectiveness; retain other available measurements.
- Unparseable candidate tree: leave raw TED blank and assign zero structural
  credit in analysis.
- Zero original SDG edges: keep the document for other dimensions; semantic
  preservation is N/A for both methods and excluded only from N_s.
- Validator errors, unresolved matching, and incomplete usage remain unavailable;
  do not treat blank cells as measured zero or silently shrink the denominators.

## Supporting records and examples

Keep source/prepared/candidate hashes, effective model settings, code revision,
scan reports, stylesheet warnings, parser errors, SDG matching evidence, replies,
request attempts, usage completeness, and artifact paths in supporting records.
Join them to the CSV using `run_id`, `document_id`, and `method`.

The example CSV contains eight rows:

- Document 1: two evaluated repairs with the same original measurements.
- Document 2: a rejected baseline reply with recorded usage; BR1DG3 has an
  evaluated partial repair whose HTML is syntactically invalid.
- Document 3: zero original SDG edges under both methods; other measurements remain.
- Document 4: a failed baseline final scan with other measurements retained;
  BR1DG3 has a missing thought-token count despite a reported provider total.
