# WMIP in evaluation frameworks

These task definitions let you run WMIP from [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) or [Inspect](https://inspect.aisi.org.uk). Both use the frozen item banks and call the release's own scorers (`analysis/score_bank.py`, `analysis/score_ext.py`), so prompts, output budgets and scoring rules match the paper. Run them from a clone of the release; the task files import code from it.

Given a released model's stored responses through a local replay endpoint, both frameworks reproduce that model's published accuracies on every task (checked for Qwen3 4B, 2026-10-28).

For the paper's full protocol, the thinking check and a comparison with the 18 published models, `python wmip.py run` remains the reference route (see the repository README).

## Tasks

Each task is one block at one output budget, because both frameworks fix the output budget per task. The paper reports each block separately; do not average across tasks.

| Task | Items | Budget | Metric |
| --- | ---: | ---: | --- |
| `core` | 60 | 16 | one integer |
| `depth` | 140 | 16 | one integer |
| `arithmetic` | 90 | 16 | one integer |
| `cancellation` | 100 | 16 | one integer |
| `assignment` | 90 | 16 | Parser 1 and Parser 2 |
| `sets_counts_16` | 30 | 16 | Parser 1 and Parser 2 |
| `sets_counts_48` | 60 | 48 | Parser 1 and Parser 2 |
| `wordings` | 150 | 16 | one integer |
| `instructions` | 60 | 16 | one integer (Inspect only) |
| `written_steps` | 60 | 512 | last integer |
| `large_budget` | 60 | 512 | one integer and last integer |
| `intermediate` | 60 | 16 | one integer, entity labels removed |
| `multitarget_tracking` | 60 | 48 | exact ordered list |
| `multitarget_readout` | 60 | 48 | exact ordered list |

The paper's Sets/counts score is the item-weighted mean of the two Sets/counts tasks: (30 × `sets_counts_16` + 60 × `sets_counts_48`) / 90.

## lm-evaluation-harness

```bash
pip install "lm_eval[api]"
lm_eval --model local-chat-completions \
    --model_args model=my-model,base_url=http://localhost:8000/v1/chat/completions,tokenizer_backend=None \
    --tasks wmip --include_path integrations/lm_eval/wmip --apply_chat_template
```

`--tasks wmip` runs the 13 tasks in the table other than `instructions`; a single task is `wmip_core`, `wmip_large_budget` and so on. Items load from the Hugging Face dataset at tag `v2026.10.1`, which needs the `datasets` package and network access on first use. Generation uses temperature 0 and no stop sequences.

Two differences from the release runner:

- `instructions` is not included, because its items carry a per-item system turn that lm-evaluation-harness cannot send.
- The harness does not see reasoning traces, so it cannot stop a run when thinking is on. Disable thinking on the server side (see "Turn thinking off" in the repository README).

## Inspect

```bash
pip install inspect-ai
inspect eval integrations/inspect/wmip_inspect.py@wmip -T task=core --model openai/gpt-4.1
```

Pass any task name from the table with `-T task=...`; all 14 are available, including `instructions` with its system turns. Items load from the release's local JSONL files. Generation uses temperature 0 and each task's budget. A response that contains a reasoning trace raises an error, as the release runner does. Each score records the response and whether it reached the output limit.
