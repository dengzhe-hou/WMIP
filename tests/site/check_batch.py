#!/usr/bin/env python3
"""Verify downloaded JSONL records against the public Python task generator.

Run with Python 3 and Node.js: python tests/site/check_batch.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "releases/2026-10/code/generator/build_item_bank.py"
spec = importlib.util.spec_from_file_location("public_generator", SOURCE)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def main():
    cases = [[0, 1, 1], [2026, 3, 5], [2027, 10, 25],
             [4294967295, 1000, 3], [4294967295, 1, 1000]]
    module_uri = (ROOT / "site/batch.mjs").as_uri()
    javascript = f"""
import {{ readFileSync }} from 'node:fs';
import {{ generateBatchItems, serializeItem }} from {json.dumps(module_uri)};
const cases = JSON.parse(readFileSync(0, 'utf8'));
const batches = cases.map(args => Array.from(generateBatchItems(...args), serializeItem).join(''));
for (const count of [0, 1001, 1.5]) {{
  let rejected = false;
  try {{ Array.from(generateBatchItems(2026, 3, count)); }}
  catch (error) {{ if (error instanceof RangeError) rejected = true; else throw error; }}
  if (!rejected) throw new Error(`Invalid count accepted: ${{count}}`);
}}
process.stdout.write(JSON.stringify(batches));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", javascript],
        input=json.dumps(cases), text=True, capture_output=True, check=True,
    )
    batches = json.loads(result.stdout)
    checked = 0
    for (seed, k, count), jsonl in zip(cases, batches, strict=True):
        assert jsonl.endswith("\n") and not jsonl.endswith("\n\n")
        lines = jsonl.splitlines()
        assert len(lines) == count
        for probe_idx, line in enumerate(lines):
            item = json.loads(line)
            problem = generator.build_problem(k, seed, probe_idx)
            prompt = generator.main_prompt(
                problem["initial_state"], [text for text, _, _ in problem["ops"]],
                problem["query_entity"],
            )
            assert item == {
                "source": "browser-generated",
                "item_id": f"core-s{seed}-k{k}-p{probe_idx}",
                "seed": seed,
                "k": k,
                "probe_idx": probe_idx,
                "prompt": prompt,
                "gold": problem["gold"],
                "answer_type": "int",
            }, f"Mismatch for seed={seed}, k={k}, probe={probe_idx}"
            checked += 1
    print(f"PASS: {len(cases)} JSONL batches, {checked} records match Python prompts and answers.")
    print("PASS: requested counts, fixed seeds, sequential probe indices and final newlines.")
    print("PASS: invalid counts fail clearly.")


if __name__ == "__main__":
    main()
