"""Databricks SQL warehouse query helpers for the wizard and monitoring features.

Provides schema inference from Unity Catalog tables, org-team lookups from
installation_config, and per-field drift data for the monitoring dashboard.

Reuses the same Statement Execution API pattern as StateService so no
additional authentication is needed.
"""

from __future__ import annotations

import time
from typing import Any

from config import AppConfig, get_config


class DbService:
    """SQL warehouse queries for schema inference and monitoring data."""

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

    def _exec(self, sql: str, timeout_s: int = 30) -> list[dict[str, Any]]:
        from databricks.sdk.service.sql import StatementState

        ws = self._workspace()
        resp = ws.statement_execution.execute_statement(
            warehouse_id=self._cfg.warehouse_id,
            statement=sql,
            wait_timeout=f"{timeout_s}s",
        )

        state = resp.status.state if resp.status else None
        while state not in (
            StatementState.SUCCEEDED,
            StatementState.FAILED,
            StatementState.CANCELED,
            StatementState.CLOSED,
        ):
            time.sleep(0.5)
            resp = ws.statement_execution.get_statement(resp.statement_id)
            state = resp.status.state if resp.status else None

        if state != StatementState.SUCCEEDED:
            err = getattr(resp.status, "error", None)
            raise RuntimeError(f"SQL failed: {getattr(err, 'message', str(err))}")

        if not resp.result or not resp.result.data_array:
            return []

        cols = [c.name for c in resp.manifest.schema.columns]
        return [dict(zip(cols, row)) for row in resp.result.data_array]

    # ── Schema inference ──────────────────────────────────────────────────────

    def infer_table_schema(self, table_path: str) -> list[dict[str, str]]:
        """Return column definitions for a Unity Catalog table.

        Args:
            table_path: Three-part UC path (catalog.schema.table).

        Returns:
            List of {name, data_type, comment} dicts.
            Partition boundary rows and metadata rows are excluded.
        """
        rows = self._exec(f"DESCRIBE TABLE {table_path}")
        return [
            {
                "name": r["col_name"],
                "data_type": r.get("data_type", ""),
                "comment": r.get("comment", ""),
            }
            for r in rows
            if r.get("col_name") and not r["col_name"].startswith("#")
        ]

    # ── Org configuration ─────────────────────────────────────────────────────

    def get_org_teams(self) -> list[str]:
        """Read available team names from installation_config.

        Returns empty list if the table does not exist or is unreachable.
        """
        try:
            rows = self._exec(
                f"SELECT DISTINCT team_name "
                f"FROM {self._cfg.catalog}.{self._cfg.schema}.installation_config "
                f"WHERE team_name IS NOT NULL ORDER BY team_name"
            )
            return [r["team_name"] for r in rows if r.get("team_name")]
        except Exception:
            return []

    # ── Field-level drift data ────────────────────────────────────────────────

    def get_field_drift_data(
        self,
        catalog: str,
        project_schema: str,
        limit_days: int = 30,
    ) -> dict[str, list[dict[str, Any]]]:
        """Read per-field drift statistics from the monitoring log table.

        Args:
            catalog: UC catalog name.
            project_schema: Schema name (e.g. "customer_churn_dev").
            limit_days: How many days of history to fetch.

        Returns:
            Mapping of field_name → list of daily row dicts.
            Empty dict if the monitoring table does not exist yet.
        """
        try:
            rows = self._exec(
                f"""
                SELECT field_name, window_date,
                       mean_value, stddev_value, min_value, max_value,
                       psi_score, ks_pvalue, null_pct, n_rows
                FROM {catalog}.{project_schema}.monitoring_drift_log
                WHERE window_date >= DATE_SUB(CURRENT_DATE(), {limit_days})
                ORDER BY field_name, window_date
                """
            )
            result: dict[str, list] = {}
            for row in rows:
                field = row.get("field_name", "")
                if field:
                    result.setdefault(field, []).append(row)
            return result
        except Exception:
            return {}

    def get_baseline_stats(
        self,
        catalog: str,
        project_schema: str,
    ) -> dict[str, dict[str, Any]]:
        """Read per-field baseline statistics computed at training time.

        Returns:
            Mapping of field_name → {mean, stddev, min, max, null_pct,
            unique_count, top_values_json}.
            Empty dict if the monitoring_baseline table does not exist yet.
        """
        try:
            rows = self._exec(
                f"""
                SELECT field_name, mean_value, stddev_value,
                       min_value, max_value, null_pct, unique_count, top_values_json
                FROM {catalog}.{project_schema}.monitoring_baseline
                ORDER BY field_name
                """
            )
            return {
                r["field_name"]: {
                    "mean": r.get("mean_value"),
                    "stddev": r.get("stddev_value"),
                    "min": r.get("min_value"),
                    "max": r.get("max_value"),
                    "null_pct": r.get("null_pct"),
                    "unique_count": r.get("unique_count"),
                    "top_values": r.get("top_values_json", ""),
                }
                for r in rows
                if r.get("field_name")
            }
        except Exception:
            return {}
