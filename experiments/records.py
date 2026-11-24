"""Local JSON records and timed stages for the experiment commands."""

import fcntl
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = PROJECT_ROOT / "experiments/local"


class RecordingError(RuntimeError):
    """Stop execution if evidence cannot be saved."""


class ExecutionStopped(RuntimeError):
    """Stop further requests while an unfinished generation needs review."""


def digest(data):
    return sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def write_text(path, value):
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        raise RecordingError(f"Could not save {path}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path, value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    except (TypeError, ValueError) as exc:
        raise RecordingError(f"Could not serialize {path}: {exc}") from exc
    write_text(path, encoded)


def local_path(path, *groups):
    path = Path(path).resolve()
    if not any(path.is_relative_to(LOCAL_ROOT / group) and path != LOCAL_ROOT / group for group in groups):
        raise ValueError(f"Choose a path below experiments/local/{' or '.join(groups)}/")
    return path


@contextmanager
def run_lock(directory, *, shared=False):
    """Linux/macOS file lock: released by the OS even after a process is killed."""
    with (Path(directory) / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("This run is in use by another command") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def last_attempt(record):
    attempts = (record or {}).get("attempts", [])
    return attempts[-1] if attempts else {}


def elapsed(record):
    attempts = (record or {}).get("attempts", [])
    if not attempts or any(a.get("seconds") is None for a in attempts):
        return None
    return sum(a["seconds"] for a in attempts)


def timed_stage(path, operation, *, resume_interrupted=True):
    """Reuse terminal results; retain attempts when resuming interrupted local work."""
    record = read_json(path, {"attempts": []})
    previous = last_attempt(record)
    if previous.get("status") in {"success", "error"}:
        return record
    if previous:
        previous["status"] = "interrupted"
        previous.setdefault("error", "Stage did not complete; saved evidence retained.")
        write_json(path, record)
        if not resume_interrupted:
            return record
    attempt = {"status": "running", "started_at": now(), "seconds": None}
    record["attempts"].append(attempt)
    write_json(path, record)
    started = time.perf_counter()
    try:
        attempt["value"] = operation()
        attempt["status"] = "success"
    except RecordingError:
        raise  # Never continue to more paid work after a storage failure.
    except (KeyboardInterrupt, SystemExit, ExecutionStopped) as exc:
        attempt.update(status="interrupted", seconds=time.perf_counter() - started, ended_at=now())
        if isinstance(exc, ExecutionStopped):
            attempt["error"] = str(exc)
        write_json(path, record)
        raise
    except Exception as exc:  # noqa: BLE001 - a failed stage is a saved experimental outcome
        attempt.update(status="error", error=f"{type(exc).__name__}: {exc}")
    attempt.update(seconds=time.perf_counter() - started, ended_at=now())
    write_json(path, record)
    return record
