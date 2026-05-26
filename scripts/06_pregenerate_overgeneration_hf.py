"""Pre-generate overgeneration sentence cache with a local HuggingFace model (Colab-friendly)."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import torch
from tqdm import tqdm

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from injection_utils import (  # noqa: E402
    OVERGENERATION_CLAUSES_BY_DOMAIN,
    build_overgeneration_prompt,
    choose_overgeneration_clause,
    load_overgeneration_cache,
    normalize_overgeneration_clause,
    read_jsonl,
    sanitize_overgeneration_clause,
    validate_overgeneration_clause,
)


DEFAULT_INPUT = Path("data/interim/toolace_base_clean_dev500.jsonl")
DEFAULT_CACHE = Path("data/interim/overgeneration_hf_cache.jsonl")
DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


def filter_examples(examples):
    return [
        ex
        for ex in examples
        if 20 <= len(ex.get("output", "")) <= 3000
        and 20 <= len(ex.get("context", "")) <= 5000
    ]


def append_cache_row(path: Path, base_id: str, clause: str, model_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "base_id": base_id,
        "clause": clause,
        "model": model_name,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_model_and_tokenizer(model_name: str, auth_token: str | None = None):
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name, token=auth_token)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        token=auth_token,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
    )
    if not torch.cuda.is_available():
        model = model.to("cpu")
    model.eval()
    return model, tokenizer


def generate_with_hf(model, tokenizer, example: dict, max_new_tokens: int = 48) -> str:
    prompt = build_overgeneration_prompt(example)
    messages = [
        {"role": "system", "content": "Return only the clause text. 6-16 words."},
        {"role": "user", "content": prompt},
    ]

    if hasattr(tokenizer, "apply_chat_template"):
        chat_prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    else:
        chat_prompt = prompt

    inputs = tokenizer(chat_prompt, return_tensors="pt")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.9,
            top_p=0.95,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated = output_ids[0, inputs["input_ids"].shape[1] :]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    return normalize_overgeneration_clause(text)


def generate_valid_clause(
    model,
    tokenizer,
    example: dict,
    max_new_tokens: int,
    max_attempts: int = 3,
) -> tuple[str, str]:
    from injection_utils import normalize_overgeneration_clause, validate_overgeneration_clause

    for _attempt in range(max_attempts):
        raw = generate_with_hf(model, tokenizer, example, max_new_tokens=max_new_tokens)
        normalized = normalize_overgeneration_clause(raw)
        is_valid, _reason = validate_overgeneration_clause(normalized, example)
        if is_valid:
            return normalized, "hf"
    return choose_overgeneration_clause(example), "template"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-generate overgeneration cache with a HuggingFace instruct model."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--cache-path", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--model-name", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--auth-token", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None, help="Max examples to generate.")
    parser.add_argument("--max-new-tokens", type=int, default=48)
    parser.add_argument("--max-attempts", type=int, default=3, help="HF retries per example if validation fails.")
    parser.add_argument(
        "--rewrite-cache",
        action="store_true",
        help="Delete existing cache file before generation.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(
            f"Input not found: {args.input}. Run scripts/01c_make_dev_sample.py first."
        )

    examples = filter_examples(read_jsonl(args.input))
    if args.limit is not None:
        examples = examples[: args.limit]

    if args.rewrite_cache and args.cache_path.exists():
        args.cache_path.unlink()

    cache = load_overgeneration_cache(args.cache_path) if args.cache_path.exists() else {}
    todo = [ex for ex in examples if ex["id"] not in cache]
    print(f"Loaded examples: {len(examples)}")
    print(f"Already cached:    {len(cache)}")
    print(f"To generate:       {len(todo)}")
    print(f"Model:             {args.model_name}")

    if not todo:
        print("Nothing to do.")
        return

    model, tokenizer = load_model_and_tokenizer(args.model_name, auth_token=args.auth_token)

    generated = 0
    failed = 0
    used_template = 0
    for example in tqdm(todo, desc="HF overgeneration"):
        try:
            clause, source = generate_valid_clause(
                model,
                tokenizer,
                example,
                max_new_tokens=args.max_new_tokens,
                max_attempts=args.max_attempts,
            )
            if source == "template":
                used_template += 1
        except Exception as exc:
            failed += 1
            print(f"\nFailed for {example['id']}: {exc}")
            clause = choose_overgeneration_clause(example)
            source = "template"
            used_template += 1

        cache[example["id"]] = clause
        append_cache_row(args.cache_path, example["id"], clause, args.model_name)
        generated += 1

    print(f"\nDone. Generated: {generated}, failed: {failed}, template_fallback: {used_template}")
    print(f"Cache saved to: {args.cache_path}")
    print("\nUse it in step 02:")
    print(
        "  python scripts/02_inject_hallucinations.py "
        f"--overgeneration-cache {args.cache_path}"
    )


if __name__ == "__main__":
    main()
