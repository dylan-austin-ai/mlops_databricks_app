"""Tests for QaCleanupService — non-essential QA/dev endpoint + scratch
table reaper (owner request 2026-07-13). The critical property: the
bundle-managed endpoint name and any non-scratch-prefixed table must never
be deleted, no matter what else is present.
"""

from __future__ import annotations

from types import SimpleNamespace

from config import AppConfig
from services.qa_cleanup_service import QaCleanupService


class FakeServingEndpointsAPI:
    def __init__(self, endpoints: list[str]):
        self._endpoints = [SimpleNamespace(name=n) for n in endpoints]
        self.delete_calls: list[str] = []

    def list(self):
        return iter(self._endpoints)

    def delete(self, name: str):
        self.delete_calls.append(name)


class FakeTablesAPI:
    def __init__(self, tables: list[str]):
        self._tables = [SimpleNamespace(name=n) for n in tables]

    def list(self, catalog_name, schema_name, **kwargs):
        return iter(self._tables)


class FakeWorkspaceClient:
    def __init__(self, endpoints: list[str], tables: list[str]):
        self.serving_endpoints = FakeServingEndpointsAPI(endpoints)
        self.tables = FakeTablesAPI(tables)


def _cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com", databricks_token="dapi-test", warehouse_id="wh123"
    )


def _svc(endpoints, tables, monkeypatch, drop_calls=None):
    svc = QaCleanupService(_cfg())
    fake_ws = FakeWorkspaceClient(endpoints, tables)
    svc._ws = fake_ws
    if drop_calls is not None:
        monkeypatch.setattr(svc, "_exec_drop", lambda path: drop_calls.append(path))
    return svc, fake_ws


class TestFindNonEssentialEndpoints:
    def test_never_flags_bundle_managed_endpoints(self, monkeypatch):
        svc, _ = _svc(["proj-dev", "proj-staging", "proj-prod"], [], monkeypatch)
        assert svc.find_non_essential_endpoints("proj") == []

    def test_flags_project_prefixed_scratch_endpoints(self, monkeypatch):
        svc, _ = _svc(["proj-dev", "proj_v25", "proj_test_endpoint"], [], monkeypatch)
        candidates = svc.find_non_essential_endpoints("proj")
        assert set(candidates) == {"proj_v25", "proj_test_endpoint"}

    def test_ignores_unrelated_projects_endpoints(self, monkeypatch):
        svc, _ = _svc(["proj-dev", "other_project_v1"], [], monkeypatch)
        assert svc.find_non_essential_endpoints("proj") == []


class TestFindScratchTables:
    def test_only_flags_explicit_scratch_prefixes(self, monkeypatch):
        svc, _ = _svc([], ["zz_probe", "scratch_eda", "tmp_join", "real_training_table"], monkeypatch)
        candidates = svc.find_scratch_tables("cat.proj_dev")
        assert set(candidates) == {"cat.proj_dev.zz_probe", "cat.proj_dev.scratch_eda", "cat.proj_dev.tmp_join"}

    def test_never_flags_non_prefixed_tables(self, monkeypatch):
        svc, _ = _svc([], ["customer_features", "training_data_snapshots"], monkeypatch)
        assert svc.find_scratch_tables("cat.proj_dev") == []


class TestCleanupNonEssential:
    def test_deletes_flagged_endpoints_and_tables(self, monkeypatch):
        drop_calls: list[str] = []
        svc, fake_ws = _svc(["proj-dev", "proj_v25"], ["zz_probe", "real_table"], monkeypatch, drop_calls=drop_calls)

        results = svc.cleanup_non_essential("proj", ["cat.proj_dev"])

        assert fake_ws.serving_endpoints.delete_calls == ["proj_v25"]
        assert drop_calls == ["cat.proj_dev.zz_probe"]
        statuses = {r["resource"]: r["status"] for r in results}
        assert statuses["endpoint:proj_v25"] == "deleted"
        assert statuses["table:cat.proj_dev.zz_probe"] == "deleted"
        assert "table:cat.proj_dev.real_table" not in statuses  # never even considered

    def test_one_failure_does_not_block_others(self, monkeypatch):
        svc, fake_ws = _svc(["proj_v25", "proj_v26"], [], monkeypatch)

        def flaky_delete(name):
            if name == "proj_v25":
                raise RuntimeError("endpoint busy")
            fake_ws.serving_endpoints.delete_calls.append(name)

        fake_ws.serving_endpoints.delete = flaky_delete

        results = svc.cleanup_non_essential("proj", [])

        statuses = {r["resource"]: r["status"] for r in results}
        assert statuses["endpoint:proj_v25"] == "failed"
        assert statuses["endpoint:proj_v26"] == "deleted"
