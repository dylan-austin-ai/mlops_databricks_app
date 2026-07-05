"""Reconciliation Service — keeps mlops.* an honest index over Databricks (§3, §21.1).

Databricks is the ground truth (design tenet 1); these passes refresh the
control plane's denormalized views of it:

  reconcile_model_aliases   UC registry aliases → mlops.model_versions
                            (current_aliases, last_reconciled_timestamp, §7.3)
  reconcile_costs           system.billing.usage joined on project_id resource
                            tags → mlops.cost_tracking (§17.3)

Every pass runs inside a self-monitoring wrapper (§21.1): rows examined/changed
land in mlops.reconciliation_runs, and a pass that previously changed rows but
suddenly changes zero is recorded as a *warning* — the classic signature of an
upstream system-table schema change silently breaking a join.

Runs on the scheduled-job pattern (§3) — never from the Streamlit request path.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from services.registry_service import RegistryService
from services.state_service import StateService

_ALIAS_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


@dataclass
class ReconcileRunResult:
    job_name: str
    rows_examined: int
    rows_changed: int
    status: str  # ok | warning | failed
    detail: str = ""


class ReconciliationService:
    def __init__(
        self,
        state: StateService | None = None,
        registry: RegistryService | None = None,
    ) -> None:
        self._state = state or StateService()
        self._registry = registry or RegistryService()

    def _tbl(self, name: str) -> str:
        return self._state._tbl(name)

    # ── §7.3: UC registry → model_versions index ────────────────────────────

    def reconcile_model_aliases(self) -> ReconcileRunResult:
        job = "model_alias_reconcile"
        try:
            rows = self._state._exec(
                f"""SELECT DISTINCT uc_full_name FROM {self._tbl("model_versions")}
                    WHERE uc_full_name IS NOT NULL"""
            )
            examined = len(rows)
            changed = 0
            for row in rows:
                uc_name = str(row["uc_full_name"])
                alias_map = self._registry.alias_map(uc_name)  # ground truth
                version_aliases: dict[int, list[str]] = {}
                for alias, version in alias_map.items():
                    if not _ALIAS_RE.match(alias):
                        raise ValueError(f"Unsafe alias name from registry: {alias!r}")
                    version_aliases.setdefault(int(version), []).append(alias)

                # Clear stale aliases on every tracked version, then set current.
                self._state._exec(
                    f"""UPDATE {self._tbl("model_versions")}
                        SET current_aliases = array(),
                            last_reconciled_timestamp = current_timestamp()
                        WHERE uc_full_name = :uc_name""",
                    {"uc_name": uc_name},
                )
                for version, aliases in version_aliases.items():
                    alias_literals = ", ".join(f"'{a}'" for a in sorted(aliases))
                    self._state._exec(
                        f"""UPDATE {self._tbl("model_versions")}
                            SET current_aliases = array({alias_literals}),
                                last_reconciled_timestamp = current_timestamp()
                            WHERE uc_full_name = :uc_name AND uc_version = :version""",
                        {"uc_name": uc_name, "version": version},
                    )
                    changed += 1
            return self._finish(job, "model_versions", examined, changed)
        except Exception as exc:
            return self._finish(job, "model_versions", 0, 0, error=str(exc))

    # ── §17.3: system.billing.usage → cost_tracking ─────────────────────────

    def reconcile_costs(self, days_back: int = 7) -> ReconcileRunResult:
        """Aggregate tagged usage into daily per-project cost rows.

        Joins list_prices for USD amounts; rows keyed on (project_id, date) via
        MERGE so re-runs refresh rather than duplicate. Only resources tagged
        with project_id (which every bundle-created resource is, §17.3) appear —
        untagged spend is intentionally out of scope for per-project rollups.
        """
        job = "cost_reconcile"
        merge_sql = f"""
        MERGE INTO {self._tbl("cost_tracking")} t
        USING (
          SELECT
            u.custom_tags['project_id'] AS project_id,
            u.usage_date AS date,
            sum(u.usage_quantity * lp.pricing.effective_list.default) AS total_cost_usd
          FROM system.billing.usage u
          JOIN system.billing.list_prices lp
            ON u.sku_name = lp.sku_name
           AND u.usage_start_time >= lp.price_start_time
           AND (lp.price_end_time IS NULL OR u.usage_start_time < lp.price_end_time)
          WHERE u.custom_tags['project_id'] IS NOT NULL
            AND u.usage_date >= date_sub(current_date(), :days_back)
          GROUP BY u.custom_tags['project_id'], u.usage_date
        ) s
        ON t.project_id = s.project_id AND t.date = s.date
        WHEN MATCHED THEN UPDATE SET
          t.total_cost_usd = s.total_cost_usd,
          t.compute_cost_usd = s.total_cost_usd
        WHEN NOT MATCHED THEN INSERT (
          cost_id, model_id, project_id, date,
          compute_cost_usd, total_cost_usd, billing_tag, created_timestamp
        ) VALUES (
          uuid(), 'project_scope', s.project_id, s.date,
          s.total_cost_usd, s.total_cost_usd, 'project_id', current_timestamp()
        )
        """
        try:
            rows = self._state._exec(merge_sql, {"days_back": days_back})
            changed = _merge_changed(rows)
            return self._finish(job, "cost_tracking", changed, changed)
        except Exception as exc:
            return self._finish(job, "cost_tracking", 0, 0, error=str(exc))

    def run_all(self) -> list[ReconcileRunResult]:
        return [self.reconcile_model_aliases(), self.reconcile_costs()]

    # ── §21.1 self-monitoring wrapper ────────────────────────────────────────

    def _finish(
        self,
        job_name: str,
        target_table: str,
        examined: int,
        changed: int,
        error: str = "",
    ) -> ReconcileRunResult:
        if error:
            status, detail = "failed", error
        elif changed == 0 and self._previous_run_changed_rows(job_name):
            # §21.1: a join that used to match rows now matching zero is a
            # schema-drift signal, not "nothing happened this period".
            status = "warning"
            detail = "changed 0 rows where previous runs changed >0 — possible upstream schema change"
        else:
            status, detail = "ok", ""

        self._state._exec(
            f"""INSERT INTO {self._tbl("reconciliation_runs")}
                (run_id, job_name, target_table, rows_examined, rows_changed,
                 status, detail, run_timestamp)
                VALUES (:run_id, :job_name, :target_table, :examined, :changed,
                        :status, :detail, current_timestamp())""",
            {
                "run_id": str(uuid.uuid4()),
                "job_name": job_name,
                "target_table": target_table,
                "examined": examined,
                "changed": changed,
                "status": status,
                "detail": detail,
            },
        )
        return ReconcileRunResult(job_name, examined, changed, status, detail)

    def _previous_run_changed_rows(self, job_name: str) -> bool:
        rows = self._state._exec(
            f"""SELECT rows_changed FROM {self._tbl("reconciliation_runs")}
                WHERE job_name = :job_name AND status IN ('ok', 'warning')
                ORDER BY run_timestamp DESC LIMIT 1""",
            {"job_name": job_name},
        )
        return bool(rows) and int(rows[0].get("rows_changed") or 0) > 0


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
