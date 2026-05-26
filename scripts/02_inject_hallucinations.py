import argparse
import random
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from injection_utils import (  # noqa: E402
    build_conflict_dataset,
    build_overgeneration_sentences,
    get_entity_replacements,
    inject_missing_tool,
    inject_overgeneration,
    load_overgeneration_cache,
    make_clean,
    read_jsonl,
    write_jsonl,
)


DEFAULT_INPUT = Path("data/interim/toolace_base_clean_dev500.jsonl")
DEFAULT_OUT_DIR = Path("data/processed")
DEFAULT_OVERGEN_CACHE = Path("data/interim/overgeneration_hf_cache.jsonl")

SEED = 42
N_PER_DATASET = 300


def filter_examples(examples):
    return [
        ex
        for ex in examples
        if 20 <= len(ex.get("output", "")) <= 3000
        and 20 <= len(ex.get("context", "")) <= 5000
    ]


def print_preview(name: str, rows, n: int = 2) -> None:
    print(f"\n{name} preview:")
    for row in rows[:n]:
        print("=" * 80)
        print("ID:", row["id"])
        print("QUERY:", row["query"][:300])
        print("CONTEXT:", row["context"][:300])
        print("OUTPUT:", row["output"][:700])
        print("LABELS:", row["hallucination_labels"])
        if row.get("corruption_types"):
            print("CORRUPTION:", row["corruption_types"])


def summarize_conflicts(conflict_rows) -> None:
    corruption_counts = Counter()
    span_counts = Counter()
    for row in conflict_rows:
        span_counts[len(row.get("hallucination_labels", []))] += 1
        for ctype in row.get("corruption_types", []):
            corruption_counts[ctype] += 1
    print("\nConflict corruption types:", dict(corruption_counts))
    print("Conflict span counts:", dict(span_counts))


def main():
    parser = argparse.ArgumentParser(description="Inject synthetic hallucinations into ToolACE examples.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--n-per-dataset", type=int, default=N_PER_DATASET)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--max-conflict-spans",
        type=int,
        default=1,
        help="Max non-overlapping factual corruptions per conflict example (1 or 2).",
    )
    parser.add_argument(
        "--multi-conflict-rate",
        type=float,
        default=0.15,
        help="Fraction of conflict examples that receive 2 corruptions when possible.",
    )
    parser.add_argument(
        "--use-llm-overgeneration",
        action="store_true",
        help="Call OpenAI API for examples missing from the cache.",
    )
    parser.add_argument(
        "--overgeneration-cache",
        type=Path,
        default=DEFAULT_OVERGEN_CACHE,
        help="Pre-generated cache (run 06_pregenerate_overgeneration_hf.py first).",
    )
    parser.add_argument(
        "--entity-replacements",
        type=Path,
        default=None,
        help="Optional entity replacement JSON (default: data/interim/entity_replacements.json).",
    )
    parser.add_argument(
        "--word-conflict-target",
        type=int,
        default=60,
        help="Target number of word-based conflict examples (dedicated first pass).",
    )
    args = parser.parse_args()

    random.seed(args.seed)

    entity_map = get_entity_replacements(args.entity_replacements)
    print(f"Entity replacements loaded: {len(entity_map)} entries")

    if not args.input.exists():
        raise FileNotFoundError(
            f"Input file not found: {args.input}. Run scripts/01c_make_dev_sample.py first."
        )

    examples = filter_examples(read_jsonl(args.input))
    print(f"Loaded examples: {len(examples)}")

    random.shuffle(examples)
    pool = examples[: max(args.n_per_dataset * 2, args.n_per_dataset)]

    clean = [make_clean(ex) for ex in pool[: args.n_per_dataset]]

    conflict = build_conflict_dataset(
        examples=examples,
        n_target=args.n_per_dataset,
        word_target=args.word_conflict_target,
        max_conflict_spans=args.max_conflict_spans,
        multi_conflict_rate=args.multi_conflict_rate,
    )
    if len(conflict) < args.n_per_dataset:
        print(
            f"Warning: only {len(conflict)} conflict examples created "
            f"(target {args.n_per_dataset}). Add more base examples or relax filters."
        )

    overgen_source = pool[: args.n_per_dataset]
    overgen_cache = load_overgeneration_cache(args.overgeneration_cache)
    if args.use_llm_overgeneration:
        overgen_cache = build_overgeneration_sentences(
            overgen_source,
            cache_path=args.overgeneration_cache,
            use_llm=True,
        )

    overgeneration = [
        inject_overgeneration(ex, clause=overgen_cache.get(ex["id"]))
        for ex in overgen_source
    ]

    missing_tool = [inject_missing_tool(ex) for ex in pool[: args.n_per_dataset]]

    print("\nCreated datasets:")
    print(f"Clean:          {len(clean)}")
    print(f"Conflict:       {len(conflict)}")
    print(f"Overgeneration: {len(overgeneration)}")
    print(f"Missing tool:   {len(missing_tool)}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "clean.jsonl", clean)
    write_jsonl(args.out_dir / "conflict.jsonl", conflict)
    write_jsonl(args.out_dir / "overgeneration.jsonl", overgeneration)
    write_jsonl(args.out_dir / "missing_tool.jsonl", missing_tool)

    all_rows = clean + conflict + overgeneration + missing_tool
    write_jsonl(args.out_dir / "all_synthetic.jsonl", all_rows)

    log_path = args.out_dir / "conflict_replacements.txt"
    with log_path.open("w", encoding="utf-8") as f:
        for row in conflict:
            ctypes = row.get("corruption_types", [])
            for i, label in enumerate(row.get("hallucination_labels", [])):
                ctype = ctypes[i] if i < len(ctypes) else "?"
                original = label.get("original_value", "?")
                replacement = label["text"]
                f.write(f"{row['id']}\t{ctype}\t{original} -> {replacement}\n")

    print(f"\nSaved files to: {args.out_dir}")
    print(f"Replacement log: {log_path}")
    summarize_conflicts(conflict)
    print_preview("Conflict", conflict)
    print_preview("Overgeneration", overgeneration)
    print_preview("Missing tool", missing_tool)


if __name__ == "__main__":
    main()
