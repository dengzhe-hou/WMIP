#!/usr/bin/env python3
"""Replace generate() with your inference code, then run this script.

    python releases/2026-10/examples/evaluate_callable.py --out-dir my-results

To check only the adapter, --demo uses three synthetic zero replies; it does
not run a model and its scores are not model results.

Rerun the same command after an interruption: successful responses are skipped
and failed or absent items are retried. Use a new --out-dir when changing the
model or inference settings, or when switching between --demo and a real run.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wmip import evaluate, load_items, score


def generate(item):
    messages = []
    if item.get("system"):
        messages.append({"role": "system", "content": item["system"]})
    messages.append({"role": "user", "content": item["prompt"]})
    # Replace this with your model's call. Honor the exact messages and each
    # item's max_tokens (16 for core items; other protocols can differ).
    # Never include item["gold"] in the model input. Keep reasoning disabled
    # for the released protocols. Do not invent finish_reason if unavailable.
    # result = your_model(messages=messages, max_tokens=item["max_tokens"])
    # return {"response": result.text, "finish_reason": result.finish_reason}
    raise NotImplementedError("Replace generate() with your inference function, or use --demo")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/item_bank/item_bank.jsonl")
    parser.add_argument("--label", default="my-model")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    items = load_items(args.bank)
    callback = generate
    if args.demo:
        print("SYNTHETIC adapter demonstration: three zero replies, no model inference.")
        items = items[:3]
        callback = lambda item: "0"
    # evaluate() resumes this append-only file automatically. Incorrect, empty
    # and truncated responses are completed trials and are never requested again.
    records = evaluate(items, callback, args.out_dir / "responses.jsonl", args.label,
                       synthetic=args.demo)
    score(items, records, args.out_dir)


if __name__ == "__main__":
    main()
