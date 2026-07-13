"""Tests for data_quality_service — data_quality_assessments was in the base
schema but nothing ever ran a check or wrote to it (IMG_1412 gap #7)."""

from __future__ import annotations

import json

import pytest

from services.data_quality_service import DataQualityService, DataQualityServiceError
from tests.test_approval_service import FakeState


class DQFakeState(FakeState):
    def __init__(self):
        super().__init__()
        self.columns: list[dict] = []
        self.row_count = 100
        self.null_counts: dict[str, int] = {}
        self.dup_counts: dict[str, int] = {}

    def _tbl(self, name: str) -> str:
        return name

    def get_contract_columns(self, contract_id: str):
        return self.columns

    def _exec(self, sql: str, params: dict | None = None):
        self.execs.append((sql, params))
        stripped = sql.strip()
        if stripped.startswith("SELECT count(*) AS n FROM") and "IS NULL" in stripped:
            col = stripped.split("WHERE")[1].split("IS NULL")[0].strip()
            return [{"n": self.null_counts.get(col, 0)}]
        if "count(*) - count(DISTINCT" in stripped:
            col = stripped.split("count(DISTINCT")[1].split(")")[0].strip()
            return [{"n": self.dup_counts.get(col, 0)}]
        if stripped.startswith("SELECT count(*) AS n FROM"):
            return [{"n": self.row_count}]
        return []


def _col(name="age", **overrides) -> dict:
    base = {
        "column_name": name,
        "is_nullable": True,
        "is_required_for_quality": True,
        "pii_level": "none",
        "quality_rules": json.dumps({"null_check": {"max_null_pct": 5.0}}),
    }
    base.update(overrides)
    return base


class TestRunAssessment:
    def test_all_checks_pass(self):
        state = DQFakeState()
        state.columns = [_col()]
        state.null_counts = {"age": 0}
        svc = DataQualityService(state=state)

        result = svc.run_assessment("p1", "c1", "catalog.schema.table")

        assert result.quality_score == 1.0
        assert result.quality_status == "excellent"
        assert result.issues_found == 0
        assert result.row_count == 100

    def test_null_check_failure_recorded(self):
        state = DQFakeState()
        state.columns = [_col()]
        state.row_count = 100
        state.null_counts = {"age": 10}  # 10% > 5% max
        svc = DataQualityService(state=state)

        result = svc.run_assessment("p1", "c1", "catalog.schema.table")

        assert result.issues_found == 1
        assert result.failed_checks[0]["check"] == "null_check"
        assert result.quality_score == 0.0  # only check run, and it failed
        assert result.quality_status == "critical"

    def test_uniqueness_check_failure_recorded(self):
        state = DQFakeState()
        state.columns = [
            _col(
                name="customer_id",
                quality_rules=json.dumps(
                    {"null_check": {"max_null_pct": 100.0}, "uniqueness_check": {"must_be_unique": True}}
                ),
            )
        ]
        state.null_counts = {"customer_id": 0}
        state.dup_counts = {"customer_id": 3}
        svc = DataQualityService(state=state)

        result = svc.run_assessment("p1", "c1", "catalog.schema.table")

        assert result.checks_run == 2
        assert result.issues_found == 1
        assert result.failed_checks[0]["check"] == "uniqueness_check"
        assert "3 duplicate" in result.failed_checks[0]["detail"]

    def test_columns_not_required_for_quality_are_skipped(self):
        state = DQFakeState()
        state.columns = [_col(is_required_for_quality=False)]
        state.null_counts = {"age": 99}  # would fail if checked
        svc = DataQualityService(state=state)

        result = svc.run_assessment("p1", "c1", "catalog.schema.table")

        assert result.checks_run == 0
        assert result.quality_score == 1.0  # no checks run — vacuously clean, not penalized

    def test_pii_columns_detected_regardless_of_quality_gate(self):
        state = DQFakeState()
        state.columns = [
            _col(name="email", pii_level="high", is_required_for_quality=False),
            _col(name="age", pii_level="none"),
        ]
        state.null_counts = {"age": 0}
        svc = DataQualityService(state=state)

        result = svc.run_assessment("p1", "c1", "catalog.schema.table")

        assert result.pii_columns_detected == ["email"]

    def test_unsafe_table_identifier_rejected(self):
        state = DQFakeState()
        svc = DataQualityService(state=state)

        with pytest.raises(DataQualityServiceError, match="Unsafe table identifier"):
            svc.run_assessment("p1", "c1", "table; DROP TABLE x")

    def test_insert_carries_expected_fields(self):
        state = DQFakeState()
        state.columns = [_col()]
        state.null_counts = {"age": 0}
        svc = DataQualityService(state=state)

        svc.run_assessment("p1", "c1", "catalog.schema.table", assessment_type="training_data", created_by="ds@co.com")

        insert_sql, params = next(e for e in state.execs if e[0].strip().startswith("INSERT INTO"))
        assert params["project_id"] == "p1"
        assert params["contract_id"] == "c1"
        assert params["assessment_type"] == "training_data"
        assert params["created_by"] == "ds@co.com"
        assert params["quality_score"] == 1.0


class TestStatusBuckets:
    @pytest.mark.parametrize(
        ("null_count", "expected_status"),
        [
            (0, "excellent"),
        ],
    )
    def test_excellent_on_clean_data(self, null_count, expected_status):
        state = DQFakeState()
        state.columns = [_col()]
        state.null_counts = {"age": null_count}
        svc = DataQualityService(state=state)

        result = svc.run_assessment("p1", "c1", "t")

        assert result.quality_status == expected_status
