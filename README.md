<div align="center">

# WMIP

**A Working-Memory-Inspired Programmable Probe of Cumulative State Tracking in Large Language Models**

[![Project website](site/assets/badges/project.svg)](https://dengzhe-hou.github.io/WMIP/) [![Hugging Face dataset](site/assets/badges/huggingface.svg)](https://huggingface.co/datasets/dengzhe-hou/WMIP) [![Stable release](site/assets/badges/release.svg)](https://github.com/dengzhe-hou/WMIP/releases/tag/v2026.10.3) [![Reproduction guide](site/assets/badges/docs.svg)](releases/2026-10/README.md)

</div>

<p align="center">
  <img src="releases/2026-10/analysis/paper/figures/fig_overview.png" width="100%" alt="Four steps: generate an item with K updates, vary the response protocol, score the answer, and compare across lengths, states, tasks, variants and BFCL scores.">
</p>
<p align="center"><em>Code computes every answer. The same items run under different response protocols and fixed scoring rules.</em></p>

The October 2026 release in [`releases/2026-10/`](releases/2026-10/) holds the generator, three frozen item banks (840 main, 60 large-budget, and 180 intermediate-state and multi-target items), the responses of 18 models, and the scoring and analysis code behind the paper's tables and figures.

## News

- **2026-10-28** Release [v2026.10.3](https://github.com/dengzhe-hou/WMIP/releases/tag/v2026.10.3) runs every frozen bank with one command and compares your model with the 18 published models. It also adds lm-evaluation-harness and Inspect tasks.
- **2026-10-26** Release [v2026.10.2](https://github.com/dengzhe-hou/WMIP/releases/tag/v2026.10.2) adds a [local Qwen tutorial](releases/2026-10/examples/README.md) that runs a real model on CPU.
- **2026-10-26** Release [v2026.10.1](https://github.com/dengzhe-hou/WMIP/releases/tag/v2026.10.1) adds evaluation through a Python function or an existing answer file, resumable runs and per-task score summaries.
- **2026-10-19** The item banks are on [Hugging Face](https://huggingface.co/datasets/dengzhe-hou/WMIP), and the [project website](https://dengzhe-hou.github.io/WMIP/) lets you play the task and generate new items.

## Results

<p align="center">
  <img src="releases/2026-10/analysis/paper/figures/fig_main_results.png" width="100%" alt="(a) Core and single-step arithmetic accuracy for 18 models. (b) Response outcomes by number of updates. (c) Correct core responses under four protocols.">
</p>

Across 18 models, accuracy is 84.9% on single-step arithmetic but 31.7% on core items with three to seven updates, and every model scores lower on the core (a). Accuracy falls as updates accumulate (b). When models may write steps within 512 tokens, 950 of 1,080 core responses are correct, compared with 342 under the core protocol (c).

## Resources

| Resource | Link |
| --- | --- |
| Play the task or generate new items | [Project website](https://dengzhe-hou.github.io/WMIP/) |
| Frozen item banks | [Hugging Face dataset](https://huggingface.co/datasets/dengzhe-hou/WMIP) |
| Code, responses and analysis | [`releases/2026-10/`](releases/2026-10/) |
| Full reproduction guide | [Release README](releases/2026-10/README.md) |
| Changes by version | [Release notes](releases/2026-10/RELEASE_NOTES.md) |

## Evaluate your model

Clone the stable release and enter its evaluation directory:

```bash
git clone --branch v2026.10.3 https://github.com/dengzhe-hou/WMIP.git
cd WMIP/releases/2026-10
```

One command sends all three frozen banks to a local or hosted OpenAI-compatible endpoint, scores them with the published rules, and prints your model among the 18 published models. It needs only the Python standard library.

```bash
python wmip.py run --base-url http://localhost:8000/v1 --model my-model --out-dir my-run
```

Add `--api-key-env WMIP_API_KEY` for a key in that environment variable, and `--concurrency 8` for parallel requests. Rerun the same command to resume. `python wmip.py compare --run-dir my-run` reprints the table, which is also saved as `my-run/comparison.csv`. Per-item scores are in `my-run/scores/`.

> [!IMPORTANT]
> The published results use thinking-disabled inference, and the run stops if a response contains a reasoning trace. Keep each item's prompt and output budget, and record any change to inference settings.

### Turn thinking off

Pass the setting with `--extra-body`, a JSON object added to every request. Use a new `--out-dir` after changing it.

| Model and endpoint | Add to the command |
| --- | --- |
| Instruct models without a reasoning mode, e.g. Llama 3, Falcon3, Qwen3-4B-Instruct-2507 | nothing |
| Hybrid-reasoning models on vLLM or SGLang whose chat template reads `enable_thinking`, e.g. Qwen3 | `--extra-body '{"chat_template_kwargs": {"enable_thinking": false}}'` |
| OpenAI reasoning models that accept effort `none`, e.g. GPT-5.2 | `--temperature none --extra-body '{"reasoning_effort": "none"}'` |
| The same models through OpenRouter, as in the paper | `--temperature none --extra-body '{"reasoning": {"effort": "none"}}'` |
| Claude through Anthropic's OpenAI-compatible endpoint | nothing; extended thinking is off unless requested |

For other models, check the model card.

### Other ways to evaluate

- **One bank only**: add `--banks main` (or `budget`, `ext`), or use the runner `code/runner/run_bank.py` directly.
- **Your own inference code**: edit `generate(item)` in the [minimal Python example](releases/2026-10/examples/evaluate_callable.py); its `--demo` option checks the plumbing without a model.
- **Answers you already have**: score them with `python wmip.py score`, as shown in the [release README](releases/2026-10/README.md#reuse-with-your-model).
- **lm-evaluation-harness or Inspect**: use the [framework tasks](releases/2026-10/integrations/README.md).
- **A first run on your own machine**: follow the [local Qwen tutorial](releases/2026-10/examples/README.md).

## Reproduce the paper

From `releases/2026-10/`, rescore the stored responses of all 18 models without any model call, GPU or network access:

```bash
python analysis/score_bank.py --out-dir "$(mktemp -d)" \
    data/responses/local/*.jsonl data/responses/api/*.jsonl
```

The [release README](releases/2026-10/README.md) covers rebuilding the item banks, the other protocols, and the analyses and figures.

## Repository layout

| Materials | Location |
| --- | --- |
| Generators and runners | [`code/`](releases/2026-10/code/) |
| Item banks and model responses | [`data/`](releases/2026-10/data/) |
| Scoring, analysis, and stored results | [`analysis/`](releases/2026-10/analysis/) |
| Figure and table generators | [`analysis/paper/`](releases/2026-10/analysis/paper/) |
| BFCL scores and model metadata | [`external/`](releases/2026-10/external/) |

> [!WARNING]
> The root [`code/`](code/) and [`data/`](data/) directories hold the earlier WMF-AM experiments, with different models, tasks, prompts and scoring. Do not pool them with the current evaluation. The [earlier README](https://github.com/dengzhe-hou/WMIP/blob/f50db70/README.md) is kept as a record.

## Citation and licenses

Cite software release `2026.10.3` with [CITATION.cff](CITATION.cff) or GitHub's **Cite this repository** button, and cite the paper separately. Code is under [MIT](releases/2026-10/LICENSE), and author-owned data, figures and documentation are under [CC BY 4.0](releases/2026-10/LICENSE-DATA). The [NOTICE](releases/2026-10/NOTICE) covers the reused BFCL scores and model-generated text. No model weights or credentials are included.
