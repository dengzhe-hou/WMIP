# Contributing to WMIP

Thank you for helping. There are three ways to contribute.

## Report an error

Open an issue with the [error form](https://github.com/dengzhe-hou/WMIP/issues/new?template=error_report.yml). It covers wrong gold answers, scoring mistakes, code bugs, and errors in the docs, the website or the leaderboard. Give the release or commit, the `item_id` or file, and the expected and actual result. Every gold answer is computed by code, so these details are usually enough to check the report.

A fix to the code or docs can come as a pull request. The item banks and the stored responses of the 18 paper models are frozen, so their files are not edited in place. A confirmed error in them is recorded in the [release notes](releases/2026-10/RELEASE_NOTES.md) and handled in a new release.

## Submit your model's results

Run all three banks and open a pull request that adds your run under `submissions/`, as described in the [submission guide](submissions/README.md). The check rescores your raw responses with the published rules, and the [leaderboard](https://dengzhe-hou.github.io/WMIP/#community) updates once the pull request is merged. Without a pull request, use the [result form](https://github.com/dengzhe-hou/WMIP/issues/new?template=result_report.yml).

To correct a merged entry, open another pull request that changes its directory.

## Ask a question

Open a blank issue. For questions about the paper, see the [arXiv page](https://arxiv.org/abs/2603.27343).
