"""ProjectProvisioningService — progressive per-step provisioning (owner
request 2026-07-13). Replaces the old single waterfall at the end of the
wizard: each wizard step fires only the infrastructure its own answers
unlock, tracked idempotently in project_infrastructure_actions so a
Streamlit rerun (or a lost session, or the app restarting mid-wizard) never
re-creates something that already succeeded.

Step 1 unlocks: DB project row, GitHub repo (new or an existing one linked
in Step 1, after an emptiness check), UC schemas + Volumes (dev/staging in
the configured non-prod catalog, prod schema created but not yet used),
MLflow experiment, Budget Policy, and an initial scaffold commit (rendered
with whatever defaults apply until later steps refine specific files — see
services/bundle_commit_service.py for the progressive per-step commits and
drift guard).

Secret scope is deliberately NOT provisioned here — see generator_service.py
module docstring for why.
"""

from __future__ import annotations

from typing import Any

from config import AppConfig, get_config
from services.generator_service import GenerationResult, ProjectInfrastructureGenerator
from services.state_service import StateService

# Action names recorded in project_infrastructure_actions for Step 1's
# idempotency checks. Must match the `name` strings each
# ProjectInfrastructureGenerator._create_*/_resolve_* method passes to
# GenerationResult.add_step().
STEP1_ACTIONS = ("budget_policy", "github_repo", "uc_schemas", "uc_volumes", "mlflow_experiment")


class ProjectProvisioningService:
    def __init__(
        self,
        config: AppConfig | None = None,
        state: StateService | None = None,
        generator: ProjectInfrastructureGenerator | None = None,
    ) -> None:
        self._cfg = config or get_config()
        self._state = state or StateService(self._cfg)
        self._generator = generator or ProjectInfrastructureGenerator(self._cfg)

    def _already_done(self, project_id: str, action_name: str) -> bool:
        last = self._state.get_last_infrastructure_action(project_id, action_name)
        return bool(last and last.get("status") == "ok")

    def _record_from_result(self, project_id: str, result: GenerationResult, action_name: str) -> None:
        """Find the most recent GenerationResult step matching action_name and
        persist it to project_infrastructure_actions. No-ops if the action
        never ran (e.g. it was skipped upstream)."""
        matches = [s for s in result.steps if s["name"] == action_name]
        if not matches:
            return
        step = matches[-1]
        resource_id = ""
        if action_name == "github_repo":
            resource_id = result.github_repo_url
        elif action_name == "uc_schemas":
            resource_id = result.uc_schema_dev
        elif action_name == "uc_volumes":
            resource_id = result.uc_volume_dev
        elif action_name == "mlflow_experiment":
            resource_id = result.mlflow_experiment_id
        elif action_name == "budget_policy":
            resource_id = result.budget_policy_id
        self._state.record_infrastructure_action(
            project_id,
            action_name,
            step["status"],
            detail=step.get("detail", ""),
            resource_id=resource_id,
        )

    def provision_step1(
        self,
        project_id: str,
        project_name: str,
        owner_email: str,
        interview_responses: dict[str, Any],
    ) -> GenerationResult:
        """Idempotent — safe to call on every Step 1 -> Step 2 transition
        (including re-visits via "Back"). Already-succeeded actions are
        skipped without hitting the network again."""
        result = GenerationResult(project_name=project_name)
        team_name = interview_responses.get("team_name", "")

        # budget_policy: independently idempotent (BudgetPolicyService itself
        # look-up-or-creates), safe to skip once recorded ok.
        if self._already_done(project_id, "budget_policy"):
            existing = self._state.get_last_infrastructure_action(project_id, "budget_policy")
            budget_policy_id = existing["resource_id"] if existing else ""
            result.budget_policy_id = budget_policy_id
            result.add_step("budget_policy", "ok", "already provisioned")
        else:
            budget_policy_id = self._generator._resolve_budget_policy(
                project_name, team_name, interview_responses, result
            )
            self._record_from_result(project_id, result, "budget_policy")

        # github_repo: scaffold_code's temp dir doesn't survive a process
        # restart, so it's cheap to re-render each time github_repo hasn't
        # yet succeeded — only skip the pair once the repo itself exists.
        if self._already_done(project_id, "github_repo"):
            existing = self._state.get_last_infrastructure_action(project_id, "github_repo")
            result.github_repo_url = existing["resource_id"] if existing else ""
            result.add_step("github_repo", "ok", "already provisioned")
        else:
            scaffold_dir = self._generator._scaffold_code(
                project_name, owner_email, interview_responses, result, budget_policy_id
            )
            if scaffold_dir and self._cfg.github_token:
                self._generator._create_github_repo(
                    project_name, owner_email, scaffold_dir, interview_responses, result
                )
            else:
                result.add_step("github_repo", "skipped", "GITHUB_TOKEN not set")
            self._record_from_result(project_id, result, "github_repo")

        # uc_schemas + uc_volumes: independently idempotent (schema/volume
        # creation both catch "already exists").
        if self._already_done(project_id, "uc_schemas"):
            # dev/staging/prod paths aren't individually tracked as separate
            # actions, so recompute them the same deterministic way
            # _create_uc_schemas does rather than re-querying Databricks.
            catalog_dev = self._cfg.projects_catalog_for("dev")
            catalog_staging = self._cfg.projects_catalog_for("staging")
            catalog_prod = self._cfg.projects_catalog_for("prod")
            result.uc_schema_dev = f"{catalog_dev}.{project_name}_dev"
            result.uc_schema_staging = f"{catalog_staging}.{project_name}_staging"
            result.uc_schema_prod = f"{catalog_prod}.{project_name}_prod"
            result.add_step("uc_schemas", "ok", "already provisioned")
        else:
            self._generator._create_uc_schemas(project_name, result)
            self._record_from_result(project_id, result, "uc_schemas")

        if self._already_done(project_id, "uc_volumes"):
            if result.uc_schema_dev:
                result.uc_volume_dev = f"{result.uc_schema_dev}.{self._generator.VOLUME_NAME}"
            if result.uc_schema_staging:
                result.uc_volume_staging = f"{result.uc_schema_staging}.{self._generator.VOLUME_NAME}"
            result.add_step("uc_volumes", "ok", "already provisioned")
        else:
            self._generator._create_uc_volumes(result)
            self._record_from_result(project_id, result, "uc_volumes")

        # mlflow_experiment: independently idempotent (get_experiment_by_name
        # look-up-or-create).
        if self._already_done(project_id, "mlflow_experiment"):
            existing = self._state.get_last_infrastructure_action(project_id, "mlflow_experiment")
            result.mlflow_experiment_id = existing["resource_id"] if existing else ""
            result.add_step("mlflow_experiment", "ok", "already provisioned")
        else:
            self._generator._create_mlflow_experiment(project_name, result)
            self._record_from_result(project_id, result, "mlflow_experiment")

        # Persist resolved references onto the project row, same as the old
        # waterfall did at the very end.
        if result.github_repo_url:
            self._state.update_project_github(
                project_id,
                repo_url=result.github_repo_url,
                repo_name=result.github_repo_name,
                updated_by=owner_email,
            )
        if result.uc_schema_dev:
            self._state.update_project_schemas(
                project_id,
                uc_schema_dev=result.uc_schema_dev,
                uc_schema_staging=result.uc_schema_staging,
                uc_schema_prod=result.uc_schema_prod,
                mlflow_experiment_id=result.mlflow_experiment_id,
                secret_scope_name="",
                updated_by=owner_email,
            )
        if result.budget_policy_id:
            self._state.update_project_budget_policy(project_id, result.budget_policy_id, updated_by=owner_email)

        return result

    def is_step1_provisioned(self, project_id: str) -> bool:
        """True once every Step 1 action that isn't explicitly skip-eligible
        has succeeded at least once. Used to lock project_name in the UI."""
        return all(self._already_done(project_id, name) for name in ("uc_schemas", "uc_volumes", "mlflow_experiment"))
