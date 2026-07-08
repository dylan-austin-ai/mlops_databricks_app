"""Tests for capacity_service — workspace pressure snapshot + control-plane budget."""

from __future__ import annotations

import pytest

from config import AppConfig
from services.capacity_service import CapacityService
from tests.test_approval_service import FakeState


class CapacityFakeState(FakeState):
    def __init__(self):
        super().__init__()
        self.rows_by_prefix: dict[str, list[dict]] = {}

    def _exec(self, sql: str, params: dict | None = None):
        self.execs.append((sql, params))
        stripped = sql.strip()
        for prefix, rows in self.rows_by_prefix.items():
            if stripped.startswith(prefix):
                return rows
        if stripped.upper().startswith("MERGE"):
            return self.rows_by_prefix.get("MERGE", [])
        return []


class FakeJobs:
    def __init__(self, jobs=None, active_runs=None):
        self._jobs = jobs or []
        self._active_runs = active_runs or []

    def list(self):
        return iter(self._jobs)

    def list_runs(self, active_only=False):
        return iter(self._active_runs)


class FakeServingEndpoints:
    def __init__(self, endpoints=None):
        self._endpoints = endpoints or []

    def list(self):
        return iter(self._endpoints)


class FakeWs:
    def __init__(self, job_count=0, endpoint_count=0, active_run_count=0):
        self.jobs = FakeJobs(jobs=list(range(job_count)), active_runs=list(range(active_run_count)))
        self.serving_endpoints = FakeServingEndpoints(endpoints=list(range(endpoint_count)))


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
        control_plane_budget_warn_usd=50.0,
        control_plane_budget_crit_usd=100.0,
        capacity_endpoint_warn_threshold=50,
    )


@pytest.fixture
def state() -> CapacityFakeState:
    return CapacityFakeState()


class TestSnapshotCapacity:
    def test_under_threshold_is_ok(self, cfg, state):
        ws = FakeWs(job_count=10, endpoint_count=5, active_run_count=2)
        svc = CapacityService(config=cfg, state=state, ws=ws)

        snapshot = svc.snapshot_capacity()

        assert snapshot.job_count == 10
        assert snapshot.endpoint_count == 5
        assert snapshot.concurrent_run_count == 2
        assert snapshot.endpoint_warn_threshold == 50
        assert snapshot.status == "ok"
        assert snapshot.detail == ""

        insert_sql, params = state.execs[-1]
        assert "capacity_snapshots" in insert_sql
        assert params["status"] == "ok"
        assert params["endpoint_count"] == 5

    def test_at_threshold_warns(self, cfg, state):
        ws = FakeWs(job_count=3, endpoint_count=50, active_run_count=0)
        svc = CapacityService(config=cfg, state=state, ws=ws)

        snapshot = svc.snapshot_capacity()

        assert snapshot.status == "warning"
        assert "50" in snapshot.detail
        _, params = state.execs[-1]
        assert params["status"] == "warning"

    def test_over_threshold_warns(self, cfg, state):
        ws = FakeWs(job_count=3, endpoint_count=75, active_run_count=0)
        svc = CapacityService(config=cfg, state=state, ws=ws)

        snapshot = svc.snapshot_capacity()

        assert snapshot.status == "warning"


class TestLatestCapacitySnapshot:
    def test_returns_none_when_empty(self, cfg, state):
        svc = CapacityService(config=cfg, state=state)
        assert svc.latest_capacity_snapshot() is None

    def test_reads_most_recent_row(self, cfg, state):
        state.rows_by_prefix["SELECT job_count"] = [
            {
                "job_count": "12",
                "endpoint_count": "6",
                "concurrent_run_count": "1",
                "endpoint_warn_threshold": "50",
                "status": "ok",
                "detail": "",
            }
        ]
        svc = CapacityService(config=cfg, state=state)

        snapshot = svc.latest_capacity_snapshot()

        assert snapshot.job_count == 12
        assert snapshot.endpoint_count == 6
        assert snapshot.status == "ok"


class TestControlPlaneCostReconcile:
    def test_merge_tags_component_control_plane(self, cfg, state):
        state.rows_by_prefix["MERGE"] = [{"num_inserted_rows": 3, "num_updated_rows": 1}]
        svc = CapacityService(config=cfg, state=state)

        changed = svc.reconcile_control_plane_cost(days_back=14)

        assert changed == 4
        merge_sql, params = state.execs[0]
        assert "system.billing.usage" in merge_sql
        assert "component'] = 'control_plane'" in merge_sql
        assert "control_plane_costs" in merge_sql
        assert params["days_back"] == 14


class TestControlPlaneBudgetStatus:
    def test_under_warn_is_ok(self, cfg, state):
        state.rows_by_prefix["SELECT sum(total_cost_usd)"] = [{"total": "10.0"}]
        svc = CapacityService(config=cfg, state=state)

        status = svc.control_plane_budget_status()

        assert status.status == "ok"
        assert status.total_cost_usd == 10.0
        assert status.warn_threshold_usd == 50.0
        assert status.crit_threshold_usd == 100.0
        assert status.is_placeholder is True

    def test_at_warn_threshold_warns(self, cfg, state):
        state.rows_by_prefix["SELECT sum(total_cost_usd)"] = [{"total": "50.0"}]
        svc = CapacityService(config=cfg, state=state)

        assert svc.control_plane_budget_status().status == "warning"

    def test_at_crit_threshold_is_critical(self, cfg, state):
        state.rows_by_prefix["SELECT sum(total_cost_usd)"] = [{"total": "150.0"}]
        svc = CapacityService(config=cfg, state=state)

        assert svc.control_plane_budget_status().status == "critical"

    def test_no_rows_is_zero_and_ok(self, cfg, state):
        svc = CapacityService(config=cfg, state=state)

        status = svc.control_plane_budget_status()

        assert status.total_cost_usd == 0.0
        assert status.status == "ok"
