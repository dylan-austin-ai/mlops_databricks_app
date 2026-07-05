"""Tests for portfolio_analytics_service — rollups and the §14.4 comparability split."""

from __future__ import annotations

import pytest

from services.portfolio_analytics_service import PortfolioAnalyticsService
from tests.test_approval_service import FakeState


class AnalyticsFakeState(FakeState):
    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []

    def _exec(self, sql: str, params: dict | None = None):
        self.execs.append((sql, params))
        return self.rows


@pytest.fixture
def state() -> AnalyticsFakeState:
    return AnalyticsFakeState()


@pytest.fixture
def svc(state) -> PortfolioAnalyticsService:
    return PortfolioAnalyticsService(state=state)


class TestSpeedAndReliability:
    def test_speed_joins_on_reviewed_plan_hash(self, svc, state):
        state.rows = [{"promotions": "4", "avg_approval_to_deploy_hours": "6.5"}]
        metrics = svc.speed_metrics(days_back=30)

        assert metrics == {"promotions": 4, "avg_approval_to_deploy_hours": 6.5}
        sql, params = state.execs[0]
        # what got approved and what got deployed are tied by the plan artifact
        assert "d.plan_hash = a.plan_hash" in sql
        assert params["days_back"] == 30

    def test_speed_handles_no_promotions(self, svc, state):
        state.rows = [{"promotions": "0", "avg_approval_to_deploy_hours": None}]
        metrics = svc.speed_metrics()
        assert metrics["promotions"] == 0
        assert metrics["avg_approval_to_deploy_hours"] is None

    def test_reliability_counts_verify_failures_as_failures(self, svc, state):
        state.rows = [
            {"status": "deployed", "n": "8"},
            {"status": "failed", "n": "1"},
            {"status": "verify_failed", "n": "1"},
        ]
        metrics = svc.reliability_metrics()

        assert metrics["deployments"] == 10
        assert metrics["failed"] == 2
        assert metrics["failure_rate_pct"] == 20.0

    def test_reliability_empty_is_none_not_zero(self, svc, state):
        state.rows = []
        assert svc.reliability_metrics()["failure_rate_pct"] is None


class TestBusinessImpactComparability:
    def test_split_by_value_fn_review_age_never_blended(self, svc, state):
        state.rows = [
            {"project_id": "p1", "impact_usd": "10000", "fn_reviewed": "1"},
            {"project_id": "p2", "impact_usd": "5000", "fn_reviewed": "0"},
            {"project_id": "p3", "impact_usd": "2500", "fn_reviewed": "0"},
        ]
        rollup = svc.business_impact_rollup()

        # §14.4: high and low confidence are separate figures
        assert rollup.high_confidence_usd == 10000.0
        assert rollup.high_confidence_projects == 1
        assert rollup.low_confidence_usd == 7500.0
        assert rollup.low_confidence_projects == 2
        assert rollup.unreviewed_projects == ["p2", "p3"]

    def test_review_age_rule_in_sql(self, svc, state):
        state.rows = []
        svc.business_impact_rollup()
        sql, _ = state.execs[0]
        assert "last_reviewed_date >= date_sub(current_date()" in sql
        assert "365" in sql


class TestReuseAndCost:
    def test_reuse_uses_lineage_explode(self, svc, state):
        state.rows = [{"shared_features": "6", "multi_consumer_features": "2"}]
        metrics = svc.reuse_metrics()
        assert metrics == {"shared_features": 6, "multi_consumer_features": 2}
        sql, _ = state.execs[0]
        assert "explode(downstream_model_ids)" in sql

    def test_cost_rollup_grouped_by_project(self, svc, state):
        state.rows = [{"project_id": "p1", "total_usd": "42.5"}]
        rows = svc.cost_rollup(days_back=7)
        assert rows[0]["total_usd"] == "42.5"
        sql, params = state.execs[0]
        assert "GROUP BY project_id" in sql
        assert params["days_back"] == 7
