# Hallucination Detection in Tool Calling

This project investigates span-level hallucination detection in tool-calling dialogues.  
We build a synthetic hallucination detection dataset from ToolACE, evaluate baseline methods, and improve detection quality with fine-tuning and hybrid approaches.

## Links

- [Final project report](https://docs.google.com/document/d/1tpRx8UnjmTNec19FPGaKTjGH8YatLNYtvUiw2I4V2tg/edit?usp=sharing)
- [Main notebook](baselines_learn_final.ipynb)
- [Final dataset on Hugging Face](https://huggingface.co/datasets/annnettte/HalluToolACE)
- [Fine-tuned model on Hugging Face](https://huggingface.co/annnettte/lettucedect-tool-calling)

## Project overview

The dataset is based on ToolACE tool-calling dialogues.  
Each example contains:

- user query
- tool output as context
- final assistant response
- span-level hallucination labels

We generate three hallucination types:

1. contradiction-based hallucinations
2. overgeneration hallucinations
3. missing-tool hallucinations

## Experiments

We evaluate:

- LettuceDetect
- LookBackLens
- fine-tuned LettuceDetect
- weighted fine-tuning for conflict examples
- hybrid model selection by hallucination type

The best final approach is the hybrid system, which combines the strongest model per hallucination category.
