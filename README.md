# WMIP: Working-Memory-Inspired Probe

Evaluation materials for **A Working-Memory-Inspired Programmable Probe of Cumulative State Tracking in Large Language Models**.

[Project website](https://dengzhe-hou.github.io/WMIP/) · [Hugging Face dataset](https://huggingface.co/datasets/dengzhe-hou/WMIP) · [Stable release](https://github.com/dengzhe-hou/WMIP/releases/tag/v2026.10.1) · [Reproduction guide](releases/2026-10/README.md)

The current October 2026 release is in [`releases/2026-10/`](releases/2026-10/). It contains the generator, frozen item banks, model responses, execution metadata, scoring and analysis code, and generated tables and figures for the 18-model evaluation. Each model has 840 main-bank requests, 60 large-budget requests, and 180 intermediate-state and multi-target requests.

## Evaluate your model

Clone the stable `v2026.10.1` release and enter its evaluation directory. A clone already contains the reproduction materials; supplementary archives are not needed. See the [release notes](releases/2026-10/RELEASE_NOTES.md) for changes in this version.

```bash
git clone --branch v2026.10.1 https://github.com/dengzhe-hou/WMIP.git
cd WMIP/releases/2026-10
```

Run the frozen 840-item bank against a local or hosted OpenAI-compatible chat endpoint, then score its responses. Both commands use the Python standard library only.

```bash
python code/runner/run_wmf_am_bank.py \
    --bank data/item_bank/item_bank.jsonl \
    --base-url http://localhost:8000/v1 --model my-model --label my-model \
    --out my-run/responses.jsonl
python analysis/score_bank.py --bank data/item_bank/item_bank.jsonl \
    --out-dir my-run/scores my-run/responses.jsonl
```

Replace the URL and model name with your endpoint's values. For an authenticated endpoint, set its key in an environment variable and add `--api-key-env WMIP_API_KEY`. Running the first command makes model requests; rerunning the same command resumes unfinished items.

The runner preserves each item's prompt, optional system message and `max_tokens` budget, including 512 tokens for Written steps. Match the release's thinking-disabled inference mode for comparison with its results; record any changes to prompts, budgets or inference settings. Scores are written by block in `my-run/scores/accuracy_by_block.csv`, with item-level scores and format diagnostics alongside it.

For your own inference code, edit `generate(item)` in the [minimal Python example](releases/2026-10/examples/evaluate_callable.py). It receives the full item, so send only the prompt and optional system message to your model, and respect `max_tokens`. The example saves responses and invokes the same scorer. After editing the function, run:

```bash
python examples/evaluate_callable.py --out-dir my-callable-run --label my-model
```

Rerun the same command after an interruption to resume. The callable keeps existing successful response records and retries unfinished or failed requests. Incorrect, empty and truncated answers are completed responses and are kept. Use a new output directory when changing the model or inference settings.

To try the plumbing without a model call:

```bash
python examples/evaluate_callable.py --demo --out-dir my-demo
```

The demo produces explicitly synthetic outputs and is not a model evaluation.

## Score your own answers

Save one JSON object per line with an unchanged item ID and the model's full answer text. For example, the format of `answers.jsonl` is:

```json
{"item_id":"A-k3-s2026-p0","response":"12","finish_reason":"stop"}
```

From `releases/2026-10/`, score a file of your actual answers:

```bash
python wmip.py score --bank data/item_bank/item_bank.jsonl \
    --responses answers.jsonl --label my-model --out-dir my-scores
```

Only `item_id` and `response` are required. Include `finish_reason` when available so truncation can be reported; failed requests can carry an `error`. Unanswered and failed items remain marked as missing; report the scored and missing counts with accuracy. The helper creates runner-compatible response records and the release scorer's CSVs, without asking you to supply internal execution fields.

You can also use JSONL exported by the [website generator](https://dengzhe-hou.github.io/WMIP/) as `--bank`. Newly generated Core items are exploratory evaluations, separate from results on the frozen bank. [Hugging Face loading and decoding](releases/2026-10/README.md#hugging-face-items) use the same helper. It selects the existing K/L scorer for extension banks, which writes its own item-level CSV.

## Read the results

Scoring prints each task's name, scored/total count, missing count and accuracy. Assignment and Sets/counts show Parser 1 and Parser 2 in parallel; other tasks use the `Accuracy` column. Accuracy excludes missing responses and displays `-` when no answers were scored. Full-precision values and format diagnostics remain in the CSVs.

For example, rescoring the stored Qwen3 4B responses prints the following. This uses the released responses and makes no new model calls.

```text
model: qwen3-4b-instruct-2507
Task                      Scored/total Missing  Accuracy  Parser 1  Parser 2 Truncated
A Core                           60/60       0      1.7%         -         -        40
B Depth                        140/140       0      0.0%         -         -        32
C Arithmetic                     90/90       0     93.3%         -         -         0
D Cancellation                 100/100       0     55.0%         -         -        29
E Assignment                     90/90       0         -     96.7%     96.7%         0
F Sets/counts                    90/90       0         -     54.4%     54.4%         5
G Wordings                     150/150       0     14.7%         -         -       111
H Instructions                   60/60       0      0.0%         -         -        31
I Written steps                  60/60       0    100.0%         -         -         0
```

## Reproduce the published responses offline

From `releases/2026-10/`, rescore all 18 models on the 840-item main bank:

```bash
score_dir=$(mktemp -d)
python analysis/score_bank.py --out-dir "$score_dir" \
    data/responses/local/*.jsonl data/responses/api/*.jsonl
```

This writes 15,120 item-level scores and summary CSVs. It makes no model calls and needs no GPU, model weights, API key, or network access. The [release README](releases/2026-10/README.md) also covers rebuilding the item banks, reproducing the additional protocols, and regenerating analyses and figures. Those analyses use NumPy and SciPy; plotting additionally uses Matplotlib.

## Current release contents

The versioned release includes the code, data, and analysis artifacts for this evaluation, with subsequent documentation and file-path corrections. The frozen item banks, model responses and reported results are unchanged.

| Materials | Location |
| --- | --- |
| Generators and runners | [`code/`](releases/2026-10/code/) |
| Item banks and model responses | [`data/`](releases/2026-10/data/) |
| Scoring, analysis, and stored results | [`analysis/`](releases/2026-10/analysis/) |
| Figure and table generators | [`analysis/paper/`](releases/2026-10/analysis/paper/) |
| BFCL scores and model metadata | [`external/`](releases/2026-10/external/) |

The [Hugging Face dataset](https://huggingface.co/datasets/dengzhe-hou/WMIP) contains the 840 main-bank items by default and five additional configurations for extension, large-budget and protocol-variant banks. Model responses and complete reproduction materials are in this repository.

## Historical materials

The root [`code/`](code/) and [`data/`](data/) directories preserve the earlier WMF-AM experiments. They use historical model panels, task versions, prompts, and scoring procedures. They are not inputs to the current 18-model evaluation and must not be pooled with it. Use the versioned release above to reproduce the current paper.

The [earlier README at commit `f50db70`](https://github.com/dengzhe-hou/WMIP/blob/f50db70/README.md) remains available as a historical record. Its descriptions and conclusions do not describe the current release.

## Citation

Use [CITATION.cff](CITATION.cff), or GitHub's **Cite this repository** button, to cite software release `2026.10.1`. The citation identifies these versioned evaluation materials. Paper citations should use the matching manuscript version.

## Licenses

The current release provides code under [MIT](releases/2026-10/LICENSE), and author-owned data, figures, and documentation under [CC BY 4.0](releases/2026-10/LICENSE-DATA). The [NOTICE](releases/2026-10/NOTICE) preserves the Apache 2.0 license and attribution for reused BFCL scores and limits the grant for model-generated text to rights held by the authors. No model weights or credentials are included.
