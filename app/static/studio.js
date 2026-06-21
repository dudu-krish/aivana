/**
 * Agent Studio — canvas, workflow, and UI orchestration
 */
const AgentStudio = (() => {
  const AGENT_DEFS = {
    "invoice-matcher": {
      id: "invoice-matcher", name: "Invoice Matcher", icon: "📋",
      type: "Reconciliation", runnable: true,
      description: "Pull invoice & payment data, reconcile matches, surface exceptions.",
      prompt: "Match invoices to payments by vendor, reference, and amount. Flag mismatches.",
      model: "gpt-4o", temperature: 0.1,
      inputs: ["invoices", "payments"], outputs: ["matched", "exceptions"],
      tools: ["pandas", "excel-reader"],
    },
    "gmail-organizer": {
      id: "gmail-organizer", name: "Gmail Organizer", icon: "📧",
      type: "Email", runnable: true,
      description: "Connect Gmail, scan emails, apply category labels, and organize attachments.",
      prompt: "Read each email, categorize it, apply the matching Gmail label, and file attachments.",
      model: "gpt-4o-mini", temperature: 0.2,
      inputs: ["gmail_inbox"], outputs: ["categories", "attachments"],
      tools: ["gmail-api", "file-organizer"],
    },
    "pdf-reader": {
      id: "pdf-reader", name: "PDF Reader", icon: "📄",
      type: "Document", runnable: false,
      description: "Extract and summarize text from PDF documents.",
      prompt: "Read PDF content and extract structured data.",
      model: "gpt-4o", temperature: 0.3,
      inputs: ["pdf_file"], outputs: ["text", "summary"],
      tools: ["pdf-parser"],
    },
    "web-search": {
      id: "web-search", name: "Web Search", icon: "🌐",
      type: "Research", runnable: false,
      description: "Search the web and return relevant results.",
      prompt: "Search for information and return cited results.",
      model: "gpt-4o-mini", temperature: 0.4,
      inputs: ["query"], outputs: ["results"],
      tools: ["web-search"],
    },
    "planner": {
      id: "planner", name: "Planner", icon: "🧠",
      type: "Orchestration", runnable: true,
      description: "Break down tasks and route to appropriate agents.",
      prompt: "Analyze user input and create an execution plan.",
      model: "gpt-4o", temperature: 0.5,
      inputs: ["user_input"], outputs: ["plan", "steps"],
      tools: ["reasoning"],
    },
    "speech-agent": {
      id: "speech-agent", name: "Speech Agent", icon: "🎤",
      type: "Audio", runnable: false,
      description: "Transcribe and process speech input.",
      prompt: "Convert speech to text and extract intent.",
      model: "whisper-1", temperature: 0,
      inputs: ["audio"], outputs: ["transcript"],
      tools: ["speech-to-text"],
    },
    "chat-agent": {
      id: "chat-agent", name: "Chat Agent", icon: "💬",
      type: "Conversation", runnable: false,
      description: "Handle conversational interactions with memory.",
      prompt: "Respond naturally while maintaining context.",
      model: "gpt-4o", temperature: 0.7,
      inputs: ["message", "history"], outputs: ["response"],
      tools: ["memory"],
    },
    "analytics": {
      id: "analytics", name: "Analytics", icon: "📊",
      type: "Insights", runnable: false,
      description: "Generate insights and visualizations from agent outputs.",
      prompt: "Analyze data and produce summary metrics.",
      model: "gpt-4o-mini", temperature: 0.2,
      inputs: ["data"], outputs: ["metrics", "charts"],
      tools: ["chart-builder"],
    },
    "telecaller": {
      id: "telecaller", name: "Telecaller", icon: "📞",
      type: "Outreach", runnable: true,
      description: "Place outbound calls to phone numbers and speak a greeting.",
      prompt: "Call each number and say hello in a clear, friendly voice.",
      model: "gpt-4o-mini", temperature: 0.2,
      inputs: ["phone_numbers"], outputs: ["call_results"],
      tools: ["twilio-voice"],
    },
    "mailer": {
      id: "mailer", name: "Mailer", icon: "✉️",
      type: "Email", runnable: true,
      description: "Send emails to one or more recipients.",
      prompt: "Compose and send the configured email to all recipients.",
      model: "gpt-4o-mini", temperature: 0.3,
      inputs: ["recipients", "subject", "body"], outputs: ["delivery_status"],
      tools: ["smtp"],
    },
    "gmail-calendar": {
      id: "gmail-calendar", name: "Gmail Calendar", icon: "📅",
      type: "Calendar", runnable: true,
      description: "List or create Google Calendar events using your connected account.",
      prompt: "Read calendar events for the date range, or create a new meeting.",
      model: "gpt-4o-mini", temperature: 0.2,
      inputs: ["date_range", "event_details"], outputs: ["events", "event_link"],
      tools: ["google-calendar-api"],
    },
    "whatsapp": {
      id: "whatsapp", name: "WhatsApp", icon: "💬",
      type: "Messaging", runnable: true,
      description: "Send WhatsApp messages to phone numbers via Twilio.",
      prompt: "Send the configured WhatsApp message to each recipient.",
      model: "gpt-4o-mini", temperature: 0.3,
      inputs: ["phone_numbers", "message"], outputs: ["delivery_status"],
      tools: ["twilio-whatsapp"],
    },
    "data-scraper": {
      id: "data-scraper", name: "Data Scraper", icon: "🕷️",
      type: "Research", runnable: true,
      description: "Fetch web pages and extract text, links, and structured data.",
      prompt: "Scrape each URL, extract content, and save JSON results.",
      model: "gpt-4o-mini", temperature: 0.1,
      inputs: ["urls", "css_selector"], outputs: ["scraped_data"],
      tools: ["httpx", "beautifulsoup"],
    },
    "file-download": {
      id: "file-download", name: "File Download", icon: "⬇️",
      type: "Files", runnable: true,
      description: "Download files from URLs into your workspace storage.",
      prompt: "Download each file URL and save it to the downloads folder.",
      model: "gpt-4o-mini", temperature: 0,
      inputs: ["urls"], outputs: ["saved_files"],
      tools: ["httpx"],
    },
  };

  const EMPTY_WORKFLOW = { nodes: [], edges: [] };

  const NODE_W = 220;
  const NODE_H = 128;

  let workflow = structuredClone(EMPTY_WORKFLOW);
  let savedWorkflows = [];
  let currentWorkflowId = null;
  let userStoragePrefix = "guest";
  let activeUserId = null;
  let agentStatuses = {};
  let gmailConnected = null;
  let selectedNodeId = null;

  const GMAIL_AGENT_IDS = new Set(["gmail-organizer", "gmail-calendar"]);

  function needsGmailConnection(agentId) {
    return GMAIL_AGENT_IDS.has(agentId);
  }

  function setGmailConnected(connected) {
    gmailConnected = !!connected;
    renderNodes();
    renderLibrary($("#search-agents")?.value || "");
  }
  let contextNodeId = null;
  let connectingFrom = null;
  let connectCursor = null;

  let workflowRuns = [];
  let currentRunId = null;
  let activeRunViewId = null;
  let resultsQueue = [];
  let activeResultId = null;
  let activeSidebarTab = "runs";
  let nodeDidDrag = false;
  let dragStartPos = null;
  let savedAgentConfigs = {};

  // Canvas state
  let scale = 1;
  let panX = 40;
  let panY = 20;
  let isPanning = false;
  let panStart = { x: 0, y: 0 };
  let dragNode = null;
  let dragOffset = { x: 0, y: 0 };
  let draftSaveTimer = null;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function runsStorageKey() {
    return `${userStoragePrefix}_agent_studio_workflow_runs`;
  }

  function savedWorkflowsStorageKey() {
    return `${userStoragePrefix}_agent_studio_saved_workflows`;
  }

  function agentConfigsStorageKey() {
    return `${userStoragePrefix}_agent_studio_agent_configs`;
  }

  function draftWorkflowStorageKey(userId = activeUserId) {
    if (!userId || userId === "guest") return null;
    return `${userId}_agent_studio_draft`;
  }

  function persistDraftWorkflow() {
    const key = draftWorkflowStorageKey();
    if (!key) return;
    try {
      localStorage.setItem(
        key,
        JSON.stringify({
          workflow: structuredClone(workflow),
          name: $("#workflow-name")?.value || "",
          task: getWorkflowTask(),
          currentWorkflowId,
          updatedAt: new Date().toISOString(),
        }),
      );
    } catch { /* ignore */ }
  }

  function loadDraftWorkflow(userId) {
    const key = draftWorkflowStorageKey(userId);
    if (!key) return null;
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const draft = JSON.parse(raw);
      if (!draft?.workflow || !Array.isArray(draft.workflow.nodes)) return null;
      return draft;
    } catch {
      return null;
    }
  }

  function clearDraftWorkflow(userId = activeUserId) {
    const key = draftWorkflowStorageKey(userId);
    if (!key) return;
    try {
      localStorage.removeItem(key);
    } catch { /* ignore */ }
  }

  function applyDraft(draft) {
    workflow = structuredClone(draft.workflow);
    currentWorkflowId = draft.currentWorkflowId || null;
    const nameEl = $("#workflow-name");
    const taskEl = $("#workflow-task");
    if (nameEl) nameEl.value = draft.name || "";
    if (draft.task) setWorkflowTask(draft.task);
    else if (taskEl) taskEl.value = "";
    updateBreadcrumb(draft.name || "Untitled Workflow");
  }

  function resetCanvasState() {
    workflow = structuredClone(EMPTY_WORKFLOW);
    currentWorkflowId = null;
    agentStatuses = {};
    selectedNodeId = null;
    closeAgentModal();
    const nameEl = $("#workflow-name");
    const taskEl = $("#workflow-task");
    if (nameEl) nameEl.value = "";
    if (taskEl) taskEl.value = "";
    updateBreadcrumb("Untitled Workflow");
    activeTemplateId = null;
    renderWorkflowTemplates();
  }

  function loadSavedAgentConfigs() {
    try {
      const raw = localStorage.getItem(agentConfigsStorageKey());
      savedAgentConfigs = raw ? JSON.parse(raw) : {};
    } catch {
      savedAgentConfigs = {};
    }
  }

  function persistSavedAgentConfigs() {
    try {
      localStorage.setItem(agentConfigsStorageKey(), JSON.stringify(savedAgentConfigs));
    } catch { /* ignore */ }
  }

  function getEffectiveAgentConfig(agentId, nodeConfig = {}) {
    const def = getAgent(agentId) || {};
    const saved = savedAgentConfigs[agentId] || {};
    return {
      ...def,
      ...saved,
      ...nodeConfig,
      name: nodeConfig.name ?? saved.name ?? def.name,
      description: nodeConfig.description ?? saved.description ?? def.description,
      prompt: nodeConfig.prompt ?? saved.prompt ?? def.prompt,
      temperature: nodeConfig.temperature ?? saved.temperature ?? def.temperature,
      model: nodeConfig.model ?? saved.model ?? def.model,
      memory: nodeConfig.memory ?? saved.memory ?? "none",
    };
  }

  function applyTheme(theme) {
    const next = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("agent_studio_theme", next);
    } catch { /* ignore */ }
  }

  function toggleTheme() {
    const isDark = document.documentElement.dataset.theme === "dark";
    applyTheme(isDark ? "light" : "dark");
  }

  function initTheme() {
    let saved = "light";
    try {
      saved = localStorage.getItem("agent_studio_theme") || "light";
    } catch { /* ignore */ }
    applyTheme(saved);
  }

  function init() {
    initTheme();
    renderLibrary();
    renderWorkflowTemplates();
    renderSavedWorkflows();
    updateEmptyCanvasHint();
    bindCanvasEvents();
    bindUI();
  }

  function initStudioForUser(userId, options = {}) {
    const nextId = userId || "guest";
    const isNewUser = Boolean(options.isNewUser);

    if (activeUserId && activeUserId !== "guest" && activeUserId !== nextId) {
      persistDraftWorkflow();
    }

    activeUserId = nextId;
    userStoragePrefix = nextId;
    loadWorkflowRuns();
    loadSavedWorkflows();
    loadSavedAgentConfigs();
    resetCanvasState();

    if (isNewUser) {
      clearDraftWorkflow(nextId);
    } else if (nextId !== "guest") {
      const draft = loadDraftWorkflow(nextId);
      if (draft) applyDraft(draft);
    }

    renderLibrary();
    renderWorkflowTemplates();
    renderCanvas();
    resetCanvasView();
    renderWorkflowRuns();
    renderSavedWorkflows();
    updateEmptyCanvasHint();
    loadResultsQueue();
  }

  function resetForLogout() {
    if (activeUserId && activeUserId !== "guest") {
      persistDraftWorkflow();
    }
    activeUserId = null;
    userStoragePrefix = "guest";
    savedWorkflows = [];
    workflowRuns = [];
    resultsQueue = [];
    activeResultId = null;
    savedAgentConfigs = {};
    gmailConnected = null;
    resetCanvasState();
    closeAgentModal();
    closeResultModal();
    renderResultsQueue();
  }

  function getAgent(id) {
    return AGENT_DEFS[id];
  }

  function setAgentStatus(agentId, status) {
    agentStatuses[agentId] = status;
    workflow.nodes.forEach((n) => {
      if (n.agentId === agentId) n.status = status;
    });
    renderLibrary();
    renderNodes();
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatRunTime(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString([], {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  function loadWorkflowRuns() {
    try {
      const raw = localStorage.getItem(runsStorageKey());
      workflowRuns = raw ? JSON.parse(raw) : [];
    } catch {
      workflowRuns = [];
    }
  }

  function saveWorkflowRuns() {
    try {
      localStorage.setItem(runsStorageKey(), JSON.stringify(workflowRuns.slice(0, 50)));
    } catch { /* ignore quota */ }
  }

  function loadSavedWorkflows() {
    try {
      const raw = localStorage.getItem(savedWorkflowsStorageKey());
      savedWorkflows = raw ? JSON.parse(raw) : [];
    } catch {
      savedWorkflows = [];
    }
  }

  function persistSavedWorkflows() {
    try {
      localStorage.setItem(savedWorkflowsStorageKey(), JSON.stringify(savedWorkflows.slice(0, 30)));
    } catch { /* ignore quota */ }
  }

  function updateBreadcrumb(name) {
    const el = $("#breadcrumb-workflow");
    if (el) el.textContent = name || "Untitled Workflow";
  }

  function updateEmptyCanvasHint() {
    const hint = $("#canvas-empty");
    if (!hint) return;
    hint.classList.toggle("hidden", workflow.nodes.length > 0);
  }

  function resetCanvasView() {
    scale = 1;
    panX = 40;
    panY = 20;
    applyTransform();
    updateEmptyCanvasHint();
  }

  function deleteNode(nodeId) {
    workflow.nodes = workflow.nodes.filter((n) => n.id !== nodeId);
    workflow.edges = workflow.edges.filter((e) => e.from !== nodeId && e.to !== nodeId);
    if (selectedNodeId === nodeId) selectedNodeId = null;
    closeAgentModal();
    renderCanvas();
    updateEmptyCanvasHint();
  }

  function saveCurrentWorkflow() {
    const nameEl = $("#workflow-name");
    let name = nameEl?.value.trim();
    if (!name) {
      name = window.prompt("Name this workflow:")?.trim();
      if (!name) return;
      if (nameEl) nameEl.value = name;
    }

    const payload = {
      id: currentWorkflowId || `wf-${Date.now()}`,
      name,
      task: getWorkflowTask(),
      nodes: structuredClone(workflow.nodes),
      edges: structuredClone(workflow.edges),
      updatedAt: new Date().toISOString(),
    };

    const idx = savedWorkflows.findIndex((w) => w.id === payload.id);
    if (idx >= 0) savedWorkflows[idx] = payload;
    else savedWorkflows.unshift(payload);

    currentWorkflowId = payload.id;
    persistSavedWorkflows();
    renderSavedWorkflows();
    updateBreadcrumb(name);
    persistDraftWorkflow();
    logRunEntry({ agent: "System", type: "completed", message: `Workflow "${name}" saved` });
  }

  function loadSavedWorkflow(id) {
    const wf = savedWorkflows.find((w) => w.id === id);
    if (!wf) return;
    workflow = {
      nodes: structuredClone(wf.nodes || []),
      edges: structuredClone(wf.edges || []),
    };
    currentWorkflowId = wf.id;
    if (wf.task) setWorkflowTask(wf.task);
    const nameEl = $("#workflow-name");
    if (nameEl) nameEl.value = wf.name || "";
    updateBreadcrumb(wf.name);
    selectedNodeId = null;
    closeAgentModal();
    renderCanvas();
    if (workflow.nodes.length) fitCanvasToWorkflow();
    else resetCanvasView();
    renderSavedWorkflows();
    persistDraftWorkflow();
  }

  function newWorkflow() {
    if (workflow.nodes.length) {
      const ok = window.confirm("Start a new blank workflow? Unsaved changes on the canvas will be lost.");
      if (!ok) return;
    }
    workflow = structuredClone(EMPTY_WORKFLOW);
    currentWorkflowId = null;
    agentStatuses = {};
    selectedNodeId = null;
    closeAgentModal();

    const nameEl = $("#workflow-name");
    const taskEl = $("#workflow-task");
    if (nameEl) nameEl.value = "";
    if (taskEl) taskEl.value = "";
    updateBreadcrumb("Untitled Workflow");
    activeTemplateId = null;
    renderWorkflowTemplates();

    renderCanvas();
    resetCanvasView();
    renderSavedWorkflows();
    clearDraftWorkflow();
    updateEmptyCanvasHint();
  }

  function parseListField(value) {
    return String(value || "")
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function collectBaseConfigFromModal() {
    const cfg = {};
    const name = document.getElementById("prop-name")?.value?.trim();
    if (name) cfg.name = name;
    const descEl = document.getElementById("prop-desc");
    if (descEl) cfg.description = descEl.value.trim();
    const promptEl = document.getElementById("prop-prompt");
    if (promptEl) cfg.prompt = promptEl.value.trim();
    const tempEl = document.getElementById("prop-temp");
    if (tempEl?.value !== "" && tempEl?.value != null) {
      cfg.temperature = parseFloat(tempEl.value);
    }
    const model = document.getElementById("prop-model")?.value;
    if (model) cfg.model = model;
    const memory = document.getElementById("prop-memory")?.value;
    if (memory) cfg.memory = memory;
    return cfg;
  }

  function collectNodeConfig(nodeId) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (!node) return {};
    const base = collectBaseConfigFromModal();
    if (node.agentId === "telecaller") {
      return {
        ...base,
        phone_numbers: parseListField(document.getElementById("telecaller-numbers")?.value),
        message: document.getElementById("telecaller-message")?.value?.trim() || "Hello",
        calls: node.config?.calls || [],
      };
    }
    if (node.agentId === "mailer") {
      return {
        ...base,
        to: parseListField(document.getElementById("mailer-recipients")?.value),
        subject: document.getElementById("mailer-subject")?.value?.trim() || "Hello",
        body: document.getElementById("mailer-body")?.value?.trim() || "Hello",
      };
    }
    if (node.agentId === "gmail-organizer") {
      const scanDate = document.getElementById("gmail-scan-date")?.value?.trim() || "";
      return {
        ...base,
        scan_date: scanDate,
        max_messages: 200,
      };
    }
    if (node.agentId === "gmail-calendar") {
      return {
        ...base,
        action: document.getElementById("calendar-action")?.value || "list_events",
        date_from: document.getElementById("calendar-date-from")?.value?.trim() || "",
        date_to: document.getElementById("calendar-date-to")?.value?.trim() || "",
        max_results: parseInt(document.getElementById("calendar-max-results")?.value || "25", 10),
        event_title: document.getElementById("calendar-event-title")?.value?.trim() || "Meeting",
        event_start: document.getElementById("calendar-event-start")?.value?.trim() || "",
        event_duration_minutes: parseInt(document.getElementById("calendar-event-duration")?.value || "30", 10),
        attendees: parseListField(document.getElementById("calendar-attendees")?.value),
      };
    }
    if (node.agentId === "whatsapp") {
      return {
        ...base,
        phone_numbers: parseListField(document.getElementById("whatsapp-numbers")?.value),
        message: document.getElementById("whatsapp-message")?.value?.trim() || "Hello",
        messages: node.config?.messages || [],
      };
    }
    if (node.agentId === "data-scraper") {
      return {
        ...base,
        urls: parseListField(document.getElementById("scraper-urls")?.value),
        css_selector: document.getElementById("scraper-selector")?.value?.trim() || "",
        extract_links: document.getElementById("scraper-extract-links")?.checked !== false,
        max_links: parseInt(document.getElementById("scraper-max-links")?.value || "20", 10),
      };
    }
    if (node.agentId === "file-download") {
      return {
        ...base,
        urls: parseListField(document.getElementById("download-urls")?.value),
        filenames: parseListField(document.getElementById("download-filenames")?.value),
      };
    }
    return { ...(node.config || {}), ...base };
  }

  function applyNodeConfig(nodeId, config) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (node) node.config = { ...(node.config || {}), ...config };
  }

  function getNodeConfig(nodeId) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (!node) return {};
    let config = getEffectiveAgentConfig(node.agentId, node.config || {});
    if (selectedNodeId === nodeId) {
      config = { ...config, ...collectNodeConfig(nodeId) };
    }
    return config;
  }

  function saveSelectedNodeConfig() {
    if (!selectedNodeId) return false;
    const node = workflow.nodes.find((n) => n.id === selectedNodeId);
    if (!node) return false;
    const config = collectNodeConfig(selectedNodeId);
    applyNodeConfig(selectedNodeId, config);
    if (config.name) node.label = config.name;
    savedAgentConfigs[node.agentId] = { ...(savedAgentConfigs[node.agentId] || {}), ...config };
    persistSavedAgentConfigs();
    renderNodes();
    return true;
  }

  function deleteSavedWorkflow(id, e) {
    e?.stopPropagation();
    savedWorkflows = savedWorkflows.filter((w) => w.id !== id);
    if (currentWorkflowId === id) currentWorkflowId = null;
    persistSavedWorkflows();
    renderSavedWorkflows();
  }

  function renderSavedWorkflows() {
    const list = $("#saved-workflows-list");
    if (!list) return;

    if (!savedWorkflows.length) {
      list.innerHTML = '<li class="saved-empty">No saved workflows yet</li>';
      return;
    }

    list.innerHTML = savedWorkflows.map((wf) => {
      const nodes = wf.nodes?.length || 0;
      const edges = wf.edges?.length || 0;
      const when = wf.updatedAt ? formatRunTime(wf.updatedAt) : "";
      return `
        <li class="saved-workflow-item${currentWorkflowId === wf.id ? " active" : ""}" data-wf-id="${wf.id}">
          <div style="flex:1;min-width:0">
            <div class="saved-workflow-name">${escapeHtml(wf.name)}</div>
            <div class="saved-workflow-meta">${nodes} agents · ${edges} links${when ? ` · ${when}` : ""}</div>
          </div>
          <button type="button" class="saved-workflow-delete" data-delete-wf="${wf.id}" title="Delete saved workflow">×</button>
        </li>`;
    }).join("");

    list.querySelectorAll(".saved-workflow-item").forEach((item) => {
      item.addEventListener("click", () => loadSavedWorkflow(item.dataset.wfId));
    });
    list.querySelectorAll("[data-delete-wf]").forEach((btn) => {
      btn.addEventListener("click", (e) => deleteSavedWorkflow(btn.dataset.deleteWf, e));
    });
  }

  function startWorkflowRun(task) {
    const run = {
      id: `run-${Date.now()}`,
      task: task || "Workflow run",
      startedAt: new Date().toISOString(),
      endedAt: null,
      status: "running",
      logs: [],
    };
    workflowRuns.unshift(run);
    if (workflowRuns.length > 50) workflowRuns.length = 50;
    currentRunId = run.id;
    activeRunViewId = run.id;
    saveWorkflowRuns();
    renderWorkflowRuns();
    return run.id;
  }

  function finishWorkflowRun(status = "completed") {
    if (!currentRunId) return;
    const run = workflowRuns.find((r) => r.id === currentRunId);
    if (run) {
      run.status = status;
      run.endedAt = new Date().toISOString();
      saveWorkflowRuns();
      renderWorkflowRuns();
    }
    currentRunId = null;
  }

  function logRunEntry(entry) {
    let run = currentRunId ? workflowRuns.find((r) => r.id === currentRunId) : null;
    if (!run) run = workflowRuns.find((r) => r.status === "running");
    if (!run && workflowRuns.length) run = workflowRuns[0];
    if (!run) return;
    run.logs.push({
      agent: entry.agent || "System",
      agentId: entry.agentId || "",
      type: entry.type || "progress",
      message: entry.message || "",
      time: entry.time || new Date().toISOString(),
      resultId: entry.resultId || null,
    });
    if (entry.type === "error" && run.status === "running") run.status = "failed";
    if (run.logs.length > 100) run.logs.shift();
    saveWorkflowRuns();
    renderWorkflowRuns();
  }

  function renderWorkflowRuns() {
    const list = $("#runs-list");
    const countEl = $("#runs-count");
    if (!list) return;

    if (countEl) {
      countEl.textContent = `${workflowRuns.length} run${workflowRuns.length === 1 ? "" : "s"}`;
    }

    if (!workflowRuns.length) {
      list.innerHTML = '<p class="runs-empty">No workflow runs yet. Click Run Workflow to start.</p>';
      return;
    }

    list.innerHTML = workflowRuns.map((run) => {
      const recent = run.logs.slice(-4);
      const stepsHtml = recent.length
        ? recent.map((log) =>
            `<div class="run-step ${log.type === "error" ? "error" : ""}">${escapeHtml(log.agent)}: ${escapeHtml(log.message)}</div>`
          ).join("")
        : '<div class="run-step">Waiting for activity…</div>';
      return `
        <article class="run-card ${run.status}${activeRunViewId === run.id ? " active" : ""}" data-run-id="${run.id}">
          <div class="run-card-head">
            <span class="run-status-badge ${run.status}">${run.status}</span>
            <time>${formatRunTime(run.startedAt)}</time>
          </div>
          <p class="run-task">${escapeHtml(run.task)}</p>
          <div class="run-steps">${stepsHtml}</div>
        </article>`;
    }).join("");

    list.querySelectorAll(".run-card").forEach((card) => {
      card.onclick = () => openRunLogsModal(card.dataset.runId);
    });
  }

  function openRunLogsModal(runId) {
    const run = workflowRuns.find((r) => r.id === runId);
    if (!run) return;

    activeRunViewId = runId;
    renderWorkflowRuns();

    const modal = $("#run-logs-modal");
    const statusEl = $("#run-logs-status");
    const metaEl = $("#run-logs-meta");
    const taskEl = $("#run-logs-task");
    const bodyEl = $("#run-logs-body");
    if (!modal || !bodyEl) return;

    if (statusEl) {
      statusEl.textContent = run.status;
      statusEl.className = `run-status-badge ${run.status}`;
    }
    if (metaEl) {
      const parts = [`Started: ${formatRunTime(run.startedAt)}`];
      if (run.endedAt) parts.push(`Ended: ${formatRunTime(run.endedAt)}`);
      parts.push(`${run.logs.length} log${run.logs.length === 1 ? "" : "s"}`);
      metaEl.textContent = parts.join(" · ");
    }
    if (taskEl) taskEl.textContent = run.task || "Workflow run";

    if (!run.logs.length) {
      bodyEl.innerHTML = '<p class="run-logs-empty">No log entries for this run.</p>';
    } else {
      bodyEl.innerHTML = run.logs.map((log) => {
        const type = log.type || "progress";
        const resultBtn = log.resultId
          ? `<button type="button" class="run-log-view-result" data-result-id="${escapeHtml(log.resultId)}">View result</button>`
          : "";
        return `
          <div class="run-log-entry ${type}">
            <div class="run-log-head">
              <span class="run-log-agent">${escapeHtml(log.agent || "System")}</span>
              <span class="run-log-type">${escapeHtml(type)}</span>
              <time>${formatRunTime(log.time)}</time>
            </div>
            <div class="run-log-message">${escapeHtml(log.message || "")}</div>
            ${resultBtn}
          </div>`;
      }).join("");

      bodyEl.querySelectorAll("[data-result-id]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          openResultModal(btn.dataset.resultId);
        });
      });
    }

    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeRunLogsModal() {
    const modal = $("#run-logs-modal");
    if (modal) {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
    }
  }

  function getCurrentRunId() {
    return currentRunId;
  }

  function switchSidebarTab(tab) {
    activeSidebarTab = tab === "queue" ? "queue" : "runs";
    document.querySelectorAll(".panel-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.panelTab === activeSidebarTab);
    });
    $("#panel-runs")?.classList.toggle("hidden", activeSidebarTab !== "runs");
    $("#panel-queue")?.classList.toggle("hidden", activeSidebarTab !== "queue");
  }

  async function loadResultsQueue() {
    if (!window.AgentApp?.api || activeUserId === "guest" || !activeUserId) {
      resultsQueue = [];
      renderResultsQueue();
      return;
    }
    try {
      const data = await window.AgentApp.api("/api/queue?limit=50");
      resultsQueue = data.items || [];
    } catch {
      /* keep existing list on transient errors */
    }
    renderResultsQueue();
  }

  function refreshResultsQueue() {
    return loadResultsQueue();
  }

  function renderResultsQueue() {
    const list = $("#queue-list");
    const countEl = $("#queue-count");
    if (!list) return;

    if (countEl) {
      countEl.textContent = `${resultsQueue.length} result${resultsQueue.length === 1 ? "" : "s"}`;
    }

    if (!resultsQueue.length) {
      list.innerHTML = '<p class="runs-empty">No agent results yet. Run an agent to populate the queue.</p>';
      return;
    }

    list.innerHTML = resultsQueue.map((item) => `
      <article class="queue-card ${item.status}${activeResultId === item.id ? " active" : ""}" data-result-id="${item.id}">
        <div class="queue-card-head">
          <span class="run-status-badge ${item.status}">${item.status}</span>
          <time>${formatRunTime(item.created_at)}</time>
        </div>
        <div class="queue-agent">${escapeHtml(item.agent_name || item.agent_id)}</div>
        <div class="queue-message">${escapeHtml(item.message || "")}</div>
      </article>
    `).join("");

    list.querySelectorAll(".queue-card").forEach((card) => {
      card.onclick = () => openResultModal(card.dataset.resultId);
    });
  }

  async function openResultModal(resultId) {
    if (!resultId || !window.AgentApp?.api) return;

    activeResultId = resultId;
    renderResultsQueue();

    let item = resultsQueue.find((r) => r.id === resultId);
    if (!item) {
      try {
        item = await window.AgentApp.api(`/api/queue/${encodeURIComponent(resultId)}`);
      } catch {
        return;
      }
    }

    const modal = $("#result-modal");
    const titleEl = $("#result-modal-title");
    const statusEl = $("#result-modal-status");
    const metaEl = $("#result-modal-meta");
    const messageEl = $("#result-modal-message");
    const jsonEl = $("#result-modal-json");
    if (!modal || !jsonEl) return;

    if (titleEl) titleEl.textContent = item.agent_name || item.agent_id || "Agent Result";
    if (statusEl) {
      statusEl.textContent = item.status || "completed";
      statusEl.className = `run-status-badge ${item.status || "completed"}`;
    }
    if (metaEl) {
      const parts = [`Agent: ${item.agent_id}`, `ID: ${item.id}`];
      if (item.run_id) parts.push(`Run: ${item.run_id}`);
      if (item.created_at) parts.push(formatRunTime(item.created_at));
      metaEl.textContent = parts.join(" · ");
    }
    if (messageEl) messageEl.textContent = item.message || "";
    jsonEl.textContent = JSON.stringify(item.result || {}, null, 2);

    switchSidebarTab("queue");
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeResultModal() {
    const modal = $("#result-modal");
    if (modal) {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
    }
    activeResultId = null;
    renderResultsQueue();
  }

  async function clearResultsQueue() {
    if (!window.AgentApp?.api) return;
    const ok = window.confirm("Clear all agent results from the queue?");
    if (!ok) return;
    try {
      await window.AgentApp.api("/api/queue", "DELETE");
      resultsQueue = [];
      renderResultsQueue();
    } catch { /* ignore */ }
  }

  function fitCanvasToWorkflow() {
    const vp = $("#canvas-viewport");
    if (!vp || !workflow.nodes.length) {
      resetCanvasView();
      return;
    }

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    workflow.nodes.forEach((n) => {
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x + NODE_W);
      maxY = Math.max(maxY, n.y + NODE_H);
    });

    const pad = 56;
    const bw = maxX - minX + pad * 2;
    const bh = maxY - minY + pad * 2;
    const vw = vp.clientWidth || 800;
    const vh = vp.clientHeight || 600;

    scale = Math.min(1.25, Math.max(0.4, Math.min(vw / bw, vh / bh)));
    panX = (vw - bw * scale) / 2 - minX * scale + pad * scale;
    panY = (vh - bh * scale) / 2 - minY * scale + pad * scale;
    applyTransform();
    updateEmptyCanvasHint();
  }

  function openAgentModal(nodeId) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    selectedNodeId = nodeId;
    renderNodes();
    renderProperties(nodeId);
    const modal = $("#agent-modal");
    if (modal) {
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
    }
    if (window.AgentApp) window.AgentApp.bindPropertyActions(node.agentId);
  }

  function closeAgentModal() {
    const modal = $("#agent-modal");
    if (modal) {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
    }
  }

  function renderLibrary(filter = "") {
    const list = $("#agent-library");
    if (!list) return;
    const q = filter.toLowerCase();
    list.innerHTML = "";

    Object.values(AGENT_DEFS).forEach((agent) => {
      if (q && !agent.name.toLowerCase().includes(q) && !agent.type.toLowerCase().includes(q)) return;
      const status = agentStatuses[agent.id] || "idle";
      const gmailAlert = needsGmailConnection(agent.id) && gmailConnected === false;
      const li = document.createElement("li");
      li.className = "library-item";
      li.draggable = true;
      li.dataset.agentId = agent.id;
      li.innerHTML = `
        <span class="library-icon">${agent.icon}</span>
        <div class="library-info">
          <div class="library-name">${agent.name}</div>
          <div class="library-type">${agent.type}</div>
        </div>
        <span class="status-dot ${gmailAlert ? "gmail-alert" : status}" title="${gmailAlert ? "Connect Gmail" : status}"></span>
        <button class="library-menu" type="button" aria-label="Menu">⋯</button>
      `;
      li.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("agentId", agent.id);
        li.classList.add("dragging");
      });
      li.addEventListener("dragend", () => li.classList.remove("dragging"));
      list.appendChild(li);
    });
  }

  function scheduleDraftSave() {
    if (!activeUserId || activeUserId === "guest") return;
    if (draftSaveTimer) clearTimeout(draftSaveTimer);
    draftSaveTimer = setTimeout(() => {
      persistDraftWorkflow();
      draftSaveTimer = null;
    }, 500);
  }

  function renderCanvas() {
    applyTransform();
    renderConnections();
    renderNodes();
    scheduleDraftSave();
  }

  function applyTransform() {
    const stage = $("#canvas-stage");
    if (!stage) return;
    stage.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
    const zoomLabel = $("#zoom-label");
    if (zoomLabel) zoomLabel.textContent = `${Math.round(scale * 100)}%`;
  }

  function portPos(node, port) {
    const cx = node.x + NODE_W / 2;
    if (port === "out") return { x: cx, y: node.y + NODE_H };
    return { x: cx, y: node.y };
  }

  function renderConnections() {
    const svg = $("#connections-svg");
    if (!svg) return;
    svg.setAttribute("viewBox", "0 0 3000 2000");
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");

    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    defs.innerHTML = `
      <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 Z" fill="#1A73E8" />
      </marker>
      <marker id="arrowhead-active" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 Z" fill="#1E8E3E" />
      </marker>`;
    svg.innerHTML = "";
    svg.appendChild(defs);

    workflow.edges.forEach((edge) => {
      const from = workflow.nodes.find((n) => n.id === edge.from);
      const to = workflow.nodes.find((n) => n.id === edge.to);
      if (!from || !to) return;

      const f = portPos(from, "out");
      const t = portPos(to, "in");
      const midY = (f.y + t.y) / 2;

      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const d = `M ${f.x} ${f.y} C ${f.x} ${midY}, ${t.x} ${midY}, ${t.x} ${t.y}`;
      path.setAttribute("d", d);
      path.classList.add("flow-line");
      const active = from.status === "running" || to.status === "running";
      const done = from.status === "done" && to.status === "done";
      if (active) path.classList.add("active");
      if (done) path.classList.add("done");
      path.setAttribute("marker-end", active || done ? "url(#arrowhead-active)" : "url(#arrowhead)");
      svg.appendChild(path);
    });

    if (connectingFrom && connectCursor) {
      const from = workflow.nodes.find((n) => n.id === connectingFrom);
      if (from) {
        const f = portPos(from, "out");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        const midY = (f.y + connectCursor.y) / 2;
        path.setAttribute("d", `M ${f.x} ${f.y} C ${f.x} ${midY}, ${connectCursor.x} ${midY}, ${connectCursor.x} ${connectCursor.y}`);
        path.classList.add("flow-line", "connecting");
        svg.appendChild(path);
      }
    }
  }

  function renderNodes() {
    const layer = $("#nodes-layer");
    layer.innerHTML = "";

    workflow.nodes.forEach((node) => {
      const agent = getAgent(node.agentId);
      if (!agent) return;
      const cfg = getEffectiveAgentConfig(node.agentId, node.config || {});
      const status = node.status || "idle";
      const title = node.label || cfg.name || agent.name;
      const elapsed = node.execTime != null ? `${node.execTime}s` : "—";
      const modelLabel = cfg.model || agent.model;
      const gmailAlert = needsGmailConnection(node.agentId) && gmailConnected === false;

      const el = document.createElement("div");
      el.className = `wf-node${selectedNodeId === node.id ? " selected" : ""}${status !== "idle" ? ` ${status}` : ""}${gmailAlert ? " gmail-disconnected" : ""}`;
      el.dataset.nodeId = node.id;
      el.style.left = `${node.x}px`;
      el.style.top = `${node.y}px`;
      el.innerHTML = `
        <div class="wf-port in"></div>
        <div class="wf-node-header">
          <span class="wf-node-icon">${agent.icon}</span>
          <span class="wf-node-title">${title}</span>
          ${gmailAlert ? '<span class="gmail-connect-dot" title="Connect Gmail"></span>' : ""}
          <button class="wf-node-expand" type="button" aria-label="Expand">⤢</button>
        </div>
        <div class="wf-node-body">
          <span class="wf-node-status ${status}">${status}</span>
          <div class="wf-node-meta">
            <span>${elapsed}</span>
            <span>${modelLabel}</span>
          </div>
        </div>
        <div class="wf-port out"></div>
      `;

      el.addEventListener("mousedown", (e) => onNodeMouseDown(e, node));
      el.addEventListener("click", (e) => {
        if (nodeDidDrag) {
          nodeDidDrag = false;
          return;
        }
        if (e.target.closest(".wf-port") || e.target.closest(".wf-node-expand")) return;
        e.stopPropagation();
        openAgentModal(node.id);
      });
      el.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        openAgentModal(node.id);
      });
      el.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        showContextMenu(e.clientX, e.clientY, node.id);
      });
      el.querySelector(".wf-node-expand").addEventListener("click", (e) => {
        e.stopPropagation();
        openAgentModal(node.id);
      });
      el.querySelector(".gmail-connect-dot")?.addEventListener("click", (e) => {
        e.stopPropagation();
        openAgentModal(node.id);
      });

      const outPort = el.querySelector(".wf-port.out");
      const inPort = el.querySelector(".wf-port.in");
      outPort.addEventListener("mousedown", (e) => {
        e.stopPropagation();
        connectingFrom = node.id;
        const rect = $("#canvas-stage").getBoundingClientRect();
        connectCursor = {
          x: (e.clientX - rect.left) / scale,
          y: (e.clientY - rect.top) / scale,
        };
        renderConnections();
      });
      inPort.addEventListener("mouseup", (e) => {
        e.stopPropagation();
        if (!connectingFrom || connectingFrom === node.id) return;
        const exists = workflow.edges.some((ed) => ed.from === connectingFrom && ed.to === node.id);
        if (!exists) workflow.edges.push({ from: connectingFrom, to: node.id });
        connectingFrom = null;
        connectCursor = null;
        renderConnections();
      });

      layer.appendChild(el);
    });
  }

  function selectNode(nodeId) {
    selectedNodeId = nodeId;
    renderNodes();
  }

  function renderProperties(nodeId) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    const agent = getAgent(node.agentId);
    const cfg = getEffectiveAgentConfig(node.agentId, node.config || {});
    const body = $("#modal-props-body");
    const agentIdEl = $("#modal-props-agent-id");
    if (!body || !agentIdEl) return;
    agentIdEl.textContent = agent.id;

    let extra = "";
    if (agent.id === "invoice-matcher") {
      extra = `
        <div class="prop-group prop-actions">
          <label>Data Files</label>
          <label class="btn btn-tonal file-btn" style="cursor:pointer;text-align:center">
            Upload invoices
            <input type="file" id="upload-invoices" accept=".csv,.xlsx,.xls" multiple hidden />
          </label>
          <label class="btn btn-tonal file-btn" style="cursor:pointer;text-align:center">
            Upload payments
            <input type="file" id="upload-payments" accept=".csv,.xlsx,.xls" multiple hidden />
          </label>
        </div>`;
    }
    if (agent.id === "gmail-organizer") {
      extra = `
        <div class="prop-group prop-actions">
          <label>Scan Date</label>
          <input type="date" id="gmail-scan-date" value="${escapeHtml(cfg.scan_date || "")}" />
          <p class="prop-hint">Emails received on this day. Leave blank to use today.</p>
          <label>Gmail Connection</label>
          <p class="prop-hint" id="gmail-hint">Connect Gmail — scans emails and applies category labels</p>
          <button class="btn btn-tonal" type="button" id="btn-connect-gmail">Connect Gmail</button>
          <button class="btn btn-text hidden" type="button" id="btn-disconnect-gmail">Disconnect</button>
        </div>`;
    }
    if (agent.id === "planner") {
      const taskVal = $("#workflow-task")?.value || "";
      extra = `
        <div class="prop-group prop-actions">
          <label>Planner Task</label>
          <textarea id="planner-task" rows="3" placeholder="Describe what the workflow should do…">${taskVal}</textarea>
          <p class="prop-hint">Used when you click Run Workflow</p>
        </div>`;
    }
    if (agent.id === "telecaller") {
      const numbers = (cfg.phone_numbers || []).join("\n");
      const message = cfg.message || "Hello";
      extra = `
        <div class="prop-group prop-actions">
          <label>Phone Numbers</label>
          <textarea id="telecaller-numbers" rows="4" placeholder="+14155551234 (one per line)">${escapeHtml(numbers)}</textarea>
          <p class="prop-hint">E.164 format recommended. Set TWILIO_* in .env for live calls.</p>
          <label>Greeting</label>
          <input type="text" id="telecaller-message" value="${escapeHtml(message)}" placeholder="Hello" />
        </div>`;
    }
    if (agent.id === "mailer") {
      const recipients = (cfg.to || []).join("\n");
      extra = `
        <div class="prop-group prop-actions">
          <label>Recipients</label>
          <textarea id="mailer-recipients" rows="3" placeholder="user@example.com (one per line)">${escapeHtml(recipients)}</textarea>
          <label>Subject</label>
          <input type="text" id="mailer-subject" value="${escapeHtml(cfg.subject || "Hello")}" />
          <label>Body</label>
          <textarea id="mailer-body" rows="4" placeholder="Email message…">${escapeHtml(cfg.body || "Hello")}</textarea>
          <p class="prop-hint">Set SMTP_* in .env for live email delivery.</p>
        </div>`;
    }
    if (agent.id === "gmail-calendar") {
      extra = `
        <div class="prop-group prop-actions">
          <label>Action</label>
          <select id="calendar-action">
            <option value="list_events"${(cfg.action || "list_events") === "list_events" ? " selected" : ""}>List events</option>
            <option value="create_event"${cfg.action === "create_event" ? " selected" : ""}>Create event</option>
          </select>
          <label>Date From</label>
          <input type="date" id="calendar-date-from" value="${escapeHtml(cfg.date_from || "")}" />
          <label>Date To</label>
          <input type="date" id="calendar-date-to" value="${escapeHtml(cfg.date_to || "")}" />
          <label>Max Results</label>
          <input type="number" id="calendar-max-results" min="1" max="100" value="${cfg.max_results || 25}" />
          <label>Event Title</label>
          <input type="text" id="calendar-event-title" value="${escapeHtml(cfg.event_title || "Meeting")}" />
          <label>Event Start (ISO datetime)</label>
          <input type="datetime-local" id="calendar-event-start" value="${escapeHtml(cfg.event_start || "")}" />
          <label>Duration (minutes)</label>
          <input type="number" id="calendar-event-duration" min="5" max="480" value="${cfg.event_duration_minutes || 30}" />
          <label>Attendees</label>
          <textarea id="calendar-attendees" rows="2" placeholder="email@example.com (one per line)">${escapeHtml((cfg.attendees || []).join("\n"))}</textarea>
          <p class="prop-hint" id="gmail-hint">Connect Google account — uses same OAuth as Gmail (includes Calendar).</p>
          <button class="btn btn-tonal" type="button" id="btn-connect-gmail">Connect Google</button>
          <button class="btn btn-text hidden" type="button" id="btn-disconnect-gmail">Disconnect</button>
        </div>`;
    }
    if (agent.id === "whatsapp") {
      const numbers = (cfg.phone_numbers || []).join("\n");
      extra = `
        <div class="prop-group prop-actions">
          <label>Phone Numbers</label>
          <textarea id="whatsapp-numbers" rows="4" placeholder="+14155551234 (one per line)">${escapeHtml(numbers)}</textarea>
          <label>Message</label>
          <textarea id="whatsapp-message" rows="4" placeholder="WhatsApp message…">${escapeHtml(cfg.message || "Hello")}</textarea>
          <p class="prop-hint">Set TWILIO_* and TWILIO_WHATSAPP_FROM in .env for live WhatsApp.</p>
        </div>`;
    }
    if (agent.id === "data-scraper") {
      const urls = (cfg.urls || []).join("\n");
      extra = `
        <div class="prop-group prop-actions">
          <label>URLs</label>
          <textarea id="scraper-urls" rows="4" placeholder="https://example.com (one per line)">${escapeHtml(urls)}</textarea>
          <label>CSS Selector (optional)</label>
          <input type="text" id="scraper-selector" value="${escapeHtml(cfg.css_selector || "")}" placeholder="article, .content, #main" />
          <label><input type="checkbox" id="scraper-extract-links"${cfg.extract_links !== false ? " checked" : ""} /> Extract links</label>
          <label>Max Links</label>
          <input type="number" id="scraper-max-links" min="0" max="100" value="${cfg.max_links || 20}" />
          <p class="prop-hint">Results saved to your scraped_data folder as JSON.</p>
        </div>`;
    }
    if (agent.id === "file-download") {
      const urls = (cfg.urls || []).join("\n");
      const names = (cfg.filenames || []).join("\n");
      extra = `
        <div class="prop-group prop-actions">
          <label>File URLs</label>
          <textarea id="download-urls" rows="4" placeholder="https://example.com/file.pdf (one per line)">${escapeHtml(urls)}</textarea>
          <label>Filenames (optional, one per line)</label>
          <textarea id="download-filenames" rows="3" placeholder="report.pdf">${escapeHtml(names)}</textarea>
          <p class="prop-hint">Files saved to your downloads folder.</p>
        </div>`;
    }
    if (node.id === "n-input") {
      const taskVal = $("#workflow-task")?.value || "";
      extra = `
        <div class="prop-group prop-actions">
          <label>Chat Input</label>
          <textarea id="planner-task" rows="3" placeholder="Describe your task for the planner…">${taskVal}</textarea>
        </div>`;
    }

    body.innerHTML = `
      <div class="prop-group">
        <label>Agent Name</label>
        <input type="text" id="prop-name" value="${escapeHtml(cfg.name || agent.name)}" />
      </div>
      <div class="prop-group">
        <label>Description</label>
        <textarea id="prop-desc">${escapeHtml(cfg.description || agent.description)}</textarea>
      </div>
      <div class="prop-group">
        <label>Prompt</label>
        <textarea id="prop-prompt">${escapeHtml(cfg.prompt || agent.prompt)}</textarea>
      </div>
      <div class="prop-group">
        <label>Temperature</label>
        <div class="prop-slider">
          <input type="range" id="prop-temp" min="0" max="1" step="0.1" value="${cfg.temperature ?? agent.temperature}" />
          <span id="prop-temp-val">${cfg.temperature ?? agent.temperature}</span>
        </div>
      </div>
      <div class="prop-group">
        <label>Model</label>
        <select id="prop-model">
          <option value="gpt-4o" ${(cfg.model || agent.model) === "gpt-4o" ? "selected" : ""}>GPT-4o</option>
          <option value="gpt-4o-mini" ${(cfg.model || agent.model) === "gpt-4o-mini" ? "selected" : ""}>GPT-4o Mini</option>
          <option value="gemini-2.0-flash" ${(cfg.model || agent.model) === "gemini-2.0-flash" ? "selected" : ""}>Gemini 2.0 Flash</option>
          <option value="whisper-1" ${(cfg.model || agent.model) === "whisper-1" ? "selected" : ""}>Whisper</option>
        </select>
      </div>
      <div class="prop-group">
        <label>Input Variables</label>
        <div class="prop-tags">${agent.inputs.map((i) => `<span class="prop-tag">${i}</span>`).join("")}</div>
      </div>
      <div class="prop-group">
        <label>Output Variables</label>
        <div class="prop-tags">${agent.outputs.map((o) => `<span class="prop-tag">${o}</span>`).join("")}</div>
      </div>
      <div class="prop-group">
        <label>Tools</label>
        <div class="prop-tags">${agent.tools.map((t) => `<span class="prop-tag">${t}</span>`).join("")}</div>
      </div>
      <div class="prop-group">
        <label>Memory</label>
        <select id="prop-memory">
          <option value="none" ${(cfg.memory || "none") === "none" ? "selected" : ""}>None</option>
          <option value="session" ${cfg.memory === "session" ? "selected" : ""}>Session</option>
          <option value="persistent" ${cfg.memory === "persistent" ? "selected" : ""}>Persistent</option>
        </select>
      </div>
      ${extra}
    `;

    const tempSlider = $("#prop-temp");
    if (tempSlider) {
      tempSlider.oninput = () => { $("#prop-temp-val").textContent = tempSlider.value; };
    }

    if (window.AgentApp) {
      window.AgentApp.bindPropertyActions(agent.id);
    }
  }

  function onNodeMouseDown(e, node) {
    if (e.button !== 0) return;
    e.stopPropagation();
    dragNode = node;
    nodeDidDrag = false;
    dragStartPos = { x: e.clientX, y: e.clientY };
    const rect = $("#canvas-stage").getBoundingClientRect();
    dragOffset.x = (e.clientX - rect.left) / scale - node.x;
    dragOffset.y = (e.clientY - rect.top) / scale - node.y;
    selectNode(node.id);
    document.querySelector(`[data-node-id="${node.id}"]`)?.classList.add("dragging");
  }

  function bindCanvasEvents() {
    const viewport = $("#canvas-viewport");
    if (!viewport) return;

    const startPan = (e) => {
      if (e.target.closest(".wf-node")) return;
      if (e.target.closest(".canvas-toolbar")) return;
      if (e.target.closest("button")) return;
      isPanning = true;
      panStart = { x: e.clientX - panX, y: e.clientY - panY };
      viewport.classList.add("panning");
      if (!e.target.closest(".wf-node")) {
        selectedNodeId = null;
        renderNodes();
        closeAgentModal();
      }
      e.preventDefault();
    };

    viewport.addEventListener("mousedown", (e) => {
      if (e.button === 0 || e.button === 1) startPan(e);
    });

    window.addEventListener("mousemove", (e) => {
      if (connectingFrom) {
        const rect = $("#canvas-stage").getBoundingClientRect();
        connectCursor = {
          x: (e.clientX - rect.left) / scale,
          y: (e.clientY - rect.top) / scale,
        };
        $$(".wf-port.in").forEach((p) => p.classList.remove("connect-target"));
        const target = document.elementFromPoint(e.clientX, e.clientY);
        target?.closest?.(".wf-port.in")?.classList.add("connect-target");
        renderConnections();
        return;
      }
      if (isPanning) {
        panX = e.clientX - panStart.x;
        panY = e.clientY - panStart.y;
        applyTransform();
        return;
      }
      if (dragNode) {
        if (dragStartPos) {
          const dx = Math.abs(e.clientX - dragStartPos.x);
          const dy = Math.abs(e.clientY - dragStartPos.y);
          if (dx > 4 || dy > 4) nodeDidDrag = true;
        }
        const rect = $("#canvas-stage").getBoundingClientRect();
        dragNode.x = Math.max(0, (e.clientX - rect.left) / scale - dragOffset.x);
        dragNode.y = Math.max(0, (e.clientY - rect.top) / scale - dragOffset.y);
        const el = document.querySelector(`[data-node-id="${dragNode.id}"]`);
        if (el) {
          el.style.left = `${dragNode.x}px`;
          el.style.top = `${dragNode.y}px`;
        }
        renderConnections();
      }
    });

    window.addEventListener("mouseup", (e) => {
      if (connectingFrom) {
        const target = document.elementFromPoint(e.clientX, e.clientY);
        const inPort = target?.closest?.(".wf-port.in");
        if (inPort) {
          const nodeEl = inPort.closest(".wf-node");
          const toId = nodeEl?.dataset?.nodeId;
          if (toId && connectingFrom !== toId) {
            const exists = workflow.edges.some((ed) => ed.from === connectingFrom && ed.to === toId);
            if (!exists) workflow.edges.push({ from: connectingFrom, to: toId });
          }
        }
        connectingFrom = null;
        connectCursor = null;
        $$(".wf-port.in").forEach((p) => p.classList.remove("connect-target"));
        renderConnections();
      }
      isPanning = false;
      viewport.classList.remove("panning");
      if (dragNode) {
        if (!nodeDidDrag && !e.target.closest(".wf-port") && !e.target.closest(".wf-node-expand")) {
          openAgentModal(dragNode.id);
        }
        document.querySelector(`[data-node-id="${dragNode.id}"]`)?.classList.remove("dragging");
        dragNode = null;
        dragStartPos = null;
      }
    });

    viewport.addEventListener("wheel", (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.08 : 0.08;
      scale = Math.min(2, Math.max(0.35, scale + delta));
      applyTransform();
    }, { passive: false });

    viewport.addEventListener("dragover", (e) => e.preventDefault());
    viewport.addEventListener("drop", (e) => {
      e.preventDefault();
      const agentId = e.dataTransfer.getData("agentId");
      if (!agentId || !getAgent(agentId)) return;
      const rect = $("#canvas-stage").getBoundingClientRect();
      const x = (e.clientX - rect.left) / scale - 110;
      const y = (e.clientY - rect.top) / scale - 45;
      workflow.nodes.push({
        id: `n-${Date.now()}`,
        agentId,
        x: Math.max(20, x),
        y: Math.max(20, y),
        status: "idle",
        config: structuredClone(savedAgentConfigs[agentId] || {}),
      });
      renderCanvas();
      updateEmptyCanvasHint();
    });

    $("#zoom-in")?.addEventListener("click", () => { scale = Math.min(2, scale + 0.15); applyTransform(); });
    $("#zoom-out")?.addEventListener("click", () => { scale = Math.max(0.35, scale - 0.15); applyTransform(); });
    $("#zoom-fit")?.addEventListener("click", () => fitCanvasToWorkflow());
  }

  function showContextMenu(x, y, nodeId) {
    contextNodeId = nodeId;
    const menu = $("#context-menu");
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.classList.remove("hidden");
  }

  function hideContextMenu() {
    $("#context-menu").classList.add("hidden");
    contextNodeId = null;
  }

  function bindUI() {
    $("#search-agents")?.addEventListener("input", (e) => renderLibrary(e.target.value));
    $("#search-workflow")?.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      $$(".wf-node").forEach((n) => {
        const title = n.querySelector(".wf-node-title")?.textContent.toLowerCase() || "";
        n.style.opacity = !q || title.includes(q) ? "1" : "0.25";
      });
    });

    $("#toggle-sidebar")?.addEventListener("click", () => {
      $("#sidebar-left")?.classList.toggle("collapsed");
    });

    $("#btn-theme")?.addEventListener("click", toggleTheme);

    $("#btn-profile")?.addEventListener("click", (e) => {
      e.stopPropagation();
      $("#profile-dropdown")?.classList.toggle("hidden");
    });

    document.addEventListener("click", () => {
      hideContextMenu();
      $("#profile-dropdown")?.classList.add("hidden");
    });

    $("#context-menu")?.addEventListener("click", (e) => {
      const action = e.target.dataset?.action;
      if (!action || !contextNodeId) return;
      const node = workflow.nodes.find((n) => n.id === contextNodeId);
      if (action === "edit") openAgentModal(contextNodeId);
      if (action === "run" && node && window.AgentApp) window.AgentApp.runAgent(node.agentId);
      if (action === "duplicate" && node) {
        workflow.nodes.push({
          ...structuredClone(node),
          id: `n-${Date.now()}`,
          x: node.x + 40,
          y: node.y + 40,
        });
        renderCanvas();
        updateEmptyCanvasHint();
      }
      if (action === "disconnect" && contextNodeId) {
        workflow.edges = workflow.edges.filter(
          (ed) => ed.from !== contextNodeId && ed.to !== contextNodeId
        );
        renderConnections();
      }
      if (action === "delete") {
        deleteNode(contextNodeId);
      }
      hideContextMenu();
    });

    $("#btn-save-workflow")?.addEventListener("click", saveCurrentWorkflow);
    $("#btn-new-workflow")?.addEventListener("click", newWorkflow);

    $("#btn-run-workflow")?.addEventListener("click", () => {
      if (window.AgentApp) window.AgentApp.runWorkflow();
    });

    $("#modal-close")?.addEventListener("click", closeAgentModal);
    $("#modal-backdrop")?.addEventListener("click", closeAgentModal);
    $("#run-logs-close")?.addEventListener("click", closeRunLogsModal);
    $("#run-logs-backdrop")?.addEventListener("click", closeRunLogsModal);
    $("#result-close")?.addEventListener("click", closeResultModal);
    $("#result-backdrop")?.addEventListener("click", closeResultModal);
    $("#btn-clear-queue")?.addEventListener("click", clearResultsQueue);
    document.querySelectorAll(".panel-tab").forEach((btn) => {
      btn.addEventListener("click", () => switchSidebarTab(btn.dataset.panelTab));
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeRunLogsModal();
        closeResultModal();
        closeAgentModal();
      }
    });

    const workflowTask = $("#workflow-task");
    if (workflowTask) {
      workflowTask.addEventListener("input", () => {
        const plannerField = document.getElementById("planner-task");
        if (plannerField) plannerField.value = workflowTask.value;
      });
    }

    $("#btn-test-agent")?.addEventListener("click", () => {
      const node = workflow.nodes.find((n) => n.id === selectedNodeId);
      if (!node || !window.AgentApp) return;
      saveSelectedNodeConfig();
      window.AgentApp.runAgent(node.agentId, { nodeId: node.id, config: getNodeConfig(node.id) });
    });

    $("#btn-save-agent")?.addEventListener("click", () => {
      const node = workflow.nodes.find((n) => n.id === selectedNodeId);
      if (!saveSelectedNodeConfig()) return;
      const agentName = node?.label || getAgent(node?.agentId)?.name || "Agent";
      logRunEntry({ agent: "System", type: "completed", message: `${agentName} configuration saved` });
      closeAgentModal();
    });
  }

  function updateMetrics() {
    /* metrics row removed — canvas uses full height */
  }

  function setMetricSuccess(_rate) {}

  function setMetricAvgTime(_ms) {}

  function highlightExecution(agentId, status, execTime) {
    setAgentStatus(agentId, status);
    workflow.nodes.forEach((n) => {
      if (n.agentId === agentId && execTime != null) n.execTime = execTime;
    });
    renderConnections();
    renderNodes();
  }

  function appendConsole(_panel, entry) {
    logRunEntry(entry);
  }

  function getRunnableNodes() {
    return workflow.nodes.filter((n) => getAgent(n.agentId)?.runnable);
  }

  function getAgentStatus(agentId) {
    return agentStatuses[agentId] || "idle";
  }

  function getDownstreamAgentIds(nodeId) {
    const ids = [];
    workflow.edges
      .filter((edge) => edge.from === nodeId)
      .forEach((edge) => {
        const node = workflow.nodes.find((n) => n.id === edge.to);
        if (node) ids.push(node.agentId);
      });
    return [...new Set(ids)];
  }

  function applyPlannerResult(plan) {
    if (!plan) return;

    const calls = plan.calls || [];
    const phones = plan.phone_numbers || calls.map((c) => c.phone_number).filter(Boolean);

    if (calls.length) {
      workflow.nodes
        .filter((node) => node.agentId === "telecaller")
        .forEach((node) => {
          node.config = {
            ...(node.config || {}),
            calls,
            phone_numbers: phones,
            message: calls[0]?.message || node.config?.message || "Hello, returning your support request call.",
          };
        });
    } else if (phones.length) {
      workflow.nodes
        .filter((node) => node.agentId === "telecaller")
        .forEach((node) => {
          node.config = {
            ...(node.config || {}),
            phone_numbers: phones,
            message: node.config?.message || "Hello, returning your support request call.",
          };
        });
    }

    const emailActions = plan.email_actions || [];
    if (emailActions.length) {
      const first = emailActions[0];
      workflow.nodes
        .filter((node) => node.agentId === "mailer")
        .forEach((node) => {
          node.config = {
            ...(node.config || {}),
            to: first.to || [],
            subject: first.subject || node.config?.subject || "Hello",
            body: first.body || node.config?.body || "Hello",
            email_actions: emailActions,
          };
        });
    }

    const whatsappMessages = plan.whatsapp_messages || [];
    if (whatsappMessages.length) {
      workflow.nodes
        .filter((node) => node.agentId === "whatsapp")
        .forEach((node) => {
          node.config = {
            ...(node.config || {}),
            messages: whatsappMessages,
            phone_numbers: whatsappMessages.map((m) => m.phone_number).filter(Boolean),
            message: whatsappMessages[0]?.message || node.config?.message || "Hello",
          };
        });
    } else if (phones.length) {
      workflow.nodes
        .filter((node) => node.agentId === "whatsapp")
        .forEach((node) => {
          node.config = {
            ...(node.config || {}),
            phone_numbers: phones,
            message: node.config?.message || "Hello",
          };
        });
    }

    const scrapeUrls = plan.scrape_urls || [];
    if (scrapeUrls.length) {
      workflow.nodes
        .filter((node) => node.agentId === "data-scraper")
        .forEach((node) => {
          node.config = { ...(node.config || {}), urls: scrapeUrls };
        });
    }

    const downloadUrls = plan.download_urls || [];
    if (downloadUrls.length) {
      workflow.nodes
        .filter((node) => node.agentId === "file-download")
        .forEach((node) => {
          node.config = { ...(node.config || {}), urls: downloadUrls };
        });
    }
  }

  function getExecutionOrder() {
    const ids = workflow.nodes.map((n) => n.id);
    const inDegree = Object.fromEntries(ids.map((id) => [id, 0]));
    workflow.edges.forEach((e) => {
      if (inDegree[e.to] != null) inDegree[e.to]++;
    });

    const start = workflow.nodes.find((n) => n.id === "n-input")?.id;
    const queue = start && inDegree[start] === 0 ? [start] : ids.filter((id) => inDegree[id] === 0);
    const order = [];

    while (queue.length) {
      const id = queue.shift();
      order.push(id);
      workflow.edges
        .filter((e) => e.from === id)
        .forEach((e) => {
          inDegree[e.to]--;
          if (inDegree[e.to] === 0) queue.push(e.to);
        });
    }

    ids.forEach((id) => {
      if (!order.includes(id)) order.push(id);
    });

    return order
      .map((id) => workflow.nodes.find((n) => n.id === id))
      .filter(Boolean);
  }

  function getWorkflowTask() {
    const plannerField = document.getElementById("planner-task");
    const workflowField = document.getElementById("workflow-task");
    return (plannerField?.value || workflowField?.value || "").trim();
  }

  function setWorkflowTask(text) {
    const workflowField = document.getElementById("workflow-task");
    const plannerField = document.getElementById("planner-task");
    if (workflowField) workflowField.value = text;
    if (plannerField) plannerField.value = text;
  }

  function highlightNodeById(nodeId, status, execTime) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    highlightExecution(node.agentId, status, execTime);
    node.status = status;
    if (execTime != null) node.execTime = execTime;
    renderConnections();
    renderNodes();
  }

  const WORKFLOW_TEMPLATES = [
    {
      id: "sales-lead-qualification",
      name: "Sales Lead Qualification",
      stars: 5,
      task: "Qualify inbound sales leads from email, score buying intent, and route hot leads to sales outreach",
      diagram: `New Email
      │
      ▼
Planner
      │
      ├── Detect buying intent
      ├── Company size
      ├── Budget
      ├── Urgency
      └── Lead score

If score > 90

↓

Sales Agent

↓

Meeting Scheduler

↓

CRM Update`,
      nodes: [
        { id: "n-gmail", agentId: "gmail-organizer", x: 40, y: 120, status: "idle", config: {} },
        { id: "n-plan", agentId: "planner", x: 300, y: 120, status: "idle", config: {} },
        { id: "n-call", agentId: "telecaller", x: 560, y: 80, status: "idle", config: {} },
        { id: "n-mail", agentId: "mailer", x: 560, y: 200, status: "idle", config: {} },
      ],
      edges: [
        { from: "n-gmail", to: "n-plan" },
        { from: "n-plan", to: "n-call" },
        { from: "n-plan", to: "n-mail" },
      ],
    },
    {
      id: "support-ticket-automation",
      name: "Support Ticket Automation",
      stars: 5,
      task: "Automate support tickets: classify issues, draft replies, update CRM, and escalate VIP customers",
      diagram: `Customer Email
        │
        ▼
Planner
        │
        ├── Classify Issue
        ├── Check FAQ
        ├── Draft Reply
        ├── Update CRM
        └── Create Ticket

Automations:
• Categorize tickets
• Assign priority
• Detect VIP customers
• Suggest replies
• Escalate to human
• Create Jira/Linear tickets
• Notify Slack`,
      nodes: [
        { id: "n-gmail", agentId: "gmail-organizer", x: 40, y: 140, status: "idle", config: {} },
        { id: "n-plan", agentId: "planner", x: 300, y: 140, status: "idle", config: {} },
        { id: "n-mail", agentId: "mailer", x: 560, y: 140, status: "idle", config: {} },
      ],
      edges: [
        { from: "n-gmail", to: "n-plan" },
        { from: "n-plan", to: "n-mail" },
      ],
    },
    {
      id: "email-organization",
      name: "Email Organization",
      stars: 4,
      task: "Organize today's emails, categorize them, and apply Gmail labels",
      diagram: `Gmail Inbox
      │
      ▼
Gmail Organizer
      │
      ├── Read emails
      ├── Categorize
      └── Apply labels`,
      nodes: [
        { id: "n-gmail", agentId: "gmail-organizer", x: 180, y: 140, status: "idle", config: {} },
      ],
      edges: [],
    },
    {
      id: "support-callbacks",
      name: "Support Callbacks",
      stars: 4,
      task: "Scan support emails, identify customers who need a callback, and call them",
      diagram: `Support Email
      │
      ▼
Gmail Organizer
      │
      ▼
Planner
      │
      ▼
Telecaller`,
      nodes: [
        { id: "n-gmail", agentId: "gmail-organizer", x: 40, y: 140, status: "idle", config: {} },
        { id: "n-plan", agentId: "planner", x: 300, y: 140, status: "idle", config: {} },
        { id: "n-call", agentId: "telecaller", x: 560, y: 140, status: "idle", config: {} },
      ],
      edges: [
        { from: "n-gmail", to: "n-plan" },
        { from: "n-plan", to: "n-call" },
      ],
    },
  ];

  let activeTemplateId = null;

  function renderStars(count) {
    return "★".repeat(count) + "☆".repeat(Math.max(0, 5 - count));
  }

  function renderWorkflowTemplates() {
    const list = $("#templates-list");
    if (!list) return;
    list.innerHTML = WORKFLOW_TEMPLATES.map((tpl) => `
      <button type="button" class="template-card${activeTemplateId === tpl.id ? " active" : ""}" data-template-id="${tpl.id}" title="Click to load on canvas">
        <div class="template-title">${escapeHtml(tpl.name)} <span class="template-stars">${renderStars(tpl.stars)}</span></div>
      </button>
    `).join("");

    list.querySelectorAll(".template-card").forEach((card) => {
      card.addEventListener("click", () => loadWorkflowTemplate(card.dataset.templateId));
    });
  }

  function loadWorkflowTemplate(templateId) {
    const template = WORKFLOW_TEMPLATES.find((t) => t.id === templateId);
    if (!template) return;
    activeTemplateId = templateId;
    workflow = {
      nodes: structuredClone(template.nodes),
      edges: structuredClone(template.edges),
    };
    currentWorkflowId = null;
    agentStatuses = {};
    selectedNodeId = null;
    closeAgentModal();
    setWorkflowTask(template.task);
    const nameEl = $("#workflow-name");
    if (nameEl) nameEl.value = template.name;
    updateBreadcrumb(template.name);
    renderWorkflowTemplates();
    renderCanvas();
    fitCanvasToWorkflow();
    updateEmptyCanvasHint();
    persistDraftWorkflow();
    logRunEntry({
      agent: "System",
      type: "completed",
      message: `Loaded template "${template.name}"`,
    });
  }

  const STARTER_WORKFLOWS = {
    email: {
      name: "Email Organization",
      task: "Organize today's emails, categorize them, and apply Gmail labels",
      nodes: [
        { id: "n-gmail", agentId: "gmail-organizer", x: 180, y: 140, status: "idle", config: {} },
      ],
      edges: [],
    },
    invoices: {
      name: "Invoice Reconciliation",
      task: "Match invoices to payments and surface exceptions",
      nodes: [
        { id: "n-inv", agentId: "invoice-matcher", x: 180, y: 140, status: "idle", config: {} },
      ],
      edges: [],
    },
    support: {
      name: "Support Callbacks",
      task: "Scan support emails, identify customers who need a callback, and call them",
      nodes: [
        { id: "n-gmail", agentId: "gmail-organizer", x: 40, y: 140, status: "idle", config: {} },
        { id: "n-plan", agentId: "planner", x: 300, y: 140, status: "idle", config: {} },
        { id: "n-call", agentId: "telecaller", x: 560, y: 140, status: "idle", config: {} },
      ],
      edges: [
        { from: "n-gmail", to: "n-plan" },
        { from: "n-plan", to: "n-call" },
      ],
    },
    all: {
      name: "Full Automation",
      task: "Organize emails, plan outreach for distressed customers, call them, and send follow-up emails",
      nodes: [
        { id: "n-gmail", agentId: "gmail-organizer", x: 30, y: 160, status: "idle", config: {} },
        { id: "n-plan", agentId: "planner", x: 280, y: 160, status: "idle", config: {} },
        { id: "n-call", agentId: "telecaller", x: 530, y: 100, status: "idle", config: {} },
        { id: "n-mail", agentId: "mailer", x: 530, y: 240, status: "idle", config: {} },
      ],
      edges: [
        { from: "n-gmail", to: "n-plan" },
        { from: "n-plan", to: "n-call" },
        { from: "n-plan", to: "n-mail" },
      ],
    },
  };

  function loadStarterWorkflow(useCase) {
    const map = {
      email: "email-organization",
      invoices: null,
      support: "support-callbacks",
      all: "support-ticket-automation",
    };
    const templateId = map[useCase];
    if (templateId) {
      loadWorkflowTemplate(templateId);
      return;
    }
    const template = STARTER_WORKFLOWS[useCase] || STARTER_WORKFLOWS.all;
    workflow = {
      nodes: structuredClone(template.nodes),
      edges: structuredClone(template.edges),
    };
    currentWorkflowId = null;
    agentStatuses = {};
    selectedNodeId = null;
    closeAgentModal();
    setWorkflowTask(template.task);
    const nameEl = $("#workflow-name");
    if (nameEl) nameEl.value = template.name;
    updateBreadcrumb(template.name);
    renderCanvas();
    fitCanvasToWorkflow();
    updateEmptyCanvasHint();
    persistDraftWorkflow();
    logRunEntry({
      agent: "System",
      type: "completed",
      message: `Loaded "${template.name}" starter workflow for you`,
    });
  }

  function showPersonalizedWelcome(userName, useCase) {
    const banner = $("#welcome-banner");
    if (!banner) return;
    const first = (userName || "there").trim().split(/\s+/)[0];
    const messages = {
      email: "Organize your inbox — Gmail labels applied automatically.",
      invoices: "Upload CSVs and reconcile invoices in minutes.",
      support: "Detect callback requests and route them to your telecaller.",
      all: "Orchestrate email, planning, calls, and mail from one canvas.",
    };
    const titleEl = $("#welcome-banner-title");
    const textEl = $("#welcome-banner-text");
    if (titleEl) titleEl.textContent = `Welcome, ${first}!`;
    if (textEl) textEl.textContent = messages[useCase] || messages.all;
    banner.classList.remove("hidden");
  }

  function dismissWelcomeBanner() {
    $("#welcome-banner")?.classList.add("hidden");
  }

  return {
    init,
    initStudioForUser,
    resetForLogout,
    renderLibrary,
    newWorkflow,
    saveCurrentWorkflow,
    getAgent,
    getNodeConfig,
    saveSelectedNodeConfig,
    setAgentStatus,
    setGmailConnected,
    highlightExecution,
    appendConsole,
    selectNodeByAgentId(agentId, openModal = false) {
      const node = workflow.nodes.find((n) => n.agentId === agentId);
      if (!node) return;
      if (openModal) openAgentModal(node.id);
      else selectNode(node.id);
    },
    startWorkflowRun,
    finishWorkflowRun,
    logRunEntry,
    renderWorkflowRuns,
    openAgentModal,
    closeAgentModal,
    openRunLogsModal,
    closeRunLogsModal,
    openResultModal,
    closeResultModal,
    refreshResultsQueue,
    getCurrentRunId,
    switchSidebarTab,
    fitCanvasToWorkflow,
    setMetricSuccess,
    setMetricAvgTime,
    getRunnableNodes,
    getExecutionOrder,
    getDownstreamAgentIds,
    applyPlannerResult,
    getWorkflowTask,
    setWorkflowTask,
    highlightNodeById,
    getAgentStatus,
    loadStarterWorkflow,
    loadWorkflowTemplate,
    renderWorkflowTemplates,
    showPersonalizedWelcome,
    dismissWelcomeBanner,
    AGENT_DEFS,
  };
})();

window.AgentStudio = AgentStudio;

function bootAgentStudio() {
  try {
    AgentStudio.init();
  } catch (err) {
    console.error("Agent Studio failed to initialize", err);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootAgentStudio);
} else {
  bootAgentStudio();
}
