"""UC table CRUD layer — all persistent state goes through here.

Uses the Databricks SQL Statement Execution API (warehouse) rather than
Spark, so this works from any Databricks App or local context without
needing a running cluster.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from config import AppConfig, get_config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


class StateService:
    """CRUD operations against UC tables via SQL warehouse."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._cfg = config or get_config()
        self._ws: Any = None

    def _workspace(self) -> Any:
        if self._ws is None:
            from databricks.sdk import WorkspaceClient

            self._ws = WorkspaceClient(
                host=self._cfg.databricks_host,
                token=self._cfg.databricks_token,
            )
        return self._ws

    def _exec(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL statement and return rows as list-of-dicts."""
        from databricks.sdk.service.sql import StatementState

        ws = self._workspace()
        response = ws.statement_execution.execute_statement(
            warehouse_id=self._cfg.warehouse_id,
            statement=sql,
            wait_timeout="30s",
        )

        exec_id = response.statement_id
        state = response.status.state if response.status else None

        while state not in (StatementState.SUCCEEDED, StatementState.FAILED, StatementState.CANCELED):
            time.sleep(0.5)
            result = ws.statement_execution.get_statement(exec_id)
            state = result.status.state if result.status else None
            response = result

        if state != StatementState.SUCCEEDED:
            err = getattr(response.status, "error", "unknown error")
            raise RuntimeError(f"SQL failed: {err}\nSQL: {sql[:200]}")

        # Parse result set into list of dicts
        if not response.result or not response.result.data_array:
            return []
        schema = response.manifest.schema.columns if response.manifest and response.manifest.schema else []
        col_names = [c.name for c in schema]
        return [dict(zip(col_names, row)) for row in response.result.data_array]

    def _tbl(self, name: str) -> str:
        return f"{self._cfg.catalog}.{self._cfg.schema}.{name}"

    # ── Projects ──────────────────────────────────────────────────────────────

    def create_project(
        self,
        project_name: str,
        owner_email: str,
        team_name: str,
        problem_statement: str,
        created_by: str,
    ) -> str:
        """Insert a new project row and return its project_id."""
        project_id = _uuid()
        now = _now()
        sql = f"""
        INSERT INTO {self._tbl("projects")}
          (project_id, project_name, project_description, created_timestamp,
           created_by, owner_email, team_name, status, last_updated, last_updated_by,
           is_archived)
        VALUES
          ('{project_id}', '{project_name}', '{problem_statement}', '{now}',
           '{created_by}', '{owner_email}', '{team_name}', 'created', '{now}', '{created_by}',
           false)
        """
        self._exec(sql)
        self.log_audit(
            action_type="project_created",
            project_id=project_id,
            actor_email=created_by,
            actor_role="data_scientist",
            resource_type="project",
            resource_id=project_id,
            change_details={"project_name": project_name, "team": team_name},
        )
        return project_id

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        rows = self._exec(f"SELECT * FROM {self._tbl('projects')} WHERE project_id = '{project_id}'")
        return rows[0] if rows else None

    def get_project_by_name(self, project_name: str) -> dict[str, Any] | None:
        rows = self._exec(f"SELECT * FROM {self._tbl('projects')} WHERE project_name = '{project_name}'")
        return rows[0] if rows else None

    def list_projects(self, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else "WHERE is_archived = false"
        return self._exec(f"SELECT * FROM {self._tbl('projects')} {where} ORDER BY created_timestamp DESC")

    def update_project_status(self, project_id: str, status: str, updated_by: str) -> None:
        now = _now()
        self._exec(f"""
        UPDATE {self._tbl("projects")}
        SET status = '{status}', last_updated = '{now}', last_updated_by = '{updated_by}'
        WHERE project_id = '{project_id}'
        """)

    def update_project_github(
        self,
        project_id: str,
        repo_url: str,
        repo_name: str,
        updated_by: str,
    ) -> None:
        now = _now()
        self._exec(f"""
        UPDATE {self._tbl("projects")}
        SET github_repo_url = '{repo_url}',
            github_repo_name = '{repo_name}',
            last_updated = '{now}',
            last_updated_by = '{updated_by}'
        WHERE project_id = '{project_id}'
        """)

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
        now = _now()
        self._exec(f"""
        UPDATE {self._tbl("projects")}
        SET uc_schema_dev = '{uc_schema_dev}',
            uc_schema_staging = '{uc_schema_staging}',
            uc_schema_prod = '{uc_schema_prod}',
            mlflow_experiment_id = '{mlflow_experiment_id}',
            secret_scope_name = '{secret_scope_name}',
            last_updated = '{now}',
            last_updated_by = '{updated_by}'
        WHERE project_id = '{project_id}'
        """)

    # ── Project Configurations ────────────────────────────────────────────────

    def save_project_config(
        self,
        project_id: str,
        interview_responses: dict[str, Any],
        created_by: str,
        change_reason: str = "initial configuration",
    ) -> str:
        """Save a versioned project configuration. Returns config_id."""
        # Find next version number
        rows = self._exec(f"""
        SELECT COALESCE(MAX(config_version), 0) AS max_v
        FROM {self._tbl("project_configurations")}
        WHERE project_id = '{project_id}'
        """)
        next_version = int(rows[0]["max_v"]) + 1 if rows else 1

        config_id = _uuid()
        now = _now()

        # Compute a deterministic manifest hash before serialising.
        # The hash identifies this exact wizard configuration for approver sign-off tracking.
        # Exclude any previously embedded hash to keep the hash stable across re-saves.
        clean_responses = {k: v for k, v in interview_responses.items() if k != "_manifest_hash"}
        canonical = json.dumps(clean_responses, sort_keys=True, ensure_ascii=True)
        manifest_hash = hashlib.sha256(canonical.encode()).hexdigest()
        # Embed hash in the blob so the dashboard and CI scripts can read it from one place
        responses_with_hash = {**clean_responses, "_manifest_hash": manifest_hash}
        responses_json = json.dumps(responses_with_hash).replace("'", "\\'")

        # Flatten key fields for efficient querying
        r = interview_responses
        inference_type = r.get("inference_type", "")
        batch_frequency = r.get("batch_frequency", "")
        sla_latency = r.get("sla_latency_ms") or "NULL"
        sla_uptime = r.get("sla_uptime_pct") or "NULL"
        retraining = r.get("retraining_strategy", "hybrid")
        retraining_sched = r.get("retraining_schedule", "0 2 * * *")
        drift_threshold = r.get("retraining_drift_threshold") or "NULL"
        fairness_thresh = r.get("fairness_threshold_pct") or "NULL"
        # Support both bias_test_types (list, new) and bias_test_type (str, legacy)
        bias_types_raw = r.get("bias_test_types", [r.get("bias_test_type", "aif360")])
        bias_type = bias_types_raw[0] if bias_types_raw else "aif360"
        canary_pct = r.get("canary_percentage") or "NULL"
        shadow = str(r.get("shadow_mode", True)).lower()
        shadow_days = r.get("shadow_mode_duration_days") or "NULL"
        rollback_thresh = r.get("rollback_error_threshold") or "NULL"
        rollback_window = r.get("rollback_time_window_minutes") or "NULL"
        # alert_destinations: derive from alert_destination_configs if available
        dest_configs = r.get("alert_destination_configs", [])
        alert_dests_list = (
            [c["destination"] for c in dest_configs] if dest_configs else r.get("alert_destinations", ["email"])
        )
        alert_thresh = r.get("alert_threshold_deviation_pct", r.get("performance_alert_threshold_pct")) or "NULL"
        code_review_count = r.get("code_review_count", 2)
        testing_thresh = r.get("testing_threshold_pct", 100)

        def _bool(key: str, default: bool = True) -> str:
            return str(r.get(key, default)).lower()

        self._exec(f"""
        INSERT INTO {self._tbl("project_configurations")}
          (config_id, project_id, config_version, created_timestamp, created_by,
           change_reason, interview_responses,
           inference_type, batch_frequency, sla_latency_ms, sla_uptime_pct,
           retraining_strategy, retraining_schedule, retraining_drift_threshold,
           fairness_attributes, fairness_threshold_pct, bias_test_type,
           canary_percentage, shadow_mode, shadow_mode_duration_days,
           rollback_error_threshold, rollback_time_window_minutes,
           alert_destinations, alert_threshold_deviation_pct,
           code_review_count, testing_threshold_pct,
           require_legal_review, require_business_approval,
           require_security_scan, require_end_to_end_test,
           monitor_data_drift, monitor_performance_drift, monitor_endpoint_uptime)
        VALUES
          ('{config_id}', '{project_id}', {next_version}, '{now}', '{created_by}',
           '{change_reason}', '{responses_json}',
           '{inference_type}', '{batch_frequency}', {sla_latency}, {sla_uptime},
           '{retraining}', '{retraining_sched}', {drift_threshold},
           array({",".join(f"'{a}'" for a in r.get("fairness_attributes", []))}),
           {fairness_thresh}, '{bias_type}',
           {canary_pct}, {shadow}, {shadow_days},
           {rollback_thresh}, {rollback_window},
           array({",".join(f"'{d}'" for d in alert_dests_list)}),
           {alert_thresh},
           {code_review_count}, {testing_thresh},
           true, true,
           true, true,
           {_bool("monitor_data_drift")}, {_bool("monitor_performance_drift")},
           {_bool("monitor_endpoint_uptime")})
        """)
        return config_id

    def get_latest_project_config(self, project_id: str) -> dict[str, Any] | None:
        rows = self._exec(f"""
        SELECT * FROM {self._tbl("project_configurations")}
        WHERE project_id = '{project_id}'
        ORDER BY config_version DESC
        LIMIT 1
        """)
        return rows[0] if rows else None

    # ── Audit Logging ─────────────────────────────────────────────────────────

    def log_audit(
        self,
        action_type: str,
        actor_email: str,
        actor_role: str,
        resource_type: str,
        resource_id: str,
        project_id: str | None = None,
        model_id: str | None = None,
        approval_id: str | None = None,
        change_details: dict[str, Any] | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
        action_status: str = "success",
        error_message: str | None = None,
    ) -> None:
        audit_id = _uuid()
        now = _now()
        details_json = json.dumps(change_details or {}).replace("'", "\\'")
        project_id_val = f"'{project_id}'" if project_id else "NULL"
        model_id_val = f"'{model_id}'" if model_id else "NULL"
        approval_id_val = f"'{approval_id}'" if approval_id else "NULL"
        old_val = f"'{old_value}'" if old_value else "NULL"
        new_val = f"'{new_value}'" if new_value else "NULL"
        err_val = f"'{error_message}'" if error_message else "NULL"

        # Best-effort — don't let audit failures break the main flow
        try:
            self._exec(f"""
            INSERT INTO {self._tbl("audit_logs")}
              (audit_id, event_timestamp, action_type,
               model_id, project_id, approval_id,
               actor_email, actor_role, resource_type, resource_id,
               change_details, old_value, new_value,
               action_status, error_message, is_immutable)
            VALUES
              ('{audit_id}', '{now}', '{action_type}',
               {model_id_val}, {project_id_val}, {approval_id_val},
               '{actor_email}', '{actor_role}', '{resource_type}', '{resource_id}',
               '{details_json}', {old_val}, {new_val},
               '{action_status}', {err_val}, true)
            """)
        except Exception:
            pass  # audit must never crash the calling operation

    # ── Installation Config ───────────────────────────────────────────────────

    def get_installation_config(self) -> dict[str, Any] | None:
        rows = self._exec(f"""
        SELECT * FROM {self._tbl("installation_config")}
        WHERE is_active = true
        ORDER BY config_version DESC
        LIMIT 1
        """)
        return rows[0] if rows else None

    def save_installation_config(self, config: dict[str, Any], created_by: str) -> str:
        # Deactivate previous active config
        self._exec(f"""
        UPDATE {self._tbl("installation_config")}
        SET is_active = false
        WHERE is_active = true
        """)

        rows = self._exec(f"""
        SELECT COALESCE(MAX(config_version), 0) AS max_v
        FROM {self._tbl("installation_config")}
        """)
        next_version = int(rows[0]["max_v"]) + 1 if rows else 1

        config_id = _uuid()
        now = _now()
        persona_json = json.dumps(config.get("personas", {})).replace("'", "\\'")
        monitoring_json = json.dumps(config.get("monitoring_defaults", {})).replace("'", "\\'")
        approval_json = json.dumps(config.get("approval_workflow_defaults", {})).replace("'", "\\'")
        frameworks = json.dumps(config.get("compliance_frameworks", [])).replace("'", "\\'")

        self._exec(f"""
        INSERT INTO {self._tbl("installation_config")}
          (config_id, config_version, created_timestamp, created_by,
           org_name, regulated_industry, compliance_frameworks, support_email,
           deployment_pattern, primary_cloud, github_org,
           persona_config, monitoring_defaults, approval_workflow_defaults, is_active)
        VALUES
          ('{config_id}', {next_version}, '{now}', '{created_by}',
           '{config.get("org_name", "")}',
           '{config.get("regulated_industry", "")}',
           array({",".join(f"'{f}'" for f in config.get("compliance_frameworks", []))}),
           '{config.get("support_email", "")}',
           '{config.get("deployment_pattern", "single_workspace")}',
           '{config.get("primary_cloud", "")}',
           '{config.get("github_org", "")}',
           '{persona_json}', '{monitoring_json}', '{approval_json}', true)
        """)
        return config_id

    # ── Data Contracts ────────────────────────────────────────────────────────

    def list_contracts_for_project(self, project_id: str) -> list[dict[str, Any]]:
        return self._exec(f"""
        SELECT * FROM {self._tbl("data_contracts")}
        WHERE project_id = '{project_id}' AND is_active = true
        ORDER BY contract_name
        """)

    def get_contract(self, contract_id: str) -> dict[str, Any] | None:
        rows = self._exec(f"SELECT * FROM {self._tbl('data_contracts')} WHERE contract_id = '{contract_id}'")
        return rows[0] if rows else None

    def get_contract_columns(self, contract_id: str) -> list[dict[str, Any]]:
        return self._exec(f"""
        SELECT * FROM {self._tbl("data_contract_columns")}
        WHERE contract_id = '{contract_id}'
        ORDER BY column_order
        """)

    def create_contract(
        self,
        project_id: str,
        contract_name: str,
        contract_type: str,
        uc_path: str,
        owner_email: str,
        purpose: str = "",
    ) -> str:
        contract_id = _uuid()
        now = _now()
        purpose_esc = purpose.replace("'", "\\'")
        self._exec(f"""
        INSERT INTO {self._tbl("data_contracts")}
          (contract_id, project_id, contract_type, contract_name, contract_version,
           uc_path, purpose, owner_email,
           is_active, is_validated,
           created_timestamp, created_by, last_updated, last_updated_by)
        VALUES
          ('{contract_id}', '{project_id}', '{contract_type}', '{contract_name}', 1,
           '{uc_path}', '{purpose_esc}', '{owner_email}',
           true, false,
           '{now}', '{owner_email}', '{now}', '{owner_email}')
        """)
        return contract_id

    def save_contract_columns(
        self,
        contract_id: str,
        columns: list[dict[str, Any]],
        created_by: str,
    ) -> None:
        """Replace all columns for a contract (delete + reinsert for simplicity)."""
        self._exec(f"DELETE FROM {self._tbl('data_contract_columns')} WHERE contract_id = '{contract_id}'")
        now = _now()
        for i, col in enumerate(columns):
            col_id = _uuid()
            name = col.get("name", "").replace("'", "\\'")
            desc = col.get("description", "").replace("'", "\\'")
            dtype = col.get("data_type", "string")
            nullable = str(col.get("is_nullable", True)).lower()
            pii = col.get("pii_level", "none")
            classification = col.get("data_classification", "internal")
            is_fairness = str(col.get("is_fairness_attribute", False)).lower()
            is_required = str(col.get("is_required_for_quality", True)).lower()
            monitor_drift = str(col.get("monitor_for_drift", True)).lower()
            quality_rules = json.dumps(col.get("quality_rules", {})).replace("'", "\\'")
            self._exec(f"""
            INSERT INTO {self._tbl("data_contract_columns")}
              (column_id, contract_id, column_order, column_name, column_description,
               data_type, is_nullable, pii_level, data_classification,
               is_fairness_attribute, is_required_for_quality, monitor_for_drift,
               quality_rules, created_timestamp, created_by, last_updated, last_updated_by)
            VALUES
              ('{col_id}', '{contract_id}', {i}, '{name}', '{desc}',
               '{dtype}', {nullable}, '{pii}', '{classification}',
               {is_fairness}, {is_required}, {monitor_drift},
               '{quality_rules}', '{now}', '{created_by}', '{now}', '{created_by}')
            """)

    def bump_contract_version(self, contract_id: str, updated_by: str, description: str = "") -> None:
        now = _now()
        desc_esc = description.replace("'", "\\'")
        self._exec(f"""
        UPDATE {self._tbl("data_contracts")}
        SET contract_version = contract_version + 1,
            last_updated = '{now}',
            last_updated_by = '{updated_by}',
            change_description = '{desc_esc}'
        WHERE contract_id = '{contract_id}'
        """)

    # ── Approvals ─────────────────────────────────────────────────────────────

    def create_approval_request(
        self,
        model_id: str,
        approval_type: str,
        approval_gate: str,
        requested_by: str,
        required_count: int = 1,
    ) -> str:
        approval_id = _uuid()
        now = _now()
        self._exec(f"""
        INSERT INTO {self._tbl("approvals")}
          (approval_id, model_id, approval_type, approval_gate,
           requested_timestamp, requested_by, required_count,
           approval_responses, approved_count, rejected_count, status,
           override_requested, created_timestamp)
        VALUES
          ('{approval_id}', '{model_id}', '{approval_type}', '{approval_gate}',
           '{now}', '{requested_by}', {required_count},
           '[]', 0, 0, 'pending',
           false, '{now}')
        """)
        return approval_id

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return self._exec(f"""
        SELECT a.*, p.project_name, p.team_name
        FROM {self._tbl("approvals")} a
        LEFT JOIN {self._tbl("models")} m ON a.model_id = m.model_id
        LEFT JOIN {self._tbl("projects")} p ON m.project_id = p.project_id
        WHERE a.status = 'pending'
        ORDER BY a.requested_timestamp DESC
        """)

    def list_approval_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._exec(f"""
        SELECT a.*, p.project_name
        FROM {self._tbl("approvals")} a
        LEFT JOIN {self._tbl("models")} m ON a.model_id = m.model_id
        LEFT JOIN {self._tbl("projects")} p ON m.project_id = p.project_id
        WHERE a.status != 'pending'
        ORDER BY a.completed_timestamp DESC
        LIMIT {limit}
        """)

    def submit_approval_decision(
        self,
        approval_id: str,
        decision: str,
        approver_email: str,
        comment: str = "",
    ) -> None:
        """Record one approver's decision. Sets status=approved/rejected when threshold met."""
        now = _now()
        comment_esc = comment.replace("'", "\\'")

        # Fetch current state
        rows = self._exec(f"SELECT * FROM {self._tbl('approvals')} WHERE approval_id = '{approval_id}'")
        if not rows:
            raise ValueError(f"Approval {approval_id} not found")
        current = rows[0]

        try:
            responses = json.loads(current.get("approval_responses") or "[]")
        except Exception:
            responses = []

        responses.append(
            {
                "approved_by": approver_email,
                "approved_timestamp": now,
                "approval_decision": decision,
                "comment": comment,
            }
        )
        responses_json = json.dumps(responses).replace("'", "\\'")

        approved = sum(1 for r in responses if r["approval_decision"] == "approve")
        rejected = sum(1 for r in responses if r["approval_decision"] == "reject")
        required = int(current.get("required_count") or 1)

        if rejected > 0:
            new_status = "rejected"
        elif approved >= required:
            new_status = "approved"
        else:
            new_status = "pending"

        completed_val = f"'{now}'" if new_status != "pending" else "NULL"
        self._exec(f"""
        UPDATE {self._tbl("approvals")}
        SET approval_responses = '{responses_json}',
            approved_count = {approved},
            rejected_count = {rejected},
            status = '{new_status}',
            completed_timestamp = {completed_val}
        WHERE approval_id = '{approval_id}'
        """)

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        rows = self._exec(f"SELECT * FROM {self._tbl('approvals')} WHERE approval_id = '{approval_id}'")
        return rows[0] if rows else None

    # ── Drift & Monitoring (read-only queries) ────────────────────────────────

    def list_recent_drift_results(self, model_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return self._exec(f"""
        SELECT * FROM {self._tbl("drift_detection_results")}
        WHERE model_id = '{model_id}'
        ORDER BY measurement_timestamp DESC
        LIMIT {limit}
        """)

    def list_recent_alerts(self, model_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._exec(f"""
        SELECT ah.*, a.alert_name, a.metric_name, a.severity
        FROM {self._tbl("alert_history")} ah
        JOIN {self._tbl("alerts")} a ON ah.alert_id = a.alert_id
        WHERE ah.model_id = '{model_id}'
        ORDER BY ah.triggered_timestamp DESC
        LIMIT {limit}
        """)

    def list_performance_history(self, model_id: str, limit: int = 30) -> list[dict[str, Any]]:
        return self._exec(f"""
        SELECT * FROM {self._tbl("model_performance")}
        WHERE model_id = '{model_id}'
        ORDER BY measurement_timestamp DESC
        LIMIT {limit}
        """)
