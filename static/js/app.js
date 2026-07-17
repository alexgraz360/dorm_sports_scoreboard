/* ============================================================
   DORM WIRE — Retro Arcade Board (frontend logic)

   Consumes the SAME backend contract as the original app:
     GET /api/mlb/today   -> { date, displayDate, generatedAt, games:[...] }
     GET /api/mlb/ticker  -> { items:[{ text, category, source }] }

   Nothing about the API changed. Only the look and the DOM
   class names changed. The Game Focus / pressure / breaking
   logic is carried over from V1.

   If the fetch fails (for example when this file is opened
   directly from disk with no Flask server), the board falls
   back to SAMPLE_PAYLOAD so it still renders a full demo board.
   ============================================================ */

const REFRESH_MS = 60_000;
const FOCUS_ROTATION_MS = 45_000;

/* Vivid per-team accent colors, keyed by MLB abbreviation.
   Dark navy teams are brightened so they glow on the black board. */
const TEAM_COLORS = {
  ARI: "#E3164A", ATL: "#E4224B", BAL: "#FF7A18", BOS: "#E43040",
  CHC: "#3F7BEF", CWS: "#C4CED4", CIN: "#F0263F", CLE: "#FF4155",
  COL: "#8A5CF6", DET: "#FF7A2E", HOU: "#FF8A1E", KC: "#2E7BE4",
  LAA: "#E4123E", LAD: "#3AA0FF", MIA: "#19C3E6", MIL: "#FFC52F",
  MIN: "#FF3B57", NYM: "#FF6A1E", NYY: "#5B8CFF", OAK: "#1FD18B",
  PHI: "#FF3141", PIT: "#FFC530", SD: "#FFC425", SEA: "#2FE0C6",
  SF: "#FF6A2C", STL: "#F0344F", TB: "#5BB8F0", TEX: "#3A7BFF",
  TOR: "#3AA0FF", WSH: "#F0263F", ATH: "#1FD18B",
};
function teamColor(abbrev) {
  return TEAM_COLORS[(abbrev || "").toUpperCase()] || "#23f0ff";
}

let latestGames = [];
let focusPool = [];
let focusIndex = 0;
let focusTimer = null;
let demoMode = false;

const els = {
  clock: document.querySelector("#clock"),
  grid: document.querySelector("#games-grid"),
  ticker: document.querySelector("#ticker-track"),
  tickerWrap: document.querySelector("#ticker"),
  date: document.querySelector("#date-label"),
  liveCount: document.querySelector("#live-count"),
  finalCount: document.querySelector("#final-count"),
  totalCount: document.querySelector("#total-count"),
  lastUpdated: document.querySelector("#last-updated"),
  statusNote: document.querySelector("#status-note"),
};

/* ---------------- helpers (carried from V1) ---------------- */
function updateClock() {
  const now = new Date();
  els.clock.textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function statusClass(game) {
  if (game.isLive) return "live";
  if (game.isFinal) return "final";
  return "scheduled";
}
function scoreOrTime(game, team) {
  if (game.status.abstract === "Preview") return game.startTime;
  return team.score;
}
function scoreDiff(game) { return Math.abs((game.away.score || 0) - (game.home.score || 0)); }
function scoreTotal(game) { return (game.away.score || 0) + (game.home.score || 0); }
function gameSummary(game) {
  if (game.status.abstract === "Preview") return `${game.away.abbrev} @ ${game.home.abbrev} ${game.startTime}`;
  return `${game.away.abbrev} ${game.away.score}, ${game.home.abbrev} ${game.home.score} ${game.inning}`;
}
function winningTeam(game) {
  if (!game.isFinal) return null;
  if ((game.away.score || 0) === (game.home.score || 0)) return null;
  return (game.away.score || 0) > (game.home.score || 0) ? game.away : game.home;
}
function trailingTeam(game) {
  if ((game.away.score || 0) === (game.home.score || 0)) return null;
  return (game.away.score || 0) < (game.home.score || 0) ? game.away : game.home;
}

function gameFocusScore(game) {
  const reasons = [];
  let score = 0;
  const inning = game.currentInning || 0;
  const closeGame = scoreDiff(game) <= 2;
  const scoringPosition = game.bases?.second || game.bases?.third;
  const basesLoaded = game.bases?.first && game.bases?.second && game.bases?.third;

  if (game.isLive) { score += 50; reasons.push("LIVE NOW"); }
  if (game.isYankees) { score += 45; reasons.push("YANKEES WATCH"); }
  if (basesLoaded) { score += 45; reasons.push("BASES LOADED"); }
  else if (scoringPosition) { score += 24; reasons.push("RISP"); }
  if (game.isLive && inning >= 7 && closeGame) { score += 38; reasons.push("LATE + CLOSE"); }
  if (game.isLive && inning > 9) { score += 40; reasons.push("EXTRA INNINGS"); }
  if (game.isLive && scoreTotal(game) >= 12) { score += 18; reasons.push("SLUGFEST"); }
  if (game.status.abstract === "Preview" && game.isYankees) { score += 22; reasons.push("UPCOMING YANKEES"); }
  if (!reasons.length) reasons.push((game.status.detailed || "").toUpperCase());
  return { score, reasons };
}
function buildFocusPool(games) {
  return games
    .map((game) => ({ game, focus: gameFocusScore(game) }))
    .filter((entry) => entry.focus.score > 0 || !entry.game.isFinal)
    .sort((a, b) => b.focus.score - a.focus.score || a.game.sortKey.localeCompare(b.game.sortKey))
    .slice(0, 5);
}

/* ---------------- ticker helpers ---------------- */
function tickerLabel(category = "") {
  if (category.includes("breaking-test")) return "TEST";
  if (category.includes("breaking")) return "BREAKING";
  if (category.includes("pressure")) return "PRESSURE";
  if (category.includes("performer")) return "PERFORMER";
  if (category.includes("news")) return "MLB NEWS";
  return "WIRE";
}
function tickerCategoryClass(category = "") {
  if (category.includes("breaking")) return "breaking";
  if (category.includes("pressure")) return "pressure";
  if (category.includes("performer")) return "performer";
  if (category.includes("news")) return "news";
  return "headline";
}

/* ---------------- rendering ---------------- */
function renderBases(game) {
  const b = game.bases || {};
  return `
    <div class="diamond" aria-label="Bases">
      <span class="base second ${b.second ? "on" : ""}"></span>
      <span class="base third ${b.third ? "on" : ""}"></span>
      <span class="base first ${b.first ? "on" : ""}"></span>
    </div>`;
}
function renderTeamRow(team, value) {
  return `
    <div class="trow">
      ${team.logoUrl ? `<img src="${team.logoUrl}" alt="" aria-hidden="true">` : `<span></span>`}
      <span class="code">${escapeHtml(team.abbrev)}</span>
      <span class="name" title="${escapeHtml(team.name)}">${escapeHtml(team.shortName || team.name)}</span>
      <strong class="score">${value}</strong>
    </div>`;
}
function renderTile(game, featured = false, focusReasons = []) {
  const isPreview = game.status.abstract === "Preview";
  const state = isPreview ? "PREGAME" : (game.status.abstract || "").toUpperCase();
  const detail = isPreview ? game.startTime : game.inning;
  const awayValue = isPreview ? "-" : scoreOrTime(game, game.away);
  const homeValue = isPreview ? "-" : scoreOrTime(game, game.home);
  const countLine = game.isLive
    ? `${game.balls}-${game.strikes} | ${game.outs} OUT${game.outs === 1 ? "" : "S"}`
    : isPreview ? `FIRST PITCH ${game.startTime}` : (game.status.detailed || "").toUpperCase();
  const label = featured ? "GAME FOCUS" : state;
  const accent = teamColor(game.home.abbrev);
  const focusCopy = featured && focusReasons.length
    ? `<div class="focus-reasons">${focusReasons.slice(0, 3).map((r) => `<span>${escapeHtml(r)}</span>`).join("")}</div>`
    : "";

  return `
    <article class="tile ${statusClass(game)} ${featured ? "featured" : ""}" style="--team:${accent}">
      <div class="tile-top">
        <span class="badge">${label}</span>
        <span class="detail">${escapeHtml(detail)}</span>
      </div>
      ${focusCopy}
      <div class="rows">
        ${renderTeamRow(game.away, awayValue)}
        ${renderTeamRow(game.home, homeValue)}
      </div>
      <div class="tile-foot">
        <span class="count">${escapeHtml(countLine)}</span>
        ${renderBases(game)}
      </div>
    </article>`;
}
function renderGrid() {
  if (!latestGames.length) {
    els.grid.innerHTML = `<article class="tile empty"><p>NO MLB GAMES TODAY</p></article>`;
    return;
  }
  const focusEntry = focusPool[focusIndex % Math.max(focusPool.length, 1)]
    || { game: latestGames[0], focus: gameFocusScore(latestGames[0]) };
  const focusGame = focusEntry.game;
  const remaining = latestGames.filter((g) => g.gamePk !== focusGame.gamePk).slice(0, 14);
  els.grid.innerHTML = [
    renderTile(focusGame, true, focusEntry.focus.reasons),
    ...remaining.map((g) => renderTile(g, false)),
  ].join("");
}
function startFocusRotation() {
  if (focusTimer) clearInterval(focusTimer);
  focusTimer = setInterval(() => {
    if (focusPool.length <= 1) return;
    focusIndex = (focusIndex + 1) % focusPool.length;
    renderGrid();
  }, FOCUS_ROTATION_MS);
}

function renderTickerFeed(feed) {
  const items = feed.items || [];
  const lead = items[0]?.category || "";
  const mode = lead.includes("breaking")
    ? "breaking-mode"
    : items.some((i) => (i.category || "").includes("pressure")) ? "pressure-mode" : "headline-mode";
  const rendered = items.length
    ? items.map((item) => {
        const cls = tickerCategoryClass(item.category || "");
        const label = escapeHtml(tickerLabel(item.category || ""));
        const source = escapeHtml(item.source || "");
        return `<span class="ticker-item ${cls}" data-label="${label}" title="${source}">${escapeHtml(item.text)}${source ? `<small>${source}</small>` : ""}</span>`;
      }).join("")
    : `<span class="ticker-item" data-label="WIRE">Ticker feed warming up…</span>`;
  els.tickerWrap.className = `ticker ${mode}`;
  els.ticker.innerHTML = `<span>${rendered}</span><span aria-hidden="true">${rendered}</span>`;
}

/* ---------------- data loading ---------------- */
function applyScores(data) {
  latestGames = data.games || [];
  focusPool = buildFocusPool(latestGames);
  focusIndex = 0;

  const liveCount = latestGames.filter((g) => g.isLive).length;
  const finalCount = latestGames.filter((g) => g.isFinal).length;
  const shown = Math.min(latestGames.length, 15);

  els.date.textContent = (data.displayDate || data.date || "").toUpperCase();
  els.liveCount.textContent = liveCount;
  els.finalCount.textContent = finalCount;
  els.totalCount.textContent = latestGames.length;
  els.statusNote.textContent = demoMode
    ? "DEMO DATA — OFFLINE PREVIEW"
    : latestGames.length ? `${shown} SHOWN · FOCUS ROTATES BY PRESSURE` : "NO GAMES ON THIS DATE";
  els.lastUpdated.textContent = demoMode
    ? "PREVIEW"
    : `UPDATED ${new Date(data.generatedAt || Date.now()).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;

  renderGrid();
  startFocusRotation();
}

async function loadScores() {
  try {
    const res = await fetch("/api/mlb/today", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "score fetch failed");
    demoMode = false;
    applyScores(data);
    loadTicker();
  } catch (err) {
    // Offline / no server: fall back to bundled demo so the board still shows.
    demoMode = true;
    applyScores(SAMPLE_PAYLOAD);
    renderTickerFeed(SAMPLE_TICKER);
  }
}
async function loadTicker() {
  try {
    const res = await fetch("/api/mlb/ticker", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "ticker fetch failed");
    renderTickerFeed(data);
  } catch (err) {
    renderTickerFeed(SAMPLE_TICKER);
  }
}

/* ============================================================
   SAMPLE DATA — only used when the API is unreachable.
   Matches the real /api contract exactly.
   ============================================================ */
const L = (id) => `https://www.mlbstatic.com/team-logos/${id}.svg`;
const SAMPLE_PAYLOAD = {
  date: "2026-07-05",
  displayDate: "Saturday, July 5",
  generatedAt: new Date().toISOString(),
  games: [
    { gamePk: 1, sortKey: "a", isLive: true, isFinal: false, isYankees: true,
      status: { abstract: "Live", detailed: "In Progress" },
      away: { abbrev: "BOS", name: "Boston Red Sox", shortName: "Red Sox", score: 3, logoUrl: L(111) },
      home: { abbrev: "NYY", name: "New York Yankees", shortName: "Yankees", score: 4, logoUrl: L(147) },
      inning: "BOT 8TH", currentInning: 8, inningState: "Bottom", startTime: "7:05 PM",
      venue: "Yankee Stadium", balls: 2, strikes: 1, outs: 1, bases: { first: true, second: true, third: true } },
    { gamePk: 2, sortKey: "b", isLive: true, isFinal: false, isYankees: false,
      status: { abstract: "Live", detailed: "In Progress" },
      away: { abbrev: "LAD", name: "Los Angeles Dodgers", shortName: "Dodgers", score: 6, logoUrl: L(119) },
      home: { abbrev: "SF", name: "San Francisco Giants", shortName: "Giants", score: 5, logoUrl: L(137) },
      inning: "TOP 9TH", currentInning: 9, inningState: "Top", startTime: "9:45 PM",
      venue: "Oracle Park", balls: 1, strikes: 2, outs: 2, bases: { first: false, second: true, third: false } },
    { gamePk: 3, sortKey: "c", isLive: true, isFinal: false, isYankees: false,
      status: { abstract: "Live", detailed: "In Progress" },
      away: { abbrev: "HOU", name: "Houston Astros", shortName: "Astros", score: 2, logoUrl: L(117) },
      home: { abbrev: "ATL", name: "Atlanta Braves", shortName: "Braves", score: 2, logoUrl: L(144) },
      inning: "MID 6TH", currentInning: 6, inningState: "Middle", startTime: "7:20 PM",
      venue: "Truist Park", balls: 0, strikes: 0, outs: 0, bases: { first: false, second: false, third: false } },
    { gamePk: 4, sortKey: "d", isLive: false, isFinal: true, isYankees: false,
      status: { abstract: "Final", detailed: "Final" },
      away: { abbrev: "CHC", name: "Chicago Cubs", shortName: "Cubs", score: 7, logoUrl: L(112) },
      home: { abbrev: "PHI", name: "Philadelphia Phillies", shortName: "Phillies", score: 6, logoUrl: L(143) },
      inning: "FINAL", currentInning: 9, inningState: "End", startTime: "1:05 PM",
      venue: "Citizens Bank Park", balls: 0, strikes: 0, outs: 0, bases: {} },
    { gamePk: 5, sortKey: "e", isLive: false, isFinal: true, isYankees: false,
      status: { abstract: "Final", detailed: "Final/10" },
      away: { abbrev: "SD", name: "San Diego Padres", shortName: "Padres", score: 4, logoUrl: L(135) },
      home: { abbrev: "SEA", name: "Seattle Mariners", shortName: "Mariners", score: 5, logoUrl: L(136) },
      inning: "FINAL/10", currentInning: 10, inningState: "End", startTime: "4:10 PM",
      venue: "T-Mobile Park", balls: 0, strikes: 0, outs: 0, bases: {} },
    { gamePk: 6, sortKey: "f", isLive: false, isFinal: false, isYankees: false,
      status: { abstract: "Preview", detailed: "Scheduled" },
      away: { abbrev: "TB", name: "Tampa Bay Rays", shortName: "Rays", score: 0, logoUrl: L(139) },
      home: { abbrev: "BAL", name: "Baltimore Orioles", shortName: "Orioles", score: 0, logoUrl: L(110) },
      inning: "", currentInning: 0, inningState: "", startTime: "7:35 PM",
      venue: "Camden Yards", balls: 0, strikes: 0, outs: 0, bases: {} },
    { gamePk: 7, sortKey: "g", isLive: false, isFinal: false, isYankees: false,
      status: { abstract: "Preview", detailed: "Scheduled" },
      away: { abbrev: "NYM", name: "New York Mets", shortName: "Mets", score: 0, logoUrl: L(121) },
      home: { abbrev: "MIA", name: "Miami Marlins", shortName: "Marlins", score: 0, logoUrl: L(146) },
      inning: "", currentInning: 0, inningState: "", startTime: "6:40 PM",
      venue: "loanDepot park", balls: 0, strikes: 0, outs: 0, bases: {} },
    { gamePk: 8, sortKey: "h", isLive: false, isFinal: true, isYankees: false,
      status: { abstract: "Final", detailed: "Final" },
      away: { abbrev: "STL", name: "St. Louis Cardinals", shortName: "Cardinals", score: 2, logoUrl: L(138) },
      home: { abbrev: "CIN", name: "Cincinnati Reds", shortName: "Reds", score: 8, logoUrl: L(113) },
      inning: "FINAL", currentInning: 9, inningState: "End", startTime: "1:10 PM",
      venue: "Great American Ball Park", balls: 0, strikes: 0, outs: 0, bases: {} },
  ],
};
const SAMPLE_TICKER = {
  items: [
    { text: "Bases loaded, Yankees cling to a 4-3 lead in the 8th", category: "pressure", source: "game state" },
    { text: "Dodgers-Giants headed to the 9th, LA up by one", category: "pressure", source: "game state" },
    { text: "Judge 2-for-3 with a solo shot and 2 walks", category: "performer", source: "box score" },
    { text: "Final: Cubs edge Phillies 7-6 in a back-and-forth one", category: "news", source: "MLB" },
    { text: "Reds pour it on late, roll the Cardinals 8-2", category: "news", source: "MLB" },
  ],
};

/* ---------------- boot (runs last, after SAMPLE data exists) ---------------- */
updateClock();
loadScores();
setInterval(updateClock, 1_000);
setInterval(loadScores, REFRESH_MS);
