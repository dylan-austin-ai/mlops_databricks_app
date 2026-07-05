"""Feedback Join Service — joins predictions to eventual ground truth (§10.2).

Runs on the same scheduled-job pattern as the Reconciliation Service (§3) —
never called synchronously from the Streamlit request path. Each run:

  1. finds contracts declaring a label source (§10.1)
  2. MERGEs newly-labeled predictions into mlops.label_feedback, keyed by the
     client_request_id captured at serving time (§9.2) — idempotent by PK
  3. records live_accuracy into mlops.model_performance (§10.3)
  4. flags a retrain candidate once enough new labels accumulate —
     Data Availability Retraining as a real trigger, not a manual button

Table names come from app-owned contract rows, not user free-text, but are
still validated as UC identifiers before entering SQL — fail closed (tenet 5).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from services.state_service import StateService

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){0,2}$")


class FeedbackJoinError(RuntimeError):
    """Raised when a feedback-join operation fails or preconditions aren't met."""


def _safe_identifier(name: str, what: str) -> str:
    if not _IDENTIFIER_RE.match(name or ""):
        raise FeedbackJoinError(f"Unsafe {what} identifier: {name!r}")
    return name


@dataclass
class JoinRunResult:
    project_id: str
    label_source_table: str
    new_labels_joined: int
    live_accuracy: float | None = None
    retrain_flagged: bool = False


class FeedbackJoinService:
    def __init__(self, state: StateService | None = None) -> None:
        self._state = state or StateService()

    def _tbl(self, name: str) -> str:
        return self._state._tbl(name)

    # ── §10.1 declared label sources ─────────────────────────────────────────

    def declared_label_sources(self) -> list[dict[str, Any]]:
        return self._state._exec(
            f"""SELECT contract_id, project_id, label_source_table,
                       label_source_column, label_join_key, label_latency_days
                FROM {self._tbl("data_contracts")}
                WHERE is_active = true AND label_source_table IS NOT NULL"""
        )

    # ── §10.2 the join ───────────────────────────────────────────────────────

    def join_new_labels(
        self,
        *,
        project_id: str,
        inference_table: str,
        label_source_table: str,
        label_source_column: str,
        label_join_key: str = "client_request_id",
        prediction_column: str = "prediction",
    ) -> int:
        """MERGE newly-labeled predictions into label_feedback. Idempotent:
        the PK on prediction_id means re-runs never duplicate rows."""
        inference = _safe_identifier(inference_table, "inference table")
        labels = _safe_identifier(label_source_table, "label source table")
        label_col = _safe_identifier(label_source_column, "label column")
        join_key = _safe_identifier(label_join_key, "join key column")
        pred_col = _safe_identifier(prediction_column, "prediction column")

        merge_sql = f"""
        MERGE INTO {self._tbl("label_feedback")} t
        USING (
          SELECT
            i.client_request_id AS prediction_id,
            :project_id AS project_id,
            CAST(i.{pred_col} AS STRING) AS predicted_value,
            CAST(l.{label_col} AS STRING) AS actual_label,
            :label_source_table AS label_source_table,
            i.request_time AS prediction_timestamp,
            l.arrived_timestamp AS label_arrived_timestamp,
            (unix_timestamp(l.arrived_timestamp) - unix_timestamp(i.request_time))
              / 86400.0 AS latency_days,
            CAST(i.{pred_col} AS STRING) = CAST(l.{label_col} AS STRING) AS correct
          FROM {inference} i
          JOIN {labels} l ON l.{join_key} = i.client_request_id
          WHERE i.client_request_id IS NOT NULL
        ) s
        ON t.prediction_id = s.prediction_id
        WHEN NOT MATCHED THEN INSERT (
          prediction_id, project_id, predicted_value, actual_label,
          label_source_table, prediction_timestamp, label_arrived_timestamp,
          latency_days, correct, created_timestamp
        ) VALUES (
          s.prediction_id, s.project_id, s.predicted_value, s.actual_label,
          s.label_source_table, s.prediction_timestamp, s.label_arrived_timestamp,
          s.latency_days, s.correct, current_timestamp()
        )
        """
        rows = self._state._exec(
            merge_sql,
            {"project_id": project_id, "label_source_table": label_source_table},
        )
        if not rows:
            return 0
        row = rows[0]
        for key in ("num_inserted_rows", "num_affected_rows"):
            if key in row and row[key] is not None:
                return int(row[key])
        return 0

    # ── §10.3 live accuracy ──────────────────────────────────────────────────

    def compute_live_accuracy(self, project_id: str, window_days: int = 30) -> tuple[float | None, int]:
        rows = self._state._exec(
            f"""SELECT avg(CASE WHEN correct THEN 1.0 ELSE 0.0 END) AS live_accuracy,
                       count(*) AS labels_count
                FROM {self._tbl("label_feedback")}
                WHERE project_id = :project_id
                  AND label_arrived_timestamp >= date_sub(current_timestamp(), :window_days)""",
            {"project_id": project_id, "window_days": window_days},
        )
        if not rows or rows[0].get("labels_count") in (None, 0, "0"):
            return None, 0
        acc = rows[0].get("live_accuracy")
        return (float(acc) if acc is not None else None), int(rows[0]["labels_count"])

    def record_live_accuracy(
        self,
        *,
        project_id: str,
        model_id: str,
        version_id: str,
        window_days: int = 30,
    ) -> float | None:
        accuracy, count = self.compute_live_accuracy(project_id, window_days)
        if accuracy is None:
            return None
        self._state._exec(
            f"""INSERT INTO {self._tbl("model_performance")}
                (performance_id, version_id, model_id, measurement_timestamp,
                 measurement_window, live_accuracy, live_accuracy_labels_count,
                 created_timestamp)
                VALUES (:performance_id, :version_id, :model_id, current_timestamp(),
                        :window, :live_accuracy, :labels_count, current_timestamp())""",
            {
                "performance_id": str(uuid.uuid4()),
                "version_id": version_id,
                "model_id": model_id,
                "window": f"last_{window_days}d",
                "live_accuracy": accuracy,
                "labels_count": count,
            },
        )
        return accuracy

    # ── §10.3 Data Availability Retraining trigger ──────────────────────────

    def check_retrain_trigger(
        self,
        *,
        project_id: str,
        last_training_timestamp: str,
        new_labels_threshold: int,
        actor_email: str = "feedback_join_service",
    ) -> bool:
        """Flag a retrain candidate once N new labeled examples accumulated
        since the last training run. Flags via the audit log — surfacing, not
        auto-retraining; the retraining job itself stays behind its gates."""
        rows = self._state._exec(
            f"""SELECT count(*) AS new_labels
                FROM {self._tbl("label_feedback")}
                WHERE project_id = :project_id
                  AND label_arrived_timestamp > :since""",
            {"project_id": project_id, "since": last_training_timestamp},
        )
        new_labels = int(rows[0]["new_labels"]) if rows else 0
        if new_labels < new_labels_threshold:
            return False

        self._state.log_audit(
            action_type="retrain_candidate_flagged",
            actor_email=actor_email,
            actor_role="feedback_join_service",
            resource_type="project",
            resource_id=project_id,
            project_id=project_id,
            change_details={
                "new_labels_since_last_training": new_labels,
                "threshold": new_labels_threshold,
                "last_training_timestamp": last_training_timestamp,
                "trigger": "data_availability_retraining (§10.3)",
            },
        )
        return True
