from datasets import load_dataset
from pathlib import Path
import json
import re
from tqdm import tqdm


OUT_DIR = Path("data/interim")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def maybe_json_loads(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return x
    return x


def find_conversation_column(row):
    """
    ToolACE may expose the conversation column under different names.
    This function tries to find the column that contains a list of messages.
    """
    candidate_names = ["conversations", "conversation", "messages", "dialogue", "dialog"]
    for name in candidate_names:
        if name in row:
            value = maybe_json_loads(row[name])
            if is_message_list(value):
                return name, value

    for name, value in row.items():
        value = maybe_json_loads(value)
        if is_message_list(value):
            return name, value

    return None, None


def is_message_list(value):
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(m, dict) for m in value)
        and all("from" in m and "value" in m for m in value)
    )


def looks_like_tool_call(text):
    """
    ToolACE assistant tool calls often look like:
    [ToolName(param="value")]
    """
    if not isinstance(text, str):
        return False
    text = text.strip()
    return text.startswith("[") and "(" in text and ")" in text


def extract_called_tools(text):
    """
    Very simple parser:
    [Weather_API(location="Beijing")]
    -> ["Weather_API"]
    """
    if not isinstance(text, str):
        return []

    names = re.findall(r"\[?\s*([A-Za-z0-9_/\- ]+)\s*\(", text)
    return [n.strip() for n in names if n.strip()]


def extract_examples_from_conversation(conv, row_id):
    examples = []

    for i, msg in enumerate(conv):
        role = msg.get("from")
        value = msg.get("value", "")

        if role != "tool":
            continue

        context = value

        # Find latest user message before this tool output
        query = None
        for j in range(i - 1, -1, -1):
            if conv[j].get("from") == "user":
                query = conv[j].get("value", "")
                break

        # Find assistant tool call before this tool output
        tool_call = ""
        for j in range(i - 1, -1, -1):
            if conv[j].get("from") == "assistant" and looks_like_tool_call(conv[j].get("value", "")):
                tool_call = conv[j].get("value", "")
                break

        # Find final assistant answer after this tool output
        output = None
        for j in range(i + 1, len(conv)):
            if conv[j].get("from") == "assistant":
                candidate = conv[j].get("value", "").strip()

                # Skip empty assistant messages and tool calls
                if not candidate:
                    continue
                if looks_like_tool_call(candidate):
                    continue

                output = candidate
                break

        if query and context and output:
            examples.append(
                {
                    "id": f"toolace_{row_id}_{i}",
                    "query": query,
                    "context": context,
                    "output": output,
                    "tool_call": tool_call,
                    "available_tools": extract_called_tools(tool_call),
                    "hallucination_labels": [],
                    "hallucination_labels_processed": {
                        "evident_conflict": 0,
                        "baseless_info": 0,
                    },
                    "source": "ToolACE",
                }
            )

    return examples


def main():
    ds = load_dataset("Team-ACE/ToolACE", split="train")

    all_examples = []
    skipped_no_conv = 0

    for row_id, row in enumerate(tqdm(ds, desc="Extracting")):
        _, conv = find_conversation_column(row)

        if conv is None:
            skipped_no_conv += 1
            continue

        examples = extract_examples_from_conversation(conv, row_id)

        for ex in examples:
            ex["system"] = row.get("system", "")

        all_examples.extend(examples)

    out_path = OUT_DIR / "toolace_base_clean.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    sample_path = OUT_DIR / "toolace_base_clean_sample.jsonl"
    with sample_path.open("w", encoding="utf-8") as f:
        for ex in all_examples[:100]:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print("\nDone.")
    print(f"Extracted examples: {len(all_examples)}")
    print(f"Skipped rows without conversation: {skipped_no_conv}")
    print(f"Saved full file to: {out_path}")
    print(f"Saved sample to: {sample_path}")

    if all_examples:
        print("\nFirst extracted example:")
        print(json.dumps(all_examples[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()