# WMIP: Working-Memory-Inspired Probe

Evaluation materials for **A Working-Memory-Inspired Programmable Probe of Cumulative State Tracking in Large Language Models**.

[Project website](https://dengzhe-hou.github.io/WMIP/) · [Hugging Face dataset](https://huggingface.co/datasets/dengzhe-hou/WMIP) · [Reproduction guide](releases/2026-10/README.md)

The current October 2026 release is in [`releases/2026-10/`](releases/2026-10/). It contains the generator, frozen item banks, model responses, execution metadata, scoring and analysis code, and generated tables and figures for the 18-model evaluation. Each model has 840 main-bank requests, 60 large-budget requests, and 180 intermediate-state and multi-target requests.

## Current release

Start with the [release README](releases/2026-10/README.md) for protocols, model identities, scoring rules, and complete reproduction instructions. The versioned release includes the code, data, and analysis artifacts for this evaluation, with subsequent documentation and file-path corrections. The frozen item banks, model responses and reported results are unchanged.

| Materials | Location |
| --- | --- |
| Generators and runners | [`code/`](releases/2026-10/code/) |
| Item banks and model responses | [`data/`](releases/2026-10/data/) |
| Scoring, analysis, and stored results | [`analysis/`](releases/2026-10/analysis/) |
| Figure and table generators | [`analysis/paper/`](releases/2026-10/analysis/paper/) |
| BFCL scores and model metadata | [`external/`](releases/2026-10/external/) |

## Hugging Face item banks

The item banks are also available on [Hugging Face](https://huggingface.co/datasets/dengzhe-hou/WMIP). The default configuration contains the 840 main-bank items; five additional configurations preserve the extension, large-budget and protocol-variant banks. Model responses, scoring code and complete reproduction materials are in the GitHub release linked above.

```python
from datasets import load_dataset

items = load_dataset("dengzhe-hou/WMIP", split="test")
```

The dataset card documents the configurations and the lossless JSON encoding of reference answers and metadata.

## Offline quick start

From the repository root, rescore all 18 models on the 840-item main bank using Python and its standard library only.

```bash
cd releases/2026-10
score_dir=$(mktemp -d)
python analysis/score_bank.py --out-dir "$score_dir" \
    data/responses/local/*.jsonl data/responses/api/*.jsonl
```

This writes 15,120 item-level scores and summary CSVs to the temporary directory. It makes no model calls and needs no GPU, model weights, API key, or network access. The release README also covers rebuilding the item banks, reproducing the additional protocols, and regenerating analyses and figures. Those analyses use NumPy and SciPy; plotting additionally uses Matplotlib.

## Historical materials

The root [`code/`](code/) and [`data/`](data/) directories preserve the earlier WMF-AM experiments. They use historical model panels, task versions, prompts, and scoring procedures. They are not inputs to the current 18-model evaluation and must not be pooled with it. Use the versioned release above to reproduce the current paper.

The [earlier README at commit `f50db70`](https://github.com/dengzhe-hou/WMIP/blob/f50db70/README.md) remains available as a historical record. Its descriptions and conclusions do not describe the current release.

## Licenses

The current release provides code under [MIT](releases/2026-10/LICENSE), and author-owned data, figures, and documentation under [CC BY 4.0](releases/2026-10/LICENSE-DATA). The [NOTICE](releases/2026-10/NOTICE) preserves the Apache 2.0 license and attribution for reused BFCL scores and limits the grant for model-generated text to rights held by the authors. No model weights or credentials are included.
