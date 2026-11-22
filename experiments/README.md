# BR1DG3 experiments

Experiment workspace for comparing BR1DG3 with the locally adapted zero-shot
baseline.

See the [experiment log](experiment-log.md) for completed preparation steps and findings.

## Layout

```text
experiments/
  README.md
  .gitignore
  scripts/                       # experiment commands
  schema/                        # column definitions and synthetic examples
  tests/                         # tests using synthetic HTML
  local/                         # local data and results
    datasets/
      ai4se/
        original/                # original HTML inputs supplied locally
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
python experiments/scripts/audit_dataset.py \
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
