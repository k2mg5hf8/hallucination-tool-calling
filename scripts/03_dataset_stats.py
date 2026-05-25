import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


DATA_DIR = Path("data/processed")
RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = {
    "clean": DATA_DIR / "clean.jsonl",
    "conflict": DATA_DIR / "conflict.jsonl",
    "overgeneration": DATA_DIR / "overgeneration.jsonl",
    "missing_tool": DATA_DIR / "missing_tool.jsonl",
}


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def get_span_lengths(example: dict) -> list[int]:
    return [
        label["end"] - label["start"]
        for label in example.get("hallucination_labels", [])
    ]


def analyze_dataset(name: str, path: Path) -> dict:
    examples = list(read_jsonl(path))

    output_lengths = [len(ex["output"]) for ex in examples]
    context_lengths = [len(ex["context"]) for ex in examples]
    label_counts = [len(ex.get("hallucination_labels", [])) for ex in examples]

    span_lengths = []
    for ex in examples:
        span_lengths.extend(get_span_lengths(ex))

    return {
        "dataset": name,
        "rows": len(examples),
        "avg_context_chars": round(sum(context_lengths) / len(context_lengths), 2),
        "avg_output_chars": round(sum(output_lengths) / len(output_lengths), 2),
        "examples_with_labels": sum(1 for c in label_counts if c > 0),
        "avg_labels_per_example": round(sum(label_counts) / len(label_counts), 2),
        "avg_span_chars": round(sum(span_lengths) / len(span_lengths), 2) if span_lengths else 0,
    }


def save_overview_plot(df: pd.DataFrame, output_path: Path) -> None:
    plot_df = df[df["dataset"] != "all"].copy()

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.bar(plot_df["dataset"], plot_df["rows"])
    ax.set_title("Synthetic Tool-Calling Hallucination Dataset")
    ax.set_xlabel("Dataset split")
    ax.set_ylabel("Number of examples")

    for idx, row in plot_df.iterrows():
        ax.text(
            row["dataset"],
            row["rows"] + 5,
            str(row["rows"]),
            ha="center",
            va="bottom",
            fontsize=9,
        )

    plt.xticks(rotation=20)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def main():
    rows = []

    for name, path in DATASETS.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing dataset file: {path}")

        rows.append(analyze_dataset(name, path))

    df = pd.DataFrame(rows)

    total_row = {
        "dataset": "all",
        "rows": int(df["rows"].sum()),
        "avg_context_chars": round(df["avg_context_chars"].mean(), 2),
        "avg_output_chars": round(df["avg_output_chars"].mean(), 2),
        "examples_with_labels": int(df["examples_with_labels"].sum()),
        "avg_labels_per_example": round(df["avg_labels_per_example"].mean(), 2),
        "avg_span_chars": round(
            df[df["avg_span_chars"] > 0]["avg_span_chars"].mean(),
            2,
        ),
    }

    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

    csv_path = RESULTS_DIR / "dataset_stats.csv"
    plot_path = RESULTS_DIR / "dataset_overview.png"

    df.to_csv(csv_path, index=False)
    save_overview_plot(df, plot_path)

    print(f"Saved dataset statistics to: {csv_path}")
    print(f"Saved dataset overview plot to: {plot_path}")


if __name__ == "__main__":
    main()