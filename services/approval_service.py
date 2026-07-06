"""Approval Service — concurrency-safe decision writes + revocation (§15.1, §15.4).

The decision write is a single Delta conditional MERGE: the match condition
(`status = 'pending' AND approved_count < required_count AND reviewer hasn't
already voted`) and all count/status arithmetic evaluate atomically SQL-side.
A concurrent submission that would over-count fails the match and gets a clear
"gate already satisfied" outcome — never a silent double-count. This reuses
Delta's native conflict detection (design tenet 6) instead of hand-rolled locks.

Revocation (§15.4) never edits or deletes the original approval — the table is
append-only. A revocation is a new record requiring sign-off from someone who
neither made the original approval nor requested the revocation (segregation
of duties). Per §29.3: revoking the approval behind the *current* champion
triggers the rollback saga; revoking a historical one opens an investigation.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from services.state_service import StateService


class ApprovalServiceError(RuntimeError):
    """Raised when an approval operation fails or preconditions aren't met."""


@dataclass
class DecisionOutcome:
    recorded: bool
    status: str  # pending | approved | rejected (post-decision state)
    approved_count: int
    required_count: int
    reason: str = ""  # human-readable explanation when not recorded


@dataclass
class RevocationOutcome:
    revocation_id: str
    recorded: bool
    revocation_status: str  # pending | approved | rejected
    original_approval_id: str = ""
    reason: str = ""


class ApprovalService:
    def __init__(self, state: StateService | None = None) -> None:
        self._state = state or StateService()

    def _tbl(self, name: str) -> str:
        return self._state._tbl(name)

    # ── §15.1 concurrency-safe decision write ────────────────────────────────

    def submit_decision(
        self,
        approval_id: str,
        decision: str,
        approver_email: str,
        comment: str = "",
    ) -> DecisionOutcome:
        """Record one reviewer's decision atomically.

        Exactly one of these outcomes happens, decided SQL-side:
          - recorded: the vote landed; status/counts reflect it
          - not recorded: gate already satisfied, already decided, or this
            reviewer already voted — with a clear reason, never an overwrite
        """
        if decision not in ("approve", "reject", "request_changes"):
            raise ApprovalServiceError(f"Invalid decision {decision!r} — approve, reject, or request_changes.")

        response_entry = json.dumps(
            {
                "approver_email": approver_email,
                "approval_decision": decision,
                "comment": comment,
            }
        )
        # Marker built from the same json.dumps encoding the entry uses, so the
        # already-voted check can't drift from the stored format. Quotes in the
        # JSON key/value make substring collisions between emails impossible.
        email_marker = "%" + json.dumps({"approver_email": approver_email})[1:-1] + "%"

        merge_sql = f"""
        MERGE INTO {self._tbl("approvals")} t
        USING (SELECT :approval_id AS approval_id) s
        ON t.approval_id = s.approval_id
           AND t.status = 'pending'
           AND coalesce(t.approved_count, 0) < coalesce(t.required_count, 1)
           AND NOT (coalesce(nullif(t.approval_responses, ''), '[]') LIKE :email_marker)
        WHEN MATCHED THEN UPDATE SET
          t.approval_responses = concat(
              substring(
                  coalesce(nullif(t.approval_responses, ''), '[]'),
                  1,
                  length(coalesce(nullif(t.approval_responses, ''), '[]')) - 1
              ),
              CASE WHEN coalesce(nullif(t.approval_responses, ''), '[]') = '[]'
                   THEN '' ELSE ',' END,
              :response_entry,
              ']'
          ),
          t.approved_count = coalesce(t.approved_count, 0)
              + CASE WHEN :decision = 'approve' THEN 1 ELSE 0 END,
          t.rejected_count = coalesce(t.rejected_count, 0)
              + CASE WHEN :decision = 'reject' THEN 1 ELSE 0 END,
          t.status = CASE
              WHEN :decision = 'reject' THEN 'rejected'
              WHEN :decision = 'approve'
                   AND coalesce(t.approved_count, 0) + 1 >= coalesce(t.required_count, 1)
                   THEN 'approved'
              ELSE t.status END,
          t.completed_timestamp = CASE
              WHEN :decision = 'reject'
                   OR (:decision = 'approve'
                       AND coalesce(t.approved_count, 0) + 1 >= coalesce(t.required_count, 1))
                   THEN current_timestamp()
              ELSE t.completed_timestamp END
        """
        params = {
            "approval_id": approval_id,
            "decision": decision,
            "response_entry": response_entry,
            "email_marker": email_marker,
        }
        rows = self._state._exec(merge_sql, params)
        affected = _merge_affected(rows)

        current = self._state.get_approval(approval_id)
        if current is None:
            raise ApprovalServiceError(f"Approval {approval_id} not found.")

        status = str(current.get("status") or "pending")
        approved = int(current.get("approved_count") or 0)
        required = int(current.get("required_count") or 1)

        if affected >= 1:
            self._state.log_audit(
                action_type=f"approval_{decision}",
                actor_email=approver_email,
                actor_role="approver",
                resource_type="approval",
                resource_id=approval_id,
                model_id=current.get("model_id"),
                approval_id=approval_id,
                change_details={"decision": decision, "comment": comment},
                new_value=status,
            )
            return DecisionOutcome(True, status, approved, required)

        # Not recorded — explain why from the row we just read.
        responses = str(current.get("approval_responses") or "")
        if email_marker.strip("%") in responses:
            reason = f"{approver_email} already submitted a decision on this gate."
        elif status != "pending":
            reason = f"Gate already {status}."
        elif approved >= required:
            reason = "Gate already satisfied."
        else:
            reason = "Decision not recorded — approval state changed concurrently; retry."
        return DecisionOutcome(False, status, approved, required, reason=reason)

    # ── §15.1: tie the reviewed plan to the approval record ─────────────────

    def attach_plan(self, approval_id: str, plan_path: str, plan_hash: str) -> None:
        """Record the exact reviewed plan file on the approval, so the saga can
        refuse to deploy anything else."""
        self._state._exec(
            f"""UPDATE {self._tbl("approvals")}
                SET plan_path = :plan_path, plan_hash = :plan_hash
                WHERE approval_id = :approval_id""",
            {"plan_path": plan_path, "plan_hash": plan_hash, "approval_id": approval_id},
        )

    # ── §15.4 revocation (append-only, segregation of duties) ───────────────

    def request_revocation(
        self,
        original_approval_id: str,
        reason: str,
        requested_by: str,
    ) -> RevocationOutcome:
        original = self._state.get_approval(original_approval_id)
        if original is None:
            raise ApprovalServiceError(f"Approval {original_approval_id} not found.")
        if str(original.get("status")) != "approved":
            raise ApprovalServiceError(f"Only approved gates can be revoked; this one is {original.get('status')!r}.")
        if str(original.get("approval_type")) == "revocation":
            raise ApprovalServiceError("A revocation record cannot itself be revoked.")

        revocation_id = str(uuid.uuid4())
        self._state._exec(
            f"""INSERT INTO {self._tbl("approvals")}
                (approval_id, model_id, approval_type, approval_gate,
                 requested_timestamp, requested_by, required_count,
                 approval_responses, approved_count, rejected_count,
                 status, revokes_approval_id, created_timestamp)
                VALUES
                (:revocation_id, :model_id, 'revocation', 'revocation',
                 current_timestamp(), :requested_by, 1,
                 :initial_responses, 0, 0,
                 'pending', :original_id, current_timestamp())""",
            {
                "revocation_id": revocation_id,
                "model_id": str(original.get("model_id") or ""),
                "requested_by": requested_by,
                "initial_responses": json.dumps([{"requested_by": requested_by, "reason": reason}]),
                "original_id": original_approval_id,
            },
        )
        self._state.log_audit(
            action_type="revocation_requested",
            actor_email=requested_by,
            actor_role="requester",
            resource_type="approval",
            resource_id=original_approval_id,
            model_id=original.get("model_id"),
            approval_id=revocation_id,
            change_details={"reason": reason},
        )
        return RevocationOutcome(revocation_id, True, "pending", original_approval_id)

    def decide_revocation(
        self,
        revocation_id: str,
        decision: str,
        approver_email: str,
        comment: str = "",
    ) -> RevocationOutcome:
        """Approve/reject a revocation. Fails closed on segregation-of-duties:
        the decider can be neither an approver of the original gate nor the
        person who requested the revocation."""
        revocation = self._state.get_approval(revocation_id)
        if revocation is None or str(revocation.get("approval_type")) != "revocation":
            raise ApprovalServiceError(f"Revocation {revocation_id} not found.")

        original_id = str(revocation.get("revokes_approval_id") or "")
        original = self._state.get_approval(original_id) if original_id else None
        if original is None:
            raise ApprovalServiceError(f"Revocation {revocation_id} references missing approval {original_id!r}.")

        if approver_email == str(revocation.get("requested_by")):
            raise ApprovalServiceError("Segregation of duties: the revocation requester cannot approve it.")
        original_voters = {r.get("approver_email") for r in _parse_responses(original.get("approval_responses"))}
        if approver_email in original_voters:
            raise ApprovalServiceError(
                "Segregation of duties: an approver of the original gate cannot decide its revocation."
            )

        outcome = self.submit_decision(revocation_id, decision, approver_email, comment)
        return RevocationOutcome(
            revocation_id=revocation_id,
            recorded=outcome.recorded,
            revocation_status=outcome.status,
            original_approval_id=original_id,
            reason=outcome.reason,
        )


def _parse_responses(raw: Any) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _merge_affected(rows: list[dict[str, Any]]) -> int:
    """Extract affected-row count from a MERGE result set (column names vary)."""
    if not rows:
        return 0
    row = rows[0]
    for key in ("num_affected_rows", "num_updated_rows"):
        if key in row and row[key] is not None:
            return int(row[key])
    return 0
