# Synthetic Tool-Calling Hallucination Dataset

Pipeline for building evaluation datasets from [ToolACE](https://huggingface.co/datasets/Team-ACE/ToolACE) with controlled hallucination injection.

## Quick start (Colab)

```bash
!pip install -r requirements-colab.txt

# 1. Extract clean tool-calling examples from ToolACE
!python scripts/01_extract_base_examples.py

# 2. Sample dev subset (500 examples)
!python scripts/01c_make_dev_sample.py

# 2. Sample dev subset (500 examples)
!python scripts/01c_make_dev_sample.py

# 2b. Auto-collect entity candidates (optional, improves conflict injection)
!python scripts/05_collect_entity_candidates.py --input data/interim/toolace_base_clean.jsonl

# 2c. Pre-generate HF overgeneration cache (optional, ~3GB GPU)
# Default model: Qwen/Qwen2.5-1.5B-Instruct
!python scripts/06_pregenerate_overgeneration_hf.py --limit 20   # smoke test
# !python scripts/06_pregenerate_overgeneration_hf.py            # full 300

# 3. Inject hallucinations
!python scripts/02_inject_hallucinations.py

# 3b. Optional: LLM-based overgeneration (needs OPENAI_API_KEY)
import os
os.environ["OPENAI_API_KEY"] = "sk-..."
!python scripts/02_inject_hallucinations.py --use-llm-overgeneration

# 4. Stats + manual review sample
!python scripts/03_dataset_stats.py
!python scripts/04_make_review_file.py
```

Outputs land in `data/processed/`:
- `clean.jsonl`
- `conflict.jsonl`
- `overgeneration.jsonl`
- `missing_tool.jsonl`
- `all_synthetic.jsonl`

## Hallucination types

| Type | Method | Label |
|------|--------|-------|
| `clean` | Original faithful response | none |
| `conflict` | Corrupt shared facts from context | `Evident Conflict` |
| `overgeneration` | Add unsupported info woven into the answer (same topic, not in tool output) | `Unsupported Addition` |
| `missing_tool` | Append unavailable action offer | `Missing Tool` |

## v2 improvements (current)

### Conflict — harder factual corruptions

Priority order when searching output/context overlap:

1. **Numbers** — multiple strategies, not only `+111.11`:
   - `multiply_150` (×1.5)
   - `divide_2`
   - `percent_flip` / `150%`
   - `scale_10` / `digit_swap`
   - `add_fixed`

2. **Dates** — ISO (`2024-09-21`), US (`3/15/2024`), month names (`June 2, 2023`), years

3. **Entities** — dictionary replacements (`Paris→London`, `Ferrari→Porsche`, `BRCA1→BRCA2`, …)

4. **Status words** — expanded antonym map (`approved↔rejected`, `online↔offline`, …)

Optional **multi-span conflicts** (~15% by default): two non-overlapping corruptions in one example.

Metadata field: `corruption_types: ["number", "date", ...]`.

### Missing tool — richer action offers

- 25 generic action sentences (email, payment, CRM, Slack, calendar, …)
- Keyword-aware selection from query (`flight`, `hotel`, `order`, `report`, …)

### Overgeneration — definition

Overgeneration means the answer adds **information not present in the tool output**, while staying on-topic.

Example:
```
User:   Help me check the weather in Beijing.
Tool:   {location: "Beijing", weather: "sunny"}
Answer: The weather in Beijing is sunny, and the weather has been pretty good over the past few months.
                                              ^^^^^^^^^^^^^^^^^ unsupported clause ^^^^^^^^^^^^^^^^^
```

This is **not** missing-tool (no action offer) and **not** conflict (does not contradict the tool).

Implementation:
- extends the last **substantive** sentence with `, and <clause>`
- skips polite closings (`feel free to ask`, `let me know if ...`)
- labels **only the clause**, not the connector
- chooses domain-aware clauses (weather / price / report / game / ...)
- HF/OpenAI cache stores `clause`, not a standalone trailing sentence

### Overgeneration — LLM mode

Templates remain the default fallback. With `--use-llm-overgeneration`:

- OpenAI generates one contextually plausible but unsupported trailing sentence
- Results cached in `data/interim/overgeneration_llm_cache.jsonl` (resumable)

```bash
export OPENAI_API_KEY=...
export OPENAI_OVERGEN_MODEL=gpt-4o-mini   # optional
python scripts/02_inject_hallucinations.py --use-llm-overgeneration
```

## CLI options

```bash
python scripts/02_inject_hallucinations.py \
  --input data/interim/toolace_base_clean_dev500.jsonl \
  --out-dir data/processed \
  --n-per-dataset 300 \
  --max-conflict-spans 2 \
  --multi-conflict-rate 0.15 \
  --use-llm-overgeneration
```

## Pipeline scripts

| Script | Purpose |
|--------|---------|
| `00_inspect_toolace.py` | Inspect raw ToolACE schema |
| `01_extract_base_examples.py` | Extract query/context/output tuples |
| `01b_validate_extracted_examples.py` | Sanity check + manual review sample |
| `01c_make_dev_sample.py` | Sample 500 dev examples |
| `02_inject_hallucinations.py` | Inject all hallucination types |
| `03_dataset_stats.py` | CSV stats + bar chart |
| `04_make_review_file.py` | Markdown review sample |
| `05_collect_entity_candidates.py` | Auto-build `entity_replacements.json` from ToolACE |
| `06_pregenerate_overgeneration_hf.py` | HF overgeneration cache (Colab-friendly) |

Core injection logic lives in `scripts/injection_utils.py`.

## Entity auto-collection (script 05)

Scans extracted ToolACE examples and finds entities appearing in **both** output and tool context — these are corruptible for conflict injection.

```bash
python scripts/05_collect_entity_candidates.py \
  --input data/interim/toolace_base_clean.jsonl \
  --out-dir data/interim \
  --min-both-freq 2
```

Outputs:
- `data/interim/entity_replacements.json` — auto-paired replacements (loaded automatically in step 02)
- `data/interim/entity_candidates.json` — top entities + stats
- `data/interim/entity_replacement_pairs.json` — pair metadata

Pairing heuristic: entities in the same bucket (`single_word`, `multi_word`, `acronym`, `code`) are paired by frequency.

## HF overgeneration cache (script 06)

Pre-generate trailing sentences **without running the full injection pipeline**. Uses a small instruct model that fits Colab T4:

| Model | VRAM (fp16) |
|-------|-------------|
| `Qwen/Qwen2.5-1.5B-Instruct` (default) | ~3 GB |
| `google/gemma-2-2b-it` | ~5 GB |

```bash
# smoke test
python scripts/06_pregenerate_overgeneration_hf.py --limit 10

# full cache for dev500 (resumable — appends to jsonl)
python scripts/06_pregenerate_overgeneration_hf.py

# then inject using the cache (no API needed)
python scripts/02_inject_hallucinations.py \
  --overgeneration-cache data/interim/overgeneration_hf_cache.jsonl
```

Features:
- Incremental append to cache (safe to interrupt/resume)
- `--rewrite-cache` to start fresh
- Validation + up to 3 HF retries; template fallback on failure
- Post-hoc repair: `python scripts/07_clean_overgeneration_cache.py`

## Extending entity replacements

Run script 05 first for auto-pairs, then hand-edit `data/interim/entity_replacements.json` if needed.
Manual overrides in `scripts/injection_utils.py` still apply:

```python
ENTITY_REPLACEMENTS = {
    "Paris": "London",
    "Ferrari": "Porsche",
}
```

Entities are matched only when they appear in **both** output and tool context, so replacements stay grounded in corruptible shared facts.
