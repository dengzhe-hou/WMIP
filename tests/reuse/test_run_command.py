"""`wmip.py run` against a local mock endpoint that replays released responses.

The mock returns Qwen3 4B's stored answers for all three banks, so the new
command must reproduce that model's published accuracies exactly. No model,
credentials or external network access is used.
"""

import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import unittest

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "releases/2026-10"
LABEL = "qwen3-4b-instruct-2507"
STORED = {
    "main": RELEASE / f"data/responses/local/{LABEL}.jsonl",
    "budget": RELEASE / f"data/responses/budget/local/{LABEL}.jsonl",
    "ext": RELEASE / f"data/responses/ext/local/{LABEL}.jsonl",
}


def final_records(path):
    final = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["error"] is None:
            final[record["item_id"]] = record
    return final


class RunCommandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.replies = {}
        for path in STORED.values():
            for record in final_records(path).values():
                key = (record.get("system"), record["prompt"], record["max_tokens"])
                assert key not in cls.replies, key
                cls.replies[key] = (record["raw_response"], record["finish_reason"])

    def setUp(self):
        self.requests = []

    def serve(self):
        replies, requests = self.replies, self.requests

        class Endpoint(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(body)
                messages = body["messages"]
                system = messages[0]["content"] if messages[0]["role"] == "system" else None
                text, finish = replies[(system, messages[-1]["content"], body["max_tokens"])]
                payload = json.dumps({"model": "mock", "choices": [
                    {"message": {"role": "assistant", "content": text}, "finish_reason": finish}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Endpoint)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/v1"

    def test_run_reproduces_published_row_and_resumes(self):
        base_url = self.serve()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "my-run"
            command = [sys.executable, str(RELEASE / "wmip.py"), "run", "--base-url", base_url,
                       "--model", "mock", "--label", "my-qwen", "--out-dir", str(out),
                       "--concurrency", "8", "--max-attempts", "1"]
            first = subprocess.run(command, capture_output=True, text=True, cwd=directory)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(len(self.requests), 840 + 60 + 180)
            self.assertIn("my-qwen: Core rank", first.stdout)

            # Every request carries the bank's own budget and system turn.
            budgets = {(bool(r["messages"][0]["role"] == "system"), r["max_tokens"]) for r in self.requests}
            self.assertEqual(budgets, {(False, 16), (False, 48), (False, 512), (True, 16)})

            with (out / "comparison.csv").open(encoding="utf-8") as handle:
                rows = {row["model"]: row for row in csv.DictReader(handle)}
            mine, published = rows["my-qwen"], rows["Qwen3-4B-2507"]
            self.assertEqual(mine["yours"], "1")
            for key in ("core", "arithmetic", "cancellation", "written_steps", "budget_last",
                        "intermediate", "tracking", "readout"):
                self.assertEqual(mine[key], published[key], key)

            # Rerunning the same command sends no new requests and prints the same table.
            second = subprocess.run(command, capture_output=True, text=True, cwd=directory)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(len(self.requests), 840 + 60 + 180)
            table = lambda text: text[text.index("Accuracy (%)"):]
            self.assertEqual(table(second.stdout), table(first.stdout))

            reprint = subprocess.run([sys.executable, str(RELEASE / "wmip.py"), "compare",
                                      "--run-dir", str(out)], capture_output=True, text=True)
            self.assertEqual(reprint.returncode, 0, reprint.stderr)
            self.assertEqual(table(reprint.stdout), table(first.stdout))

    def test_published_label_is_rejected(self):
        base_url = self.serve()
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(RELEASE / "wmip.py"), "run",
                                     "--base-url", base_url, "--model", "mock", "--label", "GPT-5.2",
                                     "--banks", "budget", "--out-dir", str(Path(directory) / "run")],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("equals a published model name", result.stderr)


if __name__ == "__main__":
    unittest.main()
