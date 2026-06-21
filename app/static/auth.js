/**
 * Agent Studio — sign in & create account
 */
const Auth = (() => {
  function $(sel) { return document.querySelector(sel); }
  function show(el) { el?.classList.remove("hidden"); }
  function hide(el) { el?.classList.add("hidden"); }

  function formatError(detail) {
    if (!detail) return "Something went wrong. Please try again.";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((e) => e.msg || e.message || String(e)).join(". ");
    }
    return "Something went wrong. Please try again.";
  }

  async function request(path, method, body, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const opts = { method, credentials: "include", signal: controller.signal };
    if (body) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
    try {
      const res = await fetch(path, opts);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatError(data.detail) || res.statusText);
      }
      return data;
    } catch (err) {
      if (err.name === "AbortError") {
        throw new Error("Server not responding. Run: uvicorn app.main:app --port 8000");
      }
      if (err instanceof TypeError) {
        throw new Error("Cannot connect to server. Make sure it is running on port 8000.");
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  function setLoading(formId, loading) {
    const form = $(formId);
    if (!form) return;
    form.classList.toggle("is-loading", loading);
    form.querySelectorAll("input, button").forEach((el) => { el.disabled = loading; });
    const btn = form.querySelector('button[type="submit"]');
    if (btn) {
      btn.dataset.defaultText = btn.dataset.defaultText || btn.textContent;
      btn.textContent = loading ? "Please wait…" : btn.dataset.defaultText;
    }
  }

  function showError(message) {
    const el = $("#auth-error");
    el.textContent = message;
    show(el);
  }

  function clearError() { hide($("#auth-error")); }

  function switchTab(tab) {
    const isLogin = tab === "login";
    $("#tab-login").classList.toggle("active", isLogin);
    $("#tab-register").classList.toggle("active", !isLogin);
    show(isLogin ? $("#form-login") : $("#form-register"));
    hide(isLogin ? $("#form-register") : $("#form-login"));
    $(".auth-card")?.classList.toggle("auth-card--register", !isLogin);
    clearError();
  }

  function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  async function login(email, password) {
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) throw new Error("Email is required");
    if (!validateEmail(trimmedEmail)) throw new Error("Enter a valid email address");
    if (!password) throw new Error("Password is required");

    return request("/api/auth/login", "POST", { email: trimmedEmail, password });
  }

  async function register(name, email, password, confirmPassword, useCase = "all") {
    const trimmedName = name.trim();
    const trimmedEmail = email.trim().toLowerCase();

    if (!trimmedName) throw new Error("Name is required");
    if (!trimmedEmail) throw new Error("Email is required");
    if (!validateEmail(trimmedEmail)) throw new Error("Enter a valid email address");
    if (!password) throw new Error("Password is required");
    if (password.length < 8) throw new Error("Password must be at least 8 characters");
    if (password !== confirmPassword) throw new Error("Passwords do not match");

    return request("/api/auth/register", "POST", {
      name: trimmedName,
      email: trimmedEmail,
      password,
      use_case: useCase || "all",
    });
  }

  async function logout() {
    return request("/api/auth/logout", "POST");
  }

  async function checkSession() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const res = await fetch("/api/auth/session", { credentials: "include", signal: controller.signal });
      return res.json();
    } catch {
      return { authenticated: false, user: null };
    } finally {
      clearTimeout(timer);
    }
  }

  async function checkServer() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const res = await fetch("/api/health", { signal: controller.signal });
      return res.ok;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  async function getMe() {
    return request("/api/auth/me", "GET");
  }

  function bind(onSuccess) {
    $("#tab-login").addEventListener("click", () => switchTab("login"));
    $("#tab-register").addEventListener("click", () => switchTab("register"));

    $("#form-login").addEventListener("submit", async (e) => {
      e.preventDefault();
      clearError();
      setLoading("#form-login", true);
      try {
        const data = await login(
          $("#login-email").value,
          $("#login-password").value
        );
        await onSuccess(data.user, data.preferences, { isNewUser: false });
      } catch (err) {
        showError(err.message);
      } finally {
        setLoading("#form-login", false);
      }
    });

    $("#form-register").addEventListener("submit", async (e) => {
      e.preventDefault();
      clearError();
      setLoading("#form-register", true);
      try {
        const data = await register(
          $("#register-name").value,
          $("#register-email").value,
          $("#register-password").value,
          $("#register-confirm").value,
          $("#register-use-case")?.value || "all"
        );
        await onSuccess(data.user, data.preferences, { isNewUser: true });
      } catch (err) {
        showError(err.message);
      } finally {
        setLoading("#form-register", false);
      }
    });

    $$togglePassword();
  }

  function $$togglePassword() {
    document.querySelectorAll(".password-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = btn.parentElement.querySelector("input");
        const isPassword = input.type === "password";
        input.type = isPassword ? "text" : "password";
        btn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
        btn.textContent = isPassword ? "🙈" : "👁";
      });
    });
  }

  return { bind, checkSession, checkServer, getMe, logout, switchTab, showError, clearError };
})();

window.Auth = Auth;
