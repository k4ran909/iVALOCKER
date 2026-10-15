/* =====================================================================
   iVALOCKER - front end
   Talks to the Python backend through Eel:
     JS -> Python : eel.get_bootstrap / select_agent / arm / disarm / update_settings / reconnect / open_link
     Python -> JS : on_event(kind, payload)   kinds: state, log, locked, toast, agents
   ===================================================================== */

"use strict";

const PHASES = {
    idle:        { label: "IDLE",              hint: "Choose an agent on the left. It gets locked the instant agent select starts." },
    waiting:     { label: "WAITING FOR GAME",  hint: "Armed. Waiting for VALORANT to be running..." },
    armed:       { label: "ARMED",             hint: "Queue up. Your agent is locked the moment agent select starts." },
    match_found: { label: "MATCH FOUND",       hint: "Match found. Get ready..." },
    locking:     { label: "LOCKING",           hint: "Agent select detected. Locking in..." },
    locked:      { label: "LOCKED IN",         hint: "Locked in. Good luck, have fun!" },
    hovered:     { label: "HOVERED",           hint: "Agent selected (hover only). Lock it in yourself when you're ready." },
    failed:      { label: "FAILED",            hint: "Could not lock this time." },
};

const ROLE_ORDER = ["Duelist", "Initiator", "Controller", "Sentinel"];

const app = {
    agents: [],
    byName: new Map(),
    settings: {},
    state: null,
    filter: { role: "all", query: "" },
    selected: null,       // agent shown on stage (follows the backend target)
    connected: false,     // websocket to the backend
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ---------------------------------------------------------------------
   Startup
   --------------------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", async () => {
    bindStaticUI();
    watchBackendConnection();

    try {
        const boot = await eel.get_bootstrap()();
        app.settings = boot.settings;
        app.hotkeys = boot.hotkeys || { supported: false, actions: {} };
        $("#version").textContent = "v" + boot.version;
        setAgents(boot.agents);
        renderSettings();
        renderHotkeys();
        boot.logs.forEach(addLog);
        applyState(boot.state);
    } catch (err) {
        console.error(err);
        toast("error", "Startup failed", "Could not talk to the iVALOCKER backend.");
    }
});

eel.expose(on_event);
function on_event(kind, payload) {
    switch (kind) {
        case "state": applyState(payload); break;
        case "log": addLog(payload); break;
        case "locked": onLocked(payload); break;
        case "toast": toast(payload.level, payload.title, payload.text); break;
        case "agents": setAgents(payload); break;
        case "settings": app.settings = payload; renderSettings(); renderStage(); decorateCards(); break;
        case "hotkey": onHotkey(payload); break;
    }
}

function watchBackendConnection() {
    const ws = eel._websocket;
    if (!ws) return;
    ws.addEventListener("open", () => { app.connected = true; });
    ws.addEventListener("close", () => {
        app.connected = false;
        $("#offline-overlay").classList.remove("hidden");
    });
}

/* ---------------------------------------------------------------------
   Roster
   --------------------------------------------------------------------- */

function setAgents(agents) {
    app.agents = agents;
    app.byName = new Map(agents.map((a) => [a.name, a]));
    renderRoleFilters();
    renderRoster();
    renderBackupSelect();
    if (app.state) applyState(app.state);
}

function displayName(agent) {
    return agent.display || agent.name;
}

function roleIcon(role) {
    const id = ROLE_ORDER.includes(role) ? role : "Unknown";
    return `<svg><use href="#r-${id}"/></svg>`;
}

function renderRoleFilters() {
    const counts = {};
    app.agents.forEach((a) => { counts[a.role] = (counts[a.role] || 0) + 1; });
    const favCount = app.agents.filter((a) => isFavorite(a.name)).length;

    const chips = [
        { id: "all", label: "All", count: app.agents.length },
        { id: "fav", label: "Favorites", icon: '<svg><use href="#i-star"/></svg>', count: favCount },
        ...ROLE_ORDER.map((r) => ({ id: r, label: r, icon: roleIcon(r), count: counts[r] || 0 })),
    ];

    $("#role-filters").innerHTML = chips.map((c) => `
        <button class="chip ${app.filter.role === c.id ? "active" : ""}" data-role="${c.id}" role="tab">
            ${c.icon || ""}${c.label}<span class="count">${c.count}</span>
        </button>`).join("");
}

function renderRoster() {
    const grid = $("#agent-grid");
    grid.innerHTML = "";

    // Favorites first, then alphabetical.
    const sorted = [...app.agents].sort((a, b) =>
        (isFavorite(b.name) - isFavorite(a.name)) || a.name.localeCompare(b.name));

    sorted.forEach((agent, i) => {
        const card = document.createElement("button");
        card.className = "agent-card";
        card.dataset.name = agent.name;
        card.style.setProperty("--c", agent.color || "#ff4655");
        card.style.animationDelay = `${Math.min(i * 18, 400)}ms`;
        card.title = `${displayName(agent)} - ${agent.role}`;
        card.innerHTML = `
            <img src="${agent.banner}" alt="" loading="lazy" draggable="false">
            <span class="tag owned"><svg><use href="#i-lock"/></svg>NOT OWNED</span>
            <span class="tag backup">BACKUP</span>
            <span class="fav" title="Favorite (F)"><svg><use href="#i-star"/></svg></span>
            <span class="meta">
                <span class="name">${displayName(agent)}</span>
                <span class="role" title="${agent.role}">${roleIcon(agent.role)}</span>
            </span>`;
        grid.appendChild(card);
    });

    applyFilter();
    decorateCards();
}

/* Highlight selected / favorite / backup / owned state without rebuilding the grid. */
function decorateCards() {
    const state = app.state || {};
    const owned = state.owned ? new Set(state.owned) : null;
    $$(".agent-card").forEach((card) => {
        const agent = app.byName.get(card.dataset.name);
        if (!agent) return;
        card.classList.toggle("selected", app.selected === agent.name);
        card.classList.toggle("armed-target", !!state.armed && state.agent === agent.name);
        card.classList.toggle("is-fav", isFavorite(agent.name));
        card.classList.toggle("is-backup", app.settings.backup_agent === agent.name);
        card.classList.toggle("not-owned", !!owned && !owned.has(agent.uuid));
    });
}

function applyFilter() {
    const query = app.filter.query.trim().toLowerCase();
    const role = app.filter.role;
    let visible = $$(".agent-card").filter((card) => {
        const agent = app.byName.get(card.dataset.name);
        const roleOk = role === "all" || (role === "fav" ? isFavorite(agent.name) : agent.role === role);
        const text = `${agent.name} ${displayName(agent)} ${agent.role}`.toLowerCase();
        const queryOk = !query || text.includes(query);
        card.classList.toggle("hidden", !(roleOk && queryOk));
        return roleOk && queryOk;
    });

    // Typo tolerance: if nothing matches, show close matches ("jet" -> Jett, "kiljoy" -> Killjoy).
    if (!visible.length && query.length >= 3) {
        visible = $$(".agent-card").filter((card) => {
            const close = levenshtein(query, card.dataset.name.toLowerCase()) <= 2;
            card.classList.toggle("hidden", !close);
            return close;
        });
    }

    const empty = $("#empty-search");
    empty.classList.toggle("hidden", visible.length > 0);
    empty.querySelector("span").textContent = app.filter.query;
    return visible;
}

function levenshtein(a, b) {
    const dp = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
    for (let j = 1; j <= b.length; j++) dp[0][j] = j;
    for (let i = 1; i <= a.length; i++) {
        for (let j = 1; j <= b.length; j++) {
            dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        }
    }
    return dp[a.length][b.length];
}

function isFavorite(name) {
    return (app.settings.favorites || []).includes(name);
}

async function toggleFavorite(name) {
    const favorites = new Set(app.settings.favorites || []);
    favorites.has(name) ? favorites.delete(name) : favorites.add(name);
    await saveSettings({ favorites: [...favorites] });
    renderRoleFilters();
    renderRoster();
}

async function pickAgent(name) {
    if (!app.byName.has(name)) return;
    app.selected = name;
    renderStage();
    decorateCards();
    applyState(await eel.select_agent(name)());
}

/* ---------------------------------------------------------------------
   State -> UI
   --------------------------------------------------------------------- */

function applyState(state) {
    if (!state) return;
    const prev = app.state;
    app.state = state;

    // The backend target wins, so the stage always shows what will actually be locked.
    if (state.agent) app.selected = state.agent;

    renderConnection(state.connection);
    renderStage();
    renderStats(state.stats);
    decorateCards();

    if (prev && prev.phase !== state.phase) updateTitle(state.phase);
}

function renderConnection(conn) {
    const el = $("#conn");
    el.dataset.status = conn.status;
    el.classList.remove("spinning");
    $("#conn-text").textContent = conn.status === "online" ? (conn.player || "Connected") : conn.message;
    $("#conn-meta").textContent = conn.status === "online" && conn.region ? conn.region : "";
}

function renderStage() {
    const state = app.state || { phase: "idle", game: {}, armed: false };
    const agent = app.byName.get(app.selected);
    const stage = $("#stage");
    const phase = PHASES[state.phase] ? state.phase : "idle";
    const info = PHASES[phase];

    stage.dataset.phase = phase;
    stage.style.setProperty("--agent", agent ? agent.color : "#ff4655");

    $("#phase-text").textContent = info.label;
    $("#game-state").textContent = [state.game && state.game.label, state.game && state.game.queue]
        .filter(Boolean).join("  ·  ") || "Waiting for game";

    // Agent visuals
    const preview = $("#preview");
    const bg = $("#stage-bg-img");
    if (agent) {
        const src = agent.preview || agent.banner;
        if (preview.dataset.agent !== agent.name) {
            preview.dataset.agent = agent.name;
            preview.src = src;
            bg.src = agent.banner;
            preview.style.animation = "none";
            void preview.offsetWidth; // restart pop animation
            preview.style.animation = "";
        }
        $("#agent-name").textContent = displayName(agent).toUpperCase();
        $("#agent-role").innerHTML = `${roleIcon(agent.role)}${agent.role}`;
    } else {
        preview.dataset.agent = "";
        preview.src = "./assets/images/slurp.gif";
        bg.removeAttribute("src");
        $("#agent-name").textContent = "PICK YOUR AGENT";
        $("#agent-role").innerHTML = "";
    }

    let hint = info.hint;
    if (phase === "failed" && state.detail) hint = state.detail;
    if (phase === "idle" && agent) hint = app.settings.mode === "hover"
        ? `Ready to hover ${displayName(agent)}. Press ARM, then queue up.`
        : `Ready to lock ${displayName(agent)}. Press ARM, then queue up.`;
    if ((phase === "locked" || phase === "hovered" || phase === "failed") && state.armed) hint += " Still armed for the next match.";
    $("#agent-hint").textContent = hint;

    // Main button
    const btn = $("#arm-btn");
    btn.disabled = !agent;
    btn.classList.toggle("stop", !!state.armed);
    if (state.armed) {
        $("#arm-label").textContent = "STOP";
        $("#arm-sub").textContent = "Esc or Space to cancel";
    } else if (agent) {
        const verb = app.settings.mode === "hover" ? "HOVER" : "INSTALOCK";
        $("#arm-label").textContent = phase === "locked" || phase === "hovered" ? `ARM AGAIN` : `ARM ${verb}`;
        $("#arm-sub").textContent = `${displayName(agent)} · press Space`;
    } else {
        $("#arm-label").textContent = "ARM INSTALOCK";
        $("#arm-sub").textContent = "Select an agent first";
    }

    // Result strip
    const result = state.result;
    const showResult = result && ["locked", "hovered"].includes(phase);
    $("#result").classList.toggle("hidden", !showResult);
    if (showResult) {
        $("#r-ms").textContent = `${result.ms} ms`;
        $("#r-map").textContent = result.map || "-";
        $("#r-queue").textContent = result.queue || "-";
    }
}

function renderStats(stats) {
    if (!stats) return;
    $("#s-locks").textContent = stats.locks;
    $("#s-best").textContent = stats.best_ms == null ? "-" : `${stats.best_ms}ms`;
    $("#s-last").textContent = stats.last_ms == null ? "-" : `${stats.last_ms}ms`;
}

function updateTitle(phase) {
    const label = PHASES[phase] ? PHASES[phase].label : "";
    document.title = phase === "idle" ? "iVALOCKER" : `${label} · iVALOCKER`;
}

function onLocked(result) {
    const stage = $("#stage");
    stage.classList.remove("flash");
    void stage.offsetWidth;
    stage.classList.add("flash");
    if (app.settings.sound) playLockSound(result.hover);
    const what = result.hover ? "Hovered" : "Locked";
    toast("success", `${what} ${result.agent}`, `${result.ms} ms${result.map ? " · " + result.map : ""}${result.backup ? " · backup pick" : ""}`);
}

/* ---------------------------------------------------------------------
   Activity log & toasts
   --------------------------------------------------------------------- */

function addLog(entry) {
    const log = $("#log");
    const li = document.createElement("li");
    li.className = entry.level;
    const time = new Date(entry.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
    li.innerHTML = `<time>${time}</time><span class="dot"></span><span></span>`;
    li.lastElementChild.textContent = entry.text;
    log.prepend(li);
    while (log.children.length > 150) log.lastElementChild.remove();
}

function toast(level, title, text) {
    const box = document.createElement("div");
    box.className = `toast ${level || ""}`;
    box.innerHTML = "<b></b><p></p>";
    box.querySelector("b").textContent = title || "";
    box.querySelector("p").textContent = text || "";
    $("#toasts").prepend(box);
    const close = () => {
        box.classList.add("out");
        setTimeout(() => box.remove(), 260);
    };
    box.addEventListener("click", close);
    setTimeout(close, level === "error" ? 6000 : 3500);
}

/* ---------------------------------------------------------------------
   Settings
   --------------------------------------------------------------------- */

async function saveSettings(changes) {
    Object.assign(app.settings, changes);
    try {
        app.settings = await eel.update_settings(changes)();
    } catch (err) {
        console.error(err);
    }
    renderSettings();
    decorateCards();
    renderStage();
}

function renderSettings() {
    const s = app.settings;
    if (app.hotkeys) updateHotkeyLabels();
    $$(".segmented").forEach((group) => {
        $$(`.segmented[data-setting="${group.dataset.setting}"] button`).forEach((b) =>
            b.classList.toggle("active", b.dataset.value === s[group.dataset.setting]));
    });
    $$('.toggle input[data-setting]').forEach((input) => { input.checked = !!s[input.dataset.setting]; });

    const delay = $("#delay");
    if (document.activeElement !== delay) delay.value = s.lock_delay_ms || 0;
    updateDelayLabel();

    const backup = $("#backup");
    if (backup.value !== (s.backup_agent || "")) backup.value = s.backup_agent || "";
}

function renderBackupSelect() {
    const select = $("#backup");
    select.innerHTML = `<option value="">None</option>` + [...app.agents]
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((a) => `<option value="${a.name}">${displayName(a)}</option>`).join("");
    select.value = app.settings.backup_agent || "";
}

function updateDelayLabel() {
    const delay = $("#delay");
    const v = Number(delay.value);
    $("#delay-value").textContent = v === 0 ? "Instant" : `${v} ms`;
    delay.style.setProperty("--fill", `${(v / Number(delay.max)) * 100}%`);
}

/* ---------------------------------------------------------------------
   Event wiring
   --------------------------------------------------------------------- */

function bindStaticUI() {
    const grid = $("#agent-grid");

    grid.addEventListener("click", (e) => {
        const card = e.target.closest(".agent-card");
        if (!card) return;
        if (e.target.closest(".fav")) {
            toggleFavorite(card.dataset.name);
            return;
        }
        pickAgent(card.dataset.name);
    });

    grid.addEventListener("contextmenu", (e) => {
        const card = e.target.closest(".agent-card");
        if (!card) return;
        e.preventDefault();
        const name = card.dataset.name;
        const backup = app.settings.backup_agent === name ? null : name;
        saveSettings({ backup_agent: backup });
        toast("", backup ? "Backup agent set" : "Backup agent cleared", backup ? `${name} will be locked if your main pick is taken.` : "");
    });

    $("#role-filters").addEventListener("click", (e) => {
        const chip = e.target.closest(".chip");
        if (!chip) return;
        setRoleFilter(chip.dataset.role);
    });

    const search = $("#search");
    search.addEventListener("input", () => {
        app.filter.query = search.value;
        applyFilter();
    });
    search.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const first = $$(".agent-card").find((c) => !c.classList.contains("hidden"));
            if (first) pickAgent(first.dataset.name);
            search.blur();
        } else if (e.key === "Escape") {
            search.value = "";
            app.filter.query = "";
            applyFilter();
            search.blur();
        }
    });

    $("#arm-btn").addEventListener("click", toggleArm);
    $("#btn-reconnect").addEventListener("click", () => {
        $("#conn").classList.add("spinning");
        eel.reconnect();
    });

    $$(".segmented").forEach((group) => {
        group.addEventListener("click", (e) => {
            const b = e.target.closest("button");
            if (b) saveSettings({ [group.dataset.setting]: b.dataset.value });
        });
    });
    $$('.toggle input[data-setting]').forEach((input) => {
        input.addEventListener("change", () => saveSettings({ [input.dataset.setting]: input.checked }));
    });

    const delay = $("#delay");
    delay.addEventListener("input", updateDelayLabel);
    delay.addEventListener("change", () => saveSettings({ lock_delay_ms: Number(delay.value) }));

    $("#backup").addEventListener("change", (e) => saveSettings({ backup_agent: e.target.value || null }));

    $$(".social").forEach((b) => b.addEventListener("click", () => eel.open_link(b.dataset.link)));

    $("#btn-help").addEventListener("click", () => $("#help").classList.toggle("hidden"));
    $("#help").addEventListener("click", (e) => { if (e.target.id === "help") $("#help").classList.add("hidden"); });

    $("#btn-panel").addEventListener("click", () => $("#panel").classList.toggle("open"));
    $("#btn-panel-close").addEventListener("click", () => $("#panel").classList.remove("open"));

    document.addEventListener("keydown", onKey);
}

function setRoleFilter(role) {
    app.filter.role = role;
    $$(".chip").forEach((c) => c.classList.toggle("active", c.dataset.role === role));
    applyFilter();
}

async function toggleArm() {
    const state = app.state || {};
    if (state.armed) {
        applyState(await eel.disarm()());
    } else if (app.selected) {
        applyState(await eel.arm(app.selected)());
    }
}

function onKey(e) {
    if (recordingHotkey) return;
    const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)
        && document.activeElement.type !== "checkbox" && document.activeElement.type !== "range";
    if (typing || e.ctrlKey || e.metaKey || e.altKey) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
            e.preventDefault();
            $("#search").focus();
        }
        return;
    }

    const help = $("#help");
    if (e.key === "/") {
        e.preventDefault();
        $("#search").focus();
    } else if (e.key === "?") {
        help.classList.toggle("hidden");
    } else if (e.key === "Escape") {
        if (!help.classList.contains("hidden")) help.classList.add("hidden");
        else if ($("#panel").classList.contains("open")) $("#panel").classList.remove("open");
        else if (app.state && app.state.armed) toggleArm();
    } else if (e.key === " " && !(document.activeElement && document.activeElement.classList.contains("agent-card"))) {
        e.preventDefault();
        toggleArm();
    } else if (e.key.toLowerCase() === "f" && app.selected) {
        toggleFavorite(app.selected);
    } else if (/^[1-6]$/.test(e.key)) {
        setRoleFilter(["all", "fav", ...ROLE_ORDER][Number(e.key) - 1]);
    }
}

/* ---------------------------------------------------------------------
   Lock sound (generated, no audio files needed)
   --------------------------------------------------------------------- */

let audioCtx = null;
function playLockSound(soft) {
    try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        const notes = soft ? [660] : [880, 1320];
        notes.forEach((freq, i) => {
            const t = audioCtx.currentTime + i * 0.09;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = "triangle";
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0.0001, t);
            gain.gain.exponentialRampToValueAtTime(0.25, t + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
            osc.connect(gain).connect(audioCtx.destination);
            osc.start(t);
            osc.stop(t + 0.2);
        });
    } catch (err) {
        console.warn("Sound unavailable", err);
    }
}

/* ---------------------------------------------------------------------
   Global hotkeys
   --------------------------------------------------------------------- */

let recordingHotkey = null;

function renderHotkeys() {
    const info = app.hotkeys || { supported: false, actions: {} };
    $("#hotkey-note").classList.toggle("hidden", info.supported);
    $("#hotkey-list").innerHTML = Object.entries(info.actions).map(([key, label]) => `
        <div class="hotkey-row">
            <span>${label}</span>
            <button class="hotkey-btn" data-hotkey="${key}" ${info.supported ? "" : "disabled"}
                    title="Click, then press a key. Backspace clears it."></button>
        </div>`).join("");
    $$(".hotkey-btn").forEach((b) => b.addEventListener("click", () => startRecording(b)));
    updateHotkeyLabels();
}

function updateHotkeyLabels() {
    $$(".hotkey-btn").forEach((b) => {
        if (b === recordingHotkey) return;
        const value = app.settings[b.dataset.hotkey];
        b.textContent = value || "Not set";
        b.classList.toggle("empty", !value);
    });
    $("#help-hk-arm").textContent = app.settings.hotkey_arm || "-";
    $("#help-hk-next").textContent = app.settings.hotkey_next || "-";
}

function startRecording(button) {
    stopRecording();
    recordingHotkey = button;
    button.classList.add("recording");
    button.textContent = "Press a key...";
    document.addEventListener("keydown", captureHotkey, true);
}

function stopRecording() {
    document.removeEventListener("keydown", captureHotkey, true);
    if (recordingHotkey) recordingHotkey.classList.remove("recording");
    recordingHotkey = null;
    updateHotkeyLabels();
}

/* KeyboardEvent.code -> the key names the backend understands */
function hotkeyKeyName(code) {
    if (/^F\d{1,2}$/.test(code)) return code;
    if (/^Key[A-Z]$/.test(code)) return code.slice(3);
    if (/^Digit\d$/.test(code)) return code.slice(5);
    if (/^Numpad\d$/.test(code)) return code;
    const map = {
        Insert: "Insert", Delete: "Delete", Home: "Home", End: "End", PageUp: "PageUp", PageDown: "PageDown",
        Pause: "Pause", ScrollLock: "ScrollLock", Space: "Space", ArrowUp: "Up", ArrowDown: "Down",
        ArrowLeft: "Left", ArrowRight: "Right", Backquote: "`", Minus: "-", Equal: "=", BracketLeft: "[",
        BracketRight: "]", Semicolon: ";", Quote: "'", Comma: ",", Period: ".", Slash: "/", Backslash: "\\",
    };
    return map[code] || null;
}

async function captureHotkey(e) {
    e.preventDefault();
    e.stopPropagation();
    if (["Control", "Alt", "Shift", "Meta"].includes(e.key)) return; // wait for the actual key

    const button = recordingHotkey;
    const setting = button.dataset.hotkey;
    if (e.key === "Escape") return stopRecording();
    if (e.key === "Backspace") {
        stopRecording();
        return saveSettings({ [setting]: "" });
    }

    const key = hotkeyKeyName(e.code);
    const spec = [e.ctrlKey && "Ctrl", e.altKey && "Alt", e.shiftKey && "Shift", e.metaKey && "Win", key]
        .filter(Boolean).join("+");
    stopRecording();
    if (!key) return toast("error", "Key not supported", "Try an F-key, or Ctrl / Alt + a letter.");

    const canonical = await eel.check_hotkey(spec)();
    if (!canonical) {
        return toast("error", "Pick another key", `${spec} would block normal typing. Use F1-F24, or add Ctrl / Alt / Shift.`);
    }
    const taken = Object.keys(app.hotkeys.actions).find((k) => k !== setting && app.settings[k] === canonical);
    if (taken) {
        return toast("error", "Already in use", `${canonical} is already set for "${app.hotkeys.actions[taken]}".`);
    }
    await saveSettings({ [setting]: canonical });
    toast("success", "Hotkey saved", `${canonical}: ${app.hotkeys.actions[setting]}`);
}

function onHotkey(event) {
    if (app.settings.sound) {
        playTone(event.action === "disarm" ? [660, 440] : event.action === "arm" ? [440, 660] : [550]);
    }
    const titles = { arm: "Armed", disarm: "Stopped", agent: "Agent", mode: "Mode" };
    const text = event.action === "mode" ? (event.mode === "hover" ? "Hover only" : "Instalock") : (event.agent || "");
    toast("", `${titles[event.action] || "Hotkey"}`, text);
}

function playTone(freqs) {
    try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        freqs.forEach((freq, i) => {
            const t = audioCtx.currentTime + i * 0.08;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = "sine";
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0.0001, t);
            gain.gain.exponentialRampToValueAtTime(0.2, t + 0.01);
            gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
            osc.connect(gain).connect(audioCtx.destination);
            osc.start(t);
            osc.stop(t + 0.14);
        });
    } catch (err) {
        console.warn("Sound unavailable", err);
    }
}
