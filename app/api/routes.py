from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.agents.data_scraper import DataScraperAgent
from app.agents.file_download import FileDownloadAgent
from app.agents.gmail_calendar import GmailCalendarAgent
from app.agents.gmail_organizer import GmailOrganizerAgent
from app.agents.invoice_matcher import InvoiceMatcherAgent
from app.agents.mailer import MailerAgent
from app.agents.planner import PlannerAgent
from app.agents.telecaller import TelecallerAgent
from app.agents.knowledge_base import OrganizationKnowledgeBaseAgent
from app.agents.perception import PerceptionAgent
from app.agents.perception_registry import PERCEPTION_AGENTS, is_perception_agent
from app.agents.understanding import UnderstandingAgent
from app.agents.understanding_registry import UNDERSTANDING_AGENTS, is_understanding_agent
from app.agents.content_os import ContentAgent, ContentDirectorAgent
from app.agents.content_registry import CONTENT_AGENTS, is_content_agent, is_content_director
from app.api.deps import SESSION_COOKIE, get_current_user, get_tenant
from app.config import settings
from app.services.auth import resolve_session, resolve_ws_ticket
from app.services.event_bus import event_bus
from app.services.gmail_auth import (
    disconnect_gmail,
    exchange_code_for_token as exchange_gmail_code,
    get_authorization_url as get_gmail_authorization_url,
    get_connected_gmail_email,
    is_gmail_connected,
)
from app.services.youtube_auth import (
    disconnect_youtube,
    exchange_code_for_token as exchange_youtube_code,
    get_authorization_url as get_youtube_authorization_url,
    get_connected_youtube_channel,
    is_youtube_connected,
)
from app.services.available_models import available_chat_models, available_audio_models, available_image_models, coerce_model
from app.services.model_router import resolve_model
from app.services.knowledge_base.service import KnowledgeBaseService
from app.services.result_queue import clear_user_queue, get_result, latest_for_agent, list_results
from app.services.run_context import current_run_id
from app.services.run_control import (
    AgentCancelledError,
    cancel_all_for_user,
    check_agent_cancelled,
    clear_agent_cancel,
    clear_workflow_cancel,
    is_agent_cancelled,
    request_cancel_agent,
    request_cancel_workflow,
)
from app.services.tenant import TenantContext

router = APIRouter(prefix="/api")

_running: dict[str, bool] = {}


class RunResponse(BaseModel):
    agent_id: str
    status: str
    message: str


class AgentRunContext(BaseModel):
    run_id: str | None = None


class InvoiceMatcherRequest(AgentRunContext):
    pass


class PlannerRequest(BaseModel):
    task: str = ""
    context: str = ""
    connected_agents: list[str] = []
    agent_config: dict[str, Any] | None = None
    run_id: str | None = None


class TelecallerRequest(AgentRunContext):
    phone_numbers: list[str] = []
    message: str = "Hello"
    calls: list[dict[str, Any]] = []


class MailerRequest(AgentRunContext):
    to: list[str] = []
    subject: str = "Hello"
    body: str = "Hello"


class GmailOrganizerRequest(AgentRunContext):
    max_messages: int = 200
    scan_date: str | None = None


class GmailCalendarRequest(AgentRunContext):
    action: str = "list_events"
    date_from: str | None = None
    date_to: str | None = None
    max_results: int = 25
    event_title: str = "Meeting"
    event_start: str | None = None
    event_duration_minutes: int = 30
    attendees: list[str] = []


class WhatsAppRequest(AgentRunContext):
    phone_numbers: list[str] = []
    message: str = "Hello"
    messages: list[dict[str, Any]] = []


class DataScraperRequest(AgentRunContext):
    urls: list[str] = []
    css_selector: str = ""
    extract_links: bool = True
    max_links: int = 20


class FileDownloadRequest(AgentRunContext):
    urls: list[str] = []
    filenames: list[str] = []


class UnderstandingRequest(AgentRunContext):
    agent_id: str
    text: str = ""
    reference_text: str = ""
    agent_config: dict[str, Any] | None = None


class PerceptionRequest(AgentRunContext):
    agent_id: str
    source: str = ""
    folder_path: str = ""
    text: str = ""
    agent_config: dict[str, Any] | None = None


class KnowledgeBuildRequest(AgentRunContext):
    collection: str = "org-knowledge"
    folder_path: str = ""
    sources: list[dict[str, Any]] = []


class KnowledgeAskRequest(AgentRunContext):
    collection: str = "org-knowledge"
    question: str = ""
    top_k: int = 8


class KnowledgeBaseRunRequest(AgentRunContext):
    action: str = "build"
    collection: str = "org-knowledge"
    folder_path: str = ""
    sources: list[dict[str, Any]] = []
    question: str = ""
    top_k: int = 8


class ContentRunRequest(AgentRunContext):
    agent_id: str
    creator_type: str = "Tech Entrepreneur"
    niche: str = ""
    platforms: list[str] = []
    goal: str = "Grow followers and leads"
    context: dict[str, Any] | None = None
    agent_config: dict[str, Any] | None = None


class ContentDirectorRunRequest(AgentRunContext):
    creator_type: str = "Content Creator"
    niche: str = ""
    platforms: list[str] = ["YouTube", "LinkedIn", "Twitter"]
    goal: str = "Grow followers and leads"
    agent_config: dict[str, Any] | None = None


class HumanInputRespondRequest(BaseModel):
    request_id: str
    answers: dict[str, Any] = {}


class WorkflowRunRequest(AgentRunContext):
    task: str = ""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    agent_configs: dict[str, dict[str, Any]] | None = None
    use_langchain: bool = True
    skip_node_ids: list[str] = []
    initial_context: dict[str, Any] | None = None


class WorkflowCancelRequest(BaseModel):
    run_id: str | None = None


class AgentCancelRequest(BaseModel):
    run_id: str | None = None


def _run_key(user_id: str, agent_id: str) -> str:
    return f"{user_id}:{agent_id}"


@router.get("/health")
async def health() -> dict[str, str]:
    from app.services.langchain_llm import langchain_available

    status = {"status": "ok"}
    if langchain_available():
        status["langchain"] = "available"
    return status


class ModelPickRequest(BaseModel):
    agent_id: str = ""
    text: str = ""
    task: str = ""
    prompt: str = ""
    question: str = ""
    connected_agents: list[str] = []
    action: str = ""
    source_size: int = 0
    agent_config: dict[str, Any] | None = None


@router.get("/models/available")
async def models_available() -> dict[str, Any]:
    return {
        "chat": list(available_chat_models()),
        "audio": list(available_audio_models()),
        "image": list(available_image_models()),
        "default": settings.planner_model,
    }


@router.post("/models/pick")
async def models_pick(body: ModelPickRequest) -> dict[str, Any]:
    pick = resolve_model(
        body.agent_config,
        agent_id=body.agent_id,
        text=body.text,
        task=body.task,
        prompt=body.prompt,
        question=body.question,
        connected_agents=body.connected_agents,
        action=body.action,
        source_size=body.source_size,
    )
    return {
        "model_id": pick.model_id,
        "tier": pick.tier,
        "score": pick.score,
        "reason": pick.reason,
    }


@router.get("/events/history")
async def events_history(user: Annotated[dict, Depends(get_current_user)]) -> list[dict]:
    return event_bus.history(user["id"])


@router.websocket("/events/ws")
async def events_websocket(websocket: WebSocket) -> None:
    session_token = websocket.cookies.get(SESSION_COOKIE)
    ticket = websocket.query_params.get("ticket")
    user = resolve_session(session_token) or resolve_ws_ticket(ticket)
    if not user:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    user_id = user["id"]
    queue = await event_bus.subscribe(user_id)
    stop = asyncio.Event()

    async def _ws_reader() -> None:
        try:
            while not stop.is_set():
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("type") != "websocket.receive":
                    continue
                text = message.get("text") or ""
                if text.strip() in ('{"type":"ping"}', "ping"):
                    await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            stop.set()

    reader_task = asyncio.create_task(_ws_reader())
    try:
        await websocket.send_json({"type": "connected", "message": "Live updates enabled"})
        while not stop.is_set():
            get_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {get_task, reader_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if reader_task in done or stop.is_set():
                get_task.cancel()
                break
            event = get_task.result()
            if event.user_id != user_id:
                continue
            await websocket.send_json(
                {
                    "agent_id": event.agent_id,
                    "agent_name": event.agent_name,
                    "event_type": event.event_type,
                    "message": event.message,
                    "data": event.data,
                    "timestamp": event.timestamp,
                }
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        stop.set()
        reader_task.cancel()
        await event_bus.unsubscribe(user_id, queue)


async def _run_agent(run_key: str, coro, run_id: str | None = None) -> None:
    token = None
    if run_id:
        token = current_run_id.set(run_id)

    user_id, _, agent_id = run_key.partition(":")
    clear_agent_cancel(user_id, agent_id)
    _running[run_key] = True
    task = asyncio.create_task(coro)
    try:
        while not task.done():
            if is_agent_cancelled(user_id, agent_id):
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, AgentCancelledError):
                    pass
                await event_bus.emit(
                    user_id,
                    agent_id,
                    agent_id.replace("-", " ").title(),
                    "cancelled",
                    "Agent stopped by user",
                )
                break
            await asyncio.sleep(0.35)
        else:
            await task
    except AgentCancelledError:
        await event_bus.emit(
            user_id,
            agent_id,
            agent_id.replace("-", " ").title(),
            "cancelled",
            "Agent stopped by user",
        )
    finally:
        _running[run_key] = False
        clear_agent_cancel(user_id, agent_id)
        if token is not None:
            current_run_id.reset(token)


@router.post("/data/invoices/upload")
async def upload_invoices(
    tenant: Annotated[TenantContext, Depends(get_tenant)],
    files: Annotated[list[UploadFile], File()],
) -> dict:
    saved = []
    for upload in files:
        dest = tenant.invoices_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved.append(upload.filename)
    return {"uploaded": saved}


@router.post("/data/payments/upload")
async def upload_payments(
    tenant: Annotated[TenantContext, Depends(get_tenant)],
    files: Annotated[list[UploadFile], File()],
) -> dict:
    saved = []
    for upload in files:
        dest = tenant.payments_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved.append(upload.filename)
    return {"uploaded": saved}


@router.post("/agents/invoice-matcher/run", response_model=RunResponse)
async def run_invoice_matcher(
    background_tasks: BackgroundTasks,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
    body: InvoiceMatcherRequest | None = None,
) -> RunResponse:
    req = body or InvoiceMatcherRequest()
    key = _run_key(tenant.user_id, "invoice-matcher")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Invoice matcher is already running")

    agent = InvoiceMatcherAgent(tenant)
    background_tasks.add_task(_run_agent, key, agent.run(), req.run_id)
    return RunResponse(
        agent_id="invoice-matcher",
        status="started",
        message="Invoice reconciliation started",
    )


@router.post("/agents/planner/run")
async def run_planner(
    body: PlannerRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict:
    token = None
    if body.run_id:
        token = current_run_id.set(body.run_id)
    try:
        agent = PlannerAgent(tenant)
        return await agent.run(
            task=body.task,
            context=body.context,
            connected_agents=body.connected_agents,
            agent_config=body.agent_config or {},
        )
    finally:
        if token is not None:
            current_run_id.reset(token)


@router.get("/agents/invoice-matcher/last-result")
async def invoice_matcher_result(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    events = event_bus.history(user["id"])
    for event in reversed(events):
        if event["agent_id"] == "invoice-matcher" and event["event_type"] == "completed":
            return event.get("data", {})
    return {}


@router.get("/gmail/setup")
async def gmail_setup_info(request: Request) -> dict:
    """Shows the exact redirect URI to register in Google Cloud Console."""
    from app.config import settings

    redirect = f"{_public_base_url(request)}/api/gmail/callback"
    return {
        "redirect_uri": redirect,
        "app_base_url": _public_base_url(request),
        "env_redirect_uri": settings.oauth_redirect_uri or None,
        "credentials_found": bool(
            settings.google_client_secrets_json.strip()
            or settings.google_client_secrets_file.exists()
        ),
        "instructions": (
            "Add the redirect_uri below to Google Cloud Console → "
            "Credentials → OAuth 2.0 Client → Authorized redirect URIs. "
            "It must match the ngrok URL you open in the browser exactly."
        ),
    }


@router.get("/gmail/status")
async def gmail_status(tenant: Annotated[TenantContext, Depends(get_tenant)]) -> dict:
    return {
        "connected": is_gmail_connected(tenant),
        "email": get_connected_gmail_email(tenant.user_id),
    }


@router.get("/gmail/auth-url")
async def gmail_auth_url(
    request: Request,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, str]:
    redirect_uri = f"{_public_base_url(request)}/api/gmail/callback"
    try:
        url = get_gmail_authorization_url(user["id"], redirect_uri)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"auth_url": url, "redirect_uri": redirect_uri}


def _public_base_url(request: Request) -> str:
    """Use the same host the user is on (works with ngrok)."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}".rstrip("/")


def _oauth_result_page(title: str, message: str, dashboard_url: str, success: bool = True) -> HTMLResponse:
    btn_color = "#1A73E8" if success else "#D93025"
    extra = (
        f'<p><a href="{dashboard_url}" style="display:inline-block;margin-top:1.5rem;padding:0.75rem 1.5rem;background:{btn_color};color:#fff;text-decoration:none;border-radius:24px;font-weight:500">Return to Agent Studio</a></p>'
        if success
        else f'<p><a href="{dashboard_url}">Back to Agent Studio</a></p>'
    )
    html = f"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  {"<meta http-equiv='refresh' content='3;url=" + dashboard_url + "' />" if success else ""}
  <style>
    body {{ font-family: Roboto, system-ui, sans-serif; background:#f8f9fa; display:flex;
           align-items:center; justify-content:center; min-height:100vh; margin:0; }}
    .card {{ background:#fff; padding:2.5rem; border-radius:16px; box-shadow:0 4px 24px rgba(0,0,0,.08);
             text-align:center; max-width:420px; }}
    h1 {{ font-size:1.4rem; margin:0 0 .75rem; color:#202124; }}
    p {{ color:#5f6368; line-height:1.5; margin:0; }}
  </style>
  {"<script>setTimeout(function(){{ window.location.replace('" + dashboard_url + "'); }}, 1500);</script>" if success else ""}
</head><body>
  <div class="card">
    <h1>{title}</h1>
    <p>{message}</p>
    {extra}
  </div>
</body></html>"""
    return HTMLResponse(html, status_code=200 if success else 400)


@router.get("/gmail/callback")
async def gmail_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    from app.services.database import get_user_by_id

    dashboard_url = f"{_public_base_url(request)}/?gmail=connected"

    if error:
        return _oauth_result_page(
            "Gmail connection cancelled",
            f"Google returned: {error}",
            _public_base_url(request),
            success=False,
        )

    if not code or not state:
        return _oauth_result_page(
            "Gmail connection failed",
            "Missing authorization code. Please try Connect Gmail again.",
            _public_base_url(request),
            success=False,
        )

    user_id_hint = None
    try:
        from app.services.database import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT user_id FROM oauth_states WHERE state = ?", (state,)
            ).fetchone()
            if row:
                user_id_hint = row["user_id"]
    except Exception:
        pass

    if not user_id_hint:
        return _oauth_result_page(
            "Gmail connection failed",
            "OAuth session expired. Go back and click Connect Gmail again.",
            _public_base_url(request),
            success=False,
        )

    user = get_user_by_id(user_id_hint)
    if not user:
        return _oauth_result_page(
            "Gmail connection failed",
            "Account not found. Please sign in again.",
            _public_base_url(request),
            success=False,
        )

    tenant = TenantContext(user_id=user["id"], email=user["email"], name=user["name"])
    try:
        gmail_email = exchange_gmail_code(code, state, tenant)
    except Exception as exc:
        return _oauth_result_page(
            "Gmail connection failed",
            str(exc),
            _public_base_url(request),
            success=False,
        )

    key = _run_key(tenant.user_id, "gmail-organizer")
    if not _running.get(key):
        agent = GmailOrganizerAgent(tenant)
        background_tasks.add_task(
            _run_agent, key, agent.run(max_messages=200)
        )

    return _oauth_result_page(
        "Gmail connected",
        f"<strong>{gmail_email}</strong> is now linked. Scanning today's emails…",
        dashboard_url,
        success=True,
    )


@router.post("/gmail/disconnect")
async def gmail_disconnect(tenant: Annotated[TenantContext, Depends(get_tenant)]) -> dict:
    disconnect_gmail(tenant)
    return {"status": "disconnected"}


@router.get("/youtube/setup")
async def youtube_setup_info(request: Request) -> dict:
    redirect = f"{_public_base_url(request)}/api/youtube/callback"
    return {
        "redirect_uri": redirect,
        "credentials_found": bool(
            settings.youtube_client_secrets_json.strip()
            or settings.youtube_client_secrets_file.exists()
            or settings.google_client_secrets_json.strip()
            or settings.google_client_secrets_file.exists()
        ),
        "instructions": (
            "Enable YouTube Data API v3 and YouTube Analytics API in Google Cloud Console. "
            "Add the redirect_uri to your OAuth client's Authorized redirect URIs."
        ),
    }


@router.get("/youtube/status")
async def youtube_status(tenant: Annotated[TenantContext, Depends(get_tenant)]) -> dict:
    channel = get_connected_youtube_channel(tenant.user_id)
    return {
        "connected": is_youtube_connected(tenant),
        "channel": channel,
    }


@router.get("/youtube/auth-url")
async def youtube_auth_url(
    request: Request,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, str]:
    redirect_uri = f"{_public_base_url(request)}/api/youtube/callback"
    try:
        url = get_youtube_authorization_url(user["id"], redirect_uri)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"auth_url": url, "redirect_uri": redirect_uri}


@router.get("/youtube/callback")
async def youtube_callback(
    request: Request,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    from app.services.database import get_user_by_id

    dashboard_url = f"{_public_base_url(request)}/?youtube=connected"

    if error:
        return _oauth_result_page(
            "YouTube connection cancelled",
            f"Google returned: {error}",
            _public_base_url(request),
            success=False,
        )

    if not code or not state:
        return _oauth_result_page(
            "YouTube connection failed",
            "Missing authorization code. Please try Connect YouTube again.",
            _public_base_url(request),
            success=False,
        )

    user_id_hint = None
    try:
        from app.services.database import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT user_id FROM oauth_states WHERE state = ?", (state,)
            ).fetchone()
            if row:
                user_id_hint = row["user_id"]
    except Exception:
        pass

    if not user_id_hint:
        return _oauth_result_page(
            "YouTube connection failed",
            "OAuth session expired. Go back and click Connect YouTube again.",
            _public_base_url(request),
            success=False,
        )

    user_row = get_user_by_id(user_id_hint)
    if not user_row:
        return _oauth_result_page(
            "YouTube connection failed",
            "User session not found.",
            _public_base_url(request),
            success=False,
        )

    tenant = TenantContext(user_id=user_id_hint, email=user_row["email"], name=user_row["name"])
    try:
        channel = exchange_youtube_code(code, state, tenant)
    except (ValueError, FileNotFoundError) as exc:
        return _oauth_result_page(
            "YouTube connection failed",
            str(exc),
            _public_base_url(request),
            success=False,
        )

    title = channel.get("channel_title", "YouTube Channel")
    return _oauth_result_page(
        "YouTube connected",
        f"<strong>{title}</strong> is now linked to CreatorOS.",
        dashboard_url,
        success=True,
    )


@router.post("/youtube/disconnect")
async def youtube_disconnect(tenant: Annotated[TenantContext, Depends(get_tenant)]) -> dict:
    disconnect_youtube(tenant)
    return {"status": "disconnected"}


@router.post("/agents/gmail-organizer/run", response_model=RunResponse)
async def run_gmail_organizer(
    background_tasks: BackgroundTasks,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
    body: GmailOrganizerRequest | None = None,
) -> RunResponse:
    req = body or GmailOrganizerRequest()
    key = _run_key(tenant.user_id, "gmail-organizer")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Gmail organizer is already running")
    if not is_gmail_connected(tenant):
        raise HTTPException(
            status_code=400,
            detail="Connect your Gmail account first.",
        )

    agent = GmailOrganizerAgent(tenant)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(max_messages=req.max_messages, scan_date=req.scan_date),
        req.run_id,
    )
    day_label = req.scan_date.strip() if req.scan_date and req.scan_date.strip() else "today"
    return RunResponse(
        agent_id="gmail-organizer",
        status="started",
        message=f"Scanning emails from {day_label} in your Gmail",
    )


@router.get("/agents/gmail-organizer/chart-data")
async def gmail_chart_data(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    events = event_bus.history(user["id"])
    for event in reversed(events):
        if event["agent_id"] == "gmail-organizer" and event["event_type"] == "completed":
            return event.get("data", {})
    return {"email_categories": [], "attachment_categories": []}


@router.post("/agents/telecaller/run", response_model=RunResponse)
async def run_telecaller(
    background_tasks: BackgroundTasks,
    body: TelecallerRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    key = _run_key(tenant.user_id, "telecaller")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Telecaller is already running")

    agent = TelecallerAgent(tenant)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(
            phone_numbers=body.phone_numbers,
            message=body.message,
            calls=body.calls,
        ),
        body.run_id,
    )
    return RunResponse(
        agent_id="telecaller",
        status="started",
        message="Outbound calls started",
    )


@router.post("/agents/mailer/run", response_model=RunResponse)
async def run_mailer(
    background_tasks: BackgroundTasks,
    body: MailerRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    key = _run_key(tenant.user_id, "mailer")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Mailer is already running")

    agent = MailerAgent(tenant)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(to=body.to, subject=body.subject, body=body.body),
        body.run_id,
    )
    return RunResponse(
        agent_id="mailer",
        status="started",
        message="Sending emails",
    )


@router.post("/agents/gmail-calendar/run", response_model=RunResponse)
async def run_gmail_calendar(
    background_tasks: BackgroundTasks,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
    body: GmailCalendarRequest | None = None,
) -> RunResponse:
    req = body or GmailCalendarRequest()
    key = _run_key(tenant.user_id, "gmail-calendar")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Gmail Calendar is already running")
    if not is_gmail_connected(tenant):
        raise HTTPException(
            status_code=400,
            detail="Connect your Google account first (Gmail OAuth includes Calendar).",
        )

    agent = GmailCalendarAgent(tenant)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(
            action=req.action,
            date_from=req.date_from,
            date_to=req.date_to,
            max_results=req.max_results,
            event_title=req.event_title,
            event_start=req.event_start,
            event_duration_minutes=req.event_duration_minutes,
            attendees=req.attendees,
        ),
        req.run_id,
    )
    label = "Creating event" if req.action == "create_event" else "Listing events"
    return RunResponse(
        agent_id="gmail-calendar",
        status="started",
        message=f"{label} on your Google Calendar",
    )


@router.post("/agents/whatsapp/run", response_model=RunResponse)
async def run_whatsapp(
    background_tasks: BackgroundTasks,
    body: WhatsAppRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    key = _run_key(tenant.user_id, "whatsapp")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="WhatsApp agent is already running")

    agent = WhatsAppAgent(tenant)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(
            phone_numbers=body.phone_numbers,
            message=body.message,
            messages=body.messages,
        ),
        body.run_id,
    )
    return RunResponse(
        agent_id="whatsapp",
        status="started",
        message="Sending WhatsApp messages",
    )


@router.post("/agents/data-scraper/run", response_model=RunResponse)
async def run_data_scraper(
    background_tasks: BackgroundTasks,
    body: DataScraperRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    key = _run_key(tenant.user_id, "data-scraper")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Data scraper is already running")

    agent = DataScraperAgent(tenant)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(
            urls=body.urls,
            css_selector=body.css_selector,
            extract_links=body.extract_links,
            max_links=body.max_links,
        ),
        body.run_id,
    )
    return RunResponse(
        agent_id="data-scraper",
        status="started",
        message=f"Scraping {len(body.urls)} URL(s)",
    )


@router.post("/agents/file-download/run", response_model=RunResponse)
async def run_file_download(
    background_tasks: BackgroundTasks,
    body: FileDownloadRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    key = _run_key(tenant.user_id, "file-download")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="File download agent is already running")

    agent = FileDownloadAgent(tenant)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(urls=body.urls, filenames=body.filenames),
        body.run_id,
    )
    return RunResponse(
        agent_id="file-download",
        status="started",
        message=f"Downloading {len(body.urls)} file(s)",
    )


@router.post("/agents/understanding/run", response_model=RunResponse)
async def run_understanding_agent(
    background_tasks: BackgroundTasks,
    body: UnderstandingRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    agent_id = body.agent_id.strip()
    if not is_understanding_agent(agent_id):
        raise HTTPException(status_code=404, detail=f"Unknown understanding agent: {agent_id}")

    key = _run_key(tenant.user_id, agent_id)
    if _running.get(key):
        raise HTTPException(status_code=409, detail=f"{UNDERSTANDING_AGENTS[agent_id]['name']} is already running")

    agent = UnderstandingAgent(tenant, agent_id)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(
            text=body.text,
            reference_text=body.reference_text,
            agent_config=body.agent_config,
        ),
        body.run_id,
    )
    return RunResponse(
        agent_id=agent_id,
        status="started",
        message=f"Running {UNDERSTANDING_AGENTS[agent_id]['name']}",
    )


@router.post("/agents/perception/run", response_model=RunResponse)
async def run_perception_agent(
    background_tasks: BackgroundTasks,
    body: PerceptionRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    agent_id = body.agent_id.strip()
    if not is_perception_agent(agent_id):
        raise HTTPException(status_code=404, detail=f"Unknown perception agent: {agent_id}")

    key = _run_key(tenant.user_id, agent_id)
    if _running.get(key):
        raise HTTPException(status_code=409, detail=f"{PERCEPTION_AGENTS[agent_id]['name']} is already running")

    source = (body.folder_path or body.source or body.text or "").strip()
    agent = PerceptionAgent(tenant, agent_id)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(source=source, agent_config=body.agent_config),
        body.run_id,
    )
    return RunResponse(
        agent_id=agent_id,
        status="started",
        message=f"Running {PERCEPTION_AGENTS[agent_id]['name']}",
    )


@router.post("/agents/content/run", response_model=RunResponse)
async def run_content_agent_route(
    background_tasks: BackgroundTasks,
    body: ContentRunRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    agent_id = body.agent_id.strip()
    if not is_content_agent(agent_id) or is_content_director(agent_id):
        raise HTTPException(status_code=404, detail=f"Unknown content agent: {agent_id}")

    key = _run_key(tenant.user_id, agent_id)
    if _running.get(key):
        raise HTTPException(status_code=409, detail=f"{CONTENT_AGENTS[agent_id]['name']} is already running")

    agent = ContentAgent(tenant, agent_id)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(
            creator_type=body.creator_type,
            niche=body.niche or body.creator_type,
            platforms=body.platforms or ["YouTube", "LinkedIn", "Twitter"],
            goal=body.goal,
            context=body.context or {},
            agent_config=body.agent_config,
        ),
        body.run_id,
    )
    return RunResponse(
        agent_id=agent_id,
        status="started",
        message=f"Running {CONTENT_AGENTS[agent_id]['name']}",
    )


@router.post("/agents/content-director/run", response_model=RunResponse)
async def run_content_director(
    background_tasks: BackgroundTasks,
    body: ContentDirectorRunRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    agent_id = "content-director"
    key = _run_key(tenant.user_id, agent_id)
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Content Director is already running")

    agent = ContentDirectorAgent(tenant)
    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(
            creator_type=body.creator_type,
            niche=body.niche or body.creator_type,
            platforms=body.platforms,
            goal=body.goal,
            agent_config=body.agent_config,
        ),
        body.run_id,
    )
    return RunResponse(
        agent_id=agent_id,
        status="started",
        message="Running CreatorOS Content Director",
    )


@router.get("/agents/human-input/pending")
async def list_pending_human_input(
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, Any]:
    from app.services.human_input import list_pending

    return {"pending": list_pending(tenant.user_id)}


@router.post("/agents/human-input/respond")
async def respond_human_input(
    body: HumanInputRespondRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, str]:
    from app.services.human_input import submit_human_input

    ok = submit_human_input(tenant.user_id, body.request_id.strip(), body.answers)
    if not ok:
        raise HTTPException(status_code=404, detail="Input request not found or already answered")
    return {"status": "accepted", "message": "Response recorded — agent will continue"}


@router.get("/content/generated-videos/{filename}")
async def get_generated_video(
    filename: str,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
):
    from fastapi.responses import FileResponse

    from app.config import settings

    safe = Path(filename).name
    path = settings.data_dir / "generated_videos" / tenant.user_id / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path, media_type="video/mp4", filename=safe)


@router.post("/workflows/run")
async def run_workflow_engine(
    body: WorkflowRunRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, Any]:
    from app.config import settings
    from app.services.langchain_workflow import run_workflow_langgraph

    if not body.nodes:
        raise HTTPException(status_code=400, detail="Workflow has no nodes")

    clear_workflow_cancel(tenant.user_id, body.run_id)
    task = body.task.strip() or "Run workflow"
    prefer = body.use_langchain and settings.use_langchain
    return await run_workflow_langgraph(
        tenant,
        task=task,
        nodes=body.nodes,
        edges=body.edges,
        agent_configs=body.agent_configs or {},
        prefer_langgraph=prefer,
        skip_node_ids=body.skip_node_ids or [],
        initial_context=body.initial_context or {},
        run_id=body.run_id,
    )


@router.post("/workflows/cancel")
async def cancel_workflow(
    body: WorkflowCancelRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, str]:
    cancel_all_for_user(tenant.user_id, body.run_id)
    return {"status": "cancelled", "message": "Workflow stop requested"}


@router.post("/agents/{agent_id}/cancel")
async def cancel_agent(
    agent_id: str,
    body: AgentCancelRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, str]:
    from app.services.human_input import cancel_pending_human_input

    request_cancel_agent(tenant.user_id, agent_id)
    if agent_id.startswith("content-") and agent_id != "content-director":
        request_cancel_agent(tenant.user_id, "content-director")
    if agent_id == "content-director":
        from app.agents.content_registry import CONTENT_AGENTS

        for cid in CONTENT_AGENTS:
            request_cancel_agent(tenant.user_id, cid)
    cancel_pending_human_input(tenant.user_id)
    if body.run_id:
        request_cancel_workflow(tenant.user_id, body.run_id)
    return {"status": "cancelled", "agent_id": agent_id, "message": f"Stop requested for {agent_id}"}


@router.post("/agents/cancel-all")
async def cancel_all_agents(
    body: WorkflowCancelRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, str]:
    cancel_all_for_user(tenant.user_id, body.run_id)
    from app.services.human_input import cancel_pending_human_input

    cancel_pending_human_input(tenant.user_id)
    from app.agents.content_registry import CONTENT_AGENTS
    from app.agents.perception_registry import PERCEPTION_AGENTS
    from app.agents.understanding_registry import UNDERSTANDING_AGENTS

    agent_ids = [
        "invoice-matcher", "gmail-organizer", "gmail-calendar", "telecaller",
        "mailer", "whatsapp", "data-scraper", "file-download", "org-knowledge-base",
        "content-director", *UNDERSTANDING_AGENTS, *PERCEPTION_AGENTS, *CONTENT_AGENTS,
    ]
    for aid in agent_ids:
        request_cancel_agent(tenant.user_id, aid)
    return {"status": "cancelled", "message": "All running agents stop requested"}


def _normalize_kb_sources(sources: list[dict], folder_path: str) -> list[dict]:
    folder = folder_path.strip()
    if not sources:
        return [{"type": "folder_pdf", "folder": folder or "."}]
    normalized: list[dict] = []
    for spec in sources:
        src_type = str(spec.get("type") or "").lower()
        if src_type in ("folder_pdf", "pdf_folder", "folder"):
            spec_folder = str(spec.get("folder") or spec.get("path") or folder or ".").strip() or "."
            normalized.append({**spec, "type": "folder_pdf", "folder": spec_folder})
        else:
            normalized.append(spec)
    return normalized


@router.post("/knowledge/build", response_model=RunResponse)
async def build_knowledge_base(
    background_tasks: BackgroundTasks,
    body: KnowledgeBuildRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    key = _run_key(tenant.user_id, "org-knowledge-base")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Knowledge base build already running")

    agent = OrganizationKnowledgeBaseAgent(tenant)
    sources = _normalize_kb_sources(body.sources, body.folder_path)

    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(action="build", collection=body.collection, sources=sources, folder_path=body.folder_path),
        body.run_id,
    )
    return RunResponse(agent_id="org-knowledge-base", status="started", message="Building organization knowledge base")


@router.post("/knowledge/ask")
async def ask_knowledge_base(
    body: KnowledgeAskRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    kb = KnowledgeBaseService(tenant)
    return await kb.ask(body.question.strip(), collection=body.collection, top_k=body.top_k)


@router.get("/knowledge/status")
async def knowledge_base_status(
    tenant: Annotated[TenantContext, Depends(get_tenant)],
    collection: str = "org-knowledge",
) -> dict:
    kb = KnowledgeBaseService(tenant)
    return kb.stats(collection)


@router.post("/agents/org-knowledge-base/run", response_model=RunResponse)
async def run_org_knowledge_base(
    background_tasks: BackgroundTasks,
    body: KnowledgeBaseRunRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> RunResponse:
    key = _run_key(tenant.user_id, "org-knowledge-base")
    if _running.get(key):
        raise HTTPException(status_code=409, detail="Organization Knowledge Base is already running")

    agent = OrganizationKnowledgeBaseAgent(tenant)
    action = (body.action or "build").strip().lower()
    if action == "ask":
        result = await agent.run(
            action="ask",
            question=body.question,
            collection=body.collection,
            top_k=body.top_k,
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message", "Ask failed"))
        return RunResponse(agent_id="org-knowledge-base", status="completed", message=result.get("answer", "")[:200])

    sources = _normalize_kb_sources(body.sources, body.folder_path)

    background_tasks.add_task(
        _run_agent,
        key,
        agent.run(action="build", collection=body.collection, sources=sources, folder_path=body.folder_path),
        body.run_id,
    )
    return RunResponse(agent_id="org-knowledge-base", status="started", message="Building organization knowledge base")


@router.get("/queue")
async def list_result_queue(
    user: Annotated[dict, Depends(get_current_user)],
    limit: int = 50,
    agent_id: str | None = None,
) -> dict:
    items = list_results(user["id"], limit=min(limit, 100), agent_id=agent_id)
    return {"items": items, "count": len(items)}


@router.get("/queue/latest/{agent_id}")
async def latest_agent_result(
    agent_id: str,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    row = latest_for_agent(user["id"], agent_id)
    if not row:
        raise HTTPException(status_code=404, detail="No results for this agent yet")
    return row


@router.get("/queue/{result_id}")
async def get_queue_result(
    result_id: str,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    row = get_result(user["id"], result_id)
    if not row:
        raise HTTPException(status_code=404, detail="Result not found")
    return row


@router.delete("/queue")
async def clear_result_queue(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    deleted = clear_user_queue(user["id"])
    return {"deleted": deleted}


@router.get("/agents/status")
async def agents_status(user: Annotated[dict, Depends(get_current_user)]) -> dict[str, bool]:
    uid = user["id"]
    status = {
        "invoice-matcher": _running.get(_run_key(uid, "invoice-matcher"), False),
        "gmail-organizer": _running.get(_run_key(uid, "gmail-organizer"), False),
        "gmail-calendar": _running.get(_run_key(uid, "gmail-calendar"), False),
        "telecaller": _running.get(_run_key(uid, "telecaller"), False),
        "mailer": _running.get(_run_key(uid, "mailer"), False),
        "whatsapp": _running.get(_run_key(uid, "whatsapp"), False),
        "data-scraper": _running.get(_run_key(uid, "data-scraper"), False),
        "file-download": _running.get(_run_key(uid, "file-download"), False),
        "org-knowledge-base": _running.get(_run_key(uid, "org-knowledge-base"), False),
    }
    for agent_id in UNDERSTANDING_AGENTS:
        status[agent_id] = _running.get(_run_key(uid, agent_id), False)
    for agent_id in PERCEPTION_AGENTS:
        status[agent_id] = _running.get(_run_key(uid, agent_id), False)
    status["content-director"] = _running.get(_run_key(uid, "content-director"), False)
    for agent_id in CONTENT_AGENTS:
        if agent_id != "content-director":
            status[agent_id] = _running.get(_run_key(uid, agent_id), False)
    return status
