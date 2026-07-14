"""Monitoring Service — Lakehouse Monitoring cutover (§13, §27.2 phase 6).

Attaches a Databricks Lakehouse Monitor (InferenceLog profile) to each
project's Inference Table at deploy time, replacing hand-rolled KS-statistic
drift detection with the managed feature (design tenet 6).

The §10.3 synergy: once the Feedback Join Service has ground truth flowing,
`attach_label_column()` upgrades the monitor with a label column so Databricks
computes real accuracy/calibration natively — the custom live_accuracy field
stays only for domain metrics the platform doesn't know about.

Graceful degradation (§25): a workspace without Lakehouse Monitoring enabled
raises MonitoringUnavailable with a clear message — callers disable the
dependent UI affordance; nothing crashes.

Note on API churn (§13): current docs already mark an older quality_monitors
path as transitioning to "data profiling" naming. The SDK surface used here
(w.quality_monitors, MonitorInferenceLog) is what databricks-sdk in this repo
ships; re-verify on the first live attach before trusting it further.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import AppConfig, get_config

_DEFAULT_GRANULARITIES = ["1 day"]

# Error fragments that mean "feature not available here", not "bad request"
_UNAVAILABLE_MARKERS = (
    "not enabled",
    "not available",
    "feature is disabled",
    "permission_denied",
    "403",
)


class MonitoringUnavailable(RuntimeError):
    """Lakehouse Monitoring isn't enabled/licensed in this workspace (§25)."""


class MonitoringServiceError(RuntimeError):
    """A monitoring operation failed for a reason other than availability."""


@dataclass
class MonitorHandle:
    table_name: str
    status: str
    dashboard_id: str = ""
    already_existed: bool = False


class MonitoringService:
    def __init__(self, config: AppConfig | None = None, ws: Any = None) -> None:
        self._cfg = config or get_config()
        self._ws_override = ws  # injectable for tests

    def _ws(self) -> Any:
        if self._ws_override is not None:
            return self._ws_override
        from databricks.sdk import WorkspaceClient

        return WorkspaceClient(host=self._cfg.databricks_host, token=self._cfg.databricks_token, auth_type="pat")

    # ── attach / read / upgrade / detach ─────────────────────────────────────

    def attach_inference_monitor(
        self,
        *,
        inference_table: str,
        output_schema: str,
        prediction_col: str,
        problem_type: str = "classification",
        timestamp_col: str = "request_time",
        model_id_col: str = "model_id",
        label_col: str | None = None,
        slicing_exprs: list[str] | None = None,
        granularities: list[str] | None = None,
    ) -> MonitorHandle:
        """Attach an InferenceLog monitor to the table. Idempotent: an existing
        monitor is returned as-is, never recreated.

        slicing_exprs should carry the contract's declared fairness attributes
        (§13) so drift/quality metrics are sliced by protected classes.
        """
        existing = self.monitor_status(inference_table)
        if existing is not None:
            return MonitorHandle(
                table_name=inference_table,
                status=existing.get("status", "unknown"),
                dashboard_id=existing.get("dashboard_id", ""),
                already_existed=True,
            )

        from databricks.sdk.service.catalog import (
            MonitorInferenceLog,
            MonitorInferenceLogProblemType,
        )

        problem = (
            MonitorInferenceLogProblemType.PROBLEM_TYPE_REGRESSION
            if problem_type == "regression"
            else MonitorInferenceLogProblemType.PROBLEM_TYPE_CLASSIFICATION
        )
        inference_log = MonitorInferenceLog(
            problem_type=problem,
            timestamp_col=timestamp_col,
            granularities=granularities or _DEFAULT_GRANULARITIES,
            prediction_col=prediction_col,
            model_id_col=model_id_col,
            label_col=label_col,
        )
        try:
            info = self._ws().quality_monitors.create(
                table_name=inference_table,
                assets_dir=f"/Shared/mlops/monitors/{inference_table}",
                output_schema_name=output_schema,
                inference_log=inference_log,
                slicing_exprs=slicing_exprs,
            )
        except Exception as exc:
            raise self._classify(exc, inference_table) from exc

        return MonitorHandle(
            table_name=inference_table,
            status=str(getattr(info, "status", "") or "created"),
            dashboard_id=str(getattr(info, "dashboard_id", "") or ""),
        )

    def monitor_status(self, inference_table: str) -> dict[str, Any] | None:
        """Current monitor info for the table, or None if no monitor exists."""
        try:
            info = self._ws().quality_monitors.get(table_name=inference_table)
        except Exception as exc:
            if _looks_like_not_found(exc):
                return None
            raise self._classify(exc, inference_table) from exc
        return {
            "table_name": inference_table,
            "status": str(getattr(info, "status", "") or "unknown"),
            "dashboard_id": str(getattr(info, "dashboard_id", "") or ""),
            "label_col": _label_col_of(info),
        }

    def attach_label_column(self, inference_table: str, label_col: str) -> None:
        """§10.3 synergy: once label_feedback flows, teach the existing monitor
        the label column so accuracy/calibration compute natively."""
        try:
            info = self._ws().quality_monitors.get(table_name=inference_table)
        except Exception as exc:
            raise self._classify(exc, inference_table) from exc

        inference_log = getattr(info, "inference_log", None)
        if inference_log is None:
            raise MonitoringServiceError(
                f"Monitor on {inference_table} has no InferenceLog profile — cannot attach a label column."
            )
        if getattr(inference_log, "label_col", None) == label_col:
            return  # idempotent

        inference_log.label_col = label_col
        try:
            self._ws().quality_monitors.update(
                table_name=inference_table,
                output_schema_name=info.output_schema_name,
                inference_log=inference_log,
            )
        except Exception as exc:
            raise self._classify(exc, inference_table) from exc

    def delete_monitor(self, inference_table: str) -> None:
        """Phase 6 retirement path (§21.2) — remove the monitor with the model."""
        try:
            self._ws().quality_monitors.delete(table_name=inference_table)
        except Exception as exc:
            if _looks_like_not_found(exc):
                return
            raise self._classify(exc, inference_table) from exc

    # ── error classification (§25 graceful degradation) ─────────────────────

    @staticmethod
    def _classify(exc: Exception, table: str) -> RuntimeError:
        text = str(exc).lower()
        if any(marker in text for marker in _UNAVAILABLE_MARKERS):
            return MonitoringUnavailable(
                f"Lakehouse Monitoring unavailable for {table}: {exc}. "
                "Enable the feature (or check workspace tier); the app disables "
                "monitoring affordances until then."
            )
        return MonitoringServiceError(f"Monitoring operation failed for {table}: {exc}")


def _looks_like_not_found(exc: Exception) -> bool:
    text = str(exc).lower()
    return "does not exist" in text or "not found" in text or "404" in text


def _label_col_of(info: Any) -> str | None:
    inference_log = getattr(info, "inference_log", None)
    return getattr(inference_log, "label_col", None) if inference_log else None
