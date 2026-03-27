const totalStakeEl = document.getElementById("perf-total-stake");
const totalProfitEl = document.getElementById("perf-total-profit");
const roiEl = document.getElementById("perf-roi");
const startBankrollInput = document.getElementById("perf-start-bankroll");
const clearBtn = document.getElementById("perf-clear");
const bankrollSummary = document.getElementById("perf-bankroll-summary");
const bankrollTable = document.getElementById("perf-bankroll-table");
const activeSummary = document.getElementById("perf-active-summary");
const activeTable = document.getElementById("perf-active-table");
const activeSort = document.getElementById("perf-active-sort");
const betsSummary = document.getElementById("perf-bets-summary");
const betsTable = document.getElementById("perf-bets-table");
const themeToggleBtn = document.getElementById("perf-theme-toggle");
const chartSummary = document.getElementById("perf-chart-summary");
const chartEl = document.getElementById("perf-bankroll-chart");
const logoutBtn = document.getElementById("perf-logout");
const userBadge = document.getElementById("perf-user-badge");

const AUTH_TOKEN_KEY = "auth-token";
const API_BASE_KEY = "api-base";
let currentUser = null;
const DEFAULT_API_BASE =
  window.APP_CONFIG?.API_BASE || "http://127.0.0.1:8000";

const formatNumber = (value, digits = 2) => {
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  return num.toFixed(digits);
};

const formatDate = (value) => {
  if (!value) return "Unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
};

const baseUrl = () =>
  (localStorage.getItem(API_BASE_KEY) || DEFAULT_API_BASE).replace(/\/$/, "");

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

const resolvedProfit = (bet) => {
  const result = bet.result || "pending";
  if (result === "win" || result === "loss" || result === "void") {
    return Number(bet.profit || 0);
  }
  return 0;
};

const resolvedPayout = (bet) => {
  const result = bet.result || "pending";
  if (result === "win" || result === "loss" || result === "void") {
    return Number(bet.payout || 0);
  }
  return Number(bet.stake || 0);
};

const derivedOdds = (bet) => {
  if (bet.odds_decimal) return Number(bet.odds_decimal);
  const stake = Number(bet.stake || 0);
  const payout = Number(bet.payout || 0);
  if (stake > 0 && payout > 0) return payout / stake;
  return "";
};

const loadStartBankroll = () => {
  if (!currentUser) return 1000;
  const key = `bet-performance-bankroll-${currentUser.id}`;
  const value = Number(localStorage.getItem(key));
  return Number.isFinite(value) && value > 0 ? value : 1000;
};

const saveStartBankroll = (value) => {
  if (!currentUser) return;
  const key = `bet-performance-bankroll-${currentUser.id}`;
  localStorage.setItem(key, value.toString());
};

const renderStats = (bets) => {
  const totalStake = bets.reduce((sum, bet) => sum + Number(bet.stake || 0), 0);
  const totalProfit = bets.reduce((sum, bet) => sum + resolvedProfit(bet), 0);
  const roi = totalStake > 0 ? (totalProfit / totalStake) * 100 : 0;
  totalStakeEl.textContent = formatNumber(totalStake, 2);
  totalProfitEl.textContent = formatNumber(totalProfit, 2);
  roiEl.textContent = `${formatNumber(roi, 2)}%`;
};

const renderChart = (bets) => {
  chartEl.innerHTML = "";
  const startBankroll = Number(startBankrollInput.value || "0");
  if (!bets.length) {
    chartSummary.textContent = "No bankroll data yet.";
    chartEl.innerHTML = `<text x="20" y="40" class="chart__label">Add bets from the dashboard to see the curve.</text>`;
    return;
  }

  const sorted = [...bets].sort(
    (a, b) => new Date(a.placed_at) - new Date(b.placed_at)
  );
  let running = startBankroll;
  const points = [{ label: "Start", value: running }];
  sorted.forEach((bet) => {
    running += resolvedProfit(bet);
    points.push({ label: formatDate(bet.placed_at), value: running });
  });

  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = 24;
  const width = 720;
  const height = 260;
  const usableHeight = height - padding * 2;
  const step = points.length > 1 ? (width - padding * 2) / (points.length - 1) : 0;
  const scale = max === min ? 1 : usableHeight / (max - min);

  const coords = points.map((point, index) => {
    const x = padding + step * index;
    const y = height - padding - (point.value - min) * scale;
    return { x, y, value: point.value };
  });

  const linePath = coords
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`)
    .join(" ");
  const areaPath = `${linePath} L${coords.at(-1).x},${height - padding} L${
    coords[0].x
  },${height - padding} Z`;

  const gridLines = [0.25, 0.5, 0.75].map((pct) => {
    const y = padding + usableHeight * pct;
    return `<line class="chart__grid" x1="${padding}" y1="${y}" x2="${
      width - padding
    }" y2="${y}" />`;
  });

  chartEl.innerHTML = `
    ${gridLines.join("\n")}
    <path class="chart__area" d="${areaPath}" />
    <path class="chart__line" d="${linePath}" />
    <text class="chart__label" x="${padding}" y="${padding - 6}">
      ${formatNumber(max, 2)}
    </text>
    <text class="chart__label" x="${padding}" y="${height - 6}">
      ${formatNumber(min, 2)}
    </text>
  `;

  chartSummary.textContent = `Bankroll from ${formatNumber(
    startBankroll,
    2
  )} to ${formatNumber(coords.at(-1).value, 2)}.`;
};

const renderBankroll = (bets) => {
  bankrollTable.innerHTML = "";
  const startBankroll = Number(startBankrollInput.value || "0");
  if (!bets.length) {
    bankrollSummary.textContent = "No bets yet.";
    bankrollTable.innerHTML = `<div class="empty">Add your first bet to start tracking.</div>`;
    return;
  }
  let running = startBankroll;
  bankrollSummary.textContent = `Starting ${formatNumber(
    startBankroll,
    2
  )} -> ${formatNumber(
    running + bets.reduce((sum, bet) => sum + resolvedProfit(bet), 0),
    2
  )}`;
  bets.forEach((bet) => {
    running += resolvedProfit(bet);
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div>
        <strong>Date</strong>
        ${formatDate(bet.placed_at)}
      </div>
      <div>
        <strong>Event</strong>
        ${bet.event || "Unknown"}
      </div>
      <div>
        <strong>Stake</strong>
        ${formatNumber(bet.stake, 2)}
      </div>
      <div>
        <strong>Profit</strong>
        ${formatNumber(resolvedProfit(bet), 2)}
      </div>
      <div>
        <strong>Bankroll</strong>
        ${formatNumber(running, 2)}
      </div>
    `;
    bankrollTable.appendChild(row);
  });
};

const renderBets = (bets) => {
  betsTable.innerHTML = "";
  if (!bets.length) {
    betsSummary.textContent = "No bets logged.";
    betsTable.innerHTML = `<div class="empty">Nothing recorded yet.</div>`;
    return;
  }
  betsSummary.textContent = `${bets.length} bets tracked.`;
  bets.forEach((bet) => {
    const oddsValue = derivedOdds(bet);
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div>
        <strong>Event</strong>
        ${bet.event || "Unknown"}
        <div class="meta">${bet.market || ""} ${bet.outcome || ""}</div>
      </div>
      <div>
        <strong>Stake</strong>
        ${formatNumber(bet.stake, 2)}
      </div>
      <div>
        <strong>Payout</strong>
        ${formatNumber(resolvedPayout(bet), 2)}
      </div>
      <div>
        <strong>Profit</strong>
        ${formatNumber(resolvedProfit(bet), 2)}
      </div>
      <div>
        <strong>Date</strong>
        ${formatDate(bet.placed_at)}
      </div>
      <div>
        <strong>Odds</strong>
        <div class="editable-field" data-display>${oddsValue || "—"}</div>
        <input class="field-input field-input--compact is-hidden" type="number" step="0.01" value="${oddsValue}" data-odds />
      </div>
      <div>
        <strong>Result</strong>
        <div class="editable-field" data-display>${(bet.result || "pending").toUpperCase()}</div>
        <select class="field-select field-input--compact is-hidden" data-result>
          <option value="pending" ${bet.result === "pending" || !bet.result ? "selected" : ""}>Pending</option>
          <option value="win" ${bet.result === "win" ? "selected" : ""}>Win</option>
          <option value="loss" ${bet.result === "loss" ? "selected" : ""}>Loss</option>
          <option value="void" ${bet.result === "void" ? "selected" : ""}>Void</option>
        </select>
      </div>
      <button class="button button--ghost" data-update-id="${bet.id}">
        Update
      </button>
      <button class="button button--ghost" data-id="${bet.id}">
        Remove
      </button>
    `;
    const removeBtn = row.querySelector("button[data-id]");
    const updateBtn = row.querySelector("button[data-update-id]");
    const oddsInput = row.querySelector("input[data-odds]");
    const resultSelect = row.querySelector("select[data-result]");
    const displayFields = row.querySelectorAll("[data-display]");
    removeBtn.addEventListener("click", async () => {
      await fetchJson(`/bets/me/${bet.id}`, { method: "DELETE" });
      renderAll();
    });
    updateBtn.addEventListener("click", async () => {
      const isEditing = updateBtn.dataset.mode === "edit";
      if (!isEditing) {
        updateBtn.dataset.mode = "edit";
        updateBtn.textContent = "Save";
        displayFields.forEach((el) => el.classList.add("is-hidden"));
        oddsInput.classList.remove("is-hidden");
        resultSelect.classList.remove("is-hidden");
        oddsInput.focus();
        return;
      }
      const odds = oddsInput.value ? Number(oddsInput.value) : null;
      const result = resultSelect.value || "pending";
      await fetchJson(`/bets/me/${bet.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          odds_decimal: odds,
          result,
        }),
      });
      updateBtn.dataset.mode = "";
      updateBtn.textContent = "Update";
      renderAll();
    });
    betsTable.appendChild(row);
  });
};

const renderActiveBets = (bets) => {
  activeTable.innerHTML = "";
  const active = bets.filter((bet) => (bet.result || "pending") === "pending");
  const sortValue = activeSort?.value || "newest";
  active.sort((a, b) => {
    const aTime = new Date(a.placed_at).getTime();
    const bTime = new Date(b.placed_at).getTime();
    return sortValue === "oldest" ? aTime - bTime : bTime - aTime;
  });
  if (!active.length) {
    activeSummary.textContent = "No active bets.";
    activeTable.innerHTML = `<div class="empty">No pending bets right now.</div>`;
    return;
  }
  activeSummary.textContent = `${active.length} active bet(s).`;
  active.forEach((bet) => {
    const oddsValue = derivedOdds(bet);
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div>
        <strong>Event</strong>
        ${bet.event || "Unknown"}
        <div class="meta">${bet.market || ""} ${bet.outcome || ""}</div>
      </div>
      <div>
        <strong>Stake</strong>
        ${formatNumber(bet.stake, 2)}
      </div>
      <div>
        <strong>Payout</strong>
        ${formatNumber(resolvedPayout(bet), 2)}
      </div>
      <div>
        <strong>Profit</strong>
        ${formatNumber(resolvedProfit(bet), 2)}
      </div>
      <div>
        <strong>Date</strong>
        ${formatDate(bet.placed_at)}
      </div>
      <div>
        <strong>Odds</strong>
        <div class="editable-field" data-display>${oddsValue || "—"}</div>
        <input class="field-input field-input--compact is-hidden" type="number" step="0.01" value="${oddsValue}" data-odds />
      </div>
      <div>
        <strong>Result</strong>
        <div class="editable-field" data-display>${(bet.result || "pending").toUpperCase()}</div>
        <select class="field-select field-input--compact is-hidden" data-result>
          <option value="pending" ${bet.result === "pending" || !bet.result ? "selected" : ""}>Pending</option>
          <option value="win" ${bet.result === "win" ? "selected" : ""}>Win</option>
          <option value="loss" ${bet.result === "loss" ? "selected" : ""}>Loss</option>
          <option value="void" ${bet.result === "void" ? "selected" : ""}>Void</option>
        </select>
      </div>
      <button class="button button--ghost" data-update-id="${bet.id}">
        Update
      </button>
      <button class="button button--ghost" data-id="${bet.id}">
        Remove
      </button>
    `;
    const removeBtn = row.querySelector("button[data-id]");
    const updateBtn = row.querySelector("button[data-update-id]");
    const oddsInput = row.querySelector("input[data-odds]");
    const resultSelect = row.querySelector("select[data-result]");
    const displayFields = row.querySelectorAll("[data-display]");
    removeBtn.addEventListener("click", async () => {
      await fetchJson(`/bets/me/${bet.id}`, { method: "DELETE" });
      renderAll();
    });
    updateBtn.addEventListener("click", async () => {
      const isEditing = updateBtn.dataset.mode === "edit";
      if (!isEditing) {
        updateBtn.dataset.mode = "edit";
        updateBtn.textContent = "Save";
        displayFields.forEach((el) => el.classList.add("is-hidden"));
        oddsInput.classList.remove("is-hidden");
        resultSelect.classList.remove("is-hidden");
        oddsInput.focus();
        return;
      }
      const odds = oddsInput.value ? Number(oddsInput.value) : null;
      const result = resultSelect.value || "pending";
      await fetchJson(`/bets/me/${bet.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          odds_decimal: odds,
          result,
        }),
      });
      updateBtn.dataset.mode = "";
      updateBtn.textContent = "Update";
      renderAll();
    });
    activeTable.appendChild(row);
  });
};

const loadBets = async () => {
  const data = await fetchJson("/bets/me");
  return data || [];
};

const refreshResults = async () => {
  try {
    await fetchJson("/bets/me/refresh-results?min_hours=2");
  } catch (err) {
    // Non-blocking: keep page usable even if refresh fails.
    console.warn("Result refresh failed", err);
  }
};

const renderAll = async () => {
  const bets = await loadBets();
  renderStats(bets);
  renderChart(bets);
  renderBankroll(bets);
  renderActiveBets(bets);
  renderBets(bets);
};

const applyTheme = (theme) => {
  if (!theme) {
    document.documentElement.removeAttribute("data-theme");
    return;
  }
  document.documentElement.setAttribute("data-theme", theme);
};

const storedTheme = localStorage.getItem("theme");
applyTheme(storedTheme);

themeToggleBtn.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  localStorage.setItem("theme", next);
});

startBankrollInput.addEventListener("change", () => {
  const value = Number(startBankrollInput.value || "0");
  if (Number.isFinite(value)) {
    saveStartBankroll(value);
    renderAll();
  }
});

clearBtn.addEventListener("click", () => {
  fetchJson("/bets/me", { method: "DELETE" })
    .then(() => renderAll())
    .catch(() => renderAll());
});

logoutBtn.addEventListener("click", () => {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  window.location.href = "./login.html";
});

const requireAuth = async () => {
  const token = getToken();
  if (!token) {
    window.location.href = "./login.html";
    return false;
  }
  try {
    currentUser = await fetchJson("/auth/me");
    if (userBadge) {
      userBadge.textContent = `${currentUser.email} (${currentUser.role})`;
    }
    return true;
  } catch {
    return false;
  }
};

requireAuth().then((ok) => {
  if (!ok) return;
  startBankrollInput.value = loadStartBankroll();
  refreshResults()
    .catch((err) => {
      console.warn("Result refresh failed", err);
    })
    .finally(() => {
      renderAll().catch((err) => {
        chartSummary.textContent = err.message;
        betsSummary.textContent = err.message;
      });
    });
});

if (activeSort) {
  activeSort.addEventListener("change", () => {
    renderAll().catch(() => {});
  });
}
