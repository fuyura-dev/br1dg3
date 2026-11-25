# Structural preservation

`structure.py::calculate_structural_preservation()` is the metric used by the
repair and evaluation APIs for both SDG and zero-shot repairs. It computes exact,
unpruned Zhang–Shasha tree edit distance (TED), with unit costs for node insertion,
deletion, and tag-name changes. Similarity is `max(0, 1 - TED / max_nodes)`; the
preservation threshold is 0.85 by default. The returned similarity retains its
floating-point precision and is compared with the threshold before any display
rounding. The frontend rounds only its display and uses the returned preservation
verdict. Spreadsheet calculations should likewise apply the threshold to the
unrounded similarity derived from TED and both node counts.

Trees contain ordered element nodes after shared script/style preprocessing.
Text, attributes, and comments are excluded; fragments use a synthetic document
root. “Unpruned” means these parsed trees are not contracted before measuring TED.
Large trees can take longer to evaluate.

## Syntactic validity

`safety.py::calculate_safety()` uses **html5lib 1.1** directly to check the
supplied HTML for parsing errors. It does not replace the artifact with the
parser's recovered tree, change repair acceptance, or alter other metrics.
BeautifulSoup remains in the repair pipeline; within this check it only
identifies explicit document markup and whether the source contains elements.
The original candidate string is passed unchanged to html5lib.

- Use document mode when either the original input or candidate has a doctype
  or an `html`, `head`, or `body` element. Document mode requires a valid HTML
  doctype; pre-existing errors are not waived for either repair method.
- Otherwise use fragment mode with a `div` context. A fragment does not need a
  doctype or document wrapper. Context-specific fragments such as bare `tr`/`td`
  are not supported; supply their containing table. Comments, attribute values,
  and text inside script/textarea/title do not select document mode.
- Parsing uses `scripting=False` and collects every reported parsing error,
  including errors recovered by the parser. A nonempty output containing HTML
  elements receives `score: 1` only when there are no reported parse errors.
  Empty or element-free output receives 0. Legal optional closing tags are
  permitted. Markdown fences retain the existing warning-only treatment.
- Responses retain the existing safety fields and add `parser`,
  `parser_version`, `parse_mode`, `fragment_context`, `error_count`, and `errors`
  (code, message, line, column). Positions refer to the supplied evaluation
  string, not the original page or individual LLM reply. `element_count` counts
  recovered element nodes, including implicit document elements, excluding
  comments and the fragment root.
- An unexpected checker failure produces `reason: "validator_error"`, null
  `score`/`is_valid`/error details, and an unavailable dashboard result. Retain
  and retry that measurement; do not count it as valid or invalid. Empty output
  and no-candidate assignments also have null error details because parsing
  was not performed. Other metrics remain independent.

This is **absence of parsing errors under the specified parser**, not complete
HTML conformance or accessibility validation. For example, `<ul><div>Text</div></ul>`
has a prohibited child but causes no html5lib parsing error. Axe still measures
accessibility separately. html5lib is version-pinned; this is not a claim of
conformance with every rule in the latest HTML specification.

For repair runs the measured artifact is the accepted assembled candidate,
before fallback substitution and script/style restoration. Existing preprocessing
and patch assembly may already have normalized errors in raw replies; this score
does not measure raw LLM-generation syntax. Standalone `/evaluate` checks the
supplied `html_repaired`, using `html_original` to establish document context.
Use saved prepared candidates and matching originals when replaying runs.

## Accessibility evaluation scope

Automatic scans use the 39 selected Axe 4.10.3 rules documented in the
[detection inventory](../detection/README.md). Both repair methods use the same
list. `fully_fixed` means no confirmed selected-rule violations remain on the
evaluated snapshot, subject to the existing scan/generation failure policy.
Excluded violations and results needing review can still exist.

`EvaluationReport.scan_reports` retains complete before/after reports when the
evaluator performs those scans. Entries are null when only precomputed violation
lists were supplied, a scan was skipped, or a scan failed. Precomputed lists must
already use the selected-rule scope; no extra scan is performed to reconstruct
missing evidence. `/repair` returns the reports from its own scans at the response
level. The four Axe outcome arrays remain separate; only selected confirmed
violations enter effectiveness. Metric formulas and count granularity are unchanged.

## Candidate and fallback scoring

When a `RepairRun` is supplied, evaluation uses its accepted assembled candidate.
If repair was needed but no reply/patch was accepted, `fallback_used` is true and
the original/current fallback receives no generated-repair credit. The report
sets `evaluation.artifact` to `no_candidate` and `evaluation.score_basis` to
`no_candidate_failure_policy`. These are assigned all-run scores, not measurements
of the returned fallback:

| Metric | No-candidate result |
| --- | --- |
| Effectiveness | Analysis after-count equals before-count; zero reduction; improved and fully fixed are false; `no_candidate: true`. |
| Safety | Score 0, `is_valid: false`, reason `no_candidate`. This does not claim that the fallback contains syntax errors. |
| Structure | Similarity 0 and preserved false. TED, candidate node count, and max node count are null because there is no candidate tree. Original node count is retained. `unparseable` remains false: no candidate was parsed. |
| Semantic dependency preservation | Assigned preserved count and rate 0 when original extracted edges exist. With none, `has_dependencies: false` and rate null (N/A). Extraction failure leaves eligibility/counts unknown. Not-preserved count is null and examples empty; no loss in the fallback was measured. |
| Efficiency | Attempted generations, application attempts and known usage subtotals are retained. Incomplete totals are null, not zero; legacy cost is unavailable when required usage is missing. |

Generation failure does not set `scan_failed` by itself. Standalone evaluation
with `fallback_used: true` skips a final scan of the fallback, but still requires
a successful initial scan. `/repair` keeps its existing final-scan behavior;
its top-level issue counts describe that scan, while metric counts follow the
declared scoring policy.

An accepted candidate identical to the input is evaluated normally. A partial
SDG run is evaluated on its assembled candidate, retaining failed steps separately.
With HTML alone, the evaluator cannot infer generation failure from equality;
saved fallback evaluations must supply `fallback_used: true` explicitly.

Full HTML conformance is outside the syntax check. Relationship preservation uses
the bounded graph-comparison policy below; semantic validity is not established.
Dataset aggregation/export remains separate work.
No-candidate rows belong in the planned N denominator,
and in N_s only when original dependencies exist; do not drop them as missing TED.

## SDG relationship preservation

`semantic.py::calculate_semantic_preservation()` retains its entry-point name for
compatibility and reports `metric: sdg_relationship_preservation`, version 4.
The interface and thesis dimension keep the name **Semantic Dependency
Preservation**, operationally defined as preservation of SDG-modeled relationships.
It measures preservation of the existing SDG model's extracted edges across its eight
categories. It does **not** verify that original or preserved edges are semantically
valid, meaningful, WCAG-conforming, or free of newly introduced conflicts.

The shared SDG builder, eight extractor categories, repair context, prompts,
ordering and patching are unchanged. A reference extractor may still emit a link
to an inappropriate target. Preserving that edge earns graph-preservation credit;
it is not evidence that the reference is valid. Do not label this metric as the
preservation of **valid** semantic dependencies.

### Counting and comparison

- One occurrence is `(relation label, original source node, original target node)`.
  Distinct repeated elements remain distinct. Duplicate discoveries of the same
  typed edge count once; different relation labels count separately, including
  overlapping category representations. There is no new cross-category semantic
  deduplication or all-pairs expansion.
- Let `D_before` count original extracted edges and `D_preserved` count those whose
  matched endpoints have the same directed relation label in the candidate.
  Rate = `100 * D_preserved / D_before`. Counts are the reproducible spreadsheet
  inputs; the returned rate is unrounded and the UI rounds only its display.
- Direct edges are compared. A new intermediate heading, focusable element or
  group member can change an original edge even when the edit is beneficial.
  No ancestor-path, focus-precedence, wrapper or grouping equivalence is inferred.
  Lower preservation means changed modeled connections, not necessarily poorer repair.
- New candidate edges do not increase the numerator. Original eligibility comes
  from the same prepared original for both methods; zero original edges means N/A
  for this metric only. Mean document rates must not be replaced with pooled counts.

### Element correspondence

`semantic_matching.py` provides a deterministic, one-to-one heuristic shared by
both methods (`policy: unique_ids_then_normalized_subtrees_then_matched_parent_v3`).
It uses no repair tracking tokens or graph-preservation optimization:

1. Identical prepared documents use document-order occurrence correspondence.
2. Otherwise, IDs appearing exactly once on each side anchor correspondence.
3. Unique normalized subtrees anchor whole corresponding subtrees, including
   repeated descendants, if they do not conflict with existing ID anchors.
4. Strong matching alternates top-down (unique subtrees and unique node
   fingerprints inside matched parents) with bottom-up parent consensus (an
   unmatched parent whose own fingerprint matches an unmatched candidate parent
   and whose matched children map exclusively between them).
5. After strong matching stops expanding, ordered fallbacks run one node at a
   time and return to strong matching after any new match:
   - Label-attribute relaxation (`aria-label`, `alt`, `title`) for unique
     subtrees inside matched parents, globally unique subtrees, unique node
     fingerprints inside matched parents, and bottom-up parent consensus.
   - Heading-level retagging (`h1`–`h6`) for unique subtrees/nodes inside
     matched parents and globally unique heading subtrees.
   - Additional repair/cleanup attributes (`role`, `lang`, `type`) inside
     matched parents and root, first preserving empty attributes and then
     dropping empty attributes (`""` / empty `class`).
   - Originally-empty headings or `<label>` elements filled with accessible text
     (requiring the exact original tag and uniqueness within a matched parent).
   - Monotonic sibling gaps inside matched parents: first a unique 1-to-1
     unmatched child between matched anchors, then exact same-count (`k == k`)
     identical unmatched siblings sharing a relaxed subtree fingerprint, paired
     in document order.

Fingerprints include tags, other attributes, direct text and child order. They
normalize whitespace and ignore IDs, modeled ID-reference attribute values,
fragment-link targets, comments and repair-marker attributes. External `href`
values remain evidence. Unique-ID matches can survive tag/attribute edits; the
other paths require their declared fingerprint evidence. No fuzzy score
threshold or forced match for deletions or mismatched sibling counts is used.
The same matching inputs and rules apply to zero-shot and BR1DG3 artifacts.

Fallback exclusions apply only to correspondence: SDG extraction and typed-edge
comparison still use the complete attributes and real heading tags. Matching an
element does not establish preservation of its relationships. Results record the
matching policy version, fallback exclusions, and the basis of each match.

This is operational correspondence, not proof of physical or semantic identity.
Reused unique IDs or indistinguishable replacements can still be misleading;
large rewrites may be unmatchable. Duplicate IDs are never unique-ID anchors,
although an unchanged document/subtree may establish occurrence correspondence.
Each match records its basis; mappings and original/candidate node IDs are local
to the saved prepared artifacts. Retain both artifacts when retaining evidence.

### Availability and raw evidence

The response preserves legacy `dependencies_before`, `dependencies_valid`,
`preservation_rate`, `broken_count`, `breakdown_valid`, and `broken_examples` keys.
Here “valid” means **preserved**, and “broken” means **not preserved as a graph edge**.
Prefer `relationships_before`, `relationships_preserved`, `preservation_rate`,
`not_preserved_count` and `breakdown_preserved` fields for new consumers.

| Status | Result |
| --- | --- |
| `measured` | Original denominator and preservation rate are available; edges with an unmatched endpoint after shared correspondence count as not preserved and are tracked separately in `unmatched_endpoint_count`. |
| `no_relationships` | Original count 0, `has_dependencies: false`, rate null. |
| `extraction_error` | Error stage/type/message preserved. An original failure leaves denominator/eligibility null; candidate or matching failure preserves the original denominator. |
| `no_candidate_failure_policy` | When original edges exist, assigned preserved count/rate 0. Observed outcomes stay null because no candidate was measured. |

`edge_outcomes` retains each original edge, mapped endpoints where known, and
`preserved`, `not_preserved` or `unmatched_endpoint`. `preserved_observed`,
`not_preserved_observed` (matched endpoints whose edge broke), and
`unmatched_endpoint_count` (deleted, corrupted, or unmatchable endpoints counted
as lost in `not_preserved_count`) sum to `relationships_before`. `unresolved_count`
remains 0 on measured v4 results for legacy compatibility. `matching` records
the policy, pairs, bases, duplicate IDs and unmatched node lists.

In version 4, an original edge whose source or target remains unmatched after
shared correspondence is counted as not preserved (`unmatched_endpoint`) rather
than leaving the document score unavailable. If a supplied candidate has no
parsed elements, it has no endpoints and preservation is measured as zero. A
missing/non-string candidate is an error unless the explicit no-candidate policy
applies. A graph-construction/endpoint failure is never converted to an empty
graph. Other metrics remain independently evaluable.

Report evaluator versions consistently and reevaluate saved artifacts under one
version while retaining earlier reports. Version 1, 2, 3, and 4 results differ
in correspondence or unmatched-endpoint policy and must not be pooled across
versions.

Run `python -m unittest tests.test_semantic tests.test_sdg_preservation` for occurrence
counting, correspondence, model limits, missingness and evaluator integration.

## Optional comparison

Run these commands from `backend/` using the backend Python environment and saved
UTF-8 HTML files. They do not generate repairs or call an LLM.

Comparison off (default; unpruned only):

```bash
python -m scripts.compare_ted original.html repaired.html
```

Comparison on:

```bash
python -m scripts.compare_ted original.html repaired.html --compare-pruned
```

`--compare-pruned` is defined in `scripts/compare_ted.py`. It adds a separate
`legacy_pruned` result next to `unpruned`, including each distance, similarity,
preservation verdict, node counts, and elapsed seconds. Each timing includes
parsing and metric calculation; it is not LLM repair latency.

The legacy function, `calculate_legacy_pruned_structural_preservation()`, retains
the old pruning behavior for comparison but shares the corrected unrounded
scoring; it does not reproduce historical round-before-threshold results.
Pruning can change edit costs and preservation
verdicts, so use the unpruned metric consistently for both repair approaches in
the main experiment. Running the comparison command does not change API behavior
or any saved configuration; the APIs always use the unpruned function.
