const states = [
  { leo: 15, james: 18, carol: 15 },
  { leo: 17, james: 18, carol: 13 },
  { leo: 15, james: 18, carol: 13 },
  { leo: 12, james: 18, carol: 13 },
];

let step = 0;
const nextButton = document.querySelector("#next-step");
const resetButton = document.querySelector("#reset-example");

function renderExample() {
  for (const [name, value] of Object.entries(states[step])) {
    document.querySelector(`#${name}-state`).textContent = value;
  }
  document.querySelector("#state-label").textContent = step === 0 ? "Initial state" : `After update ${step}`;
  document.querySelectorAll("[data-step]").forEach((row) => {
    row.classList.toggle("is-done", Number(row.dataset.step) <= step);
  });
  const complete = step === states.length - 1;
  document.querySelector("#answer-label").textContent = complete ? "Reference answer · Leo's final state" : "How many points does Leo have?";
  document.querySelector("#answer-value").textContent = complete ? states[step].leo : "?";
  nextButton.disabled = complete;
  nextButton.textContent = complete ? "All updates applied" : `Apply update ${step + 1} →`;
  resetButton.disabled = step === 0;
}

nextButton.addEventListener("click", () => {
  step += 1;
  renderExample();
});
resetButton.addEventListener("click", () => {
  step = 0;
  renderExample();
});
document.querySelector(".example-controls").hidden = false;

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const code = document.getElementById(button.dataset.copy).textContent;
    try {
      await navigator.clipboard.writeText(code);
      button.textContent = "Copied";
    } catch {
      button.textContent = "Select code to copy";
    }
    window.setTimeout(() => { button.textContent = "Copy"; }, 2500);
  });
});
