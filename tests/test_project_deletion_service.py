"""Tests for ProjectDeletionService — MLOps-approval-gated soft delete
(owner request 2026-07-13). Core properties under test:
  1. execute_deletion refuses to run without an approved gate.
  2. UC data (schemas/tables/Volumes) is NEVER touched.
  3. GitHub repo is NEVER deleted -- only surfaced as a manual reminder.
"""

from __future__ import annotations

import pytest

from config import AppConfig
from services.project_deletion_service import ProjectDeletionError, ProjectDeletionService


class FakeStateService:
    def __init__(self, project: dict | None = None):
        self.project = project or {}
        self.status_updates: list[tuple] = []
        self.audit_calls: list[dict] = []
        self.approved_gate: str | None = "approval-123"  # simulate an already-approved gate by default
        self.models_created: list[dict] = []

    def _tbl(self, name):
        return f"cat.schema.{name}"

    def _exec(self, sql, params=None):
        if "FROM cat.schema.models" in sql and "SELECT model_id" in sql:
            return []  # force placeholder-model creation path in tests that hit it
        if "INSERT INTO cat.schema.models" in sql:
            self.models_created.append(params)
            return []
        if "FROM cat.schema.approvals" in sql:
            return [{"approval_id": self.approved_gate}] if self.approved_gate else []
        return []

    def get_project(self, project_id):
        return self.project if self.project.get("project_id") == project_id else None

    def update_project_status(self, project_id, status, updated_by):
        self.status_updates.append((project_id, status, updated_by))

    def log_audit(self, **kwargs):
        self.audit_calls.append(kwargs)


class FakeApprovalService:
    def __init__(self):
        self.requests: list[dict] = []

    def request_approval(self, **kwargs):
        self.requests.append(kwargs)
        return "approval-123"


def _cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com", databricks_token="dapi-test", warehouse_id="wh123"
    )


def _project(**overrides) -> dict:
    base = {
        "project_id": "proj-1",
        "project_name": "churn_model",
        "owner_email": "owner@example.com",
        "team_name": "ds_team",
        "github_repo_url": "https://github.com/org/churn-model",
        "budget_policy_id": "policy-abc",
        "secret_scope_name": "",
    }
    base.update(overrides)
    return base


class TestRequestDeletion:
    def test_creates_approval_request(self):
        state = FakeStateService(project=_project())
        approvals = FakeApprovalService()
        svc = ProjectDeletionService(_cfg(), state=state, approvals=approvals)

        approval_id = svc.request_deletion("proj-1", "ds@example.com", "no longer needed")

        assert approval_id == "approval-123"
        assert approvals.requests[0]["approval_type"] == "project_deletion"
        assert approvals.requests[0]["required_count"] == 1

    def test_unknown_project_raises(self):
        state = FakeStateService(project={})
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())
        with pytest.raises(ProjectDeletionError):
            svc.request_deletion("nonexistent", "ds@example.com", "")


class TestExecuteDeletionGating:
    def test_refuses_without_approval(self):
        state = FakeStateService(project=_project())
        state.approved_gate = None
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())

        with pytest.raises(ProjectDeletionError, match="not been approved"):
            svc.execute_deletion("proj-1", "mlops@example.com")

        assert state.status_updates == []  # never touched the project row

    def test_proceeds_once_approved(self, monkeypatch):
        state = FakeStateService(project=_project(budget_policy_id="", secret_scope_name=""))
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())

        result = svc.execute_deletion("proj-1", "mlops@example.com")

        assert state.status_updates == [("proj-1", "deleted", "mlops@example.com")]
        assert any(s["name"] == "project_status" and s["status"] == "ok" for s in result.steps)


class TestExecuteDeletionScope:
    def test_never_touches_uc_data(self, monkeypatch):
        state = FakeStateService(project=_project())
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())
        monkeypatch.setattr("services.budget_policy_service.BudgetPolicyService.delete_policy", lambda self, pid: None)

        result = svc.execute_deletion("proj-1", "mlops@example.com")

        uc_step = next(s for s in result.steps if s["name"] == "uc_data")
        assert uc_step["status"] == "preserved"
        assert "intentionally left intact" in uc_step["detail"]

    def test_github_repo_never_deleted_only_reminded(self, monkeypatch):
        state = FakeStateService(project=_project(github_repo_url="https://github.com/org/churn-model"))
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())
        monkeypatch.setattr("services.budget_policy_service.BudgetPolicyService.delete_policy", lambda self, pid: None)

        result = svc.execute_deletion("proj-1", "mlops@example.com")

        github_step = next(s for s in result.steps if s["name"] == "github_repo")
        assert github_step["status"] == "manual_action_required"
        assert "https://github.com/org/churn-model" in github_step["detail"]
        assert result.github_repo_url == "https://github.com/org/churn-model"

    def test_lists_repo_files_for_the_ds_to_review(self, monkeypatch):

        class FakeTreeItem:
            def __init__(self, path, type_):
                self.path = path
                self.type = type_

        class FakeTree:
            tree = [
                FakeTreeItem("README.md", "blob"),
                FakeTreeItem("src", "tree"),
                FakeTreeItem("src/train.py", "blob"),
            ]

        class FakeRepo:
            default_branch = "main"

            def get_git_tree(self, sha, recursive):
                assert sha == "main" and recursive is True
                return FakeTree()

        class FakeGithub:
            def __init__(self, token):
                pass

            def get_repo(self, full_name):
                assert full_name == "org/churn-model"
                return FakeRepo()

        monkeypatch.setattr("github.Github", FakeGithub)
        state = FakeStateService(project=_project(github_repo_url="https://github.com/org/churn-model"))
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())
        monkeypatch.setattr("services.budget_policy_service.BudgetPolicyService.delete_policy", lambda self, pid: None)

        result = svc.execute_deletion("proj-1", "mlops@example.com")

        assert result.github_repo_files == ["README.md", "src/train.py"]  # only blobs, dirs excluded
        github_step = next(s for s in result.steps if s["name"] == "github_repo")
        assert "2 file(s)" in github_step["detail"]

    def test_file_listing_failure_does_not_block_deletion(self, monkeypatch):
        """github.Github() raises with the fake test token used in these
        tests -- this exercises the real failure path, not a mock."""
        state = FakeStateService(project=_project(github_repo_url="https://github.com/org/churn-model"))
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())
        monkeypatch.setattr("services.budget_policy_service.BudgetPolicyService.delete_policy", lambda self, pid: None)

        result = svc.execute_deletion("proj-1", "mlops@example.com")

        assert result.github_repo_files == []
        github_step = next(s for s in result.steps if s["name"] == "github_repo")
        assert github_step["status"] == "manual_action_required"  # still surfaced, just without a file list

    def test_no_github_repo_means_no_reminder_step(self, monkeypatch):
        state = FakeStateService(project=_project(github_repo_url=""))
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())
        monkeypatch.setattr("services.budget_policy_service.BudgetPolicyService.delete_policy", lambda self, pid: None)

        result = svc.execute_deletion("proj-1", "mlops@example.com")

        assert not any(s["name"] == "github_repo" for s in result.steps)

    def test_deletes_budget_policy_when_present(self, monkeypatch):
        state = FakeStateService(project=_project(budget_policy_id="policy-abc"))
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())
        delete_calls = []
        monkeypatch.setattr(
            "services.budget_policy_service.BudgetPolicyService.delete_policy",
            lambda self, pid: delete_calls.append(pid),
        )

        result = svc.execute_deletion("proj-1", "mlops@example.com")

        assert delete_calls == ["policy-abc"]
        budget_step = next(s for s in result.steps if s["name"] == "budget_policy")
        assert budget_step["status"] == "ok"

    def test_skips_budget_policy_deletion_when_none_provisioned(self):
        state = FakeStateService(project=_project(budget_policy_id=""))
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())

        result = svc.execute_deletion("proj-1", "mlops@example.com")

        budget_step = next(s for s in result.steps if s["name"] == "budget_policy")
        assert budget_step["status"] == "skipped"

    def test_logs_audit_trail(self, monkeypatch):
        state = FakeStateService(project=_project())
        svc = ProjectDeletionService(_cfg(), state=state, approvals=FakeApprovalService())
        monkeypatch.setattr("services.budget_policy_service.BudgetPolicyService.delete_policy", lambda self, pid: None)

        svc.execute_deletion("proj-1", "mlops@example.com")

        assert any(c["action_type"] == "project_deleted" for c in state.audit_calls)
