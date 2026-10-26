#!/usr/bin/env python3
"""Exercise browser JSONL -> API runner -> released scorer with a local mock.

Run with Python 3 and Node.js: python tests/site/check_browser_evaluation.py
No model, credentials, or external network access is used.
"""

from __future__ import annotations

import csv
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread


ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "releases/2026-10"


def main():
    # Use the exact generator and serializer called by the website download.
    module_uri = (ROOT / "site/batch.mjs").as_uri()
    javascript = f"""
import {{ generateBatchItems, serializeItem }} from {json.dumps(module_uri)};
process.stdout.write(Array.from(generateBatchItems(2026, 3, 2), serializeItem).join(''));
"""
    generated = subprocess.run(
        ["node", "--input-type=module", "-e", javascript],
        text=True, capture_output=True, check=True,
    ).stdout
    items = [json.loads(line) for line in generated.splitlines()]
    # The mock answers one task correctly and one incorrectly.
    responses = {
        item["prompt"]: str(item["gold"] + index)
        for index, item in enumerate(items)
    }
    requests = []

    class MockEndpoint(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            payload = json.dumps({
                "model": "local-mock",
                "choices": [{
                    "message": {"role": "assistant", "content": responses[body["messages"][-1]["content"]]},
                    "finish_reason": "stop",
                }],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    with TemporaryDirectory(prefix="wmip-browser-evaluation-") as directory:
        workspace = Path(directory)
        bank = workspace / "browser_items.jsonl"
        output = workspace / "mock_responses.jsonl"
        scored = workspace / "scored"
        bank.write_text(generated, encoding="utf-8")

        with HTTPServer(("127.0.0.1", 0), MockEndpoint) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                subprocess.run([
                    sys.executable, str(RELEASE / "code/runner/run_wmf_am_bank.py"),
                    "--bank", str(bank), "--out", str(output),
                    "--base-url", f"http://127.0.0.1:{server.server_port}/v1",
                    "--model", "local-mock", "--max-attempts", "1", "--timeout", "5",
                ], check=True, capture_output=True, text=True)
            finally:
                server.shutdown()
                thread.join()

        assert len(requests) == len(items)
        for (path, body), item in zip(requests, items, strict=True):
            assert path == "/v1/chat/completions"
            assert body["messages"] == [{"role": "user", "content": item["prompt"]}]
            assert body["max_tokens"] == 16
            assert body["temperature"] == 0

        subprocess.run([
            sys.executable, str(RELEASE / "analysis/score_bank.py"),
            "--bank", str(bank), "--out-dir", str(scored), str(output),
        ], check=True, capture_output=True, text=True)
        with (scored / "scored_items.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert [row["item_id"] for row in rows] == [item["item_id"] for item in items]
        assert [row["status"] for row in rows] == ["scored", "scored"]
        assert [row["correct_strict"] for row in rows] == ["1", "0"]
        assert [row["correct_submitted"] for row in rows] == ["1", "0"]
        with (scored / "accuracy_by_block.csv").open(encoding="utf-8", newline="") as handle:
            summary = list(csv.DictReader(handle))
        assert len(summary) == 1
        assert summary[0]["n_scored"] == "2"
        assert summary[0]["n_missing"] == "0"
        assert summary[0]["acc_strict"] == "0.500000"
        with (scored / "accuracy_g_by_template.csv").open(encoding="utf-8", newline="") as handle:
            assert "acc_strict" in next(csv.reader(handle))
            assert list(handle) == []

    print("PASS: browser export -> local mock API -> released scorer; one correct and one incorrect response.")
    print("PASS: exported prompts and core request settings reach the endpoint unchanged.")


if __name__ == "__main__":
    main()
