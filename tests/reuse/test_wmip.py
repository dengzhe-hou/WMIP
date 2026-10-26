"""Offline tests for the public callable/response adapter; no model calls."""

import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "releases/2026-10"
spec = importlib.util.spec_from_file_location("wmip", RELEASE / "wmip.py")
wmip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wmip)


class PublicReuseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = wmip.load_items(RELEASE / "data/item_bank/item_bank.jsonl")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def write_answers(self, rows):
        path = self.directory / "answers.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def csv_rows(self, path):
        with path.open(encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_callable_preserves_protocol_and_matches_existing_scoring(self):
        items = [next(item for item in self.items if item["block"] == block)
                 for block in "AEFGHI"]
        seen = []

        def generate(item):
            seen.append(item)
            gold = item["gold"]
            answer = ", ".join(gold) if isinstance(gold, list) else str(gold)
            if item["answer_type"] == "int_last":
                answer = "State 1 was updated; final answer: " + answer
            return {"response": answer, "finish_reason": "length"}

        records = wmip.evaluate(items, generate, self.directory / "records.jsonl", "mock",
                                synthetic=True)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            wmip.score(items, records, self.directory / "scores")
        self.assertIn("SYNTHETIC", output.getvalue())
        self.assertEqual(seen, items)
        stored = wmip._read_jsonl(records)
        scored = self.csv_rows(self.directory / "scores/scored_items.csv")
        for item, record, row in zip(items, stored, scored):
            self.assertEqual(record["prompt"], item["prompt"])
            self.assertEqual(record["system"], item.get("system"))
            self.assertEqual(record["max_tokens"], item["max_tokens"])
            self.assertEqual(record["finish_reason"], "length")
            self.assertNotIn("usage", record)
            expected = wmip._scorer.score_item(item, record["raw_response"])
            self.assertEqual(row["correct_strict"], str(int(expected["correct_strict"])))
            self.assertEqual(row["correct_submitted"], str(int(expected["correct_submitted"])))
            self.assertEqual(row["truncated"], "1")
            self.assertEqual(row["synthetic"], "1")

    def test_response_import_keeps_failed_and_omitted_items_missing(self):
        items = self.items[:3]
        answers = self.write_answers([
            {"item_id": items[0]["item_id"], "response": str(items[0]["gold"])},
            {"item_id": items[1]["item_id"], "error": "Request timed out"},
        ])
        records = wmip.import_responses(items, answers, self.directory / "records.jsonl", "mock",
                                        synthetic=True)
        with contextlib.redirect_stdout(io.StringIO()):
            wmip.score(items, records, self.directory / "scores")
        rows = self.csv_rows(self.directory / "scores/scored_items.csv")
        self.assertEqual([row["status"] for row in rows], ["scored", "missing", "missing"])
        counts = self.csv_rows(self.directory / "scores/accuracy_by_block.csv")[0]
        self.assertEqual(counts["n_scored"], "1")
        self.assertEqual(counts["n_missing"], "2")
        self.assertEqual(counts["acc_strict"], "1.000000")
        self.assertEqual(wmip._read_jsonl(records)[2]["error"], "No response supplied")
        self.assertIsNone(wmip._read_jsonl(records)[0]["finish_reason"])

    def test_all_missing_input_is_explicit_and_scores_no_denominator(self):
        records = wmip.import_responses(self.items[:1], self.write_answers([]),
                                        self.directory / "records.jsonl", "mock", synthetic=True)
        with contextlib.redirect_stdout(io.StringIO()):
            wmip.score(self.items[:1], records, self.directory / "scores")
        counts = self.csv_rows(self.directory / "scores/accuracy_by_block.csv")[0]
        self.assertEqual(counts["n_missing"], "1")
        self.assertEqual(counts["acc_strict"], "")

    def test_empty_string_is_wrong_not_missing(self):
        records = wmip.evaluate(self.items[:1], lambda item: "", self.directory / "records.jsonl",
                                "mock", synthetic=True)
        with contextlib.redirect_stdout(io.StringIO()):
            wmip.score(self.items[:1], records, self.directory / "scores")
        row = self.csv_rows(self.directory / "scores/scored_items.csv")[0]
        self.assertEqual((row["status"], row["correct_strict"]), ("scored", "0"))

    def test_response_import_rejects_unknown_duplicate_or_mismatched_protocol(self):
        item = self.items[0]
        base = {"item_id": item["item_id"], "response": "12"}
        invalid = [
            ([{**base, "item_id": "not-in-bank"}], "not in the bank"),
            ([base, base], "Duplicate"),
            ([{**base, "max_tokens": 512}], "max_tokens differs"),
            ([{"item_id": item["item_id"], "response": None}], "explicit error"),
            ([{**base, "synthetic": True}], "synthetic flag differs"),
        ]
        for rows, message in invalid:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                wmip.import_responses([item], self.write_answers(rows),
                                      self.directory / "records.jsonl", "model")

    def test_reasoning_is_rejected_by_existing_protocol_check(self):
        records = wmip.evaluate(self.items[:1], lambda item: "<think>work</think>12",
                                self.directory / "records.jsonl", "mock", synthetic=True)
        with self.assertRaisesRegex(SystemExit, "thinking must be off"):
            wmip.score(self.items[:1], records, self.directory / "scores")

    def test_imported_published_model_matches_original_scorer_for_all_840_items(self):
        released = RELEASE / "data/responses/local/qwen3-4b-instruct-2507.jsonl"
        original = wmip._read_jsonl(released)
        answers = self.write_answers([
            {"item_id": row["item_id"], "response": row["raw_response"],
             "error": row["error"], "finish_reason": row.get("finish_reason"),
             "thinking_detected": row["thinking_detected"]}
            for row in original
        ])
        records = wmip.import_responses(self.items, answers, self.directory / "records.jsonl",
                                        original[0]["label"])
        with contextlib.redirect_stdout(io.StringIO()):
            wmip.score(self.items, records, self.directory / "adapted")
            wmip.score(self.items, released, self.directory / "original")
        for path in (self.directory / "original").glob("*.csv"):
            self.assertEqual((self.directory / "adapted" / path.name).read_bytes(), path.read_bytes(),
                             path.name)

    def test_hf_decode_is_lossless_for_all_banks_and_types(self):
        for path in sorted((RELEASE / "data/item_bank").glob("*.jsonl")):
            items = wmip.load_items(path)
            rows = []
            for item in items:
                base = {key: item[key] for key in
                        ("item_id", "block", "prompt", "answer_type", "max_tokens")}
                metadata = {key: value for key, value in item.items() if key not in base and key != "gold"}
                rows.append({**base, "gold_json": json.dumps(item["gold"]),
                             "metadata_json": json.dumps(metadata), "system": item.get("system"),
                             "source_file": "data/item_bank/" + path.name})
            with self.subTest(bank=path.name):
                self.assertEqual(wmip.load_items(rows), items)
                exported = wmip.write_items(self.directory / path.name, rows)
                self.assertEqual(wmip.load_items(exported), items)

    def test_hf_mismatch_or_unknown_schema_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "HF row is missing fields"):
            wmip.load_items([{"gold_json": "12"}])

    def test_extensions_dispatch_to_existing_scorer_on_released_responses(self):
        items = wmip.load_items(RELEASE / "data/item_bank/ext_bank.jsonl")
        released = RELEASE / "data/responses/ext/local/qwen3-4b-instruct-2507.jsonl"
        wmip.score(items, released, self.directory / "scores")
        actual = self.csv_rows(self.directory / "scores/scored_items.csv")
        stored = self.csv_rows(RELEASE / "data/scored/ext/scored_items.csv")
        expected = [row for row in stored if row["model"] == "qwen3-4b-instruct-2507"]
        self.assertEqual(actual, expected)
        self.assertEqual(len(list((self.directory / "scores").glob("*.csv"))), 1)

    def test_extensions_keep_existing_synthetic_rejection_and_reject_mixed_banks(self):
        items = wmip.load_items(RELEASE / "data/item_bank/ext_bank.jsonl")
        records = wmip.evaluate(items[:1], lambda item: "0", self.directory / "records.jsonl",
                                "mock", synthetic=True)
        with self.assertRaises(subprocess.CalledProcessError):
            wmip.score(items, records, self.directory / "scores")
        with self.assertRaisesRegex(ValueError, "Mixed main and K/L"):
            wmip.score(items + self.items, records, self.directory / "scores")

    def test_cli_import_scores_single_item_subset(self):
        bank = wmip.write_items(self.directory / "bank.jsonl", self.items[:1])
        answers = self.write_answers([{"item_id": self.items[0]["item_id"], "response": "12"}])
        result = subprocess.run([
            sys.executable, str(RELEASE / "wmip.py"), "score", "--bank", str(bank),
            "--responses", str(answers), "--label", "mock", "--out-dir", str(self.directory / "scores"),
            "--synthetic"], capture_output=True, text=True, check=True)
        self.assertIn("SYNTHETIC", result.stdout)
        self.assertTrue((self.directory / "scores/responses.jsonl").exists())
        self.assertEqual(len(list((self.directory / "scores").glob("*.csv"))), 6)
        self.assertEqual(self.csv_rows(self.directory / "scores/scored_items.csv")[0]["correct_strict"], "1")


if __name__ == "__main__":
    unittest.main()
