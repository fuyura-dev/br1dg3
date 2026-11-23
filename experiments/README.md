# BR1DG3 experiments

Experiment workspace for comparing BR1DG3 with the locally adapted zero-shot
baseline.

See the [experiment log](experiment-log.md) for completed preparation steps and findings.

## Layout

```text
experiments/
  README.md
  experiment-log.md              # completed experiment work and findings
  .gitignore
  scripts/                       # experiment commands
    01_audit_dataset.py
    02_filter_dataset.py
  schema/                        # column definitions and synthetic examples
  tests/                         # tests using synthetic HTML
  local/                         # local data and results
    datasets/
      ai4se/
        original/                # original HTML inputs supplied locally
        audit-split/
          candidates/            # inputs to the eligibility filter
          unusable/              # snapshots set aside during the audit
        eligibility/
          passed/                # passed automated checks
          not-passed/            # failed an automated filter criterion
          needs-review/          # unresolved checks
          results.csv
          scan-results.jsonl
    audit/                       # inventories, findings, and supporting evidence
    manifests/                   # inclusion decisions referencing original files
    pilot/                       # separately labeled technical pilot runs
    runs/                        # final paired experiment records and artifacts
    exports/                     # raw spreadsheet exports
```

Git excludes `local/`. Recreate its directories when setting up a fresh clone.

## Local dataset placement

Place the original HTML files directly inside
`experiments/local/datasets/ai4se/original/`, preserving their filenames and
contents.

## Python environment

Use the existing backend virtual environment. From the repository root:

```bash
source backend/.venv/bin/activate
```

Backend dependency setup is documented in the [backend README](../backend/README.md).

## Audit

From the repository root, with the backend environment activated:

```bash
python experiments/scripts/01_audit_dataset.py \
  --originals experiments/local/datasets/ai4se/original \
  --reference-originals /path/to/reference/scraped_sites \
  --ground-truth /path/to/reference/dataset/ground_truth.csv \
  --output experiments/local/audit/run-001
```

`--source` selects the ground-truth CSV rows and defaults to `scraped_sites`.
Choose a new output directory for each run.

The command writes `inventory.csv` and prints a short summary in the terminal.
The CSV contains file sizes, reference-hash comparisons, duplicate groups, titles,
text excerpts, and basic review flags. The input files are read in place.

Run the synthetic audit tests from the repository root:

```bash
python -m unittest discover -s experiments/tests -p 'test_audit_dataset.py' -v
```

## Eligibility filter

From the project root with the backend venv active:

```bash
python experiments/scripts/02_filter_dataset.py \
  --input experiments/local/datasets/ai4se/audit-split/candidates \
  --output experiments/local/datasets/ai4se/eligibility
```

The command uses the backend's Chrome setup: local Chrome or a Selenium server
configured through `REMOTE_DRIVER_URL` in `backend/.env`. It checks browser startup
before writing results. The output directory may be new or contain only empty
`passed/`, `not-passed/`, and `needs-review/` folders. Choose a new output directory
for another run.

Each candidate is scanned using the backend's preprocessing and configured Axe
checks. The command maps affected elements and extracts original SDG relationships.
It copies the unchanged HTML into the appropriate folder and verifies its hash.

| CSV status | Meaning | Folder |
| --- | --- | --- |
| `passed` | Selected violations exist, affected elements map, and SDG extraction succeeds | `passed/` |
| `not_passed` | Empty snapshot, no configured-check violations, or not all violation targets could be identified | `not-passed/` |
| `needs_review` | Decoding, Axe, extraction, or mapping encountered a processing error | `needs-review/` |

Stylesheet loading problems are recorded in `stylesheet_warnings`. Unavailable
stylesheets are disabled in the scan browser before Axe runs; classification uses
the completed Axe and mapping results. Mapping exclusions retain the detected,
mapped, and unmapped occurrence counts.

Zero SDG edges do not prevent passing; semantic applicability is recorded as
`not_applicable`. Missing measurements stay blank. `content_review` remains
`pending`: passing these automated checks does not establish final inclusion
under the manuscript's content-related criteria.

`results.csv` records per-file outcomes, reasons, and raw measurements.
`scan-results.jsonl` retains each scan report, graph evidence, and result as one
JSON record per line. Completed records are flushed after each file; an
interrupted run is partial and a rerun needs a fresh output directory.

Run the synthetic filter tests:

```bash
python -m unittest discover -s experiments/tests -p 'test_filter_dataset.py' -v
```
