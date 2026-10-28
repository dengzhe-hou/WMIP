#!/usr/bin/env python3
"""Evaluate a model on WMIP and compare it with the 18 published models.

``python wmip.py run`` sends every frozen bank to an OpenAI-compatible endpoint,
scores the responses with the published rules and prints a comparison table.
The same module also scores your own inference function or response JSONL.
No model dependencies are required. Scoring delegates to the release's main
or K/L extension scorer.
All prompts, system turns and item-specific output budgets come from the bank;
your inference function must honor them. Importing saved text cannot verify
which inference settings produced it.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import io
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
    """Call ``generate(item)`` and append runner-compatible JSONL, resuming by ID.

    Return response text, or ``{"response": text, "finish_reason": "stop"}``.
    If a request fails, return ``{"error": "failure description"}``; it remains
    missing during scoring. Unexpected Python exceptions stop the run and leave
    already written records available. Rerunning with the same out_path skips
    every error-free response, including empty, incorrect or truncated answers,
    and appends retries for failed or absent items without rewriting any record.
    All saved records must match the current label, synthetic flag and bank
    fields before any callback runs. Items not yet recorded use the current bank.
    Use a fresh out_path if you change your model or inference settings; Python
    callback settings cannot be inspected. Provider telemetry is never invented.
    Pass only prompt/system to the model, never the item's reference answer.
    Reasoning traces remain subject to the released scorer's rejection rule.
    """
    bank = load_items(items)
    out_path = Path(out_path)
    done = _completed_items(bank, out_path, label, synthetic)
    pending = [item for item in bank if item["item_id"] not in done]
    if not pending:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as handle:
        for item in pending:
            record = _record(item, generate(dict(item)), label, synthetic, "user-callable")
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
    return out_path


def _completed_items(bank: list[dict[str, Any]], out_path: Path,
                     label: str, synthetic: bool) -> set[str]:
    """Validate existing records before spending any further model calls."""
    if not out_path.exists():
        return set()
    by_id = {item["item_id"]: item for item in bank}
    done = set()
    for record in _read_jsonl(out_path):
        item_id = record.get("item_id")
        if item_id not in by_id:
            raise ValueError(f"{out_path}: saved item_id is not in the bank: {item_id}; "
                             "use a fresh out_path")
        item = by_id[item_id]
        expected = {key: item.get(key) for key in
                    ("prompt", "system", "max_tokens", "gold", "answer_type")}
        expected.update(label=label, synthetic=synthetic)
        for key, value in expected.items():
            saved = record.get(key, False) if key == "synthetic" else record.get(key)
            if type(saved) is not type(value) or saved != value:
                raise ValueError(f"{out_path}: {item_id}: {key} differs; use a fresh out_path")
        if "error" not in record:
            raise ValueError(f"{out_path}: {item_id}: saved record is missing error; "
                             "use a fresh out_path")
        if record["error"] is not None:
            if not isinstance(record["error"], str):
                raise ValueError(f"{out_path}: {item_id}: error must be a string or null; "
                                 "use a fresh out_path")
            continue
        if not isinstance(record.get("raw_response"), str):
            raise ValueError(f"{out_path}: {item_id}: completed record needs raw_response text; "
                             "use a fresh out_path")
        if item_id in done:
            raise ValueError(f"{out_path}: two final records for {item_id}; use a fresh out_path")
        done.add(item_id)
    return done


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


# ── Full evaluation and comparison with the published panel ──────────────────

# The three frozen banks of the paper, in run order.
BANKS = {
    "main": HERE / "data/item_bank/item_bank.jsonl",      # 840 items, blocks A-I
    "budget": HERE / "data/item_bank/budget_bank.jsonl",  # 60 core items at 512 tokens
    "ext": HERE / "data/item_bank/ext_bank.jsonl",        # 180 intermediate-state and multi-target items
}
# Comparison columns: (key, heading, bank, rule).
METRICS = [
    ("core", "Core", "main", "A, one integer, 16 tokens"),
    ("arithmetic", "Arith.", "main", "C, single-step arithmetic"),
    ("cancellation", "Cancel.", "main", "D, updates with no net change"),
    ("written_steps", "Steps", "main", "I, written steps, last integer, 512 tokens"),
    ("budget_last", "Budget", "budget", "core prompt, 512 tokens, last integer"),
    ("intermediate", "Interm.", "ext", "K, earlier state, one integer"),
    ("tracking", "Track", "ext", "L, M targets tracked, exact ordered list"),
    ("readout", "Readout", "ext", "L, readout control, exact ordered list"),
]


def run(base_url: str, model: str, out_dir: str | Path, *, label: str | None = None,
        banks: Iterable[str] = BANKS, runner_args: Iterable[str] = ()) -> int:
    """Query one OpenAI-compatible endpoint on every frozen bank, then compare.

    Each bank goes through the released runner with its own output file, so a
    rerun of the same command resumes unfinished requests. ``runner_args`` are
    passed through (``--api-key-env``, ``--extra-body``, ``--concurrency`` ...).
    Returns the runner's worst exit code: 0 complete, 1 items missing, 2 aborted.
    """
    out_dir = Path(out_dir)
    label = label or model
    worst = 0
    for name in banks:
        print(f"\n== {name} bank ({BANKS[name].name}) ==")
        code = _runner.main(["--bank", str(BANKS[name]), "--out", str(out_dir / f"{name}.jsonl"),
                             "--base-url", base_url, "--model", model, "--label", label,
                             *runner_args])
        worst = max(worst, code)
        if code == 2:
            print(f"Stopped at the {name} bank; fix the reported problem and rerun the same command.")
            return code
    compare(out_dir)
    return worst


def _ratio(correct: int, scored: int) -> float | None:
    return correct / scored if scored else None


def _your_scores(run_dir: Path) -> tuple[str, dict[str, float | None], dict[str, str]]:
    """Score the run's response files with the published rules for each bank."""
    scores: dict[str, float | None] = {}
    coverage: dict[str, str] = {}
    labels = set()
    main_file = run_dir / "main.jsonl"
    if main_file.exists():
        with contextlib.redirect_stdout(io.StringIO()):
            _scorer.main(["--bank", str(BANKS["main"]), "--out-dir", str(run_dir / "scores/main"),
                          str(main_file)])
        (label, blocks), = _by_model(run_dir / "scores/main/accuracy_by_block.csv").items()
        labels.add(label)
        for key, block in (("core", "A"), ("arithmetic", "C"), ("cancellation", "D"),
                           ("written_steps", "I")):
            row = blocks[block]
            scores[key] = _ratio(int(row["n_correct_strict"]), int(row["n_scored"]))
            coverage[key] = f"{row['n_scored']}/{row['n_items']}"
    budget_file = run_dir / "budget.jsonl"
    if budget_file.exists():
        bank = {item["item_id"]: item for item in _scorer.load_bank(BANKS["budget"])}
        label, final, _ = _scorer.load_output(budget_file, bank)
        labels.add(label)
        correct = sum(_scorer.strict_int_last(record["raw_response"], bank[item_id]["gold"])
                      for item_id, record in final.items())
        scores["budget_last"] = _ratio(correct, len(final))
        coverage["budget_last"] = f"{len(final)}/{len(bank)}"
    ext_file = run_dir / "ext.jsonl"
    if ext_file.exists():
        subprocess.run([sys.executable, str(HERE / "analysis/score_ext.py"), "--bank", str(BANKS["ext"]),
                        "--out-dir", str(run_dir / "scores/ext"), str(ext_file)],
                       check=True, stdout=subprocess.DEVNULL)
        with (run_dir / "scores/ext/scored_items.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        labels.update(row["model"] for row in rows)
        for key, keep in (("intermediate", lambda r: r["block"] == "K"),
                          ("tracking", lambda r: r["condition"] == "tracking"),
                          ("readout", lambda r: r["condition"] == "readout")):
            cell = [r for r in rows if keep(r)]
            answered = [r for r in cell if r["status"] == "answered"]
            scores[key] = _ratio(sum(int(r["correct"]) for r in answered), len(answered))
            coverage[key] = f"{len(answered)}/{len(cell)}"
    if not scores:
        raise ValueError(f"{run_dir}: no main.jsonl, budget.jsonl or ext.jsonl to compare")
    if len(labels) != 1:
        raise ValueError(f"{run_dir}: response files carry different labels: {sorted(labels)}")
    return labels.pop(), scores, coverage


def _by_model(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    table: dict[str, dict[str, dict[str, str]]] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            table.setdefault(row["model"], {})[row["block"]] = row
    return table


def published_scores() -> dict[str, dict[str, float]]:
    """Per-model accuracies of the 18 published models, from the stored results."""
    names = {}
    with (HERE / "analysis/results/BFCL_INPUTS_20261004.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            names[row["run_label"]] = row["model"].replace("-Instruct", "").replace("-350m", "-350M")
    table = {names[model]: {} for model in names}
    for model, blocks in _by_model(HERE / "data/scored/accuracy_by_block.csv").items():
        for key, block in (("core", "A"), ("arithmetic", "C"), ("cancellation", "D"),
                           ("written_steps", "I")):
            table[names[model]][key] = int(blocks[block]["n_correct_strict"]) / int(blocks[block]["n_scored"])
    with (HERE / "analysis/results/budget/by_model.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            table[names[row["model"]]]["budget_last"] = int(row["A512_last"]) / 60
    with (HERE / "analysis/results/ext/accuracy_by_model.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            def total(columns: list[str]) -> float:
                parts = [row[column].split("/") for column in columns]
                return sum(int(a) for a, _ in parts) / sum(int(b) for _, b in parts)
            entry = table[names[row["model"]]]
            entry["intermediate"] = total(["K_q1", "K_q2", "K_q3"])
            entry["tracking"] = total([f"L_M{m}_tracking" for m in (1, 2, 4)])
            entry["readout"] = total([f"L_M{m}_readout" for m in (1, 2, 4)])
    return table


def compare(run_dir: str | Path) -> Path:
    """Print your model among the 18 published models and write comparison.csv."""
    run_dir = Path(run_dir)
    label, mine, coverage = _your_scores(run_dir)
    panel = published_scores()
    if label in panel:
        raise ValueError(f"label {label!r} equals a published model name; rerun with another --label")
    rows = sorted([(name, values, False) for name, values in panel.items()] + [(label, mine, True)],
                  key=lambda row: -(row[1].get("core") if row[1].get("core") is not None else -1))
    columns = [metric for metric in METRICS if metric[0] in mine]

    def cell(value: float | None) -> str:
        return "-" if value is None else f"{100 * value:.1f}"

    print("\nAccuracy (%) with the published scoring rules. Rows are sorted by Core.")
    print(f"{'':2s}{'Model':24s}" + "".join(f"{heading:>9s}" for _, heading, _, _ in columns))
    for name, values, yours in rows:
        print(f"{'>' if yours else '':2s}{name[:24]:24s}"
              + "".join(f"{cell(values.get(key)):>9s}" for key, _, _, _ in columns))
    if "core" in mine and mine["core"] is not None:
        rank = 1 + sum(values["core"] > mine["core"] for values in panel.values())
        print(f"\n{label}: Core rank {rank} of {len(panel) + 1}.")
    incomplete = {key: cover for key, cover in coverage.items()
                  if cover.split("/")[0] != cover.split("/")[1]}
    if incomplete:
        print("Incomplete coverage (scored/total), excluded from accuracy: "
              + ", ".join(f"{key} {cover}" for key, cover in incomplete.items())
              + ". Rerun the same command to retry missing requests.")
    print("Columns: " + "; ".join(f"{heading} = {rule}" for _, heading, _, rule in columns) + ".")
    path = run_dir / "comparison.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "yours", *[key for key, _, _, _ in columns]])
        for name, values, yours in rows:
            writer.writerow([name, int(yours), *[blank_ratio(values.get(key)) for key, _, _, _ in columns]])
    print(f"written to {path}")
    return path


def blank_ratio(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    running = subparsers.add_parser(
        "run", help="Run all frozen banks on an OpenAI-compatible endpoint and compare",
        description="Run the main, large-budget and extension banks on one endpoint, score them "
                    "with the published rules and print your model among the 18 published models. "
                    "Other runner options (--api-key-env, --extra-body, --temperature, "
                    "--concurrency, --timeout ...) are passed through.")
    running.add_argument("--base-url", required=True)
    running.add_argument("--model", required=True)
    running.add_argument("--label", help="name for your model (default: --model)")
    running.add_argument("--out-dir", type=Path, required=True)
    running.add_argument("--banks", default="main,budget,ext",
                         help="comma-separated subset of main,budget,ext")
    comparing = subparsers.add_parser("compare", help="Reprint the comparison for a finished run")
    comparing.add_argument("--run-dir", type=Path, required=True)
    scoring = subparsers.add_parser("score", help="Score your item_id + response JSONL")
    scoring.add_argument("--bank", type=Path, required=True)
    scoring.add_argument("--responses", type=Path, required=True)
    scoring.add_argument("--label", required=True)
    scoring.add_argument("--out-dir", type=Path, required=True)
    scoring.add_argument("--synthetic", action="store_true", help="mark mock data, not model results")
    args, passthrough = parser.parse_known_args()
    if args.command == "run":
        banks = [name.strip() for name in args.banks.split(",") if name.strip()]
        unknown = set(banks) - set(BANKS)
        if unknown or not banks:
            parser.error(f"--banks must name main, budget or ext; got {args.banks!r}")
        return run(args.base_url, args.model, args.out_dir, label=args.label, banks=banks,
                   runner_args=passthrough)
    if passthrough:
        parser.error(f"unrecognized arguments: {' '.join(passthrough)}")
    if args.command == "compare":
        compare(args.run_dir)
        return 0
    items = load_items(args.bank)
    _scoring_family(items)
    records = import_responses(items, args.responses, args.out_dir / "responses.jsonl", args.label,
                               synthetic=args.synthetic)
    score(items, records, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
