#!/usr/bin/env python3
"""Use a WMIP bank with your own inference function or response JSONL.

No model dependencies are required. Scoring delegates to the release's main
or K/L extension scorer.
All prompts, system turns and item-specific output budgets come from the bank;
your inference function must honor them. Importing saved text cannot verify
which inference settings produced it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_scorer = _module("wmip_score_bank", HERE / "analysis" / "score_bank.py")
_runner = _module("wmip_bank_runner", HERE / "code" / "runner" / "run_wmf_am_bank.py")


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def load_items(source: str | Path | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Load canonical/browser JSONL, or decode rows of the published HF dataset.

    ``load_items(load_dataset("dengzhe-hou/WMIP", split="test"))`` restores
    ``gold_json`` and ``metadata_json`` without changing their types or losing
    the distinction between an absent key and a null value.
    """
    rows = _read_jsonl(source) if isinstance(source, (str, Path)) else source
    items = []
    seen = set()
    for row in rows:
        item = dict(row)
        if "gold_json" in item or "metadata_json" in item:
            required = {"item_id", "block", "prompt", "answer_type", "max_tokens",
                        "gold_json", "metadata_json"}
            missing = required - item.keys()
            if missing:
                raise ValueError(f"HF row is missing fields: {sorted(missing)}")
            unknown = item.keys() - (required | {"system", "source_file"})
            if unknown:
                raise ValueError(f"Unknown HF row fields: {sorted(unknown)}")
            metadata = json.loads(item["metadata_json"])
            if not isinstance(metadata, dict):
                raise ValueError("HF metadata_json must encode an object")
            base = {key: item[key] for key in
                    ("item_id", "block", "prompt", "answer_type", "max_tokens")}
            if metadata.keys() & (base.keys() | {"gold"}):
                raise ValueError("HF metadata_json overlaps the base item fields")
            if item.get("system") != metadata.get("system"):
                raise ValueError(f"{item['item_id']}: HF system differs from metadata_json")
            item = {**metadata, **base, "gold": json.loads(item["gold_json"])}
        missing = {"item_id", "block", "prompt", "gold", "answer_type", "max_tokens"} - item.keys()
        if missing:
            raise ValueError(f"{item.get('item_id', '<item>')}: missing fields: {sorted(missing)}")
        if not isinstance(item["item_id"], str) or not isinstance(item["prompt"], str):
            raise ValueError("item_id and prompt must be strings")
        if item["item_id"] in seen:
            raise ValueError(f"Duplicate item_id: {item['item_id']}")
        if type(item["max_tokens"]) is not int or item["max_tokens"] <= 0:
            raise ValueError(f"{item['item_id']}: max_tokens must be a positive integer")
        seen.add(item["item_id"])
        items.append(item)
    if not items:
        raise ValueError("The bank has no items")
    return items


def write_items(path: str | Path, items: Iterable[Mapping[str, Any]]) -> Path:
    """Export normalized items as canonical JSONL for the existing runner."""
    path = Path(path)
    normalized = load_items(items)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in normalized:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def _record(item: dict[str, Any], result: str | Mapping[str, Any], label: str,
            synthetic: bool, source: str) -> dict[str, Any]:
    result = {"response": result} if isinstance(result, str) else dict(result)
    if "synthetic" in result and result["synthetic"] != synthetic:
        raise ValueError(f"{item['item_id']}: synthetic flag differs; set synthetic explicitly")
    error = result.get("error")
    if error is not None and not isinstance(error, str):
        raise ValueError(f"{item['item_id']}: error must be a string or null")
    response = result.get("response")
    if not isinstance(response, str) and not (response is None and error is not None):
        raise ValueError(f"{item['item_id']}: provide response text, or an explicit error")
    for key in ("prompt", "system", "max_tokens"):
        if key in result and result[key] != item.get(key):
            raise ValueError(f"{item['item_id']}: {key} differs from the bank")
    return {
        "item_id": item["item_id"], "label": label,
        "prompt": item["prompt"], "system": item.get("system"),
        "max_tokens": item["max_tokens"], "gold": item["gold"],
        "answer_type": item["answer_type"], "raw_response": response,
        "finish_reason": result.get("finish_reason"), "error": error,
        "thinking_detected": bool(result.get("thinking_detected")) or "<think>" in (response or ""),
        "synthetic": synthetic, "record_source": source,
        **_runner.score(response, item["gold"], item["answer_type"]),
    }


def evaluate(items: Iterable[Mapping[str, Any]],
             generate: Callable[[dict[str, Any]], str | Mapping[str, Any]],
             out_path: str | Path, label: str, *, synthetic: bool = False) -> Path:
    """Call ``generate(item)`` for each item and write runner-compatible JSONL.

    Return response text, or ``{"response": text, "finish_reason": "stop"}``.
    If a request fails, return ``{"error": "failure description"}``; it remains
    missing during scoring. Unexpected Python exceptions stop the run and leave
    already written records available. Provider telemetry is never invented.
    Pass only prompt/system to the model, never the item's reference answer.
    """
    bank = load_items(items)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for item in bank:
            record = _record(item, generate(dict(item)), label, synthetic, "user-callable")
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
    return out_path


def import_responses(items: Iterable[Mapping[str, Any]], responses: str | Path,
                     out_path: str | Path, label: str, *, synthetic: bool = False) -> Path:
    """Adapt JSONL with item_id + response; finish_reason/error are optional.

    Omitted IDs become explicit missing records. Duplicate or unknown IDs fail.
    Empty response text is an answer, scored by the published rules. Null or
    absent response is accepted only with an explicit error. Without a recorded
    finish_reason, truncation cannot be determined from saved text.
    """
    bank = load_items(items)
    by_id = {item["item_id"]: item for item in bank}
    supplied = {}
    for result in _read_jsonl(responses):
        item_id = result["item_id"]
        if item_id not in by_id:
            raise ValueError(f"Response item_id is not in the bank: {item_id}")
        if item_id in supplied:
            raise ValueError(f"Duplicate response item_id: {item_id}")
        supplied[item_id] = _record(by_id[item_id], result, label, synthetic, "response-import")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for item in bank:
            record = supplied.get(item["item_id"])
            if record is None:
                record = _record(item, {"error": "No response supplied"}, label, synthetic,
                                 "response-import")
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out_path


def score(items: Iterable[Mapping[str, Any]], records_path: str | Path,
          out_dir: str | Path) -> Path:
    """Score with the published main or K/L extension scorer.

    Missing/failed requests are reported separately and excluded from accuracy
    denominators, exactly as in the released scorer. Check coverage before
    comparing accuracy. This also accepts output from the existing API runner.
    Main/budget/browser banks produce six CSV diagnostics. K/L banks use the
    separate extension rules and produce scored_items.csv only; their published
    scorer rejects synthetic records. Mixed main/extension banks are unsupported.
    """
    bank = load_items(items)
    extension = _scoring_family(bank)
    out_dir = Path(out_dir)
    with tempfile.TemporaryDirectory(prefix="wmip-bank-") as temp:
        bank_path = write_items(Path(temp) / "item_bank.jsonl", bank)
        args = ["--bank", str(bank_path), "--out-dir", str(out_dir), str(records_path)]
        if extension:
            subprocess.run([sys.executable, str(HERE / "analysis/score_ext.py"), *args], check=True)
        else:
            _scorer.main(args)
    return out_dir


def _scoring_family(items: list[dict[str, Any]]) -> bool:
    extensions = [item["block"] in ("K", "L") for item in items]
    if any(extensions):
        if not all(extensions):
            raise ValueError("Mixed main and K/L extension banks are unsupported; score them separately")
        return True
    for item in items:
        if "legacy_scoring" not in item:
            raise ValueError(f"{item['item_id']}: main scoring requires legacy_scoring")
        if item["answer_type"] not in {"int", "int_last", "word", "set"}:
            raise ValueError(f"{item['item_id']}: unsupported main answer_type {item['answer_type']!r}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scoring = subparsers.add_parser("score", help="Score your item_id + response JSONL")
    scoring.add_argument("--bank", type=Path, required=True)
    scoring.add_argument("--responses", type=Path, required=True)
    scoring.add_argument("--label", required=True)
    scoring.add_argument("--out-dir", type=Path, required=True)
    scoring.add_argument("--synthetic", action="store_true", help="mark mock data, not model results")
    args = parser.parse_args()
    items = load_items(args.bank)
    _scoring_family(items)
    records = import_responses(items, args.responses, args.out_dir / "responses.jsonl", args.label,
                               synthetic=args.synthetic)
    score(items, records, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
