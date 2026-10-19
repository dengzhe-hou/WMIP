import { generateProblem } from "./generator.mjs?v=1";

const form = document.querySelector("#generator-form");
const seedInput = document.querySelector("#seed");
const lengthInput = document.querySelector("#length");
const promptElement = document.querySelector("#generated-prompt");
const copyButton = document.querySelector("#copy-prompt");
const downloadButton = document.querySelector("#download-item");
const trace = document.querySelector("#state-trace");
const actionStatus = document.querySelector("#action-status");
let currentProblem;

function renderTrace(problem) {
  const names = Object.keys(problem.initial_state);
  const headRow = document.createElement("tr");
  for (const label of ["Step", ...names]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    headRow.append(cell);
  }
  document.querySelector("#trace-head").replaceChildren(headRow);
  const rows = problem.states.map((state, index) => {
    const row = document.createElement("tr");
    const step = document.createElement("th");
    step.scope = "row";
    step.textContent = index === 0 ? "Initial" : index;
    row.append(step);
    for (const name of names) {
      const cell = document.createElement("td");
      cell.textContent = state[name];
      if (name === problem.query_entity) cell.className = "target-state";
      row.append(cell);
    }
    return row;
  });
  document.querySelector("#trace-body").replaceChildren(...rows);
}

function generate() {
  currentProblem = generateProblem(seedInput.valueAsNumber, lengthInput.valueAsNumber);
  const { seed, k, query_entity, gold, prompt } = currentProblem;
  promptElement.textContent = prompt;
  promptElement.scrollTop = 0;
  document.querySelector("#output-meta").textContent = `Seed ${seed} · ${k} ${k === 1 ? "update" : "updates"}`;
  document.querySelector("#reference-answer").textContent = gold;
  document.querySelector("#answer-description").textContent = `${query_entity}’s points after ${k} ${k === 1 ? "update" : "updates"}.`;
  trace.open = false;
  renderTrace(currentProblem);
  actionStatus.textContent = "";
  copyButton.textContent = "Copy question";
  document.querySelector("#generation-status").textContent = `Generated a question with seed ${seed} and ${k} updates. Reference answer: ${gold}.`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  generate();
});

document.querySelector("#new-seed").addEventListener("click", () => {
  seedInput.value = Math.floor(Math.random() * 4294967296);
  form.requestSubmit();
});

copyButton.addEventListener("click", async () => {
  const prompt = currentProblem.prompt;
  try {
    await navigator.clipboard.writeText(prompt);
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(promptElement);
    selection.removeAllRanges();
    selection.addRange(range);
    actionStatus.textContent = "Copy is unavailable in this browser. The question is selected for manual copying.";
    return;
  }
  actionStatus.textContent = "Question copied.";
});

downloadButton.addEventListener("click", () => {
  const { seed, k, probe_idx, prompt, gold } = currentProblem;
  const item = { source: "browser-generated", seed, k, probe_idx, prompt, gold };
  const url = URL.createObjectURL(new Blob([JSON.stringify(item, null, 2) + "\n"], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `wmip-seed-${seed}-length-${k}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
});

generate();
for (const element of [form, copyButton, downloadButton, trace]) element.hidden = false;
