/* ============================================================
   DORM WIRE — Football Board (NFL / CFB, frontend logic)

   Live version of previews/football_preview.html and
   college_preview.html. Reads <body data-league> (nfl|cfb) and
   fetches the matching backend contract:
     GET /api/<league>/today   -> { games:[...], displayDate }
     GET /api/<league>/ticker  -> { items:[...] }

   Football tile footer (down & distance, possession arrow,
   red-zone flag) is keyed off each game's `situation`. Team
   accent colors come from the backend (`team.accent`), with a
   cyan fallback.
   ============================================================ */

const LEAGUE = (document.body.dataset.league || "nfl").toLowerCase();
const REFRESH_MS = 30_000;
const FOCUS_ROTATION_MS = 12_000;

let games = [];
let payload = {};
let focusPool = [];
let focusIndex = 0;
let focusTimer = null;

const el = (s) => document.querySelector(s);
function esc(v) {
  return String(v == null ? "" : v)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function accent(t) { return t.accent || "#23f0ff"; }
function stateClass(g) { return g.isLive ? "live" : g.isFinal ? "final" : "scheduled"; }

/* ---------------- tile pieces ---------------- */
function teamRow(g, t, featured) {
  const sit = g.situation || {};
  const isPoss = sit.possession && sit.possession === t.abbrev;
  const poss = `<span class="poss ${isPoss ? "" : "off"}">&#9654;</span>`;
  const rank = t.rank ? `<span class="rank">${esc(t.rank)}</span>` : `<span></span>`;
  const val = g.status.abstract === "Preview" ? "-" : t.score;
  return `<div class="trow">${poss}${rank}`
    + `<span class="code" style="color:${esc(accent(t))}">${esc(t.abbrev)}</span>`
    + `<span class="name">${featured ? esc(t.shortName || t.name) : ""}</span>`
    + `<strong class="score">${esc(val)}</strong></div>`;
}
function fieldHTML(g) {
  const sit = g.situation;
  if (!g.isLive || !sit || !sit.possession) return "";
  const yard = Number(sit.yard);
  const y = Number.isFinite(yard) ? yard : 50;
  const rzSide = y > 50 ? "right" : "left";
  return `<div class="field">`
    + `<span class="ez" style="--c:${esc(accent(g.away))}">${esc(g.away.abbrev)}</span>`
    + `<div class="turf">${sit.redZone ? `<span class="rz ${rzSide}"></span>` : ""}`
    + `<span class="ball" style="left:${y}%"><i></i></span></div>`
    + `<span class="ez" style="--c:${esc(accent(g.home))}">${esc(g.home.abbrev)}</span></div>`;
}
function footHTML(g) {
  const sit = g.situation || {};
  let line;
  if (g.isLive && (sit.downDistance || sit.ballOn)) {
    line = [sit.downDistance, sit.ballOn].filter(Boolean).join(" · ");
  } else if (g.status.abstract === "Preview") {
    line = "KICKOFF " + (g.startTime || "");
  } else {
    line = g.isLive ? (g.detail || "LIVE") : "FINAL";
  }
  const rz = (g.isLive && sit.redZone) ? `<span class="rzflag">RED ZONE</span>` : "";
  return `<div class="tile-foot"><span class="count">${esc(line)}</span>${rz}</div>`;
}
function tile(g, featured) {
  const acc = accent(g.home.fav ? g.home : (g.away.fav ? g.away : g.home));
  const label = featured ? "GAME FOCUS"
    : (g.status.abstract === "Preview" ? "PREGAME" : g.status.abstract.toUpperCase());
  const reasons = (featured && g.focusReasons && g.focusReasons.length)
    ? `<div class="focus-reasons">${g.focusReasons.slice(0, 4).map((x) => `<span>${esc(x)}</span>`).join("")}</div>`
    : "";
  return `<article class="tile ${stateClass(g)} ${featured ? "featured" : ""}" style="--team:${esc(acc)}">`
    + `<div class="tile-top"><span class="badge">${label}</span><span class="detail">${esc(g.detail || "")}</span></div>`
    + reasons
    + `<div class="rows">${teamRow(g, g.away, featured)}${teamRow(g, g.home, featured)}</div>`
    + (featured ? fieldHTML(g) : "")
    + footHTML(g)
    + `</article>`;
}

/* ---------------- focus rotation ---------------- */
function buildPool() {
  focusPool = games
    .map((g) => ({ g, s: g.focusScore || 0 }))
    .filter((e) => e.s > 0 || !e.g.isFinal)
    .sort((a, b) => b.s - a.s)
    .slice(0, 5);
  if (!focusPool.length && games.length) focusPool = [{ g: games[0], s: 0 }];
}
function renderGrid() {
  if (!games.length) {
    el("#games-grid").innerHTML = `<article class="tile"><span>NO GAMES TODAY</span></article>`;
    return;
  }
  const focus = focusPool[focusIndex % Math.max(focusPool.length, 1)].g;
  // Narrower grid (fantasy sidebar takes the right column): show fewer tiles.
  const rest = games.filter((g) => g.id !== focus.id).slice(0, 8);
  el("#games-grid").innerHTML = [tile(focus, true), ...rest.map((g) => tile(g, false))].join("");
}

/* ---------------- ticker ---------------- */
function renderTicker(feed) {
  const items = feed.items || [];
  const lead = (items[0] && items[0].category) || "";
  const mode = lead.includes("breaking") ? "breaking-mode"
    : items.some((i) => (i.category || "").includes("pressure")) ? "pressure-mode" : "headline-mode";
  const rendered = items.length
    ? items.map((i) => {
        const cat = i.category || "";
        const cls = cat.includes("breaking") ? "breaking" : cat.includes("pressure") ? "pressure" : "news";
        const lab = cat.includes("breaking") ? "BREAKING" : cat.includes("pressure") ? "PRESSURE" : LEAGUE.toUpperCase();
        return `<span class="ticker-item ${cls}" data-label="${lab}">${esc(i.text)}`
          + (i.source ? `<small>${esc(i.source)}</small>` : "") + `</span>`;
      }).join("")
    : `<span class="ticker-item" data-label="${LEAGUE.toUpperCase()}">Wire warming up…</span>`;
  el("#ticker").className = `ticker ${mode}`;
  el("#ticker-track").innerHTML = `<span>${rendered}</span><span aria-hidden="true">${rendered}</span>`;
}

/* ---------------- fantasy rail + wire + TD animation ---------------- */
let fantasyCards = [];   // flattened (person, league) entries
let fantasyIndex = 0;
let fantasyTimer = null;
let seenTds = new Set();
let fantasyPrimed = false;

function renderFantasyRail() {
  const box = el("#frail");
  if (!box) return;
  if (!fantasyCards.length) {
    box.innerHTML = `<div class="fr-head"><span class="fr-title">FANTASY</span></div>`
      + `<div class="fr-row"><span class="fr-pname">No leagues connected</span></div>`;
    return;
  }
  const c = fantasyCards[fantasyIndex % fantasyCards.length];
  const g = c.league;
  const meWin = g.me.points >= g.opp.points;
  const dots = fantasyCards.map((_, i) =>
    `<span class="fr-dot ${i === fantasyIndex % fantasyCards.length ? "on" : ""}"></span>`).join("");
  const seasonTag = g.current === false && g.season ? ` '${String(g.season).slice(2)}` : "";
  const starters = (g.me.starters || []).slice(0, 10).map((s) =>
    `<div class="fr-row"><span class="fr-pos">${esc(s.pos)}</span>`
    + `<span class="fr-pname">${esc(s.name)}</span><span class="fr-ppts">${esc(s.points)}</span></div>`).join("");
  box.innerHTML =
    `<div class="fr-head"><span class="fr-title">${esc(c.person)} · FANTASY</span>`
    + `<span class="fr-plat ${esc(g.platform || "sleeper")}">${esc((g.platform || "sleeper").toUpperCase())}</span></div>`
    + `<div class="fr-league">${esc(g.league)}${seasonTag} · WK ${esc(g.week)}</div>`
    + `<div class="fr-score">`
    + `<div class="fr-team ${meWin ? "fr-win" : ""}"><span class="fr-nm">${esc(g.me.name)}</span><span class="fr-pts">${esc(g.me.points)}</span></div>`
    + `<span class="fr-vs">VS</span>`
    + `<div class="fr-team opp ${!meWin ? "fr-win" : ""}"><span class="fr-nm">${esc(g.opp.name)}</span><span class="fr-pts">${esc(g.opp.points)}</span></div>`
    + `</div>`
    + `<div class="fr-list">${starters}</div>`
    + `<div class="fr-dots">${dots}</div>`;
}

function renderFantasyWire(wire) {
  const box = el("#fwire");
  if (!box) return;
  const items = (wire && wire.items) || [];
  const rows = items.slice(0, 6).map((i) => {
    const kind = (i.kind || "score");
    return `<div class="fw-item"><span class="fw-tag ${esc(kind)}">${esc(kind.toUpperCase())}</span>`
      + `<span>${esc(i.text)}</span></div>`;
  }).join("");
  box.innerHTML = `<div class="fw-title">FANTASY WIRE</div>`
    + `<div class="fw-list">${rows || '<div class="fw-item"><span>Quiet on the wire…</span></div>'}</div>`;
  // Fire the TD animation for any touchdown we haven't shown yet. The real
  // per-type scene lives in td_animation.js as window.fireTdAnimation(kind,…).
  const tds = items.filter((i) => (i.kind || "") === "td");
  for (const td of tds) {
    if (!seenTds.has(td.text)) {
      seenTds.add(td.text);
      if (fantasyPrimed) playTd(td);
    }
  }
  // On the very first load, don't retro-fire for every pre-existing TD — but
  // do show one so the effect is visible, then only fire on genuinely new TDs.
  if (!fantasyPrimed) {
    fantasyPrimed = true;
    if (tds.length) playTd(tds[0]);
  }
}

// Resolve a wire TD item to the animation's play type. Use an explicit field
// if the backend supplies one (detect_touchdowns kind: passing/rushing/
// receiving); otherwise infer from the wire text.
function tdKind(td) {
  const explicit = (td.tdType || td.playType || "").toLowerCase();
  if (["passing", "rushing", "receiving"].includes(explicit)) return explicit;
  const t = (td.text || "").toLowerCase();
  if (/\b(pass|passing|threw|td pass|through the air)\b/.test(t)) return "passing";
  if (/\b(reception|receiving|catch|caught|grab|hauls? in|td catch)\b/.test(t)) return "receiving";
  return "rushing";
}
function playTd(td) {
  const player = td.player || (td.text || "").replace(/^TOUCHDOWN:\s*/i, "");
  if (typeof window.fireTdAnimation === "function") window.fireTdAnimation(tdKind(td), player);
}

async function loadFantasy() {
  try {
    const [rail, wire] = await Promise.all([
      fetch("/api/fantasy/rail", { cache: "no-store" }).then((r) => r.json()),
      fetch("/api/fantasy/wire", { cache: "no-store" }).then((r) => r.json()),
    ]);
    fantasyCards = (rail.people || []).flatMap((p) =>
      (p.leagues || []).map((lg) => ({ person: p.person, league: lg })))
      // Skip empty/inactive leagues (no lineup and no points) so the rail only
      // rotates through active teams.
      .filter((c) => (c.league.me.starters || []).length > 0
        || c.league.me.points > 0 || c.league.opp.points > 0);
    if (fantasyIndex >= fantasyCards.length) fantasyIndex = 0;
    renderFantasyRail();
    renderFantasyWire(wire);
  } catch (err) {
    /* leave last render */
  }
}

/* ---------------- counters + clock ---------------- */
function renderCounts() {
  el("#total-count").textContent = games.length;
  el("#live-count").textContent = games.filter((g) => g.isLive).length;
  el("#final-count").textContent = games.filter((g) => g.isFinal).length;
  el("#date-label").textContent = (payload.displayDate || "").toUpperCase() || (LEAGUE.toUpperCase() + " SLATE");
}
function clock() {
  el("#clock").textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/* ---------------- data loading ---------------- */
async function loadScores() {
  try {
    const res = await fetch(`/api/${LEAGUE}/today`, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "score fetch failed");
    payload = data;
    games = data.games || [];
    buildPool();
    focusIndex = 0;
    renderCounts();
    renderGrid();
    el("#last-updated").textContent = "UPDATED " + new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    el("#status-note").textContent = games.length ? "GAME FOCUS ROTATES BY PRESSURE" : "NO GAMES ON THE SLATE";
  } catch (err) {
    el("#status-note").textContent = "FEED OFFLINE — RETRYING";
    el("#last-updated").textContent = "OFFLINE";
  }
}
async function loadTicker() {
  try {
    const res = await fetch(`/api/${LEAGUE}/ticker`, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "ticker fetch failed");
    renderTicker(data);
  } catch (err) {
    renderTicker({ items: [] });
  }
}

const FANTASY_ROTATE_MS = 8_000;
function startTimers() {
  clearInterval(focusTimer);
  focusTimer = setInterval(() => {
    if (focusPool.length > 1) { focusIndex = (focusIndex + 1) % focusPool.length; renderGrid(); }
  }, FOCUS_ROTATION_MS);
  clearInterval(fantasyTimer);
  fantasyTimer = setInterval(() => {
    if (fantasyCards.length > 1) { fantasyIndex = (fantasyIndex + 1) % fantasyCards.length; renderFantasyRail(); }
  }, FANTASY_ROTATE_MS);
}

clock();
setInterval(clock, 15_000);
loadScores();
loadTicker();
loadFantasy();
startTimers();
setInterval(loadScores, REFRESH_MS);
setInterval(loadTicker, REFRESH_MS);
setInterval(loadFantasy, REFRESH_MS);
