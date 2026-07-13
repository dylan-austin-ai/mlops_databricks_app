"""HITL Review Service — concurrency-safe per-prediction review queue (§11.2).

The decision write is a conditional MERGE guarded by `decision IS NULL`: two
reviewers opening the same pending prediction can't both submit — the second
gets a clear "already decided by {reviewer}" instead of a silent overwrite.
Same Delta-native pattern as the approval write-path (§15.1, design tenet 6).

SLA handling per the accepted §29.3 suggestion: a breach escalates to a backup
reviewer/MLOps and marks the row escalated — it never auto-approves. Fail
closed extends to timeouts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from services.notification_service import NotificationService
from services.state_service import StateService

VALID_DECISIONS = ("approved", "overridden", "rejected")


class HITLReviewError(RuntimeError):
    """Raised when a review operation fails or preconditions aren't met."""


@dataclass
class ReviewOutcome:
    recorded: bool
    reason: str = ""  # who already decided, when not recorded


class HITLReviewService:
    def __init__(self, state: StateService | None = None, notifications: NotificationService | None = None) -> None:
        self._state = state or StateService()
        self._notifications = notifications or NotificationService()

    def _tbl(self, name: str) -> str:
        return self._state._tbl(name)

    # ── queue ────────────────────────────────────────────────────────────────

    def enqueue(self, *, prediction_id: str, project_id: str) -> None:
        """Add a prediction to the review queue. Idempotent by PK."""
        self._state._exec(
            f"""MERGE INTO {self._tbl("hitl_reviews")} t
                USING (SELECT :prediction_id AS prediction_id) s
                ON t.prediction_id = s.prediction_id
                WHEN NOT MATCHED THEN INSERT
                  (prediction_id, project_id, presented_timestamp, escalated)
                VALUES (:prediction_id, :project_id, current_timestamp(), false)""",
            {"prediction_id": prediction_id, "project_id": project_id},
        )

    def pending(self, project_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Pending reviews, oldest first, joined to any async explanation that
        has landed (§11.2: the reviewer sees WHY, not just the raw output)."""
        where = "WHERE h.decision IS NULL"
        params: dict[str, Any] = {}
        if project_id:
            where += " AND h.project_id = :project_id"
            params["project_id"] = project_id
        return self._state._exec(
            f"""SELECT h.*, e.feature_contributions, e.confidence_bucket, e.resolved_alias
                FROM {self._tbl("hitl_reviews")} h
                LEFT JOIN {self._tbl("telemetry_enrichment")} e
                  ON e.client_request_id = h.prediction_id
                {where}
                ORDER BY h.presented_timestamp ASC
                LIMIT {int(limit)}""",
            params or None,
        )

    # ── §11.2 concurrency-safe decision ──────────────────────────────────────

    def decide(
        self,
        *,
        prediction_id: str,
        reviewer_email: str,
        decision: str,
        overridden_value: str = "",
        comment: str = "",
    ) -> ReviewOutcome:
        if decision not in VALID_DECISIONS:
            raise HITLReviewError(f"Invalid decision {decision!r} — one of {', '.join(VALID_DECISIONS)}.")
        if decision == "overridden" and not overridden_value:
            raise HITLReviewError("An overridden decision must carry the overridden_value.")

        rows = self._state._exec(
            f"""MERGE INTO {self._tbl("hitl_reviews")} t
                USING (SELECT :prediction_id AS prediction_id) s
                ON t.prediction_id = s.prediction_id AND t.decision IS NULL
                WHEN MATCHED THEN UPDATE SET
                  t.reviewer_email = :reviewer_email,
                  t.decision = :decision,
                  t.overridden_value = :overridden_value,
                  t.comment = :comment,
                  t.decision_timestamp = current_timestamp()""",
            {
                "prediction_id": prediction_id,
                "reviewer_email": reviewer_email,
                "decision": decision,
                "overridden_value": overridden_value,
                "comment": comment,
            },
        )
        affected = 0
        if rows:
            for key in ("num_affected_rows", "num_updated_rows"):
                if key in rows[0] and rows[0][key] is not None:
                    affected = int(rows[0][key])
                    break

        if affected >= 1:
            self._state.log_audit(
                action_type=f"hitl_{decision}",
                actor_email=reviewer_email,
                actor_role="hitl_reviewer",
                resource_type="prediction",
                resource_id=prediction_id,
                change_details={"decision": decision, "overridden_value": overridden_value},
            )
            return ReviewOutcome(True)

        current = self._state._exec(
            f"""SELECT reviewer_email, decision FROM {self._tbl("hitl_reviews")}
                WHERE prediction_id = :prediction_id""",
            {"prediction_id": prediction_id},
        )
        if not current:
            raise HITLReviewError(f"Prediction {prediction_id} is not in the review queue.")
        prior = current[0]
        return ReviewOutcome(
            False,
            reason=f"Already decided ({prior.get('decision')}) by {prior.get('reviewer_email')}.",
        )

    # ── §29.3: SLA breach escalates, never auto-approves ─────────────────────

    def escalate_sla_breaches(
        self,
        *,
        sla_minutes: int,
        project_id: str | None = None,
        escalated_by: str = "hitl_review_service",
    ) -> list[str]:
        """Mark pending reviews past the SLA as escalated and return their ids.

        Escalation surfaces the breach (audit + flag for backup-reviewer
        routing); the prediction stays pending — a timeout must never quietly
        become an approval.
        """
        where = (
            "t.decision IS NULL AND t.escalated = false AND t.presented_timestamp"
            " < timestampadd(MINUTE, -:sla_minutes, current_timestamp())"
        )
        params: dict[str, Any] = {"sla_minutes": sla_minutes}
        if project_id:
            where += " AND t.project_id = :project_id"
            params["project_id"] = project_id

        breached = self._state._exec(
            f"""SELECT prediction_id, project_id FROM {self._tbl("hitl_reviews")} t WHERE {where}""",
            params,
        )
        ids = [str(r["prediction_id"]) for r in breached]
        if not ids:
            return []

        self._state._exec(
            f"""UPDATE {self._tbl("hitl_reviews")} t SET escalated = true WHERE {where}""",
            params,
        )
        by_project: dict[str, list[str]] = {}
        for r in breached:
            prediction_id = str(r["prediction_id"])
            by_project.setdefault(str(r.get("project_id") or ""), []).append(prediction_id)
            self._state.log_audit(
                action_type="hitl_sla_escalated",
                actor_email=escalated_by,
                actor_role="hitl_review_service",
                resource_type="prediction",
                resource_id=prediction_id,
                change_details={
                    "sla_minutes": sla_minutes,
                    "note": "escalated to backup reviewer — never auto-approved (§29.3)",
                },
            )
        for proj_id, prediction_ids in by_project.items():
            if not proj_id:
                continue
            try:
                self._notify_escalation(proj_id, prediction_ids, sla_minutes)
            except Exception:
                pass  # escalation is already recorded; notification is best-effort
        return ids

    def _notify_escalation(self, project_id: str, prediction_ids: list[str], sla_minutes: int) -> None:
        """Routes to the project's configured alert destinations (§9's
        alert_destination_configs) — the app has no dedicated "backup
        reviewer" contact field, and this is the only "who to tell about an
        operational problem on this project" concept that already exists."""
        rows = self._state._exec(
            f"""SELECT interview_responses FROM {self._tbl("project_configurations")}
                WHERE project_id = :project_id ORDER BY config_version DESC LIMIT 1""",
            {"project_id": project_id},
        )
        if not rows:
            return
        try:
            responses = json.loads(str(rows[0].get("interview_responses") or "{}"))
        except (TypeError, ValueError):
            return
        destinations = responses.get("alert_destination_configs") or []
        if not destinations:
            return
        shown = ", ".join(prediction_ids[:10]) + (
            f" (+{len(prediction_ids) - 10} more)" if len(prediction_ids) > 10 else ""
        )
        self._notifications.send_all(
            destinations,
            f"HITL SLA breach — {len(prediction_ids)} prediction(s) escalated",
            f"{len(prediction_ids)} pending review(s) exceeded the {sla_minutes}-minute SLA and were "
            f"escalated to a backup reviewer — never auto-approved (§29.3). Prediction IDs: {shown}",
        )
