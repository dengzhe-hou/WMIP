"""WMIP tasks for Inspect (https://inspect.aisi.org.uk).

    inspect eval integrations/inspect/wmip_inspect.py@wmip -T task=core --model <provider/model>

Items come from the frozen release banks and are scored by the release's own
scorers, so prompts, system turns, output budgets and scoring rules match the
paper. Each task is one block with one output budget; the paper never pools
tasks. Run from a clone of the release; this file must stay inside it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, ContentReasoning, GenerateConfig
from inspect_ai.scorer import Score, Target, accuracy, scorer, stderr
from inspect_ai.solver import TaskState, generate

RELEASE = Path(__file__).resolve().parents[2]


def _module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_wmip = _module("wmip_release", RELEASE / "wmip.py")
_score_bank = _wmip._scorer
_score_ext = _module("wmip_score_ext", RELEASE / "analysis/score_ext.py")

# task name: (bank, block, output budget, condition, rule)
TASKS = {
    "core": ("main", "A", 16, None, "one_integer"),
    "depth": ("main", "B", 16, None, "one_integer"),
    "arithmetic": ("main", "C", 16, None, "one_integer"),
    "cancellation": ("main", "D", 16, None, "one_integer"),
    "assignment": ("main", "E", 16, None, "two_parsers"),
    "sets_counts_16": ("main", "F", 16, None, "two_parsers"),
    "sets_counts_48": ("main", "F", 48, None, "two_parsers"),
    "wordings": ("main", "G", 16, None, "one_integer"),
    "instructions": ("main", "H", 16, None, "one_integer"),
    "written_steps": ("main", "I", 512, None, "last_integer"),
    "large_budget": ("budget", "A512", 512, None, "both_integer_rules"),
    "intermediate": ("ext", "K", 16, None, "extension"),
    "multitarget_tracking": ("ext", "L", 48, "tracking", "extension"),
    "multitarget_readout": ("ext", "L", 48, "readout", "extension"),
}


@task
def wmip(task: str = "core") -> Task:
    if task not in TASKS:
        raise ValueError(f"task must be one of {', '.join(TASKS)}; got {task!r}")
    bank, block, budget, condition, rule = TASKS[task]
    items = [item for item in _wmip.load_items(_wmip.BANKS[bank])
             if item["block"] == block and item["max_tokens"] == budget
             and (condition is None or item.get("condition") == condition)]
    samples = []
    for item in items:
        messages = ([ChatMessageSystem(content=item["system"])] if item.get("system") else [])
        messages.append(ChatMessageUser(content=item["prompt"]))
        samples.append(Sample(id=item["item_id"], input=messages, target=json.dumps(item["gold"]),
                              metadata={"item": item}))
    return Task(dataset=MemoryDataset(samples, name=f"wmip_{task}"), solver=generate(),
                scorer=_SCORERS[rule](), config=GenerateConfig(temperature=0, max_tokens=budget),
                name=f"wmip_{task}")


def _answer(state: TaskState) -> tuple[str, dict[str, Any]]:
    """The response text, refusing reasoning traces as the released runner does."""
    message = state.output.message
    if any(isinstance(part, ContentReasoning) for part in message.content if not isinstance(message.content, str)):
        raise RuntimeError(f"{state.sample_id}: reasoning trace in the response; thinking must be off")
    text = state.output.completion
    if "<think>" in text:
        raise RuntimeError(f"{state.sample_id}: reasoning trace in the response; thinking must be off")
    return text, {"truncated": state.output.stop_reason == "max_tokens", "response": text}


@scorer(metrics=[accuracy(), stderr()])
def one_integer():
    async def score(state: TaskState, target: Target) -> Score:
        text, meta = _answer(state)
        return Score(value=float(_score_bank.strict_int(text, state.metadata["item"]["gold"])), metadata=meta)
    return score


@scorer(metrics=[accuracy(), stderr()])
def last_integer():
    async def score(state: TaskState, target: Target) -> Score:
        text, meta = _answer(state)
        return Score(value=float(_score_bank.strict_int_last(text, state.metadata["item"]["gold"])), metadata=meta)
    return score


@scorer(metrics={"parser1": [accuracy(), stderr()], "parser2": [accuracy(), stderr()]})
def two_parsers():
    async def score(state: TaskState, target: Target) -> Score:
        text, meta = _answer(state)
        scored = _score_bank.score_item(state.metadata["item"], text)
        return Score(value={"parser1": float(scored["correct_submitted"]),
                            "parser2": float(scored["correct_strict"])}, metadata=meta)
    return score


@scorer(metrics={"one_integer": [accuracy(), stderr()], "last_integer": [accuracy(), stderr()]})
def both_integer_rules():
    async def score(state: TaskState, target: Target) -> Score:
        text, meta = _answer(state)
        gold = state.metadata["item"]["gold"]
        return Score(value={"one_integer": float(_score_bank.strict_int(text, gold)),
                            "last_integer": float(_score_bank.strict_int_last(text, gold))}, metadata=meta)
    return score


@scorer(metrics=[accuracy(), stderr()])
def extension():
    async def score(state: TaskState, target: Target) -> Score:
        text, meta = _answer(state)
        row = _score_ext.score_record("inspect", state.metadata["item"], {"raw_response": text})
        return Score(value=float(row["correct"]), metadata=meta)
    return score


_SCORERS = {"one_integer": one_integer, "last_integer": last_integer, "two_parsers": two_parsers,
            "both_integer_rules": both_integer_rules, "extension": extension}
