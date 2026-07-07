"""Tests for saga_engine — step ordering, compensation, plan-drift refusal."""

from __future__ import annotations

import hashlib

import pytest

from config import AppConfig
from services.registry_service import CHAMPION, RegistryService
from services.saga_engine import (
    PromoteToProductionSaga,
    assemble_model_card,
    handle_approved_revocation,
)
from tests.test_approval_service import FakeState
from tests.test_registry_service import FakeMlflowClient

MODEL = "retention_churn_prod.ml.churn"


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
    )


class FakeBundles:
    def __init__(self, fail_deploy: bool = False):
        self.fail_deploy = fail_deploy
        self.deploys: list = []

    def deploy(self, bundle_dir, plan):
        if self.fail_deploy:
            raise RuntimeError("workspace unreachable")
        self.deploys.append((bundle_dir, plan))


def _approved_approval(tmp_path, **overrides) -> dict:
    plan_file = tmp_path / "plan_prod.json"
    plan_file.write_text('{"plan": {}}')
    base = {
        "approval_id": "ap1",
        "model_id": "m1",
        "approval_gate": "promotion",
        "approval_type": "business_approval",
        "status": "approved",
        "approval_responses": '[{"approver_email": "a@co.com", "approval_decision": "approve"}]',
        "plan_path": str(plan_file),
        "plan_hash": hashlib.sha256(plan_file.read_bytes()).hexdigest(),
    }
    base.update(overrides)
    return base


def _saga(cfg, state, bundles=None, client=None, canary=None, policy=None) -> PromoteToProductionSaga:
    registry = RegistryService(config=cfg, client=client or FakeMlflowClient())
    return PromoteToProductionSaga(
        state=state,
        bundles=bundles or FakeBundles(),
        registry=registry,
        canary_check=canary,
        policy=policy,
    )


def _run(saga, tmp_path, version=2):
    return saga.run(
        project_id="p1",
        approval_id="ap1",
        bundle_dir=tmp_path,
        uc_full_name=MODEL,
        candidate_version=version,
        actor_email="mlops@co.com",
        approval_manifest_hash="mh123",
        fairness_test_result="pass",
    )


class TestHappyPath:
    def test_full_promotion(self, cfg, tmp_path):
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path)
        client = FakeMlflowClient()
        client.set_registered_model_alias(MODEL, CHAMPION, 1)
        bundles = FakeBundles()
        saga = _saga(cfg, state, bundles=bundles, client=client)

        result = _run(saga, tmp_path)

        assert result.promoted is True
        assert client.aliases[MODEL][CHAMPION] == 2
        # Version 2 carries the full audit trail (§7.4 + approval linkage)
        tags = client.tags[(MODEL, "2")]
        assert tags["approval_id"] == "ap1"
        assert tags["previous_champion_version"] == "1"
        assert bundles.deploys, "bundle deploy ran"
        # Canary skipped (no monitoring) is recorded as skipped, never as passed
        canary_step = next(s for s in result.steps if s.name == "canary_window")
        assert canary_step.status == "skipped"
        # Step 7 always runs
        assert state.audits[-1]["action_type"] == "promotion_saga"
        assert state.audits[-1]["action_status"] == "success"
        # Model card assembled (step 6.5)
        assert (tmp_path / "docs" / "MODEL_CARD.md").exists()


class TestGuards:
    def test_unapproved_gate_aborts_before_deploy(self, cfg, tmp_path):
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path, status="pending")
        bundles = FakeBundles()
        saga = _saga(cfg, state, bundles=bundles)

        result = _run(saga, tmp_path)

        assert result.promoted is False
        assert not bundles.deploys
        assert result.steps[0].status == "failed"

    def test_plan_drift_refused(self, cfg, tmp_path):
        state = FakeState()
        approval = _approved_approval(tmp_path)
        state.approvals["ap1"] = approval
        # Plan file modified after review
        (tmp_path / "plan_prod.json").write_text('{"plan": {"jobs.evil": {"action": "create"}}}')
        bundles = FakeBundles()
        saga = _saga(cfg, state, bundles=bundles)

        result = _run(saga, tmp_path)

        assert result.promoted is False
        assert not bundles.deploys
        drift_step = next(s for s in result.steps if s.name == "bundle_deploy")
        assert "drift" in drift_step.detail

    def test_deploy_failure_aborts_cleanly(self, cfg, tmp_path):
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path)
        client = FakeMlflowClient()
        client.set_registered_model_alias(MODEL, CHAMPION, 1)
        saga = _saga(cfg, state, bundles=FakeBundles(fail_deploy=True), client=client)

        result = _run(saga, tmp_path)

        assert result.promoted is False
        # Champion untouched
        assert client.aliases[MODEL][CHAMPION] == 1
        # Audit still written (step 7 always runs)
        assert state.audits[-1]["action_type"] == "promotion_saga"
        assert state.audits[-1]["action_status"] == "failure"

    def test_canary_breach_compensates_challenger(self, cfg, tmp_path):
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path)
        client = FakeMlflowClient()
        client.set_registered_model_alias(MODEL, CHAMPION, 1)
        saga = _saga(cfg, state, client=client, canary=lambda _uc: False)

        result = _run(saga, tmp_path)

        assert result.promoted is False
        assert client.aliases[MODEL][CHAMPION] == 1  # champion never moved
        compensated = [s for s in result.steps if s.status == "compensated"]
        assert compensated and "challenger" in compensated[0].detail


class TestRevocationHandling:
    def test_current_champion_revocation_rolls_back(self, cfg, tmp_path):
        state = FakeState()
        client = FakeMlflowClient()
        registry = RegistryService(config=cfg, client=client)
        # v2 is champion, promoted under approval ap1, with v1 history
        registry.promote(MODEL, 1, CHAMPION, actor_email="a@co.com")
        registry.promote(MODEL, 2, CHAMPION, actor_email="a@co.com", extra_tags={"approval_id": "ap1"})

        action = handle_approved_revocation(
            state=state,
            registry=registry,
            original_approval={"approval_id": "ap1", "plan_hash": "x"},
            uc_full_name=MODEL,
            actor_email="security@co.com",
            reason="approval based on stale fairness data",
        )

        assert action == "rolled_back"
        assert client.aliases[MODEL][CHAMPION] == 1
        assert state.audits[-1]["action_type"] == "revocation_rollback"

    def test_historical_revocation_opens_investigation(self, cfg, tmp_path):
        state = FakeState()
        client = FakeMlflowClient()
        registry = RegistryService(config=cfg, client=client)
        # champion v3 was approved under ap2; revoking older ap1 (§29.3)
        registry.promote(MODEL, 3, CHAMPION, actor_email="a@co.com", extra_tags={"approval_id": "ap2"})

        action = handle_approved_revocation(
            state=state,
            registry=registry,
            original_approval={"approval_id": "ap1", "plan_hash": "x"},
            uc_full_name=MODEL,
            actor_email="security@co.com",
            reason="historical concern",
        )

        assert action == "investigation_opened"
        assert client.aliases[MODEL][CHAMPION] == 3  # no automatic model action
        assert state.audits[-1]["action_type"] == "revocation_investigation_opened"


class PolicyStub:
    """§20.2/§20.5 policy surface the saga consults at step 1."""

    def __init__(self, missing=None, block=None):
        self.missing = set(missing or [])
        self.block = block

    def unsatisfied_gates(self, project_id):
        return self.missing

    def revalidation_block(self, project_id):
        return self.block


class TestPolicyPackGates:
    def test_missing_policy_gate_aborts_before_deploy(self, cfg, tmp_path):
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path)
        bundles = FakeBundles()
        saga = _saga(cfg, state, bundles=bundles, policy=PolicyStub(missing={"security_review"}))

        result = _run(saga, tmp_path)

        assert result.promoted is False
        assert bundles.deploys == []  # aborted at step 1, nothing deployed
        step = result.steps[0]
        assert step.name == "verify_gates" and step.status == "failed"
        assert "security_review" in step.detail

    def test_revalidation_block_aborts_promotion(self, cfg, tmp_path):
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path)
        bundles = FakeBundles()
        saga = _saga(cfg, state, bundles=bundles, policy=PolicyStub(block="block_new_traffic"))

        result = _run(saga, tmp_path)

        assert result.promoted is False
        assert bundles.deploys == []
        assert "revalidation due" in result.steps[0].detail

    def test_warn_severity_does_not_block(self, cfg, tmp_path):
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path)
        saga = _saga(cfg, state, policy=PolicyStub(block="warn"))

        result = _run(saga, tmp_path)

        assert result.promoted is True

    def test_satisfied_policy_gates_promote(self, cfg, tmp_path):
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path)
        saga = _saga(cfg, state, policy=PolicyStub())

        result = _run(saga, tmp_path)

        assert result.promoted is True
        assert result.steps[0].status == "ok"

    def test_default_policy_requires_nothing_for_untiered_projects(self, cfg, tmp_path):
        # No policy injected — the saga builds PolicyPackService over FakeState,
        # which has no project row → no packs → no extra gates (§20.2)
        state = FakeState()
        state.approvals["ap1"] = _approved_approval(tmp_path)
        saga = _saga(cfg, state)

        result = _run(saga, tmp_path)

        assert result.promoted is True


class TestModelCard:
    def test_assembles_governance_section(self, tmp_path):
        approval = {
            "approval_gate": "promotion",
            "approval_type": "business_approval",
            "plan_hash": "abc",
            "approval_responses": '[{"approver_email": "a@co.com"}]',
        }
        path = assemble_model_card(
            tmp_path,
            project_id="p1",
            uc_full_name=MODEL,
            version=2,
            approval=approval,
            fairness_test_result="pass",
        )
        text = path.read_text()
        assert "a@co.com" in text
        assert "Fairness test result: pass" in text
        assert "`abc`" in text
