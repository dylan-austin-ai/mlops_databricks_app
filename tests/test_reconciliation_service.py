"""Tests for reconciliation_service — alias sync, cost merge, self-monitoring."""

from __future__ import annotations

import pytest

from config import AppConfig
from services.reconciliation_service import ReconciliationService
from services.registry_service import RegistryService
from tests.test_approval_service import FakeState
from tests.test_registry_service import FakeMlflowClient


class ReconFakeState(FakeState):
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


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
    )


@pytest.fixture
def state() -> ReconFakeState:
    return ReconFakeState()


@pytest.fixture
def client() -> FakeMlflowClient:
    return FakeMlflowClient()


@pytest.fixture
def svc(cfg, state, client) -> ReconciliationService:
    registry = RegistryService(config=cfg, client=client)
    return ReconciliationService(state=state, registry=registry)


MODEL = "retention_churn_prod.ml.churn"


class TestAliasReconcile:
    def test_syncs_aliases_from_registry(self, svc, state, client):
        state.rows_by_prefix["SELECT DISTINCT uc_full_name"] = [{"uc_full_name": MODEL}]
        client.set_registered_model_alias(MODEL, "champion", 2)
        client.set_registered_model_alias(MODEL, "challenger", 3)

        result = svc.reconcile_model_aliases()

        assert result.status == "ok"
        assert result.rows_examined == 1
        assert result.rows_changed == 2  # two versions updated
        updates = [s for s, _ in state.execs if s.strip().startswith("UPDATE")]
        # First a clearing pass, then one per aliased version
        assert len(updates) == 3
        assert any("array('champion')" in s for s in updates)
        assert any("array('challenger')" in s for s in updates)
        # Health signal always written (§21.1)
        insert_sql, insert_params = state.execs[-1]
        assert "reconciliation_runs" in insert_sql
        assert insert_params["status"] == "ok"

    def test_registry_failure_recorded_not_raised(self, cfg, state):
        class ExplodingRegistry:
            def alias_map(self, name):
                raise RuntimeError("registry unreachable")

        state.rows_by_prefix["SELECT DISTINCT uc_full_name"] = [{"uc_full_name": MODEL}]
        svc = ReconciliationService(state=state, registry=ExplodingRegistry())

        result = svc.reconcile_model_aliases()

        assert result.status == "failed"
        assert "unreachable" in result.detail
        _, params = state.execs[-1]
        assert params["status"] == "failed"

    def test_unsafe_alias_name_fails_closed(self, svc, state, client):
        state.rows_by_prefix["SELECT DISTINCT uc_full_name"] = [{"uc_full_name": MODEL}]
        client.aliases[MODEL] = {"bad'alias": 1}

        result = svc.reconcile_model_aliases()

        assert result.status == "failed"
        assert "Unsafe alias" in result.detail


class TestSelfMonitoring:
    def test_zero_change_after_active_history_warns(self, svc, state):
        # No models to reconcile this run…
        state.rows_by_prefix["SELECT DISTINCT uc_full_name"] = []
        # …but the previous run changed rows
        state.rows_by_prefix["SELECT rows_changed"] = [{"rows_changed": "5"}]

        result = svc.reconcile_model_aliases()

        assert result.status == "warning"
        assert "possible upstream schema change" in result.detail

    def test_zero_change_with_no_history_is_ok(self, svc, state):
        state.rows_by_prefix["SELECT DISTINCT uc_full_name"] = []
        state.rows_by_prefix["SELECT rows_changed"] = []

        result = svc.reconcile_model_aliases()

        assert result.status == "ok"


class TestCostReconcile:
    def test_merge_joins_billing_and_prices(self, svc, state):
        state.rows_by_prefix["MERGE"] = [{"num_inserted_rows": 4, "num_updated_rows": 2}]

        result = svc.reconcile_costs(days_back=7)

        assert result.status == "ok"
        assert result.rows_changed == 6
        merge_sql, params = state.execs[0]
        assert "system.billing.usage" in merge_sql
        assert "system.billing.list_prices" in merge_sql
        assert "custom_tags['project_id']" in merge_sql
        assert params["days_back"] == 7

    def test_run_all_returns_all_passes(self, svc, state):
        state.rows_by_prefix["SELECT DISTINCT uc_full_name"] = []
        state.rows_by_prefix["SELECT DISTINCT p.project_id"] = []
        results = svc.run_all()
        assert [r.job_name for r in results] == [
            "model_alias_reconcile",
            "cost_reconcile",
            "revalidation_check",
        ]


# ── §20.5: revalidation trigger ──────────────────────────────────────────────


class PolicyStub:
    def __init__(self, tier_rows=None, raise_exc=None):
        self.tier_rows = tier_rows or []
        self.raise_exc = raise_exc

    def tier_rows_for_project(self, project_id):
        if self.raise_exc:
            raise self.raise_exc
        return self.tier_rows


def _reval_svc(cfg, state, client, tier_rows=None, raise_exc=None) -> ReconciliationService:
    registry = RegistryService(config=cfg, client=client)
    return ReconciliationService(state=state, registry=registry, policy=PolicyStub(tier_rows, raise_exc))


def _promoted(client, days_ago: int, version: int = 2):
    from datetime import UTC, datetime, timedelta

    client.set_registered_model_alias(MODEL, "champion", version)
    client.set_model_version_tag(
        MODEL,
        str(version),
        "promoted_timestamp",
        (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(),
    )


class TestRevalidationCheck:
    TIER_ROWS = [
        {"revalidation_frequency_days": 365, "on_revalidation_due": "warn"},
        {"revalidation_frequency_days": 180, "on_revalidation_due": "block_new_traffic"},
    ]

    def _candidates(self, state):
        state.rows_by_prefix["SELECT DISTINCT p.project_id"] = [{"project_id": "p1", "uc_full_name": MODEL}]

    def test_lapsed_window_flags_due_with_strictest_action(self, cfg, state, client):
        self._candidates(state)
        _promoted(client, days_ago=400)
        svc = _reval_svc(cfg, state, client, tier_rows=self.TIER_ROWS)

        result = svc.reconcile_revalidation()

        assert result.status == "ok" and result.rows_changed == 1
        merge_sql, params = next((s, p) for s, p in state.execs if s.strip().startswith("MERGE"))
        assert "revalidation_flags" in merge_sql
        assert params["action"] == "block_new_traffic"  # both windows lapsed → strictest
        assert params["frequency_days"] == 180
        assert params["champion_version"] == 2

    def test_within_window_does_not_flag(self, cfg, state, client):
        self._candidates(state)
        _promoted(client, days_ago=30)
        svc = _reval_svc(cfg, state, client, tier_rows=self.TIER_ROWS)

        result = svc.reconcile_revalidation()

        assert result.status == "ok" and result.rows_changed == 0
        assert not any(s.strip().startswith("MERGE") for s, _ in state.execs)

    def test_missing_promoted_timestamp_fails_closed(self, cfg, state, client):
        self._candidates(state)
        client.set_registered_model_alias(MODEL, "champion", 2)  # no §7.4 tags
        svc = _reval_svc(cfg, state, client, tier_rows=self.TIER_ROWS)

        result = svc.reconcile_revalidation()

        assert result.rows_changed == 1  # unknown provenance is flagged, not skipped
        _, params = next((s, p) for s, p in state.execs if s.strip().startswith("MERGE"))
        assert params["promoted_at"] is None

    def test_already_flagged_is_not_reflagged(self, cfg, state, client):
        self._candidates(state)
        state.rows_by_prefix["SELECT status, cleared_timestamp"] = [{"status": "due", "cleared_timestamp": None}]
        _promoted(client, days_ago=400)
        svc = _reval_svc(cfg, state, client, tier_rows=self.TIER_ROWS)

        result = svc.reconcile_revalidation()

        assert result.rows_changed == 0
        assert not any(s.strip().startswith("MERGE") for s, _ in state.execs)

    def test_repromotion_clears_stale_due_flag(self, cfg, state, client):
        self._candidates(state)
        state.rows_by_prefix["SELECT status, cleared_timestamp"] = [{"status": "due", "cleared_timestamp": None}]
        _promoted(client, days_ago=10)  # fresh champion — window no longer lapsed
        svc = _reval_svc(cfg, state, client, tier_rows=self.TIER_ROWS)

        result = svc.reconcile_revalidation()

        assert result.rows_changed == 1
        assert any("'cleared'" in s for s, _ in state.execs)

    def test_cleared_flag_resets_the_clock(self, cfg, state, client):
        # promoted 400d ago but re-reviewed (cleared) recently — not re-flagged
        from datetime import UTC, datetime, timedelta

        self._candidates(state)
        state.rows_by_prefix["SELECT status, cleared_timestamp"] = [
            {
                "status": "cleared",
                "cleared_timestamp": (datetime.now(UTC) - timedelta(days=5)).isoformat(),
            }
        ]
        _promoted(client, days_ago=400)
        svc = _reval_svc(cfg, state, client, tier_rows=self.TIER_ROWS)

        result = svc.reconcile_revalidation()

        assert result.rows_changed == 0
        assert not any(s.strip().startswith("MERGE") for s, _ in state.execs)

    def test_policy_failure_recorded_not_raised(self, cfg, state, client):
        self._candidates(state)
        svc = _reval_svc(cfg, state, client, raise_exc=RuntimeError("packs table missing"))

        result = svc.reconcile_revalidation()

        assert result.status == "failed"
        assert "packs table missing" in result.detail
