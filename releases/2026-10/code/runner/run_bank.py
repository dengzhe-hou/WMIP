#!/usr/bin/env python3
"""Run one frozen WMIP item bank against ONE OpenAI-compatible chat endpoint.

Standard library only. One invocation = one model and one bank; to run all
three banks and compare with the published models, use ``python wmip.py run``.

  vLLM or another local server
    python code/runner/run_bank.py --bank data/item_bank/item_bank.jsonl \\
        --out my-run/main.jsonl --base-url http://127.0.0.1:8000/v1 --model <served-model-name>

  Hosted API, key in an environment variable
    python code/runner/run_bank.py --bank data/item_bank/item_bank.jsonl \\
        --out my-run/main.jsonl --base-url https://api.openai.com/v1 --model gpt-4.1 \\
        --api-key-env OPENAI_API_KEY

Each item's prompt, optional system turn and max_tokens come from the bank.
Output is append-only JSONL: a record with "error": null is final; a record
with an error is a missing trial, retried when the same command is rerun.
The run stops if a response contains a reasoning trace, because the published
results use thinking-disabled inference (see "Turn thinking off" in the README).

Exit codes: 0 = bank complete, 1 = some items still missing, 2 = aborted.

This is the released runner ``run_wmf_am_bank.py`` under its current name;
both names run the same code and write the same records.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_path = Path(__file__).resolve().with_name("run_wmf_am_bank.py")
_spec = importlib.util.spec_from_file_location("wmip_bank_runner", _path)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)
runner.__doc__ = __doc__  # shown by --help

if __name__ == "__main__":
    sys.exit(runner.main())
