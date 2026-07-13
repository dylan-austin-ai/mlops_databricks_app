"""Tests for ProjectProvisioningService — progressive per-step provisioning
(owner request 2026-07-13). The real risk surface here isn't the individual
Databricks/GitHub calls (covered in test_generator_service.py) but the
idempotency logic: a second call for the same project must not re-hit the
network for anything that already succeeded.
"""

from __future__ import annotations

from config import AppConfig
from services.project_provisioning_service import ProjectProvisioningService


class FakeStateService:
    def __init__(self):
        self.actions: dict[tuple[str, str], dict] = {}
        self.recorded_calls: list[tuple] = []
        self.github_updates: list[dict] = []
        self.schema_updates: list[dict] = []
        self.budget_policy_updates: list[dict] = []

    def get_last_infrastructure_action(self, project_id: str, action_name: str):
        return self.actions.get((project_id, action_name))

    def record_infrastructure_action(
        self, project_id, action_name, status, detail="", resource_id="", content_hash=None
    ):
        self.recorded_calls.append((project_id, action_name, status))
        self.actions[(project_id, action_name)] = {
            "status": status,
            "detail": detail,
            "resource_id": resource_id,
            "content_hash": content_hash,
        }

    def update_project_github(self, project_id, repo_url, repo_name, updated_by):
        self.github_updates.append({"project_id": project_id, "repo_url": repo_url, "repo_name": repo_name})

    def update_project_schemas(self, project_id, **kwargs):
        self.schema_updates.append({"project_id": project_id, **kwargs})

    def update_project_budget_policy(self, project_id, budget_policy_id, updated_by):
        self.budget_policy_updates.append({"project_id": project_id, "budget_policy_id": budget_policy_id})


class FakeGenerator:
    """Records call counts per method so tests can assert the network is
    never re-hit for an already-succeeded action."""

    VOLUME_NAME = "artifacts"

    def __init__(self):
        self.calls: dict[str, int] = {
            "_resolve_budget_policy": 0,
            "_scaffold_code": 0,
            "_create_github_repo": 0,
            "_create_uc_schemas": 0,
            "_create_uc_volumes": 0,
            "_create_mlflow_experiment": 0,
        }

    def _resolve_budget_policy(self, project_name, team_name, interview_responses, result):
        self.calls["_resolve_budget_policy"] += 1
        result.budget_policy_id = "policy-123"
        result.add_step("budget_policy", "ok", "created: policy-123")
        return "policy-123"

    def _scaffold_code(self, project_name, owner_email, interview_responses, result, budget_policy_id):
        self.calls["_scaffold_code"] += 1
        result.add_step("scaffold_code", "ok", "/tmp/fake-scaffold")
        return "/tmp/fake-scaffold"

    def _create_github_repo(self, project_name, owner_email, scaffold_dir, interview_responses, result):
        self.calls["_create_github_repo"] += 1
        result.github_repo_url = "https://github.com/org/proj"
        result.github_repo_name = "proj"
        result.add_step("github_repo", "ok", result.github_repo_url)

    def _create_uc_schemas(self, project_name, result):
        self.calls["_create_uc_schemas"] += 1
        result.uc_schema_dev = "mlops_non_prod.proj_dev"
        result.uc_schema_staging = "mlops_non_prod.proj_staging"
        result.uc_schema_prod = "mlops.proj_prod"
        result.add_step("uc_schemas", "ok", "created")

    def _create_uc_volumes(self, result):
        self.calls["_create_uc_volumes"] += 1
        result.uc_volume_dev = f"{result.uc_schema_dev}.artifacts"
        result.uc_volume_staging = f"{result.uc_schema_staging}.artifacts"
        result.add_step("uc_volumes", "ok", "created")

    def _create_mlflow_experiment(self, project_name, result):
        self.calls["_create_mlflow_experiment"] += 1
        result.mlflow_experiment_id = "exp-456"
        result.add_step("mlflow_experiment", "ok", "/Shared/mlops/proj")


def _cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
        github_token="ghp-test",
        projects_catalog="mlops",
        projects_catalog_dev="mlops_non_prod",
        projects_catalog_staging="mlops_non_prod",
    )


class TestProvisionStep1FirstRun:
    def test_fires_every_action_and_records_it(self):
        state = FakeStateService()
        gen = FakeGenerator()
        svc = ProjectProvisioningService(_cfg(), state=state, generator=gen)

        result = svc.provision_step1("proj-1", "proj", "owner@example.com", {"team_name": "ds_team"})

        assert gen.calls["_resolve_budget_policy"] == 1
        assert gen.calls["_scaffold_code"] == 1
        assert gen.calls["_create_github_repo"] == 1
        assert gen.calls["_create_uc_schemas"] == 1
        assert gen.calls["_create_uc_volumes"] == 1
        assert gen.calls["_create_mlflow_experiment"] == 1
        assert result.github_repo_url == "https://github.com/org/proj"
        recorded_names = {name for _, name, _ in state.recorded_calls}
        assert recorded_names == {"budget_policy", "github_repo", "uc_schemas", "uc_volumes", "mlflow_experiment"}

    def test_updates_project_row_with_resolved_references(self):
        state = FakeStateService()
        gen = FakeGenerator()
        svc = ProjectProvisioningService(_cfg(), state=state, generator=gen)

        svc.provision_step1("proj-1", "proj", "owner@example.com", {"team_name": "ds_team"})

        assert state.github_updates[0]["repo_url"] == "https://github.com/org/proj"
        assert state.schema_updates[0]["uc_schema_dev"] == "mlops_non_prod.proj_dev"
        assert state.schema_updates[0]["secret_scope_name"] == ""  # deferred, never eager
        assert state.budget_policy_updates[0]["budget_policy_id"] == "policy-123"


class TestProvisionStep1Idempotency:
    def test_second_call_skips_every_network_action(self):
        state = FakeStateService()
        gen = FakeGenerator()
        svc = ProjectProvisioningService(_cfg(), state=state, generator=gen)

        svc.provision_step1("proj-1", "proj", "owner@example.com", {"team_name": "ds_team"})
        svc.provision_step1("proj-1", "proj", "owner@example.com", {"team_name": "ds_team"})

        assert gen.calls == {k: 1 for k in gen.calls}  # every action still fired exactly once total

    def test_second_call_still_returns_a_usable_result(self):
        state = FakeStateService()
        gen = FakeGenerator()
        svc = ProjectProvisioningService(_cfg(), state=state, generator=gen)

        svc.provision_step1("proj-1", "proj", "owner@example.com", {"team_name": "ds_team"})
        result = svc.provision_step1("proj-1", "proj", "owner@example.com", {"team_name": "ds_team"})

        assert result.github_repo_url == "https://github.com/org/proj"
        assert result.uc_schema_dev == "mlops_non_prod.proj_dev"
        assert result.uc_volume_dev == "mlops_non_prod.proj_dev.artifacts"
        assert result.mlflow_experiment_id == "exp-456"
        assert all(s["status"] == "ok" for s in result.steps)

    def test_different_project_ids_are_independent(self):
        state = FakeStateService()
        gen = FakeGenerator()
        svc = ProjectProvisioningService(_cfg(), state=state, generator=gen)

        svc.provision_step1("proj-1", "proj-a", "owner@example.com", {"team_name": "ds_team"})
        svc.provision_step1("proj-2", "proj-b", "owner@example.com", {"team_name": "ds_team"})

        assert gen.calls["_create_uc_schemas"] == 2  # not shared/skipped across projects


class TestIsStep1Provisioned:
    def test_false_before_provisioning(self):
        state = FakeStateService()
        svc = ProjectProvisioningService(_cfg(), state=state, generator=FakeGenerator())
        assert svc.is_step1_provisioned("proj-1") is False

    def test_true_after_provisioning(self):
        state = FakeStateService()
        gen = FakeGenerator()
        svc = ProjectProvisioningService(_cfg(), state=state, generator=gen)
        svc.provision_step1("proj-1", "proj", "owner@example.com", {"team_name": "ds_team"})
        assert svc.is_step1_provisioned("proj-1") is True

    def test_false_if_only_partially_provisioned(self):
        """A GitHub-only success (e.g. UC schema creation failed) must not
        lock project_name -- the DS could still legitimately need to retry
        under a different name if the schema path collided."""
        state = FakeStateService()
        state.record_infrastructure_action("proj-1", "github_repo", "ok", resource_id="https://github.com/org/proj")
        svc = ProjectProvisioningService(_cfg(), state=state, generator=FakeGenerator())
        assert svc.is_step1_provisioned("proj-1") is False
