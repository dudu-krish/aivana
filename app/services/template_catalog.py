"""Built-in workflow template catalog."""

from __future__ import annotations

from app.models.template_package import TEMPLATE_SCHEMA, TemplatePackage

BUILTIN_TEMPLATES: list[TemplatePackage] = [
    TemplatePackage(
        id="creator-os",
        name="CreatorOS — Content Operating System",
        task="Multi-agent content team: research → strategy → production → publishing → analytics → learning",
        nodes=[
            {"id": "n-director", "agentId": "content-director", "x": 280, "y": 20, "status": "idle", "config": {
                "creator_type": "Tech Entrepreneur", "niche": "AI Startups",
                "platforms": ["YouTube", "LinkedIn", "Twitter"], "goal": "Grow followers and leads",
            }},
            {"id": "n-trend", "agentId": "content-trend-research", "x": 40, "y": 180, "status": "idle", "config": {}},
            {"id": "n-audience", "agentId": "content-audience-psychology", "x": 200, "y": 180, "status": "idle", "config": {}},
            {"id": "n-strategy", "agentId": "content-strategy", "x": 360, "y": 180, "status": "idle", "config": {}},
            {"id": "n-hook", "agentId": "content-hook-generator", "x": 520, "y": 180, "status": "idle", "config": {}},
            {"id": "n-script", "agentId": "content-script-writer", "x": 40, "y": 340, "status": "idle", "config": {}},
            {"id": "n-visual", "agentId": "content-visual-planner", "x": 200, "y": 340, "status": "idle", "config": {}},
            {"id": "n-thumb", "agentId": "content-thumbnail", "x": 360, "y": 340, "status": "idle", "config": {}},
            {"id": "n-video", "agentId": "content-video-creator", "x": 440, "y": 340, "status": "idle", "config": {}},
            {"id": "n-edit", "agentId": "content-video-editing", "x": 520, "y": 340, "status": "idle", "config": {}},
            {"id": "n-caption", "agentId": "content-caption-hashtag", "x": 40, "y": 500, "status": "idle", "config": {}},
            {"id": "n-publish", "agentId": "content-publishing", "x": 200, "y": 500, "status": "idle", "config": {}},
            {"id": "n-community", "agentId": "content-community", "x": 360, "y": 500, "status": "idle", "config": {}},
            {"id": "n-analytics", "agentId": "content-analytics", "x": 520, "y": 500, "status": "idle", "config": {}},
            {"id": "n-learning", "agentId": "content-learning", "x": 280, "y": 660, "status": "idle", "config": {}},
        ],
        edges=[
            {"from": "n-director", "to": "n-trend"}, {"from": "n-trend", "to": "n-audience"},
            {"from": "n-audience", "to": "n-strategy"}, {"from": "n-strategy", "to": "n-hook"},
            {"from": "n-hook", "to": "n-script"}, {"from": "n-script", "to": "n-visual"},
            {"from": "n-visual", "to": "n-thumb"}, {"from": "n-thumb", "to": "n-video"},
            {"from": "n-video", "to": "n-edit"},
            {"from": "n-edit", "to": "n-caption"}, {"from": "n-caption", "to": "n-publish"},
            {"from": "n-publish", "to": "n-community"}, {"from": "n-community", "to": "n-analytics"},
            {"from": "n-analytics", "to": "n-learning"},
        ],
        meta={"stars": 5, "builtin": True, "category": "content"},
    ),
    TemplatePackage(
        id="org-knowledge-base",
        name="Organization Knowledge Base",
        task="Build organizational knowledge from PDF folders, CSV, databases, and SharePoint — then ask questions",
        nodes=[
            {"id": "n-pdf", "agentId": "read-pdf", "x": 40, "y": 120, "status": "idle", "config": {"folder_path": "invoices"}},
            {"id": "n-kb", "agentId": "org-knowledge-base", "x": 320, "y": 120, "status": "idle", "config": {"folder_path": "", "action": "build"}},
        ],
        edges=[{"from": "n-pdf", "to": "n-kb"}],
        meta={"stars": 5, "builtin": True},
    ),
    TemplatePackage(
        id="sales-lead-qualification",
        name="Sales Lead Qualification",
        task="Qualify inbound sales leads from email, score buying intent, and route hot leads to sales outreach",
        nodes=[
            {"id": "n-gmail", "agentId": "gmail-organizer", "x": 40, "y": 120, "status": "idle", "config": {}},
            {"id": "n-plan", "agentId": "planner", "x": 300, "y": 120, "status": "idle", "config": {}},
            {"id": "n-call", "agentId": "telecaller", "x": 560, "y": 80, "status": "idle", "config": {}},
            {"id": "n-mail", "agentId": "mailer", "x": 560, "y": 200, "status": "idle", "config": {}},
        ],
        edges=[
            {"from": "n-gmail", "to": "n-plan"}, {"from": "n-plan", "to": "n-call"}, {"from": "n-plan", "to": "n-mail"},
        ],
        meta={"stars": 5, "builtin": True},
    ),
    TemplatePackage(
        id="support-ticket-automation",
        name="Support Ticket Automation",
        task="Automate support tickets: classify issues, draft replies, update CRM, and escalate VIP customers",
        nodes=[
            {"id": "n-gmail", "agentId": "gmail-organizer", "x": 40, "y": 140, "status": "idle", "config": {}},
            {"id": "n-plan", "agentId": "planner", "x": 300, "y": 140, "status": "idle", "config": {}},
            {"id": "n-mail", "agentId": "mailer", "x": 560, "y": 140, "status": "idle", "config": {}},
        ],
        edges=[{"from": "n-gmail", "to": "n-plan"}, {"from": "n-plan", "to": "n-mail"}],
        meta={"stars": 5, "builtin": True},
    ),
    TemplatePackage(
        id="email-organization",
        name="Email Organization",
        task="Organize today's emails, categorize them, and apply Gmail labels",
        nodes=[{"id": "n-gmail", "agentId": "gmail-organizer", "x": 180, "y": 140, "status": "idle", "config": {}}],
        edges=[],
        meta={"stars": 4, "builtin": True},
    ),
    TemplatePackage(
        id="support-callbacks",
        name="Support Callbacks",
        task="Scan support emails, identify customers who need a callback, and call them",
        nodes=[
            {"id": "n-gmail", "agentId": "gmail-organizer", "x": 40, "y": 140, "status": "idle", "config": {}},
            {"id": "n-plan", "agentId": "planner", "x": 300, "y": 140, "status": "idle", "config": {}},
            {"id": "n-call", "agentId": "telecaller", "x": 560, "y": 140, "status": "idle", "config": {}},
        ],
        edges=[{"from": "n-gmail", "to": "n-plan"}, {"from": "n-plan", "to": "n-call"}],
        meta={"stars": 4, "builtin": True},
    ),
]

_BUILTIN_BY_ID = {t.id: t for t in BUILTIN_TEMPLATES}


def get_builtin_template(template_id: str) -> TemplatePackage | None:
    return _BUILTIN_BY_ID.get(template_id)


def list_builtin_summaries() -> list[dict]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "task": t.task,
            "stars": t.meta.get("stars", 4),
            "builtin": True,
            "node_count": len(t.nodes),
        }
        for t in BUILTIN_TEMPLATES
    ]


def validate_template_payload(data: dict) -> TemplatePackage:
    schema = str(data.get("schema") or "")
    if schema and schema != TEMPLATE_SCHEMA:
        raise ValueError(f"Unsupported template schema: {schema}")
    return TemplatePackage.model_validate(data)
