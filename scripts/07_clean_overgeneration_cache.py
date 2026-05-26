"""Validate and repair an existing overgeneration HF cache file."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from injection_utils import (  # noqa: E402
    read_jsonl,
    sanitize_overgeneration_clause,
    validate_overgeneration_clause,
    write_jsonl,
)


DEFAULT_CACHE = Path("data/interim/overgeneration_hf_cache.jsonl")
DEFAULT_EXAMPLES = [
    Path("data/interim/toolace_base_clean_dev500.jsonl"),
    Path("data/interim/toolace_base_clean_dev100.jsonl"),
    Path("data/interim/toolace_base_clean.jsonl"),
    Path("../all_synthetic.jsonl"),
]


def load_examples(paths: list[Path]) -> dict:
    examples = {}
    for path in paths:
        if not path.exists():
            continue
        for row in read_jsonl(path):
            row_id = row["id"]
            if row_id.endswith("_clean"):
                row_id = row_id.replace("_clean", "")
            examples[row_id] = {
                "id": row_id,
                "query": row.get("query", ""),
                "context": row.get("context", ""),
                "output": row.get("output", ""),
            }
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean overgeneration_hf_cache.jsonl in place.")
    parser.add_argument("--cache-path", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--examples", type=Path, nargs="*", default=None)
    parser.add_argument("--report-path", type=Path, default=Path("data/interim/overgeneration_cache_clean_report.json"))
    parser.add_argument("--backup", action="store_true", help="Keep .bak copy of original cache.")
    args = parser.parse_args()

    if not args.cache_path.exists():
        raise FileNotFoundError(f"Cache not found: {args.cache_path}")

    example_paths = args.examples or DEFAULT_EXAMPLES
    examples = load_examples(example_paths)
    print(f"Loaded examples for validation: {len(examples)}")

    raw_rows = read_jsonl(args.cache_path)
    print(f"Loaded cache rows: {len(raw_rows)}")

    before_issues = Counter()
    after_issues = Counter()
    source_counts = Counter()
    cleaned_rows = []
    changes = []

    for row in raw_rows:
        base_id = row["base_id"]
        original = row.get("clause") or row.get("sentence", "")
        example = examples.get(base_id, {"id": base_id, "query": "", "context": "", "output": ""})

        _ok_before, reason_before = validate_overgeneration_clause(original, example)
        if not _ok_before:
            before_issues[reason_before] += 1

        cleaned, source = sanitize_overgeneration_clause(original, example)
        _ok_after, reason_after = validate_overgeneration_clause(cleaned, example)
        if not _ok_after:
            after_issues[reason_after] += 1

        source_counts[source] += 1
        if cleaned != original:
            changes.append(
                {
                    "base_id": base_id,
                    "before": original,
                    "after": cleaned,
                    "source": source,
                    "reason_before": reason_before,
                }
            )

        cleaned_rows.append(
            {
                "base_id": base_id,
                "clause": cleaned,
                "model": row.get("model"),
                "source": source,
            }
        )

    if args.backup:
        backup_path = args.cache_path.with_suffix(args.cache_path.suffix + ".bak")
        backup_path.write_text(args.cache_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup saved to: {backup_path}")

    write_jsonl(args.cache_path, cleaned_rows)

    report = {
        "rows": len(cleaned_rows),
        "changed": len(changes),
        "before_issues": dict(before_issues),
        "after_issues": dict(after_issues),
        "source_counts": dict(source_counts),
        "sample_changes": changes[:30],
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    with args.report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nCleaned cache written to: {args.cache_path}")
    print(f"Report written to: {args.report_path}")
    print(f"Changed rows: {len(changes)} / {len(cleaned_rows)}")
    print("Before issues:", dict(before_issues.most_common()))
    print("After issues:", dict(after_issues.most_common()))
    print("Sources:", dict(source_counts))


if __name__ == "__main__":
    main()
