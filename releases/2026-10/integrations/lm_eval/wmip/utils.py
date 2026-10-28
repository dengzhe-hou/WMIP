"""Item selection and scoring for the WMIP lm-evaluation-harness tasks.

Scoring calls the release's own scorers (analysis/score_bank.py and
analysis/score_ext.py), so these tasks apply exactly the published rules.
This file must stay inside the cloned release tree.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

RELEASE = Path(__file__).resolve().parents[3]


def _module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_wmip = _module("wmip_release", RELEASE / "wmip.py")
_score_bank = _wmip._scorer
_score_ext = _module("wmip_score_ext", RELEASE / "analysis/score_ext.py")


def _item(doc: dict[str, Any]) -> dict[str, Any]:
    """Decode one Hugging Face row into the release's item format."""
    return _wmip.load_items([doc])[0]


def _select(dataset, block: str, max_tokens: int | None = None, condition: str | None = None):
    def keep(doc):
        if doc["block"] != block or (max_tokens is not None and doc["max_tokens"] != max_tokens):
            return False
        return condition is None or json.loads(doc["metadata_json"]).get("condition") == condition
    return dataset.filter(keep)


def core_docs(dataset): return _select(dataset, "A")
def depth_docs(dataset): return _select(dataset, "B")
def arithmetic_docs(dataset): return _select(dataset, "C")
def cancellation_docs(dataset): return _select(dataset, "D")
def assignment_docs(dataset): return _select(dataset, "E")
def sets_counts_16_docs(dataset): return _select(dataset, "F", 16)
def sets_counts_48_docs(dataset): return _select(dataset, "F", 48)
def wordings_docs(dataset): return _select(dataset, "G")
def written_steps_docs(dataset): return _select(dataset, "I")
def large_budget_docs(dataset): return _select(dataset, "A512")
def intermediate_docs(dataset): return _select(dataset, "K")
def multitarget_tracking_docs(dataset): return _select(dataset, "L", condition="tracking")
def multitarget_readout_docs(dataset): return _select(dataset, "L", condition="readout")


def score_one_integer(doc, results):
    """Blocks A-D and G: exactly one integer, equal to the reference."""
    item = _item(doc)
    return {"acc": float(_score_bank.strict_int(results[0], item["gold"]))}


def score_last_integer(doc, results):
    """Written steps: the last integer equals the reference."""
    item = _item(doc)
    return {"acc": float(_score_bank.strict_int_last(results[0], item["gold"]))}


def score_two_parsers(doc, results):
    """Assignment and Sets/counts: both documented parsers, neither primary."""
    scored = _score_bank.score_item(_item(doc), results[0])
    return {"acc_parser1": float(scored["correct_submitted"]),
            "acc_parser2": float(scored["correct_strict"])}


def score_budget(doc, results):
    """Large budget: the core prompt at 512 tokens, under both integer rules."""
    item = _item(doc)
    return {"acc_one_integer": float(_score_bank.strict_int(results[0], item["gold"])),
            "acc_last_integer": float(_score_bank.strict_int_last(results[0], item["gold"]))}


def score_extension(doc, results):
    """Intermediate states (K) and multi-target items (L), extension rules."""
    row = _score_ext.score_record("lm-eval", _item(doc), {"raw_response": results[0]})
    return {"acc": float(row["correct"])}
