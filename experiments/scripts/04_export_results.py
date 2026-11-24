"""Export the raw measurements from saved paired experiment records."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.export import export_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="Saved pilot or experiment run directory")
    parser.add_argument("--output", type=Path, required=True, help="New CSV under experiments/local/exports/")
    args = parser.parse_args()
    try:
        count = export_results(args.run, args.output)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Export could not complete: {exc}\n")
    print(f"Exported {count} rows: {args.output}")


if __name__ == "__main__":
    main()
