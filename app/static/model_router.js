/**
 * Smart model routing — uses only API-available OpenAI model IDs.
 */
(function () {
  const TIER_MODELS = window.AgentModels?.TIER_MODELS || {
    frontier: "gpt-4.1",
    strong: "gpt-4o",
    balanced: "gpt-4.1-mini",
    fast: "gpt-4.1-nano",
    economy: "gpt-4o-mini",
  };

  const COMPLEX_KEYWORDS = [
    "architect", "architecture", "design review", "research", "strategy",
    "multi-step", "analyze", "investigate", "root cause", "debug",
    "complex", "critical", "mission", "planning", "code review",
    "reasoning", "compliance", "legal",
  ];
  const SIMPLE_KEYWORDS = [
    "classify", "tag", "label", "extract", "parse", "summarize",
    "simple", "quick", "short", "yes/no", "categorize", "keyword",
    "spam", "duplicate",
  ];
  const HEAVY_AGENTS = new Set(["planner", "root-cause-finder", "org-knowledge-base", "chat-agent", "summarizer"]);
  const MEDIUM_AGENTS = new Set([
    "intent-detection", "sentiment-analysis", "entity-extraction",
    "topic-modeling", "topic-detection", "risk-detection", "similarity-detection", "read-pdf", "web-search",
  ]);
  const LIGHT_AGENTS = new Set(["spam-detection", "keyword-extraction", "urgency-detection"]);

  function coerce(modelId) {
    return window.AgentModels?.coerceModel(modelId, "gpt-4o-mini") || "gpt-4o-mini";
  }

  function combinedText(...parts) {
    return parts.filter((p) => p != null && String(p).trim()).map((p) => String(p).trim()).join(" ");
  }

  function scoreComplexity(ctx) {
    const blob = combinedText(ctx.text, ctx.task, ctx.prompt, ctx.question);
    const blobLower = blob.toLowerCase();
    const charLen = Math.max(blob.length, ctx.source_size || 0);
    let score = 0;

    if (charLen > 12000) score += 4;
    else if (charLen > 4000) score += 3;
    else if (charLen > 1500) score += 2;
    else if (charLen > 400) score += 1;

    COMPLEX_KEYWORDS.forEach((kw) => { if (blobLower.includes(kw)) score += 1.2; });
    SIMPLE_KEYWORDS.forEach((kw) => { if (blobLower.includes(kw)) score -= 0.7; });

    const aid = String(ctx.agent_id || "").toLowerCase();
    if (HEAVY_AGENTS.has(aid)) score += 2.5;
    else if (MEDIUM_AGENTS.has(aid)) score += 1;
    else if (LIGHT_AGENTS.has(aid)) score -= 0.5;

    const connected = ctx.connected_agents || [];
    if (connected.length > 4) score += 1.5;
    else if (connected.length > 2) score += 0.5;

    if (String(ctx.action || "").toLowerCase() === "ask" && charLen > 200) score += 1;
    if (/\b(?:api|sql|python|typescript|javascript|refactor)\b/.test(blobLower)) score += 1;

    return Math.max(0, score);
  }

  function pickModel(ctx) {
    const blobLower = combinedText(ctx.text, ctx.task, ctx.prompt, ctx.question).toLowerCase();
    const aid = String(ctx.agent_id || "").toLowerCase();

    if (aid === "speech-agent" || blobLower.includes("transcrib") || blobLower.includes("whisper")) {
      return { modelId: "whisper-1", tier: "speech", score: 0, reason: "Speech / audio transcription task" };
    }
    if (blobLower.includes("generate image") || blobLower.includes("image generation")) {
      return { modelId: "dall-e-3", tier: "image", score: 0, reason: "Image generation task" };
    }

    const score = scoreComplexity(ctx);
    let tier = "economy";
    let reason = "Minimal complexity — quick pass over small input";
    if (score >= 7) {
      tier = "frontier";
      reason = "High complexity — large input, deep reasoning, or critical planning";
    } else if (score >= 5) {
      tier = "strong";
      reason = "Moderate-high complexity — multi-step analysis or rich context";
    } else if (score >= 3) {
      tier = "balanced";
      reason = "Balanced workload — standard NLP / workflow step";
    } else if (score >= 1.5) {
      tier = "fast";
      reason = "Light task — classification, tagging, or short input";
    }

    return { modelId: TIER_MODELS[tier], tier, score, reason };
  }

  function isAutoModel(model) {
    const value = String(model || "").trim().toLowerCase();
    return !value || value === "auto";
  }

  function resolveModel(agentConfig, ctx) {
    const cfg = agentConfig || {};
    const explicit = String(cfg.model || "").trim();
    const mode = String(cfg.model_mode || "auto").trim().toLowerCase();

    if (explicit && explicit.toLowerCase() !== "auto" && mode !== "auto") {
      const coerced = coerce(explicit);
      if (coerced === explicit) {
        return { modelId: coerced, tier: "manual", score: 0, reason: "Manual model selection" };
      }
      return {
        modelId: coerced,
        tier: "manual",
        score: 0,
        reason: `Using ${coerced} (mapped from unavailable ${explicit})`,
      };
    }

    const pick = pickModel({
      agent_id: ctx.agent_id || cfg.agent_id || "",
      text: ctx.text || "",
      task: ctx.task || "",
      prompt: ctx.prompt || cfg.prompt || "",
      question: ctx.question || "",
      connected_agents: ctx.connected_agents || [],
      action: ctx.action || "",
      source_size: ctx.source_size || 0,
    });
    return { ...pick, modelId: coerce(pick.modelId) };
  }

  window.AgentModelRouter = {
    pickModel,
    resolveModel,
    isAutoModel,
    scoreComplexity,
    coerceModel: coerce,
  };
})();
