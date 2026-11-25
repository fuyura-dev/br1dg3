# BR1DG3 experiments

Experiment workspace for comparing BR1DG3 with the locally adapted zero-shot
baseline.

See the [experiment log](experiment-log.md) for completed preparation steps and findings.

See the [raw-data columns](schema/raw-data.md) and
[example CSV](schema/example-results.csv) for the spreadsheet format.

## Layout

```text
experiments/
  README.md
  experiment-log.md              # completed experiment work and findings
  .gitignore
  scripts/                       # experiment commands
    01_audit_dataset.py
    02_filter_dataset.py
    02_5_filter_token_budget.py
    03_run_experiment.py
    04_export_results.py
  execution.py                   # paired runs and saved stages
  export.py                      # saved records to CSV
  records.py                     # local records and timing
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
        token-budget-002/
          passed/                # prepared HTML has at most 60,000 tokens
          not-passed/            # prepared HTML exceeds 60,000 tokens
          needs-review/          # token count could not be established
          results.csv
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
`not_applicable`. Missing measurements stay blank. `content_review=pending` records
that the script does not perform manual content review. Later inclusion decisions
are recorded in the experiment log; the saved field is not updated automatically.
The token filter carries it forward unchanged and uses `status` for its outcome.

`results.csv` records per-file outcomes, reasons, and raw measurements.
`scan-results.jsonl` retains each scan report, graph evidence, and result as one
JSON record per line. Completed records are flushed after each file; an
interrupted run is partial and a rerun needs a fresh output directory.

Run the synthetic filter tests:

```bash
python -m unittest discover -s experiments/tests -p 'test_filter_dataset.py' -v
```

## Token-budget filter

From the project root with the backend venv active:

```bash
python experiments/scripts/02_5_filter_token_budget.py \
  --dataset experiments/local/datasets/ai4se/eligibility-004 \
  --output experiments/local/datasets/ai4se/token-budget-002
```

The command reads `passed/` and `results.csv` from the eligibility stage. It uses
the shared HTML decoding and preprocessing, removing `<script>` and `<style>`
elements while retaining inline style attributes and stylesheet links. It sends
the prepared HTML alone to the official Gemini Developer API `countTokens`
endpoint, using `LLM_API_KEY` and `LLM_MODEL` from `backend/.env`. Use the same model
for filtering and the paired experiment. Counting makes no repair or browser calls.

| CSV status | Token-budget result | Folder |
| --- | --- | --- |
| `passed` | Count is at most 60,000, including exactly 60,000 | `passed/` |
| `not_passed` | Count is greater than 60,000 | `not-passed/` |
| `needs_review` | Decoding, preparation, or counting failed; count is unknown | `needs-review/` |

Each group receives unchanged copies of the input HTML. The command verifies
source and copy hashes. `results.csv` retains the eligibility scan and SDG fields,
updates `status`, `reason`, and `error` for this stage, and adds `prepared_tokens`,
`count_model`, `token_limit`, `exclusion_operator`, and `prepared_sha256`. Unknown
counts stay blank. The 60,000-token limit leaves room for repair additions, but
does not guarantee the generated output will fit.

Choose a fresh output directory. Results are saved after each file; an interrupted
run is partial and a rerun needs another directory. Review the completed report
and any `needs-review` cases before preparing the paired experiment. Both methods
use the same retained `passed/` set.

## Paired experiment

From the project root with the backend venv active, prepare the accepted inputs:

```bash
python experiments/scripts/03_run_experiment.py \
  --dataset experiments/local/datasets/ai4se/token-budget-002 \
  --inventory experiments/local/audit/my-check-002/inventory.csv \
  --output experiments/local/runs/run-002 \
  --prepare-only
```

This verifies filenames and hashes, copies original and prepared inputs, and
writes `manifest.json`. It makes no browser or model calls. Choose a new output
directory for each run. For a pilot, use a directory below `experiments/local/pilot/`
and add `--documents` followed by original inventory row numbers (starting at 1,
excluding the header). IDs retain those numbers after filtering.

To process the next five pending documents, with both methods for each:

```bash
python experiments/scripts/03_run_experiment.py \
  --resume experiments/local/runs/run-002 \
  --batch-size 5
```

Repeat that command for the next batch. Change `5` to any positive integer to
adjust the batch size. Omitting `--batch-size` processes all remaining documents.
The limit applies to the current invocation; it is not saved as a default.
You can also pass it when creating and executing a new run in one command.

The full manifest and method order stay the same across batches. Completed work
is skipped, and a document needing only its remaining evaluation or second method
counts as one document. A failed pretest also uses one batch slot; recorded
terminal failures are retained without retrying. Batch size limits documents,
not model requests, tokens, or spending.

Execution makes model requests using the configured backend model and shared
settings. Each document has one fresh initial scan, shared by both methods.
The methods run sequentially, alternating which goes first across documents.
Each backend service receives the same decoded original so its own preprocessing
produces the recorded prepared input. Repairs use the existing service functions
and bypass frontend response caching.

The runner saves replies and usage as repair steps finish, then saves the complete
repair before final scanning and evaluation. Each validator has its own record;
one failed measurement leaves the other results available. The five durations
follow the [timing definitions](schema/raw-data.md#timing).

Records are organized by document and method:

```text
run-002/
  manifest.json
  document-0001/
    original.html
    prepared.html
    scan-before.json
    pretest.json
    baseline/
      progress.json
      repair.log
      returned-repair.json
      repair.json
      candidate.html
      scan-after.json
      metrics.json
      metrics/
        effectiveness.json
        safety.json
        structure.json
        semantic.json
    br1dg3/
      ...
```

Files appear as their stages run; a missing candidate has no `candidate.html`
or final scan. JSON stage records retain attempt outcomes, elapsed times, and
measurement evidence. Completed-response usage is stored with the repair.

Resume skips completed stages and continues scanning/evaluation from a saved
repair. Interrupted local scans or measurements can run again, retaining their
attempt history. A completed failed stage is retained rather than retried.
If a model request fails after the configured retry policy, the experiment saves
its progress and stops before further requests. This includes quota and
authentication errors. An unfinished generation blocks continuation until its
recovery is reviewed; it is never automatically repeated. Completed replies
rejected as repairs still proceed through the normal evaluation policy.

Known replies remain in `progress.json`; their usage is a subtotal until the whole
generation outcome is established. Changed input, candidate, configuration, or
execution code stops dependent work. Prepare a fresh run after changing execution
code; keep earlier manifests and results. A file lock prevents
two commands from executing the same run concurrently (Linux/macOS).

If the fresh pretest fails, finds no violations, or disagrees with the accepted
mapping/SDG criteria, the document stays in the manifest with an error record and
receives no model calls. Dataset membership is preserved for review.

## Raw CSV export

Export from saved records, including failed, interrupted, and unstarted pairs:

```bash
python experiments/scripts/04_export_results.py \
  --run experiments/local/runs/run-002 \
  --output experiments/local/exports/run-002.csv
```

The exporter writes the agreed 30 columns and does not load the model or browser
services. Choose a new CSV filename for each export. It reads a stopped run;
exporting while another command holds the execution lock is rejected.

Exports include every planned pair. Between batches, unstarted pairs are marked
`not_run` with unavailable measurements left blank. A manifest with N documents
exports 2N rows throughout the run. Use a new filename for each progress
export; the final CSV comes from the same run without merging batch files.

Run the synthetic experiment tests:

```bash
python -m unittest discover -s experiments/tests -v
```
