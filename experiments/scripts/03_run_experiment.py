"""Prepare or execute a paired experiment using the accepted dataset."""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.execution import execute_run, prepare_run
from experiments.export import collect_rows
from experiments.records import ExecutionStopped, RecordingError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, help="Eligibility directory containing passed/ and results.csv")
    parser.add_argument("--inventory", type=Path, help="Original audit inventory.csv")
    parser.add_argument("--output", type=Path, help="New directory under experiments/local/pilot/ or runs/")
    parser.add_argument("--documents", nargs="+", type=int, help="Original inventory document numbers; defaults to all accepted files")
    parser.add_argument("--prepare-only", action="store_true", help="Save the manifest and inputs without scans or model calls")
    parser.add_argument("--resume", type=Path, help="Continue an existing run without repeating completed generation")
    parser.add_argument("--batch-size", type=int, help="Process at most this many pending documents, with both methods; omit for all remaining")
    args = parser.parse_args()
    if args.batch_size is not None and args.batch_size < 1:
        parser.error("--batch-size must be a positive document count")
    if args.batch_size is not None and args.prepare_only:
        parser.error("--batch-size applies to execution; omit it with --prepare-only")
    if args.resume:
        if any((args.dataset, args.inventory, args.output, args.documents, args.prepare_only)):
            parser.error("Use --resume alone or with --batch-size")
        output = args.resume
    else:
        if not all((args.dataset, args.inventory, args.output)):
            parser.error("A new run requires --dataset, --inventory, and --output")
        output = args.output
    try:
        if not args.resume:
            manifest = prepare_run(args.dataset, args.inventory, output, args.documents)
            print(f"Prepared {len(manifest['documents'])} documents: {output}", flush=True)
            if args.prepare_only:
                return
        manifest = execute_run(output, batch_size=args.batch_size)
        counts = Counter(row["run_status"] for row in collect_rows(output, manifest))
        print("Results: " + " | ".join(f"{key}: {value}" for key, value in sorted(counts.items())))
        print(f"Run records: {output}")
        if counts["error"] or counts["interrupted"]:
            parser.exit(1, "Some records need review; saved evidence is retained.\n")
    except KeyboardInterrupt:
        parser.exit(130, "Stopped; saved stages are retained.\n")
    except (OSError, ValueError, KeyError, RecordingError, ExecutionStopped) as exc:
        parser.exit(1, f"Experiment could not continue: {exc}\n")


if __name__ == "__main__":
    main()
