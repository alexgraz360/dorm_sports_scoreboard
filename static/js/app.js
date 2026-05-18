const REFRESH_MS = 60_000;
const FOCUS_ROTATION_MS = 45_000;

let latestGames = [];
let focusPool = [];
let focusIndex = 0;
let focusTimer = null;

const els = {
  clock: document.querySelector("#clock"),
  grid: document.querySelector("#games-grid"),
  ticker: document.querySelector("#ticker-track"),
  date: document.querySelector("#date-label"),
  liveCount: document.querySelector("#live-count"),
  finalCount: document.querySelector("#final-count"),
  totalCount: document.querySelector("#total-count"),
  lastUpdated: document.querySelector("#last-updated"),
  statusNote: document.querySelector("#status-note"),
};

function updateClock() {
  const now = new Date();
  els.clock.textContent = now.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function scoreDiff(game) {
  return Math.abs((game.away.score || 0) - (game.home.score || 0));
}

function scoreTotal(game) {
  return (game.away.score || 0) + (game.home.score || 0);
}

function gameSummary(game) {
  if (game.status.abstract === "Preview") {
    return `${game.away.abbrev} @ ${game.home.abbrev} ${game.startTime}`;
  }

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

  if (game.isLive) {
    score += 50;
    reasons.push("Live now");
  }

  if (game.isYankees) {
    score += 45;
    reasons.push("Yankees watch");
  }

  if (basesLoaded) {
    score += 45;
    reasons.push("Bases loaded");
  } else if (scoringPosition) {
    score += 24;
    reasons.push("Runner in scoring position");
  }

  if (game.isLive && inning >= 7 && closeGame) {
    score += 38;
    reasons.push("Late close game");
  }

  if (game.isLive && inning > 9) {
    score += 40;
    reasons.push("Extra innings");
  }

  if (game.isLive && scoreTotal(game) >= 12) {
    score += 18;
    reasons.push("High scoring");
  }

  if (game.status.abstract === "Preview" && game.isYankees) {
    score += 22;
    reasons.push("Upcoming Yankees");
  }

  if (!reasons.length) reasons.push(game.status.detailed);

  return { score, reasons };
}

function headlineText(text, type = "headline") {
  return `<span class="ticker-item ${type}" data-label="${escapeHtml(tickerLabel(type))}">${escapeHtml(text)}</span>`;
}

function buildStandardHeadlines(games) {
  const headlines = [];
  const liveGames = games.filter((game) => game.isLive);
  const finalGames = games.filter((game) => game.isFinal);
  const upcomingGames = games.filter((game) => game.status.abstract === "Preview");

  liveGames.forEach((game) => {
    const total = scoreTotal(game);
    const diff = scoreDiff(game);

    if (total >= 12) {
      headlines.push(headlineText(`Slugfest watch: ${game.away.abbrev}-${game.home.abbrev} combine for ${total} runs in ${game.inning}`));
    }

    if (diff <= 1 && (game.currentInning || 0) >= 6) {
      headlines.push(headlineText(`Tight one: ${game.away.abbrev} and ${game.home.abbrev} separated by ${diff} run in ${game.inning}`));
    }

    if ((game.away.score || 0) >= 8 || (game.home.score || 0) >= 8) {
      const leader = (game.away.score || 0) >= (game.home.score || 0) ? game.away : game.home;
      headlines.push(headlineText(`${leader.abbrev} offense lighting the board with ${leader.score} runs`));
    }

    if (game.isYankees) {
      headlines.push(headlineText(`Yankees desk: ${gameSummary(game)} from ${game.venue || "the ballpark"}`));
    }
  });

  finalGames.slice(0, 4).forEach((game) => {
    const winner = winningTeam(game);
    if (winner) {
      headlines.push(headlineText(`Final: ${winner.abbrev} closes out ${gameSummary(game)}`));
    }
  });

  upcomingGames.slice(0, 4).forEach((game) => {
    headlines.push(headlineText(`On deck: ${game.away.abbrev} at ${game.home.abbrev}, first pitch ${game.startTime}`));
  });

  if (!headlines.length) {
    headlines.push(
      headlineText("MLB scoreboard rolling live from Dorm Sports Wire"),
      headlineText("Game Focus monitors late-inning pressure, Yankees priority, and scoring threats"),
      headlineText("Coming soon: NBA, NFL, fantasy football, standings, and custom lounge messages")
    );
  }

  return headlines;
}

function buildPressureAlerts(games) {
  const alerts = [];

  games.filter((game) => game.isLive).forEach((game) => {
    const basesLoaded = game.bases?.first && game.bases?.second && game.bases?.third;
    const scoringPosition = game.bases?.second || game.bases?.third;
    const late = (game.currentInning || 0) >= 8;
    const close = scoreDiff(game) <= 3;

    if (basesLoaded) {
      alerts.push(headlineText(`Pressure Alert: bases loaded in ${game.away.abbrev}-${game.home.abbrev}, ${game.inning}`, "pressure"));
    }

    if (late && close && scoringPosition) {
      alerts.push(headlineText(`Pressure Alert: tying run in scoring position, ${game.away.abbrev}-${game.home.abbrev} ${game.inning}`, "pressure"));
    }

    if (late && close && game.inningState?.toLowerCase() === "bottom") {
      alerts.push(headlineText(`Save situation watch: ${game.away.abbrev}-${game.home.abbrev} in the bottom ${game.currentInning}`, "pressure"));
    }

    if ((game.currentInning || 0) > 9) {
      alerts.push(headlineText(`Pressure Alert: extra innings in ${game.away.abbrev}-${game.home.abbrev}`, "pressure"));
    }
  });

  return alerts;
}

function buildBreakingAlerts(games) {
  const alerts = [];

  games.filter((game) => game.isLive).forEach((game) => {
    const basesLoaded = game.bases?.first && game.bases?.second && game.bases?.third;
    const late = (game.currentInning || 0) >= 9;
    const walkOffThreat = late && game.inningState?.toLowerCase() === "bottom" && scoreDiff(game) <= 1 && (game.bases?.second || game.bases?.third || basesLoaded);

    if (walkOffThreat) {
      alerts.push(headlineText(`Breaking: walk-off threat brewing in ${game.away.abbrev}-${game.home.abbrev} with runners aboard`, "breaking"));
    }

    if ((game.currentInning || 0) > 9 && scoreDiff(game) <= 1) {
      alerts.push(headlineText(`Breaking: extra-inning pressure game, ${gameSummary(game)}`, "breaking"));
    }
  });

  games.filter((game) => game.isFinal).forEach((game) => {
    const diff = scoreDiff(game);
    const winner = winningTeam(game);
    const loser = trailingTeam(game);
    if (winner && loser && diff === 1 && scoreTotal(game) >= 12) {
      alerts.push(headlineText(`Breaking: ${winner.abbrev} survives wild one-run finish over ${loser.abbrev}`, "breaking"));
    }
  });

  return alerts.slice(0, 2);
}

function buildFocusPool(games) {
  return games
    .map((game) => ({ game, focus: gameFocusScore(game) }))
    .filter((entry) => entry.focus.score > 0 || !entry.game.isFinal)
    .sort((a, b) => b.focus.score - a.focus.score || a.game.sortKey.localeCompare(b.game.sortKey))
    .slice(0, 5);
}

function renderBases(game) {
  const bases = game.bases || {};
  return `
    <div class="base-diamond" aria-label="Bases occupied">
      <span class="base second ${bases.second ? "occupied" : ""}"></span>
      <span class="base third ${bases.third ? "occupied" : ""}"></span>
      <span class="base first ${bases.first ? "occupied" : ""}"></span>
    </div>
  `;
}

function renderTeamRow(team, value, isHome = false) {
  return `
    <div class="team-row ${isHome ? "home" : "away"}">
      ${team.logoUrl ? `<img class="team-logo-badge" src="${team.logoUrl}" alt="" aria-hidden="true">` : ""}
      <span class="team-code">${team.abbrev}</span>
      <span class="team-name" title="${team.name}">${team.shortName}</span>
      <strong>${value}</strong>
    </div>
  `;
}

function renderTile(game, featured = false, focusReasons = []) {
  const state = game.status.abstract === "Preview" ? "PREGAME" : game.status.abstract.toUpperCase();
  const detail = game.status.abstract === "Preview" ? game.startTime : game.inning;
  const awayValue = game.status.abstract === "Preview" ? "-" : scoreOrTime(game, game.away);
  const homeValue = game.status.abstract === "Preview" ? "-" : scoreOrTime(game, game.home);
  const countLine = game.isLive
    ? `${game.balls}-${game.strikes} | ${game.outs} out${game.outs === 1 ? "" : "s"}`
    : game.status.abstract === "Preview"
      ? `Starts ${game.startTime}`
      : game.status.detailed;
  const label = featured ? "GAME FOCUS" : state;
  const focusCopy = featured && focusReasons.length
    ? `<div class="focus-reasons">${focusReasons.slice(0, 3).map((reason) => `<span>${reason}</span>`).join("")}</div>`
    : "";

  return `
    <article class="game-tile ${statusClass(game)} ${featured ? "featured" : ""}">
      ${game.home.logoUrl ? `<img class="team-logo-watermark home-mark" src="${game.home.logoUrl}" alt="" aria-hidden="true">` : ""}
      ${game.away.logoUrl ? `<img class="team-logo-watermark away-mark" src="${game.away.logoUrl}" alt="" aria-hidden="true">` : ""}
      <div class="tile-topline">
        <span class="state-badge">${label}</span>
        <strong>${detail}</strong>
      </div>
      ${focusCopy}
      <div class="score-lines">
        ${renderTeamRow(game.away, awayValue)}
        ${renderTeamRow(game.home, homeValue, true)}
      </div>
      <div class="tile-footer">
        <span>${countLine}</span>
        ${renderBases(game)}
      </div>
    </article>
  `;
}

function renderGrid() {
  if (!latestGames.length) {
    els.grid.innerHTML = `
      <article class="game-tile empty">
        <div class="tile-topline">
          <span class="state-badge">MLB</span>
          <strong>No games</strong>
        </div>
        <p>No MLB games found for today's slate.</p>
      </article>
    `;
    return;
  }

  const focusEntry = focusPool[focusIndex % Math.max(focusPool.length, 1)] || { game: latestGames[0], focus: gameFocusScore(latestGames[0]) };
  const focusGame = focusEntry.game;
  const remaining = latestGames.filter((game) => game.gamePk !== focusGame.gamePk);
  const visibleTiles = remaining.slice(0, 14);

  els.grid.innerHTML = [
    renderTile(focusGame, true, focusEntry.focus.reasons),
    ...visibleTiles.map((game) => renderTile(game, false)),
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

function tickerCategoryClass(category) {
  if (category.includes("breaking")) return "breaking";
  if (category.includes("pressure")) return "pressure";
  if (category.includes("performer")) return "performer";
  if (category.includes("news")) return "news";
  return "headline";
}

function tickerLabel(category) {
  if (category.includes("breaking-test")) return "TEST ALERT";
  if (category.includes("breaking")) return "BREAKING";
  if (category.includes("pressure")) return "PRESSURE";
  if (category.includes("performer")) return "PERFORMER";
  if (category.includes("news")) return "MLB NEWS";
  return "HEADLINE";
}

function renderTickerFeed(feed) {
  const items = feed.items || [];
  const leadCategory = items[0]?.category || "";
  const mode = leadCategory.includes("breaking")
    ? "breaking-mode"
    : items.some((item) => item.category.includes("pressure"))
      ? "pressure-mode"
      : "headline-mode";
  const rendered = items.length
    ? items.map((item) => {
        const category = escapeHtml(item.category || "headline");
        const label = escapeHtml(tickerLabel(item.category || "headline"));
        const source = escapeHtml(item.source || "unknown source");
        return `<span class="ticker-item ${tickerCategoryClass(category)}" data-label="${label}" title="${source}">${escapeHtml(item.text)}<small>${source}</small></span>`;
      }).join("")
    : headlineText("Ticker feed waiting for box score performers, pressure alerts, and real MLB news", "headline");

  els.ticker.parentElement.parentElement.className = `bottom-line ${mode}`;
  els.ticker.innerHTML = `<span>${rendered}</span><span aria-hidden="true">${rendered}</span>`;
}

async function loadTicker() {
  try {
    const response = await fetch("/api/mlb/ticker", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Ticker fetch failed");
    renderTickerFeed(data);
  } catch (error) {
    renderTickerFeed({
      items: [
        {
          text: `Ticker feed unavailable: ${error.message}`,
          category: "headline",
          source: "local app error",
        },
      ],
    });
  }
}

async function loadScores() {
  try {
    const response = await fetch("/api/mlb/today", { cache: "no-store" });
    const data = await response.json();

    if (!response.ok) throw new Error(data.error || "Score fetch failed");

    latestGames = data.games || [];
    focusPool = buildFocusPool(latestGames);
    focusIndex = 0;

    const liveCount = latestGames.filter((game) => game.isLive).length;
    const finalCount = latestGames.filter((game) => game.isFinal).length;
    const shownCount = Math.min(latestGames.length, 15);

    els.date.textContent = data.displayDate || data.date;
    els.liveCount.textContent = liveCount;
    els.finalCount.textContent = finalCount;
    els.totalCount.textContent = latestGames.length;
    els.statusNote.textContent = latestGames.length
      ? `${shownCount} shown | RedZone-style Game Focus rotates by live pressure`
      : "No MLB games on this date";
    els.lastUpdated.textContent = `Updated ${new Date(data.generatedAt).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    })}`;

    renderGrid();
    loadTicker();
    startFocusRotation();
  } catch (error) {
    els.statusNote.textContent = "Score feed unavailable";
    els.lastUpdated.textContent = "Update failed";
    els.grid.innerHTML = `
      <article class="game-tile empty">
        <div class="tile-topline">
          <span class="state-badge">Error</span>
          <strong>Feed down</strong>
        </div>
        <p>${error.message}</p>
      </article>
    `;
    renderTickerFeed({ items: [] });
  }
}

updateClock();
loadScores();
setInterval(updateClock, 1_000);
setInterval(loadScores, REFRESH_MS);
