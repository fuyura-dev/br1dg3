# Experiment log

## 2026-11-22 — Initial audit and content review

Ran [01_audit_dataset.py](scripts/01_audit_dataset.py) on the 331 original HTML files.
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

## 2026-11-23 — Eligibility filtering

The **293 candidates** were assessed with
[02_filter_dataset.py](scripts/02_filter_dataset.py), using shared preprocessing,
configured Axe checks, affected-element mapping, and SDG extraction.

**Criteria:** A technical pass requires detected violations, identification of all
affected targets in the saved HTML, and successful SDG extraction. Documents with
unmatched targets are excluded because the pipeline cannot reliably associate all
detected violations with source elements. Detected, mapped, and unmapped counts
are retained. Zero SDG edges alone do not exclude a document.

Stylesheet loading problems are recorded as warnings. Unavailable stylesheets are
disabled before scanning, and eligibility is decided from the completed Axe and
mapping results. A successful scan with no detected violations is recorded as
`not-passed`; processing errors remain under `needs-review`.

**Results (`eligibility-004/`):**

| Result | Files |
| --- | ---: |
| Passed technical checks | 258 |
| Excluded: no violations confirmed by the configured checks | 28 |
| Excluded: not all violation targets could be identified | 7 |
| Processing errors requiring review | 0 |

All **293 scans completed successfully**. The 35 excluded documents were copied
to `not-passed/`; the 258 technical passes were copied to `passed/`. All copies
match their inputs and originals, and the CSV and scan evidence agree.

Of the 258 technical passes, **257 have SDG edges**. The remaining document has
zero SDG edges and is retained with semantic applicability marked N/A.

**Decision:** Retain all **258 passing documents** for both repair approaches under
the applied eligibility criteria: **N = 258** and **N_s = 257**. The 38 audit
exclusions and 35 eligibility exclusions leave 73 excluded from the original 331.

Nine of the 28 zero-violation results also contain checks marked incomplete by
Axe. Their exclusion records the absence of confirmed violations, not a finding
of full accessibility.

## Technical pilot

Ran both repair methods on three accepted documents, including a larger page
and the zero-SDG-edge case. All six executions produced candidates and completed
scanning and measurement. Verified the six exported rows against saved records,
including token usage, timings, and semantic N/A for the zero-edge document.

The baseline ended with zero configured-check violations on all three documents.
BR1DG3 ended with zero on one document and one on each of the other two, where
an added heading introduced a landmark violation. Both methods retained a
pre-existing HTML syntax error on one document. These outcomes were kept as
measured. Pilot records remain separate from the full experiment.

## 2026-11-25 — Token-budget filtering

Applied [02_5_filter_token_budget.py](scripts/02_5_filter_token_budget.py) to the
258 eligible documents. Counted HTML after shared preprocessing removes script
and style elements, using the Gemini Developer API `countTokens` endpoint with
`gemini-3.1-flash-lite`. Retained counts at or below **60,000** and excluded counts
above **60,000** to reduce full-document output truncation risk for both methods.

**Results (`token-budget-002/`):** 152 passed, 106 exceeded the limit, and zero
required review. Verified all records, group memberships, original/copy hashes,
prepared HTML hashes, and threshold decisions. Original files are unchanged.

The same **152 documents** remain for both methods: **N = 152**, **N_s = 151**.
One retained document has zero SDG edges and remains semantic N/A. The paired
experiment will produce **304 method rows**, including unsuccessful runs.

## 2026-11-25 — Paired experiment

Completed all **152 of 152** documents under both methods in `run-003/`
(`gemini-3.1-flash-lite`, `thinking_level: minimal`, semantic evaluator v4).
All 152 shared pretests and all 304 method outcomes retain complete token usage
and zero transport retries: **260 accepted candidates** (151 baseline,
109 BR1DG3), **40 partial candidates** (BR1DG3), and **4 no-candidate outcomes**
retained under the declared failure policy:

- Documents 26, 35, and 44 BR1DG3 (target steps exceeding scope limits or rejected
  by tracking checks).
- Document 174 (`www_microsoft_com_en_us_research.html`) baseline, whose single
  whole-document request was rejected by the provider with HTTP 400 (`recitation`
  / copyright content filter) after 131.5 seconds. Following review of the saved
  attempt record, it was finalized as `no_candidate` (`no_candidate_failure_policy`)
  without repeating the request; BR1DG3 completed normally on Document 174.

All 300 post-repair scans and all 304 evaluation stages succeeded: **298 measured**
semantic results (150 baseline, 148 BR1DG3), **4 no-candidate failure-policy**
outcomes (1 baseline, 3 BR1DG3), and **2 semantic N/A** outcomes (`no_relationships`
on zero-edge Document 317 under both methods), with zero unresolved semantic
measurements or validator errors.

Verified the final 304-row raw export (`run-003-final.csv`): **304 completed, 0 error,
0 interrupted, 0 unstarted**, covering all **N = 152** paired documents
(**N_s = 151** for semantic dependency preservation), ready for spreadsheet
calculation.
