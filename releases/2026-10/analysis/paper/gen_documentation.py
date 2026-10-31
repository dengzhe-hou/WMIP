"""Typeset frozen prompt, score disagreements and model provenance; no inference."""
import csv
import json
from pathlib import Path

from gen_tables import appendix_table, esc, read

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PANEL = ROOT / "results"


def main():
    bank = [json.loads(line) for line in (ROOT.parent / "data/item_bank/item_bank.jsonl").read_text().splitlines()]
    item = next(row for row in bank if row["block"] == "A")
    prompt = "\n\n".join(esc(part).replace("\n", r"\newline ") for part in item["prompt"].split("\n\n"))
    (HERE / "tables/prompt_example.tex").write_text(
        "\\begin{quote}\\small\n" + prompt + "\n\\end{quote}\nThe reference answer is " + str(item["gold"]) + ".\n")
    names = {"falcon3-1b-instruct": "Falcon3 1B", "falcon3-3b-instruct": "Falcon3 3B",
             "llama-3.2-3b-instruct": "Llama 3.2 3B", "command-r7b-12-2024": "Command R7B"}
    # Written by hand from the two parsers' rules; the stored comparison file has no reason column.
    contradiction = "P1 ignores the contradictory ``no permissions'' phrase."
    reasons = {("falcon3-1b-instruct", "E-location-k7-01"): "P1 accepts a substring without word boundaries.",
               ("falcon3-3b-instruct", "F-permissions-k3-06"): "P1 accepts a contradictory permission answer.",
               ("llama-3.2-3b-instruct", "F-permissions-k3-06"): "P1 treats a partial denial as an empty set.",
               ("llama-3.2-3b-instruct", "F-permissions-k5-05"): "P2 rejects a valid empty-set description.",
               ("llama-3.2-3b-instruct", "F-permissions-k5-09"): contradiction,
               ("llama-3.2-3b-instruct", "F-permissions-k7-04"): contradiction,
               ("command-r7b-12-2024", "F-permissions-k7-02"): contradiction}
    changes = read("EF_SCORING_DIFFERENCES_20261004.csv")
    assert len(changes) == len(reasons)
    column = r">{\raggedright\arraybackslash}p"
    appendix_table("scoring_differences.tex", "tab:scoring-differences",
                    "All seven scoring disagreements among 3,240 assignment, set, and count responses. "
                    "Parser 1 accepts every listed response, whereas Parser 2 rejects it. "
                    "[] denotes the empty set. All seven responses stopped normally.",
                    [r"\textbf{Model and item}", r"\textbf{Reference answer}", r"\textbf{Complete response}", r"\textbf{Disagreement reason}"],
                    [[esc(names[r["model"]]) + r"\newline " + esc(r["item_id"]), esc(r["gold"]), esc(r["raw_response"]), reasons[r["model"], r["item_id"]]] for r in changes],
                    spec="@{}" + column + "{3cm}" + column + "{2.6cm}" + column + "{5.2cm}" + column + r"{\dimexpr\textwidth-10.8cm-6\tabcolsep\relax}@{}")
    inputs = read("BFCL_INPUTS_20261004.csv")
    rows = []
    for row in inputs:
        params = f"{int(row['params']) / 1e9:.3f}" if row["params"] else "Unavailable"
        rows.append([esc(row["model"]), params] + [f"{float(row[key]):.2f}" for key in
                    ("bfcl_overall_1216", "bfcl_multi_turn_1216", "bfcl_agentic_1216", "bfcl_single_turn_mean_1216")])
    appendix_table("criterion_inputs.tex", "tab:criterion-inputs",
                    "All external criterion inputs. BFCL scores are percentages from the official 16 December 2025 FC snapshot. "
                    "Single-turn is the mean of Non-Live and Live. Public parameter counts, shown in billions, come from "
                    "model metadata frozen on 2 October 2026. Public counts are available only for the ten local models and the "
                    "two Cohere models. Single-turn BFCL and parameter counts enter only the rank-adjusted analyses in the "
                    "supplementary material.",
                    ["Model", "Parameters (B)", "Overall", "Multi-Turn", "Agentic", "Single-turn"], rows)
    with (ROOT.parent / "external/model_metadata/model_freeze_19.csv").open() as handle:
        freeze = {r["model"].lower(): r for r in csv.DictReader(handle)}
    revisions, manifest = [], []
    for row in inputs:
        if row["kind"] != "open":
            continue
        frozen = freeze[row["run_label"]]
        sha = frozen["hf_sha"]
        repo = frozen["hf_repo"]
        repo_display = r"\path{" + repo + "}"
        if repo == "ibm-granite/granite-3.1-8b-instruct":
            repo_display = r"\shortstack[l]{\path{ibm-granite/}\\\path{granite-3.1-8b-instruct}}"
        revisions.append([repo_display,
                          r"\href{https://huggingface.co/" + repo + "/tree/" + sha + r"}{\texttt{" + sha[:12] + "}}"])
        manifest.append({"model": row["run_label"], "hf_repo": repo, "revision": sha, "params": int(row["params"])})
    appendix_table("local_revisions.tex", "tab:local-revisions",
                    "Pinned repositories for all ten local models. Revision prefixes link to the complete frozen commit. "
                    "The provenance file in the supplementary material retains full commit identifiers and exact parameter counts.",
                    ["Repository", "Revision"], revisions, wide=False, colsep=1,
                    spec=r"@{}>{\raggedright\arraybackslash}p{\dimexpr\columnwidth-65pt\relax}@{\hspace{8pt}}>{\raggedleft\arraybackslash}p{57pt}@{}")
    (HERE / "model_provenance.json").write_text(json.dumps({
        "local": manifest, "all_criterion_inputs": inputs,
        "parser_names": {"Parser 1": "correct_submitted", "Parser 2": "correct_strict (E/F only)"},
        "source_files": ["external/model_metadata/model_freeze_19.csv", "analysis/results/BFCL_INPUTS_20261004.csv"],
    }, indent=2) + "\n")
    assert len(manifest) == 10 and len(inputs) == 18 and len(changes) == 7


if __name__ == "__main__":
    main()
