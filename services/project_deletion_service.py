"""ProjectDeletionService — MLOps-approval-gated project deletion (owner
request 2026-07-13: "There should be an option to delete a project in the
app, but it needs MLOps approval. Deleting the GitHub should be required to
be manual, with a reminder in the App that the DS needs to do this
themselves.").

Reuses the existing ApprovalService/approvals table (approval_type=
approval_gate="project_deletion") rather than a bespoke workflow — same
review surface (pages/03_approvals.py) an MLOps reviewer already uses for
every other gate.

Execution scope, deliberately conservative:
  - project row: soft-deleted (status="deleted"), never physically removed
    — audit trail stays intact.
  - Budget Policy: deleted (stops cost accrual — the one clearly-safe-to-
    reverse-by-recreating side effect).
  - Secret scope: deleted, if one was ever provisioned (most projects have
    none — see generator_service.py's module docstring).
  - UC schemas/tables/Volumes/training-data-snapshots: NEVER touched here.
    Deleting them would destroy exactly the reproducibility this session
    also built (data_versioning_service.py) — a separate, explicit "purge
    data" action is out of scope for this pass.
  - GitHub repo: NEVER touched. Surfaced back to the caller as a manual
    reminder with the repo link — the app has no delete_repo scope on its
    token anyway (confirmed live 2026-07-13).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from config import AppConfig, get_config
from services.approval_service import ApprovalService
from services.state_service import StateService

_GITHUB_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")

DELETION_GATE = "project_deletion"


class ProjectDeletionError(RuntimeError):
    """Raised when a deletion operation fails or preconditions aren't met."""


@dataclass
class DeletionResult:
    project_id: str
    steps: list[dict[str, str]] = field(default_factory=list)
    github_repo_url: str = ""
    github_repo_files: list[str] = field(default_factory=list)

    def add_step(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append({"name": name, "status": status, "detail": detail})


class ProjectDeletionService:
    def __init__(
        self,
        config: AppConfig | None = None,
        state: StateService | None = None,
        approvals: ApprovalService | None = None,
    ) -> None:
        self._cfg = config or get_config()
        self._state = state or StateService(self._cfg)
        self._approvals = approvals or ApprovalService(state=self._state)

    def _ensure_placeholder_model(self, project: dict) -> str:
        """Same pattern as pages/03_approvals.py's own helper — the
        approvals table's model_id -> projects join needs a real models row
        to resolve project_name/team_name in the reviewer's queue."""
        rows = self._state._exec(
            f"SELECT model_id FROM {self._state._tbl('models')} WHERE project_id = :project_id LIMIT 1",
            params={"project_id": project["project_id"]},
        )
        if rows:
            return rows[0]["model_id"]
        model_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        self._state._exec(
            f"""
            INSERT INTO {self._state._tbl("models")}
              (model_id, project_id, model_name, status, is_production,
               owner_email, team_name, created_timestamp, created_by, last_updated, last_updated_by)
            VALUES
              (:model_id, :project_id, :model_name, 'development', false,
               :owner_email, :team_name, :now, :owner_email, :now, :owner_email)
            """,
            params={
                "model_id": model_id,
                "project_id": project["project_id"],
                "model_name": project["project_name"],
                "owner_email": project.get("owner_email", ""),
                "team_name": project.get("team_name", ""),
                "now": now,
            },
        )
        return model_id

    def request_deletion(self, project_id: str, requested_by: str, reason: str) -> str:
        project = self._state.get_project(project_id)
        if not project:
            raise ProjectDeletionError(f"Unknown project_id: {project_id!r}")
        model_id = self._ensure_placeholder_model(project)
        approval_id = self._approvals.request_approval(
            model_id=model_id,
            approval_type=DELETION_GATE,
            approval_gate=DELETION_GATE,
            requested_by=requested_by,
            required_count=1,
        )
        if reason.strip():
            self._state.log_audit(
                action_type="project_deletion_requested",
                actor_email=requested_by,
                actor_role="data_scientist",
                resource_type="project",
                resource_id=project_id,
                project_id=project_id,
                approval_id=approval_id,
                change_details={"reason": reason.strip()},
            )
        return approval_id

    def is_deletion_approved(self, project_id: str) -> str | None:
        """Returns the approved approval_id if a project_deletion gate has
        been approved for this project, else None."""
        project = self._state.get_project(project_id)
        if not project:
            return None
        rows = self._state._exec(
            f"""
            SELECT a.approval_id FROM {self._state._tbl("approvals")} a
            JOIN {self._state._tbl("models")} m ON a.model_id = m.model_id
            WHERE m.project_id = :project_id AND a.approval_gate = :gate AND a.status = 'approved'
            ORDER BY a.requested_timestamp DESC
            LIMIT 1
            """,
            params={"project_id": project_id, "gate": DELETION_GATE},
        )
        return rows[0]["approval_id"] if rows else None

    def _list_repo_files(self, repo_url: str) -> list[str]:
        """Owner request 2026-07-13: the deletion reminder should list the
        actual files in the repo so the DS can delete or archive them
        individually, rather than just being told to nuke the whole repo
        blind. Best-effort — returns [] (not an exception) on any failure,
        since a listing failure must never block the rest of deletion."""
        match = _GITHUB_URL_RE.match(repo_url)
        if not match:
            return []
        try:
            from github import Github

            gh = Github(self._cfg.github_token)
            repo = gh.get_repo(f"{match.group(1)}/{match.group(2)}")
            tree = repo.get_git_tree(sha=repo.default_branch, recursive=True)
            return sorted(item.path for item in tree.tree if item.type == "blob")
        except Exception:
            return []

    def execute_deletion(self, project_id: str, actor_email: str) -> DeletionResult:
        """Only proceeds once an MLOps reviewer has approved the
        project_deletion gate — raises otherwise, never a silent no-op."""
        approval_id = self.is_deletion_approved(project_id)
        if not approval_id:
            raise ProjectDeletionError(
                "This project's deletion has not been approved yet — request approval first "
                "and wait for an MLOps reviewer to sign off."
            )
        project = self._state.get_project(project_id)
        if not project:
            raise ProjectDeletionError(f"Unknown project_id: {project_id!r}")

        result = DeletionResult(project_id=project_id, github_repo_url=project.get("github_repo_url", ""))

        try:
            self._state.update_project_status(project_id, "deleted", actor_email)
            result.add_step("project_status", "ok", "soft-deleted")
        except Exception as exc:
            result.add_step("project_status", "failed", str(exc))

        budget_policy_id = project.get("budget_policy_id", "")
        if budget_policy_id:
            try:
                from services.budget_policy_service import BudgetPolicyService

                BudgetPolicyService(self._cfg).delete_policy(budget_policy_id)
                result.add_step("budget_policy", "ok", f"deleted: {budget_policy_id}")
            except Exception as exc:
                result.add_step("budget_policy", "failed", str(exc))
        else:
            result.add_step("budget_policy", "skipped", "none provisioned")

        secret_scope_name = project.get("secret_scope_name", "")
        if secret_scope_name:
            try:
                from databricks.sdk import WorkspaceClient

                ws = WorkspaceClient(host=self._cfg.databricks_host, token=self._cfg.databricks_token, auth_type="pat")
                ws.secrets.delete_scope(scope=secret_scope_name)
                result.add_step("secret_scope", "ok", f"deleted: {secret_scope_name}")
            except Exception as exc:
                result.add_step("secret_scope", "failed", str(exc))
        else:
            result.add_step("secret_scope", "skipped", "none provisioned")

        result.add_step(
            "uc_data",
            "preserved",
            "UC schemas/tables/Volumes/training-data-snapshots intentionally left intact",
        )
        if result.github_repo_url:
            files = self._list_repo_files(result.github_repo_url)
            result.github_repo_files = files
            if files:
                result.add_step(
                    "github_repo",
                    "manual_action_required",
                    f"{len(files)} file(s) at {result.github_repo_url} — go through each and delete or "
                    "archive it yourself (or archive/delete the whole repo).",
                )
            else:
                result.add_step(
                    "github_repo",
                    "manual_action_required",
                    f"delete or archive this yourself: {result.github_repo_url} (couldn't list its files — see logs)",
                )

        self._state.log_audit(
            action_type="project_deleted",
            actor_email=actor_email,
            actor_role="mlops",
            resource_type="project",
            resource_id=project_id,
            project_id=project_id,
            approval_id=approval_id,
        )
        return result
