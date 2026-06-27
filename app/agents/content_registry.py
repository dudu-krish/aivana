"""CreatorOS content agent registry — specialized agents for the content operating system."""

from __future__ import annotations

from typing import Any

CONTENT_PIPELINE: list[str] = [
    "content-trend-research",
    "content-audience-psychology",
    "content-strategy",
    "content-hook-generator",
    "content-script-writer",
    "content-visual-planner",
    "content-thumbnail",
    "content-video-creator",
    "content-video-editing",
    "content-caption-hashtag",
    "content-publishing",
    "content-community",
    "content-analytics",
    "content-learning",
]

CONTENT_AGENTS: dict[str, dict[str, Any]] = {
    "content-director": {
        "name": "Content Director",
        "role": "orchestrator",
        "task": "Chief Content Officer — understand niche, set goals, delegate to specialists, review outputs, track KPIs.",
        "outputs": ["weekly_plan", "assigned_agents"],
    },
    "content-trend-research": {
        "name": "Trend Research",
        "role": "research",
        "task": "Scan YouTube, Reddit, X, LinkedIn, Google Trends, and industry blogs for viral topics and emerging discussions.",
        "outputs": ["topics"],
    },
    "content-audience-psychology": {
        "name": "Audience Psychology",
        "role": "research",
        "task": "Analyze comments, DMs, and community discussions for pain points, desires, objections, and curiosity gaps.",
        "outputs": ["pain_points", "desires", "objections"],
    },
    "content-strategy": {
        "name": "Content Strategy",
        "role": "strategy",
        "task": "Combine trends, audience insights, and business goals into a weekly calendar and platform funnel strategy.",
        "outputs": ["youtube", "linkedin", "twitter", "calendar"],
    },
    "content-hook-generator": {
        "name": "Hook Generator",
        "role": "production",
        "task": "Create first-3-second hooks, headlines, and scroll-stopping openers.",
        "outputs": ["hooks"],
    },
    "content-script-writer": {
        "name": "Script Writer",
        "role": "production",
        "task": "Write long-form videos, shorts, LinkedIn posts, and Twitter threads using PAS, AIDA, and storytelling.",
        "outputs": ["scripts"],
    },
    "content-visual-planner": {
        "name": "Visual Planner",
        "role": "production",
        "task": "Create shot lists with talking head, B-roll, and animation scenes.",
        "outputs": ["shot_list"],
    },
    "content-thumbnail": {
        "name": "Thumbnail Agent",
        "role": "production",
        "task": "Generate thumbnail concepts, text overlays, and CTR predictions.",
        "outputs": ["thumbnails"],
    },
    "content-video-creator": {
        "name": "Video Creator",
        "role": "production",
        "task": "Generate introduction videos using Google Gemini Veo from approved scripts, visuals, and human direction.",
        "outputs": ["intro_video", "veo_prompt"],
    },
    "content-video-editing": {
        "name": "Video Editing",
        "role": "production",
        "task": "Plan cuts, captions, zoom effects, and B-roll suggestions for CapCut, Descript, or Premiere.",
        "outputs": ["edit_plan"],
    },
    "content-caption-hashtag": {
        "name": "Caption & Hashtag",
        "role": "production",
        "task": "Adapt content for LinkedIn, Twitter, Instagram, and YouTube descriptions with hashtags.",
        "outputs": ["captions"],
    },
    "content-publishing": {
        "name": "Publishing",
        "role": "distribution",
        "task": "Schedule and post content to YouTube, LinkedIn, X, Instagram, and Facebook.",
        "outputs": ["schedule"],
    },
    "content-community": {
        "name": "Community",
        "role": "distribution",
        "task": "Draft replies for comments, DMs, and FAQs to nurture the audience.",
        "outputs": ["replies"],
    },
    "content-analytics": {
        "name": "Analytics",
        "role": "analytics",
        "task": "Track watch time, CTR, engagement, followers, and leads.",
        "outputs": ["metrics", "best_topic"],
    },
    "content-learning": {
        "name": "Learning",
        "role": "analytics",
        "task": "Learn what worked, what failed, which hooks converted, and update the creator knowledge base.",
        "outputs": ["learnings", "knowledge_base_updates"],
    },
}

# OpenAI tool schemas — Content Director delegates via tool calls
DELEGATION_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "delegate_trend_research",
            "description": "Run Trend Research Agent — scan platforms for viral topics and competitor content.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_audience_psychology",
            "description": "Run Audience Psychology Agent — extract pain points and desires from audience signals.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_content_strategy",
            "description": "Run Content Strategy Agent — build weekly calendar and platform mix.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_hook_generator",
            "description": "Run Hook Generator Agent — create scroll-stopping hooks and headlines.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_script_writer",
            "description": "Run Script Writer Agent — produce platform-specific scripts and posts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_visual_planner",
            "description": "Run Visual Planning Agent — create shot lists for video production.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_thumbnail",
            "description": "Run Thumbnail Agent — generate thumbnail concepts and CTR estimates.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_video_creator",
            "description": "Run Video Creator Agent — generate intro video with Gemini Veo after human approval.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_video_editing",
            "description": "Run Video Editing Agent — plan cuts, captions, and effects.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_caption_hashtag",
            "description": "Run Caption & Hashtag Agent — platform-specific captions and hashtags.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_publishing",
            "description": "Run Publishing Agent — schedule posts across platforms.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_community",
            "description": "Run Community Agent — draft comment and DM replies.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_analytics",
            "description": "Run Analytics Agent — summarize performance metrics and best topics.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_learning",
            "description": "Run Learning Agent — capture weekly learnings for the creator knowledge base.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_weekly_plan",
            "description": "Review all agent outputs and produce the final weekly content plan with assigned agents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Executive summary of the weekly plan"},
                },
                "required": ["summary"],
            },
        },
    },
]

TOOL_TO_AGENT: dict[str, str] = {
    "delegate_trend_research": "content-trend-research",
    "delegate_audience_psychology": "content-audience-psychology",
    "delegate_content_strategy": "content-strategy",
    "delegate_hook_generator": "content-hook-generator",
    "delegate_script_writer": "content-script-writer",
    "delegate_visual_planner": "content-visual-planner",
    "delegate_thumbnail": "content-thumbnail",
    "delegate_video_creator": "content-video-creator",
    "delegate_video_editing": "content-video-editing",
    "delegate_caption_hashtag": "content-caption-hashtag",
    "delegate_publishing": "content-publishing",
    "delegate_community": "content-community",
    "delegate_analytics": "content-analytics",
    "delegate_learning": "content-learning",
}


def agent_name(agent_id: str) -> str:
    meta = CONTENT_AGENTS.get(agent_id)
    return str(meta["name"]) if meta else agent_id


def is_content_agent(agent_id: str) -> bool:
    return agent_id in CONTENT_AGENTS


def is_content_director(agent_id: str) -> bool:
    return agent_id == "content-director"
