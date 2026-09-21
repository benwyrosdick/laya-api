const form = document.getElementById("eval-form");
const statusEl = document.getElementById("status");
const panel = document.getElementById("result-panel") || document.getElementById("result");
const runBtn = document.getElementById("run");
const RUN_LABEL = "Evaluate";

function setStatus(text) {
  if (!statusEl) return;
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
}

function setBusy(busy) {
  if (!runBtn) return;
  runBtn.disabled = busy;
  runBtn.setAttribute("aria-busy", busy ? "true" : "false");
  runBtn.replaceChildren();
  if (busy) {
    const spin = document.createElement("span");
    spin.className = "spinner";
    spin.setAttribute("aria-hidden", "true");
    runBtn.append(spin, document.createTextNode("Evaluating"));
  } else {
    runBtn.textContent = RUN_LABEL;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("");
  setBusy(true);
  let questions;
  try {
    questions = JSON.parse(document.getElementById("questions").value);
  } catch (err) {
    setStatus("Questions must be valid JSON.");
    setBusy(false);
    return;
  }
  const stateRaw = document.getElementById("state").value;
  let state = stateRaw;
  try {
    state = JSON.parse(stateRaw);
  } catch {
    state = stateRaw;
  }
  const started = performance.now();
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
    const elapsedMs = performance.now() - started;
    renderResult(body, elapsedMs, response.ok);
    setStatus(response.ok ? "" : `Error ${response.status}`);
  } catch (err) {
    setStatus(String(err));
  } finally {
    setBusy(false);
  }
});

function renderResult(body, elapsedMs, ok) {
  if (!panel) {
    setStatus("Playground result panel is missing. Hard-refresh the page.");
    return;
  }
  panel.replaceChildren();
  if (!ok || !body.answers) {
    panel.append(renderError(body, elapsedMs));
    panel.append(renderRaw(body));
    return;
  }
  panel.append(renderHeader(body, elapsedMs));
  for (const [id, answer] of Object.entries(body.answers)) {
    panel.append(renderAnswer(id, answer));
  }
  panel.append(renderRaw(body));
}

function renderHeader(body, elapsedMs) {
  const header = el("header", "result-head");
  const row = el("div", "result-meta");
  const routeModel = (body.routing && body.routing.model) || body.model || "laya";
  row.append(el("span", "route-badge", String(routeModel).replace(/-/g, " ")));
  row.append(el("span", "meta-chip", `${elapsedMs.toFixed(1)} MS`));
  const usage = body.usage || {};
  const inn = usage.input_tokens ?? "—";
  const out = usage.output_tokens ?? 0;
  row.append(el("span", "meta-chip", `${inn} TOKENS IN / ${out} OUT`));
  header.append(row);
  if (body.routing && body.routing.reason) {
    header.append(el("p", "route-reason", `routing: ${body.routing.reason}`));
  }
  return header;
}

function renderAnswer(id, answer) {
  const type = answer.type;
  if (type === "choice") return renderChoice(id, answer);
  if (type === "score") return renderScore(id, answer);
  if (type === "noul") return renderNoul(id, answer);
  return renderUnknown(id, answer);
}

function renderChoice(id, answer) {
  const block = answerBlock(id, "choice", answer.choice, answer.confidence);
  const entries = Object.entries(answer.probabilities || {}).sort((a, b) => b[1] - a[1]);
  const winner = answer.choice;
  for (const [label, p] of entries) {
    block.append(barRow(label, p, label === winner));
  }
  return block;
}

function renderScore(id, answer) {
  const legend = answer.legend || {};
  const maxLevel = Math.max(0, Object.keys(legend).length - 1);
  const headline = `${Number(answer.score).toFixed(2)} / ${maxLevel}`;
  const block = answerBlock(id, "score", headline, answer.confidence);
  const probs = answer.probabilities || {};
  let topKey = "0";
  let topP = -1;
  for (const [key, p] of Object.entries(probs)) {
    if (p > topP) {
      topP = p;
      topKey = key;
    }
  }
  const keys = Object.keys(legend).sort((a, b) => Number(a) - Number(b));
  for (const key of keys) {
    const label = `${key} · ${legend[key]}`;
    block.append(barRow(label, probs[key] || 0, key === topKey));
  }
  return block;
}

function renderNoul(id, answer) {
  const p = Number(answer.noul);
  const yes = p >= 0.5;
  const conf = answer.confidence ?? Math.max(p, 1 - p);
  const block = answerBlock(id, "noul", yes ? "yes" : "no", conf);
  block.append(barRow("P(true)", p, true, { marker: true }));
  return block;
}

function renderUnknown(id, answer) {
  const block = answerBlock(id, answer.type || "answer", "", null);
  block.append(el("pre", "raw-fallback", JSON.stringify(answer, null, 2)));
  return block;
}

function answerBlock(id, type, value, confidence) {
  const section = el("section", "answer");
  const title = el("div", "answer-title");
  const left = el("div", "answer-id");
  left.append(el("span", "qid", id));
  left.append(el("span", "qtype", type));
  if (value !== "" && value != null) left.append(el("span", "qvalue", String(value)));
  title.append(left);
  if (confidence != null && !Number.isNaN(Number(confidence))) {
    title.append(el("span", "conf", `conf ${Number(confidence).toFixed(2)}`));
  }
  section.append(title);
  return section;
}

function barRow(label, probability, solid, opts = {}) {
  const p = clamp01(probability);
  const row = el("div", "bar-row");
  row.append(el("div", "bar-label", label));
  const track = el("div", "bar-track");
  const fill = el("div", solid ? "bar-fill" : "bar-fill hatch");
  fill.style.width = `${(p * 100).toFixed(2)}%`;
  track.append(fill);
  if (opts.marker) {
    const mark = el("div", "bar-mark");
    mark.style.left = `${(p * 100).toFixed(2)}%`;
    track.append(mark);
  }
  row.append(track);
  row.append(el("div", "bar-pct", `${(p * 100).toFixed(1)}%`));
  return row;
}

function renderRaw(body) {
  const details = el("details", "raw");
  const summary = el("summary", null, "raw response");
  details.append(summary);
  details.append(el("pre", null, JSON.stringify(body, null, 2)));
  return details;
}

function renderError(body, elapsedMs) {
  const box = el("div", "result-error");
  const detail = body && body.detail && typeof body.detail === "object" ? body.detail : body;
  const code = (detail && detail.error) || "error";
  const msg = (detail && detail.message) || (typeof body?.detail === "string" && body.detail) || "Request failed";
  box.append(el("p", "error-title", String(code)));
  box.append(el("p", null, String(msg)));
  box.append(el("p", "hint", `${elapsedMs.toFixed(0)} ms`));
  return box;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null && text !== "") node.textContent = text;
  return node;
}

function clamp01(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return 0;
  return Math.min(1, Math.max(0, n));
}
