import json
import random
from pathlib import Path


INPUT_PATH = Path("data/interim/toolace_base_clean.jsonl")
OUT_PATH = Path("data/interim/toolace_base_clean_dev500.jsonl")

SEED = 42
N = 500


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    random.seed(SEED)

    examples = list(read_jsonl(INPUT_PATH))
    print(f"Loaded examples: {len(examples)}")

    filtered = [
        ex for ex in examples
        if 20 <= len(ex["output"]) <= 3000
        and 20 <= len(ex["context"]) <= 5000
    ]

    print(f"After filtering: {len(filtered)}")

    sample = random.sample(filtered, min(N, len(filtered)))

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for ex in sample:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Saved dev sample: {OUT_PATH}")


if __name__ == "__main__":
    main()