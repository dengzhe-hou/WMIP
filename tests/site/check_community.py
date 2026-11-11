#!/usr/bin/env python3
"""Check the leaderboard ranking used by the homepage, and the exported board.

Run with Python 3 and Node.js: python tests/site/check_community.py
No model, credentials, or external network access is used.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]


def main():
    module_uri = (ROOT / "site/community.mjs").as_uri()
    rows = [{"model": name, "scores": {"core": value}}
            for name, value in [("a", 0.5), ("b", 0.9), ("c", 0.5), ("d", None), ("e", 0.1)]]
    javascript = f"""
import {{ rankRows }} from {json.dumps(module_uri)};
const rows = {json.dumps(rows)};
process.stdout.write(JSON.stringify(rankRows(rows, "core").map((row) => [row.model, row.rank])));
"""
    ranked = json.loads(subprocess.run(["node", "--input-type=module", "-e", javascript],
                                       check=True, capture_output=True, text=True).stdout)
    assert ranked == [["b", 1], ["a", 2], ["c", 2], ["e", 4], ["d", None]], ranked

    with TemporaryDirectory() as directory:
        board_path = Path(directory) / "community.json"
        subprocess.run([sys.executable, str(ROOT / "releases/2026-10/wmip.py"), "check-submissions",
                        "--export", str(board_path)], check=True, capture_output=True, text=True)
        board = json.loads(board_path.read_text(encoding="utf-8"))
    assert len(board["paper"]) == 18 and len(board["metrics"]) == 8
    for entry in board["paper"] + board["community"]:
        assert set(entry["scores"]) == {metric["key"] for metric in board["metrics"]}, entry["model"]
    print(f"Leaderboard ranking and export passed ({len(board['community'])} community rows).")


if __name__ == "__main__":
    main()
