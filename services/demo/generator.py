"""DemoProjectInfrastructureGenerator — same interface as
ProjectInfrastructureGenerator, but every method that reaches an outside
system (GitHub, Unity Catalog, MLflow, Budget Policy) fabricates a
plausible result instead of calling it, and queues a popup describing what
the real action would have done.

_scaffold_code/_git_init_commit are inherited unchanged: they only render
Jinja templates into a local temp dir and `git init`/`git commit` there, so
running them for real has no effect outside that temp dir and the preview
it produces is genuine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.generator_service import GenerationResult, ProjectInfrastructureGenerator


class DemoProjectInfrastructureGenerator(ProjectInfrastructureGenerator):
    def _resolve_budget_policy(
        self,
        project_name: str,
        team_name: str,
        interview_responses: dict[str, Any],
        result: GenerationResult,
    ) -> str:
        from components.demo import queue_action

        policy_id = f"demo-budget-{project_name}"
        result.budget_policy_id = policy_id
        result.add_step("budget_policy", "ok", f"(demo) {policy_id}")
        queue_action(
            "Budget Policy",
            f"Would create a serverless Budget Policy named `mlops-{project_name}` for cost "
            f"attribution (team: {team_name or '—'}).",
        )
        return policy_id

    def _create_github_repo(
        self,
        project_name: str,
        owner_email: str,
        scaffold_dir: Path,
        interview_responses: dict[str, Any],
        result: GenerationResult,
    ) -> None:
        from components.demo import queue_action

        repo_name = project_name.replace("_", "-")
        org = self._cfg.github_org or "your-org"
        repo_url = f"https://github.com/{org}/{repo_name}"
        result.github_repo_url = repo_url
        result.github_repo_name = repo_name
        result.add_step("github_repo", "ok", f"(demo) {repo_url}")
        queue_action(
            "GitHub Repository",
            f"Would create a private repo `{org}/{repo_name}` and push the generated scaffold. "
            f"The code you'd actually get was rendered locally at `{scaffold_dir}`.",
        )

    def _create_uc_schemas(self, project_name: str, result: GenerationResult) -> None:
        from components.demo import queue_action

        schemas = {
            "dev": f"{self._cfg.projects_catalog_for('dev')}.{project_name}_dev",
            "staging": f"{self._cfg.projects_catalog_for('staging')}.{project_name}_staging",
            "prod": f"{self._cfg.projects_catalog_for('prod')}.{project_name}_prod",
        }
        result.uc_schema_dev = schemas["dev"]
        result.uc_schema_staging = schemas["staging"]
        result.uc_schema_prod = schemas["prod"]
        result.add_step("uc_schemas", "ok", "(demo) " + ", ".join(schemas.values()))
        queue_action("Unity Catalog Schemas", "Would create these schemas: " + ", ".join(schemas.values()))

    def _create_uc_volumes(self, result: GenerationResult) -> None:
        from components.demo import queue_action

        created: list[str] = []
        if result.uc_schema_dev:
            result.uc_volume_dev = f"{result.uc_schema_dev}.{self.VOLUME_NAME}"
            created.append(result.uc_volume_dev)
        if result.uc_schema_staging:
            result.uc_volume_staging = f"{result.uc_schema_staging}.{self.VOLUME_NAME}"
            created.append(result.uc_volume_staging)
        result.add_step("uc_volumes", "ok", "(demo) " + ", ".join(created))
        queue_action("Unity Catalog Volumes", "Would create these managed Volumes: " + ", ".join(created))

    def _create_mlflow_experiment(self, project_name: str, result: GenerationResult) -> None:
        from components.demo import queue_action

        experiment_path = f"/Shared/mlops/{project_name}"
        result.mlflow_experiment_id = f"demo-{abs(hash(project_name)) % 100000}"
        result.add_step("mlflow_experiment", "ok", f"(demo) {experiment_path}")
        queue_action("MLflow Experiment", f"Would create an MLflow experiment at `{experiment_path}`.")
