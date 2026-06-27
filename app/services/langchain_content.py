"""LangChain tool-calling agent for CreatorOS Content Director."""

from __future__ import annotations

import json
from typing import Any

from app.agents.content_registry import CONTENT_PIPELINE, TOOL_TO_AGENT, agent_name
from app.agents.content_tools import build_weekly_plan, run_content_agent
from app.services.langchain_llm import get_chat_model, langchain_available


def _make_tools(state: dict[str, Any], agent_config: dict[str, Any] | None):
    from langchain_core.tools import StructuredTool

    tools = []

    async def _delegate(tool_key: str) -> str:
        agent_id = TOOL_TO_AGENT[tool_key]
        out = await run_content_agent(
            agent_id, state, agent_config=agent_config,
            user_id=str(state.get("_user_id") or "") or None,
        )
        state.setdefault("pipeline_results", {})[agent_id] = out["result"]
        state.setdefault("assigned_agents", []).append(agent_id)
        return json.dumps({"agent_id": agent_id, "mode": out["mode"], "result": out["result"]}, ensure_ascii=False)

    for tool_name, agent_id in TOOL_TO_AGENT.items():
        async def _run(_tool=tool_name) -> str:
            return await _delegate(_tool)

        tools.append(StructuredTool.from_function(
            coroutine=_run,
            name=tool_name,
            description=f"Delegate to {agent_name(agent_id)}",
        ))

    async def finalize_weekly_plan(summary: str) -> str:
        state["weekly_plan"] = build_weekly_plan(state)
        state["director_summary"] = summary
        state["status"] = "finalized"
        return json.dumps({"status": "finalized", "weekly_plan": state["weekly_plan"]}, ensure_ascii=False)

    tools.append(StructuredTool.from_function(
        coroutine=finalize_weekly_plan,
        name="finalize_weekly_plan",
        description="Finalize the weekly content plan after all specialists have run",
    ))
    return tools


async def run_content_director_langchain(
    state: dict[str, Any],
    *,
    agent_config: dict[str, Any] | None = None,
    max_iterations: int = 24,
) -> dict[str, Any]:
    if not langchain_available():
        raise RuntimeError("LangChain not available")

    from langgraph.prebuilt import create_react_agent

    cfg = agent_config or {}
    llm = get_chat_model(str(cfg.get("model") or "").strip() or None, cfg.get("temperature"))
    tools = _make_tools(state, agent_config)

    system = (
        "You are the Content Director (Chief Content Officer) in CreatorOS. "
        "Delegate to specialist tools in this order, then call finalize_weekly_plan: "
        + " → ".join(agent_name(a) for a in CONTENT_PIPELINE)
    )

    agent = create_react_agent(llm, tools, prompt=system)
    payload = {
        "creator_type": state.get("creator_type"),
        "niche": state.get("niche"),
        "platforms": state.get("platforms"),
        "goal": state.get("goal"),
    }

    iteration = 0
    while iteration < max_iterations and state.get("status") != "finalized":
        iteration += 1
        await agent.ainvoke({"messages": [("user", json.dumps(payload, ensure_ascii=False))]})
        missing = [a for a in CONTENT_PIPELINE if a not in state.get("pipeline_results", {})]
        if not missing:
            if state.get("status") != "finalized":
                state["weekly_plan"] = build_weekly_plan(state)
                state["status"] = "finalized"
            break

    state["mode"] = "langchain_react"
    state["iterations"] = iteration
    if not state.get("weekly_plan"):
        state["weekly_plan"] = build_weekly_plan(state)
    return state
