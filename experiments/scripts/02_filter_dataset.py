"""Check candidate HTML with the backend and copy it into technical-result groups."""

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from bs4 import UnicodeDammit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_ROOT = PROJECT_ROOT / "experiments" / "local"
OUTPUT_GROUPS = {"passed": "passed", "not_passed": "not-passed", "needs_review": "needs-review"}
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.detection.detect import _get_driver, scan_with_report
from app.services.validation.semantic import _extract as extract_sdg


def check_html(filename, data):
    row = {
        "filename": filename,
        "sha256": hashlib.sha256(data).hexdigest(),
        "encoding": "",
        "status": "needs_review",
        "reason": "",
        "content_review": "pending",
        "scan_status": "not_run",
        "stylesheet_warnings": "",
        "selected_violations": None,
        "distinct_rules": None,
        "mapped_violations": None,
        "unmapped_violations": None,
        "sdg_status": "not_run",
        "original_sdg_edges": None,
        "semantic_applicability": "unknown",
        "error": "",
    }
    evidence = {"filename": filename, "sha256": row["sha256"], "scan": None, "sdg": None}
    if not data.strip():
        row.update(status="not_passed", reason="Empty HTML snapshot.")
        return row, evidence

    decoded = UnicodeDammit(data, is_html=True)
    row["encoding"] = decoded.original_encoding or ""
    if decoded.unicode_markup is None or decoded.contains_replacement_characters:
        row["reason"] = "HTML decoding needs review; no scan was attempted."
        return row, evidence
    html = decoded.unicode_markup

    try:
        scan = scan_with_report(html)
    except Exception as exc:  # noqa: BLE001 - keep scan failure distinct from zero violations
        row.update(scan_status="error", reason="Axe scan failed; eligibility is unresolved.",
                   error=f"{type(exc).__name__}: {exc}")
        return row, evidence

    evidence["scan"] = scan.report
    row["stylesheet_warnings"] = "; ".join(
        f"{warning['status']}: {warning['href']}"
        for warning in scan.report.get("stylesheet_warnings", [])
    )
    count = sum(len(v["nodes"]) for v in scan.violations)
    row.update(scan_status="success", selected_violations=count,
               distinct_rules=len({v["id"] for v in scan.violations}))
    if count == 0:
        row.update(status="not_passed", reason="No accessibility violations detected by the configured checks.")
        return row, evidence

    try:
        builder, edges = extract_sdg(html)
    except Exception as exc:  # noqa: BLE001 - an extraction failure is not zero edges
        row.update(sdg_status="error", reason="SDG extraction failed; mapping and semantic applicability are unresolved.",
                   error=f"{type(exc).__name__}: {exc}")
        return row, evidence
    row.update(sdg_status="success", original_sdg_edges=len(edges),
               semantic_applicability="applicable" if edges else "not_applicable")

    try:
        # Use the same target selection and annotation as the repair pipeline.
        builder.violations = scan.violations
        builder._mark_violations()
        mapped = sum(len(node["issues"]) for _, node in builder.graph.nodes(data=True))
        evidence["sdg"] = builder.to_dict()
    except Exception as exc:  # noqa: BLE001 - retain the successful scan and edge measurement
        row.update(reason="Affected-element mapping failed; eligibility is unresolved.",
                   error=f"{type(exc).__name__}: {exc}")
        return row, evidence

    row.update(mapped_violations=mapped, unmapped_violations=count - mapped)
    if mapped != count:
        row.update(status="not_passed", reason="Not all detected violation targets could be identified in the saved HTML.")
    else:
        row.update(status="passed", reason="Selected violations found and all affected elements mapped.")
    return row, evidence


def filter_dataset(input_dir, output):
    input_dir, output = Path(input_dir).resolve(), Path(output).resolve()
    if not input_dir.is_dir():
        raise ValueError("Input must be a directory containing candidate HTML files")
    if output.is_relative_to(input_dir) or input_dir.is_relative_to(output):
        raise ValueError("Input and output directories must be separate")
    files = sorted(input_dir.iterdir())
    if not files or any(not p.is_file() or p.is_symlink() or p.suffix.lower() != ".html" for p in files):
        raise ValueError("Input must contain only HTML files, with no subfolders or symlinks")
    if output.exists() and (not output.is_dir() or any(
        p.name not in OUTPUT_GROUPS.values() or p.is_symlink() or not p.is_dir() or any(p.iterdir())
        for p in output.iterdir()
    )):
        raise ValueError("Choose a fresh output directory or one containing only empty result folders")

    print("Checking browser availability...", flush=True)
    driver = _get_driver()
    driver.quit()
    output.mkdir(parents=True, exist_ok=True)
    for group in OUTPUT_GROUPS.values():
        (output / group).mkdir(exist_ok=True)

    counts = Counter()
    with (output / "results.csv").open("x", newline="", encoding="utf-8") as csv_file, (
        output / "scan-results.jsonl"
    ).open("x", encoding="utf-8") as evidence_file:
        writer = None
        for index, path in enumerate(files, 1):
            print(f"[{index}/{len(files)}] {path.name}", flush=True)
            data = path.read_bytes()
            row, evidence = check_html(path.name, data)
            group = OUTPUT_GROUPS[row["status"]]
            target = output / group / path.name
            shutil.copy2(path, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"Copy differs from the assessed input: {path.name}")
            if writer is None:
                writer = csv.DictWriter(csv_file, fieldnames=row.keys())
                writer.writeheader()
            evidence["result"] = row
            evidence_file.write(json.dumps(evidence, ensure_ascii=False) + "\n")
            evidence_file.flush()
            writer.writerow(row)
            csv_file.flush()
            counts[row["status"]] += 1

    print(f"Checked: {len(files)} | Passed: {counts['passed']} | Not passed: {counts['not_passed']} | Needs review: {counts['needs_review']}")
    print(f"Results: {output / 'results.csv'}")
    print("Passed means the automated checks passed; content review remains pending.")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Candidate HTML directory")
    parser.add_argument("--output", type=Path, required=True, help="Fresh directory under experiments/local/")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(LOCAL_ROOT.resolve()):
        parser.error("Output must be under experiments/local/")
    try:
        filter_dataset(args.input, args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Filter could not complete: {exc}\n")


if __name__ == "__main__":
    main()
