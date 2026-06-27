/**
 * Agent Studio — canvas, workflow, and UI orchestration
 */
const AgentStudio = (() => {
  function renderMaterialIcon(name, variant = "default") {
    const icon = String(name || "smart_toy").replace(/[^a-z0-9_]/gi, "");
    const cls = variant === "library" ? " agent-mat-icon--library" : variant === "node" ? " agent-mat-icon--node" : "";
    return `<span class="material-symbols-outlined agent-mat-icon${cls}" aria-hidden="true">${icon}</span>`;
  }

  const DEFAULT_MODEL_STORAGE_KEY = "agent_studio_default_model";
  let selectedModelId = "gpt-4o-mini";
  let activeLibraryTab = "agents";

  function loadSelectedModel() {
    try {
      selectedModelId = localStorage.getItem(DEFAULT_MODEL_STORAGE_KEY) || "gpt-4o-mini";
    } catch {
      selectedModelId = "gpt-4o-mini";
    }
    if (window.AgentModels?.coerceModel) {
      selectedModelId = window.AgentModels.coerceModel(selectedModelId);
    }
  }

  function setSelectedModel(modelId) {
    selectedModelId = window.AgentModels?.coerceModel
      ? window.AgentModels.coerceModel(modelId)
      : modelId;
    try {
      localStorage.setItem(DEFAULT_MODEL_STORAGE_KEY, selectedModelId);
    } catch {
      /* ignore */
    }
    renderModelLibrary($("#search-agents")?.value || "");
  }

  function getSelectedModelId() {
    return selectedModelId;
  }

  function switchLibraryTab(tab) {
    activeLibraryTab = tab === "models" ? "models" : "agents";
    document.querySelectorAll(".library-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.libraryTab === activeLibraryTab);
    });
    $("#library-panel-agents")?.classList.toggle("hidden", activeLibraryTab !== "agents");
    $("#library-panel-models")?.classList.toggle("hidden", activeLibraryTab !== "models");
    const hint = document.querySelector(
      `#library-panel-${activeLibraryTab} .sidebar-hint`
    );
    if (hint) hint.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function shortModelLabel(name) {
    const cleaned = String(name || "")
      .replace(/^GPT-/i, "")
      .replace(/ \(legacy\)/i, "")
      .trim();
    const word = cleaned.split(/\s+/)[0] || cleaned;
    return word.toUpperCase().slice(0, 9);
  }

  function renderModelLibrary(filter = "") {
    const list = $("#model-library");
    if (!list || !window.AgentModels) return;
    const q = filter.toLowerCase().trim();
    list.innerHTML = "";

    window.AgentModels.groupByFamily(window.AgentModels.MODELS).forEach(({ family, models }) => {
      const visible = models.filter((m) => {
        if (!q) return true;
        const hay = `${m.name} ${m.family} ${m.bestFor} ${m.strengths} ${m.whenToUse}`.toLowerCase();
        return hay.includes(q);
      });
      if (!visible.length) return;

      const section = document.createElement("li");
      section.className = "library-section-block";
      section.innerHTML = `<div class="library-section-header">${family}</div>`;

      const grid = document.createElement("div");
      grid.className = "library-grid-wrap";
      const gridInner = document.createElement("ul");
      gridInner.className = "agent-library-grid";

      const familySlug = window.AgentModels.familySlug(family);

      visible.forEach((model) => {
        const selected = model.id === selectedModelId;
        let modelCardDragged = false;
        const li = document.createElement("li");
        li.className = `library-item library-card model-library-card${selected ? " selected" : ""}`;
        li.draggable = true;
        li.dataset.modelId = model.id;
        li.setAttribute("aria-label", model.name);
        li.title = model.name;
        li.innerHTML = `
          <div class="library-card-icon-wrap library-card-icon-wrap--${familySlug}">
            ${renderMaterialIcon(window.AgentModels.getModelIcon(model), "library")}
            <span class="status-dot ${selected ? "running" : "idle"}" title="${selected ? "Default model" : "Click to select"}"></span>
          </div>
          <span class="library-card-name">${shortModelLabel(model.name)}</span>
          <span class="library-card-tooltip">${model.name} — ${model.bestFor}</span>`;
        li.addEventListener("dragstart", (e) => {
          modelCardDragged = true;
          e.dataTransfer.setData("modelId", model.id);
          e.dataTransfer.effectAllowed = "copy";
          li.classList.add("dragging");
        });
        li.addEventListener("dragend", () => {
          li.classList.remove("dragging");
          setTimeout(() => { modelCardDragged = false; }, 0);
        });
        li.addEventListener("click", () => {
          if (modelCardDragged) return;
          setSelectedModel(model.id);
        });
        gridInner.appendChild(li);
      });

      grid.appendChild(gridInner);
      section.appendChild(grid);
      list.appendChild(section);
    });
  }

  const AGENT_DEFS = {
    "invoice-matcher": {
      id: "invoice-matcher", name: "Invoice Matcher", icon: "receipt_long",
      type: "Reconciliation", runnable: true,
      description: "Pull invoice & payment data, reconcile matches, surface exceptions.",
      prompt: "Match invoices to payments by vendor, reference, and amount. Flag mismatches.",
      model: "gpt-4o", temperature: 0.1,
      inputs: ["invoices", "payments"], outputs: ["matched", "exceptions"],
      tools: ["pandas", "excel-reader"],
    },
    "gmail-organizer": {
      id: "gmail-organizer", name: "Gmail Organizer", icon: "mail",
      type: "Email", runnable: true,
      description: "Connect Gmail, scan emails, apply category labels, and organize attachments.",
      prompt: "Read each email, categorize it, apply the matching Gmail label, and file attachments.",
      model: "gpt-4o-mini", temperature: 0.2,
      inputs: ["gmail_inbox"], outputs: ["categories", "attachments"],
      tools: ["gmail-api", "file-organizer"],
    },
    "pdf-reader": {
      id: "pdf-reader", name: "PDF Reader", icon: "picture_as_pdf",
      type: "Document", runnable: false,
      description: "Extract and summarize text from PDF documents.",
      prompt: "Read PDF content and extract structured data.",
      model: "gpt-4o", temperature: 0.3,
      inputs: ["pdf_file"], outputs: ["text", "summary"],
      tools: ["pdf-parser"],
    },
    "web-search": {
      id: "web-search", name: "Web Search", icon: "travel_explore",
      type: "Research", runnable: false,
      description: "Search the web and return relevant results.",
      prompt: "Search for information and return cited results.",
      model: "gpt-4o-mini", temperature: 0.4,
      inputs: ["query"], outputs: ["results"],
      tools: ["web-search"],
    },
    "planner": {
      id: "planner", name: "Planner", icon: "account_tree",
      type: "Orchestration", runnable: true,
      description: "Break down tasks and route to appropriate agents.",
      prompt: "Analyze user input and create an execution plan.",
      model: "gpt-4o", temperature: 0.5,
      inputs: ["user_input"], outputs: ["plan", "steps"],
      tools: ["reasoning"],
    },
    "speech-agent": {
      id: "speech-agent", name: "Speech Agent", icon: "mic",
      type: "Audio", runnable: false,
      description: "Transcribe and process speech input.",
      prompt: "Convert speech to text and extract intent.",
      model: "whisper-1", temperature: 0,
      inputs: ["audio"], outputs: ["transcript"],
      tools: ["speech-to-text"],
    },
    "chat-agent": {
      id: "chat-agent", name: "Chat Agent", icon: "forum",
      type: "Conversation", runnable: false,
      description: "Handle conversational interactions with memory.",
      prompt: "Respond naturally while maintaining context.",
      model: "gpt-4o", temperature: 0.7,
      inputs: ["message", "history"], outputs: ["response"],
      tools: ["memory"],
    },
    "analytics": {
      id: "analytics", name: "Analytics", icon: "bar_chart",
      type: "Insights", runnable: false,
      description: "Generate insights and visualizations from agent outputs.",
      prompt: "Analyze data and produce summary metrics.",
      model: "gpt-4o-mini", temperature: 0.2,
      inputs: ["data"], outputs: ["metrics", "charts"],
      tools: ["chart-builder"],
    },
    "telecaller": {
      id: "telecaller", name: "Telecaller", icon: "headset_mic",
      type: "Outreach", runnable: true,
      description: "Place outbound calls to phone numbers and speak a greeting.",
      prompt: "Call each number and say hello in a clear, friendly voice.",
      model: "gpt-4o-mini", temperature: 0.2,
      inputs: ["phone_numbers"], outputs: ["call_results"],
      tools: ["twilio-voice"],
    },
    "mailer": {
      id: "mailer", name: "Mailer", icon: "send",
      type: "Email", runnable: true,
      description: "Send emails to one or more recipients.",
      prompt: "Compose and send the configured email to all recipients.",
      model: "gpt-4o-mini", temperature: 0.3,
      inputs: ["recipients", "subject", "body"], outputs: ["delivery_status"],
      tools: ["smtp"],
    },
    "gmail-calendar": {
      id: "gmail-calendar", name: "Gmail Calendar", icon: "calendar_today",
      type: "Calendar", runnable: true,
      description: "List or create Google Calendar events using your connected account.",
      prompt: "Read calendar events for the date range, or create a new meeting.",
      model: "gpt-4o-mini", temperature: 0.2,
      inputs: ["date_range", "event_details"], outputs: ["events", "event_link"],
      tools: ["google-calendar-api"],
    },
    "whatsapp": {
      id: "whatsapp", name: "WhatsApp", icon: "chat_bubble",
      type: "Messaging", runnable: true,
      description: "Send WhatsApp messages to phone numbers via Twilio.",
      prompt: "Send the configured WhatsApp message to each recipient.",
      model: "gpt-4o-mini", temperature: 0.3,
      inputs: ["phone_numbers", "message"], outputs: ["delivery_status"],
      tools: ["twilio-whatsapp"],
    },
    "data-scraper": {
      id: "data-scraper", name: "Data Scraper", icon: "language",
      type: "Research", runnable: true,
      description: "Fetch web pages and extract text, links, and structured data.",
      prompt: "Scrape each URL, extract content, and save JSON results.",
      model: "gpt-4o-mini", temperature: 0.1,
      inputs: ["urls", "css_selector"], outputs: ["scraped_data"],
      tools: ["httpx", "beautifulsoup"],
    },
    "file-download": {
      id: "file-download", name: "File Download", icon: "download",
      type: "Files", category: "action", runnable: true,
      description: "Download files from URLs into your workspace storage.",
      prompt: "Download each file URL and save it to the downloads folder.",
      model: "gpt-4o-mini", temperature: 0,
      inputs: ["urls"], outputs: ["saved_files"],
      tools: ["httpx"],
    },
    "org-knowledge-base": {
      id: "org-knowledge-base", name: "Organization Knowledge Base", icon: "school",
      type: "Knowledge", category: "action", runnable: true,
      description: "Build a searchable knowledge base from PDFs, videos, CSV, databases, and SharePoint — hierarchical RAG at scale.",
      prompt: "Stream-read sources without downloading files; chunk, embed, and index with turbovec for fast Q&A.",
      model: "gpt-4o-mini", temperature: 0.1,
      inputs: ["sources", "folder_path"], outputs: ["knowledge_index"],
      tools: ["turbovec", "embeddings"],
    },
    ...buildUnderstandingAgentDefs(),
    ...buildPerceptionAgentDefs(),
    ...buildContentAgentDefs(),
  };

  function buildContentAgentDefs() {
    const specs = [
      ["content-director", "Content Director", "supervisor_account", "Chief Content Officer — orchestrates research, strategy, production, and analytics agents."],
      ["content-trend-research", "Trend Research", "trending_up", "Scan YouTube, Reddit, X, LinkedIn, and trends for viral topics."],
      ["content-audience-psychology", "Audience Psychology", "psychology", "Extract pain points, desires, and objections from audience signals."],
      ["content-strategy", "Content Strategy", "calendar_month", "Weekly calendar, platform mix, and funnel strategy."],
      ["content-hook-generator", "Hook Generator", "campaign", "First-3-second hooks, headlines, and scroll-stoppers."],
      ["content-script-writer", "Script Writer", "edit_note", "Long-form, shorts, LinkedIn posts, and threads (PAS, AIDA)."],
      ["content-visual-planner", "Visual Planner", "movie", "Shot lists — talking head, B-roll, animations."],
      ["content-thumbnail", "Thumbnail Agent", "image", "Thumbnail concepts, overlays, and CTR predictions."],
      ["content-video-creator", "Video Creator", "videocam", "Generate intro videos with Google Gemini Veo — human-approved prompts."],
      ["content-video-editing", "Video Editing", "content_cut", "Cut plans, captions, zoom effects, B-roll suggestions."],
      ["content-caption-hashtag", "Caption & Hashtag", "tag", "Platform-specific captions and hashtags."],
      ["content-publishing", "Publishing", "publish", "Schedule and post to YouTube, LinkedIn, X, Instagram."],
      ["content-community", "Community", "forum", "Draft replies for comments, DMs, and FAQs."],
      ["content-analytics", "Analytics", "insights", "Track CTR, watch time, engagement, followers, leads."],
      ["content-learning", "Learning", "school", "Weekly learnings → creator-specific knowledge base."],
    ];
    return Object.fromEntries(
      specs.map(([id, name, icon, description]) => [
        id,
        {
          id,
          name,
          icon,
          type: "CreatorOS",
          category: "content",
          runnable: true,
          description,
          prompt: id === "content-director"
            ? "Orchestrate the content pipeline: delegate to specialists via tools, review outputs, finalize weekly plan."
            : `${name}: produce structured output for the CreatorOS content operating system.`,
          model: "auto",
          temperature: 0.4,
          inputs: ["creator_type", "platforms", "goal"],
          outputs: id === "content-director" ? ["weekly_plan", "assigned_agents"] : ["result"],
          tools: id === "content-director" ? ["tool-calling", "delegation"] : ["content"],
        },
      ])
    );
  }

  function buildPerceptionAgentDefs() {
    const specs = [
      ["read-text", "Read Text", "article", "Read and normalize plain text input."],
      ["read-pdf", "Read PDF", "picture_as_pdf", "Read all PDFs in a folder and extract text from each."],
      ["read-word", "Read Word Document", "description", "Extract text from Word (.docx) files."],
      ["read-excel", "Read Excel", "table_chart", "Read spreadsheet data from Excel."],
      ["read-csv", "Read CSV", "table_rows", "Parse CSV into rows and columns."],
      ["read-image", "Read Image", "image", "Inspect image files and metadata."],
      ["ocr", "OCR", "document_scanner", "Optical character recognition on scans."],
      ["read-barcode", "Read Barcode", "barcode_scanner", "Decode barcode values."],
      ["read-qr-code", "Read QR Code", "qr_code_scanner", "Decode QR code payloads."],
      ["read-audio", "Read Audio", "audio_file", "Inspect audio file metadata."],
      ["speech-to-text", "Speech-to-Text", "record_voice_over", "Transcribe audio to text."],
      ["video-frame-extractor", "Video Frame Extractor", "video_library", "Extract frames from video."],
      ["face-detector", "Face Detector", "face", "Detect faces in visual input."],
      ["object-detector", "Object Detector", "center_focus_strong", "Detect objects in images."],
      ["handwriting-reader", "Handwriting Reader", "draw", "Read handwritten text."],
      ["table-detector", "Table Detector", "table_view", "Detect tabular structures."],
      ["form-reader", "Form Reader", "ballot", "Extract labeled form fields."],
      ["screenshot-reader", "Screenshot Reader", "screenshot_monitor", "Read screenshot content."],
      ["html-reader", "HTML Reader", "code", "Parse HTML and extract text."],
      ["email-reader", "Email Reader", "mail", "Parse email headers and body."],
      ["calendar-reader", "Calendar Reader", "calendar_month", "Parse calendar events."],
      ["database-reader", "Database Reader", "database", "Parse database row output."],
      ["api-reader", "API Reader", "api", "Fetch and parse JSON from an API URL."],
      ["log-reader", "Log Reader", "receipt_long", "Parse log lines into entries."],
      ["clipboard-reader", "Clipboard Reader", "content_paste", "Normalize pasted clipboard content."],
    ];
    return Object.fromEntries(
      specs.map(([id, name, icon, description]) => [
        id,
        {
          id,
          name,
          icon,
          type: "Perception",
          category: "perception",
          runnable: true,
          description,
          prompt: `${name}: extract structured content from the configured input source.`,
          model: "gpt-4o-mini",
          temperature: 0.1,
          inputs: id === "read-pdf" ? ["folder_path"] : ["source"],
          outputs: ["content"],
          tools: ["input"],
        },
      ])
    );
  }

  function buildUnderstandingAgentDefs() {
    const specs = [
      ["intent-detection", "Intent Detection", "ads_click", "Detect the primary user intent(s) in text."],
      ["topic-detection", "Topic Detection", "label", "Identify main topics discussed in text."],
      ["language-detection", "Language Detection", "translate", "Detect the language of the input text."],
      ["entity-extraction", "Entity Extraction", "category", "Extract named entities from text."],
      ["keyword-extraction", "Keyword Extraction", "key", "Extract important keywords and phrases."],
      ["relationship-extraction", "Relationship Extraction", "device_hub", "Extract relationships between entities."],
      ["event-detection", "Event Detection", "event", "Detect events mentioned in text."],
      ["date-extraction", "Date Extraction", "calendar_month", "Extract dates and time expressions."],
      ["location-extraction", "Location Extraction", "location_on", "Extract locations and addresses."],
      ["person-extraction", "Person Extraction", "person", "Extract person names and roles."],
      ["organization-extraction", "Organization Extraction", "corporate_fare", "Extract companies and institutions."],
      ["product-extraction", "Product Extraction", "inventory_2", "Extract products and service names."],
      ["emotion-detection", "Emotion Detection", "mood", "Detect emotions expressed in text."],
      ["sentiment-detection", "Sentiment Detection", "thumb_up", "Classify overall sentiment."],
      ["urgency-detection", "Urgency Detection", "priority_high", "Assess urgency of the message."],
      ["risk-detection", "Risk Detection", "warning", "Identify risks and compliance red flags."],
      ["spam-detection", "Spam Detection", "block", "Detect spam or unwanted content."],
      ["duplicate-detection", "Duplicate Detection", "content_copy", "Compare text to a reference for duplication."],
      ["similarity-detection", "Similarity Detection", "compare", "Score similarity between two texts."],
      ["root-cause-finder", "Root Cause Finder", "troubleshoot", "Infer likely root causes from problems."],
    ];
    return Object.fromEntries(
      specs.map(([id, name, icon, description]) => [
        id,
        {
          id,
          name,
          icon,
          type: "Understanding",
          category: "understanding",
          runnable: true,
          needsReference: id === "duplicate-detection" || id === "similarity-detection",
          description,
          prompt: `Perform ${name.toLowerCase()} on the input text and return structured findings.`,
          model: "gpt-4o-mini",
          temperature: 0.1,
          inputs: ["text"],
          outputs: ["analysis"],
          tools: ["nlp"],
        },
      ])
    );
  }

  function isUnderstandingAgent(agentId) {
    const agent = AGENT_DEFS[agentId];
    return agent?.category === "understanding";
  }

  function isPerceptionAgent(agentId) {
    const agent = AGENT_DEFS[agentId];
    return agent?.category === "perception";
  }

  function isMicroAgent(agentId) {
    return isUnderstandingAgent(agentId) || isPerceptionAgent(agentId);
  }

  function isContentAgent(agentId) {
    const agent = AGENT_DEFS[agentId];
    return agent?.category === "content";
  }

  const EMPTY_WORKFLOW = { nodes: [], edges: [] };

  const NODE_W = 176;
  const NODE_H = 102;
  const MODEL_NODE_W = 148;
  const MODEL_NODE_H = 78;

  function isModelNode(node) {
    return node?.kind === "model" || Boolean(node?.modelId && !node?.agentId);
  }

  function nodeSize(node) {
    if (isModelNode(node)) return { w: MODEL_NODE_W, h: MODEL_NODE_H };
    return { w: NODE_W, h: NODE_H };
  }

  function getModel(node) {
    return window.AgentModels?.getModel(node?.modelId) || null;
  }

  function getLinkedModelId(nodeId) {
    for (const edge of workflow.edges) {
      if (edge.to !== nodeId) continue;
      const fromNode = workflow.nodes.find((n) => n.id === edge.from);
      if (fromNode && isModelNode(fromNode)) return fromNode.modelId;
    }
    return null;
  }

  function canConnect(fromId, toId) {
    const from = workflow.nodes.find((n) => n.id === fromId);
    const to = workflow.nodes.find((n) => n.id === toId);
    if (!from || !to || fromId === toId) return false;
    if (isModelNode(to)) return false;
    if (isModelNode(from)) return Boolean(to.agentId);
    return Boolean(from.agentId && to.agentId);
  }

  function tryConnect(fromId, toId) {
    if (!canConnect(fromId, toId)) return;
    const exists = workflow.edges.some((ed) => ed.from === fromId && ed.to === toId);
    if (!exists) {
      workflow.edges.push({ from: fromId, to: toId });
      renderNodes();
      scheduleDraftSave();
    }
  }

  let workflow = structuredClone(EMPTY_WORKFLOW);
  let savedWorkflows = [];
  let currentWorkflowId = null;
  let userStoragePrefix = "guest";
  let activeUserId = null;
  let agentStatuses = {};
  let gmailConnected = null;
  let youtubeConnected = null;
  let selectedNodeId = null;

  const GMAIL_AGENT_IDS = new Set(["gmail-organizer", "gmail-calendar"]);

  function needsGmailConnection(agentId) {
    return GMAIL_AGENT_IDS.has(agentId);
  }

  function needsYouTubeConnection(agentId) {
    return isContentAgent(agentId);
  }

  function setGmailConnected(connected) {
    gmailConnected = !!connected;
    renderNodes();
    renderLibrary($("#search-agents")?.value || "");
  }

  function setYouTubeConnected(connected) {
    youtubeConnected = !!connected;
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
  const $id = (id) => document.getElementById(id);
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
      model: nodeConfig.model ?? saved.model ?? (def.model === "whisper-1" ? "whisper-1" : "auto"),
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
    loadSelectedModel();
    renderModelLibrary();
    renderLibrary();
    renderWorkflowTemplates();
    renderSavedWorkflows();
    updateEmptyCanvasHint();
    bindCanvasEvents();
    bindUI();
    bindAgentEditorWindow();
    try {
      const lc = localStorage.getItem("agent_studio_use_langchain");
      const cb = document.getElementById("use-langchain");
      if (cb && lc !== null) cb.checked = lc === "1";
    } catch { /* ignore */ }
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
    loadInstalledTemplates();
    resetCanvasState();

    if (isNewUser) {
      clearDraftWorkflow(nextId);
    } else if (nextId !== "guest") {
      const draft = loadDraftWorkflow(nextId);
      if (draft) applyDraft(draft);
    }

    loadSelectedModel();
    renderModelLibrary();
    renderLibrary();
    renderWorkflowTemplates();
    renderCanvas();
    resetCanvasView();
    renderWorkflowRuns();
    updateWorkflowControlButtons();
    renderSavedWorkflows();
    updateEmptyCanvasHint();
    loadResultsQueue();
    syncTemplatesFromServer();
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
    youtubeConnected = null;
    resetCanvasState();
    closeAgentModal();
    closeAgentEditor();
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

  function collectNodeConfig(nodeId, options = {}) {
    const node = nodeId ? workflow.nodes.find((n) => n.id === nodeId) : null;
    const agentId = options.agentId || node?.agentId;
    if (!agentId) return {};
    const nodeConfig = node?.config || savedAgentConfigs[agentId] || {};
    const base = collectBaseConfigFromModal();
    if (agentId === "telecaller") {
      return {
        ...base,
        phone_numbers: parseListField(document.getElementById("telecaller-numbers")?.value),
        message: document.getElementById("telecaller-message")?.value?.trim() || "Hello",
        calls: nodeConfig.calls || [],
      };
    }
    if (agentId === "mailer") {
      return {
        ...base,
        to: parseListField(document.getElementById("mailer-recipients")?.value),
        subject: document.getElementById("mailer-subject")?.value?.trim() || "Hello",
        body: document.getElementById("mailer-body")?.value?.trim() || "Hello",
      };
    }
    if (agentId === "gmail-organizer") {
      const scanDate = document.getElementById("gmail-scan-date")?.value?.trim() || "";
      return {
        ...base,
        scan_date: scanDate,
        max_messages: 200,
      };
    }
    if (agentId === "gmail-calendar") {
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
    if (agentId === "whatsapp") {
      return {
        ...base,
        phone_numbers: parseListField(document.getElementById("whatsapp-numbers")?.value),
        message: document.getElementById("whatsapp-message")?.value?.trim() || "Hello",
        messages: node.config?.messages || [],
      };
    }
    if (agentId === "data-scraper") {
      return {
        ...base,
        urls: parseListField(document.getElementById("scraper-urls")?.value),
        css_selector: document.getElementById("scraper-selector")?.value?.trim() || "",
        extract_links: document.getElementById("scraper-extract-links")?.checked !== false,
        max_links: parseInt(document.getElementById("scraper-max-links")?.value || "20", 10),
      };
    }
    if (agentId === "file-download") {
      return {
        ...base,
        urls: parseListField(document.getElementById("download-urls")?.value),
        filenames: parseListField(document.getElementById("download-filenames")?.value),
      };
    }
    if (isUnderstandingAgent(agentId)) {
      return {
        ...base,
        text: document.getElementById("understanding-text")?.value?.trim() || "",
        reference_text: document.getElementById("understanding-reference")?.value?.trim() || "",
      };
    }
    if (isPerceptionAgent(agentId)) {
      if (agentId === "read-pdf") {
        return {
          ...base,
          folder_path: document.getElementById("perception-folder")?.value?.trim() || "",
          source: document.getElementById("perception-folder")?.value?.trim() || "",
        };
      }
      return {
        ...base,
        source: document.getElementById("perception-source")?.value?.trim() || "",
      };
    }
    if (agentId === "org-knowledge-base") {
      const sources = [];
      const folder = document.getElementById("kb-folder")?.value?.trim();
      const includeVideos = document.getElementById("kb-include-videos")?.checked;
      if (folder) sources.push({ type: "folder_pdf", folder, include_videos: !!includeVideos });
      const videoFolder = document.getElementById("kb-video-folder")?.value?.trim();
      if (videoFolder) sources.push({ type: "folder_video", folder: videoFolder });
      const csv = document.getElementById("kb-csv")?.value?.trim();
      if (csv) sources.push({ type: "csv", path: csv });
      const dbUrl = document.getElementById("kb-db-url")?.value?.trim();
      const dbQuery = document.getElementById("kb-db-query")?.value?.trim();
      if (dbUrl && dbQuery) sources.push({ type: "database", connection_url: dbUrl, query: dbQuery });
      const spSite = document.getElementById("kb-sp-site")?.value?.trim();
      const spFolder = document.getElementById("kb-sp-folder")?.value?.trim();
      if (spSite && spFolder) sources.push({ type: "sharepoint", site_url: spSite, folder_path: spFolder });
      return {
        ...base,
        action: document.getElementById("kb-action")?.value || "build",
        collection: document.getElementById("kb-collection")?.value?.trim() || "org-knowledge",
        folder_path: folder || "",
        sources,
        question: document.getElementById("kb-question")?.value?.trim() || "",
      };
    }
    if (isContentAgent(agentId)) {
      return {
        ...base,
        creator_type: document.getElementById("content-creator-type")?.value?.trim() || "Content Creator",
        niche: document.getElementById("content-niche")?.value?.trim() || "",
        platforms: parseListField(document.getElementById("content-platforms")?.value),
        goal: document.getElementById("content-goal")?.value?.trim() || "Grow followers and leads",
        human_in_loop: document.getElementById("content-human-loop")?.checked !== false,
      };
    }
    return { ...nodeConfig, ...base };
  }

  function applyNodeConfig(nodeId, config) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (node) node.config = { ...(node.config || {}), ...config };
  }

  function resolveAgentModel(config, context = {}) {
    if (!window.AgentModelRouter) {
      const fallback = window.AgentModels?.coerceModel
        ? window.AgentModels.coerceModel(config.model === "auto" ? "gpt-4o-mini" : config.model)
        : (config.model === "auto" ? "gpt-4o-mini" : config.model);
      return { ...config, model: fallback };
    }
    if (config.model && config.model !== "auto" && config.model_mode !== "auto") {
      return config;
    }
    const pick = window.AgentModelRouter.resolveModel(config, context);
    return { ...config, model: pick.modelId, _modelPick: pick };
  }

  function setNodeResolvedModel(nodeId, pick) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (!node || !pick) return;
    node.resolvedModel = pick.modelId;
    node.modelPickReason = pick.reason;
    renderNodes();
  }

  function formatModelLabel(config, node) {
    if (node?.resolvedModel) {
      const name = window.AgentModels?.getModel(node.resolvedModel)?.name || node.resolvedModel;
      return `auto → ${name.split(" ")[0]}`;
    }
    if (config.model === "auto" || !config.model) return "auto";
    return config.model;
  }

  function getNodeConfig(nodeId) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (!node || isModelNode(node)) return {};
    let config = getEffectiveAgentConfig(node.agentId, node.config || {});
    const linkedModel = getLinkedModelId(nodeId);
    if (linkedModel) {
      config.model = window.AgentModels?.coerceModel
        ? window.AgentModels.coerceModel(linkedModel)
        : linkedModel;
    } else if (window.AgentModelRouter?.isAutoModel(config.model)) {
      const ctx = buildModelContext(node);
      config = resolveAgentModel(config, ctx);
    }
    if (selectedNodeId === nodeId) {
      config = { ...config, ...collectNodeConfig(nodeId) };
      if (!linkedModel && window.AgentModelRouter?.isAutoModel(config.model)) {
        config = resolveAgentModel(config, buildModelContext(node, config));
      }
    }
    return config;
  }

  function buildModelContext(node, configOverride = null) {
    const cfg = configOverride || getEffectiveAgentConfig(node.agentId, node.config || {});
    const text = cfg.text || cfg.source || cfg.body || cfg.question || "";
    const connected = getDownstreamAgentIds(node.id);
    getUpstreamNodeIds(node.id).forEach((id) => {
      const upstream = workflow.nodes.find((n) => n.id === id);
      if (upstream?.agentId) connected.push(upstream.agentId);
    });
    return {
      agent_id: node.agentId,
      text,
      task: $("#workflow-task")?.value || "",
      prompt: cfg.prompt || "",
      question: cfg.question || "",
      action: cfg.action || "",
      source_size: String(text).length,
      connected_agents: [...new Set(connected)],
    };
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

  function startWorkflowRun(task, options = {}) {
    const run = {
      id: options.reuseRunId || `run-${Date.now()}`,
      task: task || "Workflow run",
      startedAt: options.reuseRunId
        ? (workflowRuns.find((r) => r.id === options.reuseRunId)?.startedAt || new Date().toISOString())
        : new Date().toISOString(),
      endedAt: null,
      status: "running",
      logs: options.reuseRunId
        ? (workflowRuns.find((r) => r.id === options.reuseRunId)?.logs || [])
        : [],
      checkpoint: options.checkpoint || null,
    };
    if (!options.reuseRunId) {
      workflowRuns.unshift(run);
      if (workflowRuns.length > 50) workflowRuns.length = 50;
    } else {
      const idx = workflowRuns.findIndex((r) => r.id === options.reuseRunId);
      if (idx >= 0) workflowRuns[idx] = { ...workflowRuns[idx], ...run };
    }
    currentRunId = run.id;
    activeRunViewId = run.id;
    saveWorkflowRuns();
    renderWorkflowRuns();
    updateWorkflowControlButtons();
    return run.id;
  }

  function saveWorkflowCheckpoint(checkpoint) {
    if (!currentRunId) return;
    const run = workflowRuns.find((r) => r.id === currentRunId);
    if (!run) return;
    run.checkpoint = checkpoint;
    run.status = "stopped";
    run.endedAt = new Date().toISOString();
    saveWorkflowRuns();
    renderWorkflowRuns();
    currentRunId = null;
    updateWorkflowControlButtons();
  }

  function getResumableRun() {
    return workflowRuns.find((r) => r.status === "stopped" && r.checkpoint?.completedNodeIds?.length) || null;
  }

  function getRunCheckpoint(runId) {
    const run = workflowRuns.find((r) => r.id === runId);
    return run?.checkpoint || null;
  }

  function updateWorkflowControlButtons() {
    const running = !!currentRunId || workflowRuns.some((r) => r.status === "running");
    const resumable = getResumableRun();
    const runBtn = $id("btn-run-workflow");
    const stopBtn = $id("btn-stop-workflow");
    const resumeBtn = $id("btn-resume-workflow");
    if (runBtn) runBtn.classList.toggle("hidden", running);
    if (stopBtn) stopBtn.classList.toggle("hidden", !running);
    if (resumeBtn) resumeBtn.classList.toggle("hidden", running || !resumable);
  }

  function finishWorkflowRun(status = "completed") {
    if (!currentRunId) return;
    if (window.AgentApp?.isHitlBlocking?.()) return;
    const run = workflowRuns.find((r) => r.id === currentRunId);
    if (run) {
      run.status = status;
      run.endedAt = new Date().toISOString();
      if (status === "completed") run.checkpoint = null;
      saveWorkflowRuns();
      renderWorkflowRuns();
    }
    currentRunId = null;
    updateWorkflowControlButtons();
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
    if (entry.type === "error" && run.status === "running" && entry.agent !== "System") run.status = "failed";
    if (entry.type === "cancelled" && run.status === "running") run.status = "stopped";
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
      const resumeBtn = run.status === "stopped" && run.checkpoint
        ? `<button type="button" class="btn btn-tonal btn-sm run-resume-btn" data-resume-run="${run.id}">Resume</button>`
        : "";
      return `
        <article class="run-card ${run.status}${activeRunViewId === run.id ? " active" : ""}" data-run-id="${run.id}">
          <div class="run-card-head">
            <span class="run-status-badge ${run.status}">${run.status}</span>
            <time>${formatRunTime(run.startedAt)}</time>
          </div>
          <p class="run-task">${escapeHtml(run.task)}</p>
          <div class="run-steps">${stepsHtml}</div>
          ${resumeBtn}
        </article>`;
    }).join("");

    list.querySelectorAll(".run-card").forEach((card) => {
      card.onclick = (e) => {
        if (e.target.closest(".run-resume-btn")) return;
        openRunLogsModal(card.dataset.runId);
      };
    });
    list.querySelectorAll(".run-resume-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (window.AgentApp?.resumeWorkflow) {
          window.AgentApp.resumeWorkflow(btn.dataset.resumeRun);
        }
      });
    });
    updateWorkflowControlButtons();
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

    const items = resultsQueue.filter(Boolean);
    if (countEl) {
      countEl.textContent = `${items.length} result${items.length === 1 ? "" : "s"}`;
    }

    if (!items.length) {
      list.innerHTML = '<p class="runs-empty">No agent results yet. Run an agent to populate the queue.</p>';
      return;
    }

    list.innerHTML = items.map((item) => `
      <article class="queue-card ${item.status || "completed"}${activeResultId === item.id ? " active" : ""}" data-result-id="${item.id || ""}">
        <div class="queue-card-head">
          <span class="run-status-badge ${item.status || "completed"}">${item.status || "completed"}</span>
          <time>${formatRunTime(item.created_at)}</time>
        </div>
        <div class="queue-agent">${escapeHtml(item.agent_name || item.agent_id || "Agent")}</div>
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
    if (!item) return;

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
      const { w, h } = nodeSize(n);
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x + w);
      maxY = Math.max(maxY, n.y + h);
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

  function openAgentEditor({ nodeId = null, agentId = null } = {}) {
    if (nodeId) {
      const node = workflow.nodes.find((n) => n.id === nodeId);
      if (!node || isModelNode(node)) return;
      editorNodeId = nodeId;
      editorAgentId = node.agentId;
      selectedNodeId = nodeId;
      renderNodes();
    } else if (agentId) {
      editorNodeId = null;
      editorAgentId = agentId;
    } else {
      return;
    }

    const agent = getAgent(editorAgentId);
    if (!agent) return;

    renderProperties(editorNodeId, {
      agentId: editorAgentId,
      bodyId: "agent-editor-body",
      compact: isContentAgent(editorAgentId) || isUnderstandingAgent(editorAgentId) || isPerceptionAgent(editorAgentId),
    });

    const win = $id("agent-editor-window");
    const titleEl = $id("agent-editor-title");
    const subEl = $id("agent-editor-sub");
    const iconEl = $id("agent-editor-icon");
    if (titleEl) titleEl.textContent = agent.name;
    if (subEl) {
      subEl.textContent = editorNodeId
        ? (isContentAgent(editorAgentId) ? "Enter your goal → Run Agent" : "Canvas agent — edits apply to this node")
        : "Library defaults — double-click from sidebar";
    }
    if (iconEl) iconEl.textContent = agent.icon || "smart_toy";
    const runBtn = $id("btn-editor-run-agent");
    if (runBtn) runBtn.textContent = agent.runnable ? "Run Agent" : "Simulate";
    if (win) {
      win.classList.remove("hidden", "minimized");
      win.setAttribute("aria-hidden", "false");
    }
    setTimeout(() => {
      const editorBody = $id("agent-editor-body");
      const goalEl = $id("content-goal") || $id("planner-task") || $id("understanding-text")
        || editorBody?.querySelector("textarea, input[type=text]");
      goalEl?.focus();
    }, 50);
    if (window.AgentApp) window.AgentApp.bindPropertyActions(editorAgentId);
  }

  function openAgentEditorFromLibrary(agentId) {
    openAgentEditor({ agentId });
  }

  function openAgentModal(nodeId) {
    openAgentEditor({ nodeId });
  }

  function closeAgentEditor() {
    const win = $id("agent-editor-window");
    if (win) {
      win.classList.add("hidden");
      win.setAttribute("aria-hidden", "true");
    }
    editorNodeId = null;
    editorAgentId = null;
  }

  function closeAgentModal() {
    closeAgentEditor();
  }

  function saveEditorConfig() {
    const agentId = editorAgentId;
    if (!agentId) return false;

    if (editorNodeId) {
      selectedNodeId = editorNodeId;
      return saveSelectedNodeConfig();
    }

    const config = collectNodeConfig(null, { agentId });
    savedAgentConfigs[agentId] = { ...(savedAgentConfigs[agentId] || {}), ...config };
    persistSavedAgentConfigs();
    logRunEntry({
      agent: "System",
      type: "completed",
      message: `${getAgent(agentId)?.name || agentId} defaults saved`,
    });
    return true;
  }

  function bindAgentEditorWindow() {
    const header = $("#agent-editor-header");
    const win = $("#agent-editor-window");
    if (header && win) {
      header.addEventListener("mousedown", (e) => {
        if (e.target.closest("button")) return;
        const rect = win.getBoundingClientRect();
        editorDragOffset = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        const onMove = (ev) => {
          win.style.left = `${Math.max(8, ev.clientX - editorDragOffset.x)}px`;
          win.style.top = `${Math.max(8, ev.clientY - editorDragOffset.y)}px`;
          win.style.right = "auto";
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
    }

    $("#agent-editor-close")?.addEventListener("click", closeAgentEditor);
    $("#agent-editor-minimize")?.addEventListener("click", () => {
      win?.classList.toggle("minimized");
    });
    $("#btn-editor-save-agent")?.addEventListener("click", () => {
      saveEditorConfig();
    });
    $id("btn-editor-run-agent")?.addEventListener("click", async () => {
      if (!editorAgentId || !window.AgentApp) return;
      const goalEl = $id("content-goal");
      if (isContentAgent(editorAgentId) && goalEl && !goalEl.value.trim()) {
        goalEl.focus();
        logRunEntry({ agent: "System", type: "error", message: "Enter a goal before running the agent" });
        return;
      }
      if (editorAgentId === "content-director" && youtubeConnected !== true) {
        logRunEntry({ agent: "System", type: "error", message: "Connect your YouTube channel first, then enter your goal" });
        $id("btn-connect-youtube")?.scrollIntoView({ block: "nearest" });
        return;
      }
      saveEditorConfig();
      const config = editorNodeId
        ? getNodeConfig(editorNodeId)
        : getEffectiveAgentConfig(editorAgentId, savedAgentConfigs[editorAgentId] || {});
      if (isContentAgent(editorAgentId) && config.goal) {
        setWorkflowTask(config.goal);
        const taskEl = $id("workflow-task");
        if (taskEl) taskEl.value = config.goal;
      }
      await window.AgentApp.runAgent(editorAgentId, {
        nodeId: editorNodeId || undefined,
        config,
      });
    });
  }

  function shortAgentLabel(name) {
    const word = name.split(/\s+/)[0] || name;
    return word.toUpperCase().slice(0, 9);
  }

  function renderAgentLibrary(filter = "") {
    const list = $("#agent-library");
    if (!list) return;
    const q = filter.toLowerCase();
    list.innerHTML = "";

    const groups = [
      { key: "action", label: "Agents" },
      { key: "content", label: "CreatorOS" },
      { key: "perception", label: "Perception" },
      { key: "understanding", label: "Understanding" },
    ];

    groups.forEach((group) => {
      const agents = Object.values(AGENT_DEFS).filter((agent) => {
        const cat = agent.category || "action";
        if (cat !== group.key) return false;
        if (q && !agent.name.toLowerCase().includes(q) && !agent.type.toLowerCase().includes(q)) return false;
        return true;
      });
      if (!agents.length) return;

      const section = document.createElement("li");
      section.className = "library-section-block";
      section.innerHTML = `<div class="library-section-header">${group.label}</div>`;

      const grid = document.createElement("div");
      grid.className = "library-grid-wrap";
      const gridInner = document.createElement("ul");
      gridInner.className = "agent-library-grid";

      agents.forEach((agent) => {
        const status = agentStatuses[agent.id] || "idle";
        const gmailAlert = needsGmailConnection(agent.id) && gmailConnected !== true;
        const youtubeAlert = needsYouTubeConnection(agent.id) && youtubeConnected !== true;
        const li = document.createElement("li");
        li.className = "library-item library-card";
        li.draggable = true;
        li.dataset.agentId = agent.id;
        li.dataset.name = agent.name;
        li.setAttribute("aria-label", agent.name);
        li.title = agent.name;
        li.innerHTML = `
          <div class="library-card-icon-wrap">
            ${renderMaterialIcon(agent.icon, "library")}
            <span class="status-dot ${gmailAlert || youtubeAlert ? "gmail-alert" : status}" title="${gmailAlert ? "Connect Gmail" : youtubeAlert ? "Connect YouTube" : status}"></span>
          </div>
          <span class="library-card-name">${shortAgentLabel(agent.name)}</span>
          <span class="library-card-tooltip">${agent.name}</span>
        `;
        li.addEventListener("dragstart", (e) => {
          e.dataTransfer.setData("agentId", agent.id);
          li.classList.add("dragging");
        });
        li.addEventListener("dragend", () => li.classList.remove("dragging"));
        li.addEventListener("dblclick", () => openAgentEditorFromLibrary(agent.id));
        const alertDot = li.querySelector(".status-dot.gmail-alert");
        if (alertDot) {
          alertDot.style.cursor = "pointer";
          alertDot.addEventListener("click", (e) => {
            e.stopPropagation();
            e.preventDefault();
            if (youtubeAlert && window.AgentApp?.connectYouTube) {
              window.AgentApp.connectYouTube();
            } else if (gmailAlert && window.AgentApp?.connectGmail) {
              window.AgentApp.connectGmail();
            } else {
              openAgentEditorFromLibrary(agent.id);
            }
          });
        }
        gridInner.appendChild(li);
      });

      grid.appendChild(gridInner);
      section.appendChild(grid);
      list.appendChild(section);
    });
  }

  function renderLibrary(filter = "") {
    renderAgentLibrary(filter);
    renderModelLibrary(filter);
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
    const { w, h } = nodeSize(node);
    const cx = node.x + w / 2;
    if (port === "out") return { x: cx, y: node.y + h };
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
      if (isModelNode(from)) path.classList.add("model-feed");
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
      if (isModelNode(node)) {
        renderModelNode(layer, node);
        return;
      }
      renderAgentNode(layer, node);
    });
  }

  function bindNodeDrag(el, node) {
    el.addEventListener("mousedown", (e) => onNodeMouseDown(e, node));
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      showContextMenu(e.clientX, e.clientY, node.id);
    });
  }

  function bindOutPort(el, node) {
    el.querySelector(".wf-port.out")?.addEventListener("mousedown", (e) => {
      e.stopPropagation();
      connectingFrom = node.id;
      const rect = $("#canvas-stage").getBoundingClientRect();
      connectCursor = {
        x: (e.clientX - rect.left) / scale,
        y: (e.clientY - rect.top) / scale,
      };
      renderConnections();
    });
  }

  function bindInPort(el, node) {
    el.querySelector(".wf-port.in")?.addEventListener("mouseup", (e) => {
      e.stopPropagation();
      if (!connectingFrom || connectingFrom === node.id) return;
      tryConnect(connectingFrom, node.id);
      connectingFrom = null;
      connectCursor = null;
      renderConnections();
    });
  }

  function renderModelNode(layer, node) {
    const model = getModel(node);
    if (!model) return;
    const familySlug = window.AgentModels.familySlug(model.family);
    const selected = selectedNodeId === node.id;

    const el = document.createElement("div");
    el.className = `wf-node wf-node--model${selected ? " selected" : ""}`;
    el.dataset.nodeId = node.id;
    el.style.left = `${node.x}px`;
    el.style.top = `${node.y}px`;
    el.innerHTML = `
      <div class="wf-node-header">
        <span class="wf-node-icon wf-node-icon--model library-card-icon-wrap--${familySlug}">
          ${renderMaterialIcon(window.AgentModels.getModelIcon(model), "node")}
        </span>
        <span class="wf-node-title">${model.name}</span>
      </div>
      <div class="wf-node-body">
        <span class="wf-node-model-family">${model.family}</span>
        <div class="wf-node-meta"><span>LLM</span><span>${model.variant !== "default" ? model.variant : "Model"}</span></div>
      </div>
      <div class="wf-port out"></div>
    `;

    bindNodeDrag(el, node);
    bindOutPort(el, node);
    el.addEventListener("click", (e) => {
      if (nodeDidDrag) {
        nodeDidDrag = false;
        return;
      }
      if (e.target.closest(".wf-port")) return;
      e.stopPropagation();
      setSelectedModel(node.modelId);
      selectNode(node.id);
    });

    layer.appendChild(el);
  }

  function renderAgentNode(layer, node) {
      const agent = getAgent(node.agentId);
      if (!agent) return;
      const cfg = getEffectiveAgentConfig(node.agentId, node.config || {});
      const status = node.status || "idle";
      const title = node.label || cfg.name || agent.name;
      const elapsed = node.execTime != null ? `${node.execTime}s` : "—";
      const linkedModel = getLinkedModelId(node.id);
      const modelLabel = linkedModel
        ? (window.AgentModels?.getModel(linkedModel)?.name || linkedModel)
        : formatModelLabel(cfg, node);
      const gmailAlert = needsGmailConnection(node.agentId) && gmailConnected !== true;
      const youtubeAlert = needsYouTubeConnection(node.agentId) && youtubeConnected !== true;

      const el = document.createElement("div");
      el.className = `wf-node${selectedNodeId === node.id ? " selected" : ""}${status !== "idle" ? ` ${status}` : ""}${gmailAlert || youtubeAlert ? " gmail-disconnected" : ""}`;
      el.dataset.nodeId = node.id;
      el.style.left = `${node.x}px`;
      el.style.top = `${node.y}px`;
      const stopBtn = status === "running"
        ? '<button class="wf-node-stop" type="button" title="Stop this agent" aria-label="Stop agent">■</button>'
        : "";
      el.innerHTML = `
        <div class="wf-port in"></div>
        <div class="wf-node-header">
          <span class="wf-node-icon">${renderMaterialIcon(agent.icon, "node")}</span>
          <span class="wf-node-title">${title}</span>
          ${gmailAlert ? '<span class="gmail-connect-dot" data-connect="gmail" title="Connect Gmail — click to connect"></span>' : ""}
          ${youtubeAlert ? '<span class="youtube-connect-dot" data-connect="youtube" title="Connect YouTube — click to connect"></span>' : ""}
          ${stopBtn}
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
        if (e.target.closest(".wf-port") || e.target.closest(".wf-node-expand") || e.target.closest(".wf-node-stop")
          || e.target.closest(".gmail-connect-dot") || e.target.closest(".youtube-connect-dot")) return;
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
      el.querySelector(".wf-node-stop")?.addEventListener("mousedown", (e) => {
        e.stopPropagation();
        e.preventDefault();
      });
      el.querySelector(".wf-node-stop")?.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        dragNode = null;
        dragStartPos = null;
        nodeDidDrag = false;
        if (window.AgentApp?.stopAgent) {
          window.AgentApp.stopAgent(node.agentId, node.id);
        }
      });
      el.querySelectorAll(".gmail-connect-dot").forEach((dot) => {
        dot.addEventListener("mousedown", (e) => {
          e.stopPropagation();
          e.preventDefault();
        });
        dot.addEventListener("click", (e) => {
          e.stopPropagation();
          e.preventDefault();
          dragNode = null;
          dragStartPos = null;
          nodeDidDrag = false;
          if (window.AgentApp?.connectGmail) window.AgentApp.connectGmail();
          else openAgentModal(node.id);
        });
      });
      el.querySelectorAll(".youtube-connect-dot").forEach((dot) => {
        dot.addEventListener("mousedown", (e) => {
          e.stopPropagation();
          e.preventDefault();
        });
        dot.addEventListener("click", (e) => {
          e.stopPropagation();
          e.preventDefault();
          dragNode = null;
          dragStartPos = null;
          nodeDidDrag = false;
          if (window.AgentApp?.connectYouTube) window.AgentApp.connectYouTube();
          else {
            openAgentModal(node.id);
            setTimeout(() => document.getElementById("btn-connect-youtube")?.click(), 150);
          }
        });
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
        tryConnect(connectingFrom, node.id);
        connectingFrom = null;
        connectCursor = null;
        renderConnections();
      });

      layer.appendChild(el);
  }

  function selectNode(nodeId) {
    selectedNodeId = nodeId;
    renderNodes();
  }

  function renderProperties(nodeId, options = {}) {
    const node = nodeId ? workflow.nodes.find((n) => n.id === nodeId) : null;
    const agentId = options.agentId || node?.agentId;
    if (!agentId) return;
    const agent = getAgent(agentId);
    if (!agent) return;
    const cfg = node
      ? getEffectiveAgentConfig(agentId, node.config || {})
      : getEffectiveAgentConfig(agentId, savedAgentConfigs[agentId] || {});
    const body = options.bodyId ? $id(options.bodyId) : $id("modal-props-body");
    const agentIdEl = options.bodyId ? null : $id("modal-props-agent-id");
    if (!body) return;
    if (agentIdEl) agentIdEl.textContent = agent.id;

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
    if (agent.id === "org-knowledge-base") {
      const upstreamHint = node && hasUpstreamNodes(node.id)
        ? `<p class="prop-hint">Leave folder blank to use upstream PDF folder output.</p>`
        : "";
      extra = `
        <div class="prop-group prop-actions">
          <div class="moravec-inline">
            <strong>Moravec's Paradox</strong>
            <p>AI: repetitive reading, indexing, pattern search. You: judgment, relationships, decisions.</p>
          </div>
          <label>Action</label>
          <select id="kb-action">
            <option value="build"${(cfg.action || "build") === "build" ? " selected" : ""}>Build knowledge base</option>
            <option value="ask"${cfg.action === "ask" ? " selected" : ""}>Ask question</option>
          </select>
          <label>Collection name</label>
          <input type="text" id="kb-collection" value="${escapeHtml(cfg.collection || "org-knowledge")}" />
          <label>PDF folder</label>
          <input type="text" id="kb-folder" placeholder="Leave blank for upstream / all folders (.)" value="${escapeHtml(cfg.folder_path || "")}" />
          <label class="checkbox-row">
            <input type="checkbox" id="kb-include-videos"${cfg.include_videos ? " checked" : ""} />
            Also embed videos in PDF folder (transcript + visual scenes)
          </label>
          ${upstreamHint}
          <p class="prop-hint">PDFs and videos searched recursively. Use downloads, gmail_attachments, or . for entire workspace.</p>
          <label>Video folder (optional)</label>
          <input type="text" id="kb-video-folder" placeholder="downloads/videos" value="${escapeHtml(cfg.video_folder || "")}" />
          <p class="prop-hint">Requires ffmpeg + OPENAI_API_KEY (Whisper transcript + frame descriptions → embeddings).</p>
          <label>CSV path (optional)</label>
          <input type="text" id="kb-csv" placeholder="downloads/data.csv" value="" />
          <label>Database URL (optional)</label>
          <input type="text" id="kb-db-url" placeholder="postgresql://…" value="" />
          <label>SQL query (optional)</label>
          <textarea id="kb-db-query" rows="2" placeholder="SELECT id, body FROM documents"></textarea>
          <label>SharePoint site (optional)</label>
          <input type="text" id="kb-sp-site" placeholder="contoso.sharepoint.com:/sites/docs" value="" />
          <label>SharePoint folder (optional)</label>
          <input type="text" id="kb-sp-folder" placeholder="Shared Documents/Policies" value="" />
          <label>Question (ask mode)</label>
          <textarea id="kb-question" rows="3" placeholder="What is our refund policy?">${escapeHtml(cfg.question || "")}</textarea>
          <p class="prop-hint">Streams sources without downloading files. Indexed with turbovec for fast search at scale.</p>
        </div>`;
    }
    if (isContentAgent(agent.id)) {
      const platforms = (cfg.platforms || ["YouTube", "LinkedIn", "Twitter"]).join("\n");
      const isDirector = agent.id === "content-director";
      const directorHint = isDirector
        ? `<p class="prop-hint editor-start-hint"><strong>Step 1:</strong> Connect YouTube below.<br><strong>Step 2:</strong> Enter your goal.<br><strong>Step 3:</strong> Click Run Agent.</p>`
        : `<p class="prop-hint">Uses your connected YouTube channel when available.</p>`;
      extra = `
        <div class="prop-group prop-actions platform-connect-block">
          <label>YouTube Channel</label>
          <p class="prop-hint" id="youtube-hint">Connect your YouTube channel to enable publishing, analytics, and trend research.</p>
          <button class="btn btn-tonal" type="button" id="btn-connect-youtube">Connect YouTube</button>
          <button class="btn btn-text hidden" type="button" id="btn-disconnect-youtube">Disconnect</button>
        </div>
        <div class="prop-group prop-actions prop-goal-first">
          <label>Your Goal <span class="label-required">*</span></label>
          <textarea id="content-goal" rows="3" placeholder="e.g. Increase views and audience from Assam — grow Assamese-language YouTube channel">${escapeHtml(cfg.goal || "")}</textarea>
          ${directorHint}
          <label>Creator Type</label>
          <input type="text" id="content-creator-type" value="${escapeHtml(cfg.creator_type || "Regional Content Creator")}" placeholder="Regional Content Creator" />
          <label>Niche</label>
          <input type="text" id="content-niche" value="${escapeHtml(cfg.niche || "")}" placeholder="Assam audience, Assamese culture, Northeast India" />
          <label class="checkbox-row">
            <input type="checkbox" id="content-human-loop"${cfg.human_in_loop !== false ? " checked" : ""} />
            Human-in-the-loop — pause for questions &amp; output review (recommended)
          </label>
          <label>Platforms (one per line)</label>
          <textarea id="content-platforms" rows="3" placeholder="YouTube&#10;LinkedIn&#10;Twitter">${escapeHtml(platforms)}</textarea>
        </div>`;
    }
    if (isUnderstandingAgent(agent.id)) {
      const refBlock = agent.needsReference
        ? `
          <label>Reference Text</label>
          <textarea id="understanding-reference" rows="4" placeholder="Text to compare against…">${escapeHtml(cfg.reference_text || "")}</textarea>`
        : "";
      const upstreamHint = node && hasUpstreamNodes(node.id)
        ? `<p class="prop-hint">Leave input blank to use output from connected upstream agent(s).</p>`
        : "";
      extra = `
        <div class="prop-group prop-actions">
          <label>Input Text</label>
          <textarea id="understanding-text" rows="6" placeholder="Paste or type text to analyze…">${escapeHtml(cfg.text || "")}</textarea>
          ${refBlock}
          ${upstreamHint}
          <p class="prop-hint">Uses OpenAI when configured; otherwise rule-based analysis.</p>
        </div>`;
    }
    if (isPerceptionAgent(agent.id)) {
      const upstreamHint = node && hasUpstreamNodes(node.id)
        ? `<p class="prop-hint">Leave blank to use the output folder from connected upstream agent(s).</p>`
        : "";
      if (agent.id === "read-pdf") {
        extra = `
        <div class="prop-group prop-actions">
          <label>PDF Folder</label>
          <input type="text" id="perception-folder" placeholder="gmail_attachments, downloads, invoices…" value="${escapeHtml(cfg.folder_path || cfg.source || "")}" />
          ${upstreamHint}
          <p class="prop-hint">Reads every .pdf in the folder (including subfolders). Use paths relative to your workspace.</p>
        </div>`;
      } else {
        extra = `
        <div class="prop-group prop-actions">
          <label>Input Source</label>
          <textarea id="perception-source" rows="6" placeholder="Text, URL, file path (downloads/invoices), HTML, logs…">${escapeHtml(cfg.source || cfg.text || "")}</textarea>
          ${upstreamHint}
          <p class="prop-hint">Uses OpenAI when configured; otherwise rule-based reading.</p>
        </div>`;
      }
    }
    if (node?.id === "n-input") {
      const taskVal = $("#workflow-task")?.value || "";
      extra = `
        <div class="prop-group prop-actions">
          <label>Chat Input</label>
          <textarea id="planner-task" rows="3" placeholder="Describe your task for the planner…">${taskVal}</textarea>
        </div>`;
    }

    body.innerHTML = `
      ${options.compact ? "" : `
      <div class="prop-group">
        <label>Agent Name</label>
        <input type="text" id="prop-name" value="${escapeHtml(cfg.name || agent.name)}" />
      </div>`}
      ${extra}
      ${options.compact ? "" : `
      <details class="prop-advanced">
        <summary>Advanced settings</summary>
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
            ${window.AgentModels ? window.AgentModels.renderModelOptions(cfg.model || "auto") : `
            <option value="auto">Auto — pick by task complexity</option>
            <option value="gpt-4o-mini">GPT-4o Mini</option>`}
          </select>
          <p class="prop-hint" id="prop-model-hint">${(cfg.model === "auto" || !cfg.model) ? "Model is chosen from input size, agent type, and task keywords at run time." : "Fixed model for this agent."}</p>
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
      </details>`}
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
    if (e.target.closest(".wf-node-stop") || e.target.closest(".gmail-connect-dot")
      || e.target.closest(".youtube-connect-dot")) return;
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
          if (toId) tryConnect(connectingFrom, toId);
        }
        connectingFrom = null;
        connectCursor = null;
        $$(".wf-port.in").forEach((p) => p.classList.remove("connect-target"));
        renderConnections();
      }
      isPanning = false;
      viewport.classList.remove("panning");
      if (dragNode) {
        if (!nodeDidDrag
          && !e.target.closest(".wf-port")
          && !e.target.closest(".wf-node-expand")
          && !e.target.closest(".wf-node-stop")
          && !e.target.closest(".gmail-connect-dot")
          && !e.target.closest(".youtube-connect-dot")) {
          if (isModelNode(dragNode)) {
            setSelectedModel(dragNode.modelId);
          } else {
            openAgentModal(dragNode.id);
          }
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
      const rect = $("#canvas-stage").getBoundingClientRect();

      const modelId = e.dataTransfer.getData("modelId");
      if (modelId && window.AgentModels?.getModel(modelId)) {
        const x = (e.clientX - rect.left) / scale - MODEL_NODE_W / 2;
        const y = (e.clientY - rect.top) / scale - MODEL_NODE_H / 2;
        workflow.nodes.push({
          id: `m-${Date.now()}`,
          kind: "model",
          modelId,
          x: Math.max(20, x),
          y: Math.max(20, y),
        });
        setSelectedModel(modelId);
        renderCanvas();
        updateEmptyCanvasHint();
        return;
      }

      const agentId = e.dataTransfer.getData("agentId");
      if (!agentId || !getAgent(agentId)) return;
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
    const node = workflow.nodes.find((n) => n.id === nodeId);
    const menu = $("#context-menu");
    menu.querySelector('[data-action="edit"]')?.classList.toggle("hidden", isModelNode(node));
    menu.querySelector('[data-action="run"]')?.classList.toggle("hidden", isModelNode(node));
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
      if (action === "run" && node && !isModelNode(node) && window.AgentApp) {
        window.AgentApp.runAgent(node.agentId, { nodeId: node.id, config: getNodeConfig(node.id) });
      }
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
    $("#btn-stop-workflow")?.addEventListener("click", () => {
      if (window.AgentApp?.stopWorkflow) window.AgentApp.stopWorkflow();
    });
    $("#btn-resume-workflow")?.addEventListener("click", () => {
      const run = getResumableRun();
      if (run && window.AgentApp?.resumeWorkflow) window.AgentApp.resumeWorkflow(run.id);
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
    document.querySelectorAll(".library-tab").forEach((btn) => {
      btn.addEventListener("click", () => switchLibraryTab(btn.dataset.libraryTab));
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeRunLogsModal();
        closeResultModal();
        closeAgentEditor();
        closeAgentModal();
      }
    });

    $("#btn-import-template")?.addEventListener("click", () => {
      $("#template-file-input")?.click();
    });
    $("#template-file-input")?.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        await installTemplatePackage(data);
      } catch (err) {
        logRunEntry({ agent: "System", type: "error", message: err.message || "Failed to install template" });
      }
      e.target.value = "";
    });
    $("#btn-export-workflow")?.addEventListener("click", exportCurrentWorkflowTemplate);

    document.getElementById("use-langchain")?.addEventListener("change", (e) => {
      try {
        localStorage.setItem("agent_studio_use_langchain", e.target.checked ? "1" : "0");
      } catch { /* ignore */ }
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

  function getUpstreamNodeIds(nodeId) {
    return workflow.edges.filter((edge) => edge.to === nodeId).map((edge) => edge.from);
  }

  function getNodeById(nodeId) {
    return workflow.nodes.find((n) => n.id === nodeId) || null;
  }

  function hasUpstreamNodes(nodeId) {
    return getUpstreamNodeIds(nodeId).length > 0;
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

  function setNodeStatus(nodeId, status, execTime) {
    const node = workflow.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    node.status = status;
    if (execTime != null) node.execTime = execTime;
    agentStatuses[node.agentId] = status;
    renderLibrary();
    renderConnections();
    renderNodes();
  }

  function highlightNodeById(nodeId, status, execTime) {
    setNodeStatus(nodeId, status, execTime);
  }

  const WORKFLOW_TEMPLATES = [
    {
      id: "creator-os",
      name: "CreatorOS — Content Operating System",
      stars: 5,
      task: "Multi-agent content team: research → strategy → production → publishing → analytics → learning",
      diagram: `Creator
      │
      ▼
Content Director (CCO)
      │
 ┌────┴────┬────────┬──────────┐
 ▼         ▼        ▼          ▼
Research  Strategy Production Analytics
      │
Trend → Audience → Strategy → Hook → Script
      → Visual → Thumbnail → Edit → Captions
      → Publish → Community → Analytics → Learning`,
      nodes: [
        { id: "n-director", agentId: "content-director", x: 280, y: 20, status: "idle", config: {
          creator_type: "Tech Entrepreneur",
          niche: "AI Startups",
          platforms: ["YouTube", "LinkedIn", "Twitter"],
          goal: "Grow followers and leads",
        }},
        { id: "n-trend", agentId: "content-trend-research", x: 40, y: 180, status: "idle", config: {} },
        { id: "n-audience", agentId: "content-audience-psychology", x: 200, y: 180, status: "idle", config: {} },
        { id: "n-strategy", agentId: "content-strategy", x: 360, y: 180, status: "idle", config: {} },
        { id: "n-hook", agentId: "content-hook-generator", x: 520, y: 180, status: "idle", config: {} },
        { id: "n-script", agentId: "content-script-writer", x: 40, y: 340, status: "idle", config: {} },
        { id: "n-visual", agentId: "content-visual-planner", x: 200, y: 340, status: "idle", config: {} },
        { id: "n-thumb", agentId: "content-thumbnail", x: 360, y: 340, status: "idle", config: {} },
        { id: "n-edit", agentId: "content-video-editing", x: 520, y: 340, status: "idle", config: {} },
        { id: "n-caption", agentId: "content-caption-hashtag", x: 40, y: 500, status: "idle", config: {} },
        { id: "n-publish", agentId: "content-publishing", x: 200, y: 500, status: "idle", config: {} },
        { id: "n-community", agentId: "content-community", x: 360, y: 500, status: "idle", config: {} },
        { id: "n-analytics", agentId: "content-analytics", x: 520, y: 500, status: "idle", config: {} },
        { id: "n-learning", agentId: "content-learning", x: 280, y: 660, status: "idle", config: {} },
      ],
      edges: [
        { from: "n-director", to: "n-trend" },
        { from: "n-trend", to: "n-audience" },
        { from: "n-audience", to: "n-strategy" },
        { from: "n-strategy", to: "n-hook" },
        { from: "n-hook", to: "n-script" },
        { from: "n-script", to: "n-visual" },
        { from: "n-visual", to: "n-thumb" },
        { from: "n-thumb", to: "n-edit" },
        { from: "n-edit", to: "n-caption" },
        { from: "n-caption", to: "n-publish" },
        { from: "n-publish", to: "n-community" },
        { from: "n-community", to: "n-analytics" },
        { from: "n-analytics", to: "n-learning" },
      ],
    },
    {
      id: "org-knowledge-base",
      name: "Organization Knowledge Base",
      stars: 5,
      task: "Build organizational knowledge from PDF folders, CSV, databases, and SharePoint — then ask questions with full transparency",
      diagram: `Moravec's Paradox
AI → read millions of docs, pattern index, retrieval
You → judgment, relationships, final decisions

Sources (stream, no download)
├── PDF folder / SharePoint
├── CSV / Excel rows
└── Database query

        ▼
Organization Knowledge Base (turbovec)
        ▼
Ask your knowledge base`,
      nodes: [
        { id: "n-pdf", agentId: "read-pdf", x: 40, y: 120, status: "idle", config: { folder_path: "invoices" } },
        { id: "n-kb", agentId: "org-knowledge-base", x: 320, y: 120, status: "idle", config: { folder_path: "", action: "build" } },
      ],
      edges: [{ from: "n-pdf", to: "n-kb" }],
    },
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
  let installedTemplates = [];
  const TEMPLATE_SCHEMA = "agent-studio/template/v1";
  let editorNodeId = null;
  let editorAgentId = null;
  let editorDragOffset = { x: 0, y: 0 };

  function installedTemplatesKey() {
    return `${userStoragePrefix}_agent_studio_installed_templates`;
  }

  function loadInstalledTemplates() {
    try {
      const raw = localStorage.getItem(installedTemplatesKey());
      installedTemplates = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(installedTemplates)) installedTemplates = [];
    } catch {
      installedTemplates = [];
    }
  }

  function persistInstalledTemplates() {
    if (!userStoragePrefix) return;
    try {
      localStorage.setItem(installedTemplatesKey(), JSON.stringify(installedTemplates.slice(0, 50)));
    } catch { /* ignore */ }
  }

  function getAllTemplates() {
    const byId = new Map();
    WORKFLOW_TEMPLATES.forEach((t) => byId.set(t.id, { ...t, source: "builtin" }));
    installedTemplates.forEach((t) => byId.set(t.id, { ...t, source: "installed", installed: true }));
    return [...byId.values()];
  }

  function buildTemplatePackage(tpl, agentConfigs = {}) {
    return {
      schema: TEMPLATE_SCHEMA,
      id: tpl.id,
      name: tpl.name,
      task: tpl.task || "",
      nodes: structuredClone(tpl.nodes || []),
      edges: structuredClone(tpl.edges || []),
      agent_configs: structuredClone(agentConfigs),
      meta: { ...(tpl.meta || {}), stars: tpl.stars, exported_at: new Date().toISOString() },
    };
  }

  function downloadJsonFile(filename, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function downloadTemplate(templateId) {
    try {
      if (window.AgentApp?.api) {
        const res = await fetch(`/api/templates/${encodeURIComponent(templateId)}/download`, {
          credentials: "include",
        });
        if (res.ok) {
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `${templateId}.agent-template.json`;
          a.click();
          URL.revokeObjectURL(url);
          logRunEntry({ agent: "System", type: "completed", message: `Downloaded template "${templateId}"` });
          return;
        }
      }
    } catch { /* fallback below */ }
    const tpl = getAllTemplates().find((t) => t.id === templateId);
    if (!tpl) return;
    const configs = {};
    (tpl.nodes || []).forEach((n) => {
      if (n.agentId && savedAgentConfigs[n.agentId]) configs[n.agentId] = savedAgentConfigs[n.agentId];
    });
    downloadJsonFile(`${templateId}.agent-template.json`, buildTemplatePackage(tpl, configs));
    logRunEntry({ agent: "System", type: "completed", message: `Downloaded template "${tpl.name}"` });
  }

  function validateTemplatePackage(data) {
    if (!data || typeof data !== "object") throw new Error("Invalid template file");
    const schema = data.schema || data.schema_version;
    if (schema && schema !== TEMPLATE_SCHEMA) throw new Error(`Unsupported schema: ${schema}`);
    if (!data.id || !data.name || !Array.isArray(data.nodes)) throw new Error("Template missing id, name, or nodes");
    return data;
  }

  async function installTemplatePackage(data) {
    const pkg = validateTemplatePackage(data);
    const entry = {
      id: pkg.id,
      name: pkg.name,
      task: pkg.task || "",
      stars: pkg.meta?.stars || 4,
      nodes: pkg.nodes,
      edges: pkg.edges || [],
      meta: pkg.meta || {},
      installed: true,
    };
    installedTemplates = installedTemplates.filter((t) => t.id !== entry.id);
    installedTemplates.unshift(entry);
    persistInstalledTemplates();

    if (pkg.agent_configs && typeof pkg.agent_configs === "object") {
      Object.entries(pkg.agent_configs).forEach(([agentId, cfg]) => {
        savedAgentConfigs[agentId] = { ...(savedAgentConfigs[agentId] || {}), ...cfg };
      });
      persistSavedAgentConfigs();
    }

    if (window.AgentApp?.api) {
      try {
        await window.AgentApp.api("/api/templates/install", "POST", { package: pkg });
      } catch { /* local install still works offline */ }
    }

    renderWorkflowTemplates();
    logRunEntry({ agent: "System", type: "completed", message: `Installed template "${entry.name}" — open from Templates list` });
    return entry;
  }

  function exportCurrentWorkflowTemplate() {
    const name = $("#workflow-name")?.value?.trim() || "My Workflow";
    const id = currentWorkflowId || `custom-${Date.now()}`;
    const tpl = {
      id,
      name,
      task: getWorkflowTask(),
      stars: 4,
      nodes: structuredClone(workflow.nodes),
      edges: structuredClone(workflow.edges),
    };
    const configs = {};
    workflow.nodes.forEach((n) => {
      if (n.agentId) configs[n.agentId] = getEffectiveAgentConfig(n.agentId, n.config || {});
    });
    downloadJsonFile(`${id}.agent-template.json`, buildTemplatePackage(tpl, configs));
    logRunEntry({ agent: "System", type: "completed", message: `Exported "${name}" as template` });
  }

  async function syncTemplatesFromServer() {
    if (!window.AgentApp?.api) return;
    try {
      const data = await window.AgentApp.api("/api/templates");
      (data.templates || []).forEach((meta) => {
        if (meta.installed && !installedTemplates.some((t) => t.id === meta.id)) {
          /* full payload fetched on demand */
        }
      });
    } catch { /* ignore */ }
  }

  function applyTemplateToCanvas(tpl) {
    activeTemplateId = tpl.id;
    workflow = {
      nodes: structuredClone(tpl.nodes || []),
      edges: structuredClone(tpl.edges || []),
    };
    currentWorkflowId = null;
    agentStatuses = {};
    selectedNodeId = null;
    closeAgentEditor();
    closeAgentModal();
    setWorkflowTask(tpl.task || "");
    const nameEl = $("#workflow-name");
    if (nameEl) nameEl.value = tpl.name;
    updateBreadcrumb(tpl.name);
    renderWorkflowTemplates();
    renderCanvas();
    fitCanvasToWorkflow();
    updateEmptyCanvasHint();
    persistDraftWorkflow();
  }

  function renderStars(count) {
    return "★".repeat(count) + "☆".repeat(Math.max(0, 5 - count));
  }

  function renderWorkflowTemplates() {
    const list = $("#templates-list");
    if (!list) return;
    list.innerHTML = getAllTemplates().map((tpl) => `
      <div class="template-card${activeTemplateId === tpl.id ? " active" : ""}" data-template-id="${tpl.id}">
        <button type="button" class="template-card-main" data-action="load" title="Load on canvas">
          <div class="template-title">${escapeHtml(tpl.name)} <span class="template-stars">${renderStars(tpl.stars || 4)}</span></div>
          ${tpl.installed ? '<span class="template-installed-badge">Installed</span>' : ""}
        </button>
        <div class="template-card-actions">
          <button type="button" class="btn btn-text btn-sm" data-action="download" data-template-id="${escapeHtml(tpl.id)}">Download</button>
        </div>
      </div>
    `).join("");

    list.querySelectorAll(".template-card-main").forEach((btn) => {
      btn.addEventListener("click", () => loadWorkflowTemplate(btn.closest(".template-card")?.dataset.templateId));
    });
    list.querySelectorAll("[data-action=download]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        downloadTemplate(btn.dataset.templateId);
      });
    });
  }

  function loadWorkflowTemplate(templateId) {
    const template = getAllTemplates().find((t) => t.id === templateId);
    if (!template) return;
    applyTemplateToCanvas(template);
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
    renderAgentLibrary,
    renderModelLibrary,
    switchLibraryTab,
    getSelectedModelId,
    setSelectedModel,
    newWorkflow,
    saveCurrentWorkflow,
    getAgent,
    getNodeConfig,
    saveSelectedNodeConfig,
    setAgentStatus,
    setGmailConnected,
    setYouTubeConnected,
    needsYouTubeConnection,
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
    saveWorkflowCheckpoint,
    getResumableRun,
    getRunCheckpoint,
    updateWorkflowControlButtons,
    logRunEntry,
    renderWorkflowRuns,
    openAgentModal,
    closeAgentModal,
    openAgentEditor,
    openAgentEditorFromLibrary,
    closeAgentEditor,
    getWorkflowSnapshot: () => ({
      nodes: structuredClone(workflow.nodes),
      edges: structuredClone(workflow.edges),
      agent_configs: structuredClone(savedAgentConfigs),
    }),
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
    getUpstreamNodeIds,
    getNodeById,
    hasUpstreamNodes,
    applyPlannerResult,
    getWorkflowTask,
    setWorkflowTask,
    setNodeStatus,
    highlightNodeById,
    getAgentStatus,
    setNodeResolvedModel,
    buildModelContext,
    resolveAgentModel,
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
