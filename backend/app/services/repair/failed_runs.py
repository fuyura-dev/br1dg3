"""Local records for repairs whose final accessibility scan fails."""

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from app.services.repair.runner import RepairRun


FAILED_RUNS_DIR = Path(__file__).resolve().parents[3] / "data" / "failed_runs"


def save_failed_run(
    *,
    original_html: str,
    evaluation_original_html: str,
    use_sdg: bool,
    violations_before: list[dict],
    run: "RepairRun",
    error: Exception,
) -> str:
    """Persist existing run data, returning its ID only after a complete write.

    LLM results are saved as recorded, without recalculating usage or cost.
    A step with no LLM result remains null rather than receiving invented usage.
    Storage errors propagate so the caller can report them separately.
    """
    record_id = uuid4().hex
    record = {
        "schema_version": 1,
        "record_id": record_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "failure_stage": "post_repair_scan",
        "method": "sdg" if use_sdg else "zero_shot",
        "original_html": original_html,
        "evaluation_original_html": evaluation_original_html,
        "violations_before": violations_before,
        "violations_after": None,
        "scan_error": {"type": type(error).__name__, "message": str(error)},
        "repair_run": asdict(run),
    }
    serialized = json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    FAILED_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    destination = FAILED_RUNS_DIR / f"{record_id}.json"
    temporary_path = None
    try:
        # Publish the JSON only after writing it completely in the same directory.
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=FAILED_RUNS_DIR,
            prefix=f".{record_id}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return record_id
