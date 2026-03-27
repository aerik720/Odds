const apiBaseInput = document.getElementById("login-api-base");
const DEFAULT_API_BASE =
  window.APP_CONFIG?.API_BASE || "http://127.0.0.1:8000";
const loginEmailInput = document.getElementById("login-email");
const loginPasswordInput = document.getElementById("login-password");
const loginSubmit = document.getElementById("login-submit");
const loginStatus = document.getElementById("login-status");
const registerEmailInput = document.getElementById("register-email");
const registerPasswordInput = document.getElementById("register-password");
const registerConfirmInput = document.getElementById("register-confirm");
const registerSubmit = document.getElementById("register-submit");
const registerStatus = document.getElementById("register-status");

const AUTH_TOKEN_KEY = "auth-token";
const API_BASE_KEY = "api-base";

const baseUrl = () => apiBaseInput.value.replace(/\/$/, "");

const setLoginStatus = (text) => {
  loginStatus.textContent = text;
};

const setRegisterStatus = (text) => {
  registerStatus.textContent = text;
};

const fetchJson = async (path, options = {}) => {
  const url = `${baseUrl()}${path}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  let res;
  try {
    res = await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Request timed out. Is the API running?");
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
};

const login = async () => {
  setLoginStatus("Signing in...");
  loginSubmit.disabled = true;
  const email = loginEmailInput.value.trim();
  const password = loginPasswordInput.value;
  if (!email || !password) {
    setLoginStatus("Enter your email and password.");
    loginSubmit.disabled = false;
    return;
  }
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  try {
    const payload = await fetchJson("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    localStorage.setItem(AUTH_TOKEN_KEY, payload.access_token);
    localStorage.setItem(API_BASE_KEY, apiBaseInput.value);
    setLoginStatus("Logged in. Redirecting...");
    window.location.href = "./index.html";
  } finally {
    loginSubmit.disabled = false;
  }
};

const register = async () => {
  setRegisterStatus("Creating account...");
  registerSubmit.disabled = true;
  const email = registerEmailInput.value.trim();
  const password = registerPasswordInput.value;
  const confirm = registerConfirmInput.value;
  if (!email || !password) {
    setRegisterStatus("Email and password are required.");
    registerSubmit.disabled = false;
    return;
  }
  if (password !== confirm) {
    setRegisterStatus("Passwords do not match.");
    registerSubmit.disabled = false;
    return;
  }
  try {
    await fetchJson("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    setRegisterStatus("Account created. Logging in...");
    loginEmailInput.value = email;
    loginPasswordInput.value = password;
    await login();
  } finally {
    registerSubmit.disabled = false;
  }
};

apiBaseInput.value =
  localStorage.getItem(API_BASE_KEY) || DEFAULT_API_BASE;
apiBaseInput.addEventListener("change", () => {
  localStorage.setItem(API_BASE_KEY, apiBaseInput.value);
});

if (localStorage.getItem(AUTH_TOKEN_KEY)) {
  window.location.href = "./index.html";
}

loginSubmit.addEventListener("click", () => {
  login().catch((err) => setLoginStatus(err.message));
});

registerSubmit.addEventListener("click", () => {
  register().catch((err) => setRegisterStatus(err.message));
});
