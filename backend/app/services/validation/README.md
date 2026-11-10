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
