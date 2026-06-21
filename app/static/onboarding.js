/**
 * Agent Studio — interactive first-time tutorial
 */
const AgentOnboarding = (() => {
  let user = null;
  let preferences = {
    use_case: "all",
    onboarding_completed: false,
    onboarding_skipped_count: 0,
    onboarding_completed_count: 0,
  };
  let apiFn = null;
  let stepIndex = 0;
  let active = false;

  const USE_CASE_LABELS = {
    email: "email organization",
    invoices: "invoice reconciliation",
    support: "customer support callbacks",
    all: "full workflow automation",
  };

  function $(sel) { return document.querySelector(sel); }

  function firstName() {
    return (user?.name || "there").trim().split(/\s+/)[0];
  }

  function skippedCount() {
    return Number(preferences.onboarding_skipped_count || 0);
  }

  function completedCount() {
    return Number(preferences.onboarding_completed_count || 0);
  }

  function shouldAutoPrompt(prefs = preferences) {
    const p = prefs || preferences;
    if (Number(p.onboarding_skipped_count || 0) >= 1) return false;
    if (Number(p.onboarding_completed_count || 0) >= 1) return false;
    if (p.onboarding_completed === true || p.onboarding_completed === 1) return false;
    return true;
  }

  function buildSteps() {
    const useCase = preferences.use_case || "all";
    const focus = USE_CASE_LABELS[useCase] || USE_CASE_LABELS.all;
    return [
      {
        target: null,
        title: `Hi ${firstName()}, welcome to Agent Studio`,
        body: `You're here for ${focus}. This 60-second tour shows how to build your first workflow — your data stays private to your account.`,
        placement: "center",
      },
      {
        target: "#sidebar-left",
        title: "Agent Library",
        body: "Drag agents from the library onto the canvas. Each agent does one job — Gmail, planning, calls, email, and more.",
        placement: "right",
      },
      {
        target: "#canvas-viewport",
        title: "Workflow Canvas",
        body: "Drop agents here and connect them: drag from the bottom dot on one agent to the top dot on the next. Data flows along the arrows.",
        placement: "bottom",
      },
      {
        target: "#workflow-task",
        title: "Describe Your Goal",
        body: "Tell the Planner what you want in plain English. Example: \"Organize today's emails and call back distressed customers.\"",
        placement: "bottom",
      },
      {
        target: "#btn-run-workflow",
        title: "Run Workflow",
        body: "Click Run Workflow to execute agents in order. Live logs appear on the right as each step completes.",
        placement: "bottom",
      },
      {
        target: ".sidebar-templates",
        title: "Workflow Templates",
        body: "Start from a pre-built template — Sales Lead Qualification, Support Ticket Automation, and more. Click a template to load it on the canvas.",
        placement: "left",
      },
      {
        target: ".sidebar-runs-panel",
        title: "Run History",
        body: "Every run is saved here. Click a run card to open full logs — great for debugging and auditing.",
        placement: "left",
      },
      {
        target: "#btn-save-workflow",
        title: "Save & Reuse",
        body: "Save workflows to the sidebar. Click any agent on the canvas to configure prompts, models, and Gmail scan dates.",
        placement: "bottom",
      },
      {
        target: null,
        title: "You're ready!",
        body: `You're all set. Start with a blank canvas and drag agents from the library — or load a starter template matched to ${focus}.`,
        placement: "center",
        final: true,
      },
    ];
  }

  let steps = [];

  function configure({ user: u, preferences: prefs, api }) {
    user = u;
    preferences = { ...preferences, ...(prefs || {}) };
    apiFn = api;
    steps = buildSteps();
  }

  async function syncPreferences(next) {
    if (next) preferences = { ...preferences, ...next };
  }

  async function markSkipped() {
    if (!apiFn) return;
    try {
      const res = await apiFn("/api/auth/preferences/onboarding", "POST", { event: "skip" });
      await syncPreferences(res?.preferences);
    } catch { /* ignore */ }
  }

  async function markCompleted() {
    if (!apiFn) return;
    try {
      const res = await apiFn("/api/auth/preferences/onboarding", "POST", { event: "complete" });
      await syncPreferences(res?.preferences);
    } catch { /* ignore */ }
  }

  function positionCard(targetEl, placement) {
    const card = $("#onboarding-card");
    const spotlight = $("#onboarding-spotlight");
    if (!card) return;

    card.classList.remove("placement-center", "placement-right", "placement-left", "placement-bottom", "placement-top");

    if (!targetEl || placement === "center") {
      card.classList.add("placement-center");
      spotlight?.classList.add("hidden");
      $(".onboarding-backdrop")?.classList.remove("hidden");
      return;
    }

    $(".onboarding-backdrop")?.classList.add("hidden");
    spotlight?.classList.remove("hidden");
    const rect = targetEl.getBoundingClientRect();
    const pad = 8;
    if (spotlight) {
      spotlight.style.top = `${rect.top - pad}px`;
      spotlight.style.left = `${rect.left - pad}px`;
      spotlight.style.width = `${rect.width + pad * 2}px`;
      spotlight.style.height = `${rect.height + pad * 2}px`;
    }

    card.classList.add(`placement-${placement || "bottom"}`);
    const cardRect = card.getBoundingClientRect();
    let top = rect.bottom + 16;
    let left = rect.left + rect.width / 2 - cardRect.width / 2;

    if (placement === "right") {
      top = rect.top + rect.height / 2 - cardRect.height / 2;
      left = rect.right + 16;
    } else if (placement === "left") {
      top = rect.top + rect.height / 2 - cardRect.height / 2;
      left = rect.left - cardRect.width - 16;
    } else if (placement === "top") {
      top = rect.top - cardRect.height - 16;
      left = rect.left + rect.width / 2 - cardRect.width / 2;
    }

    left = Math.max(12, Math.min(left, window.innerWidth - cardRect.width - 12));
    top = Math.max(12, Math.min(top, window.innerHeight - cardRect.height - 12));
    card.style.top = `${top}px`;
    card.style.left = `${left}px`;
  }

  function renderStep() {
    const step = steps[stepIndex];
    if (!step) return;

    $("#onboarding-title").textContent = step.title;
    $("#onboarding-body").textContent = step.body;
    $("#onboarding-progress").textContent = `Step ${stepIndex + 1} of ${steps.length}`;

    const prevBtn = $("#onboarding-prev");
    const nextBtn = $("#onboarding-next");
    const starterBtn = $("#onboarding-load-starter");
    if (prevBtn) prevBtn.classList.toggle("hidden", stepIndex === 0);
    if (nextBtn) nextBtn.textContent = step.final ? "Start blank" : "Next";
    if (starterBtn) starterBtn.classList.toggle("hidden", !step.final);

    const targetEl = step.target ? document.querySelector(step.target) : null;
    if (targetEl) {
      targetEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    requestAnimationFrame(() => positionCard(targetEl, step.placement));
  }

  function showOverlay() {
    active = true;
    hidePrompt();
    const overlay = $("#onboarding-overlay");
    overlay?.classList.remove("hidden");
    if (overlay) overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("onboarding-active");
  }

  function hideOverlay() {
    active = false;
    const overlay = $("#onboarding-overlay");
    overlay?.classList.add("hidden");
    if (overlay) overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("onboarding-active");
  }

  function showPrompt() {
    if (active) return;
    const prompt = $("#onboarding-prompt");
    if (!prompt) {
      start(true);
      return;
    }
    const nameEl = $("#onboarding-prompt-name");
    if (nameEl) nameEl.textContent = firstName();
    prompt.classList.remove("hidden");
    prompt.setAttribute("aria-hidden", "false");
  }

  function hidePrompt() {
    const prompt = $("#onboarding-prompt");
    prompt?.classList.add("hidden");
    if (prompt) prompt.setAttribute("aria-hidden", "true");
  }

  async function dismissPrompt() {
    hidePrompt();
    await markSkipped();
    if (window.AgentStudio?.showPersonalizedWelcome) {
      AgentStudio.showPersonalizedWelcome(user?.name, preferences.use_case || "all");
    }
  }

  async function finish(loadStarter) {
    await markCompleted();
    hideOverlay();
    if (loadStarter && window.AgentStudio?.loadStarterWorkflow) {
      AgentStudio.loadStarterWorkflow(preferences.use_case || "all");
    }
    if (window.AgentStudio?.showPersonalizedWelcome) {
      AgentStudio.showPersonalizedWelcome(user?.name, preferences.use_case || "all");
    }
  }

  async function skipTour() {
    await markSkipped();
    hideOverlay();
    if (window.AgentStudio?.showPersonalizedWelcome) {
      AgentStudio.showPersonalizedWelcome(user?.name, preferences.use_case || "all");
    }
  }

  function start(force = false) {
    if (active) return;
    if (!force && !shouldAutoPrompt()) return;
    stepIndex = 0;
    steps = buildSteps();
    showOverlay();
    renderStep();
  }

  function bindUI() {
    $("#onboarding-prompt-yes")?.addEventListener("click", () => {
      hidePrompt();
      start(true);
    });

    $("#onboarding-prompt-no")?.addEventListener("click", () => {
      dismissPrompt();
    });

    $("#onboarding-next")?.addEventListener("click", async () => {
      const step = steps[stepIndex];
      if (step?.final) {
        await finish(false);
        return;
      }
      stepIndex += 1;
      renderStep();
    });

    $("#onboarding-load-starter")?.addEventListener("click", async () => {
      await finish(true);
    });

    $("#onboarding-prev")?.addEventListener("click", () => {
      if (stepIndex > 0) {
        stepIndex -= 1;
        renderStep();
      }
    });

    $("#onboarding-skip")?.addEventListener("click", async () => {
      await skipTour();
    });

    $("#btn-help-tour")?.addEventListener("click", () => start(true));

    window.addEventListener("resize", () => {
      if (active) renderStep();
    });
  }

  bindUI();

  return { configure, shouldAutoPrompt, showPrompt, start, finish, skipTour };
})();

window.AgentOnboarding = AgentOnboarding;
