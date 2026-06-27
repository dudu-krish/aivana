"""Understanding micro-agents — NLP-style analysis with LLM + rule fallback."""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

from app.agents.base import BaseAgent
from app.agents.understanding_registry import UNDERSTANDING_AGENTS, agent_name
from app.services.event_bus import event_bus
from app.services.llm import LLMError, complete_json, llm_configured
from app.services.model_router import apply_model_routing
from app.services.tenant import TenantContext

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}|"
    r"(?:today|tomorrow|yesterday|next week|next month))\b",
    re.I,
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s\-().]{0,2})?(?:\d{3}[\s\-().]?\d{3}[\s\-().]?\d{4}|\d{10})(?!\d)")
_LOCATION_RE = re.compile(
    r"\b(?:in|at|from|near)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b"
)
_PERSON_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")
_ORG_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&]+(?:\s+[A-Z][A-Za-z0-9&]+){0,4})\s+(?:Inc|LLC|Ltd|Corp|Company|Co\.)\b"
)
_POSITIVE = {"good", "great", "thanks", "happy", "excellent", "love", "pleased", "resolved"}
_NEGATIVE = {"bad", "issue", "problem", "broken", "angry", "frustrated", "urgent", "fail", "error"}
_URGENT = {"urgent", "asap", "immediately", "critical", "emergency", "now", "deadline"}
_RISK = {"fraud", "breach", "lawsuit", "violation", "unauthorized", "hack", "risk", "penalty"}
_SPAM = {"winner", "lottery", "click here", "free money", "act now", "unsubscribe", "viagra", "crypto profit"}
_INTENT_RULES = [
    ("support_request", ["help", "support", "issue", "problem", "broken", "not working"]),
    ("purchase", ["buy", "order", "purchase", "invoice", "payment"]),
    ("schedule", ["meeting", "schedule", "calendar", "appointment"]),
    ("feedback", ["feedback", "review", "suggest", "improvement"]),
    ("information", ["what is", "how do", "explain", "tell me"]),
]


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _top_keywords(text: str, limit: int = 8) -> list[str]:
    stop = {
        "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it", "this", "that",
        "with", "as", "at", "be", "are", "was", "were", "from", "by", "we", "you", "your", "our",
    }
    counts = Counter(w for w in _tokens(text) if len(w) > 2 and w not in stop)
    return [w for w, _ in counts.most_common(limit)]


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(_tokens(a)), set(_tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _rule_analyze(agent_id: str, text: str, reference_text: str = "") -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {"status": "error", "message": "No input text provided", "result": {}}

    if agent_id == "intent-detection":
        lower = text.lower()
        hits = [
            {"intent": name, "score": sum(1 for kw in kws if kw in lower)}
            for name, kws in _INTENT_RULES
        ]
        hits = [h for h in hits if h["score"]]
        hits.sort(key=lambda x: -x["score"])
        primary = hits[0]["intent"] if hits else "general_inquiry"
        return {"result": {"primary_intent": primary, "intents": hits or [{"intent": primary, "score": 1}]}}

    if agent_id == "topic-detection":
        keywords = _top_keywords(text, 5)
        topic = keywords[0] if keywords else "general"
        return {"result": {"primary_topic": topic, "topics": keywords}}

    if agent_id == "language-detection":
        if re.search(r"[\u0900-\u097F]", text):
            lang = "hi"
        elif re.search(r"[\u0980-\u09FF]", text):
            lang = "bn"
        elif re.search(r"[\u4e00-\u9fff]", text):
            lang = "zh"
        else:
            lang = "en"
        return {"result": {"language": lang, "confidence": 0.75 if lang != "en" else 0.9}}

    if agent_id == "entity-extraction":
        entities = []
        for m in _EMAIL_RE.finditer(text):
            entities.append({"type": "email", "value": m.group()})
        for m in _PHONE_RE.finditer(text):
            entities.append({"type": "phone", "value": m.group()})
        for m in _PERSON_RE.finditer(text):
            entities.append({"type": "person", "value": m.group()})
        for m in _ORG_RE.finditer(text):
            entities.append({"type": "organization", "value": m.group(0)})
        for m in _LOCATION_RE.finditer(text):
            entities.append({"type": "location", "value": m.group(1)})
        return {"result": {"entities": entities}}

    if agent_id == "keyword-extraction":
        return {"result": {"keywords": _top_keywords(text, 10)}}

    if agent_id == "relationship-extraction":
        people = [m.group() for m in _PERSON_RE.finditer(text)]
        orgs = [m.group(0) for m in _ORG_RE.finditer(text)]
        relations = []
        if people and orgs:
            relations.append({"subject": people[0], "relation": "associated_with", "object": orgs[0]})
        return {"result": {"relationships": relations}}

    if agent_id == "event-detection":
        events = []
        for m in _DATE_RE.finditer(text):
            events.append({"when": m.group(), "description": text[:120]})
        if not events and any(w in text.lower() for w in ("meeting", "launch", "incident", "outage")):
            events.append({"when": None, "description": text[:120]})
        return {"result": {"events": events}}

    if agent_id == "date-extraction":
        return {"result": {"dates": [m.group() for m in _DATE_RE.finditer(text)]}}

    if agent_id == "location-extraction":
        locs = [m.group(1) for m in _LOCATION_RE.finditer(text)]
        return {"result": {"locations": locs}}

    if agent_id == "person-extraction":
        return {"result": {"people": [m.group() for m in _PERSON_RE.finditer(text)]}}

    if agent_id == "organization-extraction":
        return {"result": {"organizations": [m.group(0) for m in _ORG_RE.finditer(text)]}}

    if agent_id == "product-extraction":
        products = re.findall(r"\b([A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z0-9][A-Za-z0-9-]*)*)\b", text)
        products = [p for p in products if p.lower() not in {"the", "we", "please"}][:10]
        return {"result": {"products": products}}

    if agent_id == "emotion-detection":
        lower = text.lower()
        if any(w in lower for w in ("angry", "frustrated", "upset")):
            emotion = "frustration"
        elif any(w in lower for w in ("thank", "happy", "glad")):
            emotion = "gratitude"
        elif any(w in lower for w in ("worried", "concern", "anxious")):
            emotion = "concern"
        else:
            emotion = "neutral"
        return {"result": {"primary_emotion": emotion, "emotions": [emotion]}}

    if agent_id == "sentiment-detection":
        toks = set(_tokens(text))
        pos = len(toks & _POSITIVE)
        neg = len(toks & _NEGATIVE)
        if pos > neg:
            label = "positive"
        elif neg > pos:
            label = "negative"
        else:
            label = "neutral"
        return {"result": {"sentiment": label, "positive_signals": pos, "negative_signals": neg}}

    if agent_id == "urgency-detection":
        lower = text.lower()
        score = sum(1 for w in _URGENT if w in lower)
        level = "high" if score >= 2 else "medium" if score == 1 else "low"
        return {"result": {"urgency": level, "signals": [w for w in _URGENT if w in lower]}}

    if agent_id == "risk-detection":
        lower = text.lower()
        flags = [w for w in _RISK if w in lower]
        level = "high" if len(flags) >= 2 else "medium" if flags else "low"
        return {"result": {"risk_level": level, "flags": flags}}

    if agent_id == "spam-detection":
        lower = text.lower()
        hits = [p for p in _SPAM if p in lower]
        score = min(1.0, len(hits) * 0.25 + (0.2 if _EMAIL_RE.search(text) and "unsubscribe" in lower else 0))
        return {"result": {"is_spam": score >= 0.5, "spam_score": round(score, 2), "signals": hits}}

    if agent_id == "duplicate-detection":
        ref = reference_text.strip()
        if not ref:
            return {"status": "error", "message": "Reference text required for duplicate detection", "result": {}}
        ratio = SequenceMatcher(None, text.lower(), ref.lower()).ratio()
        return {"result": {"is_duplicate": ratio >= 0.85, "similarity": round(ratio, 3)}}

    if agent_id == "similarity-detection":
        ref = reference_text.strip()
        if not ref:
            return {"status": "error", "message": "Reference text required for similarity detection", "result": {}}
        seq = round(SequenceMatcher(None, text.lower(), ref.lower()).ratio(), 3)
        jac = round(_jaccard(text, ref), 3)
        return {"result": {"similarity_score": round((seq + jac) / 2, 3), "sequence_ratio": seq, "jaccard": jac}}

    if agent_id == "root-cause-finder":
        causes = []
        lower = text.lower()
        if "timeout" in lower or "slow" in lower:
            causes.append("Performance or timeout issue")
        if "payment" in lower or "invoice" in lower:
            causes.append("Billing or payment workflow failure")
        if "login" in lower or "password" in lower:
            causes.append("Authentication or access problem")
        if not causes:
            causes.append("Insufficient detail — gather logs and reproduction steps")
        return {"result": {"likely_root_causes": causes, "confidence": 0.6 if len(causes) > 1 else 0.45}}

    return {"result": {"summary": text[:200]}}


class UnderstandingAgent(BaseAgent):
    def __init__(self, tenant: TenantContext, agent_id: str) -> None:
        if agent_id not in UNDERSTANDING_AGENTS:
            raise ValueError(f"Unknown understanding agent: {agent_id}")
        self.tenant = tenant
        self.agent_id = agent_id
        self.agent_name = agent_name(agent_id)

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, self.agent_id, self.agent_name, event_type, message, data
        )

    async def _llm_analyze(
        self,
        text: str,
        reference_text: str,
        agent_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        meta = UNDERSTANDING_AGENTS[self.agent_id]
        cfg = agent_config or {}
        system = (
            f"You are the {self.agent_name} micro-agent. {meta['task']} "
            "Return JSON only with a top-level \"result\" object containing structured findings."
        )
        custom = str(cfg.get("prompt") or "").strip()
        if custom:
            system += f"\n\nAdditional instructions:\n{custom}"

        payload: dict[str, Any] = {"text": text}
        if reference_text:
            payload["reference_text"] = reference_text

        raw = await complete_json(
            system=system,
            user=json.dumps(payload, ensure_ascii=False),
            model=str(cfg.get("model") or "").strip() or None,
            temperature=cfg.get("temperature"),
        )
        if "result" not in raw:
            return {"result": raw}
        return {"result": raw["result"]}

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        text = str(kwargs.get("text") or "").strip()
        reference_text = str(kwargs.get("reference_text") or "").strip()
        agent_config = kwargs.get("agent_config") or {}
        agent_config = apply_model_routing(
            agent_config,
            agent_id=self.agent_id,
            text=text,
            prompt=str(agent_config.get("prompt") or ""),
        )

        if not text:
            await self._emit("error", "No input text. Add text in the agent configuration.")
            return {"status": "error", "message": "No input text"}

        await self._emit("started", f"Analyzing with {self.agent_name}")

        analysis: dict[str, Any]
        mode = "rules"
        try:
            if llm_configured():
                analysis = await self._llm_analyze(text, reference_text, agent_config)
                mode = "llm"
            else:
                analysis = _rule_analyze(self.agent_id, text, reference_text)
        except LLMError as exc:
            await self._emit("progress", f"LLM unavailable ({exc}); using rules")
            analysis = _rule_analyze(self.agent_id, text, reference_text)
            mode = "rules"

        if analysis.get("status") == "error":
            msg = analysis.get("message", "Analysis failed")
            await self._emit("error", msg)
            return {"status": "error", "message": msg}

        result = analysis.get("result", {})
        summary = json.dumps(result, ensure_ascii=False)[:240]
        await self._emit("completed", f"{self.agent_name} complete ({mode})", {"result": result})

        return {"status": "completed", "mode": mode, "result": result}
