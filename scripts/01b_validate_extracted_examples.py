import json
import random
from pathlib import Path


INPUT_PATH = Path("data/interim/toolace_base_clean.jsonl")
OUT_PATH = Path("data/interim/manual_review_sample.md")


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    examples = list(read_jsonl(INPUT_PATH))
    print(f"Loaded examples: {len(examples)}")

    if not examples:
        print("No examples found. Run scripts/01_extract_base_examples.py first.")
        return

    output_lengths = [len(ex["output"]) for ex in examples]
    context_lengths = [len(ex["context"]) for ex in examples]

    print("\nBasic stats:")
    print(f"Avg context length: {sum(context_lengths) / len(context_lengths):.1f}")
    print(f"Avg output length: {sum(output_lengths) / len(output_lengths):.1f}")
    print(f"Min output length: {min(output_lengths)}")
    print(f"Max output length: {max(output_lengths)}")

    print("\nFirst example:")
    print(json.dumps(examples[0], ensure_ascii=False, indent=2)[:4000])

    sample = random.sample(examples, min(20, len(examples)))

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for idx, ex in enumerate(sample, 1):
            f.write(f"# Example {idx}\n\n")
            f.write(f"**ID:** `{ex['id']}`\n\n")
            f.write("## Query\n\n")
            f.write(ex["query"] + "\n\n")
            f.write("## Tool call\n\n")
            f.write("```text\n")
            f.write(ex.get("tool_call", "") + "\n")
            f.write("```\n\n")
            f.write("## Context / Tool output\n\n")
            f.write("```text\n")
            f.write(ex["context"][:3000] + "\n")
            f.write("```\n\n")
            f.write("## Assistant output\n\n")
            f.write(ex["output"][:3000] + "\n\n")
            f.write("---\n\n")

    print(f"\nSaved manual review sample to: {OUT_PATH}")


if __name__ == "__main__":
    main()