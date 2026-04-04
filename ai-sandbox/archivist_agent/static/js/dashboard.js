/* Archivist Agent Dashboard — Interactive frontend */

const API = "";

async function fetchJSON(url, opts) {
    const res = await fetch(API + url, opts);
    return res.json();
}

// ------------------------------------------------------------------
// Status
// ------------------------------------------------------------------

async function loadStatus() {
    const data = await fetchJSON("/api/status");
    document.getElementById("metric-files").textContent = data.files_tracked;
    document.getElementById("metric-sources").textContent = data.data_sources;
    document.getElementById("metric-privacy").textContent = data.privacy_tools;
    document.getElementById("metric-audit").textContent = data.audit_entries;
}

// ------------------------------------------------------------------
// Files
// ------------------------------------------------------------------

async function loadFiles() {
    const q = document.getElementById("file-search").value;
    const cat = document.getElementById("file-category-filter").value;
    let url = "/api/files/search?";
    if (q) url += `q=${encodeURIComponent(q)}&`;
    if (cat) url += `category=${encodeURIComponent(cat)}&`;
    const files = await fetchJSON(url);
    const tbody = document.getElementById("files-body");
    tbody.innerHTML = files.map(f => `
        <tr>
            <td>${esc(f.path)}</td>
            <td>${esc(f.category)}</td>
            <td>${(f.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join(" ")}</td>
            <td>${esc(f.retention)}</td>
            <td class="${f.encrypted ? "badge-yes" : "badge-no"}">${f.encrypted ? "Yes" : "No"}</td>
            <td><button class="btn-danger" onclick="deleteFile('${esc(f.path)}')">Delete</button></td>
        </tr>
    `).join("");
}

async function deleteFile(path) {
    if (!confirm(`Delete ${path}?`)) return;
    await fetchJSON(`/api/files/${encodeURIComponent(path)}`, { method: "DELETE" });
    refreshAll();
}

// ------------------------------------------------------------------
// Add file modal
// ------------------------------------------------------------------

document.getElementById("add-file-btn").addEventListener("click", () => {
    document.getElementById("add-file-modal").classList.add("active");
});

document.getElementById("cancel-file-btn").addEventListener("click", () => {
    document.getElementById("add-file-modal").classList.remove("active");
});

document.getElementById("save-file-btn").addEventListener("click", async () => {
    const path = document.getElementById("new-file-path").value.trim();
    const category = document.getElementById("new-file-category").value;
    const tagsRaw = document.getElementById("new-file-tags").value;
    const retention = document.getElementById("new-file-retention").value;
    const encrypted = document.getElementById("new-file-encrypted").checked;
    if (!path) { alert("Path is required"); return; }
    const tags = tagsRaw ? tagsRaw.split(",").map(t => t.trim()).filter(Boolean) : [];
    await fetchJSON("/api/files", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, category, tags, retention, encrypted }),
    });
    document.getElementById("add-file-modal").classList.remove("active");
    document.getElementById("new-file-path").value = "";
    document.getElementById("new-file-tags").value = "";
    refreshAll();
});

// ------------------------------------------------------------------
// Sources
// ------------------------------------------------------------------

async function loadSources() {
    const sources = await fetchJSON("/api/sources");
    const tbody = document.getElementById("sources-body");
    tbody.innerHTML = sources.map(s => `
        <tr>
            <td>${esc(s.name)}</td>
            <td>${esc(s.source_type)}</td>
            <td>${(s.data_types || []).map(t => `<span class="tag">${esc(t)}</span>`).join(" ")}</td>
            <td>${s.last_sync ? new Date(s.last_sync).toLocaleString() : "Never"}</td>
            <td><button class="btn-sync" onclick="syncSource('${esc(s.name).toLowerCase().replace(/ /g, '_')}')">Sync</button></td>
        </tr>
    `).join("");
}

async function syncSource(name) {
    await fetchJSON(`/api/sources/${encodeURIComponent(name)}/sync`, { method: "POST" });
    refreshAll();
}

// ------------------------------------------------------------------
// Privacy audit
// ------------------------------------------------------------------

document.getElementById("run-audit-btn").addEventListener("click", async () => {
    const data = await fetchJSON("/api/privacy/audit");
    const el = document.getElementById("audit-results");
    let html = "";
    for (const issue of data.issues || []) {
        html += `<div class="issue">Issue: ${esc(issue)}</div>`;
    }
    for (const rec of data.recommendations || []) {
        html += `<div class="recommendation">Recommendation: ${esc(rec)}</div>`;
    }
    html += `<div class="summary">${data.tools_active}/${data.tools_total} privacy tools active</div>`;
    el.innerHTML = html;
});

// ------------------------------------------------------------------
// Audit log
// ------------------------------------------------------------------

async function loadAuditLog() {
    const entries = await fetchJSON("/api/audit?limit=30");
    const tbody = document.getElementById("audit-body");
    tbody.innerHTML = entries.reverse().map(e => `
        <tr>
            <td>${new Date(e.timestamp).toLocaleString()}</td>
            <td>${esc(e.action)}</td>
            <td class="severity-${e.severity}">${esc(e.severity)}</td>
            <td>${esc(JSON.stringify(e.details))}</td>
        </tr>
    `).join("");
}

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function esc(str) {
    const d = document.createElement("div");
    d.textContent = String(str);
    return d.innerHTML;
}

async function refreshAll() {
    await Promise.all([loadStatus(), loadFiles(), loadSources(), loadAuditLog()]);
}

// Debounced search
let searchTimer;
document.getElementById("file-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadFiles, 300);
});
document.getElementById("file-category-filter").addEventListener("change", loadFiles);

// Refresh button
document.getElementById("refresh-btn").addEventListener("click", refreshAll);

// Auto-refresh every 30s
setInterval(refreshAll, 30000);

// Initial load
refreshAll();
