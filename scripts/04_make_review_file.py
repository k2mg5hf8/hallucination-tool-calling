import json
import random
from pathlib import Path


DATA_DIR = Path("data/processed")
OUT_PATH = Path("reports/manual_review_processed.md")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

SEED = 42
N_PER_DATASET = 10


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    random.seed(SEED)

    files = [
        "clean.jsonl",
        "conflict.jsonl",
        "overgeneration.jsonl",
        "missing_tool.jsonl",
    ]

    with OUT_PATH.open("w", encoding="utf-8") as f:
        f.write("# Manual Review Sample\n\n")

        for filename in files:
            path = DATA_DIR / filename
            examples = list(read_jsonl(path))
            sample = random.sample(examples, min(N_PER_DATASET, len(examples)))

            f.write(f"# Dataset: {filename}\n\n")

            for i, ex in enumerate(sample, 1):
                f.write(f"## Example {i}: `{ex['id']}`\n\n")

                f.write("### Query\n\n")
                f.write(ex["query"][:1500] + "\n\n")

                f.write("### Context\n\n")
                f.write("```text\n")
                f.write(ex["context"][:1500] + "\n")
                f.write("```\n\n")

                f.write("### Output\n\n")
                f.write(ex["output"][:2000] + "\n\n")

                f.write("### Labels\n\n")
                f.write("```json\n")
                f.write(json.dumps(ex.get("hallucination_labels", []), ensure_ascii=False, indent=2))
                f.write("\n```\n\n")

                for label in ex.get("hallucination_labels", []):
                    start = label["start"]
                    end = label["end"]
                    f.write(f"Marked span: `{ex['output'][start:end]}`\n\n")

                f.write("---\n\n")

    print(f"Saved review file to {OUT_PATH}")


if __name__ == "__main__":
    main()