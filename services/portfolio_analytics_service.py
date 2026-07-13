"""Portfolio Analytics Service — program-level rollups (§14).

Every metric here aggregates data the control plane already collects; this
service defines aggregation, not new raw collection. Metrics whose inputs
don't exist yet in this deployment (e.g. quality coverage needs live monitor
state, phase 6's attach path) are deliberately absent rather than fabricated.

§14.4 comparability rule, enforced structurally: business-impact rollups are
returned split by confidence — a project whose business_value_fn review is
older than 365 days (or absent) lands in the low-confidence bucket, and the
two figures are never summed into one misleadingly precise total.

Runs read-only on the scheduled/refresh pattern; the page just renders it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.state_service import StateService

VALUE_FN_REVIEW_MAX_AGE_DAYS = 365

# §26.4: the de novo baseline — how long repo+schemas+endpoint+monitoring
# takes by hand — is the denominator Interview Speed is judged against.
# PLACEHOLDER: owner set 10 days on 2026-07-07 pending a real timed
# measurement (DECISIONS_NEEDED #6); replace both values together.
DE_NOVO_BASELINE_DAYS = 10
DE_NOVO_BASELINE_IS_PLACEHOLDER = True


@dataclass
class ImpactRollup:
    """§14.4: separate figures by confidence — never one blended number."""

    high_confidence_usd: float = 0.0
    high_confidence_projects: int = 0
    low_confidence_usd: float = 0.0
    low_confidence_projects: int = 0
    unreviewed_projects: list[str] = field(default_factory=list)


class PortfolioAnalyticsService:
    def __init__(self, state: StateService | None = None) -> None:
        self._state = state or StateService()

    def _tbl(self, name: str) -> str:
        return self._state._tbl(name)

    # ── Speed (§14.1): approval → deploy, joined on the reviewed plan hash ──

    def speed_metrics(self, days_back: int = 90) -> dict[str, Any]:
        rows = self._state._exec(
            f"""SELECT count(*) AS promotions,
                       avg(timestampdiff(HOUR, a.completed_timestamp,
                                         d.created_timestamp)) AS avg_approval_to_deploy_hours
                FROM {self._tbl("approvals")} a
                JOIN {self._tbl("bundle_deployments")} d ON d.plan_hash = a.plan_hash
                WHERE a.status = 'approved' AND d.status = 'deployed'
                  AND d.created_timestamp >= date_sub(current_timestamp(), :days_back)""",
            {"days_back": days_back},
        )
        row = rows[0] if rows else {}
        return {
            "promotions": int(row.get("promotions") or 0),
            "avg_approval_to_deploy_hours": (
                float(row["avg_approval_to_deploy_hours"])
                if row.get("avg_approval_to_deploy_hours") is not None
                else None
            ),
            "de_novo_baseline_days": DE_NOVO_BASELINE_DAYS,
            "de_novo_baseline_is_placeholder": DE_NOVO_BASELINE_IS_PLACEHOLDER,
        }

    # ── Reliability (§14.1): deploy failure + destroy rates ─────────────────

    def reliability_metrics(self, days_back: int = 90) -> dict[str, Any]:
        rows = self._state._exec(
            f"""SELECT status, count(*) AS n
                FROM {self._tbl("bundle_deployments")}
                WHERE created_timestamp >= date_sub(current_timestamp(), :days_back)
                GROUP BY status""",
            {"days_back": days_back},
        )
        counts = {str(r["status"]): int(r["n"]) for r in rows}
        total = sum(counts.values())
        failed = counts.get("failed", 0) + counts.get("verify_failed", 0)
        return {
            "deployments": total,
            "failed": failed,
            "failure_rate_pct": round(100.0 * failed / total, 2) if total else None,
            "by_status": counts,
        }

    # ── Cost (§14.1/§17.4): per-project totals, control plane separate ──────

    def cost_rollup(self, days_back: int = 30, group_by: str = "project") -> list[dict[str, Any]]:
        """Sliced by project (default, unchanged shape — `project_id` key),
        team, or deployment_type (IMG_1412 Cost Tracking gap).

        Environment and per-model slices aren't in this pass: system.billing
        usage tags resources with project_id only today (§17.3) — adding
        environment attribution means tagging bundle resources and widening
        reconcile_costs's MERGE key, not just this query. Per-model would
        currently just reproduce per-project: reconcile_costs always writes
        model_id='project_scope' (this app is one model per project), so
        there's no real per-model cost split to slice yet.
        """
        if group_by == "team":
            return self._state._exec(
                f"""SELECT p.team_name AS team_name, sum(c.total_cost_usd) AS total_usd
                    FROM {self._tbl("cost_tracking")} c
                    JOIN {self._tbl("projects")} p ON p.project_id = c.project_id
                    WHERE c.date >= date_sub(current_date(), :days_back)
                    GROUP BY p.team_name
                    ORDER BY total_usd DESC""",
                {"days_back": days_back},
            )
        if group_by == "deployment_type":
            return self._state._exec(
                f"""SELECT coalesce(latest.inference_type, 'unknown') AS deployment_type,
                           sum(c.total_cost_usd) AS total_usd
                    FROM {self._tbl("cost_tracking")} c
                    LEFT JOIN (
                      SELECT project_id, inference_type,
                             row_number() OVER (PARTITION BY project_id ORDER BY config_version DESC) AS rn
                      FROM {self._tbl("project_configurations")}
                    ) latest ON latest.project_id = c.project_id AND latest.rn = 1
                    WHERE c.date >= date_sub(current_date(), :days_back)
                    GROUP BY coalesce(latest.inference_type, 'unknown')
                    ORDER BY total_usd DESC""",
                {"days_back": days_back},
            )
        return self._state._exec(
            f"""SELECT project_id, sum(total_cost_usd) AS total_usd
                FROM {self._tbl("cost_tracking")}
                WHERE date >= date_sub(current_date(), :days_back)
                GROUP BY project_id
                ORDER BY total_usd DESC""",
            {"days_back": days_back},
        )

    # ── Reuse (§14.1 ← §8.5): same lineage query as the catalog, not a copy ─

    def reuse_metrics(self) -> dict[str, Any]:
        rows = self._state._exec(
            f"""SELECT count(*) AS shared_features,
                       sum(CASE WHEN u.used_by_models >= 2 THEN 1 ELSE 0 END) AS multi_consumer_features
                FROM {self._tbl("features")} f
                LEFT JOIN (
                  SELECT feature_id, count(DISTINCT model_id) AS used_by_models
                  FROM {self._tbl("feature_lineage")}
                  LATERAL VIEW explode(downstream_model_ids) AS model_id
                  GROUP BY feature_id
                ) u ON u.feature_id = f.feature_id
                WHERE f.is_active = true AND f.is_shared = true"""
        )
        row = rows[0] if rows else {}
        return {
            "shared_features": int(row.get("shared_features") or 0),
            "multi_consumer_features": int(row.get("multi_consumer_features") or 0),
        }

    # ── Governance coverage (§14.1 ← §20.5): revalidation debt counts here ──

    def revalidation_metrics(self) -> dict[str, Any]:
        """Models whose policy-pack revalidation window has lapsed. Anything
        due or still in re-review counts *against* governance coverage —
        not just "eventually" (§20.5)."""
        rows = self._state._exec(
            f"""SELECT status, on_due_action, count(*) AS n
                FROM {self._tbl("revalidation_flags")}
                WHERE status IN ('due', 'in_revalidation')
                GROUP BY status, on_due_action"""
        )
        due = sum(int(r["n"]) for r in rows if str(r["status"]) == "due")
        in_review = sum(int(r["n"]) for r in rows if str(r["status"]) == "in_revalidation")
        blocked = sum(
            int(r["n"]) for r in rows if str(r.get("on_due_action") or "") in ("block_new_traffic", "block_all_traffic")
        )
        return {
            "revalidation_due": due,
            "in_revalidation": in_review,
            "promotion_blocked": blocked,
            "governance_coverage_penalty": due + in_review,
        }

    # ── Business impact with comparability (§14.2/§14.4) ────────────────────

    def business_impact_rollup(self, days_back: int = 90) -> ImpactRollup:
        rows = self._state._exec(
            f"""SELECT bi.project_id,
                       sum(coalesce(bi.revenue_lift_usd, 0)
                           + coalesce(bi.loss_avoided_usd, 0)) AS impact_usd,
                       max(CASE
                             WHEN fn.last_reviewed_date IS NOT NULL
                              AND fn.last_reviewed_date >= date_sub(current_date(),
                                                                    {VALUE_FN_REVIEW_MAX_AGE_DAYS})
                             THEN 1 ELSE 0 END) AS fn_reviewed
                FROM {self._tbl("business_impact")} bi
                LEFT JOIN {self._tbl("business_value_fns")} fn
                  ON fn.project_id = bi.project_id
                WHERE bi.period_end >= date_sub(current_date(), :days_back)
                GROUP BY bi.project_id""",
            {"days_back": days_back},
        )
        rollup = ImpactRollup()
        for row in rows:
            usd = float(row.get("impact_usd") or 0)
            if int(row.get("fn_reviewed") or 0) == 1:
                rollup.high_confidence_usd += usd
                rollup.high_confidence_projects += 1
            else:
                rollup.low_confidence_usd += usd
                rollup.low_confidence_projects += 1
                rollup.unreviewed_projects.append(str(row["project_id"]))
        return rollup
