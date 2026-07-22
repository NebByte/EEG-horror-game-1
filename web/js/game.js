/* EEG Horror Engine — browser renderer (raycasting, pure canvas + WebAudio).
 *
 * Replaces the DirectX 12 native runtime. No libraries, no build, no internet.
 * Two input modes:
 *   - "Local sim":  a JS affect + director model (mirrors the Python engine) so
 *                   the game plays with nothing else running.
 *   - "Live engine": streams simulated EEG to the Python engine over WebSocket
 *                    and renders the directives it sends back.
 */
(function () {
  "use strict";

  // ------------------------------------------------------------------ map ---
  // 1 = wall, 0 = floor. A corridor maze the player is stalked through.
  const MAP = [
    "1111111111111111",
    "1000000001000001",
    "1011110001011101",
    "1010000000010101",
    "1010111111010101",
    "1000100000010001",
    "1110101111011111",
    "1000101000000001",
    "1011101011111101",
    "1010000010000101",
    "1010111110110101",
    "1000100000100001",
    "1111101110101111",
    "1000001000100001",
    "1011111011101101",
    "1111111111111111",
  ].map((r) => r.split("").map(Number));
  const MH = MAP.length, MW = MAP[0].length;
  const cell = (x, y) => (x < 0 || y < 0 || x >= MW || y >= MH ? 1 : MAP[y | 0][x | 0]);

  // --------------------------------------------------------------- player ---
  const player = { x: 1.5, y: 1.5, a: 0, speed: 2.6, rot: 2.4 };
  const keys = Object.create(null);
  const FOV = Math.PI / 3;

  // ------------------------------------------------------------- director ---
  // Current render state, driven by affect -> directive (local or from engine).
  const state = {
    affect: { fear: 0, stress: 0, arousal: 0.15, engagement: 0.1, relaxation: 0.6, valence: 0.2 },
    mood: "unease",
    intensity: 0.15,
    fog: 0.2,
    flicker: 0,
    bpm: 60,
    backoff: false,
    character: "The Watcher",
    aggression: 0.15,
    stinger: false,
  };

  const MOOD_COLOR = {
    unease: [140, 150, 168],
    dread: [175, 105, 100],
    panic: [205, 70, 60],
    relief: [120, 165, 178],
  };

  // The monster: a point that hunts the player through the grid.
  const monster = { x: 8.5, y: 8.5, active: false, dist: 99 };

  // ------------------------------------------------------------- rendering --
  const canvas = document.getElementById("view");
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0, DPR = 1;
  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    // Render at a lower internal resolution for the retro/pixelated horror look.
    W = Math.floor(window.innerWidth * 0.5);
    H = Math.floor(window.innerHeight * 0.5);
    canvas.width = W; canvas.height = H;
  }
  window.addEventListener("resize", resize);
  resize();

  let flickerLevel = 1;
  function renderWorld(t) {
    const [mr, mg, mb] = MOOD_COLOR[state.mood] || MOOD_COLOR.unease;
    // Keep near walls clearly lit; the dread comes from fog, tint + flicker,
    // not from a black screen you can't navigate.
    const light = Math.max(0.55, 1.15 - state.intensity * 0.35) * flickerLevel;

    // Ceiling + floor gradient.
    const ceil = ctx.createLinearGradient(0, 0, 0, H / 2);
    ceil.addColorStop(0, `rgb(${mr * 0.10 | 0},${mg * 0.10 | 0},${mb * 0.12 | 0})`);
    ceil.addColorStop(1, `rgb(${mr * 0.04 | 0},${mg * 0.04 | 0},${mb * 0.05 | 0})`);
    ctx.fillStyle = ceil; ctx.fillRect(0, 0, W, H / 2);
    ctx.fillStyle = "#050506"; ctx.fillRect(0, H / 2, W, H / 2);

    const zbuf = new Float32Array(W);
    for (let col = 0; col < W; col++) {
      const camX = (2 * col) / W - 1;
      const ang = player.a + Math.atan(camX * Math.tan(FOV / 2));
      const sin = Math.sin(ang), cos = Math.cos(ang);

      // DDA ray march.
      let dist = 0, hit = 0, side = 0;
      let rx = player.x, ry = player.y;
      const step = 0.02;
      while (dist < 20 && !hit) {
        rx += cos * step; ry += sin * step; dist += step;
        if (cell(rx, ry) === 1) {
          hit = 1;
          const fx = rx - Math.floor(rx), fy = ry - Math.floor(ry);
          side = Math.min(fx, 1 - fx) < Math.min(fy, 1 - fy) ? 0 : 1;
        }
      }
      const corrected = dist * Math.cos(ang - player.a);
      zbuf[col] = corrected;
      const wallH = Math.min(H, H / (corrected + 0.0001));
      const y0 = (H - wallH) / 2;

      // Distance + fog shading, tinted by mood.
      const fog = Math.exp(-corrected * (0.05 + state.fog * 0.16));
      const shade = light * fog * (side ? 0.62 : 1.0);
      ctx.fillStyle = `rgb(${(mr * shade) | 0},${(mg * shade) | 0},${(mb * shade) | 0})`;
      ctx.fillRect(col, y0, 1, wallH);
    }

    drawMonster(zbuf);
    drawGrain(t);
  }

  function drawMonster(zbuf) {
    if (!monster.active) return;
    const dx = monster.x - player.x, dy = monster.y - player.y;
    const dist = Math.hypot(dx, dy);
    monster.dist = dist;
    let ang = Math.atan2(dy, dx) - player.a;
    while (ang < -Math.PI) ang += 2 * Math.PI;
    while (ang > Math.PI) ang -= 2 * Math.PI;
    if (Math.abs(ang) > FOV / 1.6) return; // out of view

    const screenX = (0.5 + ang / FOV) * W;
    const size = Math.min(H * 1.4, H / (dist + 0.001));
    const col = screenX | 0;
    if (col < 0 || col >= W || zbuf[Math.max(0, Math.min(W - 1, col))] < dist - 0.3) return;

    const y0 = (H - size) / 2;
    // A tall, thin dread silhouette; deep red glow as it closes in.
    const near = Math.max(0, 1 - dist / 6);
    const wsil = size * 0.20;
    ctx.fillStyle = `rgba(${10 + 60 * near | 0},0,0,${0.85})`;
    ctx.fillRect(screenX - wsil / 2, y0, wsil, size);
    // Head.
    ctx.beginPath();
    ctx.arc(screenX, y0 + size * 0.10, wsil * 0.7, 0, 7);
    ctx.fill();
    // Eyes.
    if (dist < 7) {
      ctx.fillStyle = `rgba(255,${40 * (1 - near) | 0},20,${0.7 + 0.3 * near})`;
      const e = wsil * 0.22;
      ctx.fillRect(screenX - wsil * 0.28, y0 + size * 0.08, e, e);
      ctx.fillRect(screenX + wsil * 0.06, y0 + size * 0.08, e, e);
    }
  }

  let grainCanvas, grainCtx, grainImg;
  function drawGrain() {
    // Cheap film-grain, composited *over* the world (drawImage respects alpha;
    // putImageData does not — it would overwrite the scene).
    if (!grainCanvas || grainCanvas.width !== W) {
      grainCanvas = document.createElement("canvas");
      grainCanvas.width = W; grainCanvas.height = Math.max(1, H);
      grainCtx = grainCanvas.getContext("2d");
      grainImg = grainCtx.createImageData(W, Math.max(1, H));
    }
    const d = grainImg.data;
    const a = 10 + (state.intensity * 22) | 0; // subtle grain opacity
    for (let i = 0; i < d.length; i += 4) {
      const n = (Math.random() * 130) | 0;
      d[i] = d[i + 1] = d[i + 2] = n; d[i + 3] = a;
    }
    grainCtx.putImageData(grainImg, 0, 0);
    ctx.drawImage(grainCanvas, 0, 0);
  }

  // ------------------------------------------------------------- movement ---
  function stepMovement(dt) {
    let mv = 0, strafe = 0, turn = 0;
    if (keys["w"] || keys["arrowup"]) mv += 1;
    if (keys["s"] || keys["arrowdown"]) mv -= 1;
    if (keys["a"]) strafe -= 1;
    if (keys["d"]) strafe += 1;
    if (keys["arrowleft"]) turn -= 1;
    if (keys["arrowright"]) turn += 1;

    player.a += turn * player.rot * dt;
    const sp = player.speed * dt;
    const nx = player.x + Math.cos(player.a) * mv * sp - Math.sin(player.a) * strafe * sp * 0.7;
    const ny = player.y + Math.sin(player.a) * mv * sp + Math.cos(player.a) * strafe * sp * 0.7;
    if (cell(nx, player.y) === 0) player.x = nx;
    if (cell(player.x, ny) === 0) player.y = ny;
  }

  function stepMonster(dt) {
    monster.active = state.intensity > 0.18 && state.mood !== "relief";
    if (!monster.active) { monster.x = 8.5; monster.y = 8.5; return; }
    // Greedy pursuit through open cells, faster with aggression/intensity.
    const speed = (0.5 + state.aggression * 1.6 + state.intensity * 1.2) * dt;
    const dx = player.x - monster.x, dy = player.y - monster.y;
    const d = Math.hypot(dx, dy) || 1;
    const stepx = (dx / d) * speed, stepy = (dy / d) * speed;
    if (cell(monster.x + stepx, monster.y) === 0) monster.x += stepx;
    else monster.y += (dy > 0 ? 1 : -1) * speed; // slide along walls
    if (cell(monster.x, monster.y + stepy) === 0) monster.y += stepy;
  }

  // ------------------------------------------------------------- LOCAL sim --
  // A compact JS mirror of the Python affect + director, so the game runs with
  // no server. `fearDrive` in [0,1] pushes arousal/valence toward terror.
  let simPhase = 0;
  function localAffect(dt, fearDrive, auto) {
    simPhase += dt;
    let drive = fearDrive;
    if (auto) {
      // Slow "breathe": tension rises, occasional lulls (relief).
      const breathe = 0.5 + 0.5 * Math.sin(simPhase * 0.18);
      drive = Math.min(1, fearDrive * 0.5 + breathe * 0.7);
    }
    const a = state.affect;
    const target = {
      arousal: drive,
      fear: Math.max(0, drive * 1.05 - 0.05),
      stress: drive * 0.85,
      engagement: 0.3 + drive * 0.6,
      relaxation: Math.max(0, 0.7 - drive),
      valence: 0.4 - drive * 1.3,
    };
    for (const k in target) a[k] = a[k] + (target[k] - a[k]) * Math.min(1, dt * 1.5);
    return a;
  }

  function localDirector(a) {
    const drive = 0.5 * a.fear + 0.3 * a.stress + 0.2 * a.arousal;
    let mood = drive < 0.3 ? "unease" : drive < 0.6 ? "dread" : "panic";
    const targetInt = Math.min(1, (0.55 * a.fear + 0.25 * a.arousal + 0.2 * a.stress) * 1.1);
    state._stressEma = (state._stressEma || 0) * 0.85 + a.stress * 0.15;
    let backoff = state._stressEma > 0.9;
    if (backoff) mood = "relief";
    state.intensity += (targetInt - state.intensity) * 0.06;
    if (backoff) state.intensity = Math.min(state.intensity, 0.25);
    applyDirective({
      mood,
      intensity: state.intensity,
      fog_density: 0.15 + 0.6 * state.intensity,
      flicker: mood === "relief" ? 0 : state.intensity,
      heartbeat_bpm: 60 + 70 * a.arousal,
      safety_backoff: backoff,
      _aggr: mood === "panic" ? 0.9 : mood === "dread" ? 0.45 : 0.15,
      _char: { unease: "The Watcher", dread: "The Crawler", panic: "The Render", relief: "Distant Echo" }[mood],
    });
  }

  function applyDirective(d) {
    state.mood = d.mood;
    state.intensity = d.intensity;
    state.fog = d.fog_density;
    state.flicker = d.flicker;
    state.bpm = d.heartbeat_bpm;
    state.backoff = !!d.safety_backoff;
    if (d._aggr !== undefined) state.aggression = d._aggr;
    if (d._char) state.character = d._char;
    if (d.stinger_sound_id) state.stinger = true;
  }

  // ------------------------------------------------------------ LIVE engine -
  // Streams simulated EEG to the Python engine; renders returned directives.
  const engine = { ws: null, sid: null, url: null, timer: 0, connected: false };
  function bandsForArousal(arousal, valence) {
    // Build a tiny synthetic EEG window the Python band/affect code will read.
    const fs = 128, n = 128, chans = ["AF3", "AF4", "TP9", "TP10"];
    const centers = { delta: 2, theta: 6, alpha: 10, beta: 20, gamma: 38 };
    const amp = {
      delta: 1 - 0.3 * arousal, theta: 0.8 + 0.3 * arousal,
      alpha: 1.2 * (1 - 0.8 * arousal), beta: 0.4 + 1.6 * arousal, gamma: 0.2 + arousal,
    };
    const samples = [];
    for (let i = 0; i < n; i++) {
      const t = i / fs, channels = [];
      for (let c = 0; c < chans.length; c++) {
        let v = 0;
        for (const b in centers) {
          let m = amp[b];
          if (b === "alpha" && (chans[c] === "AF3" || chans[c] === "AF4")) {
            m *= chans[c] === "AF3" ? 1 - 0.5 * valence : 1 + 0.5 * valence;
          }
          v += m * Math.sin(2 * Math.PI * centers[b] * t + c * 0.3);
        }
        channels.push(+(v + (Math.random() - 0.5) * 0.3).toFixed(3));
      }
      samples.push({ t: +t.toFixed(4), channels });
    }
    return { sample_rate_hz: fs, channel_names: chans, samples };
  }

  async function connectEngine(url) {
    disconnectEngine();
    engine.url = url.replace(/\/$/, "");
    setConn(false, "connecting…");
    try {
      const seed = { theme: "abandoned asylum", fears: ["darkness", "being watched"] };
      const r = await fetch(engine.url + "/v1/sessions", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ seed }),
      });
      const s = await r.json();
      engine.sid = s.id;
      await fetch(engine.url + "/v1/sessions/" + engine.sid + "/generate", { method: "POST" });
      const wsUrl = engine.url.replace(/^http/, "ws") + "/v1/sessions/" + engine.sid + "/stream";
      const ws = new WebSocket(wsUrl);
      engine.ws = ws;
      ws.onopen = () => { engine.connected = true; setConn(true, "live engine · " + engine.sid); pumpEEG(); };
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.affect) state.affect = m.affect;
        if (m.directive) applyDirective(m.directive);
      };
      ws.onclose = () => { engine.connected = false; if (mode === "live") setConn(false, "engine offline — using local"); };
      ws.onerror = () => {};
    } catch (e) {
      setConn(false, "engine unreachable — using local");
      mode = "local";
      syncModeButtons();
    }
  }
  function pumpEEG() {
    clearInterval(engine.timer);
    engine.timer = setInterval(() => {
      if (!engine.connected || !engine.ws || engine.ws.readyState !== 1) return;
      const a = state.affect;
      engine.ws.send(JSON.stringify(bandsForArousal(
        Math.max(fearSlider(), a.arousal), a.valence)));
    }, 500);
  }
  function disconnectEngine() {
    clearInterval(engine.timer);
    if (engine.ws) { try { engine.ws.close(); } catch (e) {} }
    engine.ws = null; engine.connected = false;
  }

  // ------------------------------------------------------------------ audio -
  let AC = null, master = null, droneGain = null, heartOsc = null, heartGain = null;
  let lastBeat = 0;
  function initAudio() {
    if (AC) return;
    AC = new (window.AudioContext || window.webkitAudioContext)();
    master = AC.createGain(); master.gain.value = 0.6; master.connect(AC.destination);
    // Low drone bed.
    const o1 = AC.createOscillator(); o1.type = "sawtooth"; o1.frequency.value = 55;
    const o2 = AC.createOscillator(); o2.type = "sine"; o2.frequency.value = 41.2;
    droneGain = AC.createGain(); droneGain.gain.value = 0.05;
    const lp = AC.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 220;
    o1.connect(lp); o2.connect(lp); lp.connect(droneGain); droneGain.connect(master);
    o1.start(); o2.start();
  }
  function heartbeat(now) {
    if (!AC) return;
    const interval = 60 / Math.max(40, state.bpm);
    if (now - lastBeat < interval) return;
    lastBeat = now;
    const g = AC.createGain(); g.gain.value = 0.0001;
    const o = AC.createOscillator(); o.type = "sine"; o.frequency.value = 60;
    o.connect(g); g.connect(master);
    const vol = 0.15 + state.intensity * 0.5;
    const t = AC.currentTime;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
    o.start(t); o.stop(t + 0.25);
  }
  function stinger() {
    if (!AC || !state.stinger) return;
    state.stinger = false;
    const t = AC.currentTime;
    const o = AC.createOscillator(); o.type = "sawtooth";
    o.frequency.setValueAtTime(880, t);
    o.frequency.exponentialRampToValueAtTime(140, t + 0.5);
    const g = AC.createGain(); g.gain.setValueAtTime(0.28, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + 0.6);
  }
  function updateAudio(dt) {
    if (!AC) return;
    droneGain.gain.value = 0.03 + state.intensity * 0.10;
  }

  // -------------------------------------------------------------------- HUD -
  function fearSlider() { return (+document.getElementById("fear").value) / 100; }
  const fills = {};
  document.querySelectorAll("#affect .meter").forEach((m) => (fills[m.dataset.k] = m));
  const HUE = { fear: "#d94a4a", stress: "#d98a4a", arousal: "#d9c04a", engagement: "#4a90d9", relaxation: "#4ad98f" };
  function updateHUD() {
    const a = state.affect;
    for (const k in fills) {
      const v = Math.max(0, Math.min(1, a[k] || 0));
      const m = fills[k];
      m.querySelector(".fill").style.width = (v * 100).toFixed(0) + "%";
      m.querySelector(".fill").style.background = HUE[k];
      m.querySelector(".v").textContent = v.toFixed(2);
    }
    const moodEl = document.getElementById("mood");
    moodEl.textContent = state.mood;
    moodEl.style.color = `rgb(${MOOD_COLOR[state.mood].map((c) => Math.min(255, c + 90)).join(",")})`;
    document.getElementById("s-int").textContent = state.intensity.toFixed(2);
    document.getElementById("s-bpm").textContent = state.bpm.toFixed(0);
    document.getElementById("s-chr").textContent = monster.active ? state.character : "—";
    document.getElementById("backoff").classList.toggle("on", state.backoff);
  }

  // ------------------------------------------------------------- main loop --
  let mode = "local";
  let last = performance.now() / 1000;
  function loop() {
    const now = performance.now() / 1000;
    let dt = now - last; last = now;
    dt = Math.min(dt, 0.05);

    if (mode === "local") { localDirector(localAffect(dt, fearSlider(), document.getElementById("auto").checked)); }
    // In live mode the engine drives state.* via WebSocket messages.

    // Flicker: random darkening scaled by intensity, worse in panic.
    const fl = state.flicker;
    flickerLevel = 1 - (Math.random() < fl * 0.25 ? Math.random() * fl * 0.7 : 0);

    stepMovement(dt);
    stepMonster(dt);
    renderWorld(now);
    heartbeat(now); stinger(); updateAudio(dt);
    updateHUD();
    requestAnimationFrame(loop);
  }

  // ------------------------------------------------------------- controls ---
  window.addEventListener("keydown", (e) => {
    keys[e.key.toLowerCase()] = true;
    if (e.key === "Escape" && document.pointerLockElement) document.exitPointerLock();
  });
  window.addEventListener("keyup", (e) => (keys[e.key.toLowerCase()] = false));
  document.addEventListener("mousemove", (e) => {
    if (document.pointerLockElement === canvas) player.a += e.movementX * 0.0025;
  });
  canvas.addEventListener("click", () => canvas.requestPointerLock && canvas.requestPointerLock());

  function setConn(live, text) {
    document.querySelector("#conn .dot").classList.toggle("live", !!live);
    document.getElementById("conn-t").textContent = text;
  }
  const drvLabel = document.getElementById("drv");
  document.getElementById("fear").addEventListener("input", () =>
    (drvLabel.textContent = (fearSlider() * 100).toFixed(0) + "%"));

  function syncModeButtons() {
    document.getElementById("m-local").classList.toggle("active", mode === "local");
    document.getElementById("m-live").classList.toggle("active", mode === "live");
    document.getElementById("urlbox").style.display = mode === "live" ? "block" : "none";
  }
  document.getElementById("m-local").onclick = () => {
    mode = "local"; disconnectEngine(); setConn(false, "local simulation"); syncModeButtons();
  };
  document.getElementById("m-live").onclick = () => {
    mode = "live"; syncModeButtons();
    connectEngine(document.getElementById("engineUrl").value);
  };
  document.getElementById("engineUrl").addEventListener("change", (e) => {
    if (mode === "live") connectEngine(e.target.value);
  });

  // If served from the engine itself, offer live mode automatically.
  if (location.protocol.startsWith("http")) {
    document.getElementById("engineUrl").value = location.origin;
  }

  document.getElementById("go").onclick = () => {
    initAudio();
    if (AC && AC.state === "suspended") AC.resume();
    document.getElementById("start").style.display = "none";
    canvas.requestPointerLock && canvas.requestPointerLock();
  };

  syncModeButtons();
  requestAnimationFrame(loop);

  // Debug hook (used by automated screenshots / tuning; harmless in play).
  window.__game = { player, state, monster, MAP };
})();
