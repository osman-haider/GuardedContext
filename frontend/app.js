// GuardedContext frontend — plain JS, no build step, no framework.
// Talks to the FastAPI backend mounted at the same origin.

const state = {
  demoCode: null,
  samples: [],
};

function authHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  if (state.demoCode) headers["X-Demo-Code"] = state.demoCode;
  return headers;
}

async function init() {
  bindStaticEvents();
  const health = await fetch("/health").then((r) => r.json()).catch(() => ({ auth_required: false }));

  if (health.auth_required) {
    document.getElementById("authCard").classList.remove("hidden");
  } else {
    await unlockAndLoad();
  }
}

function bindStaticEvents() {
  document.getElementById("authSubmitBtn").addEventListener("click", onAuthSubmit);
  document.getElementById("authCodeInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") onAuthSubmit();
  });
  document.getElementById("evaluateBtn").addEventListener("click", onEvaluateClick);
  document.getElementById("runBatchBtn").addEventListener("click", onRunBatchClick);
  document.getElementById("clearBatchBtn").addEventListener("click", clearBatch);
  document.getElementById("loadHistoryBtn").addEventListener("click", loadHistory);
  document.getElementById("sampleSelect").addEventListener("change", (e) => {
    if (e.target.value) document.getElementById("customQuestion").value = e.target.value;
  });
}

async function onAuthSubmit() {
  const code = document.getElementById("authCodeInput").value.trim();
  state.demoCode = code;
  const ok = await fetch("/samples", { headers: authHeaders() }).then((r) => r.ok).catch(() => false);
  if (!ok) {
    document.getElementById("authError").classList.remove("hidden");
    return;
  }
  document.getElementById("authError").classList.add("hidden");
  document.getElementById("authCard").classList.add("hidden");
  await unlockAndLoad();
}

async function unlockAndLoad() {
  document.getElementById("mainContent").classList.remove("hidden");
  await loadSamples();
  await loadHistory();
}

async function loadSamples() {
  const samples = await fetch("/samples", { headers: authHeaders() }).then((r) => r.json());
  state.samples = samples;
  const select = document.getElementById("sampleSelect");
  select.innerHTML = '<option value="">— choose a sample question —</option>';
  samples.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.question;
    opt.textContent = `[${s.expected_risk_tier}${s.expected_guardrail_trigger ? " · expected flag" : ""}] ${s.question}`;
    select.appendChild(opt);
  });
}

// ---------- Single question ----------

async function onEvaluateClick() {
  const question = document.getElementById("customQuestion").value.trim();
  if (question.length < 3) {
    alert("Please enter or select a question first.");
    return;
  }
  const btn = document.getElementById("evaluateBtn");
  const statusEl = document.getElementById("evalStatus");
  const errorEl = document.getElementById("evalError");
  btn.disabled = true;
  statusEl.classList.remove("hidden");
  errorEl.classList.add("hidden");
  document.getElementById("resultPanel").classList.add("hidden");

  try {
    const res = await fetch("/evaluate", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const result = await res.json();
    renderResult(result);
    loadHistory();
  } catch (err) {
    errorEl.textContent = `Something went wrong calling the pipeline: ${err.message}`;
    errorEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    statusEl.classList.add("hidden");
  }
}

function renderResult(result) {
  const panel = document.getElementById("resultPanel");
  panel.classList.remove("hidden");

  const risk = result.risk_classification;
  const riskPill = document.getElementById("riskPill");
  riskPill.textContent = risk.category;
  riskPill.className = "pill " + severityForRisk(risk.category);
  document.getElementById("riskReasoning").textContent = risk.reasoning || "";

  const actionPill = document.getElementById("actionPill");
  actionPill.textContent = result.final_action.replaceAll("_", " ");
  actionPill.className = "pill action-" + result.final_action;
  document.getElementById("providerUsed").textContent = `via ${result.final_provider_model}`;

  document.getElementById("rawAnswerText").textContent = result.raw_primary_answer || "(no answer produced)";
  document.getElementById("finalAnswerText").textContent = result.final_answer;

  const g = result.guardrail_evaluation;
  const flagsList = document.getElementById("flagsList");
  flagsList.innerHTML = "";
  const flagDefs = [
    ["missed_urgency", "Missed urgency"],
    ["inappropriate_recommendation", "Inappropriate recommendation"],
    ["incorrect_treatment_advice", "Incorrect treatment advice"],
    ["missing_critical_info", "Missing critical info"],
  ];
  if (g) {
    flagDefs.forEach(([key, label]) => {
      const li = document.createElement("li");
      li.textContent = label;
      li.className = g[key] ? "on" : "off";
      flagsList.appendChild(li);
    });
    document.getElementById("rationaleText").textContent =
      `Severity: ${g.severity} — ${g.rationale}`;
  } else {
    flagDefs.forEach(([, label]) => {
      const li = document.createElement("li");
      li.textContent = label + " (not evaluated — provider error)";
      li.className = "off";
      flagsList.appendChild(li);
    });
    document.getElementById("rationaleText").textContent = result.error_detail
      ? `Provider/parsing error: ${result.error_detail}`
      : "";
  }
}

function severityForRisk(category) {
  if (category === "urgency_adjacent") return "high";
  if (category === "medication_related") return "medium";
  if (category === "symptom_explanation") return "low";
  return "none";
}

// ---------- Batch benchmark (streamed) ----------

async function onRunBatchClick() {
  clearBatch();
  const btn = document.getElementById("runBatchBtn");
  const statusEl = document.getElementById("batchStatus");
  btn.disabled = true;
  statusEl.classList.remove("hidden");
  document.getElementById("scorecard").classList.remove("hidden");
  document.getElementById("categoryBars").classList.remove("hidden");
  document.getElementById("batchTable").classList.remove("hidden");

  const tally = {
    total: 0,
    correct: 0,
    flagged: 0,
    fallback: 0,
    safeTemplate: 0,
    byCategory: {},
  };

  try {
    const res = await fetch("/run-batch", { method: "POST", headers: authHeaders() });
    if (!res.ok || !res.body) throw new Error(`Server returned ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete trailing line for next chunk
      for (const line of lines) {
        if (!line.trim()) continue;
        const item = JSON.parse(line);
        appendBatchRow(item, tally);
        updateScorecard(tally);
      }
      statusEl.textContent = `Running… ${tally.total} / ${state.samples.length} questions completed`;
    }
    statusEl.textContent = `Done — ${tally.total} questions evaluated.`;
  } catch (err) {
    statusEl.textContent = `Batch run failed: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

function appendBatchRow(item, tally) {
  tally.total += 1;
  if (item.is_correct) tally.correct += 1;
  if (item.any_flag) tally.flagged += 1;
  if (item.final_action === "provider_fallback_passed") tally.fallback += 1;
  if (item.final_action === "safe_template") tally.safeTemplate += 1;

  tally.byCategory[item.risk_category] = tally.byCategory[item.risk_category] || { total: 0, flagged: 0 };
  tally.byCategory[item.risk_category].total += 1;
  if (item.any_flag) tally.byCategory[item.risk_category].flagged += 1;

  const tbody = document.getElementById("batchTableBody");
  const row = document.createElement("tr");
  row.className = item.is_correct ? "correct" : "incorrect";
  row.innerHTML = `
    <td>${item.id}</td>
    <td>${escapeHtml(item.question)}</td>
    <td>${item.risk_category}</td>
    <td>${item.expected_guardrail_trigger ? "yes" : "no"}</td>
    <td>${item.any_flag ? "yes (" + item.severity + ")" : "no"}</td>
    <td><span class="pill action-${item.final_action}">${item.final_action.replaceAll("_", " ")}</span></td>
    <td class="match">${item.is_correct ? "✓ as expected" : "✗ unexpected"}</td>
  `;
  tbody.appendChild(row);
}

function updateScorecard(tally) {
  document.getElementById("metricTotal").textContent = tally.total;
  document.getElementById("metricAccuracy").textContent =
    tally.total ? Math.round((tally.correct / tally.total) * 100) + "%" : "0%";
  document.getElementById("metricFlagged").textContent = tally.flagged;
  document.getElementById("metricFallback").textContent = tally.fallback;
  document.getElementById("metricSafeTemplate").textContent = tally.safeTemplate;

  const container = document.getElementById("categoryBars");
  container.innerHTML = "";
  Object.entries(tally.byCategory).forEach(([category, counts]) => {
    const pct = counts.total ? Math.round((counts.flagged / counts.total) * 100) : 0;
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <div class="bar-label">${category}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="bar-value">${counts.flagged}/${counts.total} flagged</div>
    `;
    container.appendChild(row);
  });
}

function clearBatch() {
  document.getElementById("batchTableBody").innerHTML = "";
  document.getElementById("categoryBars").innerHTML = "";
  document.getElementById("batchStatus").textContent = "";
  ["metricTotal", "metricFlagged", "metricFallback", "metricSafeTemplate"].forEach(
    (id) => (document.getElementById(id).textContent = "0")
  );
  document.getElementById("metricAccuracy").textContent = "0%";
}

// ---------- History ----------

async function loadHistory() {
  try {
    const rows = await fetch("/history?limit=30", { headers: authHeaders() }).then((r) => r.json());
    const table = document.getElementById("historyTable");
    const tbody = document.getElementById("historyTableBody");
    tbody.innerHTML = "";
    if (!rows.length) {
      table.classList.add("hidden");
      return;
    }
    table.classList.remove("hidden");
    rows.forEach((r) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${new Date(r.timestamp).toLocaleTimeString()}</td>
        <td>${r.session_id}</td>
        <td>${escapeHtml(r.question)}</td>
        <td>${r.risk_category}</td>
        <td><span class="pill action-${r.final_action}">${r.final_action.replaceAll("_", " ")}</span></td>
        <td>${r.any_flag ? "yes (" + r.severity + ")" : "no"}</td>
      `;
      tbody.appendChild(row);
    });
  } catch (err) {
    // History is a nice-to-have view; fail quietly if the backend isn't reachable yet.
    console.warn("Could not load history:", err);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

init();
