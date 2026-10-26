"""Check the local-model adapter's protocol and resume behavior without weights."""

import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "releases/2026-10"
spec = importlib.util.spec_from_file_location(
    "wmip_transformers_example", RELEASE / "examples/evaluate_transformers.py")
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


class LocalTransformersExampleTest(unittest.TestCase):
    def test_model_messages_preserve_system_and_never_include_gold(self):
        item = {"prompt": "original prompt", "gold": "SECRET REFERENCE", "max_tokens": 16}
        self.assertEqual(example.messages_for(item), [{"role": "user", "content": item["prompt"]}])
        self.assertEqual(example.messages_for({**item, "system": None}), example.messages_for(item))
        for system in ("original system", ""):
            self.assertEqual(example.messages_for({**item, "system": system}), [
                {"role": "system", "content": system},
                {"role": "user", "content": item["prompt"]},
            ])

    def test_finish_reason_uses_actual_eos_and_budget(self):
        class Tokenizer:
            def decode(self, ids, skip_special_tokens):
                self.last_ids = ids
                self.skip_special_tokens = skip_special_tokens
                return "decoded response"

        tokenizer = Tokenizer()
        stopped = example.generation_result(tokenizer, [7, 8, 99], [98, 99], 16)
        self.assertEqual(stopped, {"response": "decoded response", "finish_reason": "stop"})
        self.assertEqual(tokenizer.last_ids, [7, 8, 99])
        self.assertTrue(tokenizer.skip_special_tokens)
        self.assertEqual(example.generation_result(tokenizer, [7, 8], 99, 2)["finish_reason"], "length")
        self.assertEqual(example.generation_result(tokenizer, [7, 99], 99, 2)["finish_reason"], "stop")

    def test_local_generation_uses_bank_budget_and_decodes_only_new_tokens(self):
        calls = {}

        class Tokenizer:
            chat_template = "original template; enable_thinking"
            pad_token_id, bos_token_id = 98, 97

            def apply_chat_template(self, messages, **kwargs):
                calls["messages"] = messages
                calls["template_options"] = kwargs
                return {"input_ids": SimpleNamespace(shape=(1, 4))}

            def decode(self, ids, skip_special_tokens):
                calls["decoded_ids"] = ids
                return "8"

        class Output:
            def __getitem__(self, index):
                row, part = index
                self.assertion = (row, part.start)
                calls["output_slice"] = self.assertion
                return SimpleNamespace(tolist=lambda: [8, 99])

        class Model:
            generation_config = SimpleNamespace(eos_token_id=[99], do_sample=True,
                                                repetition_penalty=1.1)

            def to(self, device):
                calls["device"] = device
                return self

            def eval(self):
                return self

            def generate(self, **kwargs):
                calls["generate"] = kwargs
                return Output()

        def load_model(name, **kwargs):
            calls["load"] = (name, kwargs)
            return Model()

        fake_torch = SimpleNamespace(float32="float32", set_num_threads=lambda n: None,
                                     inference_mode=contextlib.nullcontext)
        fake_transformers = SimpleNamespace(
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=load_model),
            GenerationConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        )
        item = {"item_id": "test", "prompt": "bank prompt", "gold": "hidden", "max_tokens": 19}
        backend = example.LocalModel(Tokenizer(), "pinned-model", "pinned-revision", 4)
        with patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}), \
                contextlib.redirect_stdout(io.StringIO()):
            result = backend(item)
        self.assertEqual(calls["messages"], [{"role": "user", "content": "bank prompt"}])
        self.assertEqual(calls["template_options"]["enable_thinking"], False)
        self.assertEqual(calls["generate"]["generation_config"].max_new_tokens, 19)
        self.assertNotIn("max_new_tokens", calls["generate"])
        self.assertFalse(calls["generate"]["generation_config"].do_sample)
        self.assertEqual(calls["generate"]["generation_config"].repetition_penalty, 1.0)
        self.assertEqual(calls["generate"]["generation_config"].temperature, 1.0)
        self.assertEqual(calls["generate"]["generation_config"].top_p, 1.0)
        self.assertEqual(calls["generate"]["generation_config"].top_k, 50)
        self.assertEqual(calls["output_slice"], (0, 4))
        self.assertEqual(calls["decoded_ids"], [8, 99])
        self.assertEqual(result, {"response": "8", "finish_reason": "stop"})

    def test_prefix_resume_does_not_repeat_calls_and_fullbank_remains_missing(self):
        items = example.load_items(RELEASE / "data/item_bank/item_bank.jsonl")
        calls = []

        def generate(item):
            calls.append((item["item_id"], item["max_tokens"]))
            return {"response": "0", "finish_reason": "stop"}

        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            out = Path(temp)
            records = example.run(items, generate, out, "mock-transformers", 3)
            first = records.read_bytes()
            example.run(items, generate, out, "mock-transformers", 3)
            self.assertEqual(records.read_bytes(), first)
            self.assertEqual(calls, [(item["item_id"], item["max_tokens"]) for item in items[:3]])
            with (out / "scores/scored_items.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 840)
            self.assertEqual(sum(row["status"] == "scored" for row in rows), 3)
            self.assertEqual(sum(row["status"] == "missing" for row in rows), 837)
            example.run(items, generate, out, "mock-transformers", 5)
            self.assertEqual([call[0] for call in calls], [item["item_id"] for item in items[:5]])
            # A lower prefix can inspect coverage of an existing longer run.
            example.run(items, generate, out, "mock-transformers", 3)
            self.assertEqual(len(calls), 5)

    def test_changed_run_settings_fail_before_new_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "run_metadata.json"
            records = Path(temp) / "responses.jsonl"
            metadata = {"model": "pinned-model", "dtype": "float32", "revision": "version"}
            example.save_metadata(path, metadata, records)
            example.save_metadata(path, metadata, records)
            with self.assertRaisesRegex(ValueError, "settings differ"):
                example.save_metadata(path, {**metadata, "model": "other-model"}, records)
            self.assertEqual(json.loads(path.read_text()), metadata)


if __name__ == "__main__":
    unittest.main()
