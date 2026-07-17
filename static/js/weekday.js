/* ============================================================
   DORM WIRE — Weekday Dashboard (frontend logic)

   Live version of previews/weekday_preview.html. Fetches one
   aggregated payload:
     GET /api/weekday/today -> { quote, weather, schedules, markets, news }
   Weather + quote of the day are always live (no key). Schedules,
   markets, and news go live once the iCal URLs / Finnhub /
   Alpha Vantage keys are set; until then the backend sends
   sample data (demo:true) so nothing blanks.
   ============================================================ */

const REFRESH_MS = 120_000;   // weekday feeds move slowly
const RAIL_ROTATE_MS = 5_000;

let data = {};
let railView = 0;
let railTimer = null;

const $ = (id) => document.getElementById(id);
function esc(v) {
  return String(v == null ? "" : v)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

/* ---------------- quote ---------------- */
function renderQuote(q) {
  if (!q) return;
  $("quote").innerHTML = `<span class="q-tag">QUOTE OF THE DAY</span>`
    + `<span class="q-text">&ldquo;${esc(q.t)}&rdquo;</span>`
    + `<span class="q-by">- ${esc(q.by)}</span>`
    + `<span class="q-cat">${esc(q.catName || "")}</span>`;
}

/* ---------------- schedules ---------------- */
function renderSched(el, list) {
  if (!list || !list.length) {
    el.innerHTML = `<div class="srow"><span class="sc">No events today</span></div>`;
    return;
  }
  el.innerHTML = list.map((r) =>
    `<div class="srow ${r.now ? "now" : ""}"><span class="st">${esc(r.time)}</span>`
    + `<span class="sc">${esc(r.title)}</span><span class="sr">${esc(r.room)}</span></div>`).join("");
}

/* ---------------- weather ---------------- */
function renderWeather(w) {
  if (!w) return;
  $("wx-temp").innerHTML = `${esc(w.temp)}&deg;`;
  $("wx-cond").textContent = w.condition || "";
  $("wx-hilo").innerHTML = `HI ${esc(w.hi)}&deg; · LO ${esc(w.lo)}&deg; · WIND ${esc(w.wind)} MPH · RAIN ${esc(w.precip)}%`;
  $("wxnow").innerHTML = `${esc(w.location || "HURST 11")} · ${esc(w.temp)}&deg;F`;
  $("wxhours").innerHTML = (w.hours || []).map((h) =>
    `<div class="wx-hr"><div class="h">${esc(h.h)}</div><div class="t">${esc(h.t)}</div>`
    + `<div class="c">${esc(h.c)}</div></div>`).join("");
}

/* ---------------- rail (portfolio / watchlist) ---------------- */
function renderRail() {
  const m = data.markets || {};
  const dots = `<span class="dot ${railView === 0 ? "on" : ""}"></span>`
    + `<span class="dot ${railView === 1 ? "on" : ""}"></span>`;
  if (railView === 0 && m.portfolio) {
    const rows = (m.portfolio.rows || []).map((r) =>
      `<div class="hrow"><span class="sym">${esc(r.symbol)}</span><span class="shr">${esc(r.shares)}</span>`
      + `<span class="prc">${esc(r.price)}</span><span class="chg ${r.up ? "up" : "dn"}">${esc(r.changePct)}</span></div>`).join("");
    $("rail").innerHTML = `<div class="rhead"><span class="rtitle">MY PORTFOLIO</span><span class="dots">${dots}</span></div>`
      + `<div class="rtot"><span class="v">${esc(m.portfolio.total)}</span>`
      + `<span class="d ${m.portfolio.up ? "up" : "dn"}">${esc(m.portfolio.day)}</span></div>`
      + `<div class="rlist">${rows}</div>`;
  } else if (m.watchlist) {
    const rows = (m.watchlist.rows || []).map((r) =>
      `<div class="hrow"><span class="sym">${esc(r.symbol)}</span><span class="shr"></span>`
      + `<span class="prc">${esc(r.price)}</span><span class="chg ${r.up ? "up" : "dn"}">${esc(r.changePct)}</span></div>`).join("");
    $("rail").innerHTML = `<div class="rhead"><span class="rtitle">WATCHLIST</span><span class="dots">${dots}</span></div>`
      + `<div class="rlist" style="margin-top:.4vh">${rows}</div>`;
  }
}

/* ---------------- news strip + ribbon ---------------- */
function renderNews(news) {
  const items = (news && news.items) || [];
  const one = items.map((n) =>
    `<span class="ns-item"><span class="cat ${esc((n.cat || "").toLowerCase())}">${esc(n.cat)}</span>${esc(n.text)}</span>`).join("");
  $("news").innerHTML = one + one;
}
function renderRibbon(markets) {
  const rows = (markets && markets.ribbon) || [];
  const one = rows.map((s) =>
    `<span class="rb-item"><span class="s">${esc(s.symbol)}</span> ${esc(s.price)} `
    + `<span class="${s.up ? "up" : "dn"}">${s.up ? "▲" : "▼"}${esc(s.changePct)}</span></span>`).join("");
  $("ribbon").innerHTML = one + one;
}

/* ---------------- clock ---------------- */
function clock() {
  const d = new Date();
  $("clock").textContent = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (!data.dateline) {
    const days = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"];
    const mo = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
    $("dateline").textContent = `${days[d.getDay()]} · ${mo[d.getMonth()]} ${d.getDate()}`;
  }
}

/* ---------------- load ---------------- */
async function load() {
  try {
    const res = await fetch("/api/weekday/today", { cache: "no-store" });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || "weekday fetch failed");
    data = d;
    $("dateline").textContent = d.dateline || $("dateline").textContent;
    renderQuote(d.quote);
    renderSched($("sched-alex"), (d.schedules || {}).alex);
    renderSched($("sched-jordan"), (d.schedules || {}).jordan);
    renderWeather(d.weather);
    renderRail();
    renderNews(d.news);
    renderRibbon(d.markets);
  } catch (err) {
    /* keep last good render; try again next interval */
  }
}

clock();
setInterval(clock, 15_000);
load();
setInterval(load, REFRESH_MS);
railTimer = setInterval(() => { railView = (railView + 1) % 2; renderRail(); }, RAIL_ROTATE_MS);
