#!/usr/bin/env python3
"""Run a pinned, non-thinking Qwen chat model locally on CPU.

    python examples/evaluate_transformers.py --limit 3 --out-dir my-local-run

Install torch and transformers first; see examples/README.md. The default is
Qwen/Qwen3-4B-Instruct-2507 at the revision below, using float32, greedy decoding
and four CPU threads. --model accepts another local path or Hugging Face ID;
pin --revision for a remote model. Check custom models' chat templates and
reasoning behavior before comparing results with the released protocols.

--limit N selects the first N bank items, not N new calls. Rerunning the same
command skips their completed responses without loading the model. Increase N
or omit --limit to continue. Scores always cover the full supplied bank, with
unrun items explicitly missing. A three-item run checks installation and the
evaluation workflow; it is not a benchmark result or a reproduction of the
paper's inference setup.
"""

from __future__ import annotations

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wmip import evaluate, load_items, score

DEFAULT_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
DEFAULT_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"


class PrefixComplete(Exception):
    """Stop the existing append-only adapter at the selected bank prefix."""


def messages_for(item):
    """Expose only the bank's original conversation turns to the model."""
    messages = []
    if item.get("system") is not None:
        messages.append({"role": "system", "content": item["system"]})
    messages.append({"role": "user", "content": item["prompt"]})
    return messages


def template_options(tokenizer):
    # Qwen3 Instruct 2507 is non-thinking and has no thinking switch. Other
    # templates declaring the standard switch receive it explicitly; templates
    # without that switch retain their own behavior and need the user's review.
    return {"enable_thinking": False} if "enable_thinking" in tokenizer.chat_template else {}


def generation_result(tokenizer, generated_ids, eos_token_ids, budget):
    """Derive termination from generated tokens, not from response text."""
    stop_ids = [eos_token_ids] if isinstance(eos_token_ids, int) else (eos_token_ids or [])
    if generated_ids and generated_ids[-1] in stop_ids:
        finish_reason = "stop"
    elif len(generated_ids) == budget:
        finish_reason = "length"
    else:
        raise RuntimeError("Generation ended before the token budget without an EOS token")
    return {"response": tokenizer.decode(generated_ids, skip_special_tokens=True),
            "finish_reason": finish_reason}


class LocalModel:
    """Load weights only when evaluate() actually requests a pending item."""

    def __init__(self, tokenizer, model_name, revision, threads):
        self.tokenizer = tokenizer
        self.model_name = model_name
        self.revision = revision
        self.threads = threads
        self.model = None

    def __call__(self, item):
        import torch
        from transformers import AutoModelForCausalLM, GenerationConfig

        if self.model is None:
            torch.set_num_threads(self.threads)
            print(f"Loading {self.model_name} on CPU (float32, {self.threads} threads).",
                  flush=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name, revision=self.revision, dtype=torch.float32,
            ).to("cpu").eval()
        # Explicit neutral sampling values prevent Transformers from filling
        # them with the Qwen repository's sampled generation defaults. Keep
        # the per-item budget in this config too, rather than mixing config
        # and generation keyword arguments.
        generation_config = GenerationConfig(
            do_sample=False, temperature=1.0, top_p=1.0, top_k=50,
            num_beams=1, num_return_sequences=1, repetition_penalty=1.0,
            eos_token_id=self.model.generation_config.eos_token_id,
            pad_token_id=self.tokenizer.pad_token_id,
            bos_token_id=self.tokenizer.bos_token_id,
            max_new_tokens=item["max_tokens"],
        )
        inputs = self.tokenizer.apply_chat_template(
            messages_for(item), add_generation_prompt=True, tokenize=True,
            return_dict=True, return_tensors="pt", **template_options(self.tokenizer),
        )
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs, generation_config=generation_config,
            )
        generated_ids = outputs[0, inputs["input_ids"].shape[-1]:].tolist()
        result = generation_result(self.tokenizer, generated_ids,
                                   generation_config.eos_token_id, item["max_tokens"])
        print(f"{item['item_id']}: {result['response']!r} ({result['finish_reason']})", flush=True)
        return result


def save_metadata(path, metadata, records):
    """Keep a resumed run on the same explicit model and inference settings."""
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != metadata:
            raise ValueError("Run settings differ from run_metadata.json; use a new --out-dir")
    elif records.exists():
        raise ValueError("Existing responses have no run_metadata.json; use a new --out-dir")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(items, generate, out_dir, label, limit=None):
    """Resume a selected prefix while scoring coverage against the full bank."""
    selected = {item["item_id"] for item in items[:limit]}
    records = out_dir / "responses.jsonl"

    def selected_generate(item):
        if item["item_id"] not in selected:
            raise PrefixComplete
        return generate(item)

    try:
        evaluate(items, selected_generate, records, label)
    except PrefixComplete:
        pass
    score(items, records, out_dir / "scores")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/item_bank/item_bank.jsonl")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--revision", help="Hugging Face revision; the default example is pinned")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--limit", type=int, help="evaluate only the first N bank items; score the full bank")
    parser.add_argument("--label", default="local-transformers")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.threads < 1 or (args.limit is not None and args.limit < 1):
        parser.error("--threads and --limit must be positive integers")
    import torch
    from transformers import AutoTokenizer

    revision = args.revision or (DEFAULT_REVISION if args.model == DEFAULT_MODEL else None)
    items = load_items(args.bank)
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=revision)
    if not isinstance(tokenizer.chat_template, str):
        raise ValueError("This example requires a model with a single chat template")
    metadata = {
        "model": args.model, "revision": revision, "label": args.label,
        "torch_version": torch.__version__, "transformers_version": version("transformers"),
        "tokenizers_version": version("tokenizers"), "device": "cpu", "dtype": "float32",
        "threads": args.threads, "do_sample": False, "repetition_penalty": 1.0,
        "temperature": 1.0, "top_p": 1.0, "top_k": 50, "num_beams": 1,
        "num_return_sequences": 1,
        "max_new_tokens": "each bank item's max_tokens",
        "chat_template": tokenizer.chat_template, "chat_template_options": template_options(tokenizer),
    }
    records = args.out_dir / "responses.jsonl"
    save_metadata(args.out_dir / "run_metadata.json", metadata, records)
    selected_count = min(args.limit, len(items)) if args.limit is not None else len(items)
    print(f"Selected first {selected_count}/{len(items)} bank items; scoring the full bank. "
          "Unrun items remain missing.", flush=True)
    run(items, LocalModel(tokenizer, args.model, revision, args.threads),
        args.out_dir, args.label, args.limit)


if __name__ == "__main__":
    main()
