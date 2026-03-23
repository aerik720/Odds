const apiBaseInput = document.getElementById("admin-api-base");
const apiStatus = document.getElementById("admin-api-status");
const lastRefresh = document.getElementById("admin-last-refresh");
const refreshBtn = document.getElementById("admin-refresh");
const taskLog = document.getElementById("admin-task-log");
const statsSummary = document.getElementById("admin-stats-summary");
const statsTable = document.getElementById("admin-stats-table");
const tasksContainer = document.getElementById("admin-tasks");
const themeToggleBtn = document.getElementById("admin-theme-toggle");
const taskStatus = document.getElementById("admin-task-status");
const taskProgress = document.getElementById("admin-task-progress");
const logoutBtn = document.getElementById("admin-logout");
const userBadge = document.getElementById("admin-user-badge");
const usersSummary = document.getElementById("admin-users-summary");
const usersTable = document.getElementById("admin-users-table");
const userForm = document.getElementById("admin-user-form");
const userEmailInput = document.getElementById("admin-user-email");
const userPasswordInput = document.getElementById("admin-user-password");
const userRoleInput = document.getElementById("admin-user-role");
const usersRefreshBtn = document.getElementById("admin-users-refresh");
const bookmakersForm = document.getElementById("admin-bookmakers-form");
const bookmakersInput = document.getElementById("admin-bookmakers-input");
const bookmakersSelect = document.getElementById("admin-bookmakers-select");
const bookmakersStatus = document.getElementById("admin-bookmakers-status");
const autoArbToggle = document.getElementById("auto-arb-toggle");
const autoArbStatus = document.getElementById("auto-arb-status");
const arbAlert = document.getElementById("arb-alert");
const arbVerifyStats = document.getElementById("arb-verify-stats");

let taskPoller = null;
let runningTask = "";
let currentAdmin = null;
let autoArbTimer = null;
let audioCtx = null;
const LAST_TASK_KEY = "admin-running-task";
const AUTH_TOKEN_KEY = "auth-token";
const API_BASE_KEY = "api-base";
const AUTO_ARB_KEY = "admin-auto-arb";
const ARB_IDS_KEY = "admin-arb-ids";

let lastArbIds = new Set(
  JSON.parse(localStorage.getItem(ARB_IDS_KEY) || "[]")
);

const baseUrl = () => apiBaseInput.value.replace(/\/$/, "");

const setStatus = (text) => {
  apiStatus.textContent = text;
};

const setRefreshTime = () => {
  lastRefresh.textContent = new Date().toLocaleTimeString();
};

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
  return res.json();
};

const formatTime = (iso) => {
  if (!iso) return "Unknown";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString();
};

const setUserBadge = (user) => {
  if (!userBadge) return;
  if (!user) {
    userBadge.textContent = "Unknown";
    return;
  }
  userBadge.textContent = `${user.email} (${user.role})`;
};

const renderStats = (items) => {
  statsTable.innerHTML = "";
  if (!items.length) {
    statsSummary.textContent = "No stats available.";
    statsTable.innerHTML = `<div class="empty">No bookmaker data found.</div>`;
    return;
  }
  statsSummary.textContent = `${items.length} bookmakers found.`;
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div>
        <strong>Bookmaker</strong>
        ${item.bookmaker}
      </div>
      <div>
        <strong>Events</strong>
        ${item.events}
      </div>
      <div>
        <strong>Markets</strong>
        ${item.markets}
      </div>
      <div>
        <strong>Odds</strong>
        ${item.odds}
      </div>
      <div>
        <strong>Last update</strong>
        ${formatTime(item.last_update)}
      </div>
    `;
    statsTable.appendChild(row);
  });
};

const renderUsers = (users) => {
  usersTable.innerHTML = "";
  if (!users.length) {
    usersSummary.textContent = "No users found.";
    usersTable.innerHTML = `<div class="empty">No accounts found.</div>`;
    return;
  }
  usersSummary.textContent = `${users.length} users loaded.`;
  users.forEach((user) => {
    const row = document.createElement("div");
    row.className = "row";
    row.dataset.userId = user.id;
    const isSelf = currentAdmin && user.id === currentAdmin.id;
    row.innerHTML = `
      <div>
        <strong>Email</strong>
        ${user.email}
        <div class="meta">${formatTime(user.created_at)}</div>
        ${isSelf ? `<div class="pill">You</div>` : ""}
      </div>
      <div>
        <strong>Role</strong>
        <select class="user-role" ${isSelf ? "disabled" : ""}>
          <option value="user" ${user.role === "user" ? "selected" : ""}>User</option>
          <option value="admin" ${user.role === "admin" ? "selected" : ""}>Admin</option>
        </select>
      </div>
      <div>
        <strong>Active</strong>
        <label class="field field--inline">
          <input class="user-active" type="checkbox" ${user.is_active ? "checked" : ""} ${
            isSelf ? "disabled" : ""
          } />
          <span>${user.is_active ? "Enabled" : "Disabled"}</span>
        </label>
      </div>
      <div>
        <strong>Actions</strong>
        <button class="button button--ghost user-save" type="button" ${
          isSelf ? "disabled" : ""
        }>
          Save
        </button>
      </div>
    `;
    usersTable.appendChild(row);
  });
};

const setArbAlert = (message, isPositive = false) => {
  if (!arbAlert) return;
  arbAlert.textContent = message;
  arbAlert.classList.toggle("notice--good", Boolean(isPositive));
};

const initAudio = () => {
  if (audioCtx) return;
  const AudioContextRef = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextRef) return;
  audioCtx = new AudioContextRef();
};

const playArbSound = () => {
  if (!audioCtx) return;
  if (audioCtx.state === "suspended") {
    audioCtx.resume().catch(() => {});
  }
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  gain.gain.value = 0.06;
  osc.type = "sine";
  osc.frequency.value = 880;
  osc.connect(gain);
  gain.connect(audioCtx.destination);
  osc.start();
  osc.stop(audioCtx.currentTime + 0.18);
};

const loadArbIds = async () => {
  const data = await fetchJson("/arbitrage/odds-api");
  const ids = new Set((data || []).map((item) => item.id).filter(Boolean));
  return { ids, count: ids.size };
};

const checkArbUpdates = async () => {
  try {
    const { ids, count } = await loadArbIds();
    const newOnes = [...ids].filter((id) => !lastArbIds.has(id));
    if (newOnes.length) {
      setArbAlert(`New arbitrage found: ${newOnes.length}`, true);
      playArbSound();
      if (window.Notification && Notification.permission === "granted") {
        new Notification("ArbFinder", {
          body: `New arbitrage found: ${newOnes.length}`,
        });
      }
    } else {
      setArbAlert(`No new arbitrage. Current count: ${count}.`);
    }
    lastArbIds = ids;
    localStorage.setItem(ARB_IDS_KEY, JSON.stringify([...ids]));
  } catch (err) {
    setArbAlert(err.message);
  }
};

const setAutoArbState = (enabled) => {
  if (!autoArbToggle || !autoArbStatus) return;
  autoArbToggle.textContent = enabled
    ? "Stop auto arbitrage"
    : "Start auto arbitrage";
  autoArbStatus.textContent = enabled
    ? "Auto arbitrage is running every minute."
    : "Auto arbitrage is off.";
  localStorage.setItem(AUTO_ARB_KEY, enabled ? "1" : "0");
  if (enabled) {
    setArbAlert("Auto arbitrage started.");
  } else {
    setArbAlert("Auto arbitrage stopped.");
  }
};

const startAutoArb = () => {
  if (autoArbTimer) return;
  autoArbTimer = setInterval(() => {
    if (runningTask) return;
    runTask("run_odds_api_arbitrage").catch((err) => {
      setStatus("Error");
      setArbAlert(err.message);
    });
  }, 60_000);
  setAutoArbState(true);
};

const stopAutoArb = () => {
  if (autoArbTimer) {
    clearInterval(autoArbTimer);
    autoArbTimer = null;
  }
  setAutoArbState(false);
};

const loadStats = async () => {
  setStatus("Loading stats...");
  const data = await fetchJson("/admin/stats/bookmakers");
  renderStats(data);
};

const loadUsers = async () => {
  usersSummary.textContent = "Loading users...";
  const data = await fetchJson("/admin/users");
  renderUsers(data || []);
};

const loadBookmakersSetting = async () => {
  if (!bookmakersInput || !bookmakersStatus) return;
  const data = await fetchJson("/admin/settings/odds-api-bookmakers");
  bookmakersInput.value = data.bookmakers || "";
  if (bookmakersSelect) {
    const selected = new Set(
      (data.bookmakers || "").split(",").map((item) => item.trim()).filter(Boolean)
    );
    Array.from(bookmakersSelect.options).forEach((option) => {
      option.selected = selected.has(option.value);
    });
  }
  bookmakersStatus.textContent = data.bookmakers
    ? `Current selection: ${data.bookmakers}`
    : "No selection set.";
};

const saveBookmakersSetting = async () => {
  if (!bookmakersInput || !bookmakersStatus) return;
  if (bookmakersSelect) {
    const picked = Array.from(bookmakersSelect.selectedOptions).map(
      (option) => option.value
    );
    if (picked.length) {
      bookmakersInput.value = picked.join(",");
    }
  }
  const value = bookmakersInput.value.trim();
  if (!value) {
    bookmakersStatus.textContent = "Please enter at least one bookmaker.";
    return;
  }
  const data = await fetchJson("/admin/settings/odds-api-bookmakers", {
    method: "POST",
    body: JSON.stringify({ bookmakers: value }),
  });
  bookmakersStatus.textContent = `Current selection: ${data.bookmakers}`;
};

const runTask = async (taskName) => {
  setStatus("Running task...");
  taskLog.textContent = `Running: ${taskName}...`;
  runningTask = taskName;
  localStorage.setItem(LAST_TASK_KEY, taskName);
  updateProgress({ status: "running", step: "Starting...", progress: 0 });
  await fetchJson(`/admin/tasks/run?name=${taskName}`, {
    method: "POST",
  });
  pollTaskStatus();
};

const updateProgress = (payload) => {
  const status = payload.status || "idle";
  const step = payload.step || "";
  const progress = Math.max(0, Math.min(1, Number(payload.progress || 0)));
  taskStatus.textContent = step
    ? `${status.toUpperCase()} - ${step}`
    : status.toUpperCase();
  taskProgress.style.width = `${progress * 100}%`;

  if (payload.stdout || payload.stderr) {
    const output = [];
    if (payload.returncode !== null && payload.returncode !== undefined) {
      output.push(`Return code: ${payload.returncode}`);
    }
    if (payload.stdout) {
      output.push("--- stdout ---");
      output.push(payload.stdout.trim());
      if (arbVerifyStats && runningTask === "run_odds_api_arbitrage") {
        const match = payload.stdout.match(
          /Verification:\s*checked=(\d+)\s*filtered=(\d+)\s*kept_new=(\d+)/i
        );
        if (match) {
          arbVerifyStats.textContent = `Verification: checked ${match[1]}, filtered ${match[2]}, kept ${match[3]}`;
        }
      }
    }
    if (payload.stderr) {
      output.push("--- stderr ---");
      output.push(payload.stderr.trim());
    }
    taskLog.textContent = output.join("\n");
  }
};

const pollTaskStatus = () => {
  if (!runningTask) return;
  if (taskPoller) clearInterval(taskPoller);
  taskPoller = setInterval(async () => {
    try {
      const payload = await fetchJson(`/admin/tasks/status?name=${runningTask}`);
      updateProgress(payload);
      if (payload.status === "finished" || payload.status === "error") {
        clearInterval(taskPoller);
        taskPoller = null;
        const finishedTask = runningTask;
        await loadStats();
        setRefreshTime();
        setStatus(payload.status === "finished" ? "Ready" : "Error");
        runningTask = "";
        localStorage.removeItem(LAST_TASK_KEY);
        if (payload.status === "finished" && finishedTask === "run_odds_api_arbitrage") {
          await checkArbUpdates();
        }
      }
    } catch (err) {
      setStatus("Error");
      taskLog.textContent = err.message;
    }
  }, 2000);
};

const resumeTaskStatus = () => {
  const stored = localStorage.getItem(LAST_TASK_KEY);
  if (!stored) return;
  runningTask = stored;
  pollTaskStatus();
};

const requireAdmin = async () => {
  const token = getToken();
  if (!token) {
    window.location.href = "./login.html";
    return false;
  }
  try {
    const user = await fetchJson("/auth/me");
    currentAdmin = user;
    setUserBadge(user);
    if (user.role !== "admin") {
      window.location.href = "./index.html";
      return false;
    }
    return true;
  } catch {
    return false;
  }
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

tasksContainer.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-task]");
  if (!button) return;
  const taskName = button.dataset.task;
  runTask(taskName).catch((err) => {
    setStatus("Error");
    taskLog.textContent = err.message;
  });
});

autoArbToggle.addEventListener("click", async () => {
  initAudio();
  const enabled = Boolean(autoArbTimer);
  if (enabled) {
    stopAutoArb();
    return;
  }
  if (window.Notification && Notification.permission === "default") {
    try {
      await Notification.requestPermission();
    } catch {
      // Ignore notification permission errors.
    }
  }
  startAutoArb();
});

refreshBtn.addEventListener("click", () => {
  loadStats()
    .then(() => {
      setRefreshTime();
      setStatus("Ready");
    })
    .catch((err) => {
      setStatus("Error");
      statsSummary.textContent = err.message;
    });
});

usersRefreshBtn.addEventListener("click", () => {
  loadUsers().catch((err) => {
    usersSummary.textContent = err.message;
  });
});

userForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const email = userEmailInput.value.trim();
  const password = userPasswordInput.value.trim();
  const role = userRoleInput.value;
  if (!email || !password) {
    usersSummary.textContent = "Email and password are required.";
    return;
  }
  fetchJson("/admin/users", {
    method: "POST",
    body: JSON.stringify({ email, password, role }),
  })
    .then(() => {
      userEmailInput.value = "";
      userPasswordInput.value = "";
      userRoleInput.value = "user";
      return loadUsers();
    })
    .catch((err) => {
      usersSummary.textContent = err.message;
    });
});

usersTable.addEventListener("click", (event) => {
  const saveBtn = event.target.closest(".user-save");
  if (!saveBtn) return;
  const row = saveBtn.closest(".row");
  if (!row) return;
  const userId = row.dataset.userId;
  const roleSelect = row.querySelector(".user-role");
  const activeInput = row.querySelector(".user-active");
  const payload = {
    role: roleSelect ? roleSelect.value : undefined,
    is_active: activeInput ? activeInput.checked : undefined,
  };
  fetchJson(`/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
    .then(() => loadUsers())
    .catch((err) => {
      usersSummary.textContent = err.message;
    });
});

if (bookmakersForm) {
  bookmakersForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveBookmakersSetting().catch((err) => {
      if (bookmakersStatus) bookmakersStatus.textContent = err.message;
    });
  });
}

apiBaseInput.value = localStorage.getItem(API_BASE_KEY) || apiBaseInput.value;
apiBaseInput.addEventListener("change", () => {
  localStorage.setItem(API_BASE_KEY, apiBaseInput.value);
});

logoutBtn.addEventListener("click", () => {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  window.location.href = "./login.html";
});

requireAdmin()
  .then((ok) => {
    if (!ok) return;
    return Promise.all([loadStats(), loadUsers(), loadBookmakersSetting()]);
  })
  .then(() => {
    setRefreshTime();
    setStatus("Ready");
    resumeTaskStatus();
    if (localStorage.getItem(AUTO_ARB_KEY) === "1") {
      startAutoArb();
    } else {
      setAutoArbState(false);
    }
    return checkArbUpdates();
  })
  .catch((err) => {
    setStatus("Error");
    statsSummary.textContent = err.message;
  });
