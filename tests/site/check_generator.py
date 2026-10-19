#!/usr/bin/env python3
"""Check browser tasks against the public Python generator and replay their text.

Run with Python 3 and Node.js: python tests/site/check_generator.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "releases/2026-10/code/generator/build_item_bank.py"
spec = importlib.util.spec_from_file_location("public_generator", SOURCE)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def replay(problem):
    """Recompute states from operation sentences, independent of generator updates."""
    state = dict(problem["initial_state"])
    states = [dict(state)]
    relevant = 0
    for text, changed, kind in problem["ops"]:
        gain = re.fullmatch(r"(\w+) gains (\d+) points?\.", text)
        lose = re.fullmatch(r"(\w+) loses (\d+) points\.", text)
        transfer = re.fullmatch(r"(\w+) gives (\d+) points to (\w+)\.", text)
        if gain:
            entity, amount = gain.groups()
            state[entity] += int(amount)
            expected_changed = [entity]
            expected_kind = "gain_one" if text.endswith("1 point.") else "gain"
        elif lose:
            entity, amount = lose.groups()
            state[entity] -= int(amount)
            expected_changed = [entity]
            expected_kind = "lose"
        elif transfer:
            giver, amount, receiver = transfer.groups()
            state[giver] -= int(amount)
            state[receiver] += int(amount)
            expected_changed = [giver, receiver]
            expected_kind = "transfer"
        else:
            assert text == "No transfer occurs this round.", text
            expected_changed = []
            expected_kind = "no_transfer"
        assert list(changed) == expected_changed
        assert kind == expected_kind
        assert all(value >= 1 for value in state.values())
        relevant += problem["query_entity"] in expected_changed
        states.append(dict(state))
    assert state[problem["query_entity"]] == problem["gold"]
    assert relevant == problem["n_relevant_ops"]
    return states


def main():
    cases = [
        [seed, k, 0]
        for seed in [0, 1, 100, 2026, 2027, 4294967295]
        for k in [1, 3, 5, 10, 100, 1000]
    ]
    cases.extend([[2026, 3, 4], [2027, 100, 9]])
    module_uri = (ROOT / "site/generator.mjs").as_uri()
    javascript = f"""
import {{ readFileSync }} from 'node:fs';
import {{ generateProblem }} from {json.dumps(module_uri)};
const cases = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(cases.map(args => generateProblem(...args))));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", javascript],
        input=json.dumps(cases), text=True, capture_output=True, check=True,
    )
    actual_cases = json.loads(result.stdout)
    kinds = set()
    untouched = net_zero = 0
    for (seed, k, probe_idx), actual in zip(cases, actual_cases, strict=True):
        expected = generator.build_problem(k, seed, probe_idx)
        expected["prompt"] = generator.main_prompt(
            expected["initial_state"], [text for text, _, _ in expected["ops"]],
            expected["query_entity"],
        )
        expected["states"] = replay(expected)
        expected = json.loads(json.dumps(expected))
        assert actual == expected, f"Mismatch for seed={seed}, k={k}, probe={probe_idx}"
        assert replay(actual) == actual["states"]
        kinds.update(kind for _, _, kind in actual["ops"])
        untouched += actual["n_relevant_ops"] == 0
        net_zero += actual["gold"] == actual["initial_state"][actual["query_entity"]]
    assert kinds == {"gain", "lose", "transfer", "gain_one", "no_transfer"}, kinds
    assert untouched and net_zero, "Keep raw generated tasks without redrawing seeds."
    print(f"PASS: {len(cases)} tasks match Python exactly, including prompts and every state.")
    print("PASS: operation-text replay verifies all answers and all five operation kinds.")
    print("PASS: zero-change tasks keep the requested seed and probe index.")


if __name__ == "__main__":
    main()
