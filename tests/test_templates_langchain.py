"""Tests for template packages and LangChain availability."""

import json

import pytest

from app.models.template_package import TEMPLATE_SCHEMA, TemplatePackage
from app.services.template_catalog import get_builtin_template, list_builtin_summaries, validate_template_payload
from app.services.template_store import install_template, list_installed, load_installed
from app.services.tenant import TenantContext


def test_builtin_templates_catalog() -> None:
    summaries = list_builtin_summaries()
    assert len(summaries) >= 6
    assert any(t["id"] == "creator-os" for t in summaries)


def test_template_package_roundtrip() -> None:
    src = get_builtin_template("email-organization")
    assert src is not None
    exported = src.to_export_dict()
    assert exported["schema"] == TEMPLATE_SCHEMA
    pkg = validate_template_payload(exported)
    assert pkg.name == src.name
    assert len(pkg.nodes) == len(src.nodes)


def test_install_template_to_tenant_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path / "data")
    monkeypatch.setattr("app.config.settings.tenants_dir", tmp_path / "data" / "tenants")

    tenant = TenantContext(user_id="u1", email="u1@test.com", name="User")
    pkg = get_builtin_template("support-callbacks")
    assert pkg is not None
    path = install_template(tenant, pkg)
    assert path.exists()
    loaded = load_installed(tenant, "support-callbacks")
    assert loaded is not None
    assert loaded.id == "support-callbacks"
    installed = list_installed(tenant)
    assert any(t["id"] == "support-callbacks" for t in installed)


def test_langchain_available_flag() -> None:
    from app.services.langchain_llm import langchain_available

    # True when deps installed in dev env, False otherwise — just ensure callable
    assert isinstance(langchain_available(), bool)
