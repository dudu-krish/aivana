"""Planner agent — LLM-powered workflow routing with rule-based fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.perception_registry import PERCEPTION_AGENTS
from app.agents.understanding_registry import UNDERSTANDING_AGENTS
from app.services.event_bus import event_bus
from app.services.llm import LLMError, complete_json, llm_configured
from app.services.model_router import apply_model_routing
from app.services.tenant import TenantContext

AGENT_ID = "planner"
AGENT_NAME = "Planner"

PLANNER_SYSTEM_PROMPT = """You are the Planner agent in Agent Studio.
Analyze the user's workflow task and scanned emails. Identify customers who:
- are in distress, frustrated, or blocked
- report a problem, bug, outage, billing issue, or urgent support need
- explicitly ask for a phone callback or human contact

Rules:
- Only recommend calling phone numbers belonging to the customer who needs help.
- Do NOT use numbers from unrelated emails, marketing messages, shipping notices, or generic footer signatures unless that email is the distressed customer.
- If the same customer gives one number in the message and another in the signature, prefer the number in the main request sentence.
- Ignore newsletters, promotions, and automated notifications unless they contain an urgent customer problem.
- Return JSON only, matching the schema exactly.

Schema:
{
  "reasoning": "short explanation",
  "agents_to_run": ["telecaller", "mailer", "gmail-organizer", "gmail-calendar", "whatsapp", "data-scraper", "file-download", "invoice-matcher"],
  "distressed_customers": [
    {
      "name": "customer name or Unknown",
      "email": "sender email",
      "subject": "email subject",
      "issue_summary": "what problem they reported",
      "urgency": "high|medium|low",
      "needs_call": true,
      "phone_numbers": ["+917XXXXXXXXX"],
      "call_message": "short phone greeting tailored to their issue"
    }
  ],
  "email_actions": [
    {
      "to": ["email@example.com"],
      "subject": "subject line",
      "body": "email body",
      "reason": "why send this email"
    }
  ]
}
"""

# --- Rule-based fallback (when LLM unavailable) ---

AGENT_KEYWORDS: dict[str, list[str]] = {
    "gmail-organizer": ["gmail", "email", "emails", "inbox", "organize", "categorize", "mail"],
    "gmail-calendar": ["calendar", "schedule", "meeting", "appointment", "event", "book"],
    "invoice-matcher": ["invoice", "payment", "reconcile", "match", "vendor", "bill"],
    "telecaller": ["call", "phone", "callback", "call back", "call me", "support", "reach out"],
    "mailer": ["send email", "mailer", "reply", "respond", "follow up"],
    "whatsapp": ["whatsapp", "whats app", "wa message", "text message"],
    "data-scraper": ["scrape", "scraper", "crawl", "extract data", "web data", "fetch page"],
    "file-download": ["download", "save file", "fetch file", "get file", "pull file"],
}

for _uid, _meta in UNDERSTANDING_AGENTS.items():
    AGENT_KEYWORDS[_uid] = list(_meta.get("keywords") or [])

for _uid, _meta in PERCEPTION_AGENTS.items():
    AGENT_KEYWORDS[_uid] = list(_meta.get("keywords") or [])

CALL_INTENT_PHRASES = [
    "call back", "callback", "call me", "please call", "ring me",
    "contact me", "reach me", "request for support", "need support", "reach out",
]

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s\-().]{0,2})?"
    r"(?:\d{3}[\s\-().]?\d{3}[\s\-().]?\d{4}|\d{10})(?!\d)"
)


def _normalize_phone(raw: str) -> str | None:
    cleaned = re.sub(r"[\s\-().]", "", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    digits = cleaned.lstrip("+")
    if not digits.isdigit() or len(digits) < 10:
        return None
    if cleaned.startswith("+"):
        return cleaned
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    return f"+{digits}"


def _digits_key(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else digits


def _has_call_intent(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in CALL_INTENT_PHRASES)


def _dedupe_summaries(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in summaries:
        key = f"{item.get('subject', '')}|{item.get('from', '')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _load_gmail_context(user_id: str) -> tuple[str, list[dict[str, Any]]]:
    events = [e for e in event_bus.history(user_id) if e.get("agent_id") == "gmail-organizer"]

    for event in reversed(events):
        if event.get("event_type") != "completed":
            continue
        data = event.get("data") or {}
        summaries = data.get("email_summaries")
        if isinstance(summaries, list) and summaries:
            unique = _dedupe_summaries([s for s in summaries if isinstance(s, dict)])
            return json.dumps(unique, ensure_ascii=False), unique

    last_started = None
    for i in range(len(events) - 1, -1, -1):
        if events[i].get("event_type") == "started":
            last_started = i
            break
    if last_started is None:
        return "[]", []

    summaries: list[dict[str, Any]] = []
    for event in events[last_started:]:
        if event.get("event_type") != "categorized":
            continue
        data = event.get("data") or {}
        summaries.append(
            {
                "subject": str(data.get("subject", "")),
                "from": str(data.get("from", "")),
                "body_preview": str(data.get("body_preview", "")),
                "category": data.get("category"),
            }
        )
    unique = _dedupe_summaries(summaries)
    return json.dumps(unique, ensure_ascii=False), unique


def _filter_connected(agents: list[str], connected: list[str]) -> list[str]:
    if not connected:
        return agents
    return [a for a in agents if a in connected]


def _build_calls(distressed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    seen: set[str] = set()
    for customer in distressed:
        if not customer.get("needs_call"):
            continue
        message = str(customer.get("call_message") or "Hello, we are returning your support request call.")
        name = str(customer.get("name") or "there")
        for raw in customer.get("phone_numbers") or []:
            phone = _normalize_phone(str(raw))
            if not phone:
                continue
            key = _digits_key(phone)
            if key in seen:
                continue
            seen.add(key)
            calls.append(
                {
                    "phone_number": phone,
                    "message": message,
                    "customer_name": name,
                    "issue_summary": customer.get("issue_summary", ""),
                    "urgency": customer.get("urgency", "medium"),
                }
            )
    return calls


def _rule_based_plan(
    task: str,
    summaries: list[dict[str, Any]],
    connected: list[str],
) -> dict[str, Any]:
    combined = task.lower()
    scores: dict[str, int] = {}
    for agent_id, keywords in AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score:
            scores[agent_id] = score

    distressed: list[dict[str, Any]] = []
    for item in summaries:
        subject = str(item.get("subject", ""))
        body = str(item.get("body_preview", ""))
        text = f"{subject}\n{body}"
        if not _has_call_intent(text):
            continue
        phones: list[str] = []
        seen: set[str] = set()
        for match in PHONE_RE.finditer(body[:400]):
            phone = _normalize_phone(match.group())
            if not phone:
                continue
            key = _digits_key(phone)
            if key in seen:
                continue
            seen.add(key)
            phones.append(phone)
        if not phones:
            continue
        distressed.append(
            {
                "name": item.get("from", "Unknown").split("<")[0].strip() or "Unknown",
                "email": item.get("from", ""),
                "subject": subject,
                "issue_summary": body[:160],
                "urgency": "high",
                "needs_call": True,
                "phone_numbers": phones,
                "call_message": "Hello, I'm calling back regarding your support request.",
            }
        )

    calls = _build_calls(distressed)
    if calls:
        scores["telecaller"] = scores.get("telecaller", 0) + 5

    if connected:
        agents = _filter_connected(
            [a for a, _ in sorted(scores.items(), key=lambda x: -x[1])],
            connected,
        )
        if calls and "telecaller" in connected and "telecaller" not in agents:
            agents.insert(0, "telecaller")
    elif scores:
        agents = [a for a, _ in sorted(scores.items(), key=lambda x: -x[1])]
    else:
        agents = ["gmail-organizer"]

    return {
        "reasoning": "Rule-based planner (set OPENAI_API_KEY for LLM planning)",
        "agents_to_run": agents,
        "distressed_customers": distressed,
        "email_actions": [],
        "phone_numbers": [c["phone_number"] for c in calls],
        "calls": calls,
        "planner_mode": "rules",
    }


async def _llm_plan(
    task: str,
    summaries: list[dict[str, Any]],
    connected: list[str],
    agent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = agent_config or {}
    cfg = apply_model_routing(
        cfg,
        agent_id=AGENT_ID,
        task=task,
        prompt=str(cfg.get("prompt") or ""),
        connected_agents=connected,
        text=json.dumps(summaries, ensure_ascii=False)[:8000],
    )
    system = PLANNER_SYSTEM_PROMPT
    custom_prompt = str(cfg.get("prompt") or "").strip()
    if custom_prompt:
        system += f"\n\nAdditional planner instructions:\n{custom_prompt}"

    user_payload = {
        "workflow_task": task,
        "connected_agents": connected,
        "emails": summaries,
    }
    model = str(cfg.get("model") or "").strip() or None
    temperature = cfg.get("temperature")
    temp_val = float(temperature) if temperature is not None else None

    raw = await complete_json(
        system=system,
        user=json.dumps(user_payload, ensure_ascii=False),
        model=model,
        temperature=temp_val,
    )

    distressed = raw.get("distressed_customers") or []
    if not isinstance(distressed, list):
        distressed = []

    cleaned_distressed: list[dict[str, Any]] = []
    for item in distressed:
        if not isinstance(item, dict):
            continue
        cleaned_distressed.append(
            {
                "name": str(item.get("name") or "Unknown"),
                "email": str(item.get("email") or ""),
                "subject": str(item.get("subject") or ""),
                "issue_summary": str(item.get("issue_summary") or ""),
                "urgency": str(item.get("urgency") or "medium"),
                "needs_call": bool(item.get("needs_call")),
                "phone_numbers": [
                    p for p in (item.get("phone_numbers") or []) if str(p).strip()
                ],
                "call_message": str(
                    item.get("call_message")
                    or "Hello, I'm calling back regarding your support request."
                ),
            }
        )

    calls = _build_calls(cleaned_distressed)
    agents = raw.get("agents_to_run") or []
    if not isinstance(agents, list):
        agents = []
    agents = [str(a) for a in agents if str(a).strip()]
    agents = _filter_connected(agents, connected)

    if calls and "telecaller" in connected and "telecaller" not in agents:
        agents.insert(0, "telecaller")

    email_actions = raw.get("email_actions") or []
    if not isinstance(email_actions, list):
        email_actions = []

    if email_actions and "mailer" in connected and "mailer" not in agents:
        agents.append("mailer")

    return {
        "reasoning": str(raw.get("reasoning") or ""),
        "agents_to_run": agents,
        "distressed_customers": cleaned_distressed,
        "email_actions": email_actions,
        "phone_numbers": [c["phone_number"] for c in calls],
        "calls": calls,
        "planner_mode": "llm",
    }


class PlannerAgent(BaseAgent):
    agent_id = AGENT_ID
    agent_name = AGENT_NAME

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, AGENT_ID, AGENT_NAME, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        task = str(kwargs.get("task", "")).strip()
        if not task:
            task = "Organize today's emails and follow up with customers who need support"

        connected_agents = [str(a) for a in (kwargs.get("connected_agents") or []) if str(a).strip()]
        context = str(kwargs.get("context", "") or "").strip()
        agent_config = kwargs.get("agent_config") or {}
        if not isinstance(agent_config, dict):
            agent_config = {}

        if context and context.strip().startswith("["):
            try:
                email_summaries = _dedupe_summaries(json.loads(context))
            except json.JSONDecodeError:
                email_summaries = []
        else:
            _, email_summaries = _load_gmail_context(self.tenant.user_id)

        await self._emit("started", f"Planning task: {task[:120]}")

        if llm_configured():
            try:
                plan = await _llm_plan(task, email_summaries, connected_agents, agent_config)
                await self._emit("progress", "LLM planner analyzing customer emails")
            except LLMError as exc:
                await self._emit("progress", f"LLM unavailable ({exc}) — using rule-based planner")
                plan = _rule_based_plan(task, email_summaries, connected_agents)
        else:
            await self._emit(
                "progress",
                "OPENAI_API_KEY not set — using rule-based planner",
            )
            plan = _rule_based_plan(task, email_summaries, connected_agents)

        if plan.get("reasoning"):
            await self._emit("progress", plan["reasoning"])

        for customer in plan.get("distressed_customers") or []:
            if not customer.get("needs_call"):
                continue
            name = customer.get("name") or "Customer"
            urgency = customer.get("urgency") or "medium"
            issue = customer.get("issue_summary") or customer.get("subject") or "Support needed"
            nums = ", ".join(customer.get("phone_numbers") or []) or "no number found"
            await self._emit(
                "progress",
                f"{urgency.title()} urgency — {name}: {issue[:100]} → {nums}",
                {"customer": customer},
            )

        agents_to_run = plan["agents_to_run"]
        calls = plan.get("calls") or []
        steps: list[str] = []

        for idx, agent_id in enumerate(agents_to_run, start=1):
            label = agent_id.replace("-", " ").title()
            detail = ""
            if agent_id == "telecaller" and calls:
                detail = f" → {len(calls)} call(s)"
            step = f"Step {idx}: Run {label}{detail}"
            steps.append(step)
            await self._emit("progress", step, {"agent_id": agent_id, "step": idx})

        plan_summary = f"Plan: {len(steps)} agent(s) — " + ", ".join(agents_to_run)
        if calls:
            plan_summary += f" | {len(calls)} callback(s)"

        result = {
            "status": "completed",
            "task": task,
            "steps": steps,
            "agents_to_run": agents_to_run,
            "phone_numbers": plan.get("phone_numbers") or [],
            "calls": calls,
            "distressed_customers": plan.get("distressed_customers") or [],
            "email_actions": plan.get("email_actions") or [],
            "planner_mode": plan.get("planner_mode"),
            "reasoning": plan.get("reasoning"),
            "email_summaries": email_summaries,
        }
        await self._emit("completed", plan_summary, result)
        return result
