"""Template download, install, and catalog API."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import get_current_user, get_tenant
from app.models.template_package import TemplatePackage
from app.services.template_catalog import get_builtin_template, list_builtin_summaries, validate_template_payload
from app.services.template_store import delete_installed, install_template, list_installed, load_installed
from app.services.tenant import TenantContext

router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateInstallRequest(BaseModel):
    package: dict[str, Any]


@router.get("")
async def list_templates(
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, Any]:
    builtin = list_builtin_summaries()
    installed = list_installed(tenant)
    seen = {t["id"] for t in installed}
    merged = installed + [t for t in builtin if t["id"] not in seen]
    return {"templates": merged, "builtin_count": len(builtin), "installed_count": len(installed)}


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, Any]:
    pkg = load_installed(tenant, template_id) or get_builtin_template(template_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Template not found")
    return pkg.to_export_dict()


@router.get("/{template_id}/download")
async def download_template(
    template_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> Response:
    pkg = load_installed(tenant, template_id) or get_builtin_template(template_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Template not found")
    body = json.dumps(pkg.to_export_dict(), indent=2, ensure_ascii=False)
    filename = f"{template_id}.agent-template.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/install")
async def install_template_route(
    body: TemplateInstallRequest,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
) -> dict[str, Any]:
    try:
        pkg = validate_template_payload(body.package)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not pkg.nodes:
        raise HTTPException(status_code=400, detail="Template must include at least one node")

    path = install_template(tenant, pkg)
    return {
        "status": "installed",
        "id": pkg.id,
        "name": pkg.name,
        "path": str(path.relative_to(tenant.root)),
    }


@router.delete("/{template_id}")
async def uninstall_template(
    template_id: str,
    tenant: Annotated[TenantContext, Depends(get_tenant)],
    user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    if get_builtin_template(template_id) and not load_installed(tenant, template_id):
        raise HTTPException(status_code=400, detail="Built-in templates cannot be uninstalled")
    deleted = delete_installed(tenant, template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Installed template not found")
    return {"status": "deleted", "id": template_id}
