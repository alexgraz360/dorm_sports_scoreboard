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
  const rest = games.filter((g) => g.id !== focus.id).slice(0, 14);
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

function startTimers() {
  clearInterval(focusTimer);
  focusTimer = setInterval(() => {
    if (focusPool.length > 1) { focusIndex = (focusIndex + 1) % focusPool.length; renderGrid(); }
  }, FOCUS_ROTATION_MS);
}

clock();
setInterval(clock, 15_000);
loadScores();
loadTicker();
startTimers();
setInterval(loadScores, REFRESH_MS);
setInterval(loadTicker, REFRESH_MS);
