/* Aplikasi Monitor — frontend vanilla + Chart.js
   Semua data diambil dari API backend (REST + SSE). */
"use strict";

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Util
// ---------------------------------------------------------------------------
function fmtBytes(bytes, digits = 1) {
  if (!bytes || bytes < 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  let i = 0, v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i === 0 ? 0 : digits)} ${units[i]}`;
}

function fmtRate(bps) {
  const prefix = bps < 0 ? "-" : "";
  return `${prefix}${fmtBytes(Math.abs(bps))}/s`;
}

function fmtUptime(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}h ${h}j ${m}m`;
  if (h > 0) return `${h}j ${m}m`;
  return `${m}m ${seconds % 60}s`;
}

function fmtDuration(seconds) {
  if (seconds == null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}j ${m}m` : `${m}m`;
}

function fmtClock(tsSeconds) {
  return new Date(tsSeconds * 1000).toLocaleTimeString("id-ID", { hour12: false });
}

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function setBar(barEl, percent) {
  barEl.style.width = `${Math.min(100, Math.max(0, percent))}%`;
  const parent = barEl.parentElement;
  parent.classList.toggle("crit", percent >= 90);
  parent.classList.toggle("warn", percent >= 70 && percent < 90);
}

function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  services: [],
  processSort: "cpu",
  logSource: null,
  logEntries: [],
  history: { labels: [], cpu: [], mem: [] },
  chart: null,
};

// ---------------------------------------------------------------------------
// Resource live (SSE /api/stream)
// ---------------------------------------------------------------------------
function renderResources(r) {
  // CPU
  $("cpu-value").textContent = `${Math.round(r.cpu.percent)}%`;
  $("cpu-sub").textContent =
    `${r.cpu.count} core · load ${r.cpu.load.map((n) => n.toFixed(2)).join(" / ")}` +
    (r.cpu.freq_mhz ? ` · ${r.cpu.freq_mhz} MHz` : "");
  setBar($("cpu-bar"), r.cpu.percent);

  // Memori
  $("mem-value").textContent = `${Math.round(r.memory.percent)}%`;
  $("mem-sub").textContent = `${fmtBytes(r.memory.used)} / ${fmtBytes(r.memory.total)}`;
  setBar($("mem-bar"), r.memory.percent);

  // Swap
  const swapPct = r.swap.percent || 0;
  $("swap-value").textContent = r.swap.total ? `${Math.round(swapPct)}%` : "—";
  $("swap-sub").textContent = r.swap.total
    ? `${fmtBytes(r.swap.used)} / ${fmtBytes(r.swap.total)}` : "tidak aktif";
  setBar($("swap-bar"), swapPct);

  // Disk root
  const root = r.disk.find((d) => d.mount === "/") || r.disk[0];
  if (root) {
    $("disk-value").textContent = `${Math.round(root.percent)}%`;
    $("disk-sub").textContent = `${fmtBytes(root.used)} / ${fmtBytes(root.total)}`;
    setBar($("disk-bar"), root.percent);
  }

  // Suhu
  const temps = r.temperatures || [];
  if (temps.length) {
    const hottest = temps.reduce((a, b) => ((b.current ?? 0) > (a.current ?? 0) ? b : a));
    $("temp-value").textContent = `${Math.round(hottest.current)}°C`;
    $("temp-sub").textContent = hottest.label + (hottest.critical ? ` · crit ${Math.round(hottest.critical)}°C` : "");
  } else {
    $("temp-value").textContent = "—";
    $("temp-sub").textContent = "sensor tidak tersedia";
  }

  // Kipas
  const fans = r.fans || [];
  if (fans.length) {
    const best = fans.reduce((a, b) => ((b.rpm ?? 0) > (a.rpm ?? 0) ? b : a));
    $("fan-value").textContent = `${best.rpm}`;
    $("fan-sub").textContent = `${best.label} · RPM`;
  } else {
    $("fan-value").textContent = "—";
    $("fan-sub").textContent = "tidak terdeteksi";
  }

  // Baterai
  if (r.battery) {
    $("bat-value").textContent = `${Math.round(r.battery.percent)}%`;
    const left = r.battery.secsleft != null ? ` · sisa ${fmtDuration(r.battery.secsleft)}` : "";
    $("bat-sub").textContent = (r.battery.plugged ? "terhubung adaptor" : "pakai baterai") + left;
    setBar($("bat-bar"), r.battery.percent);
  } else {
    $("bat-value").textContent = "—";
    $("bat-sub").textContent = "tidak ada baterai";
  }

  // Jaringan
  $("net-down").textContent = `↓ ${fmtRate(r.network.down_bps)}`;
  $("net-sub").textContent = `↑ ${fmtRate(r.network.up_bps)} · total ↓${fmtBytes(r.network.recv)} ↑${fmtBytes(r.network.sent)}`;

  // Uptime & riwayat grafik
  const uptime = Date.now() / 1000 - r.boot_time;
  $("uptime").textContent = fmtUptime(uptime);
  pushHistory(r);
}

function pushHistory(r) {
  const h = state.history;
  h.labels.push(fmtClock(r.ts));
  h.cpu.push(r.cpu.percent);
  h.mem.push(r.memory.percent);
  const MAX = 60;
  if (h.labels.length > MAX) { h.labels.shift(); h.cpu.shift(); h.mem.shift(); }
  if (state.chart) state.chart.update("none");
}

function startStream() {
  const source = new EventSource("/api/stream");
  source.onopen = () => setConn(true);
  source.onerror = () => setConn(false);
  source.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      renderResources(payload.resources);
    } catch (err) {
      console.error("payload stream tidak valid", err);
    }
  };
  return source;
}

function setConn(ok) {
  const dot = $("conn-dot");
  dot.classList.toggle("on", ok);
  dot.classList.toggle("off", !ok);
  $("conn-text").textContent = ok ? "terhubung" : "terputus";
}

// ---------------------------------------------------------------------------
// Chart
// ---------------------------------------------------------------------------
function initChart() {
  const ctx = $("history-chart").getContext("2d");
  state.chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: state.history.labels,
      datasets: [
        {
          label: "CPU %",
          data: state.history.cpu,
          borderColor: "#4c9aff",
          backgroundColor: "rgba(76,154,255,.12)",
          fill: true, tension: .35, pointRadius: 0, borderWidth: 2,
        },
        {
          label: "Memori %",
          data: state.history.mem,
          borderColor: "#a371f7",
          backgroundColor: "rgba(163,113,247,.10)",
          fill: true, tension: .35, pointRadius: 0, borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { intersect: false, mode: "index" },
      scales: {
        y: { beginAtZero: true, max: 100, ticks: { color: "#8b949e", callback: (v) => `${v}%` }, grid: { color: "rgba(42,49,64,.5)" } },
        x: { ticks: { color: "#8b949e", maxTicksLimit: 8 }, grid: { display: false } },
      },
      plugins: {
        legend: { labels: { color: "#e6edf3", boxWidth: 12, boxHeight: 12 } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(1)}%` } },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Host info
// ---------------------------------------------------------------------------
async function loadHost() {
  try {
    const host = await getJSON("/api/host");
    $("host-line").textContent =
      `${host.hostname} · ${host.os} · kernel ${host.kernel} · ${host.cpu_count} core`;
    $("uptime").textContent = fmtUptime(host.uptime);
  } catch (err) {
    $("host-line").textContent = "gagal memuat info host";
  }
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------
function serviceBadge(svc) {
  if (svc.active !== "active") return `<span class="badge inactive">${esc(svc.sub || svc.active)}</span>`;
  const cls = ["running", "exited", "failed", "dead"].includes(svc.sub) ? svc.sub : "running";
  return `<span class="badge ${cls}">${esc(svc.sub)}</span>`;
}

function renderServices(data) {
  state.services = data.services || [];
  const pill = $("service-count");
  pill.textContent = `${data.running}/${data.total}`;
  pill.title = `${data.running} jalan, ${data.total} total` +
    (data.failed ? `, ${data.failed} gagal` : "");
  pill.classList.toggle("bad", Boolean(data.failed));
  filterServices();
  populateLogUnits();
}

function filterServices() {
  const term = $("service-search").value.trim().toLowerCase();
  const rows = state.services
    .filter((s) => !term || (s.unit || "").toLowerCase().includes(term) || (s.description || "").toLowerCase().includes(term))
    .slice(0, 200);

  const body = $("services-body");
  if (!rows.length) { body.innerHTML = `<div class="empty">tidak ada service cocok</div>`; return; }

  body.innerHTML = `<table class="tbl tbl-services"><thead><tr><th>Status</th><th>Unit</th><th>Deskripsi</th><th class="num">Aksi</th></tr></thead><tbody>` +
    rows.map((s) => {
      const isActive = s.active === "active";
      const toggle = isActive
        ? `<button class="chip danger" data-act="stop" data-unit="${esc(s.unit)}">stop</button>`
        : `<button class="chip ok" data-act="start" data-unit="${esc(s.unit)}">start</button>`;
      return `<tr>
        <td>${serviceBadge(s)}</td>
        <td class="mono">${esc(s.unit)}</td>
        <td class="truncate" title="${esc(s.description)}">${esc(s.description)}</td>
        <td class="num"><div class="actions">
          <button class="chip" data-act="restart" data-unit="${esc(s.unit)}" title="restart">↻</button>
          ${toggle}
        </div></td>
      </tr>`;
    }).join("") + `</tbody></table>`;
}

async function serviceAction(unit, action) {
  try {
    const res = await fetch(`/api/services/${encodeURIComponent(unit)}/${action}`, { method: "POST" });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail || payload);
      throw new Error(detail);
    }
    toast(`${unit}: ${action} berhasil`, "ok");
  } catch (err) {
    toast(`${unit}: ${action} gagal — ${err.message}`, "error");
  } finally {
    loadServices();
  }
}

async function loadServices() {
  try {
    renderServices(await getJSON("/api/services"));
  } catch (err) {
    $("services-body").innerHTML = `<div class="empty">gagal memuat service: ${esc(err.message)}</div>`;
  }
}

function populateLogUnits() {
  const select = $("log-unit");
  const current = select.value;
  const options = state.services
    .filter((s) => s.active === "active")
    .map((s) => `<option value="${esc(s.unit)}">${esc(s.unit)}</option>`).join("");
  select.innerHTML = `<option value="">semua unit</option>${options}`;
  select.value = current;
}

// ---------------------------------------------------------------------------
// Port
// ---------------------------------------------------------------------------
async function loadPorts() {
  const body = $("ports-body");
  try {
    const data = await getJSON("/api/ports");
    const ports = data.ports || [];
    $("ports-count").textContent = `${ports.length} port`;
    if (!ports.length) { body.innerHTML = `<div class="empty">tidak ada port mendengarkan</div>`; return; }
    body.innerHTML = `<table class="tbl tbl-ports"><thead><tr><th>Port</th><th>Proto</th><th>Alamat</th><th>Proses</th></tr></thead><tbody>` +
      ports.map((p) => {
        const procs = (p.processes || []).map((x) => `${esc(x.name)} <span class="muted">(${x.pid})</span>`).join(", ") || "—";
        const exposed = p.exposed ? ` <span class="badge exposed">terbuka</span>` : "";
        return `<tr>
          <td class="mono">${esc(p.raw_port || p.port)}${exposed}</td>
          <td><span class="badge inactive">${esc(p.proto)}</span></td>
          <td class="mono">${esc(p.address)}</td>
          <td class="truncate" title="${procs}">${procs}</td>
        </tr>`;
      }).join("") + `</tbody></table>`;
  } catch (err) {
    body.innerHTML = `<div class="empty">gagal memuat port: ${esc(err.message)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Proses
// ---------------------------------------------------------------------------
async function loadProcesses() {
  const body = $("processes-body");
  try {
    const data = await getJSON(`/api/processes?sort=${state.processSort}&limit=60`);
    $("proc-count").textContent = `${data.total} proses`;
    body.innerHTML = `<table class="tbl tbl-processes"><thead><tr>
        <th class="num">PID</th><th>Nama</th><th>User</th>
        <th class="num">CPU%</th><th class="num">RAM%</th><th class="num">RSS</th><th>Perintah</th>
      </tr></thead><tbody>` +
      (data.processes || []).map((p) => `<tr>
        <td class="num mono">${p.pid}</td>
        <td>${esc(p.name)}</td>
        <td class="truncate" title="${esc(p.user)}">${esc(p.user)}</td>
        <td class="num">${p.cpu.toFixed(1)}</td>
        <td class="num">${p.mem.toFixed(1)}</td>
        <td class="num">${fmtBytes(p.mem_mb * 1048576, 0)}</td>
        <td class="truncate mono" title="${esc(p.cmd)}">${esc(p.cmd)}</td>
      </tr>`).join("") + `</tbody></table>`;
  } catch (err) {
    body.innerHTML = `<div class="empty">gagal memuat proses: ${esc(err.message)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Sensor
// ---------------------------------------------------------------------------
async function loadSensors() {
  const body = $("sensors-body");
  try {
    const data = await getJSON("/api/sensors");
    if (!data.available) { body.innerHTML = `<div class="empty">${esc(data.error || "sensor tidak tersedia")}</div>`; return; }
    const readings = data.readings || [];
    $("sensor-count").textContent = `${readings.length} pembacaan`;
    body.innerHTML = `<table class="tbl tbl-sensors"><thead><tr><th>Sensor</th><th>Label</th><th class="num">Nilai</th><th class="num">Maks</th><th class="num">Kritis</th></tr></thead><tbody>` +
      readings.map((s) => {
        const hot = s.kind === "temp" && s.crit && s.value >= s.crit * 0.9;
        const value = `${s.value.toFixed(1)}${s.unit ? " " + s.unit : ""}`;
        return `<tr>
          <td class="mono">${esc(s.chip)}</td>
          <td>${esc(s.label)}</td>
          <td class="num ${hot ? "" : ""}" style="${hot ? "color:var(--red);font-weight:600" : ""}">${value}</td>
          <td class="num muted">${s.max != null ? Number(s.max).toFixed(1) : "—"}</td>
          <td class="num muted">${s.crit != null ? Number(s.crit).toFixed(1) : "—"}</td>
        </tr>`;
      }).join("") + `</tbody></table>`;
  } catch (err) {
    body.innerHTML = `<div class="empty">gagal memuat sensor: ${esc(err.message)}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Log
// ---------------------------------------------------------------------------
function logLineClass(level) {
  return ["err", "warning", "crit", "emerg", "alert", "debug"].includes(level) ? level : "";
}

function appendLog(entry) {
  if (entry.error) { toast(`log: ${entry.error}`, "error"); return; }

  const term = $("log-search").value.trim().toLowerCase();
  if (term && !(entry.message || "").toLowerCase().includes(term)) return;

  const body = $("log-body");
  const placeholder = body.querySelector(".empty");
  if (placeholder) placeholder.remove();

  const ts = entry.ts ? new Date(Number(entry.ts) / 1000) : new Date();
  const time = ts.toLocaleTimeString("id-ID", { hour12: false }) + "." +
    String(ts.getMilliseconds()).padStart(3, "0");

  const line = document.createElement("div");
  line.className = `log-line ${logLineClass(entry.level)}`;
  line.innerHTML = `<span class="lt">${time}</span>` +
    `<span class="lu" title="${esc(entry.unit)}">${esc(entry.unit || "-")}</span>` +
    `<span class="lm">${esc(entry.message)}</span>`;

  const atBottom = body.scrollTop + body.clientHeight >= body.scrollHeight - 40;
  body.appendChild(line);
  state.logEntries.push(line);
  while (state.logEntries.length > 800) state.logEntries.shift().remove();
  if ($("log-autoscroll").checked && atBottom) body.scrollTop = body.scrollHeight;
}

function startLogs() {
  if (state.logSource) state.logSource.close();
  const params = new URLSearchParams({ lines: "80" });
  const unit = $("log-unit").value;
  const level = $("log-level").value;
  if (unit) params.set("unit", unit);
  if (level) params.set("priority", level);

  const source = new EventSource(`/api/logs/stream?${params}`);
  source.onmessage = (event) => {
    try { appendLog(JSON.parse(event.data)); } catch (err) { console.error(err); }
  };
  source.onerror = () => { /* EventSource auto-reconnect */ };
  state.logSource = source;
}

// ---------------------------------------------------------------------------
// Tab panel
// ---------------------------------------------------------------------------
const TAB_NAMES = ["services", "ports", "processes", "sensors", "logs"];

function activeTabName() {
  const sel = document.querySelector('.tab[aria-selected="true"]');
  return sel ? sel.dataset.tab : "services";
}

function activateTab(name) {
  if (!TAB_NAMES.includes(name)) name = "services";
  for (const t of TAB_NAMES) {
    const on = t === name;
    const tab = $("tab-" + t);
    const panel = $("panel-" + t);
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    panel.hidden = !on;
  }
  // Log yang tersembunyi tidak bisa auto-scroll; rapikan saat tab dibuka.
  if (name === "logs" && $("log-autoscroll").checked) {
    const body = $("log-body");
    body.scrollTop = body.scrollHeight;
  }
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
}

function bindTabs() {
  const bar = document.querySelector(".tabbar");
  bar.addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (tab) activateTab(tab.dataset.tab);
  });
  bar.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const cur = TAB_NAMES.indexOf(activeTabName());
    let next = cur;
    if (e.key === "ArrowLeft") next = (cur - 1 + TAB_NAMES.length) % TAB_NAMES.length;
    else if (e.key === "ArrowRight") next = (cur + 1) % TAB_NAMES.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TAB_NAMES.length - 1;
    activateTab(TAB_NAMES[next]);
    $("tab-" + TAB_NAMES[next]).focus();
  });
  window.addEventListener("hashchange", () => activateTab(location.hash.slice(1)));
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
function bindEvents() {
  $("service-search").addEventListener("input", filterServices);

  $("services-body").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (btn) serviceAction(btn.dataset.unit, btn.dataset.act);
  });

  document.querySelectorAll(".chip[data-sort]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.processSort = btn.dataset.sort;
      document.querySelectorAll(".chip[data-sort]").forEach((b) =>
        b.setAttribute("aria-pressed", String(b === btn)));
      loadProcesses();
    });
  });

  $("log-unit").addEventListener("change", startLogs);
  $("log-level").addEventListener("change", startLogs);
  $("log-search").addEventListener("input", () => {
    // Filter diterapkan saat baris baru masuk; bersihkan lalu muat ulang.
    $("log-body").innerHTML = `<div class="empty">menunggu log…</div>`;
    state.logEntries = [];
  });
  $("log-clear").addEventListener("click", () => {
    $("log-body").innerHTML = "";
    state.logEntries = [];
  });
}

function tickClock() {
  $("clock").textContent = new Date().toLocaleString("id-ID", { hour12: false });
}

function init() {
  initChart();
  bindEvents();
  bindTabs();
  activateTab(location.hash.slice(1) || "services");
  loadHost();
  loadServices();
  loadPorts();
  loadProcesses();
  loadSensors();
  startStream();
  startLogs();

  // Data yang lebih berat di-refresh berkala.
  setInterval(loadServices, 10000);
  setInterval(loadPorts, 8000);
  setInterval(loadProcesses, 5000);
  setInterval(loadSensors, 5000);
  setInterval(tickClock, 1000);
  tickClock();
}

document.addEventListener("DOMContentLoaded", init);
