import copy
import json
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


INPUT_PATH = Path("data/interim/toolace_base_clean_dev500.jsonl")
OUT_DIR = Path("data/processed")

SEED = 42
N_PER_DATASET = 300

OUT_DIR.mkdir(parents=True, exist_ok=True)


NUM_RE = re.compile(r"(?<![\w])[$€£]?[+-]?\d[\d,]*(?:\.\d+)?%?(?![\w])")


WORD_REPLACEMENTS = {
    "sunny": "rainy",
    "rainy": "sunny",
    "cloudy": "sunny",
    "available": "unavailable",
    "unavailable": "available",
    "open": "closed",
    "closed": "open",
    "active": "inactive",
    "inactive": "active",
    "approved": "rejected",
    "rejected": "approved",
    "success": "failure",
    "true": "false",
    "false": "true",
    "yes": "no",
    "no": "yes",
}


OVERGENERATION_SENTENCES = [
    "This trend has remained stable over the past few months.",
    "Experts expect this result to improve significantly next month.",
    "This is considered one of the best options currently available.",
    "The situation is likely to become even more favorable soon.",
    "Users have reported consistently positive outcomes with this option.",
    "This result is also supported by recent independent analysis.",
]


MISSING_TOOL_SENTENCES = [
    "Would you like me to book a flight for you based on this information?",
    "Would you like me to purchase this item for you now?",
    "Would you like me to send this information to your email?",
    "Would you like me to schedule a meeting about this?",
    "Would you like me to reserve a hotel for you?",
    "Would you like me to place an order using your account?",
]


def read_jsonl(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_label(start: int, end: int, text: str, label_type: str) -> Dict:
    return {
        "start": start,
        "end": end,
        "text": text,
        "label_type": label_type,
    }


def validate_spans(example: Dict) -> None:
    output = example["output"]
    for label in example.get("hallucination_labels", []):
        start = label["start"]
        end = label["end"]
        text = label["text"]
        actual = output[start:end]

        if actual != text:
            raise ValueError(
                f"Span mismatch in {example.get('id')}: "
                f"expected {text!r}, got {actual!r}"
            )


def corrupt_number(value: str) -> str:
    """
    Produce a clearly different numeric value while preserving rough formatting.
    Examples:
    4172.80 -> 4283.91
    +0.68% -> -9.99%
    $123.45 -> $234.56
    """
    prefix = ""
    suffix = ""

    if value[0] in "$€£":
        prefix = value[0]
        value_core = value[1:]
    else:
        value_core = value

    if value_core.endswith("%"):
        suffix = "%"
        value_core = value_core[:-1]

    if suffix == "%":
        if value_core.startswith("+"):
            return "-9.99%"
        if value_core.startswith("-"):
            return "+9.99%"
        return "99.99%"

    normalized = value_core.replace(",", "")

    try:
        number = float(normalized)
    except ValueError:
        return prefix + "9999"

    if "." in normalized:
        new_number = number + 111.11
        return prefix + f"{new_number:.2f}"

    new_number = int(number) + 101
    return prefix + str(new_number)


def find_numeric_conflict(output: str, context: str) -> Optional[Tuple[int, int, str]]:
    """
    Find a number that appears both in output and context, then corrupt it.
    """
    for match in NUM_RE.finditer(output):
        original = match.group(0)

        # Avoid changing very tiny or meaningless numbers.
        if len(original) < 2:
            continue

        if original in context:
            replacement = corrupt_number(original)

            if replacement != original:
                return match.start(), match.end(), replacement

    return None


def find_word_conflict(output: str, context: str) -> Optional[Tuple[int, int, str]]:
    """
    Find a factual word that appears in both output and context, then replace it.
    """
    output_lower = output.lower()
    context_lower = context.lower()

    for original, replacement in WORD_REPLACEMENTS.items():
        pattern = re.compile(rf"\b{re.escape(original)}\b", re.IGNORECASE)
        match = pattern.search(output)

        if not match:
            continue

        if original not in context_lower:
            continue

        return match.start(), match.end(), replacement

    return None


def inject_conflict(example: Dict) -> Optional[Dict]:
    ex = copy.deepcopy(example)
    output = ex["output"]
    context = ex["context"]

    candidate = find_numeric_conflict(output, context)

    if candidate is None:
        candidate = find_word_conflict(output, context)

    if candidate is None:
        return None

    start, end, replacement = candidate
    new_output = output[:start] + replacement + output[end:]

    ex["id"] = f"{example['id']}_conflict"
    ex["original_output"] = output
    ex["output"] = new_output
    ex["hallucination_type"] = "conflict"
    ex["hallucination_labels"] = [
        make_label(
            start=start,
            end=start + len(replacement),
            text=replacement,
            label_type="Evident Conflict",
        )
    ]
    ex["hallucination_labels_processed"] = {
        "evident_conflict": 1,
        "baseless_info": 0,
    }

    validate_spans(ex)
    return ex


def append_hallucinated_sentence(example: Dict, sentence: str, label_type: str, hallucination_type: str) -> Dict:
    ex = copy.deepcopy(example)

    original_output = ex["output"]
    base = original_output.rstrip()

    separator = " "
    start = len(base) + len(separator)
    new_output = base + separator + sentence
    end = start + len(sentence)

    ex["id"] = f"{example['id']}_{hallucination_type}"
    ex["original_output"] = original_output
    ex["output"] = new_output
    ex["hallucination_type"] = hallucination_type
    ex["hallucination_labels"] = [
        make_label(
            start=start,
            end=end,
            text=sentence,
            label_type=label_type,
        )
    ]

    if hallucination_type == "overgeneration":
        ex["hallucination_labels_processed"] = {
            "evident_conflict": 0,
            "baseless_info": 1,
        }
    elif hallucination_type == "missing_tool":
        ex["hallucination_labels_processed"] = {
            "evident_conflict": 0,
            "baseless_info": 1,
        }
    else:
        raise ValueError(f"Unknown hallucination type: {hallucination_type}")

    validate_spans(ex)
    return ex


def inject_overgeneration(example: Dict) -> Dict:
    sentence = random.choice(OVERGENERATION_SENTENCES)
    return append_hallucinated_sentence(
        example=example,
        sentence=sentence,
        label_type="Unsupported Addition",
        hallucination_type="overgeneration",
    )


def inject_missing_tool(example: Dict) -> Dict:
    """
    Add an action suggestion that would require an unavailable external tool.
    For MVP, we treat these action suggestions as missing-tool hallucinations.
    """
    sentence = random.choice(MISSING_TOOL_SENTENCES)
    return append_hallucinated_sentence(
        example=example,
        sentence=sentence,
        label_type="Missing Tool",
        hallucination_type="missing_tool",
    )


def make_clean(example: Dict) -> Dict:
    ex = copy.deepcopy(example)
    ex["id"] = f"{example['id']}_clean"
    ex["hallucination_type"] = "clean"
    ex["hallucination_labels"] = []
    ex["hallucination_labels_processed"] = {
        "evident_conflict": 0,
        "baseless_info": 0,
    }

    validate_spans(ex)
    return ex


def print_preview(name: str, rows: List[Dict], n: int = 2) -> None:
    print(f"\n{name} preview:")
    for row in rows[:n]:
        print("=" * 80)
        print("ID:", row["id"])
        print("QUERY:", row["query"][:300])
        print("CONTEXT:", row["context"][:300])
        print("OUTPUT:", row["output"][:700])
        print("LABELS:", row["hallucination_labels"])


def main():
    random.seed(SEED)

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_PATH}. "
            "Run scripts/01c_make_dev_sample.py first."
        )

    examples = read_jsonl(INPUT_PATH)
    print(f"Loaded examples: {len(examples)}")

    # Additional safety filtering.
    examples = [
        ex for ex in examples
        if 20 <= len(ex.get("output", "")) <= 3000
        and 20 <= len(ex.get("context", "")) <= 5000
    ]

    print(f"After filtering: {len(examples)}")

    random.shuffle(examples)

    clean = [make_clean(ex) for ex in examples[:N_PER_DATASET]]

    conflict = []
    for ex in examples:
        injected = inject_conflict(ex)
        if injected is not None:
            conflict.append(injected)

        if len(conflict) >= N_PER_DATASET:
            break

    overgeneration = [
        inject_overgeneration(ex)
        for ex in examples[:N_PER_DATASET]
    ]

    missing_tool = [
        inject_missing_tool(ex)
        for ex in examples[:N_PER_DATASET]
    ]

    print("\nCreated datasets:")
    print(f"Clean:          {len(clean)}")
    print(f"Conflict:       {len(conflict)}")
    print(f"Overgeneration: {len(overgeneration)}")
    print(f"Missing tool:   {len(missing_tool)}")

    write_jsonl(OUT_DIR / "clean.jsonl", clean)
    write_jsonl(OUT_DIR / "conflict.jsonl", conflict)
    write_jsonl(OUT_DIR / "overgeneration.jsonl", overgeneration)
    write_jsonl(OUT_DIR / "missing_tool.jsonl", missing_tool)

    all_rows = clean + conflict + overgeneration + missing_tool
    write_jsonl(OUT_DIR / "all_synthetic.jsonl", all_rows)

    print(f"\nSaved files to: {OUT_DIR}")
    print_preview("Conflict", conflict)
    print_preview("Overgeneration", overgeneration)
    print_preview("Missing tool", missing_tool)


if __name__ == "__main__":
    main()