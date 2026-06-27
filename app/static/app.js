/**
 * Agent Studio — auth, API, live execution
 */
const AgentApp = (() => {
  let ws = null;
  let wsPingTimer = null;
  let wsReconnectTimer = null;
  let wsReconnectDelay = 3000;
  let currentUser = null;
  let currentPreferences = { use_case: "all", onboarding_completed: false };
  let runTimings = {};
  let completedRuns = 0;
  let failedRuns = 0;
  /** Maps agentId → canvas nodeId for the agent currently executing */
  const activeNodeRuns = {};
  let workflowRunning = false;
  let workflowStopRequested = false;
  let workflowAbortController = null;
  /** True when a single-agent run created the active Runs panel entry */
  let standaloneRunActive = false;

  function ensureAgentRunRecord(agentId, config = {}) {
    const existing = AgentStudio.getCurrentRunId?.();
    if (existing) return existing;
    const agent = AgentStudio.getAgent(agentId);
    const goal = String(config.goal || config.task || config.question || "").trim();
    const task = goal
      ? `${agent?.name || agentId}: ${goal.slice(0, 100)}`
      : `${agent?.name || agentId} run`;
    standaloneRunActive = true;
    AgentStudio.switchSidebarTab?.("runs");
    const id = AgentStudio.startWorkflowRun(task);
    AgentStudio.logRunEntry({
      agent: "System",
      type: "started",
      message: `Running ${agent?.name || agentId}`,
    });
    return id;
  }

  function maybeFinishStandaloneRun(status = "completed") {
    if (!standaloneRunActive || workflowRunning) return;
    AgentStudio.finishWorkflowRun(status);
    standaloneRunActive = false;
  }

  const $ = (sel) => document.querySelector(sel);

  async function api(path, method = "GET", body = null, signal = null) {
    const opts = { method, credentials: "include" };
    if (signal) opts.signal = signal;
    if (body) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const msg = formatApiError(data.detail) || res.statusText;
      if (res.status === 401 && !path.startsWith("/api/auth/")) {
        showAuth();
      }
      throw new Error(msg);
    }
    return data;
  }

  function formatApiError(detail) {
    if (!detail) return null;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((e) => e.msg || e.message).join(". ");
    return null;
  }

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function showAuth() {
    hide($("#studio"));
    show($("#auth-screen"));
    disconnectWs();
    if (window.AgentStudio?.resetForLogout) {
      AgentStudio.resetForLogout();
    }
    currentUser = null;
  }

  function showStudio(user, preferences, options = {}) {
    currentUser = user;
    if (preferences) currentPreferences = preferences;
    hide($("#auth-screen"));
    show($("#studio"));
    setUserUI(user);
    if (window.AgentStudio?.initStudioForUser) {
      AgentStudio.initStudioForUser(user.id || user.email || "guest", {
        isNewUser: Boolean(options.isNewUser),
      });
    } else if (window.AgentStudio?.renderLibrary) {
      AgentStudio.renderLibrary();
    }
    refreshGmailStatus();
    bindYouTubeActions();
  }

  async function afterStudioReady(user, preferences, options = {}) {
    const prefs = preferences || currentPreferences;
    currentPreferences = prefs;

    if (window.AgentOnboarding) {
      AgentOnboarding.configure({ user, preferences: prefs, api });
      if (AgentOnboarding.shouldAutoPrompt(prefs)) {
        requestAnimationFrame(() => AgentOnboarding.showPrompt());
      } else if (
        (prefs?.onboarding_completed_count || 0) > 0
        || prefs?.onboarding_completed
      ) {
        if (window.AgentStudio?.showPersonalizedWelcome) {
          AgentStudio.showPersonalizedWelcome(user.name, prefs?.use_case || "all");
        }
      }
    }
    await connectWs();
    await pollPendingHitl();
  }

  async function loadUserContext() {
    const me = await Auth.getMe();
    currentPreferences = me.preferences || currentPreferences;
    return me;
  }

  function setUserUI(user) {
    $("#user-name").textContent = user.name;
    $("#dropdown-name").textContent = user.name;
    $("#dropdown-email").textContent = user.email;
    const initial = (user.name || "A")[0].toUpperCase();
    $("#profile-initial").textContent = initial;
    $("#dropdown-initial").textContent = initial;
  }

  function setLiveStatus(online) {
    const dot = $("#connection-status");
    dot.classList.toggle("online", online);
    dot.title = online ? "Live" : "Disconnected";
  }

  async function init() {
    Auth.bind(async (user, preferences, options = {}) => {
      showStudio(user, preferences, options);
      try {
        const me = await loadUserContext();
        updateGmailUI(me.gmail);
        updateYouTubeUI(me.youtube);
        afterStudioReady(user, me.preferences || preferences, options);
      } catch {
        updateGmailUI({ connected: false, email: null });
        updateYouTubeUI({ connected: false, channel: null });
        afterStudioReady(user, preferences, options);
      }
    });
    bindAuth();

    const serverOk = await Auth.checkServer();
    const statusEl = document.getElementById("auth-server-status");
    if (statusEl) {
      if (serverOk) {
        statusEl.textContent = "Server connected";
        statusEl.className = "auth-server-status online";
      } else {
        statusEl.textContent = "Server offline — run: .\\start.bat";
        statusEl.className = "auth-server-status";
      }
      statusEl.classList.remove("hidden");
    }

    try {
      const session = await Auth.checkSession();
      if (session.authenticated && serverOk && !currentUser) {
        const me = await loadUserContext();
        showStudio(me.user, me.preferences);
        updateGmailUI(me.gmail);
        updateYouTubeUI(me.youtube);
        afterStudioReady(me.user, me.preferences);
        if (new URLSearchParams(location.search).get("gmail") === "connected") {
          if (window.AgentStudio) {
            AgentStudio.selectNodeByAgentId("gmail-organizer");
            updateGmailUI(me.gmail);
            AgentStudio.appendConsole("logs", {
              agent: "Gmail Organizer", type: "started",
              message: `Gmail connected${me.gmail.email ? `: ${me.gmail.email}` : ""} — scanning today's emails…`,
              time: new Date(),
            });
          }
          history.replaceState({}, "", location.pathname);
        }
        if (new URLSearchParams(location.search).get("youtube") === "connected") {
          if (window.AgentStudio) {
            AgentStudio.selectNodeByAgentId("content-director", true);
            updateYouTubeUI(me.youtube);
            AgentStudio.logRunEntry({
              agent: "Content Director",
              type: "completed",
              message: `YouTube connected${me.youtube?.channel?.channel_title ? `: ${me.youtube.channel.channel_title}` : ""} — enter your goal and click Run Agent`,
            });
          }
          history.replaceState({}, "", location.pathname);
        }
      } else if (!currentUser) {
        showAuth();
      }
    } catch {
      if (!currentUser) showAuth();
    }
    bindKnowledgeAsk();
  }

  async function refreshKbStats() {
    const el = document.getElementById("kb-stats");
    const modalEl = document.getElementById("kb-modal-stats");
    try {
      const data = await api("/api/knowledge/status");
      const label = data.parents
        ? `${data.documents || 0} docs · ${data.parents} parents · ${data.children || data.chunks || 0} child chunks`
        : `${data.documents || 0} docs · ${data.chunks || 0} chunks`;
      if (el) el.textContent = label;
      if (modalEl) modalEl.textContent = label;
    } catch {
      const fallback = "Not indexed yet";
      if (el) el.textContent = fallback;
      if (modalEl) modalEl.textContent = fallback;
    }
  }

  function openKbAskModal() {
    const modal = document.getElementById("kb-ask-modal");
    if (!modal) return;
    refreshKbStats();
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.getElementById("kb-modal-question")?.focus();
  }

  function closeKbAskModal() {
    const modal = document.getElementById("kb-ask-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  async function submitKbQuestion() {
    const input = document.getElementById("kb-modal-question");
    const answerWrap = document.getElementById("kb-modal-answer");
    const loading = document.getElementById("kb-modal-loading");
    const result = document.getElementById("kb-modal-result");
    const question = input?.value?.trim();
    if (!question) return;

    if (answerWrap) answerWrap.classList.remove("hidden");
    if (loading) loading.classList.remove("hidden");
    if (result) {
      result.classList.add("hidden");
      result.innerHTML = "";
    }

    try {
      const data = await api("/api/knowledge/ask", "POST", {
        question,
        collection: "org-knowledge",
        top_k: 5,
      });
      const sources = (data.sources || [])
        .map(
          (s) =>
            `<li><strong>${escapeHtml(s.metadata?.filename || s.document_id || "Source")}</strong> — ${escapeHtml(s.preview || "")}</li>`
        )
        .join("");
      const modeTag = data.retrieval === "hierarchical_parent_child"
        ? '<span class="kb-mode-tag">Hierarchical RAG</span>'
        : "";
      if (result) {
        result.innerHTML = `<strong>Answer</strong>${modeTag}<div class="kb-answer-body">${escapeHtml(data.answer || "")}</div>${
          sources ? `<strong>Parent context sources</strong><ul class="kb-sources-list">${sources}</ul>` : ""
        }`;
        result.classList.remove("hidden");
      }
    } catch (e) {
      if (result) {
        result.innerHTML = `<p class="error-text">${escapeHtml(e.message)}</p>`;
        result.classList.remove("hidden");
      }
    } finally {
      if (loading) loading.classList.add("hidden");
    }
  }

  function bindKnowledgeAsk() {
    refreshKbStats();
    document.getElementById("btn-kb-ask")?.addEventListener("click", openKbAskModal);
    document.getElementById("kb-ask-close")?.addEventListener("click", closeKbAskModal);
    document.getElementById("kb-ask-backdrop")?.addEventListener("click", closeKbAskModal);
    document.getElementById("kb-modal-submit")?.addEventListener("click", submitKbQuestion);
    document.getElementById("kb-modal-clear")?.addEventListener("click", () => {
      const input = document.getElementById("kb-modal-question");
      const answerWrap = document.getElementById("kb-modal-answer");
      const result = document.getElementById("kb-modal-result");
      if (input) input.value = "";
      if (result) result.innerHTML = "";
      if (answerWrap) answerWrap.classList.add("hidden");
      input?.focus();
    });
    document.getElementById("kb-modal-question")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        submitKbQuestion();
      }
    });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function bindAuth() {
    $("#btn-logout").onclick = async () => {
      await Auth.logout();
      showAuth();
      Auth.switchTab("login");
    };
    $("#welcome-banner-close")?.addEventListener("click", () => {
      AgentStudio?.dismissWelcomeBanner?.();
    });
    $("#btn-restart-tour")?.addEventListener("click", () => {
      $("#profile-dropdown")?.classList.add("hidden");
      AgentOnboarding?.start(true);
    });
  }

  function disconnectWs() {
    if (wsPingTimer) {
      clearInterval(wsPingTimer);
      wsPingTimer = null;
    }
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
    if (ws) {
      ws.onclose = null;
      ws.close();
      ws = null;
    }
    setLiveStatus(false);
  }

  async function connectWs() {
    if (!currentUser) return;
    disconnectWs();

    let ticket = "";
    try {
      const res = await api("/api/auth/ws-ticket");
      ticket = res.ticket || "";
    } catch {
      /* cookie auth may still work */
    }

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const qs = ticket ? `?ticket=${encodeURIComponent(ticket)}` : "";
    ws = new WebSocket(`${proto}://${location.host}/api/events/ws${qs}`);

    ws.onopen = () => {
      wsReconnectDelay = 3000;
      setLiveStatus(true);
      pollPendingHitl();
      wsPingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send('{"type":"ping"}');
        }
      }, 25000);
    };

    ws.onclose = () => {
      setLiveStatus(false);
      if (wsPingTimer) {
        clearInterval(wsPingTimer);
        wsPingTimer = null;
      }
      if (currentUser) {
        wsReconnectTimer = setTimeout(() => {
          connectWs();
        }, wsReconnectDelay);
        wsReconnectDelay = Math.min(wsReconnectDelay * 1.5, 30000);
      }
    };

    ws.onerror = () => {
      setLiveStatus(false);
    };

    ws.onmessage = (e) => {
      let event;
      try {
        event = JSON.parse(e.data);
      } catch {
        return;
      }
      if (event.type === "connected" || event.type === "pong") return;
      handleEvent(event);
    };
  }

  function setAgentVisualStatus(agentId, status, execTime) {
    const nodeId = activeNodeRuns[agentId];
    if (nodeId) {
      AgentStudio.highlightNodeById(nodeId, status, execTime);
    } else {
      AgentStudio.highlightExecution(agentId, status, execTime);
    }
  }

  let pendingHitlRequest = null;

  async function pollPendingHitl() {
    try {
      const res = await api("/api/agents/human-input/pending");
      const pending = res?.pending || [];
      const bar = document.getElementById("hitl-resume-bar");
      const barText = document.getElementById("hitl-resume-text");
      if (!pending.length) {
        bar?.classList.add("hidden");
        return;
      }
      const latest = pending[pending.length - 1];
      if (!latest?.request_id) return;
      const overlay = document.getElementById("hitl-overlay");
      const panelOpen = overlay && !overlay.classList.contains("hidden");
      if (!panelOpen) {
        if (bar) {
          bar.classList.remove("hidden");
          if (barText) {
            barText.textContent = `${latest.agent_name || "Agent"} is waiting — ${latest.phase === "review" ? "review output" : "answer questions"}`;
          }
        }
        window.__pendingHitlPayload = latest;
      }
      if (pendingHitlRequest?.request_id === latest.request_id && panelOpen) return;
      showHitlPanel(latest);
    } catch {
      /* ignore */
    }
  }

  function openHitlFromBar() {
    const payload = window.__pendingHitlPayload || pendingHitlRequest;
    if (payload) showHitlPanel(payload);
    else pollPendingHitl();
  }

  function showHitlPanel(payload) {
    const overlay = document.getElementById("hitl-overlay");
    const form = document.getElementById("hitl-form");
    const outputSection = document.getElementById("hitl-output-section");
    const outputPre = document.getElementById("hitl-output");
    if (!overlay || !form) return;

    pendingHitlRequest = payload;
    window.__pendingHitlPayload = payload;
    document.getElementById("hitl-resume-bar")?.classList.add("hidden");
    document.getElementById("hitl-title").textContent = payload.phase === "review"
      ? "Review agent output"
      : "Answer a few questions";
    document.getElementById("hitl-agent").textContent = payload.agent_name || payload.agent_id || "";
    document.getElementById("hitl-phase").textContent = payload.phase === "review" ? "Review" : "Input";

    const draft = payload.draft_output;
    if (draft && outputSection && outputPre) {
      outputSection.classList.remove("hidden");
      outputPre.textContent = JSON.stringify(draft, null, 2);
    } else if (outputSection) {
      outputSection.classList.add("hidden");
    }

    form.innerHTML = "";
    (payload.questions || []).forEach((q) => {
      const field = document.createElement("div");
      field.className = "hitl-field";
      const label = document.createElement("label");
      label.textContent = q.label || q.id;
      label.setAttribute("for", `hitl-${q.id}`);
      field.appendChild(label);

      let input;
      if (q.type === "select") {
        input = document.createElement("select");
        (q.options || []).forEach((opt) => {
          const o = document.createElement("option");
          o.value = opt;
          o.textContent = opt;
          input.appendChild(o);
        });
      } else if (q.type === "textarea") {
        input = document.createElement("textarea");
        input.placeholder = q.placeholder || "";
      } else {
        input = document.createElement("input");
        input.type = "text";
        input.placeholder = q.placeholder || "";
      }
      input.id = `hitl-${q.id}`;
      input.name = q.id;
      input.required = !q.optional;
      field.appendChild(input);
      form.appendChild(field);
    });

    overlay.classList.remove("hidden");
    overlay.setAttribute("aria-hidden", "false");
    AgentStudio.switchSidebarTab?.("runs");
    const submitBtn = document.getElementById("hitl-submit");
    if (submitBtn) submitBtn.disabled = false;
  }

  function hideHitlPanel() {
    const overlay = document.getElementById("hitl-overlay");
    if (overlay) {
      overlay.classList.add("hidden");
      overlay.setAttribute("aria-hidden", "true");
    }
    pendingHitlRequest = null;
  }

  async function submitHitlResponse(e) {
    e.preventDefault();
    if (!pendingHitlRequest?.request_id) return;
    const form = document.getElementById("hitl-form");
    const submitBtn = document.getElementById("hitl-submit");
    if (submitBtn) submitBtn.disabled = true;
    const answers = {};
    (pendingHitlRequest.questions || []).forEach((q) => {
      const el = form?.querySelector(`[name="${q.id}"]`);
      if (el) answers[q.id] = el.value;
    });
    try {
      await api("/api/agents/human-input/respond", "POST", {
        request_id: pendingHitlRequest.request_id,
        answers,
      });
      const phase = pendingHitlRequest.phase;
      hideHitlPanel();
      AgentStudio.logRunEntry({
        agent: pendingHitlRequest.agent_name || "Agent",
        agentId: pendingHitlRequest.agent_id || "",
        type: "progress",
        message: phase === "review"
          ? "Approved — continuing workflow…"
          : "Thanks — generating draft (review panel will appear next)…",
      });
    } catch (err) {
      if (submitBtn) submitBtn.disabled = false;
      AgentStudio.logRunEntry({
        agent: "System",
        type: "error",
        message: err.message || "Failed to submit response",
      });
    }
  }

  document.getElementById("hitl-form")?.addEventListener("submit", submitHitlResponse);
  document.getElementById("hitl-resume-btn")?.addEventListener("click", openHitlFromBar);

  function handleEvent(event) {
    const agentId = event.agent_id;
    const agentName = event.agent_name;
    const type = event.event_type;
    const resultId = event.data?.result_id || null;

    AgentStudio.logRunEntry({
      agent: agentName,
      agentId,
      type,
      message: event.message,
      time: event.timestamp,
      resultId: (type === "completed" || type === "error") ? resultId : null,
    });

    if (type === "completed" || type === "error") {
      AgentStudio.refreshResultsQueue?.();
      if (resultId) {
        AgentStudio.switchSidebarTab?.("queue");
      }
    }

    if (type === "started") {
      runTimings[agentId] = Date.now();
      setAgentVisualStatus(agentId, "running");
    }

    if (type === "error") {
      failedRuns++;
      const elapsed = runTimings[agentId] ? ((Date.now() - runTimings[agentId]) / 1000).toFixed(1) : null;
      setAgentVisualStatus(agentId, "error", elapsed);
      delete activeNodeRuns[agentId];
      updateSuccessMetrics();
      maybeFinishStandaloneRun("failed");
    }

    if (type === "cancelled") {
      const elapsed = runTimings[agentId] ? ((Date.now() - runTimings[agentId]) / 1000).toFixed(1) : null;
      setAgentVisualStatus(agentId, "idle", elapsed);
      delete activeNodeRuns[agentId];
      delete runTimings[agentId];
      maybeFinishStandaloneRun("stopped");
    }

    if (type === "completed") {
      completedRuns++;
      const elapsed = runTimings[agentId] ? ((Date.now() - runTimings[agentId]) / 1000).toFixed(1) : null;
      setAgentVisualStatus(agentId, "done", elapsed);
      delete activeNodeRuns[agentId];
      updateSuccessMetrics();
      maybeFinishStandaloneRun("completed");

      if (agentId === "invoice-matcher" && event.data) {
        AgentStudio.setMetricSuccess(
          event.data.matched != null
            ? Math.round((event.data.matched / (event.data.matched + event.data.exceptions)) * 100)
            : null
        );
      }
    }

    if (type === "awaiting_input" && event.data?.request_id) {
      showHitlPanel(event.data);
      setAgentVisualStatus(agentId, "running");
    }

    if (type === "progress" && event.data?.hitl?.request_id) {
      showHitlPanel(event.data.hitl);
    }

    if (type === "agent_output" && event.data?.result) {
      AgentStudio.logRunEntry({
        agent: agentName,
        agentId,
        type: "agent_output",
        message: event.message,
        time: event.timestamp,
        outputPreview: event.data.result,
      });
    }

    if (type === "match" || type === "exception" || type === "categorized" || type === "attachment_saved") {
      AgentStudio.selectNodeByAgentId(agentId, false);
    }
  }

  function updateSuccessMetrics() {
    const total = completedRuns + failedRuns;
    if (total > 0) {
      AgentStudio.setMetricSuccess(Math.round((completedRuns / total) * 100));
    }
    const times = Object.values(runTimings);
    if (times.length) {
      AgentStudio.setMetricAvgTime(Date.now() - times[times.length - 1]);
    }
  }

  async function uploadFiles(inputId, endpoint) {
    const input = document.getElementById(inputId);
    if (!input?.files.length) return;
    const form = new FormData();
    for (const f of input.files) form.append("files", f);
    const res = await fetch(endpoint, { method: "POST", body: form, credentials: "include" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail);
    }
    const data = await res.json();
    AgentStudio.appendConsole("logs", {
      agent: "Invoice Matcher",
      type: "progress",
      message: `Uploaded ${data.uploaded.join(", ")}`,
      time: new Date(),
    });
    input.value = "";
  }

  function updateGmailUI(gmail) {
    const hint = document.getElementById("gmail-hint");
    const btnConnect = document.getElementById("btn-connect-gmail");
    const btnDisconnect = document.getElementById("btn-disconnect-gmail");

    AgentStudio.setGmailConnected?.(!!gmail?.connected);

    if (!hint) return;

    if (gmail?.connected) {
      hint.textContent = `Connected: ${gmail.email}`;
      hint.className = "prop-hint connected";
      if (btnConnect) {
        btnConnect.textContent = "Gmail connected";
        btnConnect.classList.add("btn-connected");
        btnConnect.disabled = true;
      }
      if (btnDisconnect) btnDisconnect.classList.remove("hidden");
    } else {
      hint.textContent = "Connect your Gmail — scans today's emails only";
      hint.className = "prop-hint";
      if (btnConnect) {
        btnConnect.textContent = "Connect Gmail";
        btnConnect.classList.remove("btn-connected");
        btnConnect.disabled = false;
      }
      if (btnDisconnect) btnDisconnect.classList.add("hidden");
    }
  }

  async function refreshGmailStatus() {
    try {
      const me = await Auth.getMe();
      updateGmailUI(me.gmail);
      updateYouTubeUI(me.youtube);
    } catch { /* ignore */ }
  }

  async function connectGmail() {
    try {
      const { auth_url } = await api("/api/gmail/auth-url");
      if (!auth_url || !auth_url.startsWith("https://accounts.google.com/")) {
        throw new Error("Invalid OAuth URL from server. Check credentials and .env redirect URI.");
      }
      const hint = document.getElementById("gmail-hint");
      if (hint) hint.textContent = "Redirecting to Google sign-in…";
      window.location.href = auth_url;
    } catch (e) {
      const hint = document.getElementById("gmail-hint");
      if (hint) {
        hint.textContent = e.message;
        hint.className = "prop-hint";
      }
      AgentStudio.appendConsole("logs", { agent: "Gmail Organizer", type: "error", message: e.message, time: new Date() });
    }
  }

  function updateYouTubeUI(youtube) {
    const hints = [
      document.getElementById("youtube-hint"),
      document.getElementById("sidebar-youtube-hint"),
    ].filter(Boolean);
    const connectBtns = [
      document.getElementById("btn-connect-youtube"),
      document.getElementById("sidebar-btn-connect-youtube"),
    ].filter(Boolean);
    const disconnectBtns = [
      document.getElementById("btn-disconnect-youtube"),
      document.getElementById("sidebar-btn-disconnect-youtube"),
    ].filter(Boolean);

    AgentStudio.setYouTubeConnected?.(!!youtube?.connected);

    const connected = !!youtube?.connected;
    const title = youtube?.channel?.channel_title;
    const subs = youtube?.channel?.subscriber_count;

    hints.forEach((hint) => {
      if (connected && title) {
        const subLabel = subs != null ? ` · ${Number(subs).toLocaleString()} subscribers` : "";
        hint.textContent = `Connected: ${title}${subLabel}`;
        hint.className = hint.id === "sidebar-youtube-hint" ? "connection-hint connected" : "prop-hint connected";
      } else {
        hint.textContent = hint.id === "sidebar-youtube-hint"
          ? "Connect your channel for CreatorOS"
          : "Connect your YouTube channel to enable publishing, analytics, and trend research.";
        hint.className = hint.id === "sidebar-youtube-hint" ? "connection-hint" : "prop-hint";
      }
    });

    connectBtns.forEach((btn) => {
      btn.textContent = connected ? "YouTube connected" : "Connect YouTube";
      btn.classList.toggle("btn-connected", connected);
      btn.disabled = connected;
    });
    disconnectBtns.forEach((btn) => btn.classList.toggle("hidden", !connected));
  }

  async function refreshYouTubeStatus() {
    try {
      const data = await api("/api/youtube/status");
      updateYouTubeUI({ connected: data.connected, channel: data.channel });
    } catch { /* ignore */ }
  }

  async function connectYouTube() {
    try {
      const { auth_url } = await api("/api/youtube/auth-url");
      if (!auth_url?.startsWith("https://accounts.google.com/")) {
        throw new Error("Invalid OAuth URL. Enable YouTube Data API v3 in Google Cloud Console.");
      }
      const hint = document.getElementById("youtube-hint") || document.getElementById("sidebar-youtube-hint");
      if (hint) hint.textContent = "Redirecting to Google sign-in…";
      window.location.href = auth_url;
    } catch (e) {
      AgentStudio.logRunEntry?.({ agent: "System", type: "error", message: e.message });
    }
  }

  async function disconnectYouTube() {
    await api("/api/youtube/disconnect", "POST");
    updateYouTubeUI({ connected: false, channel: null });
  }

  function bindYouTubeActions() {
    ["btn-connect-youtube", "sidebar-btn-connect-youtube"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.onclick = connectYouTube;
    });
    ["btn-disconnect-youtube", "sidebar-btn-disconnect-youtube"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.onclick = disconnectYouTube;
    });
  }

  async function refreshGmailStatusOnly() {
    try {
      const me = await Auth.getMe();
      updateGmailUI(me.gmail);
    } catch { /* ignore */ }
  }

  function bindPropertyActions(agentId) {
    const uploadInv = document.getElementById("upload-invoices");
    const uploadPay = document.getElementById("upload-payments");
    if (uploadInv) {
      uploadInv.onchange = () =>
        uploadFiles("upload-invoices", "/api/data/invoices/upload").catch((e) =>
          AgentStudio.appendConsole("logs", { agent: "System", type: "error", message: e.message, time: new Date() })
        );
    }
    if (uploadPay) {
      uploadPay.onchange = () =>
        uploadFiles("upload-payments", "/api/data/payments/upload").catch((e) =>
          AgentStudio.appendConsole("logs", { agent: "System", type: "error", message: e.message, time: new Date() })
        );
    }

    const btnConnect = document.getElementById("btn-connect-gmail");
    const btnDisconnect = document.getElementById("btn-disconnect-gmail");
    if (btnConnect) btnConnect.onclick = connectGmail;
    if (btnDisconnect) {
      btnDisconnect.onclick = async () => {
        await api("/api/gmail/disconnect", "POST");
        updateGmailUI({ connected: false, email: null });
      };
    }

    if (agentId === "gmail-organizer" || agentId === "gmail-calendar") {
      refreshGmailStatusOnly();
    }
    if (AgentStudio.needsYouTubeConnection?.(agentId)) {
      refreshYouTubeStatus();
    }
    bindYouTubeActions();

    const plannerTask = document.getElementById("planner-task");
    const workflowTask = document.getElementById("workflow-task");
    if (plannerTask && workflowTask) {
      plannerTask.addEventListener("input", () => {
        workflowTask.value = plannerTask.value;
      });
    }
  }

  async function enrichRunConfig(agentId, nodeId, config) {
    const node = nodeId ? AgentStudio.getNodeById(nodeId) : null;
    let enriched = { ...config };

    if (nodeId && node && window.AgentModelRouter?.isAutoModel(enriched.model)) {
      let text = (enriched.text || enriched.source || enriched.question || "").trim();
      if (!text && nodeId) {
        text = (await resolveUpstreamInputText(nodeId)).trim();
      }
      const ctx = {
        ...AgentStudio.buildModelContext(node, enriched),
        text: text || AgentStudio.buildModelContext(node, enriched).text,
        task: AgentStudio.getWorkflowTask() || "",
      };
      if (agentId === "planner") {
        ctx.connected_agents = nodeId
          ? AgentStudio.getDownstreamAgentIds(nodeId)
          : (enriched.connectedAgents || []);
      }
      enriched = AgentStudio.resolveAgentModel(enriched, ctx);
      const pick = enriched._modelPick;
      if (pick && nodeId) {
        AgentStudio.setNodeResolvedModel(nodeId, pick);
        const modelName = window.AgentModels?.getModel(pick.modelId)?.name || pick.modelId;
        AgentStudio.logRunEntry({
          agent: AgentStudio.getAgent(agentId)?.name || agentId,
          agentId,
          type: "progress",
          message: `Auto model: ${modelName} — ${pick.reason}`,
        });
      }
    }

    return enriched;
  }

  async function runAgent(agentId, options = {}) {
    const agent = AgentStudio.getAgent(agentId);
    const nodeId = options.nodeId;
    let config = options.config || (nodeId ? AgentStudio.getNodeConfig(nodeId) : {});
    config = await enrichRunConfig(agentId, nodeId, config);
    const runId = options.runId ?? ensureAgentRunRecord(agentId, config);
    const runPayload = { run_id: runId };

    if (agentId === "planner") {
      const task = AgentStudio.getWorkflowTask() || "Organize today's emails and reconcile invoices";
      AgentStudio.selectNodeByAgentId("planner");
      if (nodeId) AgentStudio.highlightNodeById(nodeId, "running");
      else AgentStudio.highlightExecution(agentId, "running");
      const connected = nodeId
        ? AgentStudio.getDownstreamAgentIds(nodeId)
        : (options.connectedAgents || []);
      const plan = await api("/api/agents/planner/run", "POST", {
        task,
        context: options.context || "",
        connected_agents: connected,
        agent_config: {
          prompt: config.prompt,
          model: config.model,
          temperature: config.temperature,
          description: config.description,
        },
        ...runPayload,
      });
      AgentStudio.applyPlannerResult(plan);
      if (plan?.distressed_customers?.length) {
        plan.distressed_customers.forEach((customer) => {
          if (!customer.needs_call) return;
          AgentStudio.logRunEntry({
            agent: "Planner",
            agentId: "planner",
            type: "progress",
            message: `${(customer.urgency || "medium").toUpperCase()} — ${customer.name || "Customer"}: ${customer.issue_summary || customer.subject}`,
          });
        });
      } else if (plan?.phone_numbers?.length) {
        AgentStudio.logRunEntry({
          agent: "Planner",
          agentId: "planner",
          type: "progress",
          message: `Call plan: ${plan.phone_numbers.join(", ")}`,
        });
      }
      if (plan?.reasoning) {
        AgentStudio.logRunEntry({
          agent: "Planner",
          agentId: "planner",
          type: "progress",
          message: plan.reasoning,
        });
      }
      if (nodeId) AgentStudio.highlightNodeById(nodeId, "done", "0.5");
      else AgentStudio.highlightExecution(agentId, "done", "0.5");
      maybeFinishStandaloneRun("completed");
      return plan;
    }

    if (!agent?.runnable) {
      AgentStudio.appendConsole("logs", {
        agent: agent?.name || agentId, type: "progress",
        message: "Demo agent — simulated step", time: new Date(),
      });
      if (nodeId) AgentStudio.highlightNodeById(nodeId, "running");
      else AgentStudio.highlightExecution(agentId, "running");
      await delay(500);
      if (nodeId) AgentStudio.highlightNodeById(nodeId, "done", "0.5");
      else AgentStudio.highlightExecution(agentId, "done", "0.5");
      maybeFinishStandaloneRun("completed");
      return null;
    }

    AgentStudio.selectNodeByAgentId(agentId);
    if (nodeId) {
      activeNodeRuns[agentId] = nodeId;
      AgentStudio.highlightNodeById(nodeId, "running");
    } else {
      AgentStudio.highlightExecution(agentId, "running");
    }

    try {
      if (agentId === "invoice-matcher") {
        await api("/api/agents/invoice-matcher/run", "POST", runPayload);
      } else if (agentId === "gmail-organizer") {
        await api("/api/agents/gmail-organizer/run", "POST", {
          max_messages: config.max_messages || 200,
          scan_date: config.scan_date || null,
          ...runPayload,
        });
      } else if (agentId === "telecaller") {
        await api("/api/agents/telecaller/run", "POST", {
          phone_numbers: config.phone_numbers || [],
          message: config.message || "Hello",
          calls: config.calls || [],
          ...runPayload,
        });
      } else if (agentId === "mailer") {
        await api("/api/agents/mailer/run", "POST", {
          to: config.to || [],
          subject: config.subject || "Hello",
          body: config.body || "Hello",
          ...runPayload,
        });
      } else if (agentId === "gmail-calendar") {
        await api("/api/agents/gmail-calendar/run", "POST", {
          action: config.action || "list_events",
          date_from: config.date_from || null,
          date_to: config.date_to || null,
          max_results: config.max_results || 25,
          event_title: config.event_title || "Meeting",
          event_start: config.event_start || null,
          event_duration_minutes: config.event_duration_minutes || 30,
          attendees: config.attendees || [],
          ...runPayload,
        });
      } else if (agentId === "whatsapp") {
        await api("/api/agents/whatsapp/run", "POST", {
          phone_numbers: config.phone_numbers || [],
          message: config.message || "Hello",
          messages: config.messages || [],
          ...runPayload,
        });
      } else if (agentId === "data-scraper") {
        await api("/api/agents/data-scraper/run", "POST", {
          urls: config.urls || [],
          css_selector: config.css_selector || "",
          extract_links: config.extract_links !== false,
          max_links: config.max_links || 20,
          ...runPayload,
        });
      } else if (agentId === "file-download") {
        await api("/api/agents/file-download/run", "POST", {
          urls: config.urls || [],
          filenames: config.filenames || [],
          ...runPayload,
        });
      } else if (agent?.category === "understanding") {
        let text = (config.text || "").trim();
        if (!text && nodeId) {
          text = (await resolveUpstreamInputText(nodeId)).trim();
        }
        await api("/api/agents/understanding/run", "POST", {
          agent_id: agentId,
          text,
          reference_text: config.reference_text || "",
          agent_config: {
            prompt: config.prompt,
            model: config.model,
            temperature: config.temperature,
          },
          ...runPayload,
        });
      } else if (agentId === "org-knowledge-base") {
        let sources = config.sources || [];
        let folderPath = (config.folder_path || "").trim();
        const upstreamFolder = nodeId ? (await resolveUpstreamFolder(nodeId)).trim() : "";
        if (upstreamFolder && (!folderPath || folderPath === "invoices")) {
          folderPath = upstreamFolder;
        } else if (!folderPath && !sources.length) {
          folderPath = upstreamFolder || ".";
        }
        if (!sources.length || sources.every((s) => !String(s.folder || s.path || "").trim())) {
          sources = [{ type: "folder_pdf", folder: folderPath || "." }];
        } else if (folderPath) {
          sources = sources.map((s) => {
            if (String(s.type || "").toLowerCase().includes("folder") || s.type === "folder_pdf") {
              const f = String(s.folder || s.path || "").trim();
              return { ...s, type: "folder_pdf", folder: f || folderPath };
            }
            return s;
          });
        }
        await api("/api/agents/org-knowledge-base/run", "POST", {
          action: config.action || "build",
          collection: config.collection || "org-knowledge",
          folder_path: folderPath,
          sources,
          question: config.question || "",
          top_k: 8,
          ...runPayload,
        });
      } else if (agentId === "content-director") {
        await api("/api/agents/content-director/run", "POST", {
          creator_type: config.creator_type || "Content Creator",
          niche: config.niche || "",
          platforms: config.platforms?.length ? config.platforms : ["YouTube", "LinkedIn", "Twitter"],
          goal: config.goal || "Grow followers and leads",
          agent_config: {
            prompt: config.prompt,
            model: config.model,
            temperature: config.temperature,
            human_in_loop: config.human_in_loop !== false,
          },
          ...runPayload,
        });
      } else if (agent?.category === "content") {
        let context = {};
        if (nodeId) {
          const upstreamIds = AgentStudio.getUpstreamNodeIds?.(nodeId) || [];
          for (const upId of upstreamIds) {
            const upNode = AgentStudio.getNodeById?.(upId);
            if (!upNode?.agentId) continue;
            const row = await fetchLatestAgentResult(upNode.agentId);
            if (row?.result) {
              context[upNode.agentId] = row.result.result || row.result;
            }
          }
        }
        await api("/api/agents/content/run", "POST", {
          agent_id: agentId,
          creator_type: config.creator_type || "Content Creator",
          niche: config.niche || config.creator_type || "",
          platforms: config.platforms?.length ? config.platforms : ["YouTube", "LinkedIn", "Twitter"],
          goal: config.goal || "Grow followers and leads",
          context,
          agent_config: {
            prompt: config.prompt,
            model: config.model,
            temperature: config.temperature,
            human_in_loop: config.human_in_loop !== false,
          },
          ...runPayload,
        });
      } else if (agent?.category === "perception") {
        let source = (config.folder_path || config.source || config.text || "").trim();
        if (!source && nodeId) {
          if (agentId === "read-pdf") {
            source = (await resolveUpstreamFolder(nodeId)).trim();
          }
          if (!source) {
            source = (await resolveUpstreamInputText(nodeId)).trim();
          }
        }
        await api("/api/agents/perception/run", "POST", {
          agent_id: agentId,
          source,
          folder_path: agentId === "read-pdf" ? source : (config.folder_path || ""),
          agent_config: {
            prompt: config.prompt,
            model: config.model,
            temperature: config.temperature,
          },
          ...runPayload,
        });
      }

      await waitForAgent(agentId, nodeId);
      maybeFinishStandaloneRun("completed");
    } catch (err) {
      if (nodeId) AgentStudio.highlightNodeById(nodeId, "error");
      else AgentStudio.highlightExecution(agentId, "error");
      delete activeNodeRuns[agentId];
      maybeFinishStandaloneRun("failed");
      throw err;
    } finally {
      if (activeNodeRuns[agentId] === nodeId) {
        delete activeNodeRuns[agentId];
      }
    }
    return null;
  }

  function collectCompletedNodeIds(order) {
    const ids = [];
    order.forEach((node) => {
      const live = AgentStudio.getNodeById?.(node.id);
      const status = live?.status || node.status;
      if (status === "done") ids.push(node.id);
    });
    return ids;
  }

  function resetRunningNodes(order) {
    order.forEach((node) => {
      const live = AgentStudio.getNodeById?.(node.id);
      const status = live?.status || node.status;
      if (status === "running") AgentStudio.highlightNodeById(node.id, "idle");
    });
  }

  function beginWorkflowRun(task, options = {}) {
    workflowRunning = true;
    standaloneRunActive = false;
    workflowStopRequested = false;
    workflowAbortController = new AbortController();
    AgentStudio.updateWorkflowControlButtons?.();
    return AgentStudio.startWorkflowRun(task, options);
  }

  function endWorkflowRunControls() {
    workflowRunning = false;
    workflowStopRequested = false;
    workflowAbortController = null;
    AgentStudio.updateWorkflowControlButtons?.();
  }

  async function stopWorkflow() {
    if (!workflowRunning) return;
    workflowStopRequested = true;
    workflowAbortController?.abort();
    const runId = AgentStudio.getCurrentRunId?.();
    try {
      await api("/api/agents/cancel-all", "POST", { run_id: runId });
      await api("/api/workflows/cancel", "POST", { run_id: runId });
    } catch {
      /* ignore cancel errors */
    }
    AgentStudio.logRunEntry({
      agent: "System",
      type: "cancelled",
      message: "Workflow stop requested",
    });
  }

  async function stopAgent(agentId, nodeId) {
    workflowStopRequested = true;
    const runId = AgentStudio.getCurrentRunId?.();
    const toCancel = new Set([agentId]);
    if (agentId.startsWith("content-") && agentId !== "content-director") {
      toCancel.add("content-director");
    }
    if (agentId === "content-director") {
      AgentStudio.getWorkflowSnapshot?.().nodes
        ?.filter((n) => n.agentId?.startsWith("content-"))
        .forEach((n) => toCancel.add(n.agentId));
    }
    for (const id of toCancel) {
      try {
        await api(`/api/agents/${encodeURIComponent(id)}/cancel`, "POST", { run_id: runId });
      } catch {
        /* ignore */
      }
    }
    hideHitlPanel?.();
    if (nodeId) AgentStudio.highlightNodeById(nodeId, "idle");
    else AgentStudio.highlightExecution(agentId, "idle");
    AgentStudio.logRunEntry({
      agent: AgentStudio.getAgent(agentId)?.name || agentId,
      agentId,
      type: "cancelled",
      message: "Agent stop requested",
    });
  }

  async function runWorkflowLangChain(options = {}) {
    const snap = AgentStudio.getWorkflowSnapshot?.();
    if (!snap?.nodes?.length) {
      AgentStudio.logRunEntry({ agent: "System", type: "error", message: "Workflow is empty" });
      return;
    }

    const checkpoint = options.checkpoint || null;
    const task = checkpoint?.task || AgentStudio.getWorkflowTask() || "Run workflow";
    AgentStudio.setWorkflowTask(task);
    const runId = beginWorkflowRun(task, {
      reuseRunId: options.reuseRunId || null,
      checkpoint,
    });

    const agentNodes = snap.nodes.filter((n) => n.agentId && n.kind !== "model");
    const skipIds = new Set(checkpoint?.completedNodeIds || []);
    agentNodes.forEach((n) => {
      if (skipIds.has(n.id)) AgentStudio.highlightNodeById(n.id, "done", "—");
      else if (!workflowStopRequested) AgentStudio.highlightNodeById(n.id, "running");
    });

    AgentStudio.logRunEntry({
      agent: "System",
      type: "started",
      message: checkpoint
        ? `Resuming LangGraph workflow (${agentNodes.length - skipIds.size} steps remaining)`
        : `LangGraph workflow (${agentNodes.length} agents)`,
    });

    let stopped = false;
    try {
      const result = await api("/api/workflows/run", "POST", {
        task,
        run_id: runId,
        nodes: agentNodes,
        edges: snap.edges || [],
        agent_configs: snap.agent_configs || {},
        use_langchain: true,
        skip_node_ids: [...skipIds],
      }, workflowAbortController?.signal);

      if (result.status === "stopped" || workflowStopRequested) {
        stopped = true;
        const completed = result.node_order || collectCompletedNodeIds(agentNodes);
        completed.forEach((nid) => AgentStudio.highlightNodeById(nid, "done", "—"));
        resetRunningNodes(agentNodes);
        AgentStudio.saveWorkflowCheckpoint({
          completedNodeIds: completed,
          plan: checkpoint?.plan || null,
          task,
        });
        AgentStudio.logRunEntry({
          agent: "System",
          type: "cancelled",
          message: "Workflow stopped — click Resume to continue",
        });
      } else {
        agentNodes.forEach((n) => AgentStudio.highlightNodeById(n.id, "done", "1.0"));
        AgentStudio.logRunEntry({
          agent: "LangGraph",
          type: "completed",
          message: `Engine: ${result.engine || "langgraph"} — ${Object.keys(result.results || {}).length} steps`,
        });
        AgentStudio.finishWorkflowRun("completed");
      }
    } catch (e) {
      if (workflowStopRequested || e.name === "AbortError") {
        stopped = true;
        const completed = collectCompletedNodeIds(agentNodes);
        resetRunningNodes(agentNodes);
        AgentStudio.saveWorkflowCheckpoint({
          completedNodeIds: completed,
          plan: checkpoint?.plan || null,
          task,
        });
        AgentStudio.logRunEntry({
          agent: "System",
          type: "cancelled",
          message: "Workflow stopped — click Resume to continue",
        });
      } else {
        agentNodes.forEach((n) => {
          if (!skipIds.has(n.id)) AgentStudio.highlightNodeById(n.id, "error");
        });
        AgentStudio.logRunEntry({ agent: "LangGraph", type: "error", message: e.message });
        AgentStudio.finishWorkflowRun("failed");
      }
    } finally {
      endWorkflowRunControls();
    }
  }

  async function runWorkflowSequential(options = {}) {
    const order = AgentStudio.getExecutionOrder();
    if (!order.length) {
      AgentStudio.logRunEntry({ agent: "System", type: "error", message: "Workflow is empty" });
      return;
    }

    const checkpoint = options.checkpoint || null;
    const completedSet = new Set(checkpoint?.completedNodeIds || []);
    const task = checkpoint?.task || AgentStudio.getWorkflowTask() || "Organize today's emails and reconcile invoices";
    AgentStudio.setWorkflowTask(task);
    beginWorkflowRun(task, {
      reuseRunId: options.reuseRunId || null,
      checkpoint,
    });

    AgentStudio.logRunEntry({
      agent: "System",
      type: "started",
      message: checkpoint
        ? `Resuming workflow (${order.length - completedSet.size} steps remaining)`
        : `Running workflow (${order.length} steps)`,
    });

    let plan = checkpoint?.plan || null;
    let failed = false;
    let stopped = false;

    for (const node of order) {
      if (workflowStopRequested) {
        stopped = true;
        break;
      }

      if (completedSet.has(node.id)) {
        AgentStudio.highlightNodeById(node.id, "done");
        continue;
      }

      const agentId = node.agentId;
      const agent = AgentStudio.getAgent(agentId);

      try {
        if (agentId === "planner") {
          plan = await runAgent(agentId, { nodeId: node.id });
          if (workflowStopRequested) { stopped = true; break; }
          continue;
        }

        if (agentId === "chat-agent") {
          AgentStudio.highlightNodeById(node.id, "running");
          AgentStudio.logRunEntry({
            agent: node.label || agent?.name || "Chat",
            agentId,
            type: "progress",
            message: node.id === "n-input" ? `Task: ${task}` : "Delivering workflow results",
          });
          await delay(400);
          if (workflowStopRequested) { stopped = true; break; }
          AgentStudio.highlightNodeById(node.id, "done", "0.4");
          continue;
        }

        if (plan && agent?.runnable && !plan.agents_to_run?.includes(agentId)) {
          AgentStudio.logRunEntry({
            agent: agent.name, agentId, type: "progress",
            message: "Skipped — not in planner output",
          });
          AgentStudio.highlightNodeById(node.id, "idle");
          continue;
        }

        await runAgent(agentId, {
          nodeId: node.id,
          config: AgentStudio.getNodeConfig(node.id),
        });

        if (workflowStopRequested) { stopped = true; break; }
        await delay(400);
      } catch (e) {
        if (workflowStopRequested || e.name === "AbortError") {
          stopped = true;
          break;
        }
        failed = true;
        AgentStudio.highlightNodeById(node.id, "error");
        AgentStudio.logRunEntry({
          agent: agent?.name || agentId,
          agentId,
          type: "error",
          message: e.message,
        });
      }
    }

    if (stopped) {
      const completedNodeIds = collectCompletedNodeIds(order);
      resetRunningNodes(order);
      AgentStudio.saveWorkflowCheckpoint({
        completedNodeIds,
        plan,
        task,
      });
      AgentStudio.logRunEntry({
        agent: "System",
        type: "cancelled",
        message: "Workflow stopped — click Resume to continue",
      });
    } else {
      AgentStudio.finishWorkflowRun(failed ? "failed" : "completed");
    }
    endWorkflowRunControls();
  }

  async function runWorkflow(options = {}) {
    if (workflowRunning) return;
    const useLangchain = document.getElementById("use-langchain")?.checked;
    if (useLangchain) {
      return runWorkflowLangChain(options);
    }
    return runWorkflowSequential(options);
  }

  async function resumeWorkflow(runId) {
    if (workflowRunning) return;
    const checkpoint = AgentStudio.getRunCheckpoint?.(runId);
    if (!checkpoint?.completedNodeIds?.length) {
      AgentStudio.logRunEntry({ agent: "System", type: "error", message: "Nothing to resume for this run" });
      return;
    }
    if (checkpoint.task) AgentStudio.setWorkflowTask(checkpoint.task);
    return runWorkflow({ reuseRunId: runId, checkpoint });
  }

  function waitForAgent(agentId, nodeId, timeoutMs = 600000) {
    return new Promise((resolve) => {
      const start = Date.now();
      const poll = async () => {
        if (workflowStopRequested) return resolve();

        const status = AgentStudio.getAgentStatus(agentId);
        if (status === "done" || status === "error" || status === "idle") return resolve();

        try {
          await pollPendingHitl();
          const server = await api("/api/agents/status");
          if (server && server[agentId] === false) {
            const current = AgentStudio.getAgentStatus(agentId);
            if (current === "running") {
              const elapsed = runTimings[agentId]
                ? ((Date.now() - runTimings[agentId]) / 1000).toFixed(1)
                : null;
              setAgentVisualStatus(agentId, "done", elapsed);
            }
            return resolve();
          }
        } catch {
          /* server poll optional */
        }

        if (Date.now() - start > timeoutMs) {
          if (AgentStudio.getAgentStatus(agentId) === "running") {
            setAgentVisualStatus(agentId, "error");
          }
          return resolve();
        }
        setTimeout(poll, 800);
      };
      setTimeout(poll, 1000);
    });
  }

  function delay(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function formatGmailSummaries(summaries) {
    if (!Array.isArray(summaries) || !summaries.length) return "";
    return summaries
      .map((s) => {
        const parts = [
          s.subject ? `Subject: ${s.subject}` : "",
          s.from ? `From: ${s.from}` : "",
          s.category ? `Category: ${s.category}` : "",
          s.body_preview || s.snippet || "",
        ].filter(Boolean);
        return parts.join("\n");
      })
      .join("\n\n---\n\n");
  }

  function extractTextFromResult(agentId, row) {
    if (!row) return "";
    const payload = row.result || {};
    const agent = AgentStudio.getAgent(agentId);

    if (agentId === "gmail-organizer" || agentId === "planner") {
      const summaries = payload.email_summaries
        || payload.chart_data?.email_summaries;
      const text = formatGmailSummaries(summaries);
      if (text) return text;
      if (agentId === "planner" && payload.reasoning) {
        return String(payload.reasoning);
      }
    }

    if (agentId === "data-scraper") {
      const results = payload.results || [];
      if (results.length) {
        return results
          .map((r) => [r.title, r.text_preview].filter(Boolean).join("\n"))
          .join("\n\n---\n\n");
      }
    }

    if (agent?.category === "understanding") {
      const inner = payload.result;
      if (typeof inner === "string") return inner;
      if (inner && typeof inner === "object") {
        return JSON.stringify(inner, null, 2);
      }
    }

    if (agent?.category === "perception") {
      const inner = payload.result;
      if (typeof inner === "string") return inner;
      if (inner?.combined_content) return String(inner.combined_content);
      if (inner?.content) return String(inner.content);
      if (inner?.text) return String(inner.text);
      if (inner?.transcript) return String(inner.transcript);
      if (inner?.body) return typeof inner.body === "string" ? inner.body : JSON.stringify(inner.body, null, 2);
      if (Array.isArray(inner?.documents)) {
        return inner.documents
          .filter((d) => d?.content)
          .map((d) => `=== ${d.filename || "document"} ===\n${d.content}`)
          .join("\n\n");
      }
      if (inner && typeof inner === "object") {
        return JSON.stringify(inner, null, 2);
      }
    }

    if (payload.body_preview) return String(payload.body_preview);
    if (payload.text) return String(payload.text);
    if (payload.text_preview) return String(payload.text_preview);
    if (row.message) return String(row.message);

    try {
      const copy = { ...payload };
      delete copy.event_type;
      delete copy.run_id;
      delete copy.result_id;
      delete copy.email_categories;
      delete copy.attachment_categories;
      const keys = Object.keys(copy);
      if (keys.length) return JSON.stringify(copy, null, 2).slice(0, 12000);
    } catch (_) {
      /* ignore */
    }
    return "";
  }

  async function fetchLatestAgentResult(agentId) {
    try {
      return await api(`/api/queue/latest/${encodeURIComponent(agentId)}`);
    } catch (_) {
      return null;
    }
  }

  function extractFolderFromResult(agentId, row) {
    if (!row) return "";
    const payload = row.result || {};

    if (agentId === "gmail-organizer") {
      if (payload.output_dir) return String(payload.output_dir);
      if ((payload.attachments_saved || 0) > 0) return "gmail_attachments";
    }
    if (agentId === "file-download") {
      if (payload.output_dir) {
        const dir = String(payload.output_dir);
        if (dir.includes("downloads")) return "downloads";
        return dir;
      }
      const results = payload.results || [];
      if (results.length) return "downloads";
    }
    if (agentId === "read-pdf") {
      if (payload.folder_relative) return String(payload.folder_relative);
      if (payload.folder) return String(payload.folder);
    }
    if (agentId === "org-knowledge-base") {
      if (payload.folder_relative) return String(payload.folder_relative);
    }
    if (payload.folder_relative) return String(payload.folder_relative);
    if (payload.output_dir) return String(payload.output_dir);
    return "";
  }

  async function resolveUpstreamFolder(nodeId) {
    const upstreamIds = AgentStudio.getUpstreamNodeIds?.(nodeId) || [];
    for (const upId of upstreamIds) {
      const upNode = AgentStudio.getNodeById?.(upId);
      if (!upNode?.agentId) continue;
      const row = await fetchLatestAgentResult(upNode.agentId);
      const folder = extractFolderFromResult(upNode.agentId, row);
      if (folder.trim()) return folder.trim();
    }
    return "";
  }

  async function resolveUpstreamInputText(nodeId) {
    const upstreamIds = AgentStudio.getUpstreamNodeIds?.(nodeId) || [];
    if (!upstreamIds.length) return "";

    const chunks = [];
    for (const upId of upstreamIds) {
      const upNode = AgentStudio.getNodeById?.(upId);
      if (!upNode?.agentId) continue;
      const row = await fetchLatestAgentResult(upNode.agentId);
      const text = extractTextFromResult(upNode.agentId, row);
      if (text.trim()) chunks.push(text.trim());
    }
    return chunks.join("\n\n===\n\n");
  }

  return {
    init,
    bindPropertyActions,
    pollPendingHitl,
    openHitlFromBar,
    runAgent,
    runWorkflow,
    stopWorkflow,
    stopAgent,
    resumeWorkflow,
    refreshGmailStatus,
    connectGmail,
    connectYouTube,
    api,
  };
})();

window.AgentApp = AgentApp;
document.addEventListener("DOMContentLoaded", () => AgentApp.init());
