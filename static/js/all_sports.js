/* ============================================================
   DORM WIRE — All-Sports Board (frontend logic)

   Live version of previews/all_sports_preview.html. Instead of
   embedded demo data it consumes the aggregated backend contract:
     GET /api/all/today  -> { games:[...], liveCount, sportCount, displayDate }
     GET /api/all/ticker -> { items:[{ text, category, source }] }

   Each game carries: sport, away/home {abbrev,shortName,score,accent,fav},
   detail, isLive, isFinal, flag, hot, focusReasons, leaders, viz, winProb.
   Everything after the score row is optional and degrades cleanly.
   ============================================================ */

const REFRESH_MS = 60_000;
const FOCUS_ROTATION_MS = 6_500;
const SB_ROTATION_MS = 5_000;

let games = [];
let payload = {};
let focusPool = [];
let focusIndex = 0;
let sbPage = 0;
let focusTimer = null;
let sbTimer = null;

const el = (s) => document.querySelector(s);
function esc(v) {
  return String(v == null ? "" : v)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function stateClass(g) { return g.isLive ? "live" : g.isFinal ? "final" : "scheduled"; }

/* ---------------- tile pieces ---------------- */
function teamRow(g, t, featured) {
  const star = `<span class="star ${t.fav ? "" : "off"}">&#9733;</span>`;
  const val = (g.isFinal || g.isLive) ? t.score : "-";
  return `<div class="trow">${star}`
    + `<span class="code" style="color:${esc(t.accent)}">${esc(t.abbrev)}</span>`
    + `<span class="name">${featured ? esc(t.shortName || t.name) : ""}</span>`
    + `<strong class="score">${esc(val)}</strong></div>`;
}
function vizHTML(g) {
  const v = g.viz;
  if (!v) return "";
  let graphic = "";
  if (v.k === "mlb") {
    const b = v.bases || {};
    graphic = `<div class="diamond"><span class="base second ${b.second ? "on" : ""}"></span>`
      + `<span class="base third ${b.third ? "on" : ""}"></span>`
      + `<span class="base first ${b.first ? "on" : ""}"></span></div>`;
  } else if (v.k === "nfl" || v.k === "cfb") {
    graphic = `<div class="ffield"><span class="rz"></span>`
      + `<span class="fball" style="left:${Number(v.yard) || 60}%"></span></div>`;
  } else {
    return "";
  }
  return `<div class="viz">${graphic}<span class="vlabel">${esc(v.extra || "")}</span></div>`;
}
function wpHTML(g) {
  const wp = g.winProb;
  if (!wp || typeof wp.home !== "number") return "";
  const h = wp.home, a = 100 - h;
  return `<div class="wp"><div class="wp-bar">`
    + `<i style="width:${a}%;background:${esc(g.away.accent)}"></i>`
    + `<i style="width:${h}%;background:${esc(g.home.accent)}"></i></div>`
    + `<div class="wp-lbl"><span>${esc(g.away.abbrev)} ${a}%</span><span>WIN PROB</span>`
    + `<span>${esc(g.home.abbrev)} ${h}%</span></div></div>`;
}
function leadersHTML(g, featured) {
  if (!g.leaders || !g.leaders.length) return "";
  const key = featured ? `<span class="lg-key">LEADERS</span>` : "";
  const parts = g.leaders.map((l) => `<b>${esc(l[0])}</b> ${esc(l[1])}`).join(" &middot; ");
  return `<div class="leaders">${key}${parts}</div>`;
}
function tile(g, featured) {
  const accent = g.home.fav ? g.home.accent : (g.away.fav ? g.away.accent : g.home.accent);
  const reasons = (featured && g.focusReasons && g.focusReasons.length)
    ? `<div class="focus-reasons">${g.focusReasons.slice(0, 4).map((x) => `<span>${esc(x)}</span>`).join("")}</div>`
    : "";
  const flag = g.flag ? `<span class="flag ${g.hot ? "hot" : ""}">${esc(g.flag)}</span>` : "";
  const body = featured
    ? reasons + `<div class="rows">${teamRow(g, g.away, true)}${teamRow(g, g.home, true)}</div>`
      + vizHTML(g) + wpHTML(g) + leadersHTML(g, true)
    : `<div class="rows">${teamRow(g, g.away, false)}${teamRow(g, g.home, false)}</div>`
      + leadersHTML(g, false);
  const detail = esc(g.detail || "");
  const foot = featured
    ? `<div class="tile-foot"><span class="count">${esc(g.sport.toUpperCase())} · ${detail}</span>${flag}</div>`
    : `<div class="tile-foot"><span class="count">${g.isFinal ? "FINAL" : detail}</span>${flag}</div>`;
  return `<article class="tile ${stateClass(g)} ${featured ? "featured" : ""}" style="--team:${esc(accent)}">`
    + `<div class="tile-top"><span class="league lg-${esc(g.sport)}">${esc(g.sport.toUpperCase())}</span>`
    + `<span class="detail">${featured ? "GAME FOCUS" : detail}</span></div>`
    + body + foot + `</article>`;
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
    el("#games-grid").innerHTML = `<article class="tile"><span>NO GAMES RIGHT NOW</span></article>`;
    return;
  }
  const focus = focusPool[focusIndex % Math.max(focusPool.length, 1)].g;
  const rest = games.filter((g) => g.id !== focus.id).slice(0, 8);
  el("#games-grid").innerHTML = [tile(focus, true), ...rest.map((g) => tile(g, false))].join("");
}

/* ---------------- sidebar: "ALSO ON" ---------------- */
function renderSidebar() {
  // Group every game by league; rotate a 3-game window per league.
  const byLeague = {};
  for (const g of games) (byLeague[g.sport] ||= []).push(g);
  const perLeague = 3;
  const sections = Object.entries(byLeague).map(([lg, list]) => {
    const n = list.length;
    const start = (sbPage * perLeague) % n;
    const rows = [];
    for (let i = 0; i < Math.min(perLeague, n); i++) {
      const g = list[(start + i) % n];
      const st = g.isFinal ? "FINAL" : (g.isLive ? g.detail : g.startTime);
      const fin = g.isFinal ? "fin" : "";
      rows.push(`<div class="pg"><span class="teams">${esc(g.away.abbrev)} ${esc(g.isLive || g.isFinal ? g.away.score : "")} `
        + `&middot; ${esc(g.home.abbrev)} ${esc(g.isLive || g.isFinal ? g.home.score : "")}</span>`
        + `<span class="st ${fin}">${esc(st)}</span></div>`);
    }
    return `<div class="sb-section"><div class="sb-lg ${esc(lg)}">${esc(lg.toUpperCase())}</div>${rows.join("")}</div>`;
  }).join("");
  el("#sidebar").innerHTML = `<div class="sb-head"><span class="sb-title">ALSO ON</span>`
    + `<span class="sb-sub">ROTATES</span></div><div class="sb-body">${sections || ""}</div>`;
}

/* ---------------- ticker ---------------- */
function renderTicker(feed) {
  const items = feed.items || [];
  const rendered = items.length
    ? items.map((i) => {
        const cls = (i.category || "") === "hot" ? "hot" : "";
        const lab = (i.category || "") === "hot" ? "HOT" : "WIRE";
        return `<span class="ticker-item ${cls}" data-label="${lab}">${esc(i.text)}`
          + (i.source ? `<small>${esc(i.source)}</small>` : "") + `</span>`;
      }).join("")
    : `<span class="ticker-item" data-label="WIRE">Wire warming up…</span>`;
  el("#ticker-track").innerHTML = `<span>${rendered}</span><span aria-hidden="true">${rendered}</span>`;
}

/* ---------------- counters + clock ---------------- */
function renderCounts() {
  el("#total-count").textContent = games.length;
  el("#live-count").textContent = payload.liveCount ?? games.filter((g) => g.isLive).length;
  el("#sport-count").textContent = payload.sportCount ?? new Set(games.map((g) => g.sport)).size;
  el("#date-label").textContent = (payload.displayDate || "").toUpperCase() || "TONIGHT";
}
function clock() {
  el("#clock").textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

/* ---------------- data loading ---------------- */
async function loadScores() {
  try {
    const res = await fetch("/api/all/today", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "score fetch failed");
    payload = data;
    games = data.games || [];
    buildPool();
    focusIndex = 0;
    renderCounts();
    renderGrid();
    renderSidebar();
    el("#last-updated").textContent = "UPDATED " + new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    el("#status-note").textContent = games.length ? "BEST GAMES ACROSS EVERY SPORT" : "NO GAMES LIVE RIGHT NOW";
  } catch (err) {
    el("#status-note").textContent = "FEED OFFLINE — RETRYING";
    el("#last-updated").textContent = "OFFLINE";
  }
}
async function loadTicker() {
  try {
    const res = await fetch("/api/all/ticker", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "ticker fetch failed");
    renderTicker(data);
  } catch (err) {
    renderTicker({ items: [] });
  }
}

function startTimers() {
  clearInterval(focusTimer);
  clearInterval(sbTimer);
  focusTimer = setInterval(() => {
    if (focusPool.length > 1) { focusIndex = (focusIndex + 1) % focusPool.length; renderGrid(); }
  }, FOCUS_ROTATION_MS);
  sbTimer = setInterval(() => { sbPage = (sbPage + 1) % 3; renderSidebar(); }, SB_ROTATION_MS);
}

clock();
setInterval(clock, 15_000);
loadScores();
loadTicker();
startTimers();
setInterval(loadScores, REFRESH_MS);
setInterval(loadTicker, REFRESH_MS);
