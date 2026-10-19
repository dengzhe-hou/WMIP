import { generateProblem } from "./generator.mjs";
import { generateBatchItems, serializeItem } from "./batch.mjs?v=1";

const $ = (selector) => document.querySelector(selector);
const settingsForm = $("#game-settings-form");
const answerForm = $("#answer-form");
const action = $("#game-action");
const solution = $("#solution");
const promptElement = $("#generated-prompt");
let seed = crypto.getRandomValues(new Uint32Array(1))[0];
let length = 3;
let round = 0;
let correct = 0;
let answered = 0;
let step = 0;
let phase = "ready";
let problem;

function showStage(name) {
  phase = name;
  for (const stage of ["ready", "updates", "answer", "result"]) {
    $(`#${stage}-stage`).hidden = stage !== name;
  }
  answerForm.hidden = name !== "answer";
  action.hidden = name === "answer";
}

function renderTrace() {
  const names = Object.keys(problem.initial_state);
  const head = document.createElement("tr");
  for (const label of ["Step", ...names]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    head.append(cell);
  }
  $("#trace-head").replaceChildren(head);
  const rows = problem.states.map((state, index) => {
    const row = document.createElement("tr");
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = index === 0 ? "Initial" : index;
    row.append(label);
    for (const name of names) {
      const cell = document.createElement("td");
      cell.textContent = state[name];
      if (name === problem.query_entity) cell.className = "target-state";
      row.append(cell);
    }
    return row;
  });
  $("#trace-body").replaceChildren(...rows);
}

function prepareRound() {
  problem = generateProblem(seed, length, round);
  step = 0;
  $("#round-label").textContent = `Round ${round + 1}`;
  $("#score-label").textContent = `${correct} correct · ${answered} answered`;
  $("#output-meta").textContent = `Seed ${seed} · ${length} ${length === 1 ? "update" : "updates"}`;
  const entities = Object.entries(problem.initial_state).map(([name, value]) => {
    const entity = document.createElement("div");
    const label = document.createElement("span");
    const number = document.createElement("strong");
    label.textContent = name;
    number.textContent = value;
    entity.append(label, number);
    return entity;
  });
  $("#starting-points").replaceChildren(...entities);
  $("#player-answer").value = "";
  $("#reference-answer").textContent = "";
  $("#result-title").textContent = "";
  $("#result-note").textContent = "";
  promptElement.textContent = "";
  $("#trace-body").replaceChildren();
  solution.hidden = true;
  solution.open = false;
  $("#action-status").textContent = "";
  action.textContent = "Start";
  showStage("ready");
}

function showUpdate() {
  $("#update-count").textContent = `Update ${step + 1} of ${length}`;
  $("#operation-text").textContent = problem.ops[step][0];
  $("#update-progress").max = length;
  $("#update-progress").value = step + 1;
  action.textContent = step === length - 1 ? "Answer" : "Next update";
  showStage("updates");
}

function finishRound(value, revealed = false) {
  if (phase !== "answer") return;
  if (!revealed) {
    answered++;
    if (value === problem.gold) correct++;
  }
  $("#result-title").textContent = revealed ? "Answer revealed." : value === problem.gold ? "Correct." : "The reference answer is";
  $("#reference-answer").textContent = problem.gold;
  $("#result-note").textContent = revealed
    ? "This round does not count toward your score."
    : value === problem.gold ? `${problem.query_entity}’s final score.` : `You answered ${value}.`;
  $("#score-label").textContent = `${correct} correct · ${answered} answered`;
  promptElement.textContent = problem.prompt;
  renderTrace();
  solution.hidden = false;
  action.textContent = "Next round";
  showStage("result");
  action.focus({ preventScroll: true });
}

action.addEventListener("click", () => {
  if (phase === "ready") {
    showUpdate();
  } else if (phase === "updates" && step < length - 1) {
    step++;
    showUpdate();
  } else if (phase === "updates") {
    $("#answer-question").textContent = `How many points does ${problem.query_entity} have?`;
    showStage("answer");
    $("#player-answer").focus({ preventScroll: true });
  } else if (phase === "result") {
    round++;
    prepareRound();
  }
});

answerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  finishRound($("#player-answer").valueAsNumber);
});
$("#reveal-answer").addEventListener("click", () => finishRound(null, true));

settingsForm.addEventListener("submit", (event) => {
  event.preventDefault();
  seed = $("#seed").valueAsNumber;
  length = $("#length").valueAsNumber;
  round = correct = answered = 0;
  prepareRound();
  $(".game-settings").open = false;
  action.focus({ preventScroll: true });
});

function download(parts, filename, type) {
  const url = URL.createObjectURL(new Blob(parts, { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$("#copy-prompt").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(problem.prompt);
    $("#action-status").textContent = "Question copied.";
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(promptElement);
    selection.removeAllRanges();
    selection.addRange(range);
    $("#action-status").textContent = "The question is selected for manual copying.";
  }
});
$("#download-item").addEventListener("click", () => {
  const { seed, k, probe_idx, prompt, gold } = problem;
  download([JSON.stringify({ source: "browser-generated", seed, k, probe_idx, prompt, gold }, null, 2) + "\n"], `wmip-s${seed}-k${k}-p${probe_idx}.json`, "application/json");
});

const batchForm = $("#batch-form");
const batchFields = $("#batch-fields");
const batchStatus = $("#batch-status");
const cancelButton = $("#cancel-batch");
let cancelBatch = false;
let batchRunning = false;
cancelButton.addEventListener("click", () => { cancelBatch = true; });

batchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (batchRunning) return;
  const count = $("#batch-count").valueAsNumber;
  const batchSeed = $("#batch-seed").valueAsNumber;
  const k = $("#batch-length").valueAsNumber;
  batchRunning = true;
  cancelBatch = false;
  batchFields.disabled = true;
  cancelButton.hidden = false;
  const lines = [];
  batchStatus.textContent = `Generating 0 of ${count} questions…`;
  try {
    // Yield between small groups so large exports do not block the game or Cancel.
    await new Promise(resolve => setTimeout(resolve, 0));
    for (const item of generateBatchItems(batchSeed, k, count)) {
      if (cancelBatch) break;
      lines.push(serializeItem(item));
      if (lines.length % 10 === 0) {
        batchStatus.textContent = `Generating ${lines.length} of ${count} questions…`;
        await new Promise(resolve => setTimeout(resolve, 0));
      }
    }
    if (cancelBatch) {
      batchStatus.textContent = "Export cancelled. No file was downloaded.";
    } else {
      download(lines, `wmip-${count}-s${batchSeed}-k${k}.jsonl`, "application/x-ndjson");
      batchStatus.textContent = `Downloaded ${count} ${count === 1 ? "question" : "questions"} with reference answers.`;
    }
  } catch (error) {
    batchStatus.textContent = `Export failed: ${error.message}`;
  } finally {
    batchRunning = false;
    batchFields.disabled = false;
    cancelButton.hidden = true;
  }
});

$("#seed").value = seed;
prepareRound();
$("#playground").hidden = false;
