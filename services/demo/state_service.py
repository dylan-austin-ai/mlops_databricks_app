"""DemoStateService — StateService's public interface, backed by
DemoStore instead of a real SQL warehouse. Same method names and return
shapes as StateService so page code that calls e.g. svc.list_projects()
needs no changes when Demo Mode swaps the real service out (see
components/demo.py::get_state_service()).

Only the methods actually called from app.py, pages/02_new_project.py, and
pages/06_project_dashboard.py are implemented — Demo Mode's agreed scope.
"""

from __future__ import annotations

import json
from typing import Any

from services.demo.store import _now, _uuid, get_store


class DemoStateService:
    def __init__(self, config: Any = None) -> None:
        pass  # no real connection -- config accepted for signature parity only

    # ── Projects ──────────────────────────────────────────────────────────────

    def create_project(
        self,
        project_name: str,
        owner_email: str,
        team_name: str,
        problem_statement: str,
        created_by: str,
    ) -> str:
        project_id = _uuid()
        now = _now()
        get_store()["projects"][project_id] = {
            "project_id": project_id,
            "project_name": project_name,
            "project_description": problem_statement,
            "created_timestamp": now,
            "created_by": created_by,
            "owner_email": owner_email,
            "team_name": team_name,
            "github_repo_url": "",
            "github_repo_name": "",
            "mlflow_experiment_id": "",
            "status": "created",
            "uc_schema_dev": "",
            "uc_schema_staging": "",
            "uc_schema_prod": "",
            "secret_scope_name": "",
            "budget_policy_id": "",
            "last_updated": now,
            "last_updated_by": created_by,
            "is_archived": False,
        }
        return project_id

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return get_store()["projects"].get(project_id)

    def get_project_by_name(self, project_name: str) -> dict[str, Any] | None:
        for p in get_store()["projects"].values():
            if p["project_name"] == project_name:
                return p
        return None

    def list_projects(self, include_archived: bool = False) -> list[dict[str, Any]]:
        projects = list(get_store()["projects"].values())
        if not include_archived:
            projects = [p for p in projects if not p.get("is_archived")]
        return sorted(projects, key=lambda p: p["created_timestamp"], reverse=True)

    def update_project_status(self, project_id: str, status: str, updated_by: str) -> None:
        p = get_store()["projects"].get(project_id)
        if p:
            p["status"] = status
            p["last_updated"] = _now()
            p["last_updated_by"] = updated_by

    def update_project_github(
        self,
        project_id: str,
        repo_url: str,
        repo_name: str,
        updated_by: str,
    ) -> None:
        p = get_store()["projects"].get(project_id)
        if p:
            p["github_repo_url"] = repo_url
            p["github_repo_name"] = repo_name
            p["last_updated"] = _now()
            p["last_updated_by"] = updated_by

    def update_project_schemas(
        self,
        project_id: str,
        uc_schema_dev: str,
        uc_schema_staging: str,
        uc_schema_prod: str,
        mlflow_experiment_id: str,
        secret_scope_name: str,
        updated_by: str,
    ) -> None:
        p = get_store()["projects"].get(project_id)
        if p:
            p["uc_schema_dev"] = uc_schema_dev
            p["uc_schema_staging"] = uc_schema_staging
            p["uc_schema_prod"] = uc_schema_prod
            p["mlflow_experiment_id"] = mlflow_experiment_id
            p["secret_scope_name"] = secret_scope_name
            p["last_updated"] = _now()
            p["last_updated_by"] = updated_by

    def update_project_budget_policy(self, project_id: str, budget_policy_id: str, updated_by: str) -> None:
        p = get_store()["projects"].get(project_id)
        if p:
            p["budget_policy_id"] = budget_policy_id
            p["last_updated"] = _now()
            p["last_updated_by"] = updated_by

    # ── Project Configurations ────────────────────────────────────────────────

    def save_project_config(
        self,
        project_id: str,
        interview_responses: dict[str, Any],
        created_by: str,
        change_reason: str = "initial configuration",
    ) -> str:
        configs = get_store()["project_configs"].setdefault(project_id, [])
        config_id = _uuid()
        configs.append(
            {
                "config_id": config_id,
                "project_id": project_id,
                "config_version": len(configs) + 1,
                "created_timestamp": _now(),
                "created_by": created_by,
                "change_reason": change_reason,
                "interview_responses": json.dumps(interview_responses),
                "inference_type": interview_responses.get("inference_type", ""),
                "batch_frequency": interview_responses.get("batch_frequency", ""),
            }
        )
        return config_id

    def get_latest_project_config(self, project_id: str) -> dict[str, Any] | None:
        configs = get_store()["project_configs"].get(project_id, [])
        return configs[-1] if configs else None

    # ── Budget Alerts ─────────────────────────────────────────────────────────

    def save_budget_alert(
        self,
        project_id: str,
        budget_period: str,
        budget_threshold_usd: float,
        alert_at_pct: float,
        enabled: bool,
        alert_recipients: list[str],
    ) -> str:
        budget_id = _uuid()
        get_store()["budget_alerts"][project_id] = {
            "budget_id": budget_id,
            "project_id": project_id,
            "budget_period": budget_period,
            "budget_threshold_usd": budget_threshold_usd,
            "alert_at_pct": alert_at_pct,
            "enabled": enabled,
            "alert_recipients": alert_recipients,
            "created_timestamp": _now(),
        }
        return budget_id

    def get_budget_alert(self, project_id: str) -> dict[str, Any] | None:
        return get_store()["budget_alerts"].get(project_id)

    # ── Audit ─────────────────────────────────────────────────────────────────

    def log_audit(self, *args: Any, **kwargs: Any) -> None:
        pass  # best-effort even for the real service -- a no-op is equally safe here

    # ── Project Infrastructure Actions ────────────────────────────────────────

    def record_infrastructure_action(
        self,
        project_id: str,
        action_name: str,
        status: str,
        detail: str = "",
        resource_id: str = "",
        content_hash: str | None = None,
    ) -> None:
        actions = get_store()["infrastructure_actions"].setdefault(project_id, [])
        actions.append(
            {
                "action_id": _uuid(),
                "project_id": project_id,
                "action_name": action_name,
                "status": status,
                "detail": detail,
                "resource_id": resource_id,
                "content_hash": content_hash,
                "created_at": _now(),
            }
        )

    def list_infrastructure_actions(self, project_id: str) -> list[dict[str, Any]]:
        return list(get_store()["infrastructure_actions"].get(project_id, []))

    def get_last_infrastructure_action(self, project_id: str, action_name: str) -> dict[str, Any] | None:
        actions = [
            a for a in get_store()["infrastructure_actions"].get(project_id, []) if a["action_name"] == action_name
        ]
        return actions[-1] if actions else None

    # ── Training Data Snapshots ───────────────────────────────────────────────

    def record_training_data_snapshot(
        self,
        project_id: str,
        source_table: str,
        snapshot_table: str,
        created_by: str,
        source_delta_version: int | None = None,
        row_count: int | None = None,
    ) -> str:
        snapshots = get_store()["training_data_snapshots"].setdefault(project_id, [])
        snapshot_id = _uuid()
        snapshots.append(
            {
                "snapshot_id": snapshot_id,
                "project_id": project_id,
                "source_table": source_table,
                "snapshot_table": snapshot_table,
                "source_delta_version": source_delta_version,
                "row_count": row_count,
                "created_at": _now(),
                "created_by": created_by,
            }
        )
        return snapshot_id

    def list_training_data_snapshots(self, project_id: str) -> list[dict[str, Any]]:
        return list(get_store()["training_data_snapshots"].get(project_id, []))

    def latest_training_data_snapshot(self, project_id: str, source_table: str) -> dict[str, Any] | None:
        matches = [
            s for s in get_store()["training_data_snapshots"].get(project_id, []) if s["source_table"] == source_table
        ]
        return matches[-1] if matches else None

    # ── Installation Config (Settings is out of Demo Mode's scope) ────────────

    def get_installation_config(self) -> dict[str, Any] | None:
        return None

    def save_installation_config(self, config: dict[str, Any], created_by: str) -> str:
        return ""
