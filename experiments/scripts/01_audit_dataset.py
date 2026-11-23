"""Check original HTML files against a reference and write an audit CSV."""

import argparse
import csv
import hashlib
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

AUDIT_ROOT = Path(__file__).resolve().parents[1] / "local" / "audit"
ERROR_TEXT = re.compile(
    r"access denied|forbidden|request rejected|request blocked|403 error|bad request|"
    r"not found|cannot be found|unknown error|error id|request unsuccessful|blocked|"
    r"robot|unsupported region|not (?:yet )?available in your|unavailable in this|"
    r"technical difficulties|abusive automated request|no longer support subscriptions",
    re.IGNORECASE,
)


def read_file(path):
    try:
        return path.read_bytes(), ""
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def inspect_content(data):
    soup = BeautifulSoup(data, "html.parser")
    title_tag = soup.select_one("head title")
    title = title_tag.get_text(" ", strip=True) if title_tag else ""
    flags = []
    if soup.contains_replacement_characters:
        flags.append("decoding_warning")
    for tag in soup.find_all(["head", "script", "style", "template"]):
        if tag.parent is not None:
            tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    if ERROR_TEXT.search(title + " " + text[:2000]):
        flags.append("possible_error_page")
    if len(text) < 100:
        flags.append("little_text")
    if len(data) < 100:
        flags.append("small_file")
    if b"\x00" in data:
        flags.append("nul_byte")
    return title, len(text), text[:500], flags


def audit_dataset(originals, reference_originals, ground_truth, output, source="scraped_sites"):
    originals, reference_originals, ground_truth, output = (
        Path(p).resolve() for p in (originals, reference_originals, ground_truth, output)
    )
    if not originals.is_dir() or not reference_originals.is_dir():
        raise ValueError("Original and reference directories must exist")
    if output.exists() or any(output.is_relative_to(p) for p in (originals, reference_originals)):
        raise ValueError("Choose a new output directory outside the input directories")
    with ground_truth.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not {"filename", "source"}.issubset(reader.fieldnames or []):
            raise ValueError("Ground truth must contain filename and source columns")
        expected = {row["filename"] for row in reader if row["source"] == source}
    if not expected:
        raise ValueError(f"No filenames found for source {source!r}")
    if any(not name or name in {".", ".."} or "/" in name or "\\" in name for name in expected):
        raise ValueError("Ground truth must contain plain filenames")

    actual = {p.name for p in originals.iterdir()}
    rows = []
    for name in sorted(expected | actual):
        data, error = read_file(originals / name)
        reference, reference_error = read_file(reference_originals / name) if name in expected else (None, "")
        digest = hashlib.sha256(data).hexdigest() if data is not None else None
        reference_digest = hashlib.sha256(reference).hexdigest() if reference is not None else None
        title, text_chars, excerpt, flags = inspect_content(data) if data is not None else ("", None, "", [])
        if name not in expected:
            flags.append("unexpected_file")
        if error:
            flags.append("file_read_error")
        if reference_error:
            flags.append("reference_read_error")
        match = digest == reference_digest if data is not None and reference is not None else None
        if match is False:
            flags.append("reference_mismatch")
        rows.append(
            {
                "filename": name,
                "expected": name in expected,
                "size_bytes": len(data) if data is not None else None,
                "sha256": digest,
                "reference_sha256": reference_digest,
                "reference_match": match,
                "duplicate_group": "",
                "title": title,
                "text_chars": text_chars,
                "text_excerpt": excerpt,
                "flags": ";".join(flags),
                "file_error": error,
                "reference_error": reference_error,
            }
        )
    hashes = Counter(row["sha256"] for row in rows if row["expected"] and row["sha256"] is not None)
    for row in rows:
        if row["expected"] and hashes[row["sha256"]] > 1:
            row["duplicate_group"] = row["sha256"]

    output.mkdir(parents=True, exist_ok=False)
    with (output / "inventory.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"Expected: {len(expected)} | Found entries: {len(actual)} | Missing: {len(expected - actual)} | Extra: {len(actual - expected)}"
    )
    print(
        f"Matching reference hashes: {sum(row['reference_match'] is True for row in rows)} | Distinct contents: {len(hashes)} | Duplicate groups: {sum(count > 1 for count in hashes.values())}"
    )
    print(f"Content/integrity flags: {sum(bool(row['flags']) for row in rows)} | CSV: {output / 'inventory.csv'}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--reference-originals", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--source", default="scraped_sites")
    parser.add_argument("--output", type=Path, required=True, help="New directory under experiments/local/audit/")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(AUDIT_ROOT.resolve()):
        parser.error("Output must be under experiments/local/audit/")
    try:
        audit_dataset(args.originals, args.reference_originals, args.ground_truth, args.output, args.source)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Audit could not complete: {exc}\n")


if __name__ == "__main__":
    main()
