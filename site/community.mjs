// Community leaderboard: the 18 paper models plus merged community submissions.
// community.json is written at deploy time by `wmip.py check-submissions --export`.

// Sort by one metric, best first. Equal values share a rank ("1, 2, 2, 4").
// Missing values stay at the bottom without a rank.
export function rankRows(rows, key) {
  const sorted = [...rows].sort((a, b) => (b.scores[key] ?? -1) - (a.scores[key] ?? -1));
  let rank = 0;
  return sorted.map((row, index) => {
    const value = row.scores[key];
    if (value == null) return { ...row, rank: null };
    if (index === 0 || value !== sorted[index - 1].scores[key]) rank = index + 1;
    return { ...row, rank };
  });
}

const percent = (value) => (value == null ? "–" : (100 * value).toFixed(1));
const signed = (value) => (value == null ? "–" : `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(100 * value).toFixed(1)}`);
const gap = (value, control) => (value == null || control == null ? null : value - control);

// Two views of the same scores. "protocol" puts the core prompt next to its written-steps control
// on the same items and shows the difference in percentage points, as in Figure 1b of the paper.
const VIEW_NOTES = {
  all: "",
  protocol: "Core and Budget minus Steps, in percentage points, on the same core items. Steps lets the model write its working.",
};

export function viewOf(board, view) {
  if (view !== "protocol") return { metrics: board.metrics, rows: board.rows, key: "core" };
  const byKey = Object.fromEntries(board.metrics.map((metric) => [metric.key, metric]));
  const metrics = [
    byKey.written_steps,
    byKey.core,
    { key: "core_gap", heading: "Core gap", rule: "Core minus Steps", signed: true },
    byKey.budget_last,
    { key: "budget_gap", heading: "Budget gap", rule: "Budget minus Steps", signed: true },
  ];
  const rows = board.rows.map((row) => ({
    ...row,
    scores: {
      ...row.scores,
      core_gap: gap(row.scores.core, row.scores.written_steps),
      budget_gap: gap(row.scores.budget_last, row.scores.written_steps),
    },
  }));
  return { metrics, rows, key: "core_gap" };
}

function render(board, table, view, key) {
  const shown = viewOf(board, view);
  key ??= shown.key;
  const rows = shown.rows;
  const head = document.createElement("tr");
  for (const label of ["#", "Model", "Source"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    head.append(cell);
  }
  for (const metric of shown.metrics) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.title = metric.rule;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = metric.heading;
    button.setAttribute("aria-pressed", String(metric.key === key));
    button.addEventListener("click", () => render(board, table, view, metric.key));
    cell.append(button);
    if (metric.key === key) cell.setAttribute("aria-sort", "descending");
    head.append(cell);
  }
  const body = document.createElement("tbody");
  for (const row of rankRows(rows, key)) {
    const line = document.createElement("tr");
    if (row.source === "Community") line.className = "community-row";
    const rank = document.createElement("td");
    rank.textContent = row.rank ?? "";
    const name = document.createElement("th");
    name.scope = "row";
    if (row.evidence_url) {
      const link = document.createElement("a");
      link.href = row.evidence_url;
      link.textContent = row.model;
      name.append(link);
    } else {
      name.textContent = row.model;
    }
    const source = document.createElement("td");
    source.textContent = row.source === "Community" ? `Community, ${row.submitted}` : "Paper";
    line.append(rank, name, source);
    for (const metric of shown.metrics) {
      const cell = document.createElement("td");
      cell.textContent = (metric.signed ? signed : percent)(row.scores[metric.key]);
      line.append(cell);
    }
    body.append(line);
  }
  const thead = document.createElement("thead");
  thead.append(head);
  table.replaceChildren(table.querySelector("caption"), thead, body);
}

export async function initCommunity() {
  const table = document.getElementById("community-table");
  const status = document.getElementById("community-status");
  if (!table) return;
  try {
    const response = await fetch("community.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const board = await response.json();
    board.rows = [
      ...board.paper.map((row) => ({ ...row, source: "Paper" })),
      ...board.community.map((row) => ({ ...row, source: "Community" })),
    ];
    render(board, table, "all");
    const note = document.getElementById("community-view-note");
    const buttons = document.querySelectorAll(".view-switch button");
    for (const button of buttons) {
      button.addEventListener("click", () => {
        for (const other of buttons) other.setAttribute("aria-pressed", String(other === button));
        note.textContent = VIEW_NOTES[button.dataset.view];
        render(board, table, button.dataset.view);
      });
    }
    const count = board.community.length;
    status.textContent = count
      ? `${count} community result${count === 1 ? "" : "s"}.`
      : "No community results yet.";
  } catch (error) {
    status.textContent = "The leaderboard could not be loaded.";
  }
}

export function initCitation() {
  const button = document.getElementById("copy-bibtex");
  const status = document.getElementById("bibtex-status");
  if (!button) return;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(document.getElementById("bibtex-text").textContent);
      status.textContent = "BibTeX copied.";
    } catch (error) {
      status.textContent = "Copy failed. Select the text instead.";
    }
  });
}
