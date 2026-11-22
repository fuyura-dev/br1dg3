# Experiment log

## 2026-11-22 — Initial audit and content review

Ran [audit_dataset.py](scripts/audit_dataset.py) on the 331 original HTML files.
All were present, readable, nonempty, and identical to their reference copies.
The pool contained 328 distinct contents and two exact-duplicate groups.

The `flags` column in `inventory.csv` recorded:

| Flag | Condition | Files |
| --- | --- | ---: |
| `possible_error_page` | Error-related wording in the title or first 2,000 extracted text characters | 45 |
| `little_text` | Fewer than 100 extracted text characters | 16 |
| `nul_byte` | A NUL character in the file | 1 |

Ten files had both error-page and low-text flags: **52 unique files were flagged**.
The other 279 had no flags.

**Review:** Reviewed all **52 flagged files**. Of these, **38 were identified as
unusable**, while **14 remained candidates**.

**Decision:** Set aside **38 snapshots** under the unavailable/incomplete snapshot
criteria: **35** contained error, access-restriction, or verification responses
instead of the intended page content; **3** contained only loading or redirect
placeholders. The five files in the duplicate groups are already included in
these 38.

The other **14 flagged files** remained candidates. Ordinary keyword matches,
small accessibility test cases, and an isolated NUL inside CSS did not justify
exclusion. Together with the 279 unflagged files, **293 candidates** remain for
the manuscript's eligibility checks.

Kept all **331 originals unchanged**. Created copies under `audit-split/unusable/`
(38) and `audit-split/candidates/` (293), verifying every copy against its original.
The audit script's four synthetic tests and Ruff checks passed.
