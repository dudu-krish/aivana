"""LangGraph workflow runner — executes canvas workflows on the backend."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, TypedDict

from app.services.langchain_llm import langchain_available
from app.services.run_control import AgentCancelledError, check_workflow_cancelled


class WorkflowGraphState(TypedDict, total=False):
    task: str
    context: dict[str, Any]
    results: dict[str, Any]
    order: list[str]
    idx: int
    node_order_defs: list[dict]
    agent_configs: dict[str, dict]


def topological_node_order(nodes: list[dict], edges: list[dict]) -> list[dict]:
    by_id = {n["id"]: n for n in nodes}
    indegree: dict[str, int] = {nid: 0 for nid in by_id}
    adj: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src, dst = edge.get("from"), edge.get("to")
        if src in by_id and dst in by_id:
            adj[src].append(dst)
            indegree[dst] += 1

    queue = deque([nid for nid, deg in indegree.items() if deg == 0])
    ordered_ids: list[str] = []
    while queue:
        nid = queue.popleft()
        ordered_ids.append(nid)
        for nxt in adj.get(nid, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(ordered_ids) != len(by_id):
        for node in nodes:
            if node["id"] not in ordered_ids:
                ordered_ids.append(node["id"])
    return [by_id[nid] for nid in ordered_ids if nid in by_id]


async def invoke_agent_step(
    agent_id: str,
    tenant,
    *,
    task: str,
    node_config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    from app.agents.content_os import ContentAgent, ContentDirectorAgent
    from app.agents.content_registry import is_content_agent, is_content_director
    from app.agents.perception import PerceptionAgent
    from app.agents.perception_registry import is_perception_agent
    from app.agents.planner import PlannerAgent
    from app.agents.understanding import UnderstandingAgent
    from app.agents.understanding_registry import is_understanding_agent
    from app.services.run_control import check_agent_cancelled

    check_agent_cancelled(tenant.user_id, agent_id)

    cfg = node_config or {}

    if agent_id == "planner":
        return await PlannerAgent(tenant).run(
            task=task, context="", connected_agents=[], agent_config=cfg,
        )

    if is_content_director(agent_id):
        return await ContentDirectorAgent(tenant).run(
            creator_type=cfg.get("creator_type", "Tech Entrepreneur"),
            niche=cfg.get("niche", ""),
            platforms=cfg.get("platforms") or ["YouTube", "LinkedIn", "Twitter"],
            goal=cfg.get("goal") or task,
            agent_config=cfg,
        )

    if is_content_agent(agent_id):
        return await ContentAgent(tenant, agent_id).run(
            creator_type=cfg.get("creator_type", "Tech Entrepreneur"),
            niche=cfg.get("niche", ""),
            platforms=cfg.get("platforms") or ["YouTube", "LinkedIn", "Twitter"],
            goal=cfg.get("goal") or task,
            context=context,
            agent_config=cfg,
        )

    if is_understanding_agent(agent_id):
        return await UnderstandingAgent(tenant, agent_id).run(
            text=str(cfg.get("text") or task),
            reference_text=cfg.get("reference_text", ""),
            agent_config=cfg,
        )

    if is_perception_agent(agent_id):
        return await PerceptionAgent(tenant).run(
            source=str(cfg.get("folder_path") or cfg.get("source") or ""),
            agent_config=cfg,
        )

    return {"status": "skipped", "message": f"No handler for agent: {agent_id}"}


def _filter_order(order: list[dict], skip_node_ids: list[str]) -> list[dict]:
    if not skip_node_ids:
        return order
    skip = set(skip_node_ids)
    return [n for n in order if n["id"] not in skip]


async def _run_sequential(
    tenant,
    *,
    task: str,
    order: list[dict],
    agent_configs: dict[str, dict],
    initial_context: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    state: WorkflowGraphState = {
        "task": task,
        "context": dict(initial_context or {}),
        "results": {},
        "order": list(initial_context.get("_completed_node_ids", []) if initial_context else []),
    }
    idx = 0
    try:
        while idx < len(order):
            check_workflow_cancelled(tenant.user_id, run_id)
            node = order[idx]
            agent_id = str(node.get("agentId") or "")
            node_cfg = {**(agent_configs.get(agent_id) or {}), **(node.get("config") or {})}
            result = await invoke_agent_step(
                agent_id, tenant, task=task, node_config=node_cfg, context=dict(state.get("context") or {}),
            )
            state["context"][agent_id] = result
            state["results"][node["id"]] = result
            state["order"].append(node["id"])
            idx += 1
        return {
            "status": "completed",
            "engine": "sequential",
            "task": task,
            "node_order": state["order"],
            "results": state["results"],
            "context": state["context"],
        }
    except AgentCancelledError:
        return {
            "status": "stopped",
            "engine": "sequential",
            "task": task,
            "node_order": state["order"],
            "results": state["results"],
            "context": state["context"],
            "message": "Workflow stopped by user",
        }


async def _run_langgraph(
    tenant,
    *,
    task: str,
    order: list[dict],
    agent_configs: dict[str, dict],
    initial_context: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    from langgraph.graph import END, StateGraph

    start_idx = 0
    ctx = dict(initial_context or {})
    completed_ids: list[str] = list(ctx.pop("_completed_node_ids", []) or [])
    pre_results: dict[str, Any] = dict(ctx.pop("_pre_results", {}) or {})

    async def step(state: WorkflowGraphState) -> WorkflowGraphState:
        check_workflow_cancelled(tenant.user_id, run_id)
        idx = int(state.get("idx") or 0)
        nodes = state.get("node_order_defs") or []
        if idx >= len(nodes):
            return state
        node = nodes[idx]
        agent_id = str(node.get("agentId") or "")
        configs = state.get("agent_configs") or {}
        node_cfg = {**(configs.get(agent_id) or {}), **(node.get("config") or {})}
        result = await invoke_agent_step(
            agent_id,
            tenant,
            task=state.get("task") or task,
            node_config=node_cfg,
            context=dict(state.get("context") or {}),
        )
        ctx_local = dict(state.get("context") or {})
        ctx_local[agent_id] = result
        results = dict(state.get("results") or {})
        results[node["id"]] = result
        order_ids = list(state.get("order") or [])
        order_ids.append(node["id"])
        return {
            **state,
            "context": ctx_local,
            "results": results,
            "order": order_ids,
            "idx": idx + 1,
        }

    def route(state: WorkflowGraphState) -> str:
        idx = int(state.get("idx") or 0)
        nodes = state.get("node_order_defs") or []
        return "step" if idx < len(nodes) else "done"

    graph = StateGraph(WorkflowGraphState)
    graph.add_node("step", step)

    async def finish(state: WorkflowGraphState) -> WorkflowGraphState:
        return state

    graph.add_node("done", finish)
    graph.set_entry_point("step")
    graph.add_conditional_edges("step", route, {"step": "step", "done": "done"})
    graph.add_edge("done", END)

    compiled = graph.compile()
    try:
        final = await compiled.ainvoke({
            "task": task,
            "context": ctx,
            "results": pre_results,
            "order": completed_ids,
            "idx": start_idx,
            "node_order_defs": order,
            "agent_configs": agent_configs,
        })
        return {
            "status": "completed",
            "engine": "langgraph",
            "task": task,
            "node_order": final.get("order", []),
            "results": final.get("results", {}),
            "context": final.get("context", {}),
        }
    except AgentCancelledError:
        return {
            "status": "stopped",
            "engine": "langgraph",
            "task": task,
            "node_order": completed_ids,
            "results": pre_results,
            "context": ctx,
            "message": "Workflow stopped by user",
        }


async def run_workflow_langgraph(
    tenant,
    *,
    task: str,
    nodes: list[dict],
    edges: list[dict],
    agent_configs: dict[str, dict] | None = None,
    prefer_langgraph: bool = True,
    skip_node_ids: list[str] | None = None,
    initial_context: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    order = _filter_order(topological_node_order(nodes, edges), skip_node_ids or [])
    agent_configs = agent_configs or {}
    ctx = dict(initial_context or {})

    try:
        if prefer_langgraph and langchain_available():
            try:
                return await _run_langgraph(
                    tenant,
                    task=task,
                    order=order,
                    agent_configs=agent_configs,
                    initial_context=ctx,
                    run_id=run_id,
                )
            except AgentCancelledError:
                raise
            except Exception:
                pass

        return await _run_sequential(
            tenant,
            task=task,
            order=order,
            agent_configs=agent_configs,
            initial_context=ctx,
            run_id=run_id,
        )
    except AgentCancelledError:
        return {
            "status": "stopped",
            "engine": "sequential",
            "task": task,
            "message": "Workflow stopped by user",
            "node_order": [],
            "results": {},
            "context": ctx,
        }
