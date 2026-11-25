"""Count prepared HTML tokens with Gemini and copy eligible files by token budget."""

import argparse
import csv
import hashlib
import shutil
import sys
from collections import Counter
from pathlib import Path

import httpx
from bs4 import UnicodeDammit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_ROOT = PROJECT_ROOT / "experiments" / "local"
TOKEN_LIMIT = 60_000
OUTPUT_GROUPS = {"passed": "passed", "not_passed": "not-passed", "needs_review": "needs-review"}
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import settings
from app.services.detection.preprocess import preprocess


def count_tokens(client, model, html):
    response = client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:countTokens",
        json={"contents": [{"role": "user", "parts": [{"text": html}]}]},
    )
    response.raise_for_status()
    count = response.json().get("totalTokens")
    if type(count) is not int or count < 0:
        raise ValueError("Gemini did not return a nonnegative integer totalTokens")
    return count


def check_html(eligibility, data, client, model):
    row = {**eligibility, "status": "needs_review", "reason": "", "error": "",
           "prepared_tokens": None, "count_model": model, "token_limit": TOKEN_LIMIT,
           "exclusion_operator": ">", "prepared_sha256": ""}
    stage = "HTML preparation"
    try:
        decoded = UnicodeDammit(data, is_html=True)
        row["encoding"] = decoded.original_encoding or ""
        if decoded.unicode_markup is None or decoded.contains_replacement_characters:
            row["reason"] = "HTML decoding needs review; tokens were not counted."
            return row
        prepared = preprocess(decoded.unicode_markup)
        row["prepared_sha256"] = hashlib.sha256(prepared.encode("utf-8")).hexdigest()
        stage = "Token counting"
        count = count_tokens(client, model, prepared)
        row["prepared_tokens"] = count
        if count > TOKEN_LIMIT:
            row.update(status="not_passed", reason="Prepared HTML exceeds the 60,000-token limit.")
        else:
            row.update(status="passed", reason="Prepared HTML is within the 60,000-token limit.")
    except Exception as exc:  # noqa: BLE001 - unknown counts remain unresolved
        row.update(reason=f"{stage} failed; token eligibility is unresolved.",
                   error=f"{type(exc).__name__}: {exc}")
    return row


def load_inputs(dataset):
    with (dataset / "results.csv").open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"filename", "sha256", "status", "original_sdg_edges"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Dataset report is missing required eligibility columns")
        rows = list(reader)
    if len({row["filename"] for row in rows}) != len(rows):
        raise ValueError("Dataset report contains duplicate filenames")
    passed = [row for row in rows if row["status"] == "passed"]
    if not passed:
        raise ValueError("Dataset report has no passing files")
    folder = dataset / "passed"
    if {p.name for p in folder.iterdir()} != {row["filename"] for row in passed}:
        raise ValueError("Passed folder does not match the eligibility report")
    for row in passed:
        name = row["filename"]
        path = folder / name
        if (Path(name).name != name or path.suffix.lower() != ".html"
                or path.is_symlink() or not path.is_file()):
            raise ValueError(f"Expected an ordinary HTML file: {name}")
    return sorted(passed, key=lambda row: row["filename"])


def filter_dataset(dataset, output, client, model):
    dataset, output = Path(dataset).resolve(), Path(output).resolve()
    if output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise ValueError("Dataset and output directories must be separate")
    if output.exists():
        raise ValueError("Choose a fresh output directory")
    rows = load_inputs(dataset)
    output.mkdir(parents=True, exist_ok=False)
    for folder in OUTPUT_GROUPS.values():
        (output / folder).mkdir()

    counts = Counter()
    with (output / "results.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = None
        for index, eligibility in enumerate(rows, 1):
            name = eligibility["filename"]
            print(f"[{index}/{len(rows)}] {name}", flush=True)
            path = dataset / "passed" / name
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != eligibility["sha256"]:
                raise ValueError(f"Input differs from the eligibility report: {name}")
            row = check_html(eligibility, data, client, model)
            target = output / OUTPUT_GROUPS[row["status"]] / name
            shutil.copy2(path, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"Copy differs from the counted input: {name}")
            if writer is None:
                writer = csv.DictWriter(stream, fieldnames=row.keys())
                writer.writeheader()
            writer.writerow(row)
            stream.flush()
            counts[row["status"]] += 1

    print(f"Checked: {len(rows)} | Passed: {counts['passed']} | Not passed: {counts['not_passed']} | Needs review: {counts['needs_review']}")
    print(f"Results: {output / 'results.csv'}")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Eligibility directory containing passed/ and results.csv")
    parser.add_argument("--output", type=Path, required=True, help="Fresh directory under experiments/local/")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(LOCAL_ROOT.resolve()):
        parser.error("Output must be under experiments/local/")
    if not settings.LLM_API_KEY or not settings.LLM_MODEL:
        parser.error("Set LLM_API_KEY and LLM_MODEL in backend/.env")
    model = settings.LLM_MODEL.removeprefix("models/")
    print(f"Model: {model} | Keep <= {TOKEN_LIMIT:,} tokens; exclude > {TOKEN_LIMIT:,}", flush=True)
    try:
        with httpx.Client(timeout=60, headers={"x-goog-api-key": settings.LLM_API_KEY}) as client:
            filter_dataset(args.dataset, args.output, client, model)
    except KeyboardInterrupt:
        parser.exit(130, "Stopped; completed results are saved. Use a fresh output directory for a rerun.\n")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Token filter could not complete: {exc}\n")


if __name__ == "__main__":
    main()
