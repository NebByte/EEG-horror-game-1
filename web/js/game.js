/* EEG Horror Engine — browser renderer (enriched raycasting, pure canvas + WebAudio).
 *
 * Replaces the DirectX runtime. No libraries, no build, no internet. Now with:
 *   - procedural, textured walls generated from seeds into RAM (kkrieger-style)
 *   - procedural level layouts (corridor / maze / atrium / room)
 *   - distinct stalker silhouettes per encounter DataPoint
 *   - Script playback: walks the Architect's Beats and spawns their DataPoints
 *   - a closed learning loop: posts reactions so the model learns you as you play
 *
 * Modes:
 *   "Local sim"   — JS affect + director, no server needed.
 *   "Live engine" — creates a session, composes a Script, streams EEG, plays the
 *                   beats, and feeds reactions back to the learning layer.
 */
(function () {
  "use strict";

  // ------------------------------------------------------------ utilities ---
  const clamp = (x, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const hashStr = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };

  // ------------------------------------------------------- procedural maps --
  // Grid cells: 0 = floor, >=1 = wall type id (selects a texture). Generated
  // from a seed so the whole level is a few bytes that expand in RAM.
  const MAPW = 20, MAPH = 20;
  function genMap(spaceType, seed) {
    const rng = mulberry32(seed >>> 0);
    const g = Array.from({ length: MAPH }, () => new Array(MAPW).fill(0));
    const wall = (x, y, t) => { if (x >= 0 && y >= 0 && x < MAPW && y < MAPH) g[y][x] = t; };
    // border
    for (let x = 0; x < MAPW; x++) { wall(x, 0, 1); wall(x, MAPH - 1, 1); }
    for (let y = 0; y < MAPH; y++) { wall(0, y, 1); wall(MAPW - 1, y, 1); }

    const wtype = () => 1 + (rng() * 3 | 0); // 1..3 texture variants

    if (spaceType === "atrium") {
      // open hall with a ring of pillars + a few stubs
      for (let i = 0; i < 10; i++) {
        const cx = 4 + (rng() * (MAPW - 8) | 0), cy = 4 + (rng() * (MAPH - 8) | 0);
        wall(cx, cy, wtype());
        if (rng() < 0.4) wall(cx + 1, cy, wtype());
      }
    } else if (spaceType === "room") {
      // one big room, scattered short walls (mirror stubs / partitions)
      for (let i = 0; i < 14; i++) {
        const cx = 3 + (rng() * (MAPW - 6) | 0), cy = 3 + (rng() * (MAPH - 6) | 0);
        const len = 1 + (rng() * 3 | 0), horiz = rng() < 0.5;
        for (let k = 0; k < len; k++) wall(cx + (horiz ? k : 0), cy + (horiz ? 0 : k), wtype());
      }
    } else {
      // corridor / maze: carve on a 2-grid then thin the walls a bit
      for (let y = 2; y < MAPH - 2; y += 2) {
        for (let x = 2; x < MAPW - 2; x += 2) {
          wall(x, y, wtype());
          const d = rng();
          if (d < 0.33) wall(x + 1, y, wtype());
          else if (d < 0.66) wall(x, y + 1, wtype());
        }
      }
      const openness = spaceType === "corridor" ? 0.5 : 0.28; // maze is denser
      for (let y = 1; y < MAPH - 1; y++)
        for (let x = 1; x < MAPW - 1; x++)
          if (g[y][x] && rng() < openness) g[y][x] = 0;
    }

    // guarantee an open spawn and clear its neighbourhood
    let sx = 2, sy = 2;
    outer: for (let y = 1; y < MAPH - 1; y++)
      for (let x = 1; x < MAPW - 1; x++)
        if (!g[y][x]) { sx = x; sy = y; break outer; }
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const nx = sx + dx, ny = sy + dy;
      if (nx > 0 && ny > 0 && nx < MAPW - 1 && ny < MAPH - 1) g[ny][nx] = 0;
    }
    return { g, spawn: { x: sx + 0.5, y: sy + 0.5, a: 0 } };
  }

  // ------------------------------------------------ procedural wall textures -
  // A small atlas of 64x64 textures generated per palette+seed. kkrieger-style:
  // no image files ship; textures are synthesised into offscreen canvases.
  const TEX = 64;
  function makeTextures(palette, seed) {
    const rng = mulberry32(seed >>> 0);
    const base = palette;
    const cans = [];
    const styles = ["concrete", "tile", "rust", "flesh"];
    for (let s = 0; s < 4; s++) {
      const c = document.createElement("canvas"); c.width = c.height = TEX;
      const x = c.getContext("2d");
      const [r, g, b] = base;
      x.fillStyle = `rgb(${r | 0},${g | 0},${b | 0})`; x.fillRect(0, 0, TEX, TEX);
      const style = styles[s];
      const img = x.getImageData(0, 0, TEX, TEX), d = img.data;
      for (let i = 0; i < d.length; i += 4) {
        const n = (rng() - 0.5) * (style === "concrete" ? 46 : 30);
        d[i] = clamp(d[i] + n, 0, 255); d[i + 1] = clamp(d[i + 1] + n, 0, 255); d[i + 2] = clamp(d[i + 2] + n, 0, 255);
      }
      x.putImageData(img, 0, 0);
      x.strokeStyle = "rgba(0,0,0,.35)"; x.lineWidth = 1;
      if (style === "tile") {
        for (let k = 0; k <= TEX; k += 16) { x.beginPath(); x.moveTo(k, 0); x.lineTo(k, TEX); x.moveTo(0, k); x.lineTo(TEX, k); x.stroke(); }
      } else if (style === "concrete") {
        for (let k = 16; k < TEX; k += 16) { const off = (k / 16) % 2 ? 0 : 8; x.beginPath(); x.moveTo(0, k); x.lineTo(TEX, k); x.stroke(); for (let j = off; j < TEX; j += 16) { x.beginPath(); x.moveTo(j, k - 16); x.lineTo(j, k); x.stroke(); } }
      } else if (style === "rust") {
        x.strokeStyle = "rgba(60,20,8,.5)";
        for (let k = 0; k < 18; k++) { x.beginPath(); const px = rng() * TEX; x.moveTo(px, 0); for (let yy = 0; yy < TEX; yy += 6) x.lineTo(px + (rng() - 0.5) * 6, yy); x.stroke(); }
      } else { // flesh — organic blotches
        for (let k = 0; k < 22; k++) { x.fillStyle = `rgba(${40 + rng() * 60 | 0},10,10,.25)`; x.beginPath(); x.arc(rng() * TEX, rng() * TEX, 2 + rng() * 7, 0, 7); x.fill(); }
      }
      cans.push(c);
    }
    return cans;
  }

  // -------------------------------------------------------------- scene ------
  // Unified scene state fed by either the local director or the live Script.
  const scene = {
    map: null, texs: null, spaceType: "corridor", palette: [140, 150, 168], mapSeed: 1,
    mood: "unease", intensity: 0.15, fog: 0.2, flicker: 0, bpm: 60, backoff: false,
    encounter: null, // {type,name,speed,aggr} or null
    lightColor: null, event: null, activeDataPoints: [],
  };
  const MOOD_COLOR = {
    unease: [140, 150, 168], dread: [175, 105, 100], panic: [205, 70, 60], relief: [120, 165, 178],
  };
  const ENCOUNTERS = {
    "encounter.distant_figure": { name: "The Watcher", sil: "tall", speed: 0.5, aggr: 0.35 },
    "encounter.crawler": { name: "The Crawler", sil: "low", speed: 1.3, aggr: 0.7 },
    "encounter.render": { name: "The Render", sil: "sprint", speed: 1.7, aggr: 0.95 },
    "encounter.reflection_wrong": { name: "Wrong Reflection", sil: "tall", speed: 0.3, aggr: 0.5 },
  };
  const SPACE_OF = {
    "space.narrow_corridor": "corridor", "space.open_atrium": "atrium",
    "space.flooded_basement": "maze", "space.mirror_room": "room",
  };

  function rebuildLevel(spaceType, seedKey) {
    scene.spaceType = spaceType;
    scene.mapSeed = hashStr(spaceType + ":" + seedKey);
    scene.map = genMap(spaceType, scene.mapSeed);
    scene.texs = makeTextures(scene.palette, scene.mapSeed ^ 0x9e3779b9);
    const sp = scene.map.spawn;
    player.x = sp.x; player.y = sp.y; player.a = sp.a;
    monster.x = sp.x + 4; monster.y = sp.y + 4;
  }
  const cell = (x, y) => {
    const g = scene.map && scene.map.g;
    if (!g || x < 0 || y < 0 || x >= MAPW || y >= MAPH) return 1;
    return g[y | 0][x | 0];
  };

  // --------------------------------------------------------------- player ---
  const player = { x: 2.5, y: 2.5, a: 0, speed: 2.6, rot: 2.4 };
  const keys = Object.create(null);
  const FOV = Math.PI / 3;
  const monster = { x: 8.5, y: 8.5, active: false, dist: 99 };

  // ------------------------------------------------------------- rendering ---
  const canvas = document.getElementById("view");
  const ctx = canvas.getContext("2d");
  let W = 0, H = 0;
  function resize() { W = Math.floor(window.innerWidth * 0.5); H = Math.floor(window.innerHeight * 0.5); canvas.width = W; canvas.height = H; }
  window.addEventListener("resize", resize); resize();

  let flickerLevel = 1;
  const zbuf = () => new Float32Array(W);
  let ZB = zbuf();

  function renderWorld() {
    if (W !== ZB.length) ZB = zbuf();
    const pal = scene.lightColor || scene.palette;
    const [mr, mg, mb] = pal;
    const light = Math.max(0.55, 1.15 - scene.intensity * 0.35) * flickerLevel;

    // ceiling / floor
    const ceil = ctx.createLinearGradient(0, 0, 0, H / 2);
    ceil.addColorStop(0, `rgb(${mr * 0.11 | 0},${mg * 0.11 | 0},${mb * 0.13 | 0})`);
    ceil.addColorStop(1, `rgb(${mr * 0.03 | 0},${mg * 0.03 | 0},${mb * 0.04 | 0})`);
    ctx.fillStyle = ceil; ctx.fillRect(0, 0, W, H / 2);
    const flr = ctx.createLinearGradient(0, H / 2, 0, H);
    flr.addColorStop(0, "#050506"); flr.addColorStop(1, `rgb(${mr * 0.05 | 0},${mg * 0.05 | 0},${mb * 0.06 | 0})`);
    ctx.fillStyle = flr; ctx.fillRect(0, H / 2, W, H / 2);

    const sin0 = Math.sin(player.a), cos0 = Math.cos(player.a);
    for (let col = 0; col < W; col++) {
      const camX = (2 * col) / W - 1;
      const ang = player.a + Math.atan(camX * Math.tan(FOV / 2));
      const sin = Math.sin(ang), cos = Math.cos(ang);

      // grid DDA (Lodev-style) for exact wall hit + texture coordinate
      let mapX = player.x | 0, mapY = player.y | 0;
      const dDX = Math.abs(1 / cos), dDY = Math.abs(1 / sin);
      const stepX = cos < 0 ? -1 : 1, stepY = sin < 0 ? -1 : 1;
      let sDX = (cos < 0 ? player.x - mapX : mapX + 1 - player.x) * dDX;
      let sDY = (sin < 0 ? player.y - mapY : mapY + 1 - player.y) * dDY;
      let side = 0, hit = 0, guard = 0;
      while (!hit && guard++ < 64) {
        if (sDX < sDY) { sDX += dDX; mapX += stepX; side = 0; } else { sDY += dDY; mapY += stepY; side = 1; }
        if (mapX < 0 || mapY < 0 || mapX >= MAPW || mapY >= MAPH) { hit = 1; break; }
        const c = scene.map.g[mapY][mapX]; if (c) hit = c;
      }
      const perp = side === 0 ? sDX - dDX : sDY - dDY;
      const corrected = Math.max(0.01, perp * Math.cos(ang - player.a));
      ZB[col] = corrected;
      const wallH = Math.min(H * 4, H / corrected);
      const y0 = (H - wallH) / 2;

      // texture U coordinate
      let wallX = side === 0 ? player.y + perp * sin : player.x + perp * cos;
      wallX -= Math.floor(wallX);
      const texIdx = (Math.abs(hit) - 1) % (scene.texs ? scene.texs.length : 1);
      const tex = scene.texs ? scene.texs[Math.max(0, texIdx)] : null;
      let tx = (wallX * TEX) | 0; if (side === 0 ? cos > 0 : sin < 0) tx = TEX - tx - 1;

      if (tex) {
        ctx.drawImage(tex, tx, 0, 1, TEX, col, y0, 1, wallH);
      } else {
        ctx.fillStyle = `rgb(${mr | 0},${mg | 0},${mb | 0})`; ctx.fillRect(col, y0, 1, wallH);
      }
      // fog + light + mood tint composited over the textured slice
      const fog = Math.exp(-corrected * (0.05 + scene.fog * 0.16));
      const shade = light * fog * (side ? 0.7 : 1.0);
      const dark = clamp(1 - shade, 0, 0.96);
      ctx.fillStyle = `rgba(${mr * 0.5 | 0},${mg * 0.35 | 0},${mb * 0.35 | 0},${dark})`;
      ctx.fillRect(col, y0, 1, wallH);
    }
    void sin0; void cos0;
    drawMonster();
    drawGrain();
  }

  function drawMonster() {
    if (!monster.active || !scene.encounter) return;
    const dx = monster.x - player.x, dy = monster.y - player.y;
    const dist = Math.hypot(dx, dy); monster.dist = dist;
    let ang = Math.atan2(dy, dx) - player.a;
    while (ang < -Math.PI) ang += 2 * Math.PI; while (ang > Math.PI) ang -= 2 * Math.PI;
    if (Math.abs(ang) > FOV / 1.5) return;
    const screenX = (0.5 + ang / FOV) * W;
    const size = Math.min(H * 1.6, H / (dist + 0.001));
    const col = screenX | 0;
    if (col < 0 || col >= W || ZB[Math.max(0, Math.min(W - 1, col))] < dist - 0.3) return;
    const near = clamp(1 - dist / 6);
    const sil = scene.encounter.sil;

    ctx.save();
    ctx.fillStyle = `rgba(${8 + 70 * near | 0},0,0,.9)`;
    if (sil === "low") {
      // crawler: low, wide mass hugging the floor
      const y0 = (H + size * 0.2) / 2, w = size * 0.5;
      ctx.beginPath(); ctx.ellipse(screenX, y0, w / 2, size * 0.16, 0, 0, 7); ctx.fill();
      for (let l = -2; l <= 2; l++) { ctx.fillRect(screenX + l * w * 0.16, y0, size * 0.03, size * 0.18); }
    } else if (sil === "sprint") {
      // render: tall sprinting mass, lurching
      const y0 = (H - size) / 2, w = size * 0.26;
      ctx.fillRect(screenX - w / 2, y0 + size * 0.1, w, size * 0.9);
      ctx.beginPath(); ctx.arc(screenX + w * 0.2, y0 + size * 0.1, w * 0.55, 0, 7); ctx.fill();
    } else {
      // watcher / reflection: tall, thin, still
      const y0 = (H - size) / 2, w = size * 0.16;
      ctx.fillRect(screenX - w / 2, y0, w, size);
      ctx.beginPath(); ctx.arc(screenX, y0 + size * 0.09, w * 0.75, 0, 7); ctx.fill();
    }
    // eyes
    if (dist < 8) {
      ctx.fillStyle = `rgba(255,${30 * (1 - near) | 0},18,${0.65 + 0.35 * near})`;
      const y0 = (H - size) / 2, e = size * 0.03;
      const ey = sil === "low" ? (H + size * 0.2) / 2 - size * 0.05 : y0 + size * 0.08;
      ctx.fillRect(screenX - size * 0.05, ey, e, e); ctx.fillRect(screenX + size * 0.02, ey, e, e);
    }
    ctx.restore();
  }

  let grainCanvas, grainCtx, grainImg;
  function drawGrain() {
    if (!grainCanvas || grainCanvas.width !== W) {
      grainCanvas = document.createElement("canvas"); grainCanvas.width = W; grainCanvas.height = Math.max(1, H);
      grainCtx = grainCanvas.getContext("2d"); grainImg = grainCtx.createImageData(W, Math.max(1, H));
    }
    const d = grainImg.data, a = 10 + (scene.intensity * 22) | 0;
    for (let i = 0; i < d.length; i += 4) { const n = (Math.random() * 130) | 0; d[i] = d[i + 1] = d[i + 2] = n; d[i + 3] = a; }
    grainCtx.putImageData(grainImg, 0, 0); ctx.drawImage(grainCanvas, 0, 0);
  }

  // --------------------------------------------------------- movement/AI -----
  function stepMovement(dt) {
    let mv = 0, strafe = 0, turn = 0;
    if (keys["w"] || keys["arrowup"]) mv += 1;
    if (keys["s"] || keys["arrowdown"]) mv -= 1;
    if (keys["a"]) strafe -= 1; if (keys["d"]) strafe += 1;
    if (keys["arrowleft"]) turn -= 1; if (keys["arrowright"]) turn += 1;
    player.a += turn * player.rot * dt;
    const sp = player.speed * dt;
    const nx = player.x + Math.cos(player.a) * mv * sp - Math.sin(player.a) * strafe * sp * 0.7;
    const ny = player.y + Math.sin(player.a) * mv * sp + Math.cos(player.a) * strafe * sp * 0.7;
    if (!cell(nx, player.y)) player.x = nx;
    if (!cell(player.x, ny)) player.y = ny;
  }
  function stepMonster(dt) {
    monster.active = !!scene.encounter && scene.intensity > 0.18 && scene.mood !== "relief";
    if (!monster.active) return;
    const e = scene.encounter;
    const speed = (0.4 + e.aggr * 1.4 + scene.intensity * 1.1) * e.speed * dt;
    const dx = player.x - monster.x, dy = player.y - monster.y, d = Math.hypot(dx, dy) || 1;
    const sx = (dx / d) * speed, sy = (dy / d) * speed;
    if (!cell(monster.x + sx, monster.y)) monster.x += sx; else monster.y += Math.sign(dy) * speed;
    if (!cell(monster.x, monster.y + sy)) monster.y += sy;
    if (d < 1.2) { monster.x = player.x + (Math.random() * 8 - 4); monster.y = player.y + (Math.random() * 8 - 4); scene.stinger = true; } // "caught" -> retreat + sting
  }

  // ----------------------------------------------------------- LOCAL sim -----
  const affect = { fear: 0, stress: 0, arousal: 0.15, engagement: 0.1, relaxation: 0.6, valence: 0.2 };
  let simPhase = 0, stressEma = 0;
  function localTick(dt, fearDrive, auto) {
    simPhase += dt;
    let drive = fearDrive;
    if (auto) { const breathe = 0.5 + 0.5 * Math.sin(simPhase * 0.18); drive = Math.min(1, fearDrive * 0.5 + breathe * 0.7); }
    const target = { arousal: drive, fear: Math.max(0, drive * 1.05 - 0.05), stress: drive * 0.85, engagement: 0.3 + drive * 0.6, relaxation: Math.max(0, 0.7 - drive), valence: 0.4 - drive * 1.3 };
    for (const k in target) affect[k] += (target[k] - affect[k]) * Math.min(1, dt * 1.5);

    const dr = 0.5 * affect.fear + 0.3 * affect.stress + 0.2 * affect.arousal;
    let mood = dr < 0.3 ? "unease" : dr < 0.6 ? "dread" : "panic";
    const targetInt = Math.min(1, (0.55 * affect.fear + 0.25 * affect.arousal + 0.2 * affect.stress) * 1.1);
    stressEma = stressEma * 0.85 + affect.stress * 0.15;
    const backoff = stressEma > 0.9; if (backoff) mood = "relief";
    scene.intensity += (targetInt - scene.intensity) * 0.06;
    if (backoff) scene.intensity = Math.min(scene.intensity, 0.25);
    setMood(mood, backoff, 60 + 70 * affect.arousal);
    // local mode: pick an encounter from mood (no script)
    const enc = mood === "panic" ? "encounter.render" : mood === "dread" ? "encounter.crawler" : mood === "unease" ? "encounter.distant_figure" : null;
    setEncounter(enc);
  }

  function setMood(mood, backoff, bpm) {
    scene.mood = mood; scene.backoff = backoff; scene.bpm = bpm;
    scene.palette = MOOD_COLOR[mood];
    scene.fog = 0.15 + 0.6 * scene.intensity;
    scene.flicker = mood === "relief" ? 0 : scene.intensity;
  }
  function setEncounter(dpId) {
    if (!dpId) { scene.encounter = null; return; }
    const e = ENCOUNTERS[dpId]; if (e) scene.encounter = { type: dpId, ...e };
  }

  // ----------------------------------------------------------- LIVE engine ---
  const engine = { ws: null, sid: null, url: null, timer: 0, connected: false, script: null, beat: 0, beatT: 0, playerId: null };

  function loadPlayerId() {
    let id = null; try { id = localStorage.getItem("eeg_player_id"); } catch (e) {}
    if (!id) { id = "p_" + Math.random().toString(36).slice(2, 10); try { localStorage.setItem("eeg_player_id", id); } catch (e) {} }
    return id;
  }

  function bandsForArousal(arousal, valence) {
    const fs = 128, n = 128, chans = ["AF3", "AF4", "TP9", "TP10"];
    const centers = { delta: 2, theta: 6, alpha: 10, beta: 20, gamma: 38 };
    const amp = { delta: 1 - 0.3 * arousal, theta: 0.8 + 0.3 * arousal, alpha: 1.2 * (1 - 0.8 * arousal), beta: 0.4 + 1.6 * arousal, gamma: 0.2 + arousal };
    const samples = [];
    for (let i = 0; i < n; i++) {
      const t = i / fs, channels = [];
      for (let c = 0; c < chans.length; c++) {
        let v = 0;
        for (const b in centers) { let m = amp[b]; if (b === "alpha" && (chans[c] === "AF3" || chans[c] === "AF4")) m *= chans[c] === "AF3" ? 1 - 0.5 * valence : 1 + 0.5 * valence; v += m * Math.sin(2 * Math.PI * centers[b] * t + c * 0.3); }
        channels.push(+(v + (Math.random() - 0.5) * 0.3).toFixed(3));
      }
      samples.push({ t: +t.toFixed(4), channels });
    }
    return { sample_rate_hz: fs, channel_names: chans, samples };
  }

  async function connectEngine(url) {
    disconnectEngine();
    engine.url = url.replace(/\/$/, "");
    engine.playerId = loadPlayerId();
    setConn(false, "connecting…");
    try {
      const seed = { theme: "abandoned asylum", fears: ["darkness", "being watched", "being chased"] };
      let r = await fetch(engine.url + "/v1/sessions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ seed, player_id: engine.playerId }) });
      engine.sid = (await r.json()).id;
      await fetch(engine.url + "/v1/sessions/" + engine.sid + "/generate", { method: "POST" });
      // compose the personalized Script (the Architect authors the game)
      r = await fetch(engine.url + "/v1/sessions/" + engine.sid + "/script", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ length: 8 }) });
      engine.script = await r.json(); engine.beat = 0; engine.beatT = 0;
      applyBeat(engine.script.beats[0], engine.script);
      updateArchitectHUD();
      refreshLearning();

      const wsUrl = engine.url.replace(/^http/, "ws") + "/v1/sessions/" + engine.sid + "/stream";
      const ws = new WebSocket(wsUrl); engine.ws = ws;
      ws.onopen = () => { engine.connected = true; setConn(true, "live · " + engine.playerId); pumpEEG(); };
      ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.affect) Object.assign(affect, m.affect); if (m.directive) applyDirective(m.directive); };
      ws.onclose = () => { engine.connected = false; if (mode === "live") setConn(false, "engine offline — local"); };
      ws.onerror = () => {};
    } catch (e) {
      setConn(false, "engine unreachable — using local"); mode = "local"; syncModeButtons();
    }
  }
  function pumpEEG() {
    clearInterval(engine.timer);
    engine.timer = setInterval(() => {
      if (!engine.connected || !engine.ws || engine.ws.readyState !== 1) return;
      engine.ws.send(JSON.stringify(bandsForArousal(Math.max(fearSlider(), affect.arousal), affect.valence)));
    }, 500);
  }
  function disconnectEngine() { clearInterval(engine.timer); if (engine.ws) { try { engine.ws.close(); } catch (e) {} } engine.ws = null; engine.connected = false; engine.script = null; }

  // Live: the beat sets the baseline; the directive modulates within it. The
  // beat authors the arc, but live terror still visibly heats the scene toward
  // panic-red so the player's own fear is always felt on screen.
  const PANIC_RGB = [205, 70, 60];
  function applyDirective(d) {
    scene.intensity += (d.intensity - scene.intensity) * 0.4;
    scene.bpm = d.heartbeat_bpm; scene.backoff = !!d.safety_backoff;
    if (d.safety_backoff) { setMood("relief", true, d.heartbeat_bpm); setEncounter(null); }
    scene.fog = d.fog_density; scene.flicker = d.flicker;
    if (d.stinger_sound_id) scene.stinger = true;
    // Blend the beat's palette toward panic-red by live intensity.
    const base = MOOD_COLOR[scene.mood] || scene.palette;
    const k = clamp(scene.intensity * 0.8);
    scene.palette = base.map((c, i) => c + (PANIC_RGB[i] - c) * k);
  }

  // Applying a Beat: choose the space (level built once per space change), the
  // encounter, lighting, and record which DataPoints are active (for reactions).
  let currentSpace = null;
  function applyBeat(beat, script) {
    if (!beat) return;
    scene.mood = beat.mood; scene.palette = MOOD_COLOR[beat.mood] || scene.palette;
    scene.activeDataPoints = beat.datapoint_ids.slice();
    // space
    const spaceDp = beat.datapoint_ids.find((d) => d.startsWith("space."));
    const spaceType = SPACE_OF[spaceDp] || currentSpace || "corridor";
    if (spaceType !== currentSpace) { currentSpace = spaceType; rebuildLevel(spaceType, script.session_id + ":" + beat.index); }
    // encounter
    const encDp = beat.datapoint_ids.find((d) => d.startsWith("encounter."));
    setEncounter(encDp || null);
    // lighting tint
    const lightDp = beat.datapoint_ids.find((d) => d.startsWith("lighting."));
    scene.lightColor = lightDp && lightDp.includes("strobe") ? [210, 60, 50] : lightDp && lightDp.includes("backlight") ? [90, 40, 40] : null;
  }

  function advanceScript(dt) {
    if (mode !== "live" || !engine.script) return;
    engine.beatT += dt;
    const beat = engine.script.beats[engine.beat];
    const dur = (beat && beat.duration_s) || 40;
    if (engine.beatT >= dur && engine.beat < engine.script.beats.length - 1) {
      engine.beat++; engine.beatT = 0; applyBeat(engine.script.beats[engine.beat], engine.script); updateArchitectHUD();
    }
  }

  // ------------------------------------------------------ reactions/learning -
  // Detect a scare moment (stalker very close, or a stinger) and post how the
  // player's affect moved, so the model learns what scares THEM.
  const affectRing = []; // {t, fear, arousal}
  let lastReaction = 0;
  function trackReaction(now) {
    affectRing.push({ t: now, fear: affect.fear, arousal: affect.arousal });
    while (affectRing.length && now - affectRing[0].t > 4) affectRing.shift();
    if (mode !== "live" || !engine.sid || !engine.script) return;
    const scared = (monster.active && monster.dist < 2.6) || scene.stinger;
    if (!scared || now - lastReaction < 5) return;
    lastReaction = now;
    const before = affectRing[0] || { fear: affect.fear, arousal: affect.arousal };
    const body = {
      beat_index: engine.beat,
      affect_before: { fear: before.fear, arousal: before.arousal },
      affect_peak: { fear: affect.fear, arousal: affect.arousal },
    };
    fetch(engine.url + "/v1/sessions/" + engine.sid + "/reactions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then((r) => r.json()).then((s) => { showLearnPulse(); setLearning(s.reactions_seen, s.top_datapoints); }).catch(() => {});
  }
  function refreshLearning() {
    if (!engine.url || !engine.playerId) return;
    fetch(engine.url + "/v1/players/" + engine.playerId).then((r) => r.json())
      .then((p) => setLearning(p.reactions_seen, Object.entries(p.datapoint_scores || {}).sort((a, b) => b[1] - a[1]).slice(0, 3))).catch(() => {});
  }

  // ------------------------------------------------------------------ audio -
  let AC = null, master = null, droneGain = null, lastBeat = 0;
  function initAudio() {
    if (AC) return; AC = new (window.AudioContext || window.webkitAudioContext)();
    master = AC.createGain(); master.gain.value = 0.6; master.connect(AC.destination);
    const o1 = AC.createOscillator(); o1.type = "sawtooth"; o1.frequency.value = 55;
    const o2 = AC.createOscillator(); o2.type = "sine"; o2.frequency.value = 41.2;
    droneGain = AC.createGain(); droneGain.gain.value = 0.05;
    const lp = AC.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 220;
    o1.connect(lp); o2.connect(lp); lp.connect(droneGain); droneGain.connect(master); o1.start(); o2.start();
  }
  function heartbeat(now) {
    if (!AC) return; const interval = 60 / Math.max(40, scene.bpm); if (now - lastBeat < interval) return; lastBeat = now;
    const g = AC.createGain(), o = AC.createOscillator(); o.type = "sine"; o.frequency.value = 60; o.connect(g); g.connect(master);
    const vol = 0.15 + scene.intensity * 0.5, t = AC.currentTime;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
    o.start(t); o.stop(t + 0.25);
  }
  function stinger() {
    if (!AC || !scene.stinger) return; scene.stinger = false; const t = AC.currentTime;
    const o = AC.createOscillator(); o.type = "sawtooth"; o.frequency.setValueAtTime(880, t); o.frequency.exponentialRampToValueAtTime(140, t + 0.5);
    const g = AC.createGain(); g.gain.setValueAtTime(0.28, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.6); o.connect(g); g.connect(master); o.start(t); o.stop(t + 0.6);
  }
  function updateAudio() { if (AC) droneGain.gain.value = 0.03 + scene.intensity * 0.10; }

  // -------------------------------------------------------------------- HUD --
  function fearSlider() { return (+document.getElementById("fear").value) / 100; }
  const fills = {}; document.querySelectorAll("#affect .meter").forEach((m) => (fills[m.dataset.k] = m));
  const HUE = { fear: "#d94a4a", stress: "#d98a4a", arousal: "#d9c04a", engagement: "#4a90d9", relaxation: "#4ad98f" };
  function updateHUD() {
    for (const k in fills) { const v = clamp(affect[k] || 0); const m = fills[k]; m.querySelector(".fill").style.width = (v * 100).toFixed(0) + "%"; m.querySelector(".fill").style.background = HUE[k]; m.querySelector(".v").textContent = v.toFixed(2); }
    const moodEl = document.getElementById("mood"); moodEl.textContent = scene.mood;
    moodEl.style.color = `rgb(${MOOD_COLOR[scene.mood].map((c) => Math.min(255, c + 90)).join(",")})`;
    document.getElementById("s-int").textContent = scene.intensity.toFixed(2);
    document.getElementById("s-bpm").textContent = scene.bpm.toFixed(0);
    document.getElementById("s-space").textContent = scene.spaceType;
    document.getElementById("s-chr").textContent = monster.active && scene.encounter ? scene.encounter.name : "—";
    document.getElementById("backoff").classList.toggle("on", scene.backoff);
  }
  function updateArchitectHUD() {
    const beatEl = document.getElementById("a-beat"), beatsEl = document.getElementById("a-beats");
    const els = document.getElementById("a-els"), rat = document.getElementById("a-rat"), amood = document.getElementById("a-mood");
    if (mode === "live" && engine.script) {
      const b = engine.script.beats[engine.beat];
      beatEl.textContent = (engine.beat + 1); beatsEl.textContent = engine.script.beats.length;
      amood.textContent = b.mood;
      els.innerHTML = (b.note || "").split(" · ").filter(Boolean).map((n) => `<span class="tag">${n}</span>`).join("");
      rat.textContent = engine.script.rationale || "";
    } else {
      beatEl.textContent = "–"; beatsEl.textContent = "–"; amood.textContent = scene.mood;
      els.innerHTML = '<span class="tag">standalone sim</span><span class="tag">no server</span>';
      rat.textContent = "Switch to “Live engine” to have the Architect compose a personalized script.";
    }
  }
  function updateBeatProgress() {
    const p = document.getElementById("a-prog");
    if (mode === "live" && engine.script) { const b = engine.script.beats[engine.beat]; p.style.width = clamp(engine.beatT / ((b && b.duration_s) || 40)) * 100 + "%"; }
    else p.style.width = "0%";
  }
  function setLearning(count, top) {
    document.getElementById("l-count").textContent = count || 0;
    const el = document.getElementById("l-top");
    if (top && top.length) el.innerHTML = "top scare: <b>" + (top[0][0] || "").replace(/^.*\./, "") + "</b>";
    else el.innerHTML = "";
  }
  let pulseT = 0;
  function showLearnPulse() { const p = document.getElementById("l-pulse"); p.classList.add("on"); pulseT = performance.now() / 1000; }

  // ------------------------------------------------------------- main loop ---
  let mode = "local";
  let last = performance.now() / 1000;
  function loop() {
    const now = performance.now() / 1000; let dt = Math.min(now - last, 0.05); last = now;

    if (mode === "local") localTick(dt, fearSlider(), document.getElementById("auto").checked);
    else advanceScript(dt);

    flickerLevel = 1 - (Math.random() < scene.flicker * 0.25 ? Math.random() * scene.flicker * 0.7 : 0);
    stepMovement(dt); stepMonster(dt); renderWorld();
    heartbeat(now); stinger(); updateAudio();
    trackReaction(now); updateHUD(); updateBeatProgress();
    if (pulseT && now - pulseT > 0.6) { document.getElementById("l-pulse").classList.remove("on"); pulseT = 0; }
    requestAnimationFrame(loop);
  }

  // ------------------------------------------------------------- controls ----
  window.addEventListener("keydown", (e) => { keys[e.key.toLowerCase()] = true; if (e.key === "Escape" && document.pointerLockElement) document.exitPointerLock(); });
  window.addEventListener("keyup", (e) => (keys[e.key.toLowerCase()] = false));
  document.addEventListener("mousemove", (e) => { if (document.pointerLockElement === canvas) player.a += e.movementX * 0.0025; });
  canvas.addEventListener("click", () => canvas.requestPointerLock && canvas.requestPointerLock());

  function setConn(live, text) { document.querySelector("#conn .dot").classList.toggle("live", !!live); document.getElementById("conn-t").textContent = text; }
  const drvLabel = document.getElementById("drv");
  document.getElementById("fear").addEventListener("input", () => (drvLabel.textContent = (fearSlider() * 100).toFixed(0) + "%"));
  function syncModeButtons() {
    document.getElementById("m-local").classList.toggle("active", mode === "local");
    document.getElementById("m-live").classList.toggle("active", mode === "live");
    document.getElementById("urlbox").style.display = mode === "live" ? "block" : "none";
    updateArchitectHUD();
  }
  document.getElementById("m-local").onclick = () => { mode = "local"; disconnectEngine(); currentSpace = null; rebuildLevel("corridor", "local"); setConn(false, "local simulation"); syncModeButtons(); };
  document.getElementById("m-live").onclick = () => { mode = "live"; syncModeButtons(); connectEngine(document.getElementById("engineUrl").value); };
  document.getElementById("engineUrl").addEventListener("change", (e) => { if (mode === "live") connectEngine(e.target.value); });
  if (location.protocol.startsWith("http")) document.getElementById("engineUrl").value = location.origin;

  document.getElementById("go").onclick = () => { initAudio(); if (AC && AC.state === "suspended") AC.resume(); document.getElementById("start").style.display = "none"; canvas.requestPointerLock && canvas.requestPointerLock(); };

  // boot
  rebuildLevel("corridor", "local");
  syncModeButtons();
  requestAnimationFrame(loop);

  window.__game = { scene, player, monster, engine, get mode() { return mode; }, set mode(m) { mode = m; } };
})();
