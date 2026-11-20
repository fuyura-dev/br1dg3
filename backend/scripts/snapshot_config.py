"""Capture/check the shared local configuration without browser or LLM calls."""

import argparse
import json
from pathlib import Path

from app.services.repair.configuration import fingerprint, snapshot_configuration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--output", type=Path, help="Create a new snapshot file; never overwrite an existing file.")
    group.add_argument("--check", type=Path, help="Check a saved snapshot against this environment and source.")
    args = parser.parse_args(argv)
    current = snapshot_configuration()
    if args.check:
        saved = json.loads(args.check.read_text(encoding="utf-8"))
        if (saved.get("schema_version") != 1 or "configuration" not in saved
                or saved.get("configuration_id") != fingerprint(saved["configuration"])):
            parser.exit(1, "Saved snapshot is invalid or has been modified.\n")
        if saved["configuration_id"] != current["configuration_id"]:
            parser.exit(1, "Configuration differs from the saved snapshot.\n")
        print(f"Configuration matches: {current['configuration_id']}")
    elif args.output:
        with args.output.open("x", encoding="utf-8") as destination:
            json.dump(current, destination, ensure_ascii=False, allow_nan=False, indent=2)
            destination.write("\n")
        print(f"Configuration saved: {current['configuration_id']}")
    else:
        print(json.dumps(current, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
