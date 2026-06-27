"""Persist installed workflow templates on the user's local tenant directory."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.models.template_package import TemplatePackage
from app.services.template_catalog import validate_template_payload
from app.services.tenant import TenantContext

_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def _templates_dir(tenant: TenantContext) -> Path:
    path = tenant.root / "templates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(template_id: str) -> str:
    cleaned = _SAFE_ID.sub("-", template_id.strip()).strip("-") or "template"
    return f"{cleaned}.agent-template.json"


def install_template(tenant: TenantContext, package: TemplatePackage) -> Path:
    tenant.ensure_dirs()
    dest = _templates_dir(tenant) / _safe_filename(package.id)
    dest.write_text(json.dumps(package.to_export_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def list_installed(tenant: TenantContext) -> list[dict]:
    tenant.ensure_dirs()
    out: list[dict] = []
    for path in sorted(_templates_dir(tenant).glob("*.agent-template.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pkg = validate_template_payload(data)
            out.append({
                "id": pkg.id,
                "name": pkg.name,
                "task": pkg.task,
                "stars": pkg.meta.get("stars", 4),
                "builtin": False,
                "installed": True,
                "node_count": len(pkg.nodes),
                "path": str(path.relative_to(tenant.root)),
            })
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def load_installed(tenant: TenantContext, template_id: str) -> TemplatePackage | None:
    tenant.ensure_dirs()
    for path in _templates_dir(tenant).glob("*.agent-template.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pkg = validate_template_payload(data)
            if pkg.id == template_id:
                return pkg
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def delete_installed(tenant: TenantContext, template_id: str) -> bool:
    tenant.ensure_dirs()
    for path in _templates_dir(tenant).glob("*.agent-template.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if str(data.get("id")) == template_id:
                path.unlink(missing_ok=True)
                return True
        except json.JSONDecodeError:
            continue
    return False
