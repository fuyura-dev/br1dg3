"""Export saved experiment observations without importing model/browser services."""

import csv
from pathlib import Path

from experiments.records import elapsed, last_attempt, local_path, read_json, run_lock

COLUMNS = [
    "run_id", "document_id", "filename", "method", "run_status", "generation_status", "reason",
    "violations_before", "violations_after", "scan_status", "syntactically_valid", "safety_status",
    "dom_elements_before", "dom_elements_after", "tree_edit_distance", "structure_status",
    "sdg_edges_before", "sdg_edges_preserved", "semantic_status", "api_calls", "prompt_tokens",
    "completion_tokens", "thought_tokens", "total_tokens", "usage_status", "scan_before_seconds",
    "repair_seconds", "scan_after_seconds", "metrics_seconds", "structure_seconds",
]


def row_for(output, manifest, document, method):
    shared = Path(output) / document["key"]
    directory = shared / method
    paths = {"pretest": shared / "pretest.json", "before": shared / "scan-before.json",
             "repair": directory / "repair.json", "after": directory / "scan-after.json",
             "metrics": directory / "metrics.json"}
    paths.update({name: directory / "metrics" / f"{name}.json"
                  for name in ("effectiveness", "safety", "structure", "semantic")})
    records = {name: read_json(path) for name, path in paths.items()}
    attempts = {name: last_attempt(record) for name, record in records.items()}
    values = {name: attempt.get("value", {}) for name, attempt in attempts.items()}
    repair = values["repair"] or read_json(directory / "returned-repair.json", {})
    run = repair.get("run", {})
    row = dict.fromkeys(COLUMNS)
    row.update(run_id=manifest["run_id"], document_id=document["document_id"],
               filename=document["filename"], method=method, run_status="not_run", reason="",
               generation_status=run.get("generation_status"), scan_status="not_run",
               safety_status="not_run", structure_status="not_run", semantic_status="not_run",
               usage_status="unknown")
    for key in ("dom_elements_before", "sdg_edges_before"):
        row[key] = values["pretest"].get(key)
    for stage, column in (("before", "violations_before"), ("after", "violations_after")):
        if attempts[stage].get("status") == "success":
            row[column] = sum(len(v["nodes"]) for v in values[stage]["violations"])
    if attempts["after"]:
        row["scan_status"] = "success" if attempts["after"]["status"] == "success" else "error"
    if attempts["safety"]:
        safety = values["safety"]
        row["safety_status"] = "measured" if safety.get("is_valid") is not None else "validator_error"
        if row["safety_status"] == "measured":
            row["syntactically_valid"] = safety["score"]
    if attempts["structure"]:
        structure = values["structure"]
        row["structure_status"] = (
            "error" if attempts["structure"]["status"] != "success"
            else "unparseable" if structure.get("unparseable") else "measured"
        )
        row["dom_elements_after"] = structure.get("repaired_nodes")
        if row["structure_status"] == "measured":
            row["tree_edit_distance"] = structure["tree_edit_distance"]
    if attempts["semantic"]:
        semantic = values["semantic"]
        row["semantic_status"] = semantic.get("status", "extraction_error")
        if row["semantic_status"] == "measured":
            row["sdg_edges_preserved"] = semantic["dependencies_valid"]
    if repair:
        usage = repair.get("usage", {})
        row["api_calls"] = usage.get("completed_response_count")
        for key in ("prompt_tokens", "completion_tokens", "thought_tokens", "total_tokens"):
            row[key] = usage.get("completed_response_usage", {}).get(key)
        present = [row[k] is not None for k in ("api_calls", "prompt_tokens", "completion_tokens", "thought_tokens", "total_tokens")]
        row["usage_status"] = "complete" if all(present) else "partial" if any(present) else "unknown"
    for stage, field in (("before", "scan_before_seconds"), ("repair", "repair_seconds"),
                         ("after", "scan_after_seconds"), ("metrics", "metrics_seconds"),
                         ("structure", "structure_seconds")):
        row[field] = elapsed(records[stage])

    reasons = [f"{name}: {a['error']}" for name, a in attempts.items() if a.get("error")]
    if attempts["pretest"] and not values["pretest"].get("ready"):
        reasons.append(values["pretest"].get("reason", "Pretest did not complete"))
    for name, field, unavailable in (("safety", "safety_status", {"validator_error"}),
                                    ("semantic", "semantic_status", {"extraction_error", "unresolved_matching"})):
        if row[field] in unavailable:
            reasons.append(f"{name}: {row[field]}")
    if run.get("generation_status") in {"partial", "no_candidate"}:
        statuses = ", ".join(sorted({step["status"] for step in run.get("steps", [])}))
        reasons.append(f"generation: {run['generation_status']} ({statuses})")
    if repair and row["usage_status"] != "complete":
        reasons.append("Completed-response usage is incomplete")
    has_error = (any(a.get("status") == "error" for a in attempts.values())
                 or (bool(attempts["pretest"]) and not values["pretest"].get("ready"))
                 or row["safety_status"] == "validator_error"
                 or row["semantic_status"] in {"extraction_error", "unresolved_matching"})
    if any(a.get("status") in {"running", "interrupted"} for a in attempts.values()):
        row["run_status"] = "interrupted"
        reasons.append("Interrupted stage; recovery decision required for unfinished generation")
    elif has_error:
        row["run_status"] = "error"
    elif attempts["metrics"].get("status") == "success":
        row["run_status"] = "completed"
    elif attempts["repair"]:
        row["run_status"] = "interrupted"
        reasons.append("Saved repair awaits evaluation")
    row["reason"] = "; ".join(dict.fromkeys(reasons))
    return row


def collect_rows(output, manifest):
    return [row_for(output, manifest, document, method)
            for document in manifest["documents"] for method in document["methods"]]


def export_results(run_directory, output):
    run_directory = local_path(run_directory, "pilot", "runs")
    output = local_path(output, "exports")
    if output.suffix.lower() != ".csv":
        raise ValueError("Choose a .csv output file")
    with run_lock(run_directory, shared=True):
        manifest = read_json(run_directory / "manifest.json")
        if not manifest or manifest.get("schema_version") != 1:
            raise ValueError("Run manifest is missing or unsupported")
        rows = collect_rows(run_directory, manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    return len(rows)
