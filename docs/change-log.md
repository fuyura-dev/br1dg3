**Project change log**

Record each completed code change by date. Format:

- **Code changed:** What changed and why.
- **Recommended manuscript change:** Mark **Required** when correcting an inaccurate manuscript claim, **Optional** when adding detail, or **None** when no recommendation applies. Include the affected section and suggested wording where applicable.
- **Verification:** Checks performed and their results, including any checks not completed.

**2026-11-10 — Repair caching and experimental bypass**

- **Code changed:** Kept the five-minute repair-response cache enabled by default in `backend/app/api/repair.py`, keyed by HTML and `use_sdg` so methods cannot share results. Added `use_cache: false` to bypass both cache reads and writes for experiments. Responses include `cache_hit`; cached metrics describe the original run. Existing frontend and extension requests use caching automatically. Added regression tests and documented the API options.
- **Recommended manuscript change:** **Optional.** No revision is needed for this fix; the manuscript already describes independent processing, and caching is an implementation detail. If additional detail is desired, in Chapter 3, **Data Generation/Gathering Procedure → Phase 2 — Repair Execution**, add after the first sentence: “During experimental runs, repair-response caching is disabled (`use_cache: false`) for both approaches. Each run is executed independently without reading or updating cached repair responses.”
- **Verification:** All 10 regression tests passed, covering method separation in both orders, normal cache reuse, different HTML inputs, fresh experimental runs for both methods, bypass without cache reads or writes, five-minute expiry, and pages with no detected issues. Detection and repair generation were mocked; no browser or paid LLM calls were made. Ruff checks on both Python files and `git diff --check` passed.
