from datasets import load_dataset
from pathlib import Path
import json
from pprint import pprint


OUT_DIR = Path("data/raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def to_jsonable(x):
    try:
        json.dumps(x)
        return x
    except TypeError:
        return str(x)


def main():
    print("Loading ToolACE...")
    ds = load_dataset("Team-ACE/ToolACE", split="train")

    print("\nDataset object:")
    print(ds)

    print("\nColumn names:")
    print(ds.column_names)

    print("\nNumber of rows:")
    print(len(ds))

    print("\nFirst row keys and types:")
    row = ds[0]
    for k, v in row.items():
        print(f"- {k}: {type(v)}")

    print("\nFirst row preview:")
    pprint(row)

    out_path = OUT_DIR / "toolace_head.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for i in range(min(20, len(ds))):
            record = {k: to_jsonable(v) for k, v in ds[i].items()}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nSaved first 20 rows to: {out_path}")


if __name__ == "__main__":
    main()