const apiBaseInput = document.getElementById("api-base");
const stakePoolInput = document.getElementById("stake-pool");
const refreshAllBtn = document.getElementById("refresh-all");
const themeToggleBtn = document.getElementById("theme-toggle");

const refreshValuebetsBtn = document.getElementById("refresh-valuebets");
const showDismissedBtn = document.getElementById("valuebet-show-dismissed");
const apiStatus = document.getElementById("api-status");
const lastRefresh = document.getElementById("last-refresh");


const valuebetTable = document.getElementById("valuebet-table");
const valuebetSummary = document.getElementById("valuebet-summary");

const valuebetSort = document.getElementById("valuebet-sort");
const logoutBtn = document.getElementById("logout-btn");
const userBadge = document.getElementById("user-badge");
const adminLink = document.getElementById("admin-link");
const oddsApiTable = document.getElementById("odds-api-table");
const oddsApiSummary = document.getElementById("odds-api-summary");
const refreshOddsApiBtn = document.getElementById("refresh-odds-api");


let currentValuebets = [];
let currentOddsApi = [];
let currentUser = null;

const AUTH_TOKEN_KEY = "auth-token";
const API_BASE_KEY = "api-base";

const VALUEBET_SORT_KEY = "valuebet-sort";

const betKey = (parts) => parts.map((part) => (part || "").toString()).join("|");
let placedBets = {};
const dismissedValuebetsKey = "valuebet-dismissed";
const showDismissedKey = "valuebet-show-dismissed";
let dismissedValuebets = new Set();
let showDismissed = false;

const loadDismissedValuebets = () => {
  try {
    const raw = localStorage.getItem(dismissedValuebetsKey);
    dismissedValuebets = new Set(raw ? JSON.parse(raw) : []);
    showDismissed = localStorage.getItem(showDismissedKey) === "true";
  } catch {
    dismissedValuebets = new Set();
    showDismissed = false;
  }
  if (showDismissedBtn) {
    showDismissedBtn.textContent = showDismissed ? "Hide dismissed" : "Show dismissed";
  }
};

const saveDismissedValuebets = () => {
  localStorage.setItem(
    dismissedValuebetsKey,
    JSON.stringify([...dismissedValuebets])
  );
};

const formatNumber = (value, digits = 4) => {
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  return num.toFixed(digits);
};

const formatTimeUntil = (isoString) => {
  if (!isoString) return "Time unknown";
  const target = new Date(isoString);
  if (Number.isNaN(target.getTime())) return "Time unknown";
  const diffMs = target.getTime() - Date.now();
  if (diffMs <= 0) return "Started";
  const totalMinutes = Math.floor(diffMs / 60000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `In ${days}d ${hours}h`;
  if (hours > 0) return `In ${hours}h ${minutes}m`;
  return `In ${minutes}m`;
};

const formatValuebetSide = (valuebet) => {
  const side = (valuebet?.betSide || "").toLowerCase();
  const marketName = (valuebet?.market?.name || "").toLowerCase();
  const hdp = valuebet?.market?.hdp ?? valuebet?.bookmakerOdds?.hdp;
  const hasHdp = hdp !== null && hdp !== undefined && hdp !== "";
  const isOverUnderMarket =
    marketName.includes("total") ||
    marketName.includes("props") ||
    marketName.includes("rebounds") ||
    marketName.includes("points") ||
    marketName.includes("assists") ||
    marketName.includes("shots") ||
    marketName.includes("goals");
  if ((side === "home" || side === "away") && hasHdp && isOverUnderMarket) {
    const line = typeof hdp === "number" ? hdp : Number(hdp);
    const label = Number.isFinite(line) ? `${line}` : `${hdp}`;
    return side === "home" ? `Over ${label}` : `Under ${label}`;
  }
  if (side === "home") return "Home";
  if (side === "away") return "Away";
  return valuebet?.betSide || "";
};

const setStatus = (text) => {
  apiStatus.textContent = text;
};

const setRefreshTime = () => {
  const now = new Date();
  lastRefresh.textContent = now.toLocaleTimeString();
};

const baseUrl = () => apiBaseInput.value.replace(/\/$/, "");

const getToken = () => localStorage.getItem(AUTH_TOKEN_KEY) || "";

const handleUnauthorized = () => {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  window.location.href = "./login.html";
};

const fetchJson = async (path, options = {}) => {
  const url = `${baseUrl()}${path}`;
  const token = getToken();
  const headers = {
    ...(options.headers || {}),
    Authorization: token ? `Bearer ${token}` : "",
  };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      handleUnauthorized();
    }
    throw new Error(`Request failed: ${res.status}`);
  }
  if (res.status === 204) {
    return null;
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
};

const setUserBadge = (user) => {
  if (!userBadge) return;
  if (!user) {
    userBadge.textContent = "Unknown";
    return;
  }
  userBadge.textContent = `${user.email} (${user.role})`;
  if (adminLink) {
    adminLink.style.display = user.role === "admin" ? "inline-flex" : "none";
  }
};

const loadPlacedBets = async () => {
  const data = await fetchJson("/bets/me");
  placedBets = {};
  (data || []).forEach((bet) => {
    placedBets[bet.external_key] = bet;
  });
  return placedBets;
};

const requireAuth = async () => {
  const token = getToken();
  if (!token) {
    window.location.href = "./login.html";
    return false;
  }
  try {
    currentUser = await fetchJson("/auth/me");
    setUserBadge(currentUser);
    return true;
  } catch {
    return false;
  }
};

const renderValuebets = (items) => {
  const filtered = items.filter((item) => {
    const id = item.valuebet?.id;
    if (!id) return true;
    if (showDismissed) {
      return dismissedValuebets.has(id);
    }
    return !dismissedValuebets.has(id);
  });
  const sorted = [...filtered];
  const stake = Number(stakePoolInput.value || "100");
  if (valuebetSort.value === "ev") {
    sorted.sort((a, b) => {
      const aEv = Number(a.valuebet?.expectedValue || 0);
      const bEv = Number(b.valuebet?.expectedValue || 0);
      return bEv - aEv;
    });
  }
  if (valuebetSort.value === "time") {
    sorted.sort((a, b) => {
      const aTime = new Date(a.valuebet?.event?.date || "").getTime();
      const bTime = new Date(b.valuebet?.event?.date || "").getTime();
      return aTime - bTime;
    });
  }
  valuebetTable.innerHTML = "";
  if (!sorted.length) {
    valuebetSummary.textContent = showDismissed
      ? "No dismissed value bets."
      : "No value bets detected.";
    valuebetTable.innerHTML = `<div class="empty">${
      showDismissed ? "No dismissed value bets." : "No value bets yet."
    }</div>`;
    return;
  }
  valuebetSummary.textContent = showDismissed
    ? `${sorted.length} dismissed value bets.`
    : `${sorted.length} value bets detected.`;
  sorted.forEach((item) => {
    const valuebet = item.valuebet || {};
    const event = valuebet.event || {};
    const eventName =
      item.event_name ||
      (event.home && event.away ? `${event.home} vs ${event.away}` : "Unknown event");
    const market = valuebet.market || {};
    const marketLabel = market.hdp ? `${market.name} ${market.hdp}` : market.name || "Market";
    const ev = Number(valuebet.expectedValue || 0);
    const odds = valuebet.bookmakerOdds || {};
    const oddsValue = odds[valuebet.betSide] || "N/A";
    const oddsDecimal = Number(oddsValue);
    const link = odds.href || "";
    const profit = stake * (ev / 100 - 1);
    const valuebetId = valuebet.id || "";
    const sideLabel = formatValuebetSide(valuebet);
    const key = betKey([
      "valuebet",
      eventName,
      marketLabel,
      valuebet.betSide,
    ]);
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      ${
        showDismissed
          ? '<button class="restore-btn" title="Restore value bet" aria-label="Restore value bet">♻</button>'
          : '<button class="trash-btn" title="Remove value bet" aria-label="Remove value bet">🗑</button>'
      }
      <div>
        <strong>Event</strong>
        <div class="pill">${eventName}</div>
        <div class="meta">${formatTimeUntil(event.date)}</div>
        <div>${event.sport || ""} ${event.league || ""}</div>
      </div>
      <div>
        <strong>Market</strong>
        ${marketLabel}
      </div>
      <div>
        <strong>Side</strong>
        ${sideLabel || valuebet.betSide || ""}
      </div>
      <div>
        <strong>EV</strong>
        ${formatNumber(ev, 2)}%
      </div>
      <div>
        <strong>Odds</strong>
        ${link ? `<a href="${link}" target="_blank" rel="noreferrer">${oddsValue}</a>` : oddsValue}
      </div>
      <div>
        <strong>Est. Profit</strong>
        ${formatNumber(profit, 2)}
      </div>
      <label class="bet-toggle">
        <input type="checkbox" data-bet-key="${key}" ${
          placedBets[key] ? "checked" : ""
        } />
        Placed
      </label>
    `;
    const toggle = row.querySelector("input[data-bet-key]");
    const trashBtn = row.querySelector(".trash-btn");
    const restoreBtn = row.querySelector(".restore-btn");
    toggle.addEventListener("change", async (event) => {
      if (event.target.checked) {
        const payout = Number.isFinite(oddsDecimal) && oddsDecimal > 1 ? stake * oddsDecimal : stake;
        const payload = {
          external_key: key,
          source: "valuebet",
          event: eventName,
          market: marketLabel,
          outcome: sideLabel || valuebet.betSide || "",
          stake,
          payout,
          profit: payout - stake,
          odds_decimal: Number.isFinite(oddsDecimal) ? oddsDecimal : null,
          placed_at: new Date().toISOString(),
        };
        const bet = await fetchJson("/bets/me", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        placedBets[key] = bet;
      } else {
        await fetchJson(`/bets/me/by-key?external_key=${encodeURIComponent(key)}`, {
          method: "DELETE",
        });
        delete placedBets[key];
      }
    });
    if (trashBtn) {
      trashBtn.addEventListener("click", () => {
        if (valuebetId) {
          dismissedValuebets.add(valuebetId);
          saveDismissedValuebets();
        }
        renderValuebets(currentValuebets);
      });
    }
    if (restoreBtn) {
      restoreBtn.addEventListener("click", () => {
        if (valuebetId) {
          dismissedValuebets.delete(valuebetId);
          saveDismissedValuebets();
        }
        renderValuebets(currentValuebets);
      });
    }
    valuebetTable.appendChild(row);
  });
};

const renderOddsApi = (items) => {
  oddsApiTable.innerHTML = "";
  if (!items.length) {
    oddsApiSummary.textContent = "No arbitrage opportunities found.";
    oddsApiTable.innerHTML = `<div class="empty">No Odds API results yet.</div>`;
    return;
  }
  oddsApiSummary.textContent = `${items.length} opportunities loaded.`;
  items.forEach((item) => {
    const event = item.event || {};
    const eventName =
      item.event_name ||
      (event.home && event.away ? `${event.home} vs ${event.away}` : "Unknown event");
    const startTime = item.event_start_time || event.date || "";
    const market = item.market || {};
    const marketLabel = market.hdp ? `${market.name} ${market.hdp}` : market.name || "Market";
    const profitMargin = Number(item.profitMargin || 0);
    const implied = Number(item.impliedProbability || 0);
    const totalStake = Number(item.totalStake || 0);
    const legs = item.legs || [];
    const stakes = item.optimalStakes || [];
    const legMap = new Map(
      legs.map((leg) => [
        `${leg.bookmaker}|${leg.side}`,
        { href: leg.href, odds: leg.odds },
      ])
    );
    const key = betKey(["oddsapi", item.id]);
    const stakeLines = stakes
      .map((stake) => {
        const lookup = legMap.get(`${stake.bookmaker}|${stake.side}`) || {};
        const label = `${stake.side} ${stake.bookmaker}: ${formatNumber(
          stake.stake,
          2
        )} @ ${formatNumber(lookup.odds || 0, 2)}`;
        if (lookup.href) {
          return `<a href="${lookup.href}" target="_blank" rel="noreferrer">${label}</a>`;
        }
        return label;
      })
      .join("<br/>");

    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div>
        <strong>Event</strong>
        <div class="pill">${eventName}</div>
        <div class="meta">${formatTimeUntil(startTime)}</div>
        <div>${event.sport || ""} ${event.league || ""}</div>
      </div>
      <div>
        <strong>Market</strong>
        ${marketLabel}
      </div>
      <div>
        <strong>Margin</strong>
        ${formatNumber(profitMargin, 2)}%
      </div>
      <div>
        <strong>Implied</strong>
        ${formatNumber(implied, 4)}
      </div>
      <div>
        <strong>Stakes</strong>
        ${stakeLines || "No stake data"}
      </div>
      <label class="bet-toggle">
        <input type="checkbox" data-bet-key="${key}" ${
          placedBets[key] ? "checked" : ""
        } />
        Placed
      </label>
    `;
    const toggle = row.querySelector("input[data-bet-key]");
    toggle.addEventListener("change", async (eventToggle) => {
      if (eventToggle.target.checked) {
        const profit = (totalStake * profitMargin) / 100;
        const payload = {
          external_key: key,
          source: "odds_api",
          event: eventName,
          market: marketLabel,
          outcome: "multi",
          stake: totalStake,
          payout: totalStake + profit,
          profit,
          placed_at: new Date().toISOString(),
        };
        const bet = await fetchJson("/bets/me", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        placedBets[key] = bet;
      } else {
        await fetchJson(`/bets/me/by-key?external_key=${encodeURIComponent(key)}`, {
          method: "DELETE",
        });
        delete placedBets[key];
      }
    });
    oddsApiTable.appendChild(row);
  });
};


const loadValuebets = async () => {
  setStatus("Loading value bets...");
  const data = await fetchJson("/valuebets?min_ev=105");
  currentValuebets = data || [];
  renderValuebets(currentValuebets);
};

const loadOddsApi = async () => {
  setStatus("Loading Odds API...");
  const data = await fetchJson("/arbitrage/odds-api");
  currentOddsApi = data || [];
  renderOddsApi(currentOddsApi);
};

const refreshAll = async () => {
  try {
    setStatus("Refreshing...");
    loadDismissedValuebets();
    await loadPlacedBets();
    await Promise.all([loadValuebets(), loadOddsApi()]);
    setRefreshTime();
    setStatus("Ready");
  } catch (err) {
    setStatus("Error");
    valuebetSummary.textContent = err.message;
    oddsApiSummary.textContent = err.message;
  }
};

refreshValuebetsBtn.addEventListener("click", () => {
  loadDismissedValuebets();
  loadPlacedBets()
    .then(() => loadValuebets())
    .catch((err) => {
      valuebetSummary.textContent = err.message;
    });
});
if (showDismissedBtn) {
  showDismissedBtn.addEventListener("click", () => {
    showDismissed = !showDismissed;
    localStorage.setItem(showDismissedKey, showDismissed ? "true" : "false");
    showDismissedBtn.textContent = showDismissed ? "Hide dismissed" : "Show dismissed";
    renderValuebets(currentValuebets);
  });
}
refreshOddsApiBtn.addEventListener("click", () => {
  loadPlacedBets()
    .then(() => loadOddsApi())
    .catch((err) => {
      oddsApiSummary.textContent = err.message;
    });
});

valuebetSort.addEventListener("change", () => {
  localStorage.setItem(VALUEBET_SORT_KEY, valuebetSort.value);
  renderValuebets(currentValuebets);
});

restoreSortSelections();

const applyTheme = (theme) => {
  if (!theme) {
    document.documentElement.removeAttribute("data-theme");
    return;
  }
  document.documentElement.setAttribute("data-theme", theme);
};

function restoreSortSelections() {
  const savedValuebet = localStorage.getItem(VALUEBET_SORT_KEY);
  if (savedValuebet && valuebetSort) {
    valuebetSort.value = savedValuebet;
  }
}

const storedTheme = localStorage.getItem("theme");
applyTheme(storedTheme);

themeToggleBtn.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  localStorage.setItem("theme", next);
});

apiBaseInput.value = localStorage.getItem(API_BASE_KEY) || apiBaseInput.value;
apiBaseInput.addEventListener("change", () => {
  localStorage.setItem(API_BASE_KEY, apiBaseInput.value);
});

logoutBtn.addEventListener("click", () => {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  window.location.href = "./login.html";
});

requireAuth().then((ok) => {
  if (!ok) return;
  refreshAll();
});
