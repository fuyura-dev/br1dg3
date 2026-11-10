"""Measure unpruned TED on saved HTML; optionally compare the legacy pruned metric."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from app.services.validation.structure import (
    calculate_legacy_pruned_structural_preservation,
    calculate_structural_preservation,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path, help="Original HTML file (UTF-8).")
    parser.add_argument("repaired", type=Path, help="Repaired HTML file (UTF-8).")
    parser.add_argument(
        "--compare-pruned",
        action="store_true",
        help="Also measure the legacy pruned metric. Off by default; comparison only.",
    )
    args = parser.parse_args(argv)

    try:
        original = args.original.read_text(encoding="utf-8")
        repaired = args.repaired.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        parser.error(str(exc))

    methods = {"unpruned": calculate_structural_preservation}
    if args.compare_pruned:
        methods["legacy_pruned"] = calculate_legacy_pruned_structural_preservation

    results = {}
    for name, calculate in methods.items():
        start = perf_counter()
        result = calculate(original, repaired)
        elapsed = perf_counter() - start
        results[name] = {**result.to_dict(), "elapsed_seconds": elapsed}

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
