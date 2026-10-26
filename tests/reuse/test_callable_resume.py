"""Deterministic callable resume checks; no model or network requests."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "releases/2026-10"
spec = importlib.util.spec_from_file_location("wmip_resume", RELEASE / "wmip.py")
wmip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wmip)


class CallableResumeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "responses.jsonl"
        self.items = wmip.load_items(RELEASE / "data/item_bank/item_bank.jsonl")[:3]

    def evaluate(self, generate, items=None, **kwargs):
        return wmip.evaluate(self.items if items is None else items, generate,
                             self.path, kwargs.pop("label", "model"), **kwargs)

    def test_exception_leaves_progress_and_resume_appends_only_absent_items(self):
        called = []

        def interrupted(item):
            called.append(item["item_id"])
            if len(called) == 2:
                raise RuntimeError("Model process stopped")
            return str(item["gold"])

        with self.assertRaisesRegex(RuntimeError, "Model process stopped"):
            self.evaluate(interrupted)
        before = self.path.read_bytes()
        self.assertEqual(len(wmip._read_jsonl(self.path)), 1)
        resumed = []

        def generate(item):
            resumed.append(item["item_id"])
            return str(item["gold"])

        self.assertEqual(self.evaluate(generate), self.path)
        self.assertEqual(resumed, [item["item_id"] for item in self.items[1:]])
        self.assertTrue(self.path.read_bytes().startswith(before))
        self.assertEqual([row["item_id"] for row in wmip._read_jsonl(self.path)],
                         [item["item_id"] for item in self.items])

    def test_error_is_retried_and_all_prior_attempts_remain_available(self):
        failed_id = self.items[0]["item_id"]
        self.evaluate(lambda item: {"error": "Timed out"} if item["item_id"] == failed_id
                      else str(item["gold"]))
        before = self.path.read_bytes()
        called = []

        def generate(item):
            called.append(item["item_id"])
            return str(item["gold"])

        self.evaluate(generate)
        rows = wmip._read_jsonl(self.path)
        self.assertEqual(called, [failed_id])
        self.assertTrue(self.path.read_bytes().startswith(before))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["error"], "Timed out")
        self.assertEqual((rows[-1]["item_id"], rows[-1]["error"]), (failed_id, None))
        with contextlib.redirect_stdout(io.StringIO()):
            wmip.score(self.items, self.path, self.directory / "scores")
        # The original scorer must see one final response per item despite the
        # retained failed attempt, with the same denominator as a clean run.
        label, scored, synthetic = wmip._scorer.load_output(
            self.path, {item["item_id"]: item for item in self.items})
        self.assertEqual(label, "model")
        self.assertFalse(synthetic)
        self.assertEqual(len(scored), 3)
        completed = self.path.read_bytes()
        self.evaluate(lambda item: self.fail("Successful retry was requested again"))
        self.assertEqual(self.path.read_bytes(), completed)

    def test_repeated_failure_is_attempted_once_per_invocation(self):
        called = []

        def failed(item):
            called.append(item["item_id"])
            return {"error": "Endpoint unavailable"}

        self.evaluate(failed)
        self.assertEqual(called, [item["item_id"] for item in self.items])
        before = self.path.read_bytes()
        called.clear()
        self.evaluate(failed)
        self.assertEqual(called, [item["item_id"] for item in self.items])
        self.assertTrue(self.path.read_bytes().startswith(before))
        self.assertEqual(len(wmip._read_jsonl(self.path)), 6)

    def test_empty_wrong_and_truncated_answers_are_completed_noop_on_rerun(self):
        answers = iter(["", "no answer", {"response": "12", "finish_reason": "length"}])
        self.evaluate(lambda item: next(answers))
        before = self.path.read_bytes()

        def should_not_run(item):
            self.fail("A completed response was requested again")

        self.evaluate(should_not_run)
        self.assertEqual(self.path.read_bytes(), before)

    def test_saved_configuration_mismatches_stop_before_any_callback(self):
        self.evaluate(lambda item: str(item["gold"]))
        original = self.path.read_bytes()
        changes = {
            "label": "another-model", "synthetic": True,
            "prompt": "A changed prompt", "system": "A new system message",
            "max_tokens": 512, "gold": self.items[1]["gold"] + 1,
            "answer_type": "int_last",
        }
        for key, value in changes.items():
            with self.subTest(field=key):
                rows = [json.loads(line) for line in original.splitlines()]
                # Make the first item pending, so any late validation would
                # make an unnecessary model request before reaching this row.
                rows[0]["error"] = "Retry this item"
                rows[1][key] = value
                self.path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                before = self.path.read_bytes()

                def should_not_run(item):
                    self.fail("Mismatch was checked after a model request")

                with self.assertRaisesRegex(ValueError, key + " differs"):
                    self.evaluate(should_not_run)
                self.assertEqual(self.path.read_bytes(), before)

    def test_saved_ids_outside_current_bank_stop_before_any_callback(self):
        self.evaluate(lambda item: str(item["gold"]))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "saved item_id is not in the bank"):
            self.evaluate(lambda item: self.fail("Unexpected callback"), items=self.items[:1])
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_saved_records_are_also_checked_before_any_callback(self):
        self.evaluate(lambda item: {"error": "Timed out"})
        rows = wmip._read_jsonl(self.path)
        rows[-1]["max_tokens"] += 1
        self.path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "max_tokens differs; use a fresh out_path"):
            self.evaluate(lambda item: self.fail("Unexpected callback"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_not_yet_recorded_items_use_current_bank_without_replaying_prior_items(self):
        self.evaluate(lambda item: str(item["gold"]), items=self.items[:1])
        bank = [dict(item) for item in self.items]
        bank[1]["prompt"] = "A new item that has not been evaluated yet"
        received = []

        def generate(item):
            received.append(item)
            return str(item["gold"])

        self.evaluate(generate, items=bank)
        self.assertEqual(received, bank[1:])

    def test_saved_reasoning_is_never_laundered_by_resuming(self):
        self.evaluate(lambda item: "<think>reasoning</think>12", items=self.items[:1])
        before = self.path.read_bytes()
        self.evaluate(lambda item: self.fail("Completed response requested again"),
                      items=self.items[:1])
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaisesRegex(SystemExit, "thinking must be off"):
            wmip.score(self.items[:1], self.path, self.directory / "scores")

    def test_duplicate_final_records_fail_before_further_model_calls(self):
        self.evaluate(lambda item: str(item["gold"]), items=self.items[:1])
        first = self.path.read_bytes()
        self.path.write_bytes(first + first)
        with self.assertRaisesRegex(ValueError, "two final records"):
            self.evaluate(lambda item: self.fail("Unexpected callback"))


if __name__ == "__main__":
    unittest.main()
