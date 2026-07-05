"""Tests for feedback_join_service — join SQL shape, identifier guards, triggers."""

from __future__ import annotations

import pytest

from services.feedback_join_service import FeedbackJoinError, FeedbackJoinService
from tests.test_approval_service import FakeState


class FeedbackFakeState(FakeState):
    """FakeState variant returning canned rows per statement kind."""

    def __init__(self):
        super().__init__()
        self.select_rows: list[dict] = []
        self.merge_rows: list[dict] = [{"num_inserted_rows": 3}]

    def _exec(self, sql: str, params: dict | None = None):
        self.execs.append((sql, params))
        stripped = sql.strip().upper()
        if stripped.startswith("MERGE"):
            return self.merge_rows
        if stripped.startswith("SELECT"):
            return self.select_rows
        return []


@pytest.fixture
def state() -> FeedbackFakeState:
    return FeedbackFakeState()


@pytest.fixture
def svc(state) -> FeedbackJoinService:
    return FeedbackJoinService(state=state)


def _join(svc, **overrides) -> int:
    kwargs = {
        "project_id": "p1",
        "inference_table": "retention_churn_prod.monitoring.inference_log_payload",
        "label_source_table": "retention_churn_prod.ml.churn_outcomes",
        "label_source_column": "churned",
        "prediction_column": "prediction",
    }
    kwargs.update(overrides)
    return svc.join_new_labels(**kwargs)


class TestJoinNewLabels:
    def test_merge_keyed_by_client_request_id(self, svc, state):
        inserted = _join(svc)

        assert inserted == 3
        sql, params = state.execs[0]
        assert "MERGE INTO label_feedback" in sql
        assert "l.client_request_id = i.client_request_id" in sql
        assert "WHEN NOT MATCHED THEN INSERT" in sql
        # No update branch — label feedback rows are immutable once joined
        assert "WHEN MATCHED" not in sql
        assert params["project_id"] == "p1"

    def test_custom_join_key(self, svc, state):
        _join(svc, label_join_key="request_uuid")
        sql, _ = state.execs[0]
        assert "l.request_uuid = i.client_request_id" in sql

    @pytest.mark.parametrize(
        "field,value",
        [
            ("inference_table", "bad; DROP TABLE x"),
            ("label_source_table", "cat.schema.tbl.extra.part"),
            ("label_source_column", "col--"),
            ("prediction_column", "p col"),
        ],
    )
    def test_unsafe_identifiers_fail_closed(self, svc, field, value):
        with pytest.raises(FeedbackJoinError, match="Unsafe"):
            _join(svc, **{field: value})

    def test_zero_when_no_result(self, svc, state):
        state.merge_rows = []
        assert _join(svc) == 0


class TestLiveAccuracy:
    def test_no_labels_returns_none(self, svc, state):
        state.select_rows = [{"live_accuracy": None, "labels_count": 0}]
        acc, count = svc.compute_live_accuracy("p1")
        assert acc is None
        assert count == 0

    def test_accuracy_and_count(self, svc, state):
        state.select_rows = [{"live_accuracy": "0.91", "labels_count": "200"}]
        acc, count = svc.compute_live_accuracy("p1", window_days=7)
        assert acc == pytest.approx(0.91)
        assert count == 200

    def test_record_inserts_performance_row(self, svc, state):
        state.select_rows = [{"live_accuracy": "0.88", "labels_count": "50"}]
        acc = svc.record_live_accuracy(project_id="p1", model_id="m1", version_id="v1", window_days=30)
        assert acc == pytest.approx(0.88)
        sql, params = state.execs[-1]
        assert "INSERT INTO model_performance" in sql
        assert params["live_accuracy"] == pytest.approx(0.88)
        assert params["labels_count"] == 50
        assert params["window"] == "last_30d"

    def test_record_skips_insert_without_labels(self, svc, state):
        state.select_rows = [{"live_accuracy": None, "labels_count": 0}]
        acc = svc.record_live_accuracy(project_id="p1", model_id="m1", version_id="v1")
        assert acc is None
        assert len(state.execs) == 1  # only the SELECT ran


class TestRetrainTrigger:
    def test_below_threshold_not_flagged(self, svc, state):
        state.select_rows = [{"new_labels": "40"}]
        flagged = svc.check_retrain_trigger(
            project_id="p1",
            last_training_timestamp="2026-06-01T00:00:00Z",
            new_labels_threshold=100,
        )
        assert flagged is False
        assert state.audits == []

    def test_threshold_reached_flags_audit(self, svc, state):
        state.select_rows = [{"new_labels": "150"}]
        flagged = svc.check_retrain_trigger(
            project_id="p1",
            last_training_timestamp="2026-06-01T00:00:00Z",
            new_labels_threshold=100,
        )
        assert flagged is True
        audit = state.audits[0]
        assert audit["action_type"] == "retrain_candidate_flagged"
        assert audit["change_details"]["new_labels_since_last_training"] == 150
