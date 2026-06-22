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

  const $ = (sel) => document.querySelector(sel);

  async function api(path, method = "GET", body = null) {
    const opts = { method, credentials: "include" };
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
        afterStudioReady(user, me.preferences || preferences, options);
      } catch {
        updateGmailUI({ connected: false, email: null });
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
      } else if (!currentUser) {
        showAuth();
      }
    } catch {
      if (!currentUser) showAuth();
    }
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
      AgentStudio.highlightExecution(agentId, "running");
    }

    if (type === "error") {
      failedRuns++;
      const elapsed = runTimings[agentId] ? ((Date.now() - runTimings[agentId]) / 1000).toFixed(1) : null;
      AgentStudio.highlightExecution(agentId, "error", elapsed);
      updateSuccessMetrics();
    }

    if (type === "completed") {
      completedRuns++;
      const elapsed = runTimings[agentId] ? ((Date.now() - runTimings[agentId]) / 1000).toFixed(1) : null;
      AgentStudio.highlightExecution(agentId, "done", elapsed);
      updateSuccessMetrics();

      if (agentId === "invoice-matcher" && event.data) {
        AgentStudio.setMetricSuccess(
          event.data.matched != null
            ? Math.round((event.data.matched / (event.data.matched + event.data.exceptions)) * 100)
            : null
        );
      }
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
    if (btnConnect) {
      btnConnect.onclick = async () => {
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
      };
    }
    if (btnDisconnect) {
      btnDisconnect.onclick = async () => {
        await api("/api/gmail/disconnect", "POST");
        updateGmailUI({ connected: false, email: null });
      };
    }

    if (agentId === "gmail-organizer" || agentId === "gmail-calendar") {
      refreshGmailStatus();
    }

    const plannerTask = document.getElementById("planner-task");
    const workflowTask = document.getElementById("workflow-task");
    if (plannerTask && workflowTask) {
      plannerTask.addEventListener("input", () => {
        workflowTask.value = plannerTask.value;
      });
    }
  }

  async function runAgent(agentId, options = {}) {
    const agent = AgentStudio.getAgent(agentId);
    const nodeId = options.nodeId;
    const config = options.config || (nodeId ? AgentStudio.getNodeConfig(nodeId) : {});
    const runId = options.runId ?? AgentStudio.getCurrentRunId?.() ?? null;
    const runPayload = runId ? { run_id: runId } : {};

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
      return null;
    }

    AgentStudio.selectNodeByAgentId(agentId);
    if (nodeId) AgentStudio.highlightNodeById(nodeId, "running");
    else AgentStudio.highlightExecution(agentId, "running");

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
    }
    return null;
  }

  async function runWorkflow() {
    const order = AgentStudio.getExecutionOrder();
    if (!order.length) {
      AgentStudio.logRunEntry({ agent: "System", type: "error", message: "Workflow is empty" });
      return;
    }

    const task = AgentStudio.getWorkflowTask() || "Organize today's emails and reconcile invoices";
    AgentStudio.setWorkflowTask(task);
    AgentStudio.startWorkflowRun(task);

    AgentStudio.logRunEntry({
      agent: "System", type: "started",
      message: `Running workflow (${order.length} steps)`,
    });

    let plan = null;
    let failed = false;

    for (const node of order) {
      const agentId = node.agentId;
      const agent = AgentStudio.getAgent(agentId);

      try {
        if (agentId === "planner") {
          plan = await runAgent(agentId, { nodeId: node.id });
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

        if (agent?.runnable) {
          await waitForAgent(agentId);
        }

        await delay(400);
      } catch (e) {
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

    AgentStudio.finishWorkflowRun(failed ? "failed" : "completed");
  }

  function waitForAgent(agentId, timeoutMs = 120000) {
    return new Promise((resolve) => {
      const start = Date.now();
      const poll = () => {
        const status = AgentStudio.getAgentStatus(agentId);
        if (status === "done" || status === "error") return resolve();
        if (Date.now() - start > timeoutMs) return resolve();
        setTimeout(poll, 600);
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
    runAgent,
    runWorkflow,
    refreshGmailStatus,
    api,
  };
})();

window.AgentApp = AgentApp;
document.addEventListener("DOMContentLoaded", () => AgentApp.init());
