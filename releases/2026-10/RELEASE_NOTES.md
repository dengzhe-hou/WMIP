# WMIP v2026.10.3

Released on 2026-10-28. This version makes it easier to evaluate a new model
and place it among the published ones.

- `python wmip.py run` sends the three frozen banks (840 main, 60 large-budget,
  180 intermediate-state and multi-target items) to one OpenAI-compatible
  endpoint, scores each with its published rule and prints the model among the
  18 published models. `python wmip.py compare` reprints the table.
- lm-evaluation-harness and Inspect task definitions in `integrations/` use
  the frozen banks and the release's own scorers.
- The repository README shows how to turn thinking off for common model and
  server types.
- `code/runner/run_bank.py` is the released runner under its current name; the
  original `run_wmf_am_bank.py` remains and runs the same code.

Frozen item banks, stored model responses, scoring rules and reported results
are unchanged. The matching frozen Hugging Face banks remain at dataset tag
`v2026.10.1`.

## WMIP v2026.10.2

Released on 2026-10-26. This version adds a complete local Transformers
example for the existing model-function interface. It loads a pinned
Qwen3 4B Instruct model on CPU, writes real responses, resumes completed
items and scores against the frozen bank. The [walkthrough](examples/README.md)
covers installation, a three-item connection check, resuming and a full run.

The connection check is an onboarding example. Its CPU float32 backend
differs from the released paper runs and its scores are not a reproduction
of the reported model results. Frozen item banks, stored model responses,
scoring rules and reported results are unchanged. The matching frozen
Hugging Face banks remain at dataset tag `v2026.10.1`.

## WMIP v2026.10.1

Released on 2026-10-26. The current evaluation materials are in
[`releases/2026-10/`](./). The repository's root `code/` and `data/` directories
preserve the earlier WMF-AM experiments.

## Reuse improvements

- Evaluate a model through an OpenAI-compatible endpoint, a Python function,
  or an existing JSONL answer file. The README documents each route.
- Resume Python function evaluations without repeating successful requests.
  Failed or unfinished requests can be retried.
- Score browser-generated items and task subsets, including Written steps
  alone, without failures from absent blocks.
- Read task names, accuracy, scored counts and missing counts together in
  the scoring summary. Accuracy uses scored responses; missing responses
  remain visible separately.
- Load and decode all six Hugging Face configurations with instructions for
  selecting the corresponding scorer.
- Cite this version through the repository's `CITATION.cff` and fixed release
  tag.

## Reproduction materials

The frozen item banks, model responses, scoring rules and reported results
are unchanged. This release adds reuse tools and fixes their execution paths.

Code is covered by [MIT](LICENSE), and author-owned data, figures and
documentation by [CC BY 4.0](LICENSE-DATA), subject to the third-party
attributions and model-output qualifications in [NOTICE](NOTICE).
