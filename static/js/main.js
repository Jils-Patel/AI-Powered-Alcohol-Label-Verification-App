// --- Tab switching ---
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => { t.classList.remove("active"); t.setAttribute("aria-selected", "false"); });
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    document.getElementById(`panel-${tab.dataset.tab}`).classList.add("active");
  });
});

const VERDICT_LABEL = { match: "Match", review: "Needs Review", mismatch: "Mismatch", no_data: "Not Checked", partial: "Partial", unreadable: "Unreadable" };

function badge(verdict) {
  return `<span class="badge ${verdict}">${VERDICT_LABEL[verdict] || verdict}</span>`;
}

function overallBadgeText(overall) {
  return {
    match: "All checked fields match",
    review: "Needs human review",
    mismatch: "Mismatch found",
    no_data: "No application data provided",
    partial: "Checked fields match — some fields had no application data to compare",
    unreadable: "Photo quality too low to verify — retake and re-check",
  }[overall] || overall;
}

function renderFieldRow(key, field) {
  let issuesList = field.issues || [];
  if (field.verdict === "unreadable" && !issuesList.length) {
    issuesList = ["Not clearly visible on this photo -- retake and re-verify manually."];
  }
  const issues = issuesList.length
    ? `<ul class="issues">${issuesList.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`
    : "";
  const sim = field.similarity !== null && field.similarity !== undefined
    ? `<span class="meta">similarity ${(field.similarity * 100).toFixed(0)}%</span>` : "";
  return `
    <div class="field-row">
      <div class="field-row-top">
        <span class="field-name">${escapeHtml(field.label)}</span>
        <div>${sim} ${badge(field.verdict)}</div>
      </div>
      <div class="field-values">
        <div><span class="k">Extracted from label</span>${escapeHtml(field.extracted || "—")}</div>
        <div><span class="k">On application</span>${escapeHtml(field.expected || "—")}</div>
      </div>
      ${issues}
    </div>`;
}

function renderResultCard(result) {
  if (result.error) {
    return `<div class="error-box">${escapeHtml(result.filename ? result.filename + ": " : "")}${escapeHtml(result.error)}</div>`;
  }
  const fieldsHtml = Object.entries(result.fields).map(([k, f]) => renderFieldRow(k, f)).join("");
  const qualityNote = result.image_quality_notes ? ` &middot; image quality: ${escapeHtml(result.image_quality_notes)}` : "";
  const lowConfidence = typeof result.model_confidence === "number" && result.model_confidence < 0.6;
  const qualityWarning = lowConfidence
    ? `<div class="quality-warning">⚠ Low confidence read on this photo (${Math.round(result.model_confidence * 100)}%). Consider retaking it in better lighting, straight-on, before relying on these results.</div>`
    : "";
  return `
    <div class="result-card">
      <div class="result-header">
        <div>
          <div class="result-title">${escapeHtml(result.filename || "Label")}</div>
          <div class="meta">processed in ${result.processing_seconds}s${qualityNote}</div>
        </div>
        ${badge(result.overall)} <span class="meta">${overallBadgeText(result.overall)}</span>
      </div>
      ${qualityWarning}
      ${fieldsHtml}
    </div>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

// --- Single mode ---
const singleDropzone = document.getElementById("single-dropzone");
const singleFileInput = document.getElementById("single-file");
const singlePreview = document.getElementById("single-preview");

setupDropzone(singleDropzone, singleFileInput, (files) => {
  if (files[0]) {
    singlePreview.src = URL.createObjectURL(files[0]);
    singlePreview.hidden = false;
  }
});

document.getElementById("single-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const submitBtn = document.getElementById("single-submit");
  const resultArea = document.getElementById("single-result-area");
  if (!singleFileInput.files.length) return;

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span class="spinner"></span>Verifying…`;
  resultArea.innerHTML = "";

  try {
    const res = await fetch("/api/verify", { method: "POST", body: new FormData(form) });
    const data = await res.json();
    resultArea.innerHTML = renderResultCard(data);
  } catch (err) {
    resultArea.innerHTML = `<div class="error-box">Something went wrong: ${escapeHtml(err.message)}</div>`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Verify Label";
  }
});

// --- Batch mode ---
const batchDropzone = document.getElementById("batch-dropzone");
const batchFilesInput = document.getElementById("batch-files");
const batchFileCount = document.getElementById("batch-file-count");

setupDropzone(batchDropzone, batchFilesInput, (files) => {
  batchFileCount.textContent = files.length
    ? `${files.length} file(s) selected: ${Array.from(files).map((f) => f.name).join(", ")}`
    : "No files selected yet.";
});

let lastBatchResults = [];

document.getElementById("batch-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const submitBtn = document.getElementById("batch-submit");
  const resultArea = document.getElementById("batch-result-area");
  if (!batchFilesInput.files.length) return;

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span class="spinner"></span>Verifying batch…`;
  resultArea.innerHTML = "";

  try {
    const res = await fetch("/api/verify-batch", { method: "POST", body: new FormData(form) });
    const data = await res.json();
    lastBatchResults = data.results || [];
    renderBatchResults(lastBatchResults, resultArea);
  } catch (err) {
    resultArea.innerHTML = `<div class="error-box">Something went wrong: ${escapeHtml(err.message)}</div>`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Verify Batch";
  }
});

function renderBatchResults(results, container) {
  const rows = results.map((r, i) => {
    if (r.error) {
      return `<tr><td>${escapeHtml(r.filename || "")}</td><td colspan="3" class="error-box" style="margin:0">${escapeHtml(r.error)}</td></tr>`;
    }
    return `
      <tr class="batch-row" data-idx="${i}">
        <td>${escapeHtml(r.filename)}</td>
        <td>${badge(r.overall)}</td>
        <td>${r.processing_seconds}s</td>
        <td>▸</td>
      </tr>
      <tr class="batch-detail" id="detail-${i}"><td colspan="4">${renderResultCard(r)}</td></tr>`;
  }).join("");

  container.innerHTML = `
    <div class="result-card">
      <table class="batch-table">
        <thead><tr><th>File</th><th>Result</th><th>Time</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <button class="export-btn" id="export-csv">Export results as CSV</button>
    </div>`;

  container.querySelectorAll(".batch-row").forEach((row) => {
    row.addEventListener("click", () => {
      document.getElementById(`detail-${row.dataset.idx}`).classList.toggle("open");
    });
  });

  document.getElementById("export-csv").addEventListener("click", () => exportCsv(results));
}

function exportCsv(results) {
  const header = ["filename", "overall", "processing_seconds", "field", "extracted", "expected", "verdict", "similarity"];
  const lines = [header.join(",")];
  results.forEach((r) => {
    if (r.error) {
      lines.push([csvEscape(r.filename), "error", "", "", "", csvEscape(r.error), "", ""].join(","));
      return;
    }
    Object.values(r.fields).forEach((f) => {
      lines.push([
        csvEscape(r.filename), r.overall, r.processing_seconds,
        csvEscape(f.label), csvEscape(f.extracted), csvEscape(f.expected), f.verdict, f.similarity ?? ""
      ].join(","));
    });
  });
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "label_verification_results.csv";
  a.click();
}

function csvEscape(val) {
  if (val == null) return "";
  const s = String(val).replace(/"/g, '""');
  return /[",\n]/.test(s) ? `"${s}"` : s;
}

// --- Shared dropzone helper ---
function setupDropzone(zone, input, onFiles) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => onFiles(input.files));
  ["dragenter", "dragover"].forEach((evt) => zone.addEventListener(evt, (e) => { e.preventDefault(); zone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach((evt) => zone.addEventListener(evt, (e) => { e.preventDefault(); zone.classList.remove("dragover"); }));
  zone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      onFiles(input.files);
    }
  });
}
