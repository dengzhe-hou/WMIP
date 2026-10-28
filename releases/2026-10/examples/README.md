# Run a real model locally

Run these commands from `releases/2026-10/` in the [v2026.10.3 clone](../../../README.md#evaluate-your-model). This example uses Qwen/Qwen3-4B-Instruct-2507 at revision `cdbee75f17c01a7cc42f958dc650907174af0554`, with CPU float32 and four threads.

## Install

Use an isolated Python 3.13 environment. The [official CPU wheels](https://download.pytorch.org/whl/cpu/torch/) avoid installing CUDA dependencies.

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.11.0
python -m pip install transformers==5.9.0
```

Weights load from the Hugging Face cache or download on first use. To reuse a shared cache, set `HF_HUB_CACHE` to its existing directory before running.

## Run three items

```bash
python examples/evaluate_transformers.py \
    --limit 3 --label qwen3-4b-cpu --out-dir my-local-run
```

The verified run begins with:

```text
Selected first 3/840 bank items; scoring the full bank. Unrun items remain missing.
```

The script preserves each item's prompt, optional system message and token budget. The default model is non-thinking; decoding is greedy, with no added system instruction.

## Resume

Rerun the same command. Completed answers are retained, with no model loading or inference when all three are complete. `--limit 3` selects the first three bank items, rather than three new requests. The smoke command stops there. To choose a full 840-item run, continue with:

```bash
python examples/evaluate_transformers.py \
    --label qwen3-4b-cpu --out-dir my-local-run
```

Use a new output directory when changing inference settings.

## Inspect

```bash
cat my-local-run/responses.jsonl
cat my-local-run/scores/accuracy_by_block.csv
```

`run_metadata.json` records the model revision, dependency versions and inference settings. Scores cover the full bank; after three completed requests, 837 items remain missing. Accuracy excludes missing answers, so report coverage alongside it.

This is an installation and workflow check. CPU float32 inference differs from the paper's backend; these three items do not reproduce its results. Verification used Python 3.13.12, Transformers 5.9.0 and PyTorch 2.11.0+cu130 running on CPU; the installation above selects the CPU build instead.
