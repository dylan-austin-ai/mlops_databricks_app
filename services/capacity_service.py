"""Capacity Service — workspace-level resource pressure and control-plane
budget, run alongside the Reconciliation Service (§17.4, §19.2, phase 13).

Two independent concerns share this module because the roadmap phases them
together, not because they're one mechanism:

  snapshot_capacity()           job/endpoint/concurrent-run counts vs an
                                 internally-set alert threshold (§19.2) —
                                 Databricks doesn't publish a per-workspace
                                 endpoint ceiling, so this flags pressure
                                 before a real limit is hit instead of after.
  reconcile_control_plane_cost() system.billing.usage tagged
                                 component=control_plane → its own cost line,
                                 separate from per-project mlops.cost_tracking
                                 (§17.4) — the control plane's own overhead
                                 shouldn't hide inside a project's bill.

Write methods (snapshot_capacity, reconcile_control_plane_cost) run on the
scheduled-job pattern, same as ReconciliationService. Read methods
(latest_capacity_snapshot, control_plane_budget_status) are cheap table
reads for Portfolio Analytics to render without hitting the Jobs/Serving
Endpoints APIs on every page load.

Budget thresholds are config-driven placeholders (owner decision 2026-07-07,
DECISIONS_NEEDED #3) — surfaced as PLACEHOLDER in the UI, not presented as a
real number until the owner sets one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from config import AppConfig, get_config
from services.state_service import StateService

CONTROL_PLANE_BUDGET_IS_PLACEHOLDER = True


@dataclass
class CapacitySnapshot:
    job_count: int
    endpoint_count: int
    concurrent_run_count: int
    endpoint_warn_threshold: int
    status: str  # ok | warning
    detail: str = ""


@dataclass
class ControlPlaneBudgetStatus:
    total_cost_usd: float
    warn_threshold_usd: float
    crit_threshold_usd: float
    status: str  # ok | warning | critical
    is_placeholder: bool = CONTROL_PLANE_BUDGET_IS_PLACEHOLDER


class CapacityService:
    def __init__(self, config: AppConfig | None = None, state: StateService | None = None, ws: Any = None) -> None:
        self._cfg = config or get_config()
        self._state = state or StateService(config=self._cfg)
        self._ws_override = ws  # injectable for tests

    def _ws(self) -> Any:
        if self._ws_override is not None:
            return self._ws_override
        from databricks.sdk import WorkspaceClient

        return WorkspaceClient(host=self._cfg.databricks_host, token=self._cfg.databricks_token, auth_type="pat")

    def _tbl(self, name: str) -> str:
        return self._state._tbl(name)

    # ── §19.2: workspace capacity snapshot ──────────────────────────────────

    def snapshot_capacity(self) -> CapacitySnapshot:
        ws = self._ws()
        job_count = sum(1 for _ in ws.jobs.list())
        endpoint_count = sum(1 for _ in ws.serving_endpoints.list())
        concurrent_run_count = sum(1 for _ in ws.jobs.list_runs(active_only=True))

        threshold = self._cfg.capacity_endpoint_warn_threshold
        if endpoint_count >= threshold:
            status = "warning"
            detail = f"{endpoint_count} serving endpoints >= warn threshold {threshold} (§19.2)"
        else:
            status, detail = "ok", ""

        self._state._exec(
            f"""INSERT INTO {self._tbl("capacity_snapshots")}
                (snapshot_id, measured_timestamp, job_count, endpoint_count,
                 concurrent_run_count, endpoint_warn_threshold, status, detail)
                VALUES (:snapshot_id, current_timestamp(), :job_count, :endpoint_count,
                        :concurrent_run_count, :threshold, :status, :detail)""",
            {
                "snapshot_id": str(uuid.uuid4()),
                "job_count": job_count,
                "endpoint_count": endpoint_count,
                "concurrent_run_count": concurrent_run_count,
                "threshold": threshold,
                "status": status,
                "detail": detail,
            },
        )
        return CapacitySnapshot(job_count, endpoint_count, concurrent_run_count, threshold, status, detail)

    def latest_capacity_snapshot(self) -> CapacitySnapshot | None:
        rows = self._state._exec(
            f"""SELECT job_count, endpoint_count, concurrent_run_count,
                       endpoint_warn_threshold, status, detail
                FROM {self._tbl("capacity_snapshots")}
                ORDER BY measured_timestamp DESC LIMIT 1"""
        )
        if not rows:
            return None
        row = rows[0]
        return CapacitySnapshot(
            job_count=int(row["job_count"] or 0),
            endpoint_count=int(row["endpoint_count"] or 0),
            concurrent_run_count=int(row["concurrent_run_count"] or 0),
            endpoint_warn_threshold=int(row["endpoint_warn_threshold"] or 0),
            status=str(row["status"]),
            detail=str(row.get("detail") or ""),
        )

    # ── §17.4: control-plane cost reconciliation + budget status ────────────

    def reconcile_control_plane_cost(self, days_back: int = 30) -> int:
        """MERGE component=control_plane tagged usage into daily rows, keyed
        on date so re-runs refresh rather than duplicate (mirrors
        ReconciliationService.reconcile_costs's per-project MERGE)."""
        merge_sql = f"""
        MERGE INTO {self._tbl("control_plane_costs")} t
        USING (
          SELECT
            u.usage_date AS date,
            sum(u.usage_quantity * lp.pricing.effective_list.default) AS total_cost_usd
          FROM system.billing.usage u
          JOIN system.billing.list_prices lp
            ON u.sku_name = lp.sku_name
           AND u.usage_start_time >= lp.price_start_time
           AND (lp.price_end_time IS NULL OR u.usage_start_time < lp.price_end_time)
          WHERE u.custom_tags['component'] = 'control_plane'
            AND u.usage_date >= date_sub(current_date(), :days_back)
          GROUP BY u.usage_date
        ) s
        ON t.date = s.date
        WHEN MATCHED THEN UPDATE SET
          t.total_cost_usd = s.total_cost_usd
        WHEN NOT MATCHED THEN INSERT (
          control_plane_cost_id, date, total_cost_usd, created_timestamp
        ) VALUES (
          uuid(), s.date, s.total_cost_usd, current_timestamp()
        )
        """
        rows = self._state._exec(merge_sql, {"days_back": days_back})
        return _merge_changed(rows)

    def control_plane_budget_status(self, days_back: int = 30) -> ControlPlaneBudgetStatus:
        rows = self._state._exec(
            f"""SELECT sum(total_cost_usd) AS total
                FROM {self._tbl("control_plane_costs")}
                WHERE date >= date_sub(current_date(), :days_back)""",
            {"days_back": days_back},
        )
        total = float(rows[0].get("total") or 0) if rows else 0.0
        warn = self._cfg.control_plane_budget_warn_usd
        crit = self._cfg.control_plane_budget_crit_usd
        if total >= crit:
            status = "critical"
        elif total >= warn:
            status = "warning"
        else:
            status = "ok"
        return ControlPlaneBudgetStatus(total, warn, crit, status)


def _merge_changed(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    row = rows[0]
    total = 0
    for key in ("num_inserted_rows", "num_updated_rows"):
        if key in row and row[key] is not None:
            total += int(row[key])
    if total == 0 and row.get("num_affected_rows") is not None:
        total = int(row["num_affected_rows"])
    return total
