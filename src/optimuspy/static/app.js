/* ============================================================
   OptimusPy Dashboard — app.js
   Single IIFE module: API, Router, Toast, Modal, Theme, Table,
   DimensionConfigurator, StreamManager, Sidebar and the page modules.
   ============================================================ */

const OptimusPy = (function () {
  "use strict";

  // ==================================================================
  // State
  // ==================================================================
  const state = {
    // Connection
    instances: [],
    activeInstance: null,
    connected: false,
    serverName: null,
    // The config.ini in use: { config_path, source, own_copy_exists, error }
    config: {},

    // Scan
    scanData: null,
    scanTimestamp: null,  // Date.now() when last scan completed

    // Cubes & configs
    savedCubes: [],
    cubeMetadata: {},   // cubeName → { dimensions_metadata, storage_order, suggested_order }
    cubeViews: {},      // cubeName → [view names]
    processes: [],      // all TI process names

    // Jobs
    jobs: [],

    // UI prefs
    theme: localStorage.getItem("op-theme") || "system",
    sidebarCollapsed: localStorage.getItem("op-sidebar") === "collapsed",
  };

  // ==================================================================
  // Icons (inline SVG strings — Lucide style)
  // ==================================================================
  const Icons = {
    x: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    check: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    alertTriangle: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    info: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    chevronRight: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>',
    chevronLeft: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>',
    arrowRight: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>',
    arrowLeft: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>',
    play: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    download: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    refresh: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>',
    trash: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>',
    search: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    zap: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    sun: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
    moon: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>',
    monitor: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
    externalLink: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
    gripVertical: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="5" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="19" r="1"/></svg>',
    lock: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>',
    unlock: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 019.9-1"/></svg>',
    rotateCcw: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>',
    square: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" stroke="none"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>',
    plus: '<svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    transfer: '<svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"/><line x1="3" y1="5" x2="21" y2="5"/><polyline points="7 23 3 19 7 15"/><line x1="21" y1="19" x2="3" y2="19"/></svg>',
  };

  // ==================================================================
  // Helpers
  // ==================================================================
  function $(sel, parent) { return (parent || document).querySelector(sel); }
  function $$(sel, parent) { return Array.from((parent || document).querySelectorAll(sel)); }
  function el(tag, attrs, ...children) {
    const e = document.createElement(tag);
    if (attrs) Object.entries(attrs).forEach(([k, v]) => {
      if (k === "className") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === "html") e.innerHTML = v;
      else if (k === "dataset") Object.assign(e.dataset, v);
      else e.setAttribute(k, v);
    });
    children.forEach(c => {
      if (c == null) return;
      if (typeof c === "string") e.appendChild(document.createTextNode(c));
      else e.appendChild(c);
    });
    // Keyboard activation for non-button elements with role="button"
    if (attrs && attrs.role === "button" && tag !== "button") {
      e.addEventListener("keydown", ev => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); e.click(); }
      });
    }
    return e;
  }
  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + " MB";
    return (bytes / 1073741824).toFixed(2) + " GB";
  }
  function formatDate(ts) {
    return new Date(ts * 1000).toLocaleString();
  }
  function formatDuration(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  }

  // ---- Jobs: where each kind lives in the UI, and how its state reads ----
  // Single-cube jobs belong to their cube's Optimize tab; the instance-wide pass
  // and the order sync have pages of their own. A job's label is its cube, its
  // plan id (Optimize DB) or its cube count (a sync).
  const JOB_KINDS = {
    "optimize-db": { page: "#/optimize-db", title: "Optimize DB" },
    transfer: { page: "#/transfer", title: "Sync Order" },
  };
  function jobLink(job) {
    const kind = JOB_KINDS[job.mode];
    return kind ? kind.page : `#/cube/${encodeURIComponent(job.label)}?tab=optimize`;
  }
  function jobTitle(job) {
    const kind = JOB_KINDS[job.mode];
    return kind ? kind.title : "Optimizing";
  }
  const JOB_STATUS_BADGES = { running: "badge-info", completed: "badge-success", cancelled: "badge-warning", failed: "badge-error" };
  function jobStatusBadge(status) {
    return el("span", { className: `badge ${JOB_STATUS_BADGES[status] || "badge-neutral"}` }, status);
  }

  // How long a job has been running, counted from when the server started it,
  // so leaving the page and coming back does not reset it. start() replaces
  // whatever the timer was showing; stop() is safe to call at any time.
  function createElapsedTimer() {
    let interval = null;
    return {
      start(target, startedAtSeconds) {
        this.stop();
        const tick = () => {
          const s = Math.max(0, Math.floor(Date.now() / 1000 - startedAtSeconds));
          target.textContent = [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60]
            .map(n => String(n).padStart(2, "0")).join(":");
        };
        tick();
        interval = setInterval(tick, 1000);
      },
      stop() {
        if (interval !== null) { clearInterval(interval); interval = null; }
      },
    };
  }
  // ---- Scan cache (localStorage, keyed by instance) ----
  const ScanCache = {
    _key(instance) { return `op-scan-${instance}`; },
    save(instance, scanData) {
      const entry = { data: scanData, ts: Date.now() };
      try { localStorage.setItem(this._key(instance), JSON.stringify(entry)); } catch { /* quota */ }
    },
    load(instance) {
      try {
        const raw = localStorage.getItem(this._key(instance));
        if (!raw) return null;
        const entry = JSON.parse(raw);
        // Expire after 24 hours
        if (Date.now() - entry.ts > 86400000) { this.clear(instance); return null; }
        return entry;
      } catch { return null; }
    },
    clear(instance) {
      try { localStorage.removeItem(this._key(instance)); } catch { /* */ }
    },
    formatAge(ts) {
      if (!ts) return "";
      const mins = Math.floor((Date.now() - ts) / 60000);
      if (mins < 1) return "just now";
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      return `${Math.floor(hrs / 24)}d ago`;
    },
  };

  // ---- Cube intelligence cache (localStorage, keyed by instance+cube) ----
  const IntelCache = {
    _key(instance, cube) { return `op-intel-${instance}-${cube}`; },
    save(instance, cube, data) {
      const entry = { data, ts: Date.now() };
      try { localStorage.setItem(this._key(instance, cube), JSON.stringify(entry)); } catch { /* quota */ }
    },
    load(instance, cube) {
      try {
        const raw = localStorage.getItem(this._key(instance, cube));
        if (!raw) return null;
        const entry = JSON.parse(raw);
        // Expire after 7 days
        if (Date.now() - entry.ts > 7 * 86400000) { this.clear(instance, cube); return null; }
        return entry;
      } catch { return null; }
    },
    clear(instance, cube) {
      try { localStorage.removeItem(this._key(instance, cube)); } catch { /* */ }
    },
  };

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  // ==================================================================
  // API Client
  // ==================================================================
  const Api = {
    async _fetch(method, url, body) {
      const opts = { method, headers: {} };
      if (body) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
      const res = await fetch(url, opts);
      const data = await res.json();
      if (!res.ok) throw Object.assign(new Error(data.error || `HTTP ${res.status}`), { status: res.status, data });
      return data;
    },
    getInstances() { return this._fetch("GET", "/api/instances"); },
    getInstance(name) { return this._fetch("GET", `/api/instance/${encodeURIComponent(name)}`); },
    setConfigSource(body) { return this._fetch("POST", "/api/config-source", body); },
    connect(instance, password) { return this._fetch("POST", "/api/connect", { instance, password }); },
    scan(instance, password, ramPercent, includeOptimized) {
      return this._fetch("POST", "/api/scan", { instance, password, ram_percent: ramPercent, include_optimized: includeOptimized });
    },
    getViews(instance, password, cube) { return this._fetch("POST", "/api/views", { instance, password, cube }); },
    getProcesses(instance, password) { return this._fetch("POST", "/api/processes", { instance, password }); },
    getProcessParameters(instance, password, processName) {
      return this._fetch("POST", "/api/process_parameters", { instance, password, process_name: processName });
    },
    getCubeIntelligence(instance, password, cube) {
      return this._fetch("POST", "/api/cube_intelligence", { instance, password, cube });
    },
    saveConfig(config, filename) { return this._fetch("POST", "/api/config", { config, filename }); },
    deleteConfig(filename) { return this._fetch("DELETE", `/api/config/${encodeURIComponent(filename)}`); },
    getSavedCubes() { return this._fetch("GET", "/api/saved-cubes"); },
    getFolders() { return this._fetch("GET", "/api/folders"); },
    setFolder(body) { return this._fetch("POST", "/api/folders", body); },
    validate(config, mode) { return this._fetch("POST", "/api/validate", { config, mode }); },
    startJob(mode, cubeConfig, password) {
      return this._fetch("POST", "/api/job/start", { mode, cube_config: cubeConfig, password });
    },
    cancelJob(id) { return this._fetch("POST", `/api/job/${id}/cancel`); },
    getJobs() { return this._fetch("GET", "/api/jobs"); },
    getResults() { return this._fetch("GET", "/api/results"); },
    transferScan(instance, password, ramPercent) {
      return this._fetch("POST", "/api/transfer/scan", { instance, password, ram_percent: ramPercent });
    },
    transferTargetOrders(instance, password, cubes) {
      return this._fetch("POST", "/api/transfer/target-orders", { instance, password, cubes });
    },
    transferApply(instance, password, orders) {
      return this._fetch("POST", "/api/transfer/apply", { instance, password, orders });
    },
    transferExport(instance, orders) {
      return this._fetch("POST", "/api/transfer/export", { instance, orders });
    },
    optimizeDbPlan(instance, password, options) {
      return this._fetch("POST", "/api/optimize-db/plan", Object.assign({ instance, password }, options));
    },
    optimizeDbRun(instance, password, planId) {
      return this._fetch("POST", "/api/optimize-db/run", { instance, password, plan_id: planId });
    },
    optimizeDbRuns() { return this._fetch("POST", "/api/optimize-db/runs", {}); },
    optimizeDbRunState(planId) { return this._fetch("GET", `/api/optimize-db/run/${encodeURIComponent(planId)}`); },
    optimizeDbRestoreChores(instance, password, planId) {
      return this._fetch("POST", "/api/optimize-db/restore-chores", { instance, password, plan_id: planId });
    },
  };

  // ==================================================================
  // Credentials — the password typed for each instance this session
  // ==================================================================
  // The server never sends a stored password to the page, so a password is only
  // ever what the user typed. A remembered null means "use config.ini". An entry
  // is kept only once a connection with it has succeeded.
  const Credentials = {
    _typed: new Map(),

    get(instance) {
      return this._typed.has(instance) ? this._typed.get(instance) : null;
    },

    clear() {
      this._typed.clear();
    },

    ensure(instance) {
      if (this._typed.has(instance)) return Promise.resolve(true);
      return new Promise(resolve => {
        const body = el("div");
        body.appendChild(el("p", { className: "text-sm text-secondary mb-4" },
          `Connect to "${instance}". Enter the password if it is not stored in config.ini.`));
        const group = el("div", { className: "form-group" });
        group.appendChild(el("label", { className: "form-label" }, "Password (optional)"));
        const input = el("input", { type: "password", className: "form-input", placeholder: "Leave blank to use config.ini" });
        group.appendChild(input);
        body.appendChild(group);

        const connectBtn = el("button", { className: "btn btn-primary" }, "Connect");
        const cancelBtn = el("button", { className: "btn btn-secondary", onClick: () => Modal.close() }, "Cancel");
        const submit = async () => {
          connectBtn.disabled = true;
          connectBtn.textContent = "Connecting...";
          const password = input.value || null;
          try {
            await Api.connect(instance, password);
            this._typed.set(instance, password);
            resolve(true);
            Modal.close();
          } catch (err) {
            Toast.error(err.message);
            connectBtn.disabled = false;
            connectBtn.textContent = "Connect";
          }
        };
        connectBtn.addEventListener("click", submit);
        input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); submit(); } });

        Modal.open({ title: "Connect to Instance", body, size: "sm", footer: [cancelBtn, connectBtn],
          onClose: () => resolve(false) });
        setTimeout(() => input.focus(), 100);
      });
    },
  };

  // ==================================================================
  // Toast
  // ==================================================================
  const Toast = {
    _container: null,
    _counter: 0,

    init() { this._container = $("#toast-container"); },

    show(message, type = "info", duration) {
      // Default durations: success/info fade fast, warnings a bit longer, errors stick
      if (duration === undefined) {
        duration = type === "error" ? 0 : type === "warning" ? 4000 : 2500;
      }
      const id = ++this._counter;
      const iconMap = { success: Icons.check, error: Icons.x, warning: Icons.alertTriangle, info: Icons.info };
      const closeBtn = el("button", { className: "toast-close", html: Icons.x });
      const t = el("div", { className: `toast ${type}`, dataset: { id: String(id) } },
        el("span", { className: "toast-icon", html: iconMap[type] || iconMap.info }),
        el("span", { className: "toast-body" }, message),
        closeBtn,
      );
      closeBtn.addEventListener("click", (e) => { e.stopPropagation(); this._remove(t); });
      // Clicking anywhere on an error toast also dismisses it
      if (type === "error") {
        t.style.cursor = "pointer";
        t.addEventListener("click", () => this._remove(t));
      }
      this._container.appendChild(t);
      if (duration > 0) setTimeout(() => this._remove(t), duration);
      return id;
    },

    _remove(t) {
      if (!t || !t.parentNode) return;
      t.classList.add("removing");
      t.addEventListener("animationend", () => t.remove());
      // Fallback in case animation doesn't fire
      setTimeout(() => { if (t.parentNode) t.remove(); }, 300);
    },

    dismiss(id) {
      const t = this._container.querySelector(`[data-id="${id}"]`);
      if (t) this._remove(t);
    },

    success(msg) { return this.show(msg, "success"); },
    error(msg) { return this.show(msg, "error"); },
    warning(msg) { return this.show(msg, "warning"); },
    info(msg) { return this.show(msg, "info"); },
  };

  // ==================================================================
  // Modal
  // ==================================================================
  const Modal = {
    _backdrop: null,
    _container: null,
    _previousFocus: null,

    init() {
      this._backdrop = $("#modal-backdrop");
      this._container = $("#modal-container");
      this._backdrop.addEventListener("click", () => this.close());
      document.addEventListener("keydown", e => {
        if (this._container.classList.contains("hidden")) return;
        if (e.key === "Escape") { this.close(); return; }
        // Focus trap: Tab / Shift+Tab within modal
        if (e.key === "Tab") {
          const focusable = this._container.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          );
          if (focusable.length === 0) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (e.shiftKey) {
            if (document.activeElement === first) { e.preventDefault(); last.focus(); }
          } else {
            if (document.activeElement === last) { e.preventDefault(); first.focus(); }
          }
        }
      });
    },

    open({ title, body, footer, size = "md", onClose = null }) {
      this._settle();
      this._onClose = onClose;
      this._previousFocus = document.activeElement;
      const titleId = "modal-title-id";
      const m = el("div", { className: `modal ${size}` },
        el("div", { className: "modal-header" },
          el("h2", { className: "modal-title", id: titleId }, title),
          el("button", { className: "modal-close", html: Icons.x, onClick: () => this.close() },
            el("span", { className: "sr-only" }, "Close")),
        ),
        el("div", { className: "modal-body" }, ...(typeof body === "string" ? [el("p", null, body)] : [body])),
      );
      if (footer) m.appendChild(el("div", { className: "modal-footer" }, ...footer));
      this._container.innerHTML = "";
      this._container.appendChild(m);
      this._container.setAttribute("aria-labelledby", titleId);
      this._backdrop.classList.remove("hidden");
      this._container.classList.remove("hidden");
      // Move focus into modal
      const firstFocusable = m.querySelector(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (firstFocusable) requestAnimationFrame(() => firstFocusable.focus());
    },

    confirm(message, onConfirm) {
      this.open({
        title: "Confirm",
        body: message,
        size: "sm",
        footer: [
          el("button", { className: "btn btn-secondary", onClick: () => this.close() }, "Cancel"),
          el("button", { className: "btn btn-danger", onClick: () => { this.close(); onConfirm(); } }, "Confirm"),
        ],
      });
    },

    close() {
      this._backdrop.classList.add("hidden");
      this._container.classList.add("hidden");
      this._container.innerHTML = "";
      // Restore focus to trigger element
      if (this._previousFocus && typeof this._previousFocus.focus === "function") {
        this._previousFocus.focus();
        this._previousFocus = null;
      }
      this._settle();
    },

    // Tell whoever opened the current modal that it has gone — exactly once.
    _settle() {
      const onClose = this._onClose;
      this._onClose = null;
      if (onClose) onClose();
    },
  };

  // ==================================================================
  // Theme
  // ==================================================================
  const Theme = {
    init() {
      this.apply();
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (state.theme === "system") this.apply();
      });
    },
    set(theme) {
      state.theme = theme;
      localStorage.setItem("op-theme", theme);
      this.apply();
    },
    apply() {
      // Always resolve to explicit light/dark so CSS only needs [data-theme="dark"]
      const resolved = this.current();
      document.documentElement.setAttribute("data-theme", resolved);
    },
    current() {
      if (state.theme !== "system") return state.theme;
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    },
  };

  // ==================================================================
  // Table factory
  // ==================================================================
  function createTable({ columns, data, sortable = true, filterable = true, onRowClick, emptyMessage = "No data", emptyIcon }) {
    let _data = data || [];
    let _filtered = _data;
    let _sortCol = null;
    let _sortDir = "asc";
    let _filter = "";

    const wrapper = el("div", { className: "table-wrapper" });
    const table = el("table", { className: "data-table" });
    const thead = el("thead");
    const tbody = el("tbody");
    table.appendChild(thead);
    table.appendChild(tbody);

    let searchInput;
    if (filterable) {
      const toolbar = el("div", { className: "table-toolbar" });
      const searchWrap = el("div", { className: "table-search" });
      searchInput = el("input", { type: "text", placeholder: "Search..." });
      searchInput.addEventListener("input", () => { _filter = searchInput.value.toLowerCase(); applyFilter(); render(); });
      searchWrap.appendChild(searchInput);
      toolbar.appendChild(searchWrap);
      wrapper.appendChild(toolbar);
    }
    wrapper.appendChild(table);

    function applyFilter() {
      if (!_filter) { _filtered = _data; return; }
      _filtered = _data.filter(row =>
        columns.some(col => {
          const v = col.value ? col.value(row) : row[col.key];
          return v != null && String(v).toLowerCase().includes(_filter);
        })
      );
    }

    function renderHeader() {
      thead.innerHTML = "";
      const tr = el("tr");
      columns.forEach(col => {
        const th = el("th", null, col.label);
        if (col.align === "right") th.classList.add("align-right");
        if (sortable && col.sortable !== false) {
          th.classList.add("sortable");
          const arrow = el("span", { className: "sort-arrow" }, "▲");
          th.appendChild(arrow);
          if (_sortCol === col.key) {
            th.classList.add(_sortDir === "asc" ? "sort-asc" : "sort-desc");
            arrow.textContent = _sortDir === "asc" ? "▲" : "▼";
          }
          th.addEventListener("click", () => {
            if (_sortCol === col.key) _sortDir = _sortDir === "asc" ? "desc" : "asc";
            else { _sortCol = col.key; _sortDir = "asc"; }
            doSort();
            renderHeader();
            renderBody();
          });
        }
        tr.appendChild(th);
      });
      thead.appendChild(tr);
    }

    function doSort() {
      if (!_sortCol) return;
      const col = columns.find(c => c.key === _sortCol);
      // Sort by the underlying value: a column's value() is formatted for display
      // ("10,000", "1.2 GB", a locale date) and does not order correctly as text.
      const sortKey = row => col.sortValue ? col.sortValue(row)
        : (col.key in row ? row[col.key] : (col.value ? col.value(row) : undefined));
      _filtered.sort((a, b) => {
        let va = sortKey(a);
        let vb = sortKey(b);
        if (va == null) va = "";
        if (vb == null) vb = "";
        let cmp = typeof va === "number" ? va - vb : String(va).localeCompare(String(vb));
        return _sortDir === "desc" ? -cmp : cmp;
      });
    }

    function renderBody() {
      tbody.innerHTML = "";
      if (_filtered.length === 0) {
        const tr = el("tr");
        const td = el("td", { colspan: columns.length, className: "table-empty" });
        if (emptyIcon) td.appendChild(el("div", { className: "table-empty-icon", html: emptyIcon }));
        td.appendChild(document.createTextNode(emptyMessage));
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
      }
      _filtered.forEach((row, idx) => {
        const tr = el("tr");
        if (onRowClick) {
          tr.classList.add("clickable");
          tr.addEventListener("click", () => onRowClick(row, idx));
        }
        columns.forEach(col => {
          const td = el("td");
          if (col.align === "right") td.classList.add("align-right");
          if (col.render) {
            const content = col.render(row, idx);
            if (content instanceof HTMLElement) td.appendChild(content);
            else td.textContent = content != null ? String(content) : "";
          } else {
            const v = col.value ? col.value(row) : row[col.key];
            td.textContent = v != null ? v : "";
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    function render() { renderHeader(); renderBody(); }

    render();

    return {
      el: wrapper,
      update(newData) {
        _data = newData;
        applyFilter();
        doSort();
        render();
      },
      getData() { return _filtered; },
      destroy() { wrapper.remove(); },
    };
  }

  // ==================================================================
  // Terminal — the log view of a job stream
  // ==================================================================
  // Lines are coloured by the record's level, appended in one batch per animation
  // frame, capped at TERMINAL_MAX_LINES (oldest dropped first), and scrolled to
  // the bottom only while the reader is already there.
  const TERMINAL_MAX_LINES = 2000;
  const LOG_LEVEL_CLASSES = { ERROR: "log-error", CRITICAL: "log-error", WARNING: "log-warning" };

  function createTerminal() {
    const view = el("div", { className: "terminal" });
    let pending = [];
    let scheduled = false;

    function line(log) {
      const text = log && log.message != null ? String(log.message) : String(log);
      const cls = LOG_LEVEL_CLASSES[log && log.level];
      return el("div", { className: "terminal-line" }, cls ? el("span", { className: cls }, text) : text);
    }

    function flush() {
      scheduled = false;
      const pinned = view.scrollHeight - view.scrollTop - view.clientHeight < 24;
      const batch = document.createDocumentFragment();
      pending.forEach(log => batch.appendChild(line(log)));
      pending = [];
      view.appendChild(batch);
      while (view.childElementCount > TERMINAL_MAX_LINES) view.firstElementChild.remove();
      if (pinned) view.scrollTop = view.scrollHeight;
    }

    return {
      el: view,
      append(log) {
        pending.push(log);
        if (pending.length > TERMINAL_MAX_LINES) pending.splice(0, pending.length - TERMINAL_MAX_LINES);
        if (!scheduled) { scheduled = true; requestAnimationFrame(flush); }
      },
    };
  }

  // ==================================================================
  // DimensionConfigurator factory
  // ==================================================================
  function createDimensionConfigurator({ dimensions, metadata, mode, onChange }) {
    // dimensions: [name, ...] in storage order, metadata: { name: { leaf_elements, has_strings, ... } }
    const _origDims = dimensions.map((name, i) => ({ name, meta: metadata[name] || {} }));
    let _dims = _origDims.map((d, i) => ({ ...d, included: true, locked: false }));
    let _mode = mode;
    let _targetPosition = 1;                      // position mode: 1-based
    let _targetDimension = dimensions[0] || "";    // dimension mode: dim name
    let _ignoreOrders = [];                        // greedy mode: [[dim, dim, ...], ...]
    let _positionRules = [];                       // greedy mode: [{ dimension, position }, ...]
    let _predefinedOrders = [];                    // predefined mode: [[dim, dim, ...], ...]
    let _dragIdx = null;                           // predefined drag source

    const container = el("div", { className: "dim-configurator" });

    function fire() { if (onChange) onChange(getConfig()); }

    // ── Shared card builder ──
    function dimCard(dim, idx, opts = {}) {
      const { showToggle, showDrag, showLock, showMeta = true, highlight } = opts;
      const cls = ["dim-card"];
      if (!dim.included) cls.push("excluded");
      if (dim.locked) cls.push("locked");
      if (highlight) cls.push("highlight");
      const card = el("div", { className: cls.join(" ") });

      // Drag handle
      if (showDrag) {
        card.setAttribute("draggable", "true");
        card.appendChild(el("span", { className: "drag-handle", html: Icons.gripVertical }));
      }

      // Position label (auto from index)
      if (showDrag && dim.included) {
        card.appendChild(el("span", { className: "dim-card-pos-label" }, `${idx + 1}.`));
      }

      // Include/exclude toggle
      if (showToggle) {
        const toggle = el("label", { className: "toggle-switch dim-card-toggle" });
        const cb = el("input", { type: "checkbox" });
        cb.checked = dim.included;
        cb.addEventListener("change", () => { dim.included = cb.checked; dim.locked = false; fire(); render(); });
        toggle.appendChild(cb);
        toggle.appendChild(el("span", { className: "toggle-slider" }));
        card.appendChild(toggle);
      }

      // Lock toggle
      if (showLock) {
        const lockBtn = el("span", {
          className: `dim-card-lock${dim.locked ? " locked" : ""}`,
          role: "button",
          tabindex: "0",
          "aria-label": dim.locked ? "Unlock dimension" : "Lock dimension in place",
          "aria-pressed": dim.locked ? "true" : "false",
          html: dim.locked ? Icons.lock : Icons.unlock,
          title: dim.locked ? "Locked — will not be moved" : "Click to lock in place",
        });
        lockBtn.addEventListener("click", () => { dim.locked = !dim.locked; fire(); render(); });
        card.appendChild(lockBtn);
      }

      // Name
      card.appendChild(el("span", { className: "dim-card-name" }, dim.name));

      // Meta badges
      if (showMeta) {
        const metaWrap = el("span", { className: "dim-card-meta" });
        if (dim.meta.leaf_elements != null) {
          metaWrap.appendChild(el("span", { className: "badge" }, `${dim.meta.leaf_elements.toLocaleString()} elem`));
        }
        if (dim.meta.has_strings) {
          metaWrap.appendChild(el("span", { className: "dim-card-warning", html: Icons.alertTriangle + " Strings" }));
        }
        card.appendChild(metaWrap);
      }

      return card;
    }

    // ── Modal: build an order to ignore (greedy mode) ──
    function _showIgnoreOrderModal() {
      const modalDims = _dims.filter(d => d.included).map(d => d.name);
      let dragIdx = null;

      const body = el("div");
      body.appendChild(el("p", { className: "text-xs text-tertiary mb-3" },
        "Drag dimensions to build the order you want the greedy algorithm to skip."));

      const list = el("div", { className: "dim-card-list" });
      body.appendChild(list);

      function renderModalList() {
        list.innerHTML = "";
        modalDims.forEach((name, i) => {
          const card = el("div", { className: "dim-card" });
          card.setAttribute("draggable", "true");
          card.appendChild(el("span", { className: "drag-handle", html: Icons.gripVertical }));
          card.appendChild(el("span", { className: "dim-card-pos-label" }, `${i + 1}.`));
          card.appendChild(el("span", { className: "dim-card-name" }, name));

          card.addEventListener("dragstart", e => {
            dragIdx = i;
            card.classList.add("dragging");
            e.dataTransfer.effectAllowed = "move";
          });
          card.addEventListener("dragend", () => {
            dragIdx = null;
            card.classList.remove("dragging");
            list.querySelectorAll(".drag-indicator").forEach(x => x.remove());
          });
          card.addEventListener("dragover", e => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            list.querySelectorAll(".drag-indicator").forEach(x => x.remove());
            const rect = card.getBoundingClientRect();
            const mid = rect.top + rect.height / 2;
            const ind = el("div", { className: "drag-indicator" });
            if (e.clientY < mid) card.before(ind); else card.after(ind);
          });
          card.addEventListener("drop", e => {
            e.preventDefault();
            list.querySelectorAll(".drag-indicator").forEach(x => x.remove());
            if (dragIdx == null) return;
            const rect = card.getBoundingClientRect();
            let ti = e.clientY < rect.top + rect.height / 2 ? i : i + 1;
            if (dragIdx < ti) ti--;
            if (dragIdx !== ti) {
              const [m] = modalDims.splice(dragIdx, 1);
              modalDims.splice(ti, 0, m);
              renderModalList();
            }
          });
          list.appendChild(card);
        });
      }

      renderModalList();

      Modal.open({
        title: "Build Order to Ignore",
        body,
        footer: [
          el("button", { className: "btn btn-ghost", onClick: () => Modal.close() }, "Cancel"),
          el("button", { className: "btn btn-primary", onClick: () => {
            _ignoreOrders.push([...modalDims]);
            fire();
            render();
            Modal.close();
          }}, "Add to Ignore List"),
        ],
        size: "md",
      });
    }

    // ── Modal: build a predefined order ──
    function _showPredefinedOrderModal() {
      const modalDims = _dims.filter(d => d.included).map(d => ({ name: d.name, meta: d.meta }));
      let dragIdx = null;

      const body = el("div");
      body.appendChild(el("p", { className: "text-xs text-tertiary mb-3" },
        "Drag dimensions to build the order you want to benchmark."));

      const list = el("div", { className: "dim-card-list" });
      body.appendChild(list);

      function renderModalList() {
        list.innerHTML = "";
        modalDims.forEach((dim, i) => {
          const card = el("div", { className: "dim-card" });
          card.setAttribute("draggable", "true");
          card.appendChild(el("span", { className: "drag-handle", html: Icons.gripVertical }));
          card.appendChild(el("span", { className: "dim-card-pos-label" }, `${i + 1}.`));
          card.appendChild(el("span", { className: "dim-card-name" }, dim.name));
          const leafCount = dim.meta.leaf_elements;
          if (leafCount != null) {
            card.appendChild(el("span", { className: "dim-card-elements text-tertiary", style: "margin-left:auto;font-size:11px;" },
              `${leafCount.toLocaleString()} elements`));
          }

          card.addEventListener("dragstart", e => {
            dragIdx = i;
            card.classList.add("dragging");
            e.dataTransfer.effectAllowed = "move";
          });
          card.addEventListener("dragend", () => {
            dragIdx = null;
            card.classList.remove("dragging");
            list.querySelectorAll(".drag-indicator").forEach(x => x.remove());
          });
          card.addEventListener("dragover", e => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            list.querySelectorAll(".drag-indicator").forEach(x => x.remove());
            const rect = card.getBoundingClientRect();
            const mid = rect.top + rect.height / 2;
            const ind = el("div", { className: "drag-indicator" });
            if (e.clientY < mid) card.before(ind); else card.after(ind);
          });
          card.addEventListener("drop", e => {
            e.preventDefault();
            list.querySelectorAll(".drag-indicator").forEach(x => x.remove());
            if (dragIdx == null) return;
            const rect = card.getBoundingClientRect();
            let ti = e.clientY < rect.top + rect.height / 2 ? i : i + 1;
            if (dragIdx < ti) ti--;
            if (dragIdx !== ti) {
              const [m] = modalDims.splice(dragIdx, 1);
              modalDims.splice(ti, 0, m);
              renderModalList();
            }
          });
          list.appendChild(card);
        });
      }

      renderModalList();

      Modal.open({
        title: "Build Predefined Order",
        body,
        footer: [
          el("button", { className: "btn btn-ghost", onClick: () => Modal.close() }, "Cancel"),
          el("button", { className: "btn btn-primary", onClick: () => {
            _predefinedOrders.push(modalDims.map(d => d.name));
            fire();
            render();
            Modal.close();
          }}, "Add Order"),
        ],
        size: "md",
      });
    }

    // ── Modal: add a dimension position rule ──
    function _showPositionRuleModal() {
      const includedDims = _dims.filter(d => d.included).map(d => d.name);
      const body = el("div");

      body.appendChild(el("label", { className: "form-label mb-1" }, "Dimension"));
      const dimSelect = el("select", { className: "form-input mb-3" });
      includedDims.forEach(name => {
        dimSelect.appendChild(el("option", { value: name }, name));
      });
      body.appendChild(dimSelect);

      body.appendChild(el("label", { className: "form-label mb-1" }, "Never in Position"));
      const posSelect = el("select", { className: "form-input mb-3" });
      posSelect.appendChild(el("option", { value: "first" }, "First"));
      for (let i = 2; i < includedDims.length; i++) {
        posSelect.appendChild(el("option", { value: String(i) }, `Position ${i}`));
      }
      posSelect.appendChild(el("option", { value: "last" }, "Last"));
      body.appendChild(posSelect);

      Modal.open({
        title: "Add Dimension Position Rule",
        body,
        footer: [
          el("button", { className: "btn btn-ghost", onClick: () => Modal.close() }, "Cancel"),
          el("button", { className: "btn btn-primary", onClick: () => {
            const dim = dimSelect.value;
            const pos = posSelect.value;
            const exists = _positionRules.some(r => r.dimension === dim && r.position === pos);
            if (!exists) {
              _positionRules.push({ dimension: dim, position: pos });
              fire();
              render();
            }
            Modal.close();
          }}, "Add Rule"),
        ],
        size: "sm",
      });
    }

    // ── GREEDY render ──
    function renderGreedy() {
      // Dim toggles
      const list = el("div", { className: "dim-card-list" });
      _dims.forEach((dim, i) => list.appendChild(dimCard(dim, i, { showToggle: true })));
      container.appendChild(list);

      // Dimension position rules section
      container.appendChild(el("div", { className: "section-divider mt-4" }, "Dimension Position Rules (optional)"));
      container.appendChild(el("div", { className: "form-hint mb-2" }, "Prevent specific dimensions from being placed in certain positions"));

      const rulesList = el("div");
      _positionRules.forEach((rule, ri) => {
        const row = el("div", { className: "selection-row" });
        const label = rule.position === "first" ? "Never First"
                    : rule.position === "last" ? "Never Last"
                    : `Never Position ${rule.position}`;
        const nameSpan = el("span", { className: "selection-row-name" });
        nameSpan.appendChild(el("span", { className: "badge" }, rule.dimension));
        nameSpan.appendChild(document.createTextNode(` \u2014 ${label}`));
        row.appendChild(nameSpan);
        const removeBtn = el("span", { className: "selection-row-remove", role: "button", tabindex: "0", "aria-label": "Remove", html: Icons.x, title: "Remove" });
        removeBtn.addEventListener("click", () => { _positionRules.splice(ri, 1); fire(); render(); });
        row.appendChild(removeBtn);
        rulesList.appendChild(row);
      });
      if (_positionRules.length === 0) {
        rulesList.appendChild(el("div", { className: "text-xs text-tertiary" }, "No position rules defined"));
      }
      container.appendChild(rulesList);

      const addRuleBtn = el("button", { className: "btn btn-ghost btn-sm mt-2" },
        el("span", { html: Icons.plus }), "Add Rule");
      addRuleBtn.addEventListener("click", () => _showPositionRuleModal());
      container.appendChild(addRuleBtn);

      // Orders to ignore section
      container.appendChild(el("div", { className: "section-divider mt-4" }, "Orders to Ignore (optional)"));
      container.appendChild(el("div", { className: "form-hint mb-2" }, "Full dimension orders the greedy algorithm will skip"));

      const ignoreList = el("div");
      _ignoreOrders.forEach((order, oi) => {
        const row = el("div", { className: "selection-row", style: "flex-wrap:wrap" });
        const badges = el("span", { className: "selection-row-name", style: "display:flex;gap:4px;flex-wrap:wrap" });
        order.forEach((name, pi) => {
          badges.appendChild(el("span", { className: "badge" }, `${pi + 1}. ${name}`));
        });
        row.appendChild(badges);
        const removeBtn = el("span", { className: "selection-row-remove", role: "button", tabindex: "0", "aria-label": "Remove", html: Icons.x, title: "Remove" });
        removeBtn.addEventListener("click", () => { _ignoreOrders.splice(oi, 1); fire(); render(); });
        row.appendChild(removeBtn);
        ignoreList.appendChild(row);
      });
      if (_ignoreOrders.length === 0) {
        ignoreList.appendChild(el("div", { className: "text-xs text-tertiary" }, "No orders to ignore"));
      }
      container.appendChild(ignoreList);

      const addBtn = el("button", { className: "btn btn-ghost btn-sm mt-2" },
        el("span", { html: Icons.plus }), "Add Order to Ignore");
      addBtn.addEventListener("click", () => _showIgnoreOrderModal());
      container.appendChild(addBtn);
    }

    // ── PREDEFINED render (multi-order list builder) ──
    function renderPredefined() {
      container.appendChild(el("div", { className: "section-divider" }, "Predefined Orders"));
      container.appendChild(el("div", { className: "form-hint mb-2" }, "Dimension orders to benchmark against each other"));

      const orderList = el("div");
      _predefinedOrders.forEach((order, oi) => {
        const row = el("div", { className: "selection-row", style: "flex-wrap:wrap" });
        const badges = el("span", { className: "selection-row-name", style: "display:flex;gap:4px;flex-wrap:wrap" });
        order.forEach((name, pi) => {
          badges.appendChild(el("span", { className: "badge" }, `${pi + 1}. ${name}`));
        });
        row.appendChild(badges);
        const removeBtn = el("span", { className: "selection-row-remove", role: "button", tabindex: "0", "aria-label": "Remove", html: Icons.x, title: "Remove" });
        removeBtn.addEventListener("click", () => { _predefinedOrders.splice(oi, 1); fire(); render(); });
        row.appendChild(removeBtn);
        orderList.appendChild(row);
      });
      if (_predefinedOrders.length === 0) {
        orderList.appendChild(el("div", { className: "text-xs text-tertiary" }, "No orders defined"));
      }
      container.appendChild(orderList);

      const btnRow = el("div", { style: "display:flex;gap:8px;flex-wrap:wrap" });
      const addBtn = el("button", { className: "btn btn-ghost btn-sm mt-2" },
        el("span", { html: Icons.plus }), "Add Custom Order");
      addBtn.addEventListener("click", () => _showPredefinedOrderModal());
      btnRow.appendChild(addBtn);
      container.appendChild(btnRow);
    }

    // ── POSITION render ──
    function renderPosition() {
      // Target position selector
      container.appendChild(el("div", { className: "form-label mb-2" }, "Target Position"));
      container.appendChild(el("div", { className: "form-hint mb-2" }, "Select the position to optimize — OptimusPy will try each unlocked dimension in this position"));
      const chips = el("div", { className: "position-chips" });
      const positions = [
        { value: "first", label: "First" },
        ...dimensions.map((_, i) => ({ value: i + 1, label: `${i + 1}` })),
        { value: "last", label: "Last" },
      ];
      positions.forEach(p => {
        const chip = el("button", {
          className: `position-chip${_targetPosition === p.value ? " active" : ""}`,
        }, p.label);
        chip.addEventListener("click", () => { _targetPosition = p.value; fire(); render(); });
        chips.appendChild(chip);
      });
      container.appendChild(chips);

      // Dimension list with lock toggles
      container.appendChild(el("div", { className: "form-label mb-2" }, "Dimensions"));
      container.appendChild(el("div", { className: "form-hint mb-2" }, "Lock dimensions to keep them fixed in their current position"));
      const list = el("div", { className: "dim-card-list" });
      const resolvedPos = _targetPosition === "first" ? 0 : _targetPosition === "last" ? _dims.length - 1 : _targetPosition - 1;
      _dims.forEach((dim, i) => {
        const isTarget = i === resolvedPos;
        const card = dimCard(dim, i, { showLock: !isTarget, showMeta: true, highlight: isTarget });
        // Show position label
        const posLabel = el("span", { className: "dim-card-pos-label" }, `${i + 1}.`);
        card.insertBefore(posLabel, card.firstChild);
        if (isTarget) {
          card.appendChild(el("span", { className: "badge badge-info", style: "margin-left:auto" }, "target"));
        }
        list.appendChild(card);
      });
      container.appendChild(list);
    }

    // ── DIMENSION render ──
    function renderDimension() {
      // Target dimension selector
      container.appendChild(el("div", { className: "form-label mb-2" }, "Target Dimension"));
      container.appendChild(el("div", { className: "form-hint mb-2" }, "Select the dimension to pivot — OptimusPy will try it in every possible position"));
      const sel = el("select", { className: "form-input mb-4" });
      dimensions.forEach(name => {
        const opt = el("option", { value: name }, name);
        if (name === _targetDimension) opt.selected = true;
        sel.appendChild(opt);
      });
      sel.addEventListener("change", () => { _targetDimension = sel.value; fire(); render(); });
      container.appendChild(sel);

      // Dimension list with lock toggles
      container.appendChild(el("div", { className: "form-label mb-2" }, "Current Order"));
      container.appendChild(el("div", { className: "form-hint mb-2" }, "Lock dimensions to keep them fixed while the target dimension moves"));
      const list = el("div", { className: "dim-card-list" });
      _dims.forEach((dim, i) => {
        const isTarget = dim.name === _targetDimension;
        const card = dimCard(dim, i, { showLock: !isTarget, showMeta: true, highlight: isTarget });
        const posLabel = el("span", { className: "dim-card-pos-label" }, `${i + 1}.`);
        card.insertBefore(posLabel, card.firstChild);
        if (isTarget) {
          card.appendChild(el("span", { className: "badge badge-info", style: "margin-left:auto" }, "target"));
        }
        list.appendChild(card);
      });
      container.appendChild(list);
    }

    function render() {
      container.innerHTML = "";
      switch (_mode) {
        case "greedy": renderGreedy(); break;
        case "predefined": renderPredefined(); break;
        case "position": renderPosition(); break;
        case "dimension": renderDimension(); break;
      }
    }

    function getConfig() {
      const included = _dims.filter(d => d.included).map(d => d.name);
      const excluded = _dims.filter(d => !d.included).map(d => d.name);
      const locked = _dims.filter(d => d.locked).map(d => d.name);

      switch (_mode) {
        case "greedy":
          return {
            included, excluded,
            ignoreOrders: _ignoreOrders.length > 0 ? [..._ignoreOrders] : [],
            positionRules: _positionRules.length > 0 ? [..._positionRules] : [],
          };
        case "predefined":
          return { included, excluded, predefinedOrders: [..._predefinedOrders] };
        case "position":
          return { targetPosition: _targetPosition, excluded: locked };
        case "dimension":
          return { targetDimension: _targetDimension, excluded: locked };
        default:
          return { included, excluded };
      }
    }

    render();

    return {
      el: container,
      getConfig,
      setMode(m) { _mode = m; render(); fire(); },
      applySuggested(suggestedOrder) {
        if (!Array.isArray(suggestedOrder) || suggestedOrder.length === 0) return;
        if (_mode === "predefined") {
          // Add as a new predefined order (dedup by JSON comparison)
          const orderStr = JSON.stringify(suggestedOrder);
          const exists = _predefinedOrders.some(o => JSON.stringify(o) === orderStr);
          if (!exists) _predefinedOrders.push([...suggestedOrder]);
          fire();
          render();
        } else {
          // Reorder _dims to match suggested order
          const orderMap = {};
          suggestedOrder.forEach((name, i) => { orderMap[name] = i; });
          _dims.sort((a, b) => {
            const ai = orderMap[a.name] != null ? orderMap[a.name] : 999;
            const bi = orderMap[b.name] != null ? orderMap[b.name] : 999;
            return ai - bi;
          });
          _dims.forEach(d => { d.included = true; });
          fire();
          render();
        }
      },
      reset() {
        _dims = _origDims.map(d => ({ ...d, included: true, locked: false }));
        _targetPosition = 1;
        _targetDimension = dimensions[0] || "";
        _ignoreOrders = [];
        _positionRules = [];
        _predefinedOrders = [];
        fire();
        render();
      },
      destroy() { container.remove(); },
    };
  }

  // ==================================================================
  // StreamManager — holds EventSource connections across navigations
  // ==================================================================
  const StreamManager = {
    _streams: {},   // jobId → { es, logs, lastId, status, subscribers }

    _entry(jobId) {
      if (!this._streams[jobId]) {
        this._streams[jobId] = { es: null, logs: [], lastId: 0, status: "unknown", subscribers: [] };
      }
      return this._streams[jobId];
    },

    connect(jobId) {
      const entry = this._entry(jobId);
      if (entry.es) return;
      if (entry.status === "unknown") entry.status = "running";
      // Continue after the last event already received, so reopening a stream
      // neither repeats nor loses lines. EventSource resumes the same way when it
      // reconnects by itself.
      const es = new EventSource(`/api/job/${jobId}/stream?after=${entry.lastId}`);
      entry.es = es;
      const notify = (event, data) => entry.subscribers.forEach(cb => cb(event, data));
      const on = (event, handle) => es.addEventListener(event, e => {
        entry.lastId = Number(e.lastEventId) || entry.lastId;
        handle(JSON.parse(e.data));
      });
      on("log", data => {
        entry.logs.push(data);
        if (entry.logs.length > TERMINAL_MAX_LINES) entry.logs.shift();
        notify("log", data);
      });
      on("progress", data => notify("progress", data));
      ["complete", "error_event", "cancelled"].forEach(event => on(event, data => {
        entry.status = event === "complete" ? (data.status || "completed")
          : event === "cancelled" ? "cancelled" : "failed";
        es.close();
        entry.es = null;
        notify(event, data);
      }));
      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) entry.es = null;
      };
    },

    subscribe(jobId, callback) {
      const entry = this._entry(jobId);
      entry.subscribers.push(callback);
      return () => { entry.subscribers = entry.subscribers.filter(cb => cb !== callback); };
    },

    getLogs(jobId) {
      return this._streams[jobId]?.logs || [];
    },

    getStatus(jobId) {
      return this._streams[jobId]?.status || "unknown";
    },
  };

  // ==================================================================
  // Sidebar
  // ==================================================================
  const Sidebar = {
    init() {
      const sidebar = $("#sidebar");
      const collapseBtn = $("#sidebarCollapseBtn");
      if (state.sidebarCollapsed) sidebar.classList.add("collapsed");

      collapseBtn.addEventListener("click", () => {
        sidebar.classList.toggle("collapsed");
        state.sidebarCollapsed = sidebar.classList.contains("collapsed");
        localStorage.setItem("op-sidebar", state.sidebarCollapsed ? "collapsed" : "expanded");
        collapseBtn.setAttribute("aria-expanded", String(!state.sidebarCollapsed));
        collapseBtn.setAttribute("aria-label", state.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar");
      });
      // Sync initial aria-expanded state
      if (state.sidebarCollapsed) {
        collapseBtn.setAttribute("aria-expanded", "false");
        collapseBtn.setAttribute("aria-label", "Expand sidebar");
      }

      // Mobile menu button & overlay
      const mobileMenuBtn = $("#mobileMenuBtn");
      const sidebarOverlay = $("#sidebarOverlay");
      const _closeMobileSidebar = () => {
        sidebar.classList.remove("mobile-open");
        sidebarOverlay.classList.remove("visible");
        mobileMenuBtn.setAttribute("aria-expanded", "false");
      };
      const _openMobileSidebar = () => {
        sidebar.classList.add("mobile-open");
        sidebarOverlay.classList.add("visible");
        mobileMenuBtn.setAttribute("aria-expanded", "true");
      };
      if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener("click", () => {
          if (sidebar.classList.contains("mobile-open")) _closeMobileSidebar();
          else _openMobileSidebar();
        });
      }
      if (sidebarOverlay) {
        sidebarOverlay.addEventListener("click", _closeMobileSidebar);
      }
      // Close mobile sidebar on nav link click
      $$(".nav-item, .nav-sub-item").forEach(link => {
        link.addEventListener("click", () => {
          if (window.innerWidth < 768) _closeMobileSidebar();
        });
      });

      // Instance switcher
      const switcherBtn = $("#instanceSwitcherBtn");
      const dropdown = $("#instanceDropdown");
      const _toggleDropdown = (show) => {
        const isHidden = typeof show === "boolean" ? !show : !dropdown.classList.contains("hidden");
        dropdown.classList.toggle("hidden", isHidden);
        switcherBtn.setAttribute("aria-expanded", String(!isHidden));
      };
      switcherBtn.addEventListener("click", () => {
        if (switcherBtn.disabled) return;
        _toggleDropdown();
      });
      document.addEventListener("keydown", e => {
        if (e.key === "Escape" && !dropdown.classList.contains("hidden")) _toggleDropdown(false);
      });
      document.addEventListener("click", e => {
        if (!e.target.closest("#instanceSwitcher")) _toggleDropdown(false);
      });
    },

    async loadInstances() {
      try {
        const data = await Api.getInstances();
        state.instances = data.instances || [];
        state.config = data;
        this.renderInstanceSwitcher();
      } catch (err) {
        Toast.error("Failed to load instances: " + err.message);
      }
    },

    renderInstanceSwitcher() {
      const btn = $("#instanceSwitcherBtn");
      const dropdown = $("#instanceDropdown");
      btn.disabled = state.instances.length === 0;
      const nameEl = btn.querySelector(".instance-name");
      nameEl.textContent = state.activeInstance || "Select instance";

      dropdown.innerHTML = "";
      state.instances.forEach(name => {
        const isActive = name === state.activeInstance && state.connected;
        const item = el("div", {
          className: `instance-dropdown-item${isActive ? " active connected" : ""}`,
          role: "option",
          "aria-selected": isActive ? "true" : "false",
          tabindex: "0",
          onClick: () => {
            dropdown.classList.add("hidden");
            btn.setAttribute("aria-expanded", "false");
            if (isActive) return;
            this._promptConnect(name);
          },
          onKeydown: (e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              item.click();
            }
          },
        },
          el("span", { className: "dot" }),
          el("span", null, name),
        );
        dropdown.appendChild(item);
      });
    },

    async _promptConnect(instanceName) {
      if (!(await Credentials.ensure(instanceName))) return;
      try {
        const resp = await Api.connect(instanceName, Credentials.get(instanceName));
        state.activeInstance = instanceName;
        state.connected = true;
        state.serverName = resp.server_name;
        // Reset cached data from previous instance, restore scan cache if available
        state.cubeMetadata = {};
        state.cubeViews = {};
        state.processes = [];
        const cached = ScanCache.load(instanceName);
        if (cached) {
          state.scanData = cached.data;
          state.scanTimestamp = cached.ts;
        } else {
          state.scanData = null;
          state.scanTimestamp = null;
        }
        this.renderInstanceSwitcher();
        Sidebar.loadSavedCubes();
        Sidebar.updateActivityMonitor();
        Toast.success(`Connected to ${resp.server_name}`);
        Router.navigate("#/nav");
      } catch (err) {
        Toast.error(err.message);
      }
    },

    async loadSavedCubes() {
      try {
        const data = await Api.getSavedCubes();
        state.savedCubes = data.saved_cubes || [];
        this.renderScannedCubes();
      } catch {
        // Non-critical
      }
    },

    renderScannedCubes() {
      // Cube list now lives in the NavPage left panel — clear sidebar sub-items
      const nav = $("#savedCubesNav");
      if (nav) nav.innerHTML = "";
    },

    async updateActivityMonitor() {
      const container = $("#sidebarActivity");
      try {
        const data = await Api.getJobs();
        const jobs = data.jobs || [];
        const running = jobs.find(j => j.status === "running");
        if (running) {
          container.innerHTML = "";
          container.appendChild(el("div", { className: "activity-bar" },
            el("div", { className: "activity-pulse" }),
            el("div", { className: "activity-label" },
              el("div", { className: "activity-title" }, jobTitle(running)),
              el("div", { className: "activity-subtitle" }, running.label),
            ),
            el("div", { className: "activity-spinner" }),
          ));
          container.classList.remove("hidden");
          container.onclick = () => Router.navigate(jobLink(running));
        } else {
          container.classList.add("hidden");
          container.innerHTML = "";
          container.onclick = null;
        }
      } catch {
        // Non-critical
      }
    },
  };

  // ==================================================================
  // Router — hash-based
  // ==================================================================
  const Router = {
    _pages: {},
    _current: null,

    register(name, module) {
      this._pages[name] = module;
    },

    init() {
      window.addEventListener("hashchange", () => {
        // Close mobile sidebar on navigation
        if (window.innerWidth < 768) {
          const sidebar = $("#sidebar");
          const overlay = $("#sidebarOverlay");
          const menuBtn = $("#mobileMenuBtn");
          if (sidebar) sidebar.classList.remove("mobile-open");
          if (overlay) overlay.classList.remove("visible");
          if (menuBtn) menuBtn.setAttribute("aria-expanded", "false");
        }
        this._resolve();
      });
      this._resolve();
    },

    navigate(hash) {
      window.location.hash = hash;
    },

    _resolve() {
      const hash = window.location.hash || "#/home";
      const [path, queryStr] = hash.slice(1).split("?");
      const query = {};
      if (queryStr) {
        queryStr.split("&").forEach(p => {
          const [k, v] = p.split("=");
          query[decodeURIComponent(k)] = decodeURIComponent(v || "");
        });
      }

      const segments = path.split("/").filter(Boolean);
      let pageName, params = {};

      // Route: #/cube/CubeName?tab=x → redirect to #/nav?cube=CubeName&tab=x
      if (segments[0] === "cube" && segments[1]) {
        const cubeName = decodeURIComponent(segments[1]);
        const tabParam = query.tab ? `&tab=${query.tab}` : "";
        window.location.hash = `#/nav?cube=${encodeURIComponent(cubeName)}${tabParam}`;
        return;
      }

      // Route: #/nav?cube=X&tab=Y
      if (segments[0] === "nav") {
        pageName = "nav";
        if (query.cube) params.cubeName = query.cube;
      } else {
        pageName = segments[0] || "home";
      }

      // Unmount current (skip if staying on same page module)
      const stayingSamePage = this._current === pageName;
      if (this._current && this._pages[this._current] && !stayingSamePage) {
        const mod = this._pages[this._current];
        if (mod.unmount) mod.unmount();
      }

      // Show/hide pages
      $$(".page").forEach(p => p.classList.remove("active"));
      const pageEl = $(`#page-${pageName}`);
      if (pageEl) pageEl.classList.add("active");

      // Update nav active state
      $$(".nav-item").forEach(a => {
        const href = a.getAttribute("href");
        if (!href) return;
        const page = a.dataset.page;
        a.classList.toggle("active", page === pageName || pageName === "nav" && page === "home");
      });

      // Update title
      const titles = { home: "Optimize", nav: query.cube || "Navigation", results: "Results", jobs: "Jobs", settings: "Settings", transfer: "Sync Order", "optimize-db": "Optimize DB" };
      document.title = `OptimusPy — ${titles[pageName] || "Dashboard"}`;

      // Mount
      this._current = pageName;
      if (this._pages[pageName]) {
        this._pages[pageName].mount(params, query);
      }
    },
  };

  // ==================================================================
  // Page: Home
  // ==================================================================
  const HomePage = {
    _ramThreshold: 60,
    _includeOptimized: false,

    mount() {
      const page = $("#page-home");
      page.innerHTML = "";

      if (!state.connected) {
        this._renderDisconnected(page);
      } else {
        // Connected — redirect to the navigation split-panel view
        Router.navigate("#/nav");
      }
    },

    // ---- Not connected: instance tiles + collapsible help ----
    _renderDisconnected(page) {
      page.appendChild(el("div", { className: "page-header" },
        el("h1", { className: "page-title" }, "OptimusPy"),
        el("p", { className: "page-subtitle" }, "Connect to a TM1 instance to get started"),
      ));

      if (state.instances.length > 0) {
        const tilesGrid = el("div", { className: "instance-tiles" });
        state.instances.forEach(name => {
          const tile = el("button", {
            className: "instance-tile",
            onClick: () => Sidebar._promptConnect(name),
          },
            el("div", { className: "instance-tile-icon", html: '<svg aria-hidden="true" viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>' }),
            el("div", { className: "instance-tile-name" }, name),
            el("div", { className: "instance-tile-hint" }, "Click to connect"),
          );
          tilesGrid.appendChild(tile);
        });
        page.appendChild(tilesGrid);
      } else {
        page.appendChild(el("div", { className: "empty-state" },
          el("div", { className: "empty-state-icon", html: '<svg aria-hidden="true" viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>' }),
          el("div", { className: "empty-state-title" }, "No instances configured"),
          el("div", { className: "empty-state-text" }, "Add TM1 server connections to config.ini to get started."),
        ));
      }

      // Collapsible help section
      page.appendChild(this._buildCollapsibleHelp());
    },

    // ---- Help: show tips in a modal instead of inline ----
    _showHelpDrawer() {
      Modal.open({
        title: "Tips & Help",
        body: this._buildGuideContent(),
        size: "lg",
      });
    },

    // ---- Collapsible help (for not-connected page) ----
    _buildCollapsibleHelp() {
      const section = el("div", { className: "collapsible-help" });
      const toggle = el("button", { className: "collapsible-help-toggle" },
        el("span", null, "Tips & Getting Started"),
        el("span", { className: "collapsible-help-chevron", html: Icons.chevronRight }),
      );
      const content = el("div", { className: "collapsible-help-content hidden" });
      content.appendChild(this._buildGuideContent());
      toggle.addEventListener("click", () => {
        content.classList.toggle("hidden");
        const chevron = toggle.querySelector(".collapsible-help-chevron");
        chevron.style.transform = content.classList.contains("hidden") ? "" : "rotate(90deg)";
      });
      section.appendChild(toggle);
      section.appendChild(content);
      return section;
    },

    _buildGuideContent() {
      const wrap = el("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:24px" });

      // ---- How to Use OptimusPy ----
      const howTo = el("div", { className: "card" });
      howTo.appendChild(el("h2", { className: "card-title", style: "margin-bottom:12px" }, "How to Use OptimusPy"));

      const steps = [
        { n: "1", title: "Connect", desc: "Select a TM1 instance from the sidebar and enter your password if needed." },
        { n: "2", title: "Scan", desc: "The cube list on the left scans the instance and ranks cubes by RAM. Use the RAM threshold and Rescan to change what it shows." },
        { n: "3", title: "Configure", desc: "Select a cube, choose an optimization mode (Greedy, Predefined, Position, or Dimension), pick views to benchmark, and set the number of executions per permutation." },
        { n: "4", title: "Optimize", desc: "Start the optimization. OptimusPy will test dimension orderings, measuring RAM and query time for each. You can stop the process at any time." },
        { n: "5", title: "Review", desc: "Check the Results tab for CSV/HTML reports showing all tested permutations and the recommended order." },
      ];
      steps.forEach(s => {
        const row = el("div", { style: "display:flex;gap:10px;margin-bottom:10px" });
        row.appendChild(el("div", { style: "width:24px;height:24px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0" }, s.n));
        const text = el("div");
        text.appendChild(el("div", { style: "font-weight:600;font-size:13px;color:var(--text-primary)" }, s.title));
        text.appendChild(el("div", { style: "font-size:12px;color:var(--text-secondary);line-height:1.4" }, s.desc));
        row.appendChild(text);
        howTo.appendChild(row);
      });

      // Optimization modes
      howTo.appendChild(el("div", { style: "margin-top:14px;padding-top:14px;border-top:1px solid var(--border-secondary)" }));
      howTo.appendChild(el("div", { style: "font-weight:600;font-size:13px;color:var(--text-primary);margin-bottom:8px" }, "Optimization Modes"));
      const modes = [
        { badge: "Greedy", color: "var(--accent)", desc: "Cardinality-aware outside-in search: uses leaf-count tolerance (τ) to test only the orderings measurement must decide and pins clearly-placed dimensions. Toggle Fast mode for the seed-and-refine fold. Best general-purpose approach." },
        { badge: "Predefined", color: "var(--warning)", desc: "Benchmarks specific dimension orders you define. Use when you have candidate orders from manual analysis." },
        { badge: "Position", color: "var(--success)", desc: "Tests all dimensions for a single position (e.g., find the best last dimension). Quick, targeted optimization." },
        { badge: "Dimension", color: "var(--error)", desc: "Tests all positions for a single dimension. Useful when you know which dimension to focus on." },
      ];
      modes.forEach(m => {
        const row = el("div", { style: "display:flex;gap:8px;align-items:baseline;margin-bottom:6px" });
        row.appendChild(el("span", { style: `display:inline-block;padding:1px 8px;border-radius:4px;font-size:11px;font-weight:600;color:#fff;background:${m.color}` }, m.badge));
        row.appendChild(el("span", { style: "font-size:12px;color:var(--text-secondary);line-height:1.4" }, m.desc));
        howTo.appendChild(row);
      });

      wrap.appendChild(howTo);

      // ---- Dimension Ordering Tips ----
      const tips = el("div", { className: "card" });
      tips.appendChild(el("h2", { className: "card-title", style: "margin-bottom:12px" }, "Dimension Ordering Tips"));
      tips.appendChild(el("div", { style: "font-size:12px;color:var(--text-tertiary);margin-bottom:14px;line-height:1.4" },
        "Based on research from IBM documentation, the TM1 community, and the Horizon 2021 presentation by Hubert Heijkers, IBM Chief Architect of the TM1 Server."));

      const tipItems = [
        {
          icon: "&#x1F3AF;", title: "The 90/10 Rule",
          text: "~90% of memory optimization comes from correctly identifying the last dimension. The second-to-last accounts for ~9%. Getting the last dimension right is the single most impactful change."
        },
        {
          icon: "&#x2B06;", title: "Small-Sparse First, Large-Dense Last",
          text: "Order dimensions from smallest/sparsest at the top to largest/densest at the bottom. Dimensions higher in the storage order multiply the index structure below them \u2014 fewer branches at the top means less replication."
        },
        {
          icon: "&#x1F50D;", title: "Title Dimensions First for Query Speed",
          text: "Dimensions commonly used in view titles or MDX WHERE clauses (Version, Year, Currency) should be near the top. This lets TM1 prune the internal index early, drastically reducing traversal."
        },
        {
          icon: "&#x1F4BE;", title: "Partitioning Dimension First for Write Speed",
          text: "If TI loads data partitioned by a dimension (e.g., one file per Store), place that dimension first. All writes go to a single compact branch, minimizing lock contention."
        },
        {
          icon: "&#x26A0;", title: "Watch for String Dimensions",
          text: "TM1 requires the dimension with string elements to stay in the last position. This can prevent the optimal dimension from taking that spot. Best practice: separate string elements into a different cube."
        },
        {
          icon: "&#x1F4CA;", title: "Density Matters More Than Size",
          text: "A 10,000-element dimension at 2% density behaves very differently from one at 95%. Size alone isn\u2019t enough \u2014 always consider how much of the dimension is actually populated with data."
        },
        {
          icon: "&#x2696;", title: "RAM vs. Speed Is a Trade-Off",
          text: "The optimal order for memory, query speed, and write speed can differ for the same cube. Under 2 GB? Prioritize query speed. Hitting RAM limits? Prioritize memory. Use OptimusPy to find the best compromise."
        },
        {
          icon: "&#x1F504;", title: "Re-evaluate Periodically",
          text: "Data volumes and distribution patterns change over time. An order that was optimal last year may no longer be. Re-run the analysis after major data changes or growth."
        },
      ];
      tipItems.forEach(t => {
        const row = el("div", { style: "display:flex;gap:10px;margin-bottom:12px" });
        row.appendChild(el("div", { html: t.icon, style: "font-size:16px;flex-shrink:0;margin-top:1px" }));
        const text = el("div");
        text.appendChild(el("div", { style: "font-weight:600;font-size:13px;color:var(--text-primary)" }, t.title));
        text.appendChild(el("div", { style: "font-size:12px;color:var(--text-secondary);line-height:1.4" }, t.text));
        row.appendChild(text);
        tips.appendChild(row);
      });

      // Storage vs Presentation callout
      tips.appendChild(el("div", { style: "margin-top:10px;padding:12px;border-radius:var(--radius-md);background:var(--bg-tertiary);border:1px solid var(--border-secondary);font-size:12px;color:var(--text-secondary);line-height:1.5" },
        el("strong", { style: "color:var(--text-primary)" }, "Storage order \u2260 Presentation order. "),
        "The storage (internal) order controls how TM1 indexes data in memory. It can be changed at any time without affecting rules, processes, views, or reports. The presentation (build) order is set at cube creation and determines how dimensions appear in viewers and code \u2014 it cannot be changed. OptimusPy only modifies the storage order."
      ));

      wrap.appendChild(tips);
      return wrap;
    },

    unmount() {},
  };

  // ==================================================================
  // Page: Navigation (split-panel: cube list + workspace)
  // ==================================================================
  const NavPage = {
    _selectedCube: null,
    _panelHidden: false,
    _ramThreshold: 60,
    _includeOptimized: false,
    _searchQuery: "",

    mount(params, query) {
      if (!state.connected) {
        Router.navigate("#/home");
        return;
      }

      const cubeName = params.cubeName || query.cube || null;
      const tab = query.tab || null;

      // If same cube, just update workspace tab
      if (cubeName && cubeName === this._selectedCube && tab) {
        // Re-render workspace for tab switch
        this._renderWorkspace(tab);
        return;
      }

      this._selectedCube = cubeName;
      this._renderCubePanel();

      if (cubeName) {
        this._renderWorkspace(tab || "overview");
        this._highlightCube(cubeName);
      } else {
        this._renderEmptyWorkspace();
      }
    },

    // ---- Left panel: cube list ----
    _renderCubePanel() {
      const header = $("#cubePanelHeader");
      const body = $("#cubePanelBody");
      header.innerHTML = "";
      body.innerHTML = "";

      // Header: filter controls
      const filterWrap = el("div");
      // Search input (filters the already-scanned cube list client-side)
      const searchInput = el("input", {
        type: "search",
        placeholder: "Search cubes…",
        value: this._searchQuery,
        className: "form-input",
        style: "width:100%;margin-bottom:8px;font-size:12px;padding:4px 8px",
      });
      searchInput.addEventListener("input", () => {
        this._searchQuery = searchInput.value;
        const body = $("#cubePanelBody");
        if (body && state.scanData) {
          body.innerHTML = "";
          this._renderCubeList(body);
        }
      });
      filterWrap.appendChild(searchInput);
      // RAM slider
      const ramRow = el("div", { className: "flex items-center justify-between mb-2" });
      ramRow.appendChild(el("span", { className: "cube-filter-label" }, "RAM Threshold"));
      const ramValSpan = el("span", { className: "cube-filter-value" }, this._ramThreshold + "%");
      ramRow.appendChild(ramValSpan);
      filterWrap.appendChild(ramRow);
      const ramSlider = el("input", { type: "range", min: "0", max: "100", value: String(this._ramThreshold), style: "width:100%;margin-bottom:8px" });
      ramSlider.addEventListener("input", () => {
        this._ramThreshold = parseInt(ramSlider.value);
        ramValSpan.textContent = this._ramThreshold + "%";
      });
      // Don't auto-scan on slider change — user clicks Rescan when ready
      filterWrap.appendChild(ramSlider);
      // Include optimized + Rescan
      const bottomRow = el("div", { className: "flex items-center justify-between" });
      const optLabel = el("label", { className: "checkbox-label", style: "font-size:11px;gap:4px" });
      const optCb = el("input", { type: "checkbox" });
      optCb.checked = this._includeOptimized;
      optCb.addEventListener("change", () => { this._includeOptimized = optCb.checked; });
      optLabel.appendChild(optCb);
      optLabel.appendChild(document.createTextNode("Include optimized"));
      bottomRow.appendChild(optLabel);
      const rescanBtn = el("button", { className: "btn btn-ghost btn-sm", id: "nav-rescan-btn", onClick: () => this._doScan() },
        el("span", { html: Icons.refresh }));
      bottomRow.appendChild(rescanBtn);
      filterWrap.appendChild(bottomRow);
      // Scan age indicator
      const ageEl = el("div", { className: "text-xs text-tertiary", id: "scan-age", style: "margin-top:6px" });
      filterWrap.appendChild(ageEl);
      header.appendChild(filterWrap);

      // Body: cube list — use cached data if available, otherwise scan
      if (state.scanData) {
        this._renderCubeList(body);
        this._updateScanAge();
      } else {
        this._doScan();
      }
    },

    _updateScanAge() {
      const ageEl = $("#scan-age");
      if (!ageEl) return;
      if (state.scanTimestamp) {
        ageEl.textContent = `Scanned ${ScanCache.formatAge(state.scanTimestamp)}`;
      } else {
        ageEl.textContent = "";
      }
    },

    async _doScan() {
      const body = $("#cubePanelBody");
      const btn = $("#nav-rescan-btn");
      if (btn) btn.disabled = true;
      body.innerHTML = "";
      // Loading
      for (let i = 0; i < 6; i++) {
        body.appendChild(el("div", { className: "cube-card-skeleton", style: "height:52px;margin-bottom:4px" }));
      }
      try {
        const data = await Api.scan(state.activeInstance, Credentials.get(state.activeInstance), this._ramThreshold, this._includeOptimized);
        state.scanData = data;
        state.scanTimestamp = Date.now();
        ScanCache.save(state.activeInstance, data);
        Sidebar.renderScannedCubes();
        body.innerHTML = "";
        this._renderCubeList(body);
        this._updateScanAge();
      } catch (err) {
        body.innerHTML = "";
        body.appendChild(el("div", { className: "text-sm text-tertiary", style: "padding:12px" }, "Scan failed: " + err.message));
      } finally {
        if (btn) btn.disabled = false;
      }
    },

    _renderCubeList(container) {
      const allCubes = state.scanData?.candidates || [];
      if (allCubes.length === 0) {
        container.appendChild(el("div", { className: "text-sm text-tertiary", style: "padding:12px;text-align:center" }, "No cubes found"));
        return;
      }
      const query = (this._searchQuery || "").trim().toLowerCase();
      const cubes = query
        ? allCubes.filter(c => (c.cube_name || "").toLowerCase().includes(query))
        : allCubes;
      // Normalize bars against the full population so filtering doesn't rescale them.
      const maxRam = Math.max(...allCubes.map(c => c.ram_gb || 0), 0.01);
      // Summary
      const summaryText = query
        ? `${cubes.length} of ${allCubes.length} cube${allCubes.length !== 1 ? "s" : ""}`
        : `${allCubes.length} cube${allCubes.length !== 1 ? "s" : ""}`;
      container.appendChild(el("div", { className: "text-xs text-tertiary", style: "padding:0 4px 8px" }, summaryText));

      if (query && cubes.length === 0) {
        container.appendChild(el("div", { className: "text-sm text-tertiary", style: "padding:12px;text-align:center" },
          `No cubes match "${this._searchQuery}"`));
        return;
      }

      cubes.forEach(c => {
        const isActive = c.cube_name === this._selectedCube;
        const item = el("button", {
          className: `cube-list-item${isActive ? " active" : ""}`,
          dataset: { cube: c.cube_name },
          onClick: () => {
            this._selectedCube = c.cube_name;
            history.replaceState(null, "", `#/nav?cube=${encodeURIComponent(c.cube_name)}`);
            this._highlightCube(c.cube_name);
            this._renderWorkspace("overview");
          },
        });
        // Top: name + RAM
        const top = el("div", { className: "cube-list-item-top" });
        top.appendChild(el("span", { className: "cube-list-item-name" }, c.cube_name));
        top.appendChild(el("span", { className: "cube-list-item-ram" }, `${(c.ram_gb || 0).toFixed(2)} GB`));
        item.appendChild(top);
        // Bar
        const barWrap = el("div", { className: "cube-card-bar-wrap" });
        const pct = Math.max((c.ram_gb || 0) / maxRam * 100, 2);
        const barFill = el("div", { className: `cube-card-bar-fill ${pct > 66 ? "high" : pct > 33 ? "mid" : "low"}` });
        barFill.style.width = pct + "%";
        barWrap.appendChild(barFill);
        item.appendChild(barWrap);
        // Meta
        const meta = el("div", { className: "cube-list-item-meta" });
        meta.appendChild(el("span", null, `${c.dim_count || 0} dims`));
        meta.appendChild(el("span", null, `${(c.pct_of_total || 0).toFixed(1)}%`));
        if (c.already_optimized) meta.appendChild(el("span", { className: "badge badge-success", style: "font-size:9px;padding:0 4px" }, "opt"));
        if (c.last_dim_has_strings) meta.appendChild(el("span", { className: "badge badge-warning", style: "font-size:9px;padding:0 4px" }, "str"));
        item.appendChild(meta);
        container.appendChild(item);
      });
    },

    _highlightCube(cubeName) {
      const body = $("#cubePanelBody");
      if (!body) return;
      body.querySelectorAll(".cube-list-item").forEach(item => {
        item.classList.toggle("active", item.dataset.cube === cubeName);
      });
    },

    // ---- Right panel: workspace ----
    _renderEmptyWorkspace() {
      const panel = $("#workspacePanel");
      panel.innerHTML = "";
      panel.appendChild(el("div", { className: "empty-state", style: "padding-top:80px" },
        el("div", { className: "empty-state-icon", html: '<svg aria-hidden="true" viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>' }),
        el("div", { className: "empty-state-title" }, "Select a cube"),
        el("div", { className: "empty-state-text" }, "Choose a cube from the list to view details and start optimizing."),
      ));
    },

    _renderWorkspace(tab) {
      const panel = $("#workspacePanel");
      panel.innerHTML = "";
      panel.style.position = "relative";

      if (!this._selectedCube) {
        this._renderEmptyWorkspace();
        return;
      }

      // Toggle button to show/hide cube panel
      const cubePanel = $("#cubePanel");
      const toggleBtn = el("button", {
        className: "cube-panel-toggle",
        "aria-label": this._panelHidden ? "Show cube list" : "Hide cube list",
        onClick: () => {
          this._panelHidden = !this._panelHidden;
          cubePanel.classList.toggle("hidden-panel", this._panelHidden);
          toggleBtn.setAttribute("aria-label", this._panelHidden ? "Show cube list" : "Hide cube list");
          toggleBtn.innerHTML = this._panelHidden ? Icons.chevronRight : Icons.chevronLeft;
          // Show/hide breadcrumb
          const bc = panel.querySelector(".workspace-breadcrumb");
          if (bc) bc.style.display = this._panelHidden ? "flex" : "none";
        },
      });
      toggleBtn.innerHTML = this._panelHidden ? Icons.chevronRight : Icons.chevronLeft;
      panel.appendChild(toggleBtn);

      // Breadcrumb (shown when panel hidden)
      const breadcrumb = el("div", { className: "workspace-breadcrumb", style: this._panelHidden ? "" : "display:none" });
      breadcrumb.appendChild(el("button", { onClick: () => toggleBtn.click() },
        el("span", { html: Icons.chevronRight }), "Show cubes"));
      breadcrumb.appendChild(el("span", null, " / "));
      breadcrumb.appendChild(el("span", { style: "font-weight:600;color:var(--text-primary)" }, this._selectedCube));
      panel.appendChild(breadcrumb);

      // Content container (offset for toggle button)
      const content = el("div", { style: "padding-left:36px" });

      // Cube title
      content.appendChild(el("h1", { className: "page-title mb-2" }, this._selectedCube));

      // Delegate to CubeWorkspace for the actual tab rendering
      // We pass the content container and tab name
      this._renderCubeContent(content, tab || "overview");

      panel.appendChild(content);
    },

    _renderCubeContent(container, tab) {
      // We reuse CubeWorkspace's internal methods by telling it to render into our container
      // Set the cube name on CubeWorkspace and trigger its tab rendering
      CubeWorkspace._cubeName = this._selectedCube;
      CubeWorkspace._activeTab = tab;
      CubeWorkspace._tabCache = {};

      // Tabs bar
      const tabsEl = el("div", { className: "tabs", role: "tablist", "aria-label": "Cube workspace tabs" });
      const tabNames = ["overview", "configure", "optimize", "results"];
      tabNames.forEach((t, idx) => {
        const label = t.charAt(0).toUpperCase() + t.slice(1);
        const isActive = t === tab;
        const tabBtn = el("button", {
          className: `tab${isActive ? " active" : ""}`,
          role: "tab",
          "aria-selected": isActive ? "true" : "false",
          tabindex: isActive ? "0" : "-1",
          id: `tab-${t}`,
          "aria-controls": `tabpanel-${t}`,
          dataset: { tab: t },
          onClick: () => {
            history.replaceState(null, "", `#/nav?cube=${encodeURIComponent(this._selectedCube)}&tab=${t}`);
            // Re-render workspace for this tab
            this._renderWorkspace(t);
          },
          onKeydown: (e) => {
            let newIdx = idx;
            if (e.key === "ArrowRight") newIdx = (idx + 1) % tabNames.length;
            else if (e.key === "ArrowLeft") newIdx = (idx - 1 + tabNames.length) % tabNames.length;
            else if (e.key === "Home") newIdx = 0;
            else if (e.key === "End") newIdx = tabNames.length - 1;
            else return;
            e.preventDefault();
            const target = tabsEl.querySelector(`[data-tab="${tabNames[newIdx]}"]`);
            if (target) { target.click(); target.focus(); }
          },
        }, label);
        tabsEl.appendChild(tabBtn);
      });

      // Check for results availability and add "View Results" action
      const hasResults = this._cubeHasResults(this._selectedCube);
      const actionsRow = el("div", { className: "flex items-center gap-2 mb-4", style: "margin-top:-4px" });
      const viewResultsBtn = el("button", {
        className: `btn btn-ghost btn-sm${hasResults ? "" : " disabled"}`,
        disabled: !hasResults,
        onClick: () => { if (hasResults) Router.navigate(`#/results?cube=${encodeURIComponent(this._selectedCube)}`); },
      }, el("span", { html: Icons.externalLink }), "View Prior Results");
      actionsRow.appendChild(viewResultsBtn);

      // Help button
      const helpBtn = el("button", { className: "btn btn-ghost btn-sm", onClick: () => HomePage._showHelpDrawer() },
        el("span", { html: Icons.info }), "Help");
      actionsRow.appendChild(helpBtn);

      container.appendChild(tabsEl);
      container.appendChild(actionsRow);

      // Tab content
      const tabPane = el("div", { className: "tab-pane", role: "tabpanel", id: `tabpanel-${tab}`, "aria-labelledby": `tab-${tab}` });
      CubeWorkspace._tabCache = {};
      CubeWorkspace._contentEl = tabPane;
      CubeWorkspace._tabsEl = tabsEl;

      switch (tab) {
        case "overview": CubeWorkspace._renderOverview(tabPane); break;
        case "configure": CubeWorkspace._renderConfigure(tabPane).catch(err => {
          tabPane.innerHTML = "";
          tabPane.appendChild(el("div", { className: "empty-state" },
            el("div", { className: "empty-state-title" }, "Failed to load configuration"),
            el("div", { className: "empty-state-text" }, err.message),
          ));
        }); break;
        case "optimize": CubeWorkspace._renderOptimize(tabPane); break;
        case "results": CubeWorkspace._renderResults(tabPane); break;
      }
      container.appendChild(tabPane);
    },

    _cubeHasResults(cubeName) {
      // Check if there are result files for this cube in the results API cache
      // We'll do a quick check — if scanData has the cube or savedCubes has it
      return state.savedCubes.some(sc => sc.cube === cubeName);
    },

    // ---- Panel visibility ----
    showPanel() {
      this._panelHidden = false;
      const cubePanel = $("#cubePanel");
      if (cubePanel) cubePanel.classList.remove("hidden-panel");
    },

    hidePanel() {
      this._panelHidden = true;
      const cubePanel = $("#cubePanel");
      if (cubePanel) cubePanel.classList.add("hidden-panel");
    },

    unmount() {
      CubeWorkspace._releaseJobView();
      this._selectedCube = null;
    },
  };

  // ==================================================================
  // Page: CubeWorkspace (4 tabs: Overview, Configure, Optimize, Results)
  // ==================================================================
  const CubeWorkspace = {
    _cubeName: null,
    _activeTab: "overview",
    _dimConfigurator: null,
    _jobId: null,
    _unsubStream: null,
    _timer: createElapsedTimer(),
    _tabCache: {},     // tab name → DOM container (cached rendered tabs)
    _tabsEl: null,     // tabs bar element
    _contentEl: null,  // tab content wrapper

    // ---- Overview Tab ----
    _renderOverview(container) {
      // Show scan-level data immediately if available
      const scanCandidate = (state.scanData?.candidates || []).find(c => c.cube_name === this._cubeName);

      // Current storage order — shown as badges before analysis, then merged into
      // the Dimension Details table (with a position column) once metadata loads.
      const storageOrder = scanCandidate?.storage_order || state.cubeMetadata[this._cubeName]?.storage_order || [];

      // Cube stats from scan
      if (scanCandidate) {
        const statsCard = el("div", { className: "card mb-4" });
        statsCard.appendChild(el("div", { className: "card-title mb-2" }, "Cube Stats"));
        const statsGrid = el("div", { className: "flex gap-4", style: "flex-wrap:wrap" });
        statsGrid.appendChild(el("div", { className: "stat-card", style: "flex:1;min-width:120px" },
          el("div", { className: "stat-label" }, "Dimensions"),
          el("div", { className: "stat-value" }, String(scanCandidate.dim_count)),
        ));
        statsGrid.appendChild(el("div", { className: "stat-card", style: "flex:1;min-width:120px" },
          el("div", { className: "stat-label" }, "RAM"),
          el("div", { className: "stat-value" }, scanCandidate.ram_gb.toFixed(2) + " GB"),
        ));
        statsGrid.appendChild(el("div", { className: "stat-card", style: "flex:1;min-width:120px" },
          el("div", { className: "stat-label" }, "% of Model"),
          el("div", { className: "stat-value" }, scanCandidate.pct_of_total.toFixed(1) + "%"),
        ));
        if (scanCandidate.already_optimized) {
          statsGrid.appendChild(el("div", { className: "stat-card", style: "flex:1;min-width:120px" },
            el("div", { className: "stat-label" }, "Status"),
            el("div", { className: "stat-value" }, el("span", { className: "badge badge-success" }, "Optimized")),
          ));
        }
        if (scanCandidate.last_dim_has_strings) {
          statsGrid.appendChild(el("div", { className: "stat-card", style: "flex:1;min-width:120px" },
            el("div", { className: "stat-label" }, "Last Dimension"),
            el("div", { className: "stat-value" }, el("span", { className: "dim-card-warning", html: Icons.alertTriangle + " Has Strings" })),
          ));
        }
        statsCard.appendChild(statsGrid);
        container.appendChild(statsCard);
      }

      // Full metadata section — load on demand
      const metaSection = el("div", { id: "overview-metadata" });
      const intel = state.cubeMetadata[this._cubeName];
      if (intel) {
        // Already loaded — show it with a refresh option
        const refreshRow = el("div", { className: "flex items-center gap-2 mb-3" });
        const cachedEntry = IntelCache.load(state.activeInstance, this._cubeName);
        if (cachedEntry) {
          refreshRow.appendChild(el("span", { className: "text-xs text-tertiary" },
            `Analyzed ${ScanCache.formatAge(cachedEntry.ts)}`));
        }
        const refreshBtn = el("button", { className: "btn btn-ghost btn-sm" },
          el("span", { html: Icons.refresh }), "Refresh");
        refreshBtn.addEventListener("click", async () => {
          // Clear caches and re-fetch
          delete state.cubeMetadata[this._cubeName];
          IntelCache.clear(state.activeInstance, this._cubeName);
          delete state.cubeViews[this._cubeName];
          refreshBtn.disabled = true;
          refreshBtn.textContent = "Refreshing...";
          try {
            const [data] = await Promise.all([
              this._fetchIntelligence(),
              this._prefetchViews(),
            ]);
            metaSection.innerHTML = "";
            const newRefreshRow = el("div", { className: "flex items-center gap-2 mb-3" });
            newRefreshRow.appendChild(el("span", { className: "text-xs text-tertiary" }, "Analyzed just now"));
            metaSection.appendChild(newRefreshRow);
            this._renderFullMetadata(metaSection, data);
            Toast.success("Cube analysis refreshed");
          } catch (err) {
            Toast.error("Refresh failed: " + err.message);
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = Icons.refresh + " Refresh";
          }
        });
        refreshRow.appendChild(refreshBtn);
        metaSection.appendChild(refreshRow);
        this._renderFullMetadata(metaSection, intel);
      } else {
        // Pre-analysis: show the current storage order as badges (leaf counts,
        // strings, etc. load on demand and then merge into one ordered table).
        if (storageOrder.length > 0) {
          const orderCard = el("div", { className: "card mb-4" });
          orderCard.appendChild(el("div", { className: "card-title mb-2" }, "Current Storage Order"));
          const orderList = el("div", { className: "flex gap-2", style: "flex-wrap:wrap" });
          storageOrder.forEach((dim, i) => {
            orderList.appendChild(el("span", { className: "badge badge-neutral" }, `${i + 1}. ${dim}`));
          });
          orderCard.appendChild(orderList);
          metaSection.appendChild(orderCard);
        }
        // Show button to analyze cube (fetches dimension metadata + views)
        const loadBtn = el("button", { className: "btn btn-primary" },
          el("span", { html: Icons.search }), "Analyze Cube Dimensions & Views");
        loadBtn.addEventListener("click", async () => {
          loadBtn.disabled = true;
          // Replace button with scan-style loading animation
          metaSection.innerHTML = "";
          const loadingCard = el("div", { className: "card", id: "analyze-loading" });
          loadingCard.appendChild(el("div", { className: "flex items-center gap-3 mb-4" },
            el("div", { style: "width:8px;height:8px;border-radius:50%;background:var(--success);animation:pulse 1.5s ease-in-out infinite" }),
            el("span", { className: "text-sm font-medium" }, "Analyzing cube — fetching dimension metadata, element stats, views, and computing suggested order..."),
          ));
          for (let i = 0; i < 4; i++) {
            loadingCard.appendChild(el("div", { className: "loading-skeleton" }));
          }
          metaSection.appendChild(loadingCard);

          try {
            // Fetch intelligence and views in parallel
            const [data] = await Promise.all([
              this._fetchIntelligence(),
              this._prefetchViews(),
            ]);
            metaSection.innerHTML = "";
            this._renderFullMetadata(metaSection, data);
            Toast.success("Cube analysis complete");
          } catch (err) {
            metaSection.innerHTML = "";
            Toast.error("Failed to analyze cube: " + err.message);
            loadBtn.disabled = false;
            metaSection.appendChild(loadBtn);
          }
        });
        metaSection.appendChild(loadBtn);
      }
      container.appendChild(metaSection);
    },

    _renderFullMetadata(container, intel) {
      // Suggested order
      const sugOrder = intel.suggested_order;
      if (sugOrder?.order?.length || (Array.isArray(sugOrder) && sugOrder.length)) {
        const sugCard = el("div", { className: "card mb-4" });
        sugCard.appendChild(el("div", { className: "card-title mb-2" }, "Suggested Order"));
        const sugList = el("div", { className: "flex gap-2", style: "flex-wrap:wrap" });
        const orderArr = sugOrder.order || sugOrder;
        orderArr.forEach((dim, i) => {
          sugList.appendChild(el("span", { className: "badge badge-info" }, `${i + 1}. ${dim}`));
        });
        sugCard.appendChild(sugList);
        if (sugOrder.confidence) {
          sugCard.appendChild(el("div", { className: "text-xs text-tertiary mt-2" },
            `Confidence: ${sugOrder.confidence}` + (sugOrder.notes?.length ? ` — ${sugOrder.notes.join(", ")}` : "")));
        }
        container.appendChild(sugCard);
      }

      // Storage order + dimension details, merged: rows are ordered by the cube's
      // current storage order (position column), each with its leaf count / strings.
      const metaCard = el("div", { className: "card" });
      metaCard.appendChild(el("div", { className: "card-title mb-2" }, "Current Storage Order & Dimension Details"));
      const dimList = Array.isArray(intel.dimensions_metadata) ? intel.dimensions_metadata : [];
      const byName = {};
      dimList.forEach(d => { byName[d.name] = d; });
      const order = (intel.storage_order && intel.storage_order.length) ? intel.storage_order : dimList.map(d => d.name);
      const orderedDims = order.map((name, i) => Object.assign({ position: i + 1 }, byName[name] || { name, leaf_elements: 0, has_strings: false, string_elements: 0 }));
      const metaTable = createTable({
        columns: [
          { key: "position", label: "#", align: "right", value: r => r.position },
          { key: "name", label: "Dimension" },
          { key: "leaf_elements", label: "Leaf Elements", align: "right", value: r => (r.leaf_elements || 0).toLocaleString() },
          { key: "has_strings", label: "Strings", render: r =>
            r.has_strings ? el("span", { className: "dim-card-warning", html: Icons.alertTriangle + " Yes" }) : "No"
          },
          { key: "string_elements", label: "String Count", align: "right", value: r => r.string_elements || 0 },
        ],
        data: orderedDims,
        sortable: true,
        filterable: false,
      });
      metaCard.appendChild(metaTable.el);
      container.appendChild(metaCard);
    },

    // ---- Configure Tab ----
    async _renderConfigure(container) {
      // Show loading state while fetching dimension metadata
      const loadingEl = el("div", { className: "empty-state", style: "padding:3rem" },
        el("div", { className: "loading-spinner mb-2" }),
        el("div", { className: "empty-state-text" }, "Loading cube dimensions and views from TM1..."),
      );
      container.appendChild(loadingEl);

      const intel = await this._fetchIntelligence();
      container.removeChild(loadingEl);

      const dimNames = intel.storage_order || [];
      // Convert dimensions_metadata list to dict keyed by name
      const dimMetaList = Array.isArray(intel.dimensions_metadata) ? intel.dimensions_metadata : [];
      const dimMeta = {};
      dimMetaList.forEach(d => { dimMeta[d.name] = d; });

      const layout = el("div", { className: "config-layout" });
      const leftCol = el("div");
      const rightCol = el("div");

      // --- Left column ---

      // Mode
      const modeGroup = el("div", { className: "form-group" });
      modeGroup.appendChild(el("label", { className: "form-label" }, "Mode"));
      const modeSelect = el("select", { className: "form-input" });
      ["greedy", "predefined", "position", "dimension"].forEach(m => {
        modeSelect.appendChild(el("option", { value: m }, m.charAt(0).toUpperCase() + m.slice(1)));
      });
      modeGroup.appendChild(modeSelect);
      leftCol.appendChild(modeGroup);

      // Executions
      const execGroup = el("div", { className: "form-group" });
      execGroup.appendChild(el("label", { className: "form-label" }, "Executions per permutation"));
      const execInput = el("input", { type: "number", className: "form-input", value: "5", min: "1", max: "20" });
      execGroup.appendChild(execInput);
      leftCol.appendChild(execGroup);

      // Output format
      const outputGroup = el("div", { className: "form-group" });
      outputGroup.appendChild(el("label", { className: "form-label" }, "Output format"));
      const outputSelect = el("select", { className: "form-input" });
      outputSelect.appendChild(el("option", { value: "csv" }, "CSV"));
      outputSelect.appendChild(el("option", { value: "xlsx" }, "Excel (XLSX)"));
      outputGroup.appendChild(outputSelect);
      leftCol.appendChild(outputGroup);

      // Toggles row
      const toggleRow = el("div", { className: "form-row mb-4" });
      const fastLabel = el("label", { className: "checkbox-label" });
      const fastCb = el("input", { type: "checkbox" });
      fastLabel.appendChild(fastCb);
      fastLabel.appendChild(document.createTextNode("Fast mode (seed & refine)"));
      fastLabel.title = "Seed from the cardinality-suggested order, then refine only " +
        "the dimensions leaf-count theory leaves ambiguous. Faster than a full search; " +
        "unchecked runs the thorough search.";
      toggleRow.appendChild(fastLabel);

      const autoApplyLabel = el("label", { className: "checkbox-label" });
      const autoApplyCb = el("input", { type: "checkbox" });
      autoApplyLabel.appendChild(autoApplyCb);
      autoApplyLabel.appendChild(document.createTextNode("Auto-apply best"));
      toggleRow.appendChild(autoApplyLabel);
      leftCol.appendChild(toggleRow);

      // Dimensions section — dimensions are listed in the cube's current storage
      // order; the Refresh button re-fetches it (e.g. after applying an optimization).
      const dimsHeader = el("div", { className: "section-divider flex items-center gap-2" });
      dimsHeader.appendChild(document.createTextNode("Dimensions"));
      const dimRefreshBtn = el("button", {
        className: "btn btn-ghost btn-sm", style: "margin-left:auto",
        title: "Re-fetch the current storage order from TM1 (use after applying an optimization run)",
      }, el("span", { html: Icons.refresh }), "Refresh");
      dimRefreshBtn.addEventListener("click", async () => {
        delete state.cubeMetadata[this._cubeName];
        IntelCache.clear(state.activeInstance, this._cubeName);
        container.innerHTML = "";
        try {
          await this._renderConfigure(container);
          Toast.success("Dimension order refreshed");
        } catch (err) {
          Toast.error("Refresh failed: " + err.message);
        }
      });
      dimsHeader.appendChild(dimRefreshBtn);
      leftCol.appendChild(dimsHeader);

      // Suggested order button — only shown in predefined mode
      const sugBtn = el("button", { className: "btn btn-secondary btn-sm mb-2" },
        el("span", { html: Icons.zap }), "Add Suggested Order");
      sugBtn.style.display = modeSelect.value === "predefined" ? "" : "none";
      sugBtn.addEventListener("click", () => {
        if (intel.suggested_order && this._dimConfigurator) {
          const sugArr = intel.suggested_order?.order || intel.suggested_order;
          this._dimConfigurator.applySuggested(Array.isArray(sugArr) ? sugArr : []);
        }
      });
      leftCol.appendChild(sugBtn);

      this._dimConfigurator = createDimensionConfigurator({
        dimensions: dimNames,
        metadata: dimMeta,
        mode: modeSelect.value,
        onChange: () => updatePreview(),
      });
      leftCol.appendChild(this._dimConfigurator.el);

      modeSelect.addEventListener("change", () => {
        this._dimConfigurator.setMode(modeSelect.value);
        sugBtn.style.display = modeSelect.value === "predefined" ? "" : "none";
        updatePreview();
      });

      // Views section
      leftCol.appendChild(el("div", { className: "section-divider" }, "Views (optional)"));
      leftCol.appendChild(el("div", { className: "form-hint mb-2" }, "Omit for RAM-only optimization"));
      this._selectedViews = [];
      this._viewsContainer = el("div", { id: "views-section" });
      leftCol.appendChild(this._viewsContainer);
      this._loadViews(this._viewsContainer);

      // Processes section
      leftCol.appendChild(el("div", { className: "section-divider" }, "Processes (optional)"));
      const procsContainer = el("div", { id: "procs-transfer" });
      leftCol.appendChild(procsContainer);
      const processParamsContainer = el("div", { id: "process-params" });
      leftCol.appendChild(processParamsContainer);
      this._loadProcesses(procsContainer, processParamsContainer);

      // --- Right column ---
      const previewHeader = el("div", { className: "section-divider flex items-center gap-2" });
      previewHeader.appendChild(document.createTextNode("Config Preview"));
      const resetBtn = el("button", { className: "btn btn-ghost btn-sm", style: "margin-left:auto", title: "Reset to defaults" },
        el("span", { html: Icons.rotateCcw }), "Reset");
      resetBtn.addEventListener("click", () => {
        modeSelect.value = "greedy";
        execInput.value = "5";
        outputSelect.value = "csv";
        fastCb.checked = false;
        autoApplyCb.checked = false;
        if (self._dimConfigurator) self._dimConfigurator.reset();
        self._selectedViews = [];
        if (self._viewsContainer) self._renderViewsSection();
        self._selectedProcesses = [];
        if (self._procsContainer) self._renderProcessSection();
        sugBtn.style.display = "none";
        updatePreview();
      });
      previewHeader.appendChild(resetBtn);
      rightCol.appendChild(previewHeader);
      const preview = el("pre", { className: "json-preview", id: "config-preview" });
      rightCol.appendChild(preview);

      // Action buttons
      const btnRow = el("div", { className: "flex gap-2 mt-4" });
      const saveStartBtn = el("button", { className: "btn btn-primary" },
        el("span", { html: Icons.play }), "Save & Start Optimization");
      const saveOnlyBtn = el("button", { className: "btn btn-secondary" }, "Save Config Only");

      saveStartBtn.addEventListener("click", async () => {
        const config = buildConfig();
        try {
          const vResult = await Api.validate(config, "optimize");
          if (!vResult.valid) { Toast.error("Validation: " + vResult.error); return; }

          const filename = `${config.cube}_${config.instance}.json`;
          await Api.saveConfig(config, filename);
          Sidebar.loadSavedCubes();

          const resp = await Api.startJob("optimize", config, Credentials.get(state.activeInstance));
          this._jobId = resp.job_id;
          StreamManager.connect(resp.job_id);
          Sidebar.updateActivityMonitor();
          Toast.success("Optimization started!");
          // Invalidate optimize tab cache so it re-renders with the new job
          if (this._tabCache.optimize) {
            this._tabCache.optimize.remove();
            delete this._tabCache.optimize;
          }
          this._activeTab = "optimize";
          Router.navigate(`#/cube/${encodeURIComponent(this._cubeName)}?tab=optimize`);
        } catch (err) {
          Toast.error(err.message);
        }
      });

      saveOnlyBtn.addEventListener("click", async () => {
        const config = buildConfig();
        try {
          const filename = `${config.cube}_${config.instance}.json`;
          const resp = await Api.saveConfig(config, filename);
          Sidebar.loadSavedCubes();
          Toast.success(`Config saved to ${resp.path}`);
        } catch (err) {
          Toast.error(err.message);
        }
      });

      btnRow.appendChild(saveStartBtn);
      btnRow.appendChild(saveOnlyBtn);
      rightCol.appendChild(btnRow);

      layout.appendChild(leftCol);
      layout.appendChild(rightCol);
      container.appendChild(layout);

      const self = this;
      function buildConfig() {
        const dimConfig = self._dimConfigurator ? self._dimConfigurator.getConfig() : { included: [], excluded: [] };
        const views = self._selectedViews || [];
        const selectedProcs = self._selectedProcesses || [];
        const mode = modeSelect.value;

        const config = {
          instance: state.activeInstance,
          cube: self._cubeName,
          executions: parseInt(execInput.value) || 5,
          output: outputSelect.value,
        };

        if (views.length > 0) config.views = views;
        if (selectedProcs.length > 0) config.processes = selectedProcs.map(p => p.name);
        if (fastCb.checked) config.fast = true;
        if (autoApplyCb.checked) config.auto_apply = true;

        if (mode === "greedy") {
          if (dimConfig.excluded.length > 0) config.dimensions_to_exclude = dimConfig.excluded;
          if (dimConfig.ignoreOrders?.length > 0) config.orders_to_ignore = dimConfig.ignoreOrders;
          if (dimConfig.positionRules?.length > 0) config.dimension_position_rules = dimConfig.positionRules;
        } else if (mode === "predefined") {
          if (dimConfig.predefinedOrders?.length > 0) config.predefined_orders = dimConfig.predefinedOrders;
        } else if (mode === "position") {
          config.optimize_position = dimConfig.targetPosition;
          if (dimConfig.excluded.length > 0) config.dimensions_to_exclude = dimConfig.excluded;
        } else if (mode === "dimension") {
          config.optimize_dimension = dimConfig.targetDimension;
        }

        // Collect process parameters from selected processes
        if (selectedProcs.length > 0) {
          const processParams = {};
          selectedProcs.forEach(proc => {
            if (proc.params && proc.params.length > 0) {
              processParams[proc.name] = {};
              proc.params.forEach(p => { processParams[proc.name][p.name] = p.value; });
            }
          });
          if (Object.keys(processParams).length > 0) config.process_parameters = processParams;
        }

        return config;
      }

      function updatePreview() {
        const config = buildConfig();
        const previewEl = $("#config-preview");
        if (previewEl) previewEl.innerHTML = syntaxHighlight(JSON.stringify(config, null, 2));
      }
      self._updatePreview = updatePreview;

      // Wire up all inputs to update preview
      fastCb.addEventListener("change", updatePreview);
      autoApplyCb.addEventListener("change", updatePreview);
      execInput.addEventListener("input", updatePreview);
      outputSelect.addEventListener("change", updatePreview);

      // Initial preview
      setTimeout(updatePreview, 100);
    },

    async _loadViews(container) {
      if (!state.connected) {
        container.appendChild(el("div", { className: "text-xs text-tertiary" }, "Connect to an instance to load views"));
        return;
      }
      if (!state.cubeViews[this._cubeName]) {
        container.appendChild(el("div", { className: "text-xs text-tertiary", id: "views-loading" }, "Loading views..."));
        try {
          const data = await Api.getViews(state.activeInstance, Credentials.get(state.activeInstance), this._cubeName);
          state.cubeViews[this._cubeName] = data.views || [];
        } catch (err) {
          state.cubeViews[this._cubeName] = [];
          console.warn("Failed to load views:", err);
        }
        const loadingEl = container.querySelector("#views-loading");
        if (loadingEl) loadingEl.remove();
      }
      this._renderViewsSection();
    },

    _renderViewsSection() {
      const container = this._viewsContainer;
      if (!container) return;
      container.innerHTML = "";

      const views = state.cubeViews[this._cubeName] || [];

      if (this._selectedViews.length === 0) {
        container.appendChild(el("div", { className: "text-xs text-tertiary" }, "No views selected"));
      } else {
        this._selectedViews.forEach((view, idx) => {
          const row = el("div", { className: "selection-row" });
          row.appendChild(el("span", { className: "selection-row-name" }, view));
          const removeBtn = el("span", { className: "selection-row-remove", role: "button", tabindex: "0", "aria-label": "Remove", html: Icons.x, title: "Remove" });
          removeBtn.addEventListener("click", () => {
            this._selectedViews.splice(idx, 1);
            this._renderViewsSection();
            if (this._updatePreview) this._updatePreview();
          });
          row.appendChild(removeBtn);
          container.appendChild(row);
        });
      }

      if (views.length > 0) {
        const addBtn = el("button", { className: "btn btn-ghost btn-sm mt-2" },
          el("span", { html: Icons.plus }), "Add Views");
        addBtn.addEventListener("click", () => this._showViewsPicker());
        container.appendChild(addBtn);
      } else if (views.length === 0 && this._selectedViews.length === 0) {
        container.innerHTML = "";
        container.appendChild(el("div", { className: "text-xs text-tertiary" }, "No public views found for this cube"));
      }
    },

    _showViewsPicker() {
      const views = state.cubeViews[this._cubeName] || [];
      const alreadySelected = new Set(this._selectedViews);
      const available = views.filter(v => !alreadySelected.has(v));
      const checked = new Set();

      const body = el("div");
      const searchInput = el("input", { type: "text", className: "form-input w-full mb-2", placeholder: "Search views..." });
      body.appendChild(searchInput);

      const listEl = el("div", { style: "max-height:300px;overflow-y:auto;border:1px solid var(--border-primary);border-radius:var(--radius-md)" });
      body.appendChild(listEl);

      const addSelectedBtn = el("button", { className: "btn btn-primary" }, "Add Selected");
      addSelectedBtn.disabled = true;

      const renderList = (filter) => {
        listEl.innerHTML = "";
        const filtered = available.filter(v => !filter || v.toLowerCase().includes(filter));
        if (filtered.length === 0) {
          listEl.appendChild(el("div", { className: "transfer-item-empty" }, available.length === 0 ? "All views already selected" : "No matching views"));
          return;
        }
        filtered.forEach(viewName => {
          const item = el("div", { className: "transfer-item", style: "cursor:pointer;display:flex;align-items:center;gap:8px" });
          const cb = el("input", { type: "checkbox" });
          cb.checked = checked.has(viewName);
          cb.addEventListener("change", () => {
            if (cb.checked) checked.add(viewName); else checked.delete(viewName);
            addSelectedBtn.disabled = checked.size === 0;
            addSelectedBtn.textContent = checked.size > 0 ? `Add Selected (${checked.size})` : "Add Selected";
          });
          item.appendChild(cb);
          item.appendChild(document.createTextNode(viewName));
          item.addEventListener("click", e => {
            if (e.target !== cb) { cb.checked = !cb.checked; cb.dispatchEvent(new Event("change")); }
          });
          listEl.appendChild(item);
        });
      };

      searchInput.addEventListener("input", () => renderList(searchInput.value.toLowerCase()));
      renderList("");

      addSelectedBtn.addEventListener("click", () => {
        checked.forEach(v => this._selectedViews.push(v));
        this._renderViewsSection();
        if (this._updatePreview) this._updatePreview();
        Modal.close();
      });

      Modal.open({
        title: "Add Views",
        body,
        footer: [
          el("button", { className: "btn btn-ghost", onClick: () => Modal.close() }, "Cancel"),
          addSelectedBtn,
        ],
        size: "md",
      });
      setTimeout(() => searchInput.focus(), 100);
    },

    _selectedProcesses: [],   // [{ name, params: [{name, value}] }]

    async _loadProcesses(container, paramsContainer) {
      if (state.processes.length === 0) {
        try {
          const data = await Api.getProcesses(state.activeInstance, Credentials.get(state.activeInstance));
          state.processes = data.processes || [];
        } catch {
          state.processes = [];
        }
      }
      this._selectedProcesses = [];
      this._procsContainer = container;
      this._procsParamsContainer = paramsContainer;
      this._renderProcessSection();
    },

    _renderProcessSection() {
      const container = this._procsContainer;
      const paramsContainer = this._procsParamsContainer;
      if (!container) return;
      container.innerHTML = "";
      paramsContainer.innerHTML = "";

      if (this._selectedProcesses.length === 0) {
        container.appendChild(el("div", { className: "text-xs text-tertiary" }, "No processes selected"));
      } else {
        this._selectedProcesses.forEach((proc, idx) => {
          // Selection row
          const row = el("div", { className: "selection-row" });
          row.appendChild(el("span", { className: "selection-row-name" }, proc.name));
          const removeBtn = el("span", { className: "selection-row-remove", role: "button", tabindex: "0", "aria-label": "Remove", html: Icons.x, title: "Remove" });
          removeBtn.addEventListener("click", () => {
            this._selectedProcesses.splice(idx, 1);
            this._renderProcessSection();
            if (this._updatePreview) this._updatePreview();
          });
          row.appendChild(removeBtn);
          container.appendChild(row);

          // Parameter inputs below the row
          if (proc.params && proc.params.length > 0) {
            const paramsBlock = el("div", { className: "process-params" });
            proc.params.forEach(p => {
              const paramRow = el("div", { className: "param-row" });
              paramRow.appendChild(el("span", { className: "param-label" }, p.name));
              const input = el("input", {
                className: "param-input",
                type: "text",
                value: p.value || "",
                dataset: { process: proc.name, param: p.name },
              });
              input.addEventListener("input", () => {
                p.value = input.value;
                if (this._updatePreview) this._updatePreview();
              });
              paramRow.appendChild(input);
              paramsBlock.appendChild(paramRow);
            });
            paramsContainer.appendChild(paramsBlock);
          }
        });
      }

      const addBtn = el("button", { className: "btn btn-ghost btn-sm mt-2" },
        el("span", { html: Icons.plus }), "Add Process");
      addBtn.addEventListener("click", () => this._showProcessPicker());
      container.appendChild(addBtn);
    },

    _showProcessPicker() {
      const body = el("div");
      const searchInput = el("input", { type: "text", className: "form-input w-full mb-2", placeholder: "Search processes..." });
      body.appendChild(searchInput);

      const listEl = el("div", { style: "max-height:300px;overflow-y:auto;border:1px solid var(--border-primary);border-radius:var(--radius-md)" });
      body.appendChild(listEl);

      const alreadySelected = new Set(this._selectedProcesses.map(p => p.name));

      const renderList = (filter) => {
        listEl.innerHTML = "";
        const filtered = state.processes.filter(p =>
          !alreadySelected.has(p) && (!filter || p.toLowerCase().includes(filter.toLowerCase()))
        );
        if (filtered.length === 0) {
          listEl.appendChild(el("div", { className: "transfer-item-empty" }, "No matching processes"));
          return;
        }
        filtered.forEach(procName => {
          const item = el("div", {
            className: "transfer-item",
            style: "cursor:pointer",
            onClick: async () => {
              Modal.close();
              // Fetch params for this process
              try {
                const data = await Api.getProcessParameters(state.activeInstance, Credentials.get(state.activeInstance), procName);
                const params = (data.parameters || []).map(p => ({ name: p.name, value: p.value || "" }));
                this._selectedProcesses.push({ name: procName, params });
              } catch {
                this._selectedProcesses.push({ name: procName, params: [] });
              }
              this._renderProcessSection();
              if (this._updatePreview) this._updatePreview();
            }
          }, procName);
          listEl.appendChild(item);
        });
      };

      searchInput.addEventListener("input", () => renderList(searchInput.value));
      renderList("");

      Modal.open({ title: "Add Process", body, size: "md" });
      setTimeout(() => searchInput.focus(), 100);
    },

    // ---- Optimize Tab ----
    _renderOptimize(container) {
      this._releaseJobView();
      // Status bar
      const statusBar = el("div", { className: "terminal-status" });
      const statusDot = el("span", { className: "status-dot" });
      const statusText = el("span", { className: "text-sm font-medium" }, "Idle");
      const timerEl = el("span", { className: "terminal-timer" }, "00:00");
      const stopBtn = el("button", { className: "btn btn-danger btn-sm", style: "display:none;margin-left:auto" },
        el("span", { html: Icons.square, style: "display:inline-flex;margin-right:4px" }), "Stop");
      stopBtn.addEventListener("click", async () => {
        if (!this._jobId) return;
        stopBtn.disabled = true;
        stopBtn.textContent = "Stopping\u2026";
        try { await Api.cancelJob(this._jobId); } catch (e) { Toast.error("Cancel failed: " + e.message); stopBtn.disabled = false; stopBtn.innerHTML = ""; stopBtn.appendChild(el("span", { html: Icons.square, style: "display:inline-flex;margin-right:4px" })); stopBtn.appendChild(document.createTextNode("Stop")); }
      });
      statusBar.appendChild(statusDot);
      statusBar.appendChild(statusText);
      statusBar.appendChild(timerEl);
      statusBar.appendChild(stopBtn);
      container.appendChild(statusBar);

      // Terminal
      const terminal = createTerminal();
      container.appendChild(terminal.el);

      // Determine job for this cube
      this._findActiveJob().then(job => {
        this._jobId = job ? job.job_id : null;
        if (!job) {
          terminal.el.appendChild(el("div", { className: "terminal-line text-tertiary" }, "No active optimization. Configure and start from the Configure tab."));
          return;
        }

        StreamManager.getLogs(job.job_id).forEach(log => terminal.append(log));

        // This tab's stream manager only knows the jobs this tab has streamed. For
        // any other job — one started in another tab, or before a reload — the
        // server's status decides; connecting replays the whole log from the start.
        const streamed = StreamManager.getStatus(job.job_id);
        const sseStatus = streamed === "unknown" ? job.status : streamed;
        if (sseStatus === "running") {
          statusDot.classList.add("running");
          statusText.textContent = "Running";
          stopBtn.style.display = "";
          this._timer.start(timerEl, job.started_at);
          StreamManager.connect(job.job_id);
        } else if (sseStatus === "completed") {
          statusDot.classList.add("completed");
          statusText.textContent = "Completed";
        } else if (sseStatus === "failed") {
          statusDot.classList.add("failed");
          statusText.textContent = "Failed";
        } else if (sseStatus === "cancelled") {
          statusDot.classList.add("failed");
          statusText.textContent = "Cancelled";
        }
        // A finished job this tab never streamed: connect once to replay its log.
        // The server sends the log, then the final event, then closes the stream.
        // The status above is already drawn, so the final event is not announced.
        const replaying = streamed === "unknown" && sseStatus !== "running";
        if (replaying) StreamManager.connect(job.job_id);

        this._unsubStream = StreamManager.subscribe(job.job_id, (event, data) => {
          if (event === "log") {
            terminal.append(data);
          } else if (replaying) {
            return;
          } else if (event === "complete") {
            // A run that fails without raising still ends with "complete"; its
            // status says whether it succeeded.
            const ok = data.status === "completed";
            statusDot.className = `status-dot ${ok ? "completed" : "failed"}`;
            statusText.textContent = ok ? "Completed" : "Failed";
            stopBtn.style.display = "none";
            this._timer.stop();
            Sidebar.updateActivityMonitor();
            if (ok) Toast.success("Optimization completed!");
            else Toast.error("Optimization failed — see the log above");
          } else if (event === "error_event") {
            statusDot.className = "status-dot failed";
            statusText.textContent = "Failed";
            stopBtn.style.display = "none";
            this._timer.stop();
            Sidebar.updateActivityMonitor();
            Toast.error("Optimization failed: " + (data.error || "Unknown error"));
          } else if (event === "cancelled") {
            statusDot.className = "status-dot failed";
            statusText.textContent = "Cancelled";
            stopBtn.style.display = "none";
            this._timer.stop();
            Sidebar.updateActivityMonitor();
            Toast.info("Optimization cancelled");
          }
        });
      });
    },

    // Stop following the job on the Optimize tab. Called before the tab is drawn
    // again and when the cube page is left, so no stream subscriber or timer
    // outlives the view it draws into.
    _releaseJobView() {
      if (this._unsubStream) { this._unsubStream(); this._unsubStream = null; }
      this._timer.stop();
    },

    // The job this cube's Optimize tab shows: the one running on it, else its most
    // recent. Asked of the server each time — an id kept from another cube would
    // show that cube's log here.
    async _findActiveJob() {
      try {
        const data = await Api.getJobs();
        const mine = (data.jobs || []).filter(j => !JOB_KINDS[j.mode] && j.label === this._cubeName);
        return mine.find(j => j.status === "running") || mine[0] || null;
      } catch {
        return null;
      }
    },

    // ---- Results Tab (per-cube) ----
    async _renderResults(container) {
      container.appendChild(el("div", { className: "text-secondary text-sm" }, "Loading results..."));
      try {
        const data = await Api.getResults();
        const results = (data.results || []).filter(r => r.cube === this._cubeName);
        container.innerHTML = "";

        if (results.length === 0) {
          container.appendChild(el("div", { className: "empty-state" },
            el("div", { className: "empty-state-title" }, "No results yet"),
            el("div", { className: "empty-state-text" }, "Run an optimization to see results here."),
          ));
          return;
        }

        const tbl = createTable({
          columns: [
            { key: "instance", label: "Instance", render: r => el("span", { className: "text-secondary text-sm" }, r.instance || "—") },
            { key: "filename", label: "File", render: r => el("span", { className: "font-medium" }, (r.filename || "").split("/").pop()) },
            { key: "type", label: "Type", render: r => el("span", { className: "badge badge-neutral" }, r.type.toUpperCase()) },
            { key: "size", label: "Size", align: "right", value: r => formatBytes(r.size) },
            { key: "modified", label: "Date", value: r => formatDate(r.modified) },
            { key: "actions", label: "", sortable: false, render: r => {
              return el("a", { href: `/api/result/${encodeURIComponent(r.filename)}`, target: "_blank", className: "btn btn-ghost btn-sm", html: Icons.externalLink + " Open" });
            }},
          ],
          data: results,
          filterable: false,
        });
        container.appendChild(tbl.el);
      } catch (err) {
        container.innerHTML = "";
        container.appendChild(el("div", { className: "text-secondary" }, "Failed to load results: " + err.message));
      }
    },

    async _fetchIntelligence() {
      // 1. In-memory cache
      if (state.cubeMetadata[this._cubeName]) return state.cubeMetadata[this._cubeName];
      // 2. localStorage cache
      const cached = IntelCache.load(state.activeInstance, this._cubeName);
      if (cached) {
        state.cubeMetadata[this._cubeName] = cached.data;
        return cached.data;
      }
      // 3. Fetch from API and cache
      const data = await Api.getCubeIntelligence(state.activeInstance, Credentials.get(state.activeInstance), this._cubeName);
      state.cubeMetadata[this._cubeName] = data;
      IntelCache.save(state.activeInstance, this._cubeName, data);
      return data;
    },

    async _prefetchViews() {
      if (state.cubeViews[this._cubeName]) return state.cubeViews[this._cubeName];
      try {
        const data = await Api.getViews(state.activeInstance, Credentials.get(state.activeInstance), this._cubeName);
        state.cubeViews[this._cubeName] = data.views || [];
      } catch (_) {
        state.cubeViews[this._cubeName] = [];
      }
      return state.cubeViews[this._cubeName];
    },
  };

  // ==================================================================
  // Page: Results (global)
  // ==================================================================
  const ResultsPage = {
    mount() {
      const page = $("#page-results");
      page.innerHTML = "";

      page.appendChild(el("div", { className: "page-header" },
        el("h1", { className: "page-title" }, "Results"),
        el("p", { className: "page-subtitle" }, "All optimization results across cubes"),
      ));

      this._loadResults(page);
    },

    async _loadResults(page) {
      try {
        const data = await Api.getResults();
        const results = data.results || [];

        if (results.length === 0) {
          page.appendChild(el("div", { className: "empty-state" },
            el("div", { className: "empty-state-title" }, "No results"),
            el("div", { className: "empty-state-text" }, "Run cube optimizations to see results here."),
          ));
          return;
        }

        const tbl = createTable({
          columns: [
            { key: "instance", label: "Instance", render: r => el("span", { className: "text-secondary text-sm" }, r.instance || "—") },
            { key: "cube", label: "Cube", render: r => el("a", { href: `#/cube/${encodeURIComponent(r.cube)}?tab=results`, className: "font-medium" }, r.cube) },
            { key: "filename", label: "File", value: r => (r.filename || "").split("/").pop() },
            { key: "type", label: "Type", render: r => el("span", { className: "badge badge-neutral" }, r.type.toUpperCase()) },
            { key: "size", label: "Size", align: "right", sortValue: r => r.size, value: r => formatBytes(r.size) },
            { key: "modified", label: "Date", sortValue: r => r.modified, value: r => formatDate(r.modified) },
            { key: "actions", label: "", sortable: false, render: r => {
              return el("a", { href: `/api/result/${encodeURIComponent(r.filename)}`, target: "_blank", className: "btn btn-ghost btn-sm", html: Icons.externalLink + " Open" });
            }},
          ],
          data: results,
        });
        page.appendChild(tbl.el);
      } catch (err) {
        Toast.error("Failed to load results: " + err.message);
      }
    },

    unmount() {},
  };

  // ==================================================================
  // Page: Jobs
  // ==================================================================
  const JobsPage = {
    _refreshInterval: null,

    mount() {
      const page = $("#page-jobs");
      page.innerHTML = "";

      page.appendChild(el("div", { className: "page-header" },
        el("h1", { className: "page-title" }, "Jobs"),
        el("p", { className: "page-subtitle" }, "Optimization job history and status"),
      ));

      this._loadJobs(page);
      this._refreshInterval = setInterval(() => this._loadJobs(page), 10000);
    },

    async _loadJobs(page) {
      try {
        const data = await Api.getJobs();
        const jobs = data.jobs || [];

        // Remove old table
        const existing = page.querySelector(".table-wrapper");
        if (existing) existing.remove();
        const existingEmpty = page.querySelector(".empty-state");
        if (existingEmpty) existingEmpty.remove();

        if (jobs.length === 0) {
          page.appendChild(el("div", { className: "empty-state" },
            el("div", { className: "empty-state-title" }, "No jobs"),
            el("div", { className: "empty-state-text" }, "Start an optimization to see jobs here."),
          ));
          return;
        }

        const tbl = createTable({
          columns: [
            { key: "status", label: "Status", render: r => jobStatusBadge(r.status) },
            { key: "label", label: "Job", render: r => el("a", { href: jobLink(r), className: "font-medium" }, r.label) },
            { key: "mode", label: "Kind", value: r => jobTitle(r) },
            { key: "instance", label: "Instance", value: r => r.instance || "—" },
            { key: "started_at", label: "Started", value: r => formatDate(r.started_at), sortValue: r => r.started_at },
            { key: "job_id", label: "Job ID", render: r => el("span", { className: "text-xs text-tertiary" }, r.job_id) },
          ],
          data: jobs,
          filterable: false,
          onRowClick: row => Router.navigate(jobLink(row)),
        });
        page.appendChild(tbl.el);
      } catch (err) {
        Toast.error("Failed to load jobs: " + err.message);
      }
    },

    unmount() {
      if (this._refreshInterval) { clearInterval(this._refreshInterval); this._refreshInterval = null; }
    },
  };

  // ==================================================================
  // Page: Sync Order — copy storage orders from one instance to another
  // ==================================================================
  const TransferPage = {
    _sourceInstance: null,
    _sourceConnected: false,
    _sourceCubes: [],

    _targetInstance: null,
    _targetConnected: false,
    _targetOrders: {},
    _transferredCubes: {},
    _targetMissing: [],
    _jobId: null,
    _applyTarget: null,
    _applyTotal: 0,
    _applyResults: [],
    _applyDone: null,
    _unsubApply: null,

    _includeOptimized: true,

    mount() {
      const page = $("#page-transfer");
      page.innerHTML = "";

      page.appendChild(el("div", { className: "page-header" },
        el("h1", { className: "page-title" }, "Sync Order"),
        el("p", { className: "text-secondary text-sm mt-1" }, "Sync optimized dimension orders from a source instance to a target instance"),
      ));

      const panels = el("div", { className: "transfer-panels" });

      const sourcePanel = el("div", { className: "transfer-panel transfer-source" });
      sourcePanel.appendChild(el("div", { className: "transfer-panel-header" }, "Source Instance"));
      this._buildSourcePanel(sourcePanel);
      panels.appendChild(sourcePanel);

      const targetPanel = el("div", { className: "transfer-panel transfer-target" });
      targetPanel.appendChild(el("div", { className: "transfer-panel-header" }, "Target Instance"));
      this._buildTargetPanel(targetPanel);
      panels.appendChild(targetPanel);

      page.appendChild(panels);
      const applyContainer = el("div", { id: "transfer-apply" });
      page.appendChild(applyContainer);
      this._renderApplyPanel(applyContainer);
    },

    _buildSourcePanel(panel) {
      const connRow = el("div", { className: "transfer-connect-row" });
      const instanceSelect = el("select", { className: "form-input", id: "transfer-source-instance" });
      instanceSelect.appendChild(el("option", { value: "" }, "Select instance..."));
      state.instances.forEach(name => {
        instanceSelect.appendChild(el("option", { value: name }, name));
      });
      if (this._sourceInstance) instanceSelect.value = this._sourceInstance;
      connRow.appendChild(instanceSelect);

      const connectBtn = el("button", { className: "btn btn-primary btn-sm", onClick: async () => {
        const inst = instanceSelect.value;
        if (!inst) { Toast.error("Select a source instance"); return; }
        this._sourceInstance = inst;
        if (!(await Credentials.ensure(inst))) return;
        connectBtn.disabled = true;
        connectBtn.textContent = "Scanning...";
        try {
          const data = await Api.transferScan(inst, Credentials.get(inst), 100);
          this._sourceCubes = data.candidates || [];
          this._sourceConnected = true;
          Toast.success(`Scanned ${this._sourceCubes.length} cubes`);
          this.mount();
        } catch (err) {
          Toast.error(err.message);
          connectBtn.disabled = false;
          connectBtn.textContent = "Connect & Scan";
        }
      }}, "Connect & Scan");
      connRow.appendChild(connectBtn);
      panel.appendChild(connRow);

      if (!this._sourceConnected) return;

      const filterBar = el("div", { className: "transfer-filter-bar" });

      const inclOptCb = el("input", { type: "checkbox", id: "filter-include-optimized" });
      inclOptCb.checked = this._includeOptimized;
      inclOptCb.addEventListener("change", () => { this._includeOptimized = inclOptCb.checked; this._renderSourceList(listContainer); });
      filterBar.appendChild(el("label", { className: "flex items-center gap-1 text-sm" }, inclOptCb, "Include Optimized"));

      panel.appendChild(filterBar);

      const listContainer = el("div", { className: "transfer-cube-list" });
      this._renderSourceList(listContainer);
      panel.appendChild(listContainer);
    },

    _filteredCubes() {
      return this._sourceCubes.filter(c => {
        if (c.already_optimized && !this._includeOptimized) return false;
        return true;
      });
    },

    _renderSourceList(container) {
      container.innerHTML = "";
      const filtered = this._filteredCubes();
      if (filtered.length === 0) {
        container.appendChild(el("div", { className: "text-secondary text-sm p-2" }, "No cubes match filters"));
        return;
      }
      filtered.forEach(cube => {
        const row = el("div", {
          className: "transfer-cube-row",
          draggable: "true",
          dataset: { cubeName: cube.cube_name },
        });
        row.addEventListener("dragstart", (e) => {
          e.dataTransfer.setData("text/plain", JSON.stringify(
            [{ cube_name: cube.cube_name, storage_order: cube.storage_order }]
          ));
          e.dataTransfer.effectAllowed = "copy";
        });

        const info = el("div", { className: "transfer-cube-info" });
        info.appendChild(el("div", { className: "font-medium text-sm" }, cube.cube_name));
        const meta = `${cube.dim_count} dims | ${cube.ram_gb.toFixed(2)} GB`;
        const badge = cube.already_optimized
          ? el("span", { className: "badge badge-success", style: "font-size:9px;margin-left:4px" }, "optimized")
          : null;
        info.appendChild(el("div", { className: "text-xs text-tertiary" }, meta, badge));
        row.appendChild(info);

        container.appendChild(row);
      });
    },

    _buildTargetPanel(panel) {
      const connRow = el("div", { className: "transfer-connect-row" });
      const instanceSelect = el("select", { className: "form-input", id: "transfer-target-instance" });
      instanceSelect.appendChild(el("option", { value: "" }, "Select instance..."));
      state.instances.forEach(name => {
        instanceSelect.appendChild(el("option", { value: name }, name));
      });
      if (this._targetInstance) instanceSelect.value = this._targetInstance;
      connRow.appendChild(instanceSelect);

      const connectBtn = el("button", { className: "btn btn-primary btn-sm", onClick: async () => {
        const inst = instanceSelect.value;
        if (!inst) { Toast.error("Select a target instance"); return; }
        this._targetInstance = inst;
        if (!(await Credentials.ensure(inst))) return;
        this._targetConnected = true;
        if (this._sourceInstance && this._targetInstance === this._sourceInstance) {
          Toast.info("Source and target are the same instance");
        }
        const cubeNames = Object.keys(this._transferredCubes);
        if (cubeNames.length > 0) {
          await this._fetchTargetOrders(cubeNames);
        }
        Toast.success(`Connected to target: ${inst}`);
        this.mount();
      }}, "Connect");
      connRow.appendChild(connectBtn);
      panel.appendChild(connRow);

      const dropZone = el("div", { className: "transfer-drop-zone" });
      dropZone.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; dropZone.classList.add("drag-over"); });
      dropZone.addEventListener("dragleave", () => { dropZone.classList.remove("drag-over"); });
      dropZone.addEventListener("drop", async (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        try {
          const cubes = JSON.parse(e.dataTransfer.getData("text/plain"));
          cubes.forEach(c => {
            if (!this._transferredCubes[c.cube_name]) {
              this._transferredCubes[c.cube_name] = { proposed: c.storage_order, current: null };
            }
          });
          if (this._targetConnected) {
            await this._fetchTargetOrders(cubes.map(c => c.cube_name));
          }
          this.mount();
        } catch (err) {
          Toast.error("Invalid drop data");
        }
      });

      const transferredNames = Object.keys(this._transferredCubes);
      if (transferredNames.length === 0) {
        dropZone.appendChild(el("div", { className: "transfer-drop-placeholder" },
          el("span", { html: Icons.arrowRight, style: "opacity:0.3" }),
          el("div", { className: "text-secondary text-sm mt-2" }, "Drag cubes here from the source list"),
        ));
      } else {
        transferredNames.forEach(cubeName => {
          const cube = this._transferredCubes[cubeName];
          const card = el("div", { className: "transfer-target-card" });

          const header = el("div", { className: "flex items-center justify-between mb-2" });
          header.appendChild(el("div", { className: "font-medium text-sm" }, cubeName));
          header.appendChild(el("button", { className: "btn btn-ghost btn-sm", html: Icons.x, onClick: () => {
            delete this._transferredCubes[cubeName];
            this.mount();
          }}));
          card.appendChild(header);

          if (this._targetMissing.includes(cubeName)) {
            card.appendChild(el("div", { className: "text-warning text-xs mb-1" }, "Cube not found on target instance"));
          }

          const comparison = el("div", { className: "transfer-order-comparison" });

          const currentCol = el("div", { className: "transfer-order-col" });
          currentCol.appendChild(el("div", { className: "text-xs text-tertiary mb-1" }, "Current (Target)"));
          if (cube.current) {
            cube.current.forEach(dim => currentCol.appendChild(el("div", { className: "transfer-dim-tag dim-current" }, dim)));
          } else {
            currentCol.appendChild(el("div", { className: "text-xs text-tertiary" }, this._targetConnected ? "Loading..." : "Connect target to see"));
          }
          comparison.appendChild(currentCol);

          comparison.appendChild(el("div", { className: "transfer-order-arrow", html: Icons.arrowRight }));

          const proposedCol = el("div", { className: "transfer-order-col" });
          proposedCol.appendChild(el("div", { className: "text-xs text-tertiary mb-1" }, "Proposed (Source)"));
          cube.proposed.forEach((dim, i) => {
            const changed = cube.current && cube.current[i] !== dim;
            proposedCol.appendChild(el("div", { className: `transfer-dim-tag dim-proposed${changed ? " dim-changed" : ""}` }, dim));
          });
          comparison.appendChild(proposedCol);

          card.appendChild(comparison);
          dropZone.appendChild(card);
        });
      }
      panel.appendChild(dropZone);

      if (transferredNames.length > 0) {
        const actionsRow = el("div", { className: "flex gap-2 mt-3 flex-wrap" });

        const applyBtn = el("button", { id: "transfer-apply-all", className: "btn btn-primary", onClick: () => {
          if (!this._targetConnected) { Toast.error("Connect to target instance first"); return; }
          const orders = {};
          Object.entries(this._transferredCubes).forEach(([name, cube]) => {
            if (!this._targetMissing.includes(name)) orders[name] = cube.proposed;
          });
          const names = Object.keys(orders);
          if (names.length === 0) { Toast.error("No valid cubes to apply"); return; }
          const unchanged = names.filter(name => {
            const current = this._transferredCubes[name].current;
            return current && JSON.stringify(current) === JSON.stringify(orders[name]);
          });
          const target = this._targetInstance;
          Modal.confirm(
            `Apply the storage order to ${names.length - unchanged.length} cube(s) on '${target}'? ` +
            "Each one is rebuilt in place on the server and is blocked while it runs." +
            (unchanged.length ? ` ${unchanged.length} already match and will be skipped.` : ""),
            async () => {
              try {
                const resp = await Api.transferApply(target, Credentials.get(target), orders);
                this._watchApply(resp.job_id, target, names.length);
                Sidebar.updateActivityMonitor();
              } catch (err) {
                Toast.error(err.message);
              }
            });
        }}, "Apply All");
        applyBtn.disabled = !!(this._jobId && !this._applyDone);
        actionsRow.appendChild(applyBtn);

        const exportBtn = el("button", { className: "btn btn-secondary", onClick: async () => {
          const orders = {};
          Object.entries(this._transferredCubes).forEach(([name, cube]) => {
            orders[name] = cube.proposed;
          });
          try {
            const resp = await Api.transferExport(this._targetInstance || this._sourceInstance || "", orders);
            Toast.success(`Exported ${resp.files.length} file(s) to ${resp.folder}`);
          } catch (err) {
            Toast.error(err.message);
          }
        }}, el("span", { html: Icons.download }), " Export to Folder");
        actionsRow.appendChild(exportBtn);

        actionsRow.appendChild(el("button", { className: "btn btn-ghost", onClick: () => {
          this._transferredCubes = {};
          this._targetMissing = [];
          this.mount();
        }}, "Clear All"));

        panel.appendChild(actionsRow);
      }
    },

    async _fetchTargetOrders(cubeNames) {
      try {
        const data = await Api.transferTargetOrders(this._targetInstance, Credentials.get(this._targetInstance), cubeNames);
        Object.entries(data.orders || {}).forEach(([name, order]) => {
          if (this._transferredCubes[name]) {
            this._transferredCubes[name].current = order;
          }
        });
        this._targetMissing = [...new Set([...this._targetMissing, ...(data.missing || [])])];
      } catch (err) {
        Toast.error(`Failed to fetch target orders: ${err.message}`);
      }
    },

    // ---- Apply: one row per cube, as the server reports it ----
    _watchApply(jobId, target, total) {
      if (this._unsubApply) this._unsubApply();
      this._jobId = jobId;
      this._applyTarget = target;
      this._applyTotal = total;
      this._applyResults = [];
      this._applyDone = null;
      StreamManager.connect(jobId);
      // Kept across navigation: the rows are held here, and the panel is redrawn
      // only while the page is on screen.
      this._unsubApply = StreamManager.subscribe(jobId, (event, data) => {
        if (event === "log") return;
        if (event === "progress") {
          this._applyResults.push(data);
        } else {
          this._applyDone = event === "complete" ? data : { status: "failed", error: data && data.error };
          const failed = this._applyResults.filter(r => r.status === "failed").length;
          if (this._applyDone.status === "completed") Toast.success(`Storage order applied on '${target}'`);
          else if (this._applyDone.status === "cancelled") Toast.info("Sync stopped");
          else Toast.error(failed ? `${failed} cube(s) failed on '${target}' — see the list` : `Sync failed: ${this._applyDone.error || "unknown error"}`);
          Sidebar.updateActivityMonitor();
        }
        this._renderApplyPanel($("#transfer-apply"));
      });
      this._renderApplyPanel($("#transfer-apply"));
    },

    _renderApplyPanel(container) {
      if (!container) return;
      // Apply All is drawn with the rest of the page; the panel is redrawn on every
      // sync event, so it keeps the button's state in step with the job.
      const applyAll = $("#transfer-apply-all");
      if (applyAll) applyAll.disabled = !!(this._jobId && !this._applyDone);
      container.innerHTML = "";
      if (!this._jobId) return;
      const done = this._applyDone;
      const count = status => this._applyResults.filter(r => r.status === status).length;
      const card = el("div", { className: "card mt-4" });
      const header = el("div", { className: "card-header" });
      header.appendChild(el("div", { className: "card-title" }, `Applied to '${this._applyTarget}'`));
      header.appendChild(el("span", { className: "text-sm text-secondary" },
        `${count("applied")} applied · ${count("skipped")} skipped · ${count("failed")} failed — ` +
        (done ? done.status : `${this._applyResults.length} of ${this._applyTotal}`)));
      if (!done) {
        const stopBtn = el("button", { className: "btn btn-danger btn-sm" }, "Stop after current cube");
        stopBtn.addEventListener("click", async () => {
          stopBtn.disabled = true;
          try { await Api.cancelJob(this._jobId); } catch (err) { Toast.error("Stop failed: " + err.message); stopBtn.disabled = false; }
        });
        header.appendChild(stopBtn);
      }
      card.appendChild(header);
      const badge = { applied: "badge-success", skipped: "badge-neutral", failed: "badge-error" };
      card.appendChild(createTable({
        columns: [
          { key: "index", label: "#", align: "right" },
          { key: "cube", label: "Cube" },
          { key: "status", label: "Result", render: r => el("span", { className: `badge ${badge[r.status]}` }, r.status) },
          { key: "error", label: "Detail", value: r => r.error || "" },
        ],
        data: this._applyResults,
        filterable: false,
        emptyMessage: "Waiting for the first cube…",
      }).el);
      container.appendChild(card);
    },

    unmount() {},
  };

  // ==================================================================
  // Page: Optimize DB — reorder every cube on an instance by leaf-element count
  // ==================================================================
  // Skip reasons arrive as codes; these are the page's wording for SKIP_LABELS in optimize_db.py.
  const OPTDB_SKIP_LABELS = {
    excluded: "Excluded in the run settings",
    empty: "No memory in use",
    below_min_ram: "Below minimum cube size",
    too_few_dimensions: "Fewer than 3 dimensions",
    string_elements: "Has string elements",
    multiple_string_dims: "More than one dimension with strings",
    already_in_target_order: "Already in target order",
  };

  const OPTDB_RUN_STATUS = {
    running: "Running",
    completed: "Completed",
    stopped_time_limit: "Stopped — time limit",
    cancelled: "Stopped — cancelled",
    failed: "Failed",
  };

  const OPTDB_CUBE_BADGES = {
    pending: "badge-neutral", in_flight: "badge-info", done: "badge-success",
    reverted: "badge-warning", skipped: "badge-neutral", failed: "badge-error",
  };

  function optdbGb(bytes) {
    return ((bytes || 0) / 1073741824).toFixed(2) + " GB";
  }

  // A run can take hours — the shared formatDuration only reaches minutes.
  function optdbDuration(seconds) {
    const total = Math.floor(seconds || 0);
    if (total < 3600) return formatDuration(total);
    return `${Math.floor(total / 3600)}h ${Math.floor((total % 3600) / 60)}m`;
  }

  const OptimizeDbPage = {
    _instance: null,
    _timeLimitHours: 8,
    _order: "asc",
    _minCubeMb: 10,
    _stringPolicy: "skip_any",
    _revertOnRegression: true,
    _disableActiveChores: false,
    _excludeCubes: [],

    _plan: null,
    _planKey: null,
    _jobId: null,
    _unsubStream: null,
    _timer: createElapsedTimer(),
    _jobStartedAt: null,
    _planId: null,
    _queuePoll: null,

    mount() {
      const page = $("#page-optimize-db");
      page.innerHTML = "";
      if (!this._instance) this._instance = state.activeInstance || state.instances[0] || null;

      page.appendChild(el("div", { className: "page-header" },
        el("h1", { className: "page-title" }, "Optimize DB"),
        el("p", { className: "page-subtitle" },
          "Reorder the dimensions of every cube on an instance, one cube at a time, within a time limit you set"),
      ));

      page.appendChild(this._buildNotice());
      page.appendChild(this._buildForm());

      const planContainer = el("div", { id: "optdb-plan" });
      this._renderPlan(planContainer);
      page.appendChild(planContainer);

      const progressContainer = el("div", { id: "optdb-progress" });
      page.appendChild(progressContainer);

      const recoveryContainer = el("div", { id: "optdb-recovery" });
      page.appendChild(recoveryContainer);

      if (this._jobId) {
        this._renderProgress(progressContainer);
      } else {
        this._adoptActiveJob().then(job => {
          // The lookup is async — do not attach a stream to a page the user left.
          if (!job || !page.classList.contains("active")) return;
          this._jobId = job.job_id;
          this._jobStartedAt = job.started_at;
          this._planId = job.label;
          this._renderProgress($("#optdb-progress") || progressContainer);
        });
      }
      this._renderRecovery(recoveryContainer);
    },

    // ---- What this mode is, stated where the operator starts it ----
    _buildNotice() {
      const notice = el("div", { className: "optdb-notice mb-4" });
      notice.appendChild(el("div", { className: "optdb-notice-title" },
        el("span", { html: Icons.info }), "How this mode behaves"));
      const list = el("ul", { className: "optdb-notice-list" });
      [
        "This is a quick pass with one simple rule, not the full search the Optimize page runs. Each cube's dimensions are put in order of their leaf-element count, fewest first, and applied once. Nothing is tested against views or TI processes.",
        "The time limit is checked before each cube starts. While TM1 reorders a cube, the cube is locked and the reorder cannot be safely interrupted, so the run can end later than the limit by as long as its last cube takes.",
        "The memory saving shown is what TM1 reports for each cube. The instance's total memory only goes down after TM1 is restarted.",
        "Run it on an instance nobody is using, such as a copy of production. Restart TM1 afterwards, before optimizing individual cubes on the Optimize page.",
      ].forEach(text => list.appendChild(el("li", null, text)));
      notice.appendChild(list);
      return notice;
    },

    // ---- Instructions form ----
    _buildForm() {
      const card = el("div", { className: "card mb-4" });
      card.appendChild(el("div", { className: "card-title mb-4" }, "Run settings"));

      const row1 = el("div", { className: "form-row-3" });

      const instGroup = el("div", { className: "form-group" });
      instGroup.appendChild(el("label", { className: "form-label", for: "optdb-instance" }, "Instance"));
      const instSelect = el("select", { className: "form-input", id: "optdb-instance" });
      instSelect.appendChild(el("option", { value: "" }, "Select instance..."));
      state.instances.forEach(name => instSelect.appendChild(el("option", { value: name }, name)));
      instSelect.value = this._instance || "";
      instSelect.addEventListener("change", () => { this._instance = instSelect.value || null; });
      instGroup.appendChild(instSelect);
      row1.appendChild(instGroup);

      const limitGroup = el("div", { className: "form-group" });
      limitGroup.appendChild(el("label", { className: "form-label", for: "optdb-time-limit" }, "Time limit (hours)"));
      const limitInput = el("input", {
        type: "number", className: "form-input", id: "optdb-time-limit",
        min: "0.25", step: "0.25", value: String(this._timeLimitHours),
      });
      limitInput.addEventListener("change", () => {
        const value = parseFloat(limitInput.value);
        this._timeLimitHours = isNaN(value) ? this._timeLimitHours : value;
        limitInput.value = String(this._timeLimitHours);
      });
      limitGroup.appendChild(limitInput);
      limitGroup.appendChild(el("div", { className: "form-hint" }, "Checked before each cube — a cube already being reordered always finishes"));
      row1.appendChild(limitGroup);

      const minGroup = el("div", { className: "form-group" });
      minGroup.appendChild(el("label", { className: "form-label", for: "optdb-min-mb" }, "Minimum cube size (MB)"));
      const minInput = el("input", {
        type: "number", className: "form-input", id: "optdb-min-mb",
        min: "0", step: "1", value: String(this._minCubeMb),
      });
      minInput.addEventListener("change", () => {
        const value = parseFloat(minInput.value);
        this._minCubeMb = isNaN(value) ? this._minCubeMb : value;
        minInput.value = String(this._minCubeMb);
      });
      minGroup.appendChild(minInput);
      minGroup.appendChild(el("div", { className: "form-hint" }, "Smaller cubes are skipped — reordering them costs more time than it saves memory"));
      row1.appendChild(minGroup);
      card.appendChild(row1);

      const row2 = el("div", { className: "form-row-3" });

      const orderGroup = el("div", { className: "form-group" });
      orderGroup.appendChild(el("label", { className: "form-label", for: "optdb-order" }, "Cube order"));
      const orderSelect = el("select", { className: "form-input", id: "optdb-order" },
        el("option", { value: "asc" }, "Smallest → largest"),
        el("option", { value: "desc" }, "Largest → smallest"),
      );
      orderSelect.value = this._order;
      orderSelect.addEventListener("change", () => { this._order = orderSelect.value; });
      orderGroup.appendChild(orderSelect);
      orderGroup.appendChild(el("div", { className: "form-hint" }, "The order cubes are processed in — not the dimension order"));
      row2.appendChild(orderGroup);

      const policyGroup = el("div", { className: "form-group" });
      policyGroup.appendChild(el("label", { className: "form-label", for: "optdb-string-policy" }, "String dimensions"));
      const policySelect = el("select", { className: "form-input", id: "optdb-string-policy" },
        el("option", { value: "skip_any" }, "Skip any cube with string elements"),
        el("option", { value: "pin_last" }, "Keep the string dimension last"),
      );
      policySelect.value = this._stringPolicy;
      policySelect.addEventListener("change", () => { this._stringPolicy = policySelect.value; });
      policyGroup.appendChild(policySelect);
      policyGroup.appendChild(el("div", { className: "form-hint" }, "Cubes with strings in more than one dimension are always skipped"));
      row2.appendChild(policyGroup);

      const flagsGroup = el("div", { className: "form-group" });
      flagsGroup.appendChild(el("label", { className: "form-label" }, "Safety"));
      const revertLabel = el("label", { className: "checkbox-label", style: "cursor:pointer;display:flex;align-items:center;gap:6px" });
      const revertCb = el("input", { type: "checkbox" });
      revertCb.checked = this._revertOnRegression;
      revertCb.addEventListener("change", () => { this._revertOnRegression = revertCb.checked; });
      revertLabel.appendChild(revertCb);
      revertLabel.appendChild(el("span", { className: "text-sm" }, "Revert a cube that ends up using more memory"));
      flagsGroup.appendChild(revertLabel);
      const choresLabel = el("label", { className: "checkbox-label", style: "cursor:pointer;display:flex;align-items:center;gap:6px;margin-top:6px" });
      const choresCb = el("input", { type: "checkbox" });
      choresCb.checked = this._disableActiveChores;
      choresCb.addEventListener("change", () => { this._disableActiveChores = choresCb.checked; });
      choresLabel.appendChild(choresCb);
      choresLabel.appendChild(el("span", { className: "text-sm" }, "Disable active chores for the run"));
      flagsGroup.appendChild(choresLabel);
      flagsGroup.appendChild(el("div", { className: "form-hint" }, "Re-activated when the run ends, even if it fails. If OptimusPy itself is killed they stay off; re-enable them under Previous runs"));
      row2.appendChild(flagsGroup);
      card.appendChild(row2);

      card.appendChild(this._buildExcludeGroup());

      const actions = el("div", { className: "flex gap-2 mt-4 items-center" });
      const buildBtn = el("button", { className: "btn btn-secondary", id: "optdb-plan-btn" }, "Build plan");
      buildBtn.addEventListener("click", () => this._buildPlan(buildBtn));
      actions.appendChild(buildBtn);
      const runBtn = el("button", { className: "btn btn-primary", id: "optdb-run-btn" }, "Run plan");
      runBtn.disabled = !this._plan || !(this._plan.cubes || []).length;
      runBtn.addEventListener("click", () => this._runPlan(runBtn));
      actions.appendChild(runBtn);
      actions.appendChild(el("span", { className: "text-xs text-tertiary" },
        "Building a plan only reads from TM1. Running it reorders the cubes on the server."));
      card.appendChild(actions);

      return card;
    },

    _buildExcludeGroup() {
      const group = el("div", { className: "form-group" });
      group.appendChild(el("label", { className: "form-label", for: "optdb-exclude-input" }, "Exclude cubes"));
      const row = el("div", { className: "flex gap-2" });
      const input = el("input", {
        type: "text", className: "form-input", id: "optdb-exclude-input",
        placeholder: "Cube name or pattern, e.g. Sales*",
      });
      const chips = el("div", { className: "optdb-chips mt-2" });
      const add = () => {
        const value = input.value.trim();
        if (!value) return;
        if (!this._excludeCubes.includes(value)) this._excludeCubes.push(value);
        input.value = "";
        this._renderChips(chips);
      };
      input.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); add(); }
      });
      row.appendChild(input);
      row.appendChild(el("button", { className: "btn btn-secondary btn-sm", onClick: add },
        el("span", { html: Icons.plus }), "Add"));
      group.appendChild(row);
      group.appendChild(el("div", { className: "form-hint" }, "Case-insensitive; * and ? wildcards are supported"));
      this._renderChips(chips);
      group.appendChild(chips);
      return group;
    },

    _renderChips(container) {
      container.innerHTML = "";
      if (this._excludeCubes.length === 0) {
        container.appendChild(el("span", { className: "text-xs text-tertiary" }, "No cubes excluded"));
        return;
      }
      this._excludeCubes.forEach(name => {
        const remove = el("button", {
          className: "optdb-chip-remove", "aria-label": `Remove ${name}`, html: Icons.x,
          onClick: () => {
            this._excludeCubes = this._excludeCubes.filter(c => c !== name);
            this._renderChips(container);
          },
        });
        container.appendChild(el("span", { className: "optdb-chip" }, name, remove));
      });
    },

    _instructions() {
      return {
        time_limit_hours: this._timeLimitHours,
        order: this._order,
        exclude_cubes: this._excludeCubes,
        min_cube_mb: this._minCubeMb,
        string_policy: this._stringPolicy,
        revert_on_regression: this._revertOnRegression,
        disable_active_chores: this._disableActiveChores,
      };
    },

    // What the plan on screen was built from. Running is refused once this has
    // changed, so a run is always the plan the operator is looking at.
    _planKeyNow() {
      return JSON.stringify([this._instance, this._instructions()]);
    },

    // ---- Plan ----
    async _buildPlan(btn) {
      if (!this._instance) { Toast.error("Select an instance"); return; }
      if (!(await Credentials.ensure(this._instance))) return;
      btn.disabled = true;
      btn.textContent = "Building plan\u2026";
      try {
        const plan = await Api.optimizeDbPlan(this._instance, Credentials.get(this._instance), this._instructions());
        this._plan = plan;
        this._planKey = this._planKeyNow();
        this._renderPlan($("#optdb-plan"));
        const runBtn = $("#optdb-run-btn");
        if (runBtn) runBtn.disabled = !(plan.cubes || []).length;
        Toast.success(`Plan ready — ${(plan.cubes || []).length} cube(s) to reorder`);
      } catch (err) {
        Toast.error(err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = "Build plan";
      }
    },

    _renderPlan(container) {
      if (!container) return;
      container.innerHTML = "";
      const plan = this._plan;
      if (!plan) {
        container.appendChild(el("div", { className: "empty-state" },
          el("div", { className: "empty-state-title" }, "No plan yet"),
          el("div", { className: "empty-state-text" },
            "Build a plan to see which cubes would be reordered, in what order, and which are skipped. Building a plan only reads from TM1 — nothing is changed."),
        ));
        return;
      }

      const cubes = plan.cubes || [];
      const skipped = plan.skipped || [];

      const stats = el("div", { className: "stat-cards" });
      const stat = (label, value, hint) => stats.appendChild(el("div", { className: "stat-card" },
        el("div", { className: "stat-card-label" }, label),
        el("div", { className: "stat-card-value" }, value),
        hint ? el("div", { className: "stat-card-hint" }, hint) : null,
      ));
      stat("Cube memory", optdbGb(plan.total_model_ram_bytes), "All cubes on the instance");
      stat("In this plan", optdbGb(plan.planned_ram_bytes), "Memory of the cubes to reorder");
      stat("Share", (plan.coverage_pct || 0).toFixed(1) + "%", "Of all cube memory, the part this plan reorders");
      stat("Cubes", String(cubes.length), `${skipped.length} skipped`);
      container.appendChild(stats);

      const queueCard = el("div", { className: "card mb-4" });
      queueCard.appendChild(el("div", { className: "card-title mb-2" },
        `Cubes to reorder (${cubes.length})`));
      queueCard.appendChild(el("div", { className: "text-sm text-secondary mb-2" },
        `Plan ${plan.plan_id} — reordered top to bottom, ${plan.options && plan.options.order === "desc" ? "largest cube first" : "smallest cube first"}.`));
      if (cubes.length === 0) {
        queueCard.appendChild(el("div", { className: "text-secondary text-sm" }, "No cube qualifies — nothing would be reordered."));
      } else {
        const rows = cubes.map((c, i) => Object.assign({ position: i + 1 }, c));
        const tbl = createTable({
          columns: [
            { key: "position", label: "#", align: "right" },
            { key: "cube", label: "Cube", render: r => el("span", { className: "font-medium" }, r.cube) },
            { key: "ram_bytes", label: "Memory", align: "right", value: r => formatBytes(r.ram_bytes || 0), sortValue: r => r.ram_bytes || 0 },
            {
              key: "target_order", label: "New dimension order", sortable: false,
              render: r => el("span", { className: "optdb-order" }, (r.target_order || []).join(" \u2192 ")),
            },
          ],
          data: rows,
        });
        queueCard.appendChild(tbl.el);
      }
      container.appendChild(queueCard);

      if (skipped.length > 0) container.appendChild(this._buildSkippedCard(skipped));
      container.appendChild(this._buildChoresCard(plan));
    },

    _buildSkippedCard(skipped) {
      const groups = {};
      skipped.forEach(s => {
        const reason = s.reason || "unknown";
        (groups[reason] = groups[reason] || []).push(s);
      });
      const card = el("div", { className: "card mb-4" });
      card.appendChild(el("div", { className: "card-title mb-2" }, `Skipped cubes (${skipped.length})`));
      Object.keys(groups).sort().forEach(reason => {
        const entries = groups[reason];
        const group = el("div", { className: "optdb-skip-group" });
        group.appendChild(el("div", { className: "optdb-skip-reason" },
          el("span", null, OPTDB_SKIP_LABELS[reason] || reason),
          el("span", { className: "badge badge-neutral" }, String(entries.length)),
        ));
        const chips = el("div", { className: "optdb-chips" });
        entries.forEach(entry => chips.appendChild(el("span", { className: "optdb-chip" },
          `${entry.cube} · ${formatBytes(entry.ram_bytes || 0)}`)));
        group.appendChild(chips);
        card.appendChild(group);
      });
      return card;
    },

    _buildChoresCard(plan) {
      const chores = plan.active_chores || [];
      const willDisable = !!(plan.options && plan.options.disable_active_chores);
      const card = el("div", { className: "card mb-4" });
      card.appendChild(el("div", { className: "card-title mb-2" }, `Active chores (${chores.length})`));
      card.appendChild(el("div", { className: "text-sm text-secondary mb-2" }, willDisable
        ? "These chores are deactivated when the run starts and re-activated when it ends, even if it fails. If OptimusPy itself is killed they stay off; re-enable them under Previous runs below."
        : "These chores keep running during the run. Tick 'Disable active chores for the run' to switch exactly these off while it runs."));
      if (chores.length === 0) {
        card.appendChild(el("div", { className: "text-secondary text-sm" }, "No chore is active on this instance."));
      } else {
        const chips = el("div", { className: "optdb-chips" });
        chores.forEach(name => chips.appendChild(el("span", { className: "optdb-chip" }, name)));
        card.appendChild(chips);
      }
      return card;
    },

    // ---- Run ----
    _runPlan(btn) {
      const plan = this._plan;
      if (!plan) return;
      if (this._planKeyNow() !== this._planKey) {
        Toast.error("The run settings changed after this plan was built — build the plan again before running it");
        return;
      }
      this._confirmRun(plan.instance, plan.plan_id,
        `Reorder ${(plan.cubes || []).length} cube(s) on '${plan.instance}' exactly as listed in plan ${plan.plan_id}? Each cube is locked on the server while TM1 reorders it.`,
        btn);
    },

    // Start plan `planId`: a fresh run, or the continuation of one already on
    // disk — the server decides which. Shared by Run plan and every Resume button.
    _confirmRun(instance, planId, message, btn) {
      Modal.confirm(message, async () => {
        if (!(await Credentials.ensure(instance))) return;
        const label = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Starting…";
        try {
          const resp = await Api.optimizeDbRun(instance, Credentials.get(instance), planId);
          this._jobId = resp.job_id;
          this._jobStartedAt = resp.started_at;
          this._planId = planId;
          StreamManager.connect(resp.job_id);
          this._renderProgress($("#optdb-progress"));
          Sidebar.updateActivityMonitor();
          Toast.success(`Optimize DB run started (${resp.job_id})`);
        } catch (err) {
          Toast.error(err.message);
        } finally {
          btn.disabled = false;
          btn.textContent = label;
        }
      });
    },

    async _adoptActiveJob() {
      try {
        const data = await Api.getJobs();
        const jobs = (data.jobs || []).filter(j => j.mode === "optimize-db");
        return jobs.find(j => j.status === "running") || jobs[0] || null;
      } catch {
        return null;
      }
    },

    // Stop everything that follows the run on screen: the stream subscription, the
    // timer and the queue poll. Called before the progress card is drawn again,
    // when the run ends, and when the page is left.
    _releaseProgress() {
      if (this._unsubStream) { this._unsubStream(); this._unsubStream = null; }
      this._timer.stop();
      if (this._queuePoll) { clearInterval(this._queuePoll); this._queuePoll = null; }
    },

    // One row per planned cube, in plan order, read from the run artifact the
    // server rewrites after every cube.
    _renderQueue(container, run) {
      container.innerHTML = "";
      const cubes = Object.entries(run.cubes || {});
      const finished = cubes.filter(([, c]) => ["done", "reverted", "skipped", "failed"].includes(c.status)).length;
      let budget = "";
      if (run.deadline_at && !run.finished_at) {
        const left = run.deadline_at - Date.now() / 1000;
        budget = left > 0 ? ` · ${optdbDuration(left)} of the time limit left`
          : " · time limit reached — stops after the cube being reordered";
      }
      container.appendChild(el("div", { className: "text-sm text-secondary mb-2" },
        `${finished} of ${cubes.length} cubes finished${budget}`));
      container.appendChild(createTable({
        columns: [
          { key: "position", label: "#", align: "right" },
          { key: "cube", label: "Cube" },
          { key: "status", label: "Status", render: r => el("span",
            { className: `badge ${OPTDB_CUBE_BADGES[r.status] || "badge-neutral"}` }, r.status === "in_flight" ? "reordering" : r.status) },
          { key: "pct_change", label: "RAM change", align: "right",
            value: r => r.pct_change == null ? "—" : `${r.pct_change > 0 ? "+" : ""}${r.pct_change.toFixed(2)}%` },
          { key: "duration_s", label: "Took", align: "right",
            value: r => r.duration_s == null ? "—" : optdbDuration(r.duration_s) },
        ],
        data: cubes.map(([cube, c], i) => Object.assign({ position: i + 1, cube }, c)),
        filterable: false,
      }).el);
    },

    _renderProgress(container) {
      if (!container) return;
      this._releaseProgress();
      container.innerHTML = "";
      if (!this._jobId) return;

      const card = el("div", { className: "card mb-4" });
      card.appendChild(el("div", { className: "card-title mb-2" }, "Run progress"));

      const statusBar = el("div", { className: "terminal-status" });
      const statusDot = el("span", { className: "status-dot" });
      const statusText = el("span", { className: "text-sm font-medium" }, "Idle");
      const timerEl = el("span", { className: "terminal-timer" }, "00:00");
      const stopBtn = el("button", { className: "btn btn-danger btn-sm", style: "display:none;margin-left:auto" },
        "Stop after current cube");
      stopBtn.addEventListener("click", async () => {
        stopBtn.disabled = true;
        stopBtn.textContent = "Stopping\u2026";
        try {
          await Api.cancelJob(this._jobId);
          Toast.info("Stopping — the cube being reordered finishes first");
        } catch (e) {
          Toast.error("Cancel failed: " + e.message);
          stopBtn.disabled = false;
          stopBtn.textContent = "Stop after current cube";
        }
      });
      statusBar.appendChild(statusDot);
      statusBar.appendChild(statusText);
      statusBar.appendChild(timerEl);
      statusBar.appendChild(stopBtn);
      card.appendChild(statusBar);
      const queue = el("div", { className: "mb-4" });
      card.appendChild(queue);
      const refreshQueue = async () => {
        if (!this._planId) return;
        try {
          this._renderQueue(queue, (await Api.optimizeDbRunState(this._planId)).run);
        } catch { /* the run artifact exists once the run has started */ }
      };
      refreshQueue();

      const terminal = createTerminal();
      card.appendChild(terminal.el);
      const summary = el("div", { className: "mt-4" });
      card.appendChild(summary);
      container.appendChild(card);

      StreamManager.getLogs(this._jobId).forEach(log => terminal.append(log));

      const sseStatus = StreamManager.getStatus(this._jobId);
      if (sseStatus === "running" || sseStatus === "unknown") {
        statusDot.classList.add("running");
        statusText.textContent = "Running";
        stopBtn.style.display = "";
        this._timer.start(timerEl, this._jobStartedAt || Date.now() / 1000);
        StreamManager.connect(this._jobId);
        this._queuePoll = setInterval(refreshQueue, 5000);
      } else if (sseStatus === "completed") {
        statusDot.classList.add("completed");
        statusText.textContent = "Finished";
      } else {
        statusDot.classList.add("failed");
        statusText.textContent = sseStatus === "cancelled" ? "Cancelled" : "Failed";
      }

      this._unsubStream = StreamManager.subscribe(this._jobId, (event, data) => {
        if (event === "log") {
          terminal.append(data);
          return;
        }
        stopBtn.style.display = "none";
        this._releaseProgress(); refreshQueue();
        Sidebar.updateActivityMonitor();
        if (event === "complete") {
          const run = (data && data.run) || null;
          const status = run && run.status;
          // With no qualifying cube the core never opens a run and hands back
          // the plan instead — a clean no-op, not a failure.
          const nothingToRun = !!run && !status;
          const ok = nothingToRun || !!(data && data.success);
          statusDot.className = `status-dot ${ok ? "completed" : "failed"}`;
          statusText.textContent = nothingToRun ? "Nothing to run" : (OPTDB_RUN_STATUS[status] || "Finished");
          this._renderRunSummary(summary, run);
          this._renderRecovery($("#optdb-recovery"));
          if (nothingToRun) Toast.info("No cube qualified — nothing was reordered");
          else if (data && data.success) Toast.success("Optimize DB finished — restart TM1 to see the memory saving");
          else Toast.warning(`Optimize DB ended: ${OPTDB_RUN_STATUS[status] || status || "unknown"}`);
        } else if (event === "cancelled") {
          statusDot.className = "status-dot failed";
          statusText.textContent = "Cancelled";
          Toast.info("Optimize DB run cancelled");
        } else if (event === "error_event") {
          statusDot.className = "status-dot failed";
          statusText.textContent = "Failed";
          this._renderRecovery($("#optdb-recovery"));
          Toast.error("Optimize DB failed: " + ((data && data.error) || "Unknown error"));
        }
      });
    },

    _renderRunSummary(container, run) {
      container.innerHTML = "";
      if (!run) return;
      if (!run.status) {
        container.appendChild(el("div", { className: "text-sm text-secondary" },
          "No cube qualified under these run settings — nothing was reordered."));
        return;
      }
      const totals = run.totals || {};
      const stats = el("div", { className: "stat-cards" });
      const stat = (label, value, hint) => stats.appendChild(el("div", { className: "stat-card" },
        el("div", { className: "stat-card-label" }, label),
        el("div", { className: "stat-card-value" }, value),
        hint ? el("div", { className: "stat-card-hint" }, hint) : null,
      ));
      stat("Outcome", OPTDB_RUN_STATUS[run.status] || run.status || "—", `Plan ${run.plan_id || "—"}`);
      stat("Reordered", String(totals.cubes_reordered || 0),
        `${totals.cubes_reverted || 0} reverted · ${totals.cubes_failed || 0} failed · ${totals.cubes_pending || 0} not started`);
      stat("Expected saving", formatBytes(totals.bytes_saved || 0), "Visible after a TM1 restart");
      stat("Average change", (totals.mean_pct_change || 0).toFixed(2) + "%", "Per reordered cube");
      stat("Elapsed", optdbDuration(totals.elapsed_s || 0), `Limit ${(run.options && run.options.time_limit_hours) || "—"}h — checked before each cube`);
      container.appendChild(stats);

      const chores = run.chores || {};
      if (chores.state === "disabled") {
        container.appendChild(this._buildChoreWarning({
          plan_id: run.plan_id, instance: run.instance,
        }));
      } else if (chores.state === "restored") {
        container.appendChild(el("div", { className: "text-sm text-secondary" },
          `Re-activated ${(chores.deactivated || []).length} chore(s).`));
      }
    },

    // ---- Recovery ----
    async _renderRecovery(container) {
      if (!container) return;
      container.innerHTML = "";
      const card = el("div", { className: "card" });
      const header = el("div", { className: "card-header" });
      header.appendChild(el("div", { className: "card-title" }, "Previous runs"));
      header.appendChild(el("button", {
        className: "btn btn-ghost btn-sm",
        onClick: () => this._renderRecovery(container),
      }, el("span", { html: Icons.refresh }), "Refresh"));
      card.appendChild(header);
      const body = el("div");
      body.appendChild(el("div", { className: "text-secondary text-sm" }, "Loading runs\u2026"));
      card.appendChild(body);
      container.appendChild(card);

      let runs;
      try {
        const data = await Api.optimizeDbRuns();
        runs = data.runs || [];
      } catch (err) {
        body.innerHTML = "";
        body.appendChild(el("div", { className: "text-warning text-sm" }, "Could not load runs: " + err.message));
        return;
      }

      body.innerHTML = "";
      if (runs.length === 0) {
        body.appendChild(el("div", { className: "text-secondary text-sm" },
          "No Optimize DB run has been recorded yet."));
        return;
      }

      runs.filter(r => r.chores_pending_restore)
        .forEach(r => body.appendChild(this._buildChoreWarning(r, container)));

      const tbl = createTable({
        columns: [
          {
            key: "status", label: "Status", render: r => {
              const cls = r.status === "completed" ? "badge-success"
                : r.status === "running" ? "badge-info"
                  : r.status === "stopped_time_limit" ? "badge-warning" : "badge-error";
              return el("span", { className: `badge ${cls}` }, OPTDB_RUN_STATUS[r.status] || r.status || "—");
            },
          },
          { key: "plan_id", label: "Plan", value: r => r.plan_id || "—" },
          { key: "instance", label: "Instance", value: r => r.instance || "—" },
          { key: "started_at", label: "Started", value: r => r.started_at ? formatDate(r.started_at) : "—" },
          {
            key: "cubes_done", label: "Cubes", align: "right",
            value: r => `${r.cubes_done || 0} / ${r.cubes_total || 0}`,
            sortValue: r => r.cubes_done || 0,
          },
          {
            key: "chores_state", label: "Chores", render: r => r.chores_pending_restore
              ? el("span", { className: "badge badge-warning" }, "disabled")
              : el("span", { className: "text-xs text-tertiary" }, r.chores_state || "untouched"),
          },
          {
            key: "resume", label: "", sortable: false,
            render: r => r.status === "completed" ? null : el("button", {
              className: "btn btn-ghost btn-sm",
              onClick: e => this._confirmRun(r.instance, r.plan_id,
                `Continue run ${r.plan_id} on '${r.instance}'? Cubes already done are checked and kept; the rest are reordered in the time left from the original limit.`,
                e.currentTarget),
            }, "Resume"),
          },
        ],
        data: runs,
        filterable: false,
      });
      body.appendChild(tbl.el);
    },

    _buildChoreWarning(run, recoveryContainer) {
      const banner = el("div", { className: "optdb-warning mb-2" });
      banner.appendChild(el("span", { className: "optdb-warning-icon", html: Icons.alertTriangle }));
      banner.appendChild(el("div", null,
        el("div", { className: "font-semibold" }, "Chores still disabled"),
        el("div", { className: "text-sm" },
          `Run ${run.plan_id || "—"} on '${run.instance || "—"}' deactivated chores and never re-activated them. They stay off until restored.`),
      ));
      const btn = el("button", { className: "btn btn-primary btn-sm", style: "margin-left:auto;flex-shrink:0" },
        "Re-enable chores");
      btn.addEventListener("click", async () => {
        if (!(await Credentials.ensure(run.instance))) return;
        btn.disabled = true;
        btn.textContent = "Re-enabling\u2026";
        try {
          const resp = await Api.optimizeDbRestoreChores(
            run.instance, Credentials.get(run.instance), run.plan_id);
          Toast.success(`Re-activated ${(resp.restored || []).length} chore(s)`);
          this._renderRecovery(recoveryContainer || $("#optdb-recovery"));
        } catch (err) {
          Toast.error(err.message);
          btn.disabled = false;
          btn.textContent = "Re-enable chores";
        }
      });
      banner.appendChild(btn);
      return banner;
    },

    unmount() {
      this._releaseProgress();
    },
  };

  const SettingsPage = {
    mount() {
      const page = $("#page-settings");
      page.innerHTML = "";

      page.appendChild(el("div", { className: "page-header" },
        el("h1", { className: "page-title" }, "Settings"),
      ));

      // Theme
      const themeCard = el("div", { className: "card mb-4" });
      themeCard.appendChild(el("div", { className: "card-title mb-4" }, "Appearance"));

      const themeRow = el("div", { className: "flex gap-2" });
      const themes = [
        { value: "system", label: "System", icon: Icons.monitor },
        { value: "light", label: "Light", icon: Icons.sun },
        { value: "dark", label: "Dark", icon: Icons.moon },
      ];
      themes.forEach(t => {
        const btn = el("button", {
          className: `btn ${state.theme === t.value ? "btn-primary" : "btn-secondary"}`,
          onClick: () => {
            Theme.set(t.value);
            this.mount(); // re-render
          },
        }, el("span", { html: t.icon }), t.label);
        themeRow.appendChild(btn);
      });
      themeCard.appendChild(themeRow);
      page.appendChild(themeCard);

      // TM1 Instances — the config.ini in use, read-only
      {
        const cfg = state.config;
        const instancesCard = el("div", { className: "card mb-4" });
        instancesCard.appendChild(el("div", { className: "card-title mb-4" }, "TM1 Instances"));

        const sourceLabels = { linked: "Linked file", default: "OptimusPy's own copy", flag: "Set by --config at launch" };
        instancesCard.appendChild(el("div", { className: "form-group" },
          el("div", { className: "form-label" }, "File in use"),
          el("div", { className: "flex items-center gap-2 flex-wrap" },
            el("code", { className: "config-path" }, cfg.config_path || ""),
            el("span", { className: "badge badge-neutral" }, sourceLabels[cfg.source] || ""),
          ),
        ));

        if (cfg.source !== "flag") instancesCard.appendChild(this._buildConfigChooser(cfg));

        if (cfg.error) {
          instancesCard.appendChild(el("div", { className: "config-error" }, cfg.error));
        } else if (state.instances.length === 0) {
          instancesCard.appendChild(el("div", { className: "text-secondary text-sm" }, cfg.source === "default"
            ? "There's no config.ini yet. Point to one above, or create config/config.ini from config/config.ini.example."
            : "This config.ini has no instances."));
        }

        const tabs = el("div", { className: "tabs" });
        const containers = {};
        const instances = cfg.error ? [] : state.instances;
        instances.forEach((name, i) => {
          const tab = el("div", {
            className: `tab${i === 0 ? " active" : ""}`,
            dataset: { instance: name },
            onClick: () => {
              tabs.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
              tab.classList.add("active");
              Object.values(containers).forEach(c => c.style.display = "none");
              containers[name].style.display = "block";
              if (!containers[name].dataset.loaded) {
                this._loadInstanceConfig(containers[name], name);
                containers[name].dataset.loaded = "true";
              }
            },
          });
          const isActive = name === state.activeInstance && state.connected;
          tab.appendChild(document.createTextNode(name));
          if (isActive) tab.appendChild(el("span", { className: "badge badge-success", style: "margin-left:8px;font-size:9px" }, "connected"));
          tabs.appendChild(tab);
          containers[name] = el("div", { style: i === 0 ? "" : "display:none" });
        });
        if (instances.length > 0) {
          instancesCard.appendChild(tabs);
          Object.values(containers).forEach(c => instancesCard.appendChild(c));
        }
        page.appendChild(instancesCard);

        // Load first instance config
        if (instances.length > 0) {
          const firstName = instances[0];
          this._loadInstanceConfig(containers[firstName], firstName);
          containers[firstName].dataset.loaded = "true";
        }
      }

      // Cache management
      const cacheCard = el("div", { className: "card mb-4" });
      cacheCard.appendChild(el("div", { className: "card-title mb-4" }, "Cache"));
      cacheCard.appendChild(el("p", { className: "text-secondary text-sm mb-3" }, "Scan results and cube intelligence are cached locally. Clear the cache to force fresh data from the server."));
      const clearCacheBtn = el("button", { className: "btn btn-secondary", onClick: () => {
        // Clear localStorage caches
        const keys = Object.keys(localStorage);
        keys.forEach(k => {
          if (k.startsWith("op-scan-") || k.startsWith("op-intel-")) {
            localStorage.removeItem(k);
          }
        });
        // Clear in-memory caches
        state.scanData = null;
        state.scanTimestamp = null;
        state.cubeMetadata = {};
        Toast.success("Cache cleared — scans and cube intelligence will be refreshed");
      }}, "Clear Cache");
      cacheCard.appendChild(clearCacheBtn);
      page.appendChild(cacheCard);

      // Folders the UI writes JSON to
      const foldersCard = el("div", { className: "card mb-4" });
      foldersCard.appendChild(el("div", { className: "card-title mb-4" }, "Folders"));
      const foldersList = el("div");
      foldersCard.appendChild(foldersList);
      foldersCard.appendChild(el("p", { className: "text-xs text-tertiary" }, "Files already saved stay in the old folder."));
      page.appendChild(foldersCard);

      // Saved configs management
      const configsCard = el("div", { className: "card" });
      configsCard.appendChild(el("div", { className: "card-title mb-4" }, "Saved Cube Configs"));
      const configsList = el("div", { id: "saved-configs-list" });
      configsCard.appendChild(configsList);
      page.appendChild(configsCard);
      this._loadSavedConfigs(configsList);
      this._loadFolders(foldersList, configsList);
    },

    async _loadFolders(container, configsList) {
      let folders;
      try {
        folders = await Api.getFolders();
      } catch (err) {
        container.appendChild(el("div", { className: "text-secondary text-sm" }, "Failed to load folders: " + err.message));
        return;
      }
      const rows = [
        { kind: "cube_configs", label: "Saved cube configs" },
        { kind: "exports", label: "Sync Order exports" },
      ];
      const change = async (body) => {
        try {
          await Api.setFolder(body);
        } catch (err) {
          Toast.error(err.message);
          return;
        }
        if (body.kind === "cube_configs") {
          configsList.innerHTML = "";
          this._loadSavedConfigs(configsList);
          Sidebar.loadSavedCubes();
        }
        container.innerHTML = "";
        this._loadFolders(container, configsList);
      };
      rows.forEach(({ kind, label }) => {
        const folder = folders[kind];
        const inputId = `folder-input-${kind}`;
        const input = el("input", { id: inputId, className: "form-input", type: "text", placeholder: "Path to a folder", style: "flex:1;min-width:200px;" });
        const controls = el("div", { className: "flex gap-2 flex-wrap items-center" },
          input,
          el("button", { className: "btn btn-secondary", onClick: () => change({ kind, path: input.value }) }, "Change folder"),
        );
        if (!folder.is_default) {
          controls.appendChild(el("button", { className: "btn btn-ghost", onClick: () => change({ kind, reset: true }) }, "Use default"));
        }
        container.appendChild(el("div", { className: "form-group" },
          el("label", { className: "form-label", for: inputId }, label),
          el("div", { className: "flex items-center gap-2 flex-wrap mb-2" },
            el("code", { className: "config-path" }, folder.path),
            folder.is_default ? el("span", { className: "text-xs text-tertiary" }, "(default)") : null,
          ),
          controls,
        ));
      });
    },

    // Point OptimusPy at another config.ini, by link or by copy. Hidden when
    // --config chose the file at launch.
    _buildConfigChooser(cfg) {
      const box = el("div", { className: "form-group" });
      box.appendChild(el("label", { className: "form-label", for: "config-path-input" }, "Change file"));
      const input = el("input", {
        id: "config-path-input", className: "form-input", type: "text",
        placeholder: "Path to a config.ini, or to the folder that holds one",
      });
      box.appendChild(input);
      const buttons = el("div", { className: "flex gap-2 mt-2 flex-wrap" },
        el("button", { className: "btn btn-secondary", onClick: () => this._switchConfig({ mode: "link", path: input.value }) }, "Link to this file"),
        el("button", { className: "btn btn-secondary", onClick: () => this._switchConfig({ mode: "copy", path: input.value }) }, "Copy into OptimusPy"),
      );
      if (cfg.source === "linked" && cfg.own_copy_exists) {
        buttons.appendChild(el("button", { className: "btn btn-ghost", onClick: () => this._switchConfig({ mode: "own" }) }, "Use OptimusPy's own copy"));
      }
      box.appendChild(buttons);
      box.appendChild(el("p", { className: "text-xs text-tertiary mt-2" },
        "A link follows the file, so changes made for RushTI or your scripts show up here. A copy is a snapshot, so later changes to the original don't."));
      return box;
    },

    async _switchConfig(body) {
      let data;
      try {
        data = await Api.setConfigSource(body);
      } catch (err) {
        if (err.status === 409 && err.data && err.data.exists) {
          Modal.open({
            title: "Replace config/config.ini?",
            body: el("p", { className: "text-sm" }, "OptimusPy's own copy is replaced with this file. The instances in the current copy are lost."),
            size: "sm",
            footer: [
              el("button", { className: "btn btn-secondary", onClick: () => Modal.close() }, "Cancel"),
              el("button", { className: "btn btn-danger", onClick: () => {
                Modal.close();
                this._switchConfig(Object.assign({}, body, { overwrite: true }));
              }}, "Replace"),
            ],
          });
        } else {
          Toast.error(err.message);
        }
        return;
      }
      // The same instance name can point at a different server in the new file,
      // so nothing from the old one carries over.
      state.activeInstance = null;
      state.connected = false;
      state.serverName = null;
      Credentials.clear();
      await Sidebar.loadInstances();
      Toast.success(`Reading ${data.config_path}`);
      this.mount();
    },

    async _loadInstanceConfig(container, instanceName) {
      try {
        const data = await Api.getInstance(instanceName);
        const fieldsContainer = el("div", { className: "instance-fields" });
        Object.entries(data.params || {}).forEach(([key, value]) => {
          fieldsContainer.appendChild(el("div", { className: "flex gap-2 items-center mb-2" },
            el("span", { className: "form-label", style: "flex:0.4;min-width:100px;margin:0;" }, key),
            value === ""
              ? el("span", { className: "text-sm text-tertiary", style: "flex:1;" }, "(empty)")
              : el("span", { className: "text-sm", style: "flex:1;word-break:break-all;" }, value),
          ));
        });
        container.appendChild(fieldsContainer);

        // Test Connection: the password typed in the Connect dialog, else config.ini's
        const testBtn = el("button", { className: "btn btn-secondary mt-2" }, "Test Connection");
        testBtn.addEventListener("click", async () => {
          testBtn.disabled = true;
          testBtn.textContent = "Testing...";
          try {
            const resp = await Api.connect(instanceName, Credentials.get(instanceName));
            Toast.success(`Connected to ${resp.server_name} (${resp.cube_count} cubes)`);
          } catch (err) {
            Toast.error(`Connection failed: ${err.message}`);
          } finally {
            testBtn.disabled = false;
            testBtn.textContent = "Test Connection";
          }
        });
        container.appendChild(testBtn);
      } catch (err) {
        container.appendChild(el("div", { className: "text-secondary text-sm" }, "Failed to load config: " + err.message));
      }
    },

    async _loadSavedConfigs(container) {
      try {
        const data = await Api.getSavedCubes();
        const configs = data.saved_cubes || [];
        // Reloaded after a delete or a folder change: replace the rows, don't add to them.
        container.innerHTML = "";

        if (configs.length === 0) {
          container.appendChild(el("div", { className: "text-secondary text-sm" }, "No saved configs."));
          return;
        }

        configs.forEach(c => {
          const row = el("div", { className: "flex items-center justify-between", style: "padding: 8px 0; border-bottom: 1px solid var(--border-secondary)" });
          const info = el("div");
          info.appendChild(el("div", { className: "font-medium text-sm" }, c.cube));
          info.appendChild(el("div", { className: "text-xs text-tertiary" }, `${c.instance} / ${c.mode} / ${c.filename}`));
          row.appendChild(info);
          const deleteBtn = el("button", { className: "btn btn-ghost btn-sm", "aria-label": "Delete config", html: Icons.trash, onClick: () => {
            Modal.confirm(`Delete config "${c.filename}"?`, async () => {
              try {
                await Api.deleteConfig(c.filename);
                Sidebar.loadSavedCubes();
                Toast.success("Config deleted");
                this._loadSavedConfigs(container);
              } catch (err) {
                Toast.error(err.message);
              }
            });
          }});
          row.appendChild(deleteBtn);
          container.appendChild(row);
        });
      } catch (err) {
        container.appendChild(el("div", { className: "text-secondary text-sm" }, "Failed to load configs: " + err.message));
      }
    },

    unmount() {},
  };

  // ==================================================================
  // JSON Syntax Highlighting
  // ==================================================================
  function syntaxHighlight(json) {
    return escapeHtml(json).replace(
      /("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      match => {
        let cls = "json-number";
        if (/^"/.test(match)) {
          cls = /:$/.test(match) ? "json-key" : "json-string";
        } else if (/true|false/.test(match)) {
          cls = "json-boolean";
        } else if (/null/.test(match)) {
          cls = "json-null";
        }
        return `<span class="${cls}">${match}</span>`;
      }
    );
  }

  // ==================================================================
  // Init
  // ==================================================================
  async function init() {
    Toast.init();
    Modal.init();
    Theme.init();
    Sidebar.init();

    // Register pages
    Router.register("home", HomePage);
    Router.register("nav", NavPage);
    Router.register("results", ResultsPage);
    Router.register("jobs", JobsPage);
    Router.register("settings", SettingsPage);
    Router.register("transfer", TransferPage);
    Router.register("optimize-db", OptimizeDbPage);

    // Load initial data (non-blocking — app should load even if API calls fail)
    try { await Sidebar.loadInstances(); } catch { /* will show empty instance list */ }
    Sidebar.loadSavedCubes();
    Sidebar.updateActivityMonitor();

    // Start router
    Router.init();
  }

  // Boot
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Public API (for debugging)
  return { state, Api, Router, Toast, Modal, Theme, StreamManager, Sidebar };
})();
