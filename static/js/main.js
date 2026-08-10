// Frontend behavior for AI Meeting Summarizer

document.addEventListener("DOMContentLoaded", () => {
    setupTabs();
    setupAudioUpload();
    setupTextForm();
    if (document.getElementById("meetings-body")) loadMeetings();
    if (document.getElementById("report-card")) loadReport();
});

// ---------- Tabs ----------
function setupTabs() {
    const tabs = document.querySelectorAll(".tab");
    if (!tabs.length) return;
    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => { t.classList.remove("active"); t.setAttribute("aria-selected", "false"); });
            tab.classList.add("active");
            tab.setAttribute("aria-selected", "true");
            document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
            document.getElementById(tab.dataset.target).classList.add("active");
        });
    });
}

// ---------- Audio upload ----------
function setupAudioUpload() {
    const form = document.getElementById("audio-form");
    if (!form) return;
    const dropzone = document.getElementById("dropzone");
    const input = document.getElementById("audio-input");
    const submitBtn = form.querySelector("button[type=submit]");

    dropzone.addEventListener("click", () => input.click());
    dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") input.click(); });

    ["dragover", "dragenter"].forEach(ev => dropzone.addEventListener(ev, e => {
        e.preventDefault(); dropzone.classList.add("dragover");
    }));
    ["dragleave", "drop"].forEach(ev => dropzone.addEventListener(ev, e => {
        e.preventDefault(); dropzone.classList.remove("dragover");
    }));
    dropzone.addEventListener("drop", e => {
        if (e.dataTransfer.files.length) {
            input.files = e.dataTransfer.files;
            updateDropzoneLabel();
        }
    });
    input.addEventListener("change", updateDropzoneLabel);

    function updateDropzoneLabel() {
        if (input.files.length) {
            dropzone.querySelector("p").textContent = `Selected: ${input.files[0].name}`;
            submitBtn.disabled = false;
        }
    }

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!input.files.length) return;
        const fd = new FormData();
        fd.append("audio", input.files[0]);
        fd.append("title", form.title.value || input.files[0].name);
        fd.append("language", getLanguage());
        await submitAndTrack(fd, "/api/meetings/upload-audio");
    });
}

// ---------- Text transcript ----------
function setupTextForm() {
    const form = document.getElementById("text-form");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        fd.append("language", getLanguage());
        await submitAndTrack(fd, "/api/meetings/upload-text");
    });
}

// ---------- Language helper ----------
function getLanguage() {
    const sel = document.getElementById("language-select");
    return sel ? sel.value : "auto";
}

// ---------- Submit + poll progress ----------
async function submitAndTrack(formData, endpoint) {
    const progress = document.getElementById("progress");
    const fill = document.getElementById("progress-fill");
    const status = document.getElementById("progress-status");
    progress.classList.remove("hidden");
    fill.style.width = "5%";
    status.textContent = "Uploading...";

    try {
        const res = await fetch(endpoint, { method: "POST", body: formData });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || "Upload failed");
        }
        const data = await res.json();
        await pollStatus(data.meeting_id, fill, status);
        window.location.href = `/meetings/${data.meeting_id}`;
    } catch (err) {
        status.innerHTML = `<span class="error">${err.message}</span>`;
    }
}

async function pollStatus(meetingId, fill, statusEl) {
    const stages = {
        "pending": "Queued...",
        "transcribing": "Transcribing audio with Whisper...",
        "preprocessing": "Cleaning transcript...",
        "summarizing": "Summarizing discussions...",
        "extracting": "Extracting action items & deadlines...",
        "building": "Building report...",
        "done": "Done!",
        "error": "Failed",
    };
    const widths = { pending: 10, transcribing: 30, preprocessing: 50, summarizing: 70, extracting: 85, building: 95, done: 100, error: 100 };

    while (true) {
        try {
            const res = await fetch(`/api/meetings/${meetingId}/status`);
            const data = await res.json();
            const st = data.status || "pending";
            fill.style.width = `${widths[st] ?? 50}%`;
            statusEl.textContent = stages[st] || st;
            if (st === "done") return;
            if (st === "error") throw new Error(data.error || "Processing failed");
        } catch (e) {
            statusEl.innerHTML = `<span class="error">${e.message}</span>`;
            throw e;
        }
        await sleep(1500);
    }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ---------- Past meetings list ----------
async function loadMeetings() {
    try {
        const res = await fetch("/api/meetings");
        const data = await res.json();
        const meetings = data.meetings || data;
        const body = document.getElementById("meetings-body");
        if (!meetings.length) {
            body.innerHTML = `<tr><td colspan="5" class="muted">No meetings yet. <a href="/">Create one</a>.</td></tr>`;
            return;
        }
        body.innerHTML = meetings.map(m => `
            <tr>
                <td>${m.id}</td>
                <td>${escapeHtml(m.title || "Untitled")}</td>
                <td><span class="badge ${m.source_type}">${m.source_type}</span>${m.language ? ` <span class="badge owner">${escapeHtml(m.language)}</span>` : ""}</td>
                <td>${new Date(m.created_at).toLocaleString()}</td>
                <td><a class="btn" href="/meetings/${m.id}">View</a></td>
            </tr>`).join("");
    } catch (e) {
        document.getElementById("meetings-body").innerHTML = `<tr><td colspan="5" class="error">Failed to load: ${e.message}</td></tr>`;
    }
}

// ---------- Meeting report ----------
async function loadReport() {
    const card = document.getElementById("report-card");
    if (!card) return;
    const id = card.dataset.meetingId;
    try {
        const res = await fetch(`/api/meetings/${id}`);
        if (!res.ok) throw new Error("Meeting not found");
        const m = await res.json();
        card.innerHTML = renderReport(m);
        bindExportButtons(m);
    } catch (e) {
        card.innerHTML = `<p class="error">${e.message}</p>`;
    }
}

function renderReport(m) {
    const actions = (m.action_items || []).map(a => `
        <tr>
            <td>${escapeHtml(a.text)}</td>
            <td>${a.owner ? `<span class="badge owner">${escapeHtml(a.owner)}</span>` : '<span class="muted">—</span>'}</td>
            <td>${a.due_date ? `<span class="badge due">${escapeHtml(a.due_date)}</span>` : '<span class="muted">—</span>'}</td>
            <td><span class="muted">${escapeHtml(a.status || "open")}</span></td>
        </tr>`).join("");

    const decisions = (m.decisions || []).map(d => `<li>${escapeHtml(d.text)}</li>`).join("");
    const participants = (m.participants || []).map(p => `<span class="badge owner">${escapeHtml(p)}</span>`).join("");

    return `
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem">
            <div>
                <h1>${escapeHtml(m.title || "Untitled Meeting")}</h1>
                <p class="muted small">
                    <span class="badge ${m.source_type}">${m.source_type}</span>
                    ${m.language ? `<span class="badge owner">${escapeHtml(m.language)}</span>` : ""}
                    &middot; ${new Date(m.created_at).toLocaleString()}
                </p>
            </div>
            <div class="export-row">
                <button class="btn" id="export-json">Export JSON</button>
                <button class="btn" id="export-md">Export Markdown</button>
            </div>
        </div>

        <div class="report-section">
            <h2>Summary</h2>
            <div class="summary-box">${escapeHtml(m.summary || "No summary generated.")}</div>
        </div>

        <div class="report-section">
            <h2>Key Decisions</h2>
            ${decisions ? `<ul>${decisions}</ul>` : '<p class="muted">No decisions detected.</p>'}
        </div>

        <div class="report-section">
            <h2>Action Items</h2>
            ${actions ? `<table class="action-table"><thead><tr><th>Task</th><th>Owner</th><th>Due</th><th>Status</th></tr></thead><tbody>${actions}</tbody></table>` : '<p class="muted">No action items detected.</p>'}
        </div>

        <div class="report-section">
            <h2>Participants</h2>
            <div class="participants">${participants || '<span class="muted">None detected.</span>'}</div>
        </div>

        <details>
            <summary>Raw transcript</summary>
            <div class="transcript">${escapeHtml(m.transcript || "")}</div>
        </details>
    `;
}

function bindExportButtons(m) {
    const jsonBtn = document.getElementById("export-json");
    const mdBtn = document.getElementById("export-md");
    if (jsonBtn) jsonBtn.addEventListener("click", () => download(JSON.stringify(m, null, 2), `${m.id}-report.json`, "application/json"));
    if (mdBtn) mdBtn.addEventListener("click", () => download(renderMarkdown(m), `${m.id}-report.md`, "text/markdown"));
}

function renderMarkdown(m) {
    const lines = [`# ${m.title || "Untitled Meeting"}`, ``, `*Source: ${m.source_type} &middot; Created: ${m.created_at}*`, ``, `## Summary`, m.summary || "", ``, `## Key Decisions`];
    (m.decisions || []).forEach(d => lines.push(`- ${d.text}`));
    lines.push("", "## Action Items", "| Task | Owner | Due | Status |", "| --- | --- | --- | --- |");
    (m.action_items || []).forEach(a => lines.push(`| ${a.text} | ${a.owner || "—"} | ${a.due_date || "—"} | ${a.status || "open"} |`));
    lines.push("", "## Participants", (m.participants || []).join(", "));
    lines.push("", "## Transcript", "```", m.transcript || "", "```");
    return lines.join("\n");
}

function download(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
}

function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
