"""Tests for reconciliation_service — alias sync, cost merge, self-monitoring."""

from __future__ import annotations

import json

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
        state.rows_by_prefix["SELECT * FROM budget_alerts"] = []
        state.rows_by_prefix["SELECT p.project_id, mp.model_id"] = []
        results = svc.run_all()
        assert [r.job_name for r in results] == [
            "model_alias_reconcile",
            "cost_reconcile",
            "revalidation_check",
            "budget_alert_check",
            "performance_alert_check",
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


class FakeNotifications:
    def __init__(self):
        self.sent: list[tuple] = []

    def send(self, destination_config, subject, message):
        self.sent.append((destination_config, subject, message))
        return None

    def send_all(self, destination_configs, subject, message):
        return [self.send(dc, subject, message) for dc in destination_configs]


def _current_period_bucket(days_back: int) -> str:
    from datetime import UTC, datetime

    return str(datetime.now(UTC).toordinal() // days_back)


class TestBudgetAlerts:
    """§17.3 — budget_alerts was in the schema but never read or written."""

    def _budget(self, **overrides) -> dict:
        base = {
            "budget_id": "b1",
            "project_id": "p1",
            "budget_period": "monthly",
            "budget_threshold_usd": 1000.0,
            "alert_at_pct": 80.0,
            "enabled": True,
            "alert_recipients": ["mlops@co.com"],
            "last_alerted_period": None,
        }
        base.update(overrides)
        return base

    def test_no_budgets_is_a_no_op(self, cfg, state):
        state.rows_by_prefix["SELECT * FROM budget_alerts"] = []
        svc = ReconciliationService(state=state, notifications=FakeNotifications())

        result = svc.reconcile_budget_alerts()

        assert result.status == "ok"
        assert result.rows_examined == 0

    def test_under_threshold_no_notification(self, cfg, state):
        state.rows_by_prefix["SELECT * FROM budget_alerts"] = [self._budget()]
        state.rows_by_prefix["SELECT sum(total_cost_usd)"] = [{"total": 100.0}]  # 10% of 1000
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_budget_alerts()

        assert result.rows_changed == 0
        assert not notifications.sent

    def test_breach_sends_notification_and_marks_period(self, cfg, state):
        state.rows_by_prefix["SELECT * FROM budget_alerts"] = [self._budget()]
        state.rows_by_prefix["SELECT sum(total_cost_usd)"] = [{"total": 900.0}]  # 90% >= 80% alert_at_pct
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_budget_alerts()

        assert result.rows_changed == 1
        assert len(notifications.sent) == 1
        dest, subject, message = notifications.sent[0]
        assert dest == {"destination": "email", "email_addresses": ["mlops@co.com"]}
        assert "p1" in subject
        assert "$900.00" in message
        update_sql, update_params = next(e for e in state.execs if e[0].strip().startswith("UPDATE budget_alerts"))
        assert update_params["budget_id"] == "b1"

    def test_already_alerted_this_period_skips(self, cfg, state):
        period = _current_period_bucket(30)
        state.rows_by_prefix["SELECT * FROM budget_alerts"] = [self._budget(last_alerted_period=period)]
        state.rows_by_prefix["SELECT sum(total_cost_usd)"] = [{"total": 900.0}]
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_budget_alerts()

        assert result.rows_changed == 0
        assert not notifications.sent

    def test_no_recipients_still_marks_but_does_not_notify(self, cfg, state):
        state.rows_by_prefix["SELECT * FROM budget_alerts"] = [self._budget(alert_recipients=[])]
        state.rows_by_prefix["SELECT sum(total_cost_usd)"] = [{"total": 900.0}]
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_budget_alerts()

        assert result.rows_changed == 1
        assert not notifications.sent

    def test_zero_threshold_skipped(self, cfg, state):
        state.rows_by_prefix["SELECT * FROM budget_alerts"] = [self._budget(budget_threshold_usd=0.0)]
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_budget_alerts()

        assert result.rows_changed == 0
        assert not notifications.sent

    def test_failure_recorded_not_raised(self, cfg, state):
        class ExplodingState(ReconFakeState):
            def _exec(self, sql, params=None):
                if sql.strip().startswith("SELECT * FROM budget_alerts"):
                    raise RuntimeError("budget_alerts unreachable")
                return super()._exec(sql, params)

        svc = ReconciliationService(state=ExplodingState(), notifications=FakeNotifications())

        result = svc.reconcile_budget_alerts()

        assert result.status == "failed"
        assert "unreachable" in result.detail


class TestPerformanceAlerts:
    """§13/§14.1 — alert_history was read by the dashboard but nothing ever
    wrote to it; no breach ever reached a human."""

    _DEST = {"destination": "email", "email_addresses": ["mlops@co.com"]}

    def _degraded_row(self, **overrides) -> dict:
        base = {"project_id": "p1", "model_id": "m1", "degradation_pct": 15.0}
        base.update(overrides)
        return base

    def _config_row(self, threshold=10.0, destinations=None) -> dict:
        return {
            "interview_responses": json.dumps(
                {
                    "performance_alert_threshold_pct": threshold,
                    "alert_destination_configs": destinations if destinations is not None else [self._DEST],
                }
            )
        }

    def test_breach_triggers_alert_and_notification(self, cfg, state):
        state.rows_by_prefix["SELECT p.project_id, mp.model_id"] = [self._degraded_row()]
        state.rows_by_prefix["SELECT interview_responses"] = [self._config_row()]
        state.rows_by_prefix["SELECT max(triggered_timestamp)"] = [{"last_fired": None}]
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_performance_alerts()

        assert result.rows_changed == 1
        assert len(notifications.sent) == 1
        dest, subject, message = notifications.sent[0]
        assert dest == self._DEST
        assert "m1" in subject
        assert "15.0%" in message
        insert_sql, insert_params = next(e for e in state.execs if e[0].strip().startswith("INSERT INTO alert_history"))
        assert insert_params["model_id"] == "m1"
        assert insert_params["alert_value"] == 15.0

    def test_under_threshold_no_alert(self, cfg, state):
        state.rows_by_prefix["SELECT p.project_id, mp.model_id"] = [self._degraded_row(degradation_pct=5.0)]
        state.rows_by_prefix["SELECT interview_responses"] = [self._config_row(threshold=10.0)]
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_performance_alerts()

        assert result.rows_changed == 0
        assert not notifications.sent

    def test_recently_fired_dedups(self, cfg, state):
        from datetime import UTC, datetime

        state.rows_by_prefix["SELECT p.project_id, mp.model_id"] = [self._degraded_row()]
        state.rows_by_prefix["SELECT interview_responses"] = [self._config_row()]
        state.rows_by_prefix["SELECT max(triggered_timestamp)"] = [{"last_fired": datetime.now(UTC).isoformat()}]
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_performance_alerts()

        assert result.rows_changed == 0
        assert not notifications.sent

    def test_no_config_skips(self, cfg, state):
        state.rows_by_prefix["SELECT p.project_id, mp.model_id"] = [self._degraded_row()]
        state.rows_by_prefix["SELECT interview_responses"] = []
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_performance_alerts()

        assert result.rows_changed == 0
        assert not notifications.sent

    def test_no_destinations_skips(self, cfg, state):
        state.rows_by_prefix["SELECT p.project_id, mp.model_id"] = [self._degraded_row()]
        state.rows_by_prefix["SELECT interview_responses"] = [self._config_row(destinations=[])]
        notifications = FakeNotifications()
        svc = ReconciliationService(state=state, notifications=notifications)

        result = svc.reconcile_performance_alerts()

        assert result.rows_changed == 0
        assert not notifications.sent

    def test_failure_recorded_not_raised(self, cfg, state):
        class ExplodingState(ReconFakeState):
            def _exec(self, sql, params=None):
                if sql.strip().startswith("SELECT p.project_id, mp.model_id"):
                    raise RuntimeError("model_performance unreachable")
                return super()._exec(sql, params)

        svc = ReconciliationService(state=ExplodingState(), notifications=FakeNotifications())

        result = svc.reconcile_performance_alerts()

        assert result.status == "failed"
        assert "unreachable" in result.detail
