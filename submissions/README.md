# Submit your results

Evaluate your own model on WMIP and add it to the [leaderboard](https://dengzhe-hou.github.io/WMIP/#community) through a pull request. You run the model on your own machine or provider account. Each submission includes the raw responses, so the check rescores them with the published rules instead of trusting the stated numbers. The 18 models in the paper stay unchanged and are labeled separately.

## 1. Run all three banks

```bash
git clone --branch v2026.10.5 https://github.com/dengzhe-hou/WMIP.git
cd WMIP/releases/2026-10
python wmip.py run --base-url http://localhost:8000/v1 --model my-model --out-dir my-run
```

Follow the [evaluation instructions](../README.md#evaluate-your-model), including the thinking-off settings. Only complete runs can be submitted. All 840 main, 60 large-budget and 180 extension items must have a response, so rerun the same command until nothing is missing. Do not change inference settings partway through. Use a fresh `--out-dir` after any change.

## 2. Package the run

Copy [the metadata template](../releases/2026-10/examples/submission_metadata.json) to `my-run/metadata.json` and fill in every field. `model_name` must equal the `--label` of the run (by default its `--model`). `evidence_url` links to a model card or run notes. Never include an API key.

```bash
python wmip.py package --run-dir my-run --metadata my-run/metadata.json \
    --id my-model-20261111 --output ../../submissions/my-model-20261111
python wmip.py check-submissions
```

`package` copies the three response files and their run records and writes `submission.json` with the scores. [`example-qwen3-4b-replay`](../releases/2026-10/examples/submission/example-qwen3-4b-replay) shows a complete result, with a filled-in `metadata` block. It replays the paper's Qwen3-4B responses, so it is kept outside this directory and does not appear on the leaderboard. The run records keep the endpoint URL of the run. You may replace a private host in `base_url` before opening the pull request. No other field may change.

## 3. Open a pull request

Fork the repository, commit only the new `submissions/<id>/` directory and open a pull request against `main`. GitHub runs the same check. A maintainer reviews the settings and the evidence link, then merges. The homepage updates automatically after the merge.

If you prefer not to open a pull request, use the [result form](https://github.com/dengzhe-hou/WMIP/issues/new?template=result_report.yml) with a link to an archive of your run directory. A maintainer packages it and opens the pull request, and the same check applies.

The check confirms that the run is complete, that one setting produced it and that the scores match the responses. It cannot confirm that the responses came from the stated model. A merged entry is a reviewed community report, not a rerun by the maintainers. Corrections go through another pull request.
