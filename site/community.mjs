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

function render(board, table, key) {
  const rows = [
    ...board.paper.map((row) => ({ ...row, source: "Paper" })),
    ...board.community.map((row) => ({ ...row, source: "Community" })),
  ];
  const head = document.createElement("tr");
  for (const label of ["#", "Model", "Source"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    head.append(cell);
  }
  for (const metric of board.metrics) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.title = metric.rule;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = metric.heading;
    button.setAttribute("aria-pressed", String(metric.key === key));
    button.addEventListener("click", () => render(board, table, metric.key));
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
    for (const metric of board.metrics) {
      const cell = document.createElement("td");
      cell.textContent = percent(row.scores[metric.key]);
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
    render(board, table, "core");
    const count = board.community.length;
    status.textContent = count
      ? `${count} community result${count === 1 ? "" : "s"}.`
      : "No community results yet.";
  } catch (error) {
    status.textContent = "The leaderboard could not be loaded.";
  }
}
