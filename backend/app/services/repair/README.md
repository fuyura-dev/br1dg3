# LLM Repair

## Failed final-scan records

When a `/api/repair` run reaches the final accessibility scan and that scan fails,
`failed_runs.py` saves one JSON record in `backend/data/failed_runs/`. The folder
is created on the first saved failure and is ignored by Git. Its path is resolved
from the backend source location, independently of the working directory.

Each file is named `<record-id>.json`. The backend log reports that ID only after
the complete JSON file has been written. The record contains:

- Schema version, record ID, UTC recording time, repair method, and failure stage.
- `original_html`: the submitted HTML, including its original scripts and styles.
- `evaluation_original_html`: the original prepared for evaluation, with scripts
  and styles stashed as placeholders by the repair API.
- The selected-rule `violations_before`, and `violations_after: null` because the
  final scan did not supply a measurement.
- The scan error's type and message.
- `repair_run`: the runner's output HTML, unmapped-target count, and complete step records.
  Each available `llm` record preserves reply text, model, status, token fields,
  attempts, and latency as currently recorded. A missing LLM result remains null.

These are saved run artifacts, not validated repairs. The runner's output may
include fallback output; candidate/fallback separation remains review item #5.
Usage is preserved without recalculation, and existing usage-field limitations
still apply. Accurate request/token/cost accounting remains review item #13;
this recorder does not calculate a monetary cost or claim to retain the full
provider response.

Saving performs no repair generation, detection retry, or metric computation.
The API continues returning its existing HTTP 503 error and does not cache the
failed result. If storage fails, the backend logs that the record could not be
saved and preserves the original scan error. Normal write failures are cleaned
up before a final JSON file is published.

Successful repairs, cache hits, initial-scan failures, and requests outside this
`/api/repair` final-scan failure path do not create these records. This folder is
not the complete experiment logger planned under review item #17.
