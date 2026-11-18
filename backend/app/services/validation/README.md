# Structural preservation

`structure.py::calculate_structural_preservation()` is the metric used by the
repair and evaluation APIs for both SDG and zero-shot repairs. It computes exact,
unpruned Zhang–Shasha tree edit distance (TED), with unit costs for node insertion,
deletion, and tag-name changes. Similarity is `max(0, 1 - TED / max_nodes)`; the
preservation threshold is 0.85 by default.

Trees contain ordered element nodes after shared script/style preprocessing.
Text, attributes, and comments are excluded; fragments use a synthetic document
root. “Unpruned” means these parsed trees are not contracted before measuring TED.
Large trees can take longer to evaluate.

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
| Semantic | Preserved count and SDP 0 when original dependencies exist. With none, `has_dependencies: false` and rate null (N/A). Broken count is null and broken examples empty; no breakage in the fallback was measured. |
| Efficiency | Available recorded usage/cost is retained without changing the existing accounting. |

Generation failure does not set `scan_failed` by itself. Standalone evaluation
with `fallback_used: true` skips a final scan of the fallback, but still requires
a successful initial scan. `/repair` keeps its existing final-scan behavior;
its top-level issue counts describe that scan, while metric counts follow the
declared scoring policy.

An accepted candidate identical to the input is evaluated normally. A partial
SDG run is evaluated on its assembled candidate, retaining failed steps separately.
With HTML alone, the evaluator cannot infer generation failure from equality;
saved fallback evaluations must supply `fallback_used: true` explicitly.

Stronger HTML validation, semantic relationship matching and validity rules,
usage accounting corrections, and dataset aggregation remain pending.
No-candidate rows belong in the planned N denominator,
and in N_s only when original dependencies exist; do not drop them as missing TED.

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
the old pruning behavior for comparison. It can change edit costs and preservation
verdicts, so use the unpruned metric consistently for both repair approaches in
the main experiment. Running the comparison command does not change API behavior
or any saved configuration; the APIs always use the unpruned function.
