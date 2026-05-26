"""Collect entity candidates from extracted ToolACE examples."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from entity_collection import build_entity_report, save_entity_report  # noqa: E402
from injection_utils import read_jsonl  # noqa: E402


DEFAULT_INPUT = Path("data/interim/toolace_base_clean.jsonl")
DEFAULT_OUT_DIR = Path("data/interim")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect corruptible entity candidates from ToolACE extracted examples."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Extracted examples JSONL (from 01_extract_base_examples.py).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for entity_replacements.json and stats files.",
    )
    parser.add_argument(
        "--min-both-freq",
        type=int,
        default=2,
        help="Minimum co-occurrence in output+context to consider an entity corruptible.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=100,
        help="How many top entities to include in the report.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(
            f"Input not found: {args.input}. Run scripts/01_extract_base_examples.py first."
        )

    examples = read_jsonl(args.input)
    print(f"Loaded examples: {len(examples)}")

    report = build_entity_report(
        examples,
        min_both_freq=args.min_both_freq,
        top_k=args.top_k,
    )
    report["summary"]["num_examples"] = len(examples)

    print("\nSummary:")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")

    print("\nTop corruptible entities:")
    for row in report["top_entities"][:15]:
        if row["both_freq"] < args.min_both_freq:
            continue
        repl = row.get("replacement") or "-"
        print(
            f"  {row['entity']!r:30} both={row['both_freq']:3d} "
            f"bucket={row['bucket']:<12} -> {repl}"
        )

    save_entity_report(report, args.out_dir)


if __name__ == "__main__":
    main()
