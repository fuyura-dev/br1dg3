"""Paired execution using the existing backend repair and validation services."""

import csv
import subprocess
import sys
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from bs4 import UnicodeDammit

from experiments.records import (
    PROJECT_ROOT,
    ExecutionStopped,
    digest,
    last_attempt,
    local_path,
    now,
    read_json,
    run_lock,
    timed_stage,
    write_json,
    write_text,
)

sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.detection.detect import scan_with_report
from app.services.detection.preprocess import preprocess
from app.services.repair.configuration import snapshot_configuration
from app.services.repair.runner import run_baseline, run_sdg
from app.services.repair.usage import summarize_completed_usage
from app.services.validation.effectiveness import (
    calculate_effectiveness,
    count_violations,
)
from app.services.validation.safety import calculate_safety
from app.services.validation.semantic import _extract, calculate_semantic_preservation
from app.services.validation.structure import (
    calculate_structural_preservation,
    count_nodes,
    html_to_tree,
)


def experiment_sources():
    paths = [Path(__file__), PROJECT_ROOT / "experiments/records.py",
             PROJECT_ROOT / "experiments/export.py",
             PROJECT_ROOT / "experiments/scripts/03_run_experiment.py"]
    return {str(p.relative_to(PROJECT_ROOT)): digest(p.read_bytes()) for p in paths}


def csv_rows(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or len({r["filename"] for r in rows}) != len(rows):
        raise ValueError(f"Empty or duplicate filename list: {path}")
    return rows


def prepare_run(dataset, inventory, output, document_numbers=None):
    """Verify and snapshot selected inputs without browser or model calls."""
    dataset, inventory = Path(dataset).resolve(), Path(inventory).resolve()
    output = local_path(output, "pilot", "runs")
    if output.exists():
        raise ValueError("Choose a new run directory; use --resume for an existing run")
    originals = {r["filename"]: (i, r) for i, r in enumerate(csv_rows(inventory), 1)}
    passed = [r for r in csv_rows(dataset / "results.csv") if r["status"] == "passed"]
    folder = dataset / "passed"
    if {p.name for p in folder.iterdir()} != {r["filename"] for r in passed}:
        raise ValueError("Passed folder does not match the eligibility report")
    selected = set(document_numbers or [])
    if document_numbers and len(selected) != len(document_numbers):
        raise ValueError("Document numbers must be unique")
    documents, inputs = [], {}
    for row in sorted(passed, key=lambda r: originals[r["filename"]][0]):
        number, original = originals[row["filename"]]
        if selected and number not in selected:
            continue
        filename = row["filename"]
        if Path(filename).name != filename or Path(filename).suffix.lower() != ".html":
            raise ValueError(f"Invalid HTML filename: {filename}")
        path = folder / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Expected an ordinary HTML file: {path}")
        data = path.read_bytes()
        if digest(data) != row["sha256"] or row["sha256"] != original["sha256"]:
            raise ValueError(f"Input differs from the audited file: {filename}")
        decoded = UnicodeDammit(data, is_html=True)
        if decoded.unicode_markup is None or decoded.contains_replacement_characters:
            raise ValueError(f"Cannot decode without replacement characters: {filename}")
        prepared = preprocess(decoded.unicode_markup)
        key = f"document-{number:04d}"
        methods = ["baseline", "br1dg3"] if len(documents) % 2 == 0 else ["br1dg3", "baseline"]
        documents.append({"number": number, "document_id": f"Document {number}", "key": key,
                          "filename": filename, "sha256": row["sha256"],
                          "prepared_sha256": digest(prepared.encode()), "encoding": decoded.original_encoding,
                          "eligibility": row, "methods": methods})
        inputs[key] = (data, prepared)
    if not documents or (selected and selected != {d["number"] for d in documents}):
        raise ValueError("Select document numbers belonging to the accepted passed set")
    configuration = snapshot_configuration()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    manifest = {"schema_version": 1, "run_id": uuid4().hex, "created_at": now(),
                "dataset": str(dataset), "inventory_sha256": digest(inventory.read_bytes()),
                "eligibility_sha256": digest((dataset / "results.csv").read_bytes()),
                "revision": revision, "configuration": configuration,
                "experiment_sources": experiment_sources(), "documents": documents}
    output.mkdir(parents=True, exist_ok=False)
    for document in documents:
        directory = output / document["key"]
        directory.mkdir()
        data, prepared = inputs[document["key"]]
        (directory / "original.html").write_bytes(data)
        write_text(directory / "prepared.html", prepared)
    write_json(output / "manifest.json", manifest)
    return manifest


def scan(html):
    result = scan_with_report(html)
    return {"violations": result.violations, "report": result.report}


def pretest(directory, document, html):
    initial = timed_stage(directory / "scan-before.json", lambda: scan(html))
    attempt = last_attempt(initial)
    if attempt.get("status") != "success":
        return {"ready": False, "reason": attempt.get("error", "Initial scan unavailable")}
    value = attempt["value"]
    if value["report"].get("prepared_html_sha256") != document["prepared_sha256"]:
        raise ValueError("Scan input hash differs from the saved prepared HTML")
    findings = count_violations(value["violations"])
    if findings == 0:
        return {"ready": False, "reason": "Pretest found no confirmed violations; membership decision required."}
    builder, edges = _extract(html)
    builder.violations = deepcopy(value["violations"])
    builder._mark_violations()
    mapped = sum(len(node["issues"]) for _, node in builder.graph.nodes(data=True))
    ready = findings == mapped and len(edges) == int(document["eligibility"]["original_sdg_edges"])
    return {"ready": ready, "dom_elements_before": count_nodes(html_to_tree(html)),
            "sdg_edges_before": len(edges), "mapped": mapped, "detected": findings,
            "reason": "" if ready else "Pretest mapping or original SDG count differs; decision required."}


def generate_repair(directory, method, html, violations, configuration_id):
    steps = []

    def progress(step, current_html):
        steps.append(step)
        write_json(directory / "progress.json", {
            "complete": False, "steps": [asdict(s) for s in steps],
            "partial_html": current_html, "known_usage": summarize_completed_usage(steps),
        })
        if step.status == "llm_error" or (step.llm is not None and step.llm.status == "request_error"):
            raise ExecutionStopped(
                f"Model request failed; progress saved in {directory / 'progress.json'}. "
                "Review the failed generation before continuing."
            )

    operation = run_baseline if method == "baseline" else run_sdg
    with (directory / "repair.log").open("a", encoding="utf-8") as log, redirect_stdout(log):
        run = operation(html, deepcopy(violations), on_progress=progress)
    # Save the entire returned run before evaluating it or checking its provenance.
    result = {"run": asdict(run), "usage": summarize_completed_usage(run.steps),
              "candidate_sha256": digest(run.candidate_html.encode()) if run.candidate_html is not None else None}
    write_json(directory / "returned-repair.json", result)
    if not run.configuration or run.configuration["configuration_id"] != configuration_id:
        raise ValueError("Repair configuration differs from the run manifest")
    if run.configuration["prepared_input_sha256"] != digest(preprocess(html).encode()):
        raise ValueError("Repair input differs from the shared prepared HTML")
    if run.candidate_html is not None:
        write_text(directory / "candidate.html", run.candidate_html)
    return result


def compute_metrics(directory, html, repair, before, after):
    candidate = repair["run"]["candidate_html"]
    missing = candidate is None
    tasks = {
        "effectiveness": lambda: calculate_effectiveness(before, after, no_candidate=missing),
        "semantic": lambda: calculate_semantic_preservation(html, candidate, no_candidate=missing),
    }
    if not missing:
        tasks.update(safety=lambda: calculate_safety(candidate, html_original=html),
                     structure=lambda: calculate_structural_preservation(html, candidate))
    for name, operation in tasks.items():
        print(f"    {name}", flush=True)
        timed_stage(directory / "metrics" / f"{name}.json", lambda op=operation: op().to_dict())
    return {"computed": list(tasks)}


def execute_method(directory, method, html, initial, configuration_id):
    directory.mkdir(exist_ok=True)
    repair_record = timed_stage(directory / "repair.json",
                                lambda: generate_repair(directory, method, html, initial["violations"], configuration_id),
                                resume_interrupted=False)
    repair = last_attempt(repair_record)
    if repair.get("status") == "interrupted":
        raise ExecutionStopped(f"Unfinished generation in {directory}; review recovery before continuing.")
    if repair.get("status") != "success":
        return
    value = repair["value"]
    candidate = value["run"]["candidate_html"]
    after = None
    if candidate is not None:
        if digest(candidate.encode()) != value["candidate_sha256"] or digest((directory / "candidate.html").read_bytes()) != value["candidate_sha256"]:
            raise ValueError(f"Saved candidate changed: {directory}")
        final = last_attempt(timed_stage(directory / "scan-after.json", lambda: scan(candidate)))
        if final.get("status") == "success":
            after = final["value"]["violations"]
    timed_stage(directory / "metrics.json",
                lambda: compute_metrics(directory, html, value, initial["violations"], after))


def document_pending(directory, document):
    """Terminal outcomes need no rerun; unfinished local work can still resume."""
    pre = last_attempt(read_json(directory / "pretest.json"))
    if pre.get("status") == "error":
        return False
    if pre.get("status") != "success":
        return True
    if not pre.get("value", {}).get("ready"):
        return False
    for method in document["methods"]:
        repair = last_attempt(read_json(directory / method / "repair.json"))
        metrics = last_attempt(read_json(directory / method / "metrics.json"))
        if repair.get("status") != "error" and metrics.get("status") not in {"success", "error"}:
            return True
    return False


def execute_run(output, *, batch_size=None):
    if batch_size is not None and batch_size < 1:
        raise ValueError("Batch size must be a positive document count")
    output = local_path(output, "pilot", "runs")
    with run_lock(output):
        manifest = read_json(output / "manifest.json")
        if not manifest or manifest.get("schema_version") != 1:
            raise ValueError("Run manifest is missing or unsupported")
        configuration_id = manifest["configuration"]["configuration_id"]
        if snapshot_configuration()["configuration_id"] != configuration_id or experiment_sources() != manifest["experiment_sources"]:
            raise ValueError("Run configuration/code changed; use a new run or review recovery before continuing")
        # Verify all saved input identities before making any model call.
        for document in manifest["documents"]:
            directory = output / document["key"]
            if digest((directory / "original.html").read_bytes()) != document["sha256"] or digest((directory / "prepared.html").read_bytes()) != document["prepared_sha256"]:
                raise ValueError(f"Saved input changed: {document['filename']}")
        pending = [d for d in manifest["documents"] if document_pending(output / d["key"], d)]
        selected = pending[:batch_size]
        print(f"Processing {len(selected)} of {len(pending)} pending documents", flush=True)
        for document in selected:
            directory = output / document["key"]
            # These backend entry points each prepare their own input. Passing
            # already serialized HTML would apply preprocessing a second time.
            html = UnicodeDammit((directory / "original.html").read_bytes(), is_html=True).unicode_markup
            if html is None or digest(preprocess(html).encode()) != document["prepared_sha256"]:
                raise ValueError(f"Input decoding/preparation changed: {document['filename']}")
            print(f"{document['document_id']}: {document['filename']}", flush=True)
            pre = last_attempt(timed_stage(directory / "pretest.json",
                                          lambda d=directory, doc=document, source=html: pretest(d, doc, source)))
            if pre.get("status") != "success" or not pre.get("value", {}).get("ready"):
                print(f"  Pretest unresolved: {pre.get('error') or pre.get('value', {}).get('reason')}", flush=True)
                continue
            initial = last_attempt(read_json(directory / "scan-before.json"))["value"]
            for method in document["methods"]:
                print(f"  {method}", flush=True)
                execute_method(directory / method, method, html, initial, configuration_id)
        remaining = sum(document_pending(output / d["key"], d) for d in manifest["documents"])
        print(f"Documents still pending: {remaining}", flush=True)
    return manifest
