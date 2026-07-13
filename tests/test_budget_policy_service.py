"""Tests for budget_policy_service — account-level Budget Policy attribution
(owner request 2026-07-12). No live account credentials exist in this repo's
test environment, so every test injects a fake AccountClient or exercises
the unavailable-credentials path directly."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import AppConfig
from services.budget_policy_service import (
    BudgetPolicyService,
    BudgetPolicyServiceError,
    BudgetPolicyUnavailable,
)

UNCONFIGURED = AppConfig(
    databricks_host="https://test.cloud.databricks.com",
    databricks_token="dapi-test",
    warehouse_id="wh123",
)

CONFIGURED = AppConfig(
    databricks_host="https://test.cloud.databricks.com",
    databricks_token="dapi-test",
    warehouse_id="wh123",
    databricks_account_host="https://accounts.cloud.databricks.com",
    databricks_account_id="acct-1",
    databricks_account_client_id="sp-client-id",
    databricks_account_client_secret="sp-secret",
)


class FakeBudgetPolicyAPI:
    def __init__(self, existing: list[SimpleNamespace] | None = None, raise_on_create: Exception | None = None):
        self.policies = list(existing or [])
        self.create_calls: list[SimpleNamespace] = []
        self.raise_on_create = raise_on_create
        self._next_id = 100

    def list(self):
        return iter(self.policies)

    def create(self, *, policy, request_id=None):
        if self.raise_on_create:
            raise self.raise_on_create
        self._next_id += 1
        created = SimpleNamespace(
            policy_id=str(self._next_id), policy_name=policy.policy_name, custom_tags=policy.custom_tags
        )
        self.policies.append(created)
        self.create_calls.append(created)
        return created


class FakeAccountClient:
    def __init__(self, budget_policy: FakeBudgetPolicyAPI):
        self.budget_policy = budget_policy


class TestAvailability:
    def test_unconfigured_raises_unavailable_not_generic_error(self):
        svc = BudgetPolicyService(config=UNCONFIGURED)

        with pytest.raises(BudgetPolicyUnavailable, match="Account-level credentials"):
            svc.find_by_name("mlops-churn")

    def test_ensure_policy_unconfigured_raises_unavailable(self):
        svc = BudgetPolicyService(config=UNCONFIGURED)

        with pytest.raises(BudgetPolicyUnavailable):
            svc.ensure_policy("mlops-churn", {"project_id": "churn"})


class TestFindByName:
    def test_finds_existing_policy(self):
        api = FakeBudgetPolicyAPI(existing=[SimpleNamespace(policy_id="p1", policy_name="mlops-churn")])
        svc = BudgetPolicyService(config=CONFIGURED, account_client=FakeAccountClient(api))

        handle = svc.find_by_name("mlops-churn")

        assert handle is not None
        assert handle.policy_id == "p1"
        assert handle.already_existed is True

    def test_returns_none_when_not_found(self):
        api = FakeBudgetPolicyAPI(existing=[])
        svc = BudgetPolicyService(config=CONFIGURED, account_client=FakeAccountClient(api))

        assert svc.find_by_name("mlops-ghost") is None

    def test_list_failure_wrapped_as_service_error(self):
        class ExplodingAPI:
            def list(self):
                raise RuntimeError("account api unreachable")

        svc = BudgetPolicyService(config=CONFIGURED, account_client=FakeAccountClient(ExplodingAPI()))

        with pytest.raises(BudgetPolicyServiceError, match="unreachable"):
            svc.find_by_name("mlops-churn")


class TestEnsurePolicy:
    def test_creates_when_missing(self):
        api = FakeBudgetPolicyAPI()
        svc = BudgetPolicyService(config=CONFIGURED, account_client=FakeAccountClient(api))

        handle = svc.ensure_policy("mlops-churn", {"project_id": "churn", "team": "retention"})

        assert handle.already_existed is False
        assert len(api.create_calls) == 1
        created_tags = {t.key: t.value for t in api.create_calls[0].custom_tags}
        assert created_tags == {"project_id": "churn", "team": "retention"}

    def test_idempotent_returns_existing_without_creating(self):
        api = FakeBudgetPolicyAPI(existing=[SimpleNamespace(policy_id="p1", policy_name="mlops-churn")])
        svc = BudgetPolicyService(config=CONFIGURED, account_client=FakeAccountClient(api))

        handle = svc.ensure_policy("mlops-churn", {"project_id": "churn"})

        assert handle.policy_id == "p1"
        assert handle.already_existed is True
        assert not api.create_calls

    def test_reserved_tag_keys_stripped(self):
        api = FakeBudgetPolicyAPI()
        svc = BudgetPolicyService(config=CONFIGURED, account_client=FakeAccountClient(api))

        svc.ensure_policy("mlops-churn", {"budget-policy-name": "evil", "project_id": "churn"})

        created_tags = {t.key: t.value for t in api.create_calls[0].custom_tags}
        assert "budget-policy-name" not in created_tags
        assert created_tags == {"project_id": "churn"}

    def test_create_failure_wrapped_as_service_error(self):
        api = FakeBudgetPolicyAPI(raise_on_create=RuntimeError("quota exceeded"))
        svc = BudgetPolicyService(config=CONFIGURED, account_client=FakeAccountClient(api))

        with pytest.raises(BudgetPolicyServiceError, match="quota exceeded"):
            svc.ensure_policy("mlops-churn", {})


class TestEnsureDefaultPolicy:
    def test_preset_id_used_as_is_no_lookup(self):
        cfg = AppConfig(
            databricks_host="https://test.cloud.databricks.com",
            databricks_token="dapi-test",
            warehouse_id="wh123",
            default_budget_policy_id="preset-123",
            default_budget_policy_name="mlops-control-plane-default",
        )
        # No account credentials at all — proves no API call is made
        svc = BudgetPolicyService(config=cfg)

        handle = svc.ensure_default_policy()

        assert handle.policy_id == "preset-123"
        assert handle.already_existed is True

    def test_no_preset_id_ensures_named_default(self):
        api = FakeBudgetPolicyAPI()
        svc = BudgetPolicyService(config=CONFIGURED, account_client=FakeAccountClient(api))

        handle = svc.ensure_default_policy()

        assert handle.policy_name == "mlops-control-plane-default"
        assert len(api.create_calls) == 1
        assert api.create_calls[0].policy_name == "mlops-control-plane-default"

    def test_no_preset_id_and_no_credentials_raises_unavailable(self):
        svc = BudgetPolicyService(config=UNCONFIGURED)

        with pytest.raises(BudgetPolicyUnavailable):
            svc.ensure_default_policy()
