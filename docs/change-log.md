**Project change log**

Record each completed code change by date. Format:

- **Code changed:** What changed and why.
- **Recommended manuscript change:** Mark **Required** when correcting an inaccurate manuscript claim, **Optional** when adding detail, or **None** when no recommendation applies. Include the affected section and suggested wording where applicable.
- **Verification:** Checks performed and their results, including any checks not completed.

**2026-11-10 — Repair caching and experimental bypass**

- **Code changed:** Kept the five-minute repair-response cache enabled by default in `backend/app/api/repair.py`, keyed by HTML and `use_sdg` so methods cannot share results. Added `use_cache: false` to bypass both cache reads and writes for experiments. Responses include `cache_hit`; cached metrics describe the original run. Existing frontend and extension requests use caching automatically. Added regression tests and documented the API options.
- **Recommended manuscript change:** **Optional.** No revision is needed for this fix; the manuscript already describes independent processing, and caching is an implementation detail. If additional detail is desired, in Chapter 3, **Data Generation/Gathering Procedure → Phase 2 — Repair Execution**, add after the first sentence: “During experimental runs, repair-response caching is disabled (`use_cache: false`) for both approaches. Each run is executed independently without reading or updating cached repair responses.”
- **Verification:** All 10 regression tests passed, covering method separation in both orders, normal cache reuse, different HTML inputs, fresh experimental runs for both methods, bypass without cache reads or writes, five-minute expiry, and pages with no detected issues. Detection and repair generation were mocked; no browser or paid LLM calls were made. Ruff checks on both Python files and `git diff --check` passed.

**2026-11-10 — Unpruned structural preservation**

- **Code changed:** `calculate_structural_preservation()` in `backend/app/services/validation/structure.py` now computes exact TED without subtree pruning for both repair approaches. The old pruning could count three deleted nodes as one and incorrectly mark a structure as preserved. Kept it in `calculate_legacy_pruned_structural_preservation()` for comparison. From `backend/`, run `python -m scripts.compare_ted original.html repaired.html` for unpruned results only; add `--compare-pruned` to show both metrics and their calculation times. Comparison is off by default and does not change API behavior. Use unpruned results for the main experiment.
- **Recommended manuscript change:** **Optional.** The existing TED formula can remain. For reproducibility, in Chapter 3, **Structural Preservation**, after the paragraph defining the two DOM trees and TED, add: “TED is computed on complete ordered element trees after script and style removal, without subtree pruning. Nodes are labeled by tag name, with unit insertion, deletion, and rename costs; text, attributes, and comments are excluded. The same unpruned metric is used for both repair approaches.” The baseline paper mentions DOM similarity and a 0.85 threshold but does not establish whether its implementation used pruning; do not describe this as a verified reproduction of its algorithm.
- **Verification:** All 12 structural and comparison tests passed, including repeated-subtree insertion/deletion and comparison on/off behavior. In the deletion example, unpruned TED is 3 (similarity 0.7857, not preserved), while legacy TED is 1 (0.9286, preserved). Ruff checks and `git diff --check` passed. No browser or LLM calls were made; runtime on the experimental dataset has not been benchmarked.
