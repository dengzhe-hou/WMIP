"""Community submissions: package a complete run, rescore it, and reject edits.

The run replays Qwen3 4B's stored answers through a local mock endpoint, so the
packaged scores must equal that model's published row. No model, credentials
or external network access is used.
"""

import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import test_run_command as replay

RELEASE = replay.RELEASE
WMIP = [sys.executable, str(RELEASE / "wmip.py")]


class CommunityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        replay.RunCommandTest.setUpClass.__func__(cls)
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.run_dir = Path(cls.temp.name) / "my-run"
        cls.requests = []
        server = cls()
        server.requests = cls.requests
        base_url = replay.RunCommandTest.serve(server)
        result = subprocess.run([*WMIP, "run", "--base-url", base_url, "--model", "mock",
                                 "--label", "my-qwen", "--out-dir", str(cls.run_dir),
                                 "--concurrency", "8", "--max-attempts", "1"],
                                capture_output=True, text=True)
        server.doCleanups()
        assert result.returncode == 0, result.stderr + result.stdout
        template = json.loads((RELEASE / "examples/submission_metadata.json").read_text(encoding="utf-8"))
        cls.metadata = {key: "filled in" for key in template}
        cls.metadata.update(model_name="my-qwen", evidence_url="https://example.org/my-qwen")

    def runTest(self):
        pass

    def package(self, root, metadata=None, run_dir=None):
        meta = Path(root) / "metadata.json"
        meta.write_text(json.dumps(metadata or self.metadata), encoding="utf-8")
        return subprocess.run([*WMIP, "package", "--run-dir", str(run_dir or self.run_dir),
                               "--metadata", str(meta), "--id", "my-qwen-20261111",
                               "--output", str(Path(root) / "submissions/my-qwen-20261111")],
                              capture_output=True, text=True)

    def check(self, root, export=None):
        command = [*WMIP, "check-submissions", "--root", str(Path(root) / "submissions")]
        return subprocess.run(command + (["--export", str(export)] if export else []),
                              capture_output=True, text=True)

    def test_package_matches_published_row_and_exports(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.package(root).returncode, 0)
            board_path = Path(root) / "community.json"
            result = self.check(root, board_path)
            self.assertEqual(result.returncode, 0, result.stdout)
            board = json.loads(board_path.read_text(encoding="utf-8"))
            self.assertEqual(len(board["paper"]), 18)
            (entry,) = board["community"]
            with (self.run_dir / "comparison.csv").open(encoding="utf-8") as handle:
                published = {row["model"]: row for row in csv.DictReader(handle)}["Qwen3-4B-2507"]
            for metric in board["metrics"]:
                self.assertEqual(f"{entry['scores'][metric['key']]:.6f}", published[metric["key"]])

    def test_edited_score_or_response_fails(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.package(root).returncode, 0)
            folder = Path(root) / "submissions/my-qwen-20261111"
            submission = json.loads((folder / "submission.json").read_text(encoding="utf-8"))
            original = (folder / "submission.json").read_text(encoding="utf-8")
            submission["scores"]["core"] = 0.9
            (folder / "submission.json").write_text(json.dumps(submission), encoding="utf-8")
            result = self.check(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("differ from the rescored responses", result.stdout)

            (folder / "submission.json").write_text(original, encoding="utf-8")
            lines = (folder / "main.jsonl").read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[0])
            record["raw_response"] = str(record["gold"])
            (folder / "main.jsonl").write_text("\n".join([json.dumps(record), *lines[1:]]) + "\n",
                                               encoding="utf-8")
            self.assertEqual(self.check(root).returncode, 1)

    def test_incomplete_run_and_placeholders_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            partial = Path(root) / "partial"
            shutil.copytree(self.run_dir, partial)
            lines = (partial / "budget.jsonl").read_text(encoding="utf-8").splitlines()
            (partial / "budget.jsonl").write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
            result = self.package(root, run_dir=partial)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("incomplete", result.stderr)

            template = json.loads((RELEASE / "examples/submission_metadata.json").read_text(encoding="utf-8"))
            result = self.package(root, metadata=template)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("fill in", result.stderr)


if __name__ == "__main__":
    unittest.main()
