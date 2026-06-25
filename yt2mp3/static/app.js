/* yt2mp3 v3.3 — interactive stage: links become floating balls tied to the real
   download queue; finished downloads fly into the real player dock. */
(() => {
  "use strict";
  const T = window.I18N || {};
  const $ = (s, r = document) => r.querySelector(s);
  const api = (u, o) => fetch(u, o).then(r => r.ok ? r.json() : Promise.reject(r));

  const stage = $("#stage");
  const dock = $("#dock");
  const dockList = $("#dock-list");
  const dockCount = $("#dock-count");
  const input = $("#url-input");
  const toastBox = $("#toast");

  const balls = new Map();        // jobId -> {state, el, landed}
  let queueTimer = null, libTimer = null;
  let audioCtx = null;

  // ---- sound (WebAudio tones, no files) ----
  const soundOn = () => localStorage.getItem("yt_sound") !== "0";
  function tone(freq, dur, type = "sine", vol = 0.05, slideTo) {
    if (!soundOn()) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.type = type; o.frequency.value = freq;
      if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, audioCtx.currentTime + dur);
      g.gain.value = vol;
      g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + dur);
      o.connect(g); g.connect(audioCtx.destination);
      o.start(); o.stop(audioCtx.currentTime + dur);
    } catch (e) {}
  }
  const ding = () => { tone(660, .15, "sine", .06, 990); setTimeout(() => tone(990, .2, "sine", .05), 90); };
  const blip = () => tone(520, .08, "triangle", .05, 720);
  const errTone = () => tone(200, .25, "sawtooth", .05, 120);

  function toast(msg) {
    toastBox.textContent = msg;
    toastBox.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toastBox.classList.remove("show"), 2600);
  }

  // ---- submit links ----
  function submit(text) {
    text = (text || "").trim();
    if (!text) { input.classList.add("shake"); setTimeout(() => input.classList.remove("shake"), 500); toast(T.needLink); return; }
    const fd = new FormData();
    fd.append("urls", text);
    if ($("#force-cb")?.checked) fd.append("force", "1");
    if ($("#playlist-cb")?.checked) fd.append("allow_playlist", "1");
    api("/api/download", { method: "POST", body: fd }).then(res => {
      (res.errors || []).forEach(toast);
      (res.skipped || []).forEach(s => toast("✓ " + (s.url)));
      if (res.evict_warning) toast("⚠️ " + res.evict_warning);
      if (res.submitted && res.submitted.length) {
        blip();
        res.submitted.forEach(s => addBall(s.id, s.url, "queued", 0, null));
        input.value = "";
        startPolling();
      }
    }).catch(() => toast(T.failed));
  }

  // ---- balls ----
  function addBall(id, url, state, pct, title) {
    if (balls.has(id)) return;
    const el = document.createElement("div");
    el.className = "ball";
    el.dataset.id = id;
    el.style.setProperty("--x", (8 + Math.random() * 74) + "%");
    el.style.setProperty("--y", (10 + Math.random() * 55) + "%");
    el.style.setProperty("--bob", (3 + Math.random() * 2.4).toFixed(2) + "s");
    el.style.setProperty("--sway", (4 + Math.random() * 3).toFixed(2) + "s");
    el.style.setProperty("--d", (-Math.random() * 4).toFixed(2) + "s");
    el.style.setProperty("--hue", String(Math.floor(Math.random() * 5)));
    el.innerHTML = `
      <div class="ball-prog"><svg viewBox="0 0 36 36"><circle class="bg" cx="18" cy="18" r="16"/><circle class="fg" cx="18" cy="18" r="16"/></svg></div>
      <div class="ball-body"><span class="ball-title"></span><span class="ball-state"></span></div>`;
    stage.appendChild(el);
    balls.set(id, { state: null, el, landed: false });
    stage.classList.add("has-balls");
    updateBall(id, state, pct, title, null);
  }

  function updateBall(id, state, pct, title, error) {
    const b = balls.get(id);
    if (!b || b.landed) return;
    b.el.querySelector(".ball-title").textContent = title || "…";
    const label = { queued: T.queued, downloading: T.downloading, converting: T.converting, done: T.ready, failed: T.failed, cancelled: T.failed }[state] || state;
    b.el.querySelector(".ball-state").textContent = error ? (T.failed) : label;
    const fg = b.el.querySelector(".fg");
    const shown = state === "converting" ? 100 : pct;
    fg.style.strokeDashoffset = String(100 - shown);
    b.el.classList.toggle("is-failed", state === "failed");
    b.el.classList.toggle("is-converting", state === "converting");
    if (state === "failed" && b.state !== "failed") {
      errTone();
      b.el.classList.add("shake");
      if (!b.el.querySelector(".ball-retry")) {
        const r = document.createElement("button");
        r.className = "ball-retry"; r.textContent = T.retry;
        r.onclick = (e) => { e.stopPropagation(); balls.delete(id); b.el.remove(); submit(b._url || ""); };
        b._url = b.el.dataset.url;
        b.el.appendChild(r);
      }
    }
    b.el.dataset.url = b.el.dataset.url || "";
    if (state === "done" && b.state !== "done") land(id);
    b.state = state;
  }

  function land(id) {
    const b = balls.get(id);
    if (!b || b.landed) return;
    b.landed = true;
    ding();
    const br = b.el.getBoundingClientRect();
    const dr = (dock.getBoundingClientRect());
    const dx = (dr.left + 40) - (br.left + br.width / 2);
    const dy = (dr.top + 30) - (br.top + br.height / 2);
    b.el.classList.add("landing");
    b.el.style.transform = `translate(${dx}px, ${dy}px) scale(.2)`;
    b.el.style.opacity = "0";
    setTimeout(() => { b.el.remove(); balls.delete(id); if (!balls.size) stage.classList.remove("has-balls"); loadLibrary(); }, 760);
  }

  // ---- polling ----
  function startPolling() {
    if (!queueTimer) { pollQueue(); queueTimer = setInterval(pollQueue, 1200); }
    if (!libTimer) { libTimer = setInterval(loadLibrary, 4000); }
  }
  function pollQueue() {
    api("/api/queue").then(res => {
      const seen = new Set();
      (res.jobs || []).forEach(j => {
        seen.add(j.id);
        if (!balls.has(j.id)) addBall(j.id, j.url, j.state, j.pct, j.title);
        else updateBall(j.id, j.state, j.pct, j.title, j.error);
      });
      // jobs that vanished while still active (done & removed) → land if not yet
      balls.forEach((b, id) => {
        if (!seen.has(id) && !b.landed) {
          if (b.state === "failed" || b.state === "cancelled") return;
          land(id);
        }
      });
      if (!balls.size && !(res.jobs || []).length) {
        clearInterval(queueTimer); queueTimer = null;
      }
    }).catch(() => {});
  }

  // ---- player dock (real tracks) ----
  let curAudio = null;
  let dockSig = null;   // signature of the rendered track set — skip rebuild if unchanged
  function loadLibrary() {
    api("/api/library").then(res => renderTracks(res.tracks || [])).catch(() => {});
  }
  function fmtDur(s) { if (!s) return ""; const m = Math.floor(s / 60); return m + ":" + String(s % 60).padStart(2, "0"); }
  function renderTracks(tracks) {
    // Don't touch the DOM if the set of tracks is unchanged — rebuilding would
    // destroy a currently-playing <audio> element and stop playback.
    const sig = tracks.map(t => t.id).join(",");
    if (sig === dockSig) return;
    dockSig = sig;
    dockCount.textContent = tracks.length + " " + (T.tracks || "");
    if (!tracks.length) {
      dockList.innerHTML = `<li class="dock-empty">${T.emptyTracks || ""}</li>`;
      return;
    }
    dockList.innerHTML = "";
    tracks.forEach(t => {
      const li = document.createElement("li");
      li.className = "track";
      li.innerHTML = `
        <button class="t-play" title="${T.play}">▶</button>
        <div class="t-meta"><span class="t-title"></span><span class="t-sub"></span></div>
        <a class="t-dl" href="/file/${t.id}" download title="${T.save}">↓</a>
        <button class="t-del" title="${T.del}">✕</button>
        <audio preload="none" src="/file/${t.id}"></audio>`;
      li.querySelector(".t-title").textContent = t.title;
      li.querySelector(".t-sub").textContent = [t.channel, fmtDur(t.duration_s), t.size_mb ? t.size_mb + " " + (T.mb || "MB") : ""].filter(Boolean).join(" · ");
      const audio = li.querySelector("audio");
      const playBtn = li.querySelector(".t-play");
      playBtn.onclick = () => {
        if (curAudio && curAudio !== audio) { curAudio.pause(); }
        if (audio.paused) { audio.play(); playBtn.textContent = "⏸"; curAudio = audio; }
        else { audio.pause(); playBtn.textContent = "▶"; }
      };
      audio.onended = () => { playBtn.textContent = "▶"; };
      audio.onpause = () => { playBtn.textContent = "▶"; };
      audio.onplay = () => { playBtn.textContent = "⏸"; };
      li.querySelector(".t-del").onclick = () => {
        const fd = new FormData();
        fetch(`/file/${t.id}/delete`, { method: "POST", body: fd }).then(() => loadLibrary());
      };
      dockList.appendChild(li);
    });
  }

  // ---- theme & sound controls ----
  function applyTheme(name) {
    document.documentElement.setAttribute("data-theme", name);
    localStorage.setItem("yt_theme", name);
    document.querySelectorAll("[data-theme-btn]").forEach(b => b.classList.toggle("active", b.dataset.themeBtn === name));
  }
  function applySound() {
    const on = soundOn();
    const btn = $("#sound-btn");
    if (btn) { btn.textContent = on ? "🔊" : "🔇"; btn.classList.toggle("off", !on); }
  }

  // ---- wire up ----
  function init() {
    applyTheme(localStorage.getItem("yt_theme") || "mango");
    applySound();
    document.querySelectorAll("[data-theme-btn]").forEach(b => b.onclick = () => applyTheme(b.dataset.themeBtn));
    $("#sound-btn") && ($("#sound-btn").onclick = () => { localStorage.setItem("yt_sound", soundOn() ? "0" : "1"); applySound(); });
    $("#go-btn") && ($("#go-btn").onclick = () => submit(input.value));
    input && (input.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(input.value); } });
    // drag & drop links onto the stage
    ["dragover", "dragenter"].forEach(ev => stage.addEventListener(ev, e => { e.preventDefault(); stage.classList.add("drop"); }));
    ["dragleave", "drop"].forEach(ev => stage.addEventListener(ev, e => { if (ev !== "drop") stage.classList.remove("drop"); }));
    stage.addEventListener("drop", e => {
      e.preventDefault(); stage.classList.remove("drop");
      let txt = "";
      try { txt = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain") || e.dataTransfer.getData("text"); } catch (_) {}
      txt.trim() ? submit(txt) : toast(T.dropVideo);
    });
    loadLibrary();
    // pick up downloads started elsewhere / on first load
    api("/api/queue").then(res => { if ((res.jobs || []).length) startPolling(); }).catch(() => {});
  }
  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
