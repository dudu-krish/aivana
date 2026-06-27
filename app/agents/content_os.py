"""CreatorOS agents — Content Director orchestrator and content specialists."""

from __future__ import annotations

import json
from typing import Any

from app.agents.base import BaseAgent
from app.agents.content_registry import (
    CONTENT_PIPELINE,
    DELEGATION_TOOLS,
    TOOL_TO_AGENT,
    agent_name,
)
from app.agents.content_tools import (
    build_weekly_plan,
    normalize_creator_context,
    run_content_agent,
    run_pipeline_sequential,
)
from app.services.event_bus import event_bus
from app.services.llm import LLMError, complete_with_tools, llm_configured
from app.services.model_router import apply_model_routing
from app.services.run_control import AgentCancelledError, check_agent_cancelled
from app.services.tenant import TenantContext

MAX_DIRECTOR_ITERATIONS = 24
REQUIRED_DELEGATIONS = set(TOOL_TO_AGENT.values()) - set()  # all pipeline agents


class ContentAgent(BaseAgent):
    """Run a single CreatorOS specialist agent."""

    def __init__(self, tenant: TenantContext, agent_id: str) -> None:
        self.tenant = tenant
        self.agent_id = agent_id
        self.agent_name = agent_name(agent_id)

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, self.agent_id, self.agent_name, event_type, message, data
        )

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        agent_config = kwargs.get("agent_config") or {}
        agent_config = apply_model_routing(
            agent_config,
            agent_id=self.agent_id,
            text=str(kwargs.get("goal") or ""),
            prompt=str(agent_config.get("prompt") or ""),
        )

        state = normalize_creator_context({
            "creator_type": str(kwargs.get("creator_type") or "Content Creator"),
            "niche": str(kwargs.get("niche") or kwargs.get("creator_type") or ""),
            "platforms": kwargs.get("platforms") or ["YouTube", "LinkedIn", "Twitter"],
            "goal": str(kwargs.get("goal") or "Grow followers and leads"),
            "pipeline_results": dict(kwargs.get("context") or {}),
            "_user_id": self.tenant.user_id,
        })

        await self._emit("started", f"Running {self.agent_name}")
        out = await run_content_agent(
            self.agent_id, state, agent_config=agent_config, user_id=self.tenant.user_id,
        )
        result = out["result"]
        await self._emit(
            "completed",
            f"{self.agent_name} complete ({out['mode']})",
            {"result": result},
        )
        return {"status": "completed", "mode": out["mode"], "result": result}


class ContentDirectorAgent(BaseAgent):
    """Chief Content Officer — orchestrates specialists via tool calling and review loops."""

    agent_id = "content-director"
    agent_name = "Content Director"

    def __init__(self, tenant: TenantContext) -> None:
        self.tenant = tenant

    async def _emit(self, event_type: str, message: str, data: dict | None = None):
        return await event_bus.emit(
            self.tenant.user_id, self.agent_id, self.agent_name, event_type, message, data
        )

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        state: dict[str, Any],
        agent_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if tool_name == "finalize_weekly_plan":
            summary = str(arguments.get("summary") or "Weekly content plan ready.")
            state["weekly_plan"] = build_weekly_plan(state)
            state["director_summary"] = summary
            state["status"] = "finalized"
            return {"status": "finalized", "summary": summary, "weekly_plan": state["weekly_plan"]}

        agent_id = TOOL_TO_AGENT.get(tool_name)
        if not agent_id:
            return {"error": f"Unknown tool: {tool_name}"}

        await self._emit("progress", f"Delegating → {agent_name(agent_id)}")
        out = await run_content_agent(
            agent_id, state, agent_config=agent_config, user_id=self.tenant.user_id,
        )
        state.setdefault("pipeline_results", {})[agent_id] = out["result"]
        state.setdefault("assigned_agents", []).append(agent_id)
        state.setdefault("completed_delegations", set()).add(agent_id)
        return {"agent_id": agent_id, "mode": out["mode"], "result": out["result"]}

    async def _run_with_tools(
        self,
        state: dict[str, Any],
        agent_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        cfg = agent_config or {}
        system = (
            "You are the Content Director (Chief Content Officer) in CreatorOS. "
            "Understand the creator niche, region, and goals, delegate to specialist agents via tools, "
            "review their outputs, and call finalize_weekly_plan when all specialists have run. "
            "Production agents (hooks, scripts, visual, thumbnail, video creator) pause for human input — "
            "wait for the user to respond in the UI before continuing. "
            "NEVER use generic AI/SaaS/startup content unless the niche explicitly requires it. "
            "Required delegation order: trend research → audience psychology → strategy → "
            "hooks → scripts → visual → thumbnail → video creator → editing → captions → publishing → "
            "community → analytics → learning. Call one or more tools per turn."
        )
        custom = str(cfg.get("prompt") or "").strip()
        if custom:
            system += f"\n\nAdditional instructions:\n{custom}"

        user_payload = {
            "creator_type": state.get("creator_type"),
            "niche": state.get("niche"),
            "platforms": state.get("platforms"),
            "goal": state.get("goal"),
            "completed_agents": list(state.get("assigned_agents") or []),
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]

        completed: set[str] = set(state.get("assigned_agents") or [])
        iteration = 0

        while iteration < MAX_DIRECTOR_ITERATIONS:
            iteration += 1
            check_agent_cancelled(self.tenant.user_id, self.agent_id)
            response = await complete_with_tools(
                messages=messages,
                tools=DELEGATION_TOOLS,
                model=str(cfg.get("model") or "").strip() or None,
                temperature=cfg.get("temperature"),
            )
            message = response.get("message") or {}
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                content = str(message.get("content") or "").strip()
                if state.get("status") == "finalized" or REQUIRED_DELEGATIONS <= completed:
                    state["director_summary"] = content or state.get("director_summary", "")
                    break
                # Nudge: if model stopped early, continue loop with reminder
                messages.append({"role": "assistant", "content": content or "(no tool calls)"})
                remaining = [a for a in CONTENT_PIPELINE if a not in completed]
                messages.append({
                    "role": "user",
                    "content": f"Continue delegating. Remaining agents: {remaining}. "
                    "Call tools until all are done, then finalize_weekly_plan.",
                })
                continue

            messages.append(message)
            for tc in tool_calls:
                fn = tc.get("function") or {}
                tool_name = str(fn.get("name") or "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}

                result = await self._execute_tool(tool_name, args, state, agent_config)
                agent_id = TOOL_TO_AGENT.get(tool_name)
                if agent_id:
                    completed.add(agent_id)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", tool_name),
                    "content": json.dumps(result, ensure_ascii=False),
                })

            if state.get("status") == "finalized":
                break

        if not state.get("weekly_plan"):
            state["weekly_plan"] = build_weekly_plan(state)
        state["mode"] = "llm_tools"
        state["iterations"] = iteration
        return state

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        agent_config = kwargs.get("agent_config") or {}
        agent_config = apply_model_routing(
            agent_config,
            agent_id=self.agent_id,
            text=str(kwargs.get("goal") or ""),
            prompt=str(agent_config.get("prompt") or ""),
        )

        state: dict[str, Any] = normalize_creator_context({
            "creator_type": str(kwargs.get("creator_type") or "Content Creator"),
            "niche": str(kwargs.get("niche") or ""),
            "platforms": kwargs.get("platforms") or ["YouTube", "LinkedIn", "Twitter"],
            "goal": str(kwargs.get("goal") or "Grow followers and leads"),
            "pipeline_results": {},
            "assigned_agents": [],
            "completed_delegations": set(),
            "_user_id": self.tenant.user_id,
        })
        from app.services.youtube_auth import get_connected_youtube_channel, is_youtube_connected

        if is_youtube_connected(self.tenant):
            state["youtube_channel"] = get_connected_youtube_channel(self.tenant.user_id)

        await self._emit(
            "started",
            f"CreatorOS planning for {state['niche']} — goal: {state['goal']}",
        )

        try:
            if llm_configured():
                from app.config import settings
                from app.services.langchain_llm import langchain_available
                from app.services.langchain_content import run_content_director_langchain

                if settings.use_langchain and langchain_available():
                    try:
                        await self._emit("progress", "Running Content Director via LangChain")
                        final = await run_content_director_langchain(state, agent_config=agent_config)
                        final["mode"] = "langchain_react"
                    except Exception as exc:
                        await self._emit("progress", f"LangChain fallback ({exc}); using native tool loop")
                        final = await self._run_with_tools(state, agent_config)
                else:
                    final = await self._run_with_tools(state, agent_config)
            else:
                await self._emit("progress", "LLM not configured — running sequential pipeline")
                final = await run_pipeline_sequential(state, agent_config=agent_config, user_id=self.tenant.user_id)
                final["mode"] = "rules_pipeline"
        except LLMError as exc:
            await self._emit("progress", f"Tool loop fallback ({exc}) — sequential pipeline")
            final = await run_pipeline_sequential(state, agent_config=agent_config, user_id=self.tenant.user_id)
            final["mode"] = "rules_pipeline"
        except AgentCancelledError:
            await self._emit("cancelled", "Content Director stopped by user")
            raise

        # Ensure any missing pipeline steps run (review loop)
        missing_idx = 0
        pipeline_results = dict(final.get("pipeline_results") or {})
        assigned = list(final.get("assigned_agents") or [])

        while missing_idx < len(CONTENT_PIPELINE):
            check_agent_cancelled(self.tenant.user_id, self.agent_id)
            agent_id = CONTENT_PIPELINE[missing_idx]
            if agent_id not in pipeline_results:
                step_state = {**final, "pipeline_results": pipeline_results}
                out = await run_content_agent(agent_id, step_state, agent_config=agent_config, user_id=self.tenant.user_id)
                pipeline_results[agent_id] = out["result"]
                if agent_id not in assigned:
                    assigned.append(agent_id)
                await self._emit("progress", f"Filled gap → {agent_name(agent_id)}")
            missing_idx += 1

        final["pipeline_results"] = pipeline_results
        final["assigned_agents"] = assigned
        if not final.get("weekly_plan"):
            final["weekly_plan"] = build_weekly_plan(final)

        result_payload = {
            "weekly_plan": final["weekly_plan"],
            "assigned_agents": final["assigned_agents"],
            "pipeline_results": pipeline_results,
            "director_summary": final.get("director_summary", "CreatorOS weekly plan generated."),
            "mode": final.get("mode", "rules_pipeline"),
        }

        await self._emit("completed", "CreatorOS weekly plan ready", {"result": result_payload})
        return {"status": "completed", **result_payload}
