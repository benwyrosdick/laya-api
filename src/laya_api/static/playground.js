const form = document.getElementById("eval-form");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const runBtn = document.getElementById("run");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "Evaluating…";
  runBtn.disabled = true;
  let questions;
  try {
    questions = JSON.parse(document.getElementById("questions").value);
  } catch (err) {
    statusEl.textContent = "Questions must be valid JSON.";
    runBtn.disabled = false;
    return;
  }
  const stateRaw = document.getElementById("state").value;
  let state = stateRaw;
  try {
    state = JSON.parse(stateRaw);
  } catch {
    state = stateRaw;
  }
  try {
    const response = await fetch("/console/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state,
        model: document.getElementById("model").value,
        questions,
      }),
    });
    const body = await response.json();
    resultEl.textContent = JSON.stringify(body, null, 2);
    statusEl.textContent = response.ok ? "Done" : `Error ${response.status}`;
  } catch (err) {
    statusEl.textContent = String(err);
  } finally {
    runBtn.disabled = false;
  }
});
