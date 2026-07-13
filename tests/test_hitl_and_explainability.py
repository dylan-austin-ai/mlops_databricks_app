"""Tests for hitl_review_service and explainability_config (phase 8, §11/§12)."""

from __future__ import annotations

import json

import pytest

from services.explainability_config import (
    ExplainabilityConfigError,
    ExplainabilityItem,
    default_method,
    resolve,
)
from services.hitl_review_service import HITLReviewError, HITLReviewService
from tests.test_approval_service import FakeState


class HITLFakeState(FakeState):
    def __init__(self):
        super().__init__()
        self.rows_for: dict[str, list[dict]] = {}

    def _exec(self, sql: str, params: dict | None = None):
        self.execs.append((sql, params))
        stripped = " ".join(sql.split())
        if stripped.startswith("MERGE"):
            return [{"num_affected_rows": self.merge_affected}]
        for key, rows in self.rows_for.items():
            if key in stripped:
                return rows
        return []


@pytest.fixture
def state() -> HITLFakeState:
    return HITLFakeState()


@pytest.fixture
def svc(state) -> HITLReviewService:
    return HITLReviewService(state=state)


class TestHITLDecide:
    def test_decision_merge_guards_on_null_decision(self, svc, state):
        outcome = svc.decide(prediction_id="pred1", reviewer_email="r@co.com", decision="approved")

        assert outcome.recorded is True
        sql, params = state.execs[0]
        assert "t.decision IS NULL" in sql  # §11.2 concurrency guard
        assert params["decision"] == "approved"
        assert state.audits[0]["action_type"] == "hitl_approved"

    def test_second_reviewer_gets_already_decided(self, svc, state):
        state.merge_affected = 0
        state.rows_for["SELECT reviewer_email"] = [{"reviewer_email": "first@co.com", "decision": "approved"}]

        outcome = svc.decide(prediction_id="pred1", reviewer_email="second@co.com", decision="rejected")

        assert outcome.recorded is False
        assert "first@co.com" in outcome.reason
        assert state.audits == []

    def test_override_requires_value(self, svc):
        with pytest.raises(HITLReviewError, match="overridden_value"):
            svc.decide(prediction_id="p", reviewer_email="r@co.com", decision="overridden")

    def test_invalid_decision_rejected(self, svc):
        with pytest.raises(HITLReviewError, match="Invalid decision"):
            svc.decide(prediction_id="p", reviewer_email="r@co.com", decision="maybe")

    def test_unknown_prediction_raises(self, svc, state):
        state.merge_affected = 0
        state.rows_for["SELECT reviewer_email"] = []
        with pytest.raises(HITLReviewError, match="not in the review queue"):
            svc.decide(prediction_id="ghost", reviewer_email="r@co.com", decision="approved")

    def test_pending_joins_explanations(self, svc, state):
        state.rows_for["SELECT h.*"] = [{"prediction_id": "p1", "confidence_bucket": "low"}]
        rows = svc.pending("proj1")
        sql, params = state.execs[0]
        assert "telemetry_enrichment" in sql  # reviewer sees the why (§11.2)
        assert params["project_id"] == "proj1"
        assert rows[0]["confidence_bucket"] == "low"


class TestSLAEscalation:
    def test_breaches_escalated_and_audited_never_approved(self, svc, state):
        state.rows_for["SELECT prediction_id"] = [
            {"prediction_id": "p1"},
            {"prediction_id": "p2"},
        ]
        ids = svc.escalate_sla_breaches(sla_minutes=60, project_id="proj1")

        assert ids == ["p1", "p2"]
        update_sqls = [" ".join(s.split()) for s, _ in state.execs if s.strip().startswith("UPDATE")]
        assert any("SET escalated = true" in s for s in update_sqls)
        # No decision written anywhere — escalation is not approval (§29.3)
        assert not any("t.decision =" in s for s, _ in state.execs)
        assert all(a["action_type"] == "hitl_sla_escalated" for a in state.audits)

    def test_no_breaches_no_writes(self, svc, state):
        state.rows_for["SELECT prediction_id"] = []
        assert svc.escalate_sla_breaches(sla_minutes=60) == []
        assert len(state.execs) == 1  # only the SELECT


class FakeNotifications:
    def __init__(self):
        self.sent_all: list[tuple] = []

    def send_all(self, destination_configs, subject, message):
        self.sent_all.append((destination_configs, subject, message))
        return None


_DEST = {"destination": "slack", "channel_name": "#mlops-alerts"}


class TestSLAEscalationNotification:
    """IMG_1412 gap: escalation only ever wrote a DB row — no backup
    reviewer/MLOps was ever actually told."""

    def test_escalation_notifies_projects_configured_destinations(self, state):
        state.rows_for["SELECT prediction_id"] = [
            {"prediction_id": "p1", "project_id": "proj1"},
            {"prediction_id": "p2", "project_id": "proj1"},
        ]
        state.rows_for["SELECT interview_responses"] = [
            {"interview_responses": json.dumps({"alert_destination_configs": [_DEST]})}
        ]
        notifications = FakeNotifications()
        svc = HITLReviewService(state=state, notifications=notifications)

        ids = svc.escalate_sla_breaches(sla_minutes=60, project_id="proj1")

        assert ids == ["p1", "p2"]
        assert len(notifications.sent_all) == 1
        destinations, subject, message = notifications.sent_all[0]
        assert destinations == [_DEST]
        assert "2 prediction" in subject
        assert "p1" in message and "p2" in message
        assert "never auto-approved" in message

    def test_no_destinations_configured_skips_notification(self, state):
        state.rows_for["SELECT prediction_id"] = [{"prediction_id": "p1", "project_id": "proj1"}]
        state.rows_for["SELECT interview_responses"] = [
            {"interview_responses": json.dumps({"alert_destination_configs": []})}
        ]
        notifications = FakeNotifications()
        svc = HITLReviewService(state=state, notifications=notifications)

        svc.escalate_sla_breaches(sla_minutes=60, project_id="proj1")

        assert not notifications.sent_all

    def test_notification_failure_never_blocks_escalation(self, state):
        class ExplodingNotifications:
            def send_all(self, *a, **k):
                raise RuntimeError("webhook down")

        state.rows_for["SELECT prediction_id"] = [{"prediction_id": "p1", "project_id": "proj1"}]
        state.rows_for["SELECT interview_responses"] = [
            {"interview_responses": json.dumps({"alert_destination_configs": [_DEST]})}
        ]
        svc = HITLReviewService(state=state, notifications=ExplodingNotifications())

        ids = svc.escalate_sla_breaches(sla_minutes=60, project_id="proj1")

        assert ids == ["p1"]  # escalation still recorded despite notification blowing up
        assert state.audits[0]["action_type"] == "hitl_sla_escalated"


class TestExplainabilityResolve:
    def _items(self):
        return [
            ExplainabilityItem("confidence_bucket", "sync"),
            ExplainabilityItem("top_3_feature_contributions", "sync"),
            ExplainabilityItem("full_shap_vector", "sync"),  # misconfigured on purpose
            ExplainabilityItem("counterfactual_example", "sync"),  # ditto
        ]

    def test_tree_model_keeps_cheap_sync_demotes_expensive(self):
        plan = resolve(model_type="xgboost", items=self._items())

        by_name = {i.name: i for i in plan.items}
        assert by_name["confidence_bucket"].delivery == "sync"
        assert by_name["top_3_feature_contributions"].delivery == "sync"
        # Structural demotions, with reasons the UI can show
        assert by_name["full_shap_vector"].delivery == "async"
        assert by_name["full_shap_vector"].demoted is True
        assert by_name["counterfactual_example"].delivery == "async"
        assert "§12.4" in by_name["counterfactual_example"].demotion_reason

    def test_non_tree_model_demotes_contributions(self):
        plan = resolve(model_type="svm", items=self._items())
        by_name = {i.name: i for i in plan.items}
        assert by_name["top_3_feature_contributions"].delivery == "async"
        assert "TreeExplainer" in by_name["top_3_feature_contributions"].demotion_reason

    def test_measured_latency_demotes_over_budget(self):
        plan = resolve(
            model_type="xgboost",
            items=[ExplainabilityItem("confidence_bucket", "sync")],
            sync_latency_budget_ms=50,
            measured_sync_latency_ms={"confidence_bucket": 80.0},
        )
        item = plan.items[0]
        assert item.delivery == "async"
        assert "80ms exceeds" in item.demotion_reason

    def test_counterfactual_defaults_to_dice(self):
        plan = resolve(
            model_type="xgboost",
            items=[ExplainabilityItem("counterfactual_example", "async")],
        )
        assert plan.items[0].method == "dice"  # accepted §29.2 suggestion
        assert plan.items[0].demoted is False  # was already async — no demotion

    def test_method_defaults_shap_for_trees_lime_otherwise(self):
        assert default_method("lightgbm") == "shap"
        assert default_method("neural_net") == "lime"

    def test_duplicate_items_rejected(self):
        with pytest.raises(ExplainabilityConfigError, match="Duplicate"):
            resolve(
                model_type="xgboost",
                items=[
                    ExplainabilityItem("confidence_bucket", "sync"),
                    ExplainabilityItem("confidence_bucket", "async"),
                ],
            )

    def test_bad_delivery_rejected(self):
        with pytest.raises(ExplainabilityConfigError, match="sync or async"):
            resolve(model_type="xgboost", items=[ExplainabilityItem("x", "immediately")])
