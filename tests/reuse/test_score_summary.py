"""Subset scoring and readable task summaries, using offline data only."""

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
spec = importlib.util.spec_from_file_location("wmip_summary", RELEASE / "wmip.py")
wmip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wmip)


class TaskSummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = wmip.load_items(RELEASE / "data/item_bank/item_bank.jsonl")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def csv_rows(self, path):
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def score_subset(self, items, generate):
        records = wmip.evaluate(items, generate, self.directory / (items[0]["item_id"] + ".jsonl"),
                                "offline-fixture", synthetic=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            wmip.score(items, records, self.directory / "scores")
        return output.getvalue(), self.csv_rows(self.directory / "scores/scored_items.csv")

    def test_written_steps_only_uses_last_integer_without_core_or_int_items(self):
        item = next(item for item in self.items if item["block"] == "I")
        output, rows = self.score_subset([item], lambda item: {
            "response": f"After state 12345, the answer is {item['gold']}",
            "finish_reason": "length",
        })
        self.assertIn("I Written steps", output)
        self.assertIn("1/1", output)
        self.assertIn("100.0%", output)
        self.assertNotIn("A Core", output)
        self.assertEqual(rows[0]["rule_strict"], "last_integer")
        self.assertEqual(rows[0]["correct_strict"], "1")
        self.assertEqual(rows[0]["truncated"], "1")
        self.assertEqual(self.csv_rows(self.directory / "scores/compliance.csv"), [])

    def test_assignment_and_sets_subsets_display_both_existing_parsers(self):
        assignment = next(item for item in self.items if item["block"] == "E")
        other = next(word for word in assignment["vocab"] if word != assignment["gold"])
        sets = next(item for item in self.items if item["block"] == "F"
                    and isinstance(item["gold"], list) and len(item["gold"]) > 1)
        cases = [(assignment, f"{assignment['gold']} or {other}", "Assignment", "1", "0"),
                 (sets, " and ".join(sets["gold"]), "Sets/counts", "0", "1")]
        for item, response, name, parser1, parser2 in cases:
            with self.subTest(task=name):
                output, rows = self.score_subset([item], lambda item: response)
                self.assertIn(name, output)
                self.assertIn("Parser 1", output)
                self.assertIn("Parser 2", output)
                self.assertEqual(rows[0]["correct_submitted"], parser1)
                self.assertEqual(rows[0]["correct_strict"], parser2)
                line = next(line for line in output.splitlines() if line.startswith(item["block"] + " "))
                self.assertEqual(line.split()[-4:], ["-", f"{100 * int(parser1):.1f}%",
                                                     f"{100 * int(parser2):.1f}%", "0"])

    def test_missing_subset_has_coverage_and_no_accuracy_denominator(self):
        items = [item for item in self.items if item["block"] == "I"][:3]
        answers = self.directory / "answers.jsonl"
        answers.write_text(json.dumps({"item_id": items[0]["item_id"],
                                       "error": "offline fixture timeout"}) + "\n", encoding="utf-8")
        records = wmip.import_responses(items, answers, self.directory / "responses.jsonl",
                                        "offline-fixture", synthetic=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            wmip.score(items, records, self.directory / "scores")
        line = next(line for line in output.getvalue().splitlines() if line.startswith("I Written steps"))
        self.assertEqual(line.split()[-4:], ["0/3", "3", "-", "0"])
        counts = self.csv_rows(self.directory / "scores/accuracy_by_block.csv")[0]
        self.assertEqual((counts["n_scored"], counts["n_missing"], counts["acc_strict"]),
                         ("0", "3", ""))

    def test_large_budget_uses_existing_one_integer_scoring(self):
        item = wmip.load_items(RELEASE / "data/item_bank/budget_bank.jsonl")[0]
        output, rows = self.score_subset([item], lambda item: f"1, then {item['gold']}")
        self.assertIn("A512 Large budget", output)
        self.assertIn("0.0%", output)
        self.assertEqual(rows[0]["rule_strict"], "one_integer")
        self.assertEqual(rows[0]["correct_strict"], "0")

    def test_full_bank_values_match_all_six_released_tables(self):
        outputs = sorted((RELEASE / "data/responses/local").glob("*.jsonl"))
        outputs += sorted((RELEASE / "data/responses/api").glob("*.jsonl"))
        with contextlib.redirect_stdout(io.StringIO()):
            wmip._scorer.main(["--out-dir", str(self.directory / "scores"), *map(str, outputs)])
        files = list((self.directory / "scores").glob("*.csv"))
        self.assertEqual(len(files), 6)
        for path in files:
            with self.subTest(table=path.name):
                # The archived tables have a different model order; every field must match.
                expected = self.csv_rows(RELEASE / "data/scored" / path.name)
                actual = self.csv_rows(path)
                order = lambda row: tuple(row.items())
                self.assertEqual(sorted(actual, key=order), sorted(expected, key=order))

    def test_extension_subsets_show_named_tasks_and_missing_coverage(self):
        bank = wmip.load_items(RELEASE / "data/item_bank/ext_bank.jsonl")
        original = wmip._read_jsonl(RELEASE / "data/responses/ext/local/qwen3-4b-instruct-2507.jsonl")
        by_id = {record["item_id"]: record for record in original}
        for block, name in [("K", "Intermediate states"), ("L", "Multi-target")]:
            items = [item for item in bank if item["block"] == block][:2]
            for all_missing in (False, True):
                with self.subTest(block=block, all_missing=all_missing):
                    record = dict(by_id[items[0]["item_id"]])
                    if all_missing:
                        record["error"] = "offline fixture timeout"
                    bank_path = wmip.write_items(self.directory / "bank.jsonl", items)
                    records_path = self.directory / "records.jsonl"
                    records_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
                    result = subprocess.run([
                        sys.executable, str(RELEASE / "analysis/score_ext.py"), "--bank", str(bank_path),
                        "--out-dir", str(self.directory / "ext-scores"), str(records_path),
                    ], capture_output=True, text=True, check=True)
                    line = next(line for line in result.stdout.splitlines() if line.startswith(block + " " + name))
                    coverage = "0/2" if all_missing else "1/2"
                    self.assertIn(coverage, line)
                    rows = self.csv_rows(self.directory / "ext-scores/scored_items.csv")
                    self.assertEqual(sum(row["status"] == "missing" for row in rows), 2 if all_missing else 1)
                    if all_missing:
                        self.assertEqual(line.split()[-2], "-")
                    else:
                        expected = wmip._read_jsonl(records_path)[0]
                        self.assertEqual(rows[0]["raw_response"], expected["raw_response"])


if __name__ == "__main__":
    unittest.main()
