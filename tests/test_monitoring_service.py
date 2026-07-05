"""Tests for monitoring_service — attach idempotency, label upgrade, degradation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import AppConfig
from services.monitoring_service import (
    MonitoringService,
    MonitoringServiceError,
    MonitoringUnavailable,
)

TABLE = "retention_churn_prod.monitoring.inference_log_payload"


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
    )


class FakeQualityMonitors:
    def __init__(self):
        self.monitors: dict[str, SimpleNamespace] = {}
        self.create_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.raise_on_create: Exception | None = None

    def create(self, **kwargs):
        if self.raise_on_create:
            raise self.raise_on_create
        self.create_calls.append(kwargs)
        info = SimpleNamespace(
            table_name=kwargs["table_name"],
            status="MONITOR_STATUS_ACTIVE",
            dashboard_id="dash1",
            output_schema_name=kwargs["output_schema_name"],
            inference_log=kwargs["inference_log"],
        )
        self.monitors[kwargs["table_name"]] = info
        return info

    def get(self, table_name):
        if table_name not in self.monitors:
            raise RuntimeError(f"Table monitor {table_name} does not exist (404)")
        return self.monitors[table_name]

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        self.monitors[kwargs["table_name"]].inference_log = kwargs["inference_log"]

    def delete(self, table_name):
        if table_name not in self.monitors:
            raise RuntimeError("not found")
        del self.monitors[table_name]


@pytest.fixture
def qm() -> FakeQualityMonitors:
    return FakeQualityMonitors()


@pytest.fixture
def svc(cfg, qm) -> MonitoringService:
    return MonitoringService(config=cfg, ws=SimpleNamespace(quality_monitors=qm))


def _attach(svc, **overrides):
    kwargs = {
        "inference_table": TABLE,
        "output_schema": "retention_churn_prod.monitoring",
        "prediction_col": "prediction",
        "slicing_exprs": ["age_bucket", "gender"],
    }
    kwargs.update(overrides)
    return svc.attach_inference_monitor(**kwargs)


class TestAttach:
    def test_creates_inference_log_monitor(self, svc, qm):
        handle = _attach(svc)

        assert handle.already_existed is False
        assert handle.dashboard_id == "dash1"
        call = qm.create_calls[0]
        log = call["inference_log"]
        assert log.prediction_col == "prediction"
        assert log.timestamp_col == "request_time"
        assert log.model_id_col == "model_id"
        assert "CLASSIFICATION" in str(log.problem_type)
        # Fairness attributes travel as slicing columns (§13)
        assert call["slicing_exprs"] == ["age_bucket", "gender"]

    def test_attach_is_idempotent(self, svc, qm):
        _attach(svc)
        handle = _attach(svc)

        assert handle.already_existed is True
        assert len(qm.create_calls) == 1  # never recreated

    def test_regression_problem_type(self, svc, qm):
        _attach(svc, problem_type="regression")
        assert "REGRESSION" in str(qm.create_calls[0]["inference_log"].problem_type)

    def test_feature_disabled_raises_unavailable(self, svc, qm):
        qm.raise_on_create = RuntimeError("Lakehouse Monitoring is not enabled for this workspace")
        with pytest.raises(MonitoringUnavailable, match="disables monitoring affordances"):
            _attach(svc)

    def test_other_errors_are_not_masked_as_unavailable(self, svc, qm):
        qm.raise_on_create = RuntimeError("invalid prediction_col: no such column")
        with pytest.raises(MonitoringServiceError):
            _attach(svc)


class TestStatusAndLabel:
    def test_status_none_when_absent(self, svc):
        assert svc.monitor_status(TABLE) is None

    def test_status_reports_label_col(self, svc):
        _attach(svc, label_col="actual")
        status = svc.monitor_status(TABLE)
        assert status["label_col"] == "actual"
        assert status["status"] == "MONITOR_STATUS_ACTIVE"

    def test_attach_label_column_updates_monitor(self, svc, qm):
        _attach(svc)  # no label at deploy time
        svc.attach_label_column(TABLE, "actual_label")

        assert qm.update_calls[0]["inference_log"].label_col == "actual_label"
        assert svc.monitor_status(TABLE)["label_col"] == "actual_label"

    def test_attach_label_column_idempotent(self, svc, qm):
        _attach(svc, label_col="actual_label")
        svc.attach_label_column(TABLE, "actual_label")
        assert qm.update_calls == []  # already set — no update issued


class TestDelete:
    def test_delete_removes_monitor(self, svc, qm):
        _attach(svc)
        svc.delete_monitor(TABLE)
        assert TABLE not in qm.monitors

    def test_delete_missing_is_noop(self, svc):
        svc.delete_monitor(TABLE)  # §21.2 retirement must be re-runnable
