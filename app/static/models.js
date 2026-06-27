/**
 * OpenAI model catalog — only API-available models for the library grid.
 */
(function () {
  const AVAILABLE_CHAT = new Set([
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
  ]);

  const MODEL_ALIASES = {
    "gpt-5.5": "gpt-4.1",
    "gpt-5.5-pro": "gpt-4.1",
    "gpt-5.2": "gpt-4o",
    "gpt-5.2-pro": "gpt-4o",
    "gpt-5.2-mini": "gpt-4.1-mini",
    "gpt-5.2-nano": "gpt-4.1-nano",
    "gpt-5.1": "gpt-4.1",
    "gpt-5.1-thinking": "gpt-4.1",
    "gpt-5.1-pro": "gpt-4.1",
    "gpt-5": "gpt-4o",
    "gpt-5-mini": "gpt-4.1-mini",
    "gpt-5-nano": "gpt-4.1-nano",
    "gpt-oss-120b": "gpt-4.1",
    "gpt-oss-20b": "gpt-4.1-mini",
    "gpt-image-2": "dall-e-3",
    "gpt-image-1.5": "dall-e-3",
  };

  const TIER_MODELS = {
    frontier: "gpt-4.1",
    strong: "gpt-4o",
    balanced: "gpt-4.1-mini",
    fast: "gpt-4.1-nano",
    economy: "gpt-4o-mini",
  };

  const FAMILY_ICON_DEFAULT = {
    "GPT-4.1": "terminal",
    "GPT-4o": "psychology",
    Audio: "mic",
    Image: "image",
  };

  const VARIANT_ICONS = {
    Pro: "workspace_premium",
    Mini: "speed",
    Nano: "bolt",
  };

  const FAMILY_SLUG = {
    "GPT-4.1": "gpt-41",
    "GPT-4o": "gpt-4o",
    Audio: "audio",
    Image: "image-models",
  };

  const MODELS = [
    { id: "gpt-4.1", family: "GPT-4.1", name: "GPT-4.1", variant: "default", icon: "terminal", bestFor: "Coding, agents, long context", strengths: "Strong code generation", whenToUse: "Complex workflows and architecture" },
    { id: "gpt-4.1-mini", family: "GPT-4.1", name: "GPT-4.1 Mini", variant: "Mini", icon: "speed", bestFor: "Balanced cost and quality", strengths: "Fast, capable", whenToUse: "Most agent steps" },
    { id: "gpt-4.1-nano", family: "GPT-4.1", name: "GPT-4.1 Nano", variant: "Nano", icon: "bolt", bestFor: "Classification and tagging", strengths: "Lowest latency tier", whenToUse: "High-volume simple tasks" },
    { id: "gpt-4o", family: "GPT-4o", name: "GPT-4o", variant: "default", icon: "psychology", bestFor: "General multimodal chat", strengths: "Proven all-rounder", whenToUse: "Planning and rich analysis" },
    { id: "gpt-4o-mini", family: "GPT-4o", name: "GPT-4o Mini", variant: "Mini", icon: "speed", bestFor: "Default economy model", strengths: "Reliable and cheap", whenToUse: "Fallback for light tasks" },
    { id: "whisper-1", family: "Audio", name: "Whisper", variant: "Nano", icon: "mic", bestFor: "Speech-to-text", strengths: "Audio transcription", whenToUse: "Audio & video agents" },
    { id: "dall-e-3", family: "Image", name: "DALL·E 3", variant: "default", icon: "palette", bestFor: "Image generation", strengths: "Production image API", whenToUse: "Marketing and design assets" },
  ];

  function coerceModel(modelId, fallback = "gpt-4o-mini") {
    const raw = String(modelId || "").trim();
    if (!raw || raw === "auto") return fallback;
    if (MODEL_ALIASES[raw]) return MODEL_ALIASES[raw];
    if (AVAILABLE_CHAT.has(raw) || raw === "whisper-1" || raw === "dall-e-3") return raw;
    if (/whisper/i.test(raw)) return "whisper-1";
    if (/dall-e|image/i.test(raw)) return "dall-e-3";
    if (/nano|mini/i.test(raw)) return "gpt-4o-mini";
    if (/4\.1/i.test(raw)) return "gpt-4.1";
    return fallback;
  }

  function isAvailableModel(modelId) {
    const id = coerceModel(modelId, "");
    return Boolean(id);
  }

  function getModelIcon(model) {
    if (model.icon) return model.icon;
    if (model.variant !== "default" && VARIANT_ICONS[model.variant]) {
      return VARIANT_ICONS[model.variant];
    }
    return FAMILY_ICON_DEFAULT[model.family] || "smart_toy";
  }

  function familySlug(family) {
    return FAMILY_SLUG[family] || "default";
  }

  function groupByFamily(models) {
    const order = ["GPT-4.1", "GPT-4o", "Audio", "Image"];
    const map = new Map();
    models.forEach((m) => {
      if (!map.has(m.family)) map.set(m.family, []);
      map.get(m.family).push(m);
    });
    return order.filter((f) => map.has(f)).map((f) => ({ family: f, models: map.get(f) }));
  }

  function renderModelOptions(selectedId) {
    const coerced = selectedId && selectedId !== "auto" ? coerceModel(selectedId) : selectedId;
    const autoSelected = !selectedId || selectedId === "auto";
    const autoOption = `<option value="auto"${autoSelected ? " selected" : ""}>Auto — pick by task complexity</option>`;
    return autoOption + groupByFamily(MODELS)
      .map(
        (g) =>
          `<optgroup label="${g.family}">${g.models
            .map(
              (m) =>
                `<option value="${m.id}"${m.id === coerced ? " selected" : ""}>${m.name}</option>`
            )
            .join("")}</optgroup>`
      )
      .join("");
  }

  window.AgentModels = {
    MODELS,
    TIER_MODELS,
    AVAILABLE_CHAT,
    coerceModel,
    isAvailableModel,
    getModelIcon,
    familySlug,
    groupByFamily,
    renderModelOptions,
    getModel(id) {
      const coerced = coerceModel(id, "");
      return MODELS.find((m) => m.id === coerced) || null;
    },
  };
})();
