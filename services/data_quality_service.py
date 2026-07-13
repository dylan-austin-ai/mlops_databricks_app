"""Data Quality Service — runs the checks a data contract's columns already
declare against a real table, and writes the result (§6, IMG_1412
"Not-covered #7"). data_quality_assessments existed in the base schema but
nothing ever wrote to it — every contract authored quality rules that were
never actually run.

Checks are grounded in what pages/07_data_contracts.py actually lets an
owner author per column — not a bigger, unbuilt rules DSL:
  null_check        quality_rules.null_check.max_null_pct, against is_nullable
  uniqueness_check  quality_rules.uniqueness_check.must_be_unique

Only columns with is_required_for_quality=True are checked — matches the
wizard's own Required/Acceptable DQ-gate framing (step 4 Governance) rather
than treating every declared column as equally blocking.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from services.state_service import StateService

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){0,2}$")
_COLUMN_RE = re.compile(r"^[A-Za-z0-9_]+$")

_STATUS_THRESHOLDS = (
    (0.95, "excellent"),
    (0.85, "good"),
    (0.70, "acceptable"),
    (0.50, "poor"),
)


class DataQualityServiceError(RuntimeError):
    pass


@dataclass
class DataQualityResult:
    assessment_id: str
    quality_score: float
    quality_status: str
    row_count: int
    checks_run: int
    issues_found: int
    failed_checks: list[dict[str, Any]] = field(default_factory=list)
    pii_columns_detected: list[str] = field(default_factory=list)


class DataQualityService:
    def __init__(self, state: StateService | None = None) -> None:
        self._state = state or StateService()

    def run_assessment(
        self,
        project_id: str,
        contract_id: str,
        table_name: str,
        assessment_type: str = "production_data",
        created_by: str = "",
    ) -> DataQualityResult:
        if not _IDENTIFIER_RE.match(table_name or ""):
            raise DataQualityServiceError(f"Unsafe table identifier: {table_name!r}")

        columns = self._state.get_contract_columns(contract_id)
        row_count = self._row_count(table_name)

        checks_run = 0
        failed: list[dict[str, Any]] = []
        column_scores: dict[str, float] = {}
        null_issues = 0
        uniqueness_issues = 0
        pii_columns: list[str] = []

        for col in columns:
            col_name = str(col.get("column_name") or "")
            if col.get("pii_level") and str(col["pii_level"]) != "none":
                pii_columns.append(col_name)
            if not col.get("is_required_for_quality", True):
                continue
            if not _COLUMN_RE.match(col_name):
                continue  # not a checkable identifier — skip rather than fail the whole assessment

            rules = _parse_rules(col.get("quality_rules"))
            col_checks = 0
            col_failures = 0

            null_rule = rules.get("null_check")
            if null_rule is not None or col.get("is_nullable") is False:
                max_pct = float((null_rule or {}).get("max_null_pct", 0.0))
                null_count = self._null_count(table_name, col_name)
                checks_run += 1
                col_checks += 1
                null_pct = (null_count / row_count * 100.0) if row_count else (100.0 if null_count else 0.0)
                if null_pct > max_pct:
                    null_issues += 1
                    col_failures += 1
                    failed.append(
                        {
                            "column": col_name,
                            "check": "null_check",
                            "detail": f"{null_pct:.1f}% null, exceeds max {max_pct:.1f}%",
                        }
                    )

            uniq_rule = rules.get("uniqueness_check")
            if uniq_rule and uniq_rule.get("must_be_unique"):
                dup_count = self._duplicate_count(table_name, col_name)
                checks_run += 1
                col_checks += 1
                if dup_count > 0:
                    uniqueness_issues += 1
                    col_failures += 1
                    failed.append(
                        {"column": col_name, "check": "uniqueness_check", "detail": f"{dup_count} duplicate value(s)"}
                    )

            if col_checks:
                column_scores[col_name] = 1.0 - (col_failures / col_checks)

        issues_found = len(failed)
        quality_score = 1.0 - (issues_found / checks_run) if checks_run else 1.0
        quality_status = _status_for(quality_score)

        assessment_id = str(uuid.uuid4())
        self._state._exec(
            f"""INSERT INTO {self._state._tbl("data_quality_assessments")}
                (assessment_id, project_id, contract_id, assessment_timestamp,
                 assessment_type, table_name, row_count, quality_score, quality_status,
                 column_quality_scores, failed_checks, null_issues_found, range_issues_found,
                 uniqueness_issues_found, format_issues_found, outlier_issues_found,
                 distribution_issues_found, pii_columns_detected, created_timestamp, created_by)
                VALUES
                (:assessment_id, :project_id, :contract_id, current_timestamp(),
                 :assessment_type, :table_name, :row_count, :quality_score, :quality_status,
                 :column_scores, :failed_checks, :null_issues, 0,
                 :uniqueness_issues, 0, 0,
                 0, :pii_columns, current_timestamp(), :created_by)""",
            {
                "assessment_id": assessment_id,
                "project_id": project_id,
                "contract_id": contract_id,
                "assessment_type": assessment_type,
                "table_name": table_name,
                "row_count": row_count,
                "quality_score": quality_score,
                "quality_status": quality_status,
                "column_scores": column_scores,
                "failed_checks": json.dumps(failed),
                "null_issues": null_issues,
                "uniqueness_issues": uniqueness_issues,
                "pii_columns": pii_columns,
                "created_by": created_by,
            },
        )
        return DataQualityResult(
            assessment_id=assessment_id,
            quality_score=quality_score,
            quality_status=quality_status,
            row_count=row_count,
            checks_run=checks_run,
            issues_found=issues_found,
            failed_checks=failed,
            pii_columns_detected=pii_columns,
        )

    def latest_assessment(self, project_id: str) -> dict[str, Any] | None:
        rows = self._state._exec(
            f"""SELECT * FROM {self._state._tbl("data_quality_assessments")}
                WHERE project_id = :project_id
                ORDER BY assessment_timestamp DESC LIMIT 1""",
            {"project_id": project_id},
        )
        return rows[0] if rows else None

    def list_assessments(self, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._state._exec(
            f"""SELECT * FROM {self._state._tbl("data_quality_assessments")}
                WHERE project_id = :project_id
                ORDER BY assessment_timestamp DESC LIMIT {int(limit)}""",
            {"project_id": project_id},
        )

    # ── check primitives ──────────────────────────────────────────────────

    def _row_count(self, table_name: str) -> int:
        rows = self._state._exec(f"SELECT count(*) AS n FROM {table_name}")
        return int(rows[0]["n"]) if rows else 0

    def _null_count(self, table_name: str, column: str) -> int:
        rows = self._state._exec(f"SELECT count(*) AS n FROM {table_name} WHERE {column} IS NULL")
        return int(rows[0]["n"]) if rows else 0

    def _duplicate_count(self, table_name: str, column: str) -> int:
        rows = self._state._exec(
            f"""SELECT count(*) - count(DISTINCT {column}) AS n
                FROM {table_name} WHERE {column} IS NOT NULL"""
        )
        return int(rows[0]["n"]) if rows else 0


def _parse_rules(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(str(raw or "{}"))
    except (TypeError, ValueError):
        return {}


def _status_for(score: float) -> str:
    for threshold, status in _STATUS_THRESHOLDS:
        if score >= threshold:
            return status
    return "critical"
