"""Tests for feature_contract_service — discovery, ack gating, fail-closed release."""

from __future__ import annotations

import pytest

from services.feature_contract_service import FeatureContractError, FeatureContractService
from tests.test_approval_service import FakeState


class FeatureFakeState(FakeState):
    """Routes canned rows by statement prefix; records all writes."""

    def __init__(self):
        super().__init__()
        self.rows_for: dict[str, list[dict]] = {}

    def _exec(self, sql: str, params: dict | None = None):
        self.execs.append((sql, params))
        stripped = " ".join(sql.split())
        for key, rows in self.rows_for.items():
            if key in stripped:
                return rows
        return []


@pytest.fixture
def state() -> FeatureFakeState:
    return FeatureFakeState()


@pytest.fixture
def svc(state) -> FeatureContractService:
    return FeatureContractService(state=state)


def _wire_feature(state, version="1.0.0", consumers=()):
    state.rows_for["SELECT feature_version"] = [{"feature_version": version}]
    state.rows_for["SELECT DISTINCT m.project_id"] = [{"project_id": p} for p in consumers]


class TestDiscovery:
    def test_search_includes_used_by_count_and_params(self, svc, state):
        state.rows_for["SELECT f.feature_id"] = [{"feature_name": "tenure", "used_by_models": 3}]
        rows = svc.catalog_search("ten", shared_only=True)

        assert rows[0]["used_by_models"] == 3
        sql, params = state.execs[0]
        assert "explode(downstream_model_ids)" in sql
        assert "f.is_shared = true" in sql
        assert params["pattern"] == "%ten%"  # parameterized, not interpolated


class TestProposeChange:
    def test_non_breaking_releases_immediately(self, svc, state):
        _wire_feature(state, consumers=("p1", "p2"))
        proposal = svc.propose_change(
            feature_id="f1",
            to_version="1.1.0",
            is_breaking=False,
            description="new optional column",
            proposed_by="owner@co.com",
        )

        assert proposal.status == "released"
        assert proposal.consumers == []  # §8.6: no consumer action for non-breaking
        bumps = [s for s, _ in state.execs if "SET feature_version" in " ".join(s.split())]
        assert bumps, "feature_version bumped immediately"
        assert state.audits[0]["action_type"] == "feature_change_released"

    def test_breaking_with_consumers_pends(self, svc, state):
        _wire_feature(state, consumers=("p1", "p2"))
        proposal = svc.propose_change(
            feature_id="f1",
            to_version="2.0.0",
            is_breaking=True,
            description="drop tenure_days",
            proposed_by="owner@co.com",
        )

        assert proposal.status == "pending_acks"
        assert proposal.consumers == ["p1", "p2"]
        bumps = [s for s, _ in state.execs if "SET feature_version" in " ".join(s.split())]
        assert not bumps, "version must NOT bump before acks"
        assert state.audits[0]["change_details"]["consumers_requiring_ack"] == ["p1", "p2"]

    def test_breaking_without_consumers_releases(self, svc, state):
        _wire_feature(state, consumers=())
        proposal = svc.propose_change(
            feature_id="f1",
            to_version="2.0.0",
            is_breaking=True,
            description="unshared feature",
            proposed_by="owner@co.com",
        )
        assert proposal.status == "released"

    def test_unknown_feature_raises(self, svc, state):
        state.rows_for["SELECT feature_version"] = []
        with pytest.raises(FeatureContractError, match="not found"):
            svc.propose_change(
                feature_id="ghost",
                to_version="2.0.0",
                is_breaking=True,
                description="",
                proposed_by="o@co.com",
            )


class TestAckAndRelease:
    def _wire_change(self, state, status="pending_acks", consumers=("p1", "p2"), acked=("p1",)):
        state.rows_for["SELECT * FROM feature_contract_changes"] = [
            {"change_id": "c1", "feature_id": "f1", "to_version": "2.0.0", "status": status}
        ]
        state.rows_for["SELECT DISTINCT m.project_id"] = [{"project_id": p} for p in consumers]
        state.rows_for["SELECT project_id FROM feature_change_acks"] = [{"project_id": p} for p in acked]

    def test_ack_is_idempotent_merge(self, svc, state):
        svc.acknowledge(change_id="c1", project_id="p1", acked_by="a@co.com")
        sql, params = state.execs[0]
        assert "MERGE INTO feature_change_acks" in sql
        assert "WHEN NOT MATCHED THEN INSERT" in sql
        assert params["project_id"] == "p1"

    def test_pending_acks_lists_missing_consumers(self, svc, state):
        self._wire_change(state)
        assert svc.pending_acks("c1") == ["p2"]

    def test_release_fails_closed_with_missing_acks(self, svc, state):
        self._wire_change(state)
        with pytest.raises(FeatureContractError, match="awaiting acknowledgment.*p2"):
            svc.release("c1", "owner@co.com")
        bumps = [s for s, _ in state.execs if "SET feature_version" in " ".join(s.split())]
        assert not bumps

    def test_release_with_all_acks_bumps_version(self, svc, state):
        self._wire_change(state, acked=("p1", "p2"))
        svc.release("c1", "owner@co.com")

        flat = [" ".join(s.split()) for s, _ in state.execs]
        assert any("SET status = 'released'" in s for s in flat)
        assert any("SET feature_version" in s for s in flat)
        assert state.audits[-1]["action_type"] == "feature_change_released"

    def test_release_already_released_is_noop(self, svc, state):
        self._wire_change(state, status="released")
        svc.release("c1", "owner@co.com")
        flat = [" ".join(s.split()) for s, _ in state.execs]
        assert not any("SET status = 'released'" in s for s in flat)
