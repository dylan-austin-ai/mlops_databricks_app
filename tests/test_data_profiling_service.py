"""Tests for data_profiling_service — quick_stats (SQL-only, safe to run
automatically) and full_profile (fg-data-profiling, explicit opt-in),
owner request 2026-07-13."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from services.data_profiling_service import (
    DataProfilingError,
    DataProfilingService,
)


class FakeDbService:
    def __init__(self, rows: list[dict] | None = None, raise_exc: Exception | None = None):
        self.rows = rows if rows is not None else [{}]
        self.raise_exc = raise_exc
        self.queries: list[str] = []

    def _exec(self, sql: str, timeout_s: int = 30):
        self.queries.append(sql)
        if self.raise_exc:
            raise self.raise_exc
        return self.rows


class TestQuickStats:
    def test_unsafe_table_identifier_rejected(self):
        svc = DataProfilingService(db_service=FakeDbService())
        with pytest.raises(DataProfilingError, match="Unsafe table identifier"):
            svc.quick_stats("table; DROP TABLE x", ["col"])

    def test_no_safe_columns_returns_empty(self):
        svc = DataProfilingService(db_service=FakeDbService())
        assert svc.quick_stats("cat.schema.tbl", ["bad col; DROP"]) == {}

    def test_computes_null_pct_and_distinct(self):
        db = FakeDbService(rows=[{"__n": 100, "age__nulls": 10, "age__distinct": 42}])
        svc = DataProfilingService(db_service=db)

        result = svc.quick_stats("cat.schema.tbl", ["age"], sample_rows=100)

        assert result["age"].null_pct == 10.0
        assert result["age"].distinct_count == 42
        assert result["age"].suggested_dq_box == "acceptable"  # 10% > 5% threshold

    def test_low_null_pct_suggests_required(self):
        db = FakeDbService(rows=[{"__n": 100, "age__nulls": 1, "age__distinct": 42}])
        svc = DataProfilingService(db_service=db)

        result = svc.quick_stats("cat.schema.tbl", ["age"], sample_rows=100)

        assert result["age"].suggested_dq_box == "required"

    def test_no_rows_returned_gives_empty_dict(self):
        db = FakeDbService(rows=[])
        svc = DataProfilingService(db_service=db)

        assert svc.quick_stats("cat.schema.tbl", ["age"]) == {}

    def test_sample_rows_respected_in_query(self):
        db = FakeDbService(rows=[{"__n": 0, "age__nulls": 0, "age__distinct": 0}])
        svc = DataProfilingService(db_service=db)

        svc.quick_stats("cat.schema.tbl", ["age"], sample_rows=2500)

        assert "LIMIT 2500" in db.queries[0]


class TestFullProfile:
    def test_unsafe_table_identifier_rejected(self):
        svc = DataProfilingService(db_service=FakeDbService())
        with pytest.raises(DataProfilingError, match="Unsafe table identifier"):
            svc.full_profile("table; DROP TABLE x")

    def test_no_rows_raises(self):
        svc = DataProfilingService(db_service=FakeDbService(rows=[]))
        with pytest.raises(DataProfilingError, match="no rows to profile"):
            svc.full_profile("cat.schema.tbl")

    def test_missing_dependency_raises_clear_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "data_profiling", None)
        db = FakeDbService(rows=[{"a": 1, "b": 2}, {"a": 3, "b": None}])
        svc = DataProfilingService(db_service=db)

        with pytest.raises(DataProfilingError, match="fg-data-profiling is not installed"):
            svc.full_profile("cat.schema.tbl")

    def test_computes_summary_from_sampled_dataframe(self, monkeypatch):
        fake_module = ModuleType("data_profiling")

        class FakeProfileReport:
            def __init__(self, df, title="", minimal=False, **kwargs):
                self.df = df
                self.kwargs = kwargs

            def to_html(self):
                return "<html>fake report</html>"

        fake_module.ProfileReport = FakeProfileReport
        monkeypatch.setitem(sys.modules, "data_profiling", fake_module)

        db = FakeDbService(rows=[{"a": 1, "b": 2}, {"a": 1, "b": 2}, {"a": 3, "b": None}])
        svc = DataProfilingService(db_service=db)

        result = svc.full_profile("cat.schema.tbl", sample_rows=3)

        assert result.html == "<html>fake report</html>"
        assert result.row_count == 3
        assert result.column_count == 2
        assert result.duplicate_rows_pct == pytest.approx(100.0 / 3.0)
        assert result.missing_cells_pct > 0

    def test_narrow_table_keeps_interactions_enabled(self, monkeypatch):
        fake_module = ModuleType("data_profiling")
        captured: dict = {}

        class FakeProfileReport:
            def __init__(self, df, title="", minimal=False, **kwargs):
                captured.update(kwargs)

            def to_html(self):
                return "<html>fake report</html>"

        fake_module.ProfileReport = FakeProfileReport
        monkeypatch.setitem(sys.modules, "data_profiling", fake_module)

        db = FakeDbService(rows=[{"a": 1, "b": 2}])
        svc = DataProfilingService(db_service=db)
        svc.full_profile("cat.schema.tbl", sample_rows=1)

        assert "interactions" not in captured

    def test_wide_table_disables_interactions(self, monkeypatch):
        fake_module = ModuleType("data_profiling")
        captured: dict = {}

        class FakeProfileReport:
            def __init__(self, df, title="", minimal=False, **kwargs):
                captured.update(kwargs)

            def to_html(self):
                return "<html>fake report</html>"

        fake_module.ProfileReport = FakeProfileReport
        monkeypatch.setitem(sys.modules, "data_profiling", fake_module)

        wide_row = {f"col_{i}": i for i in range(11)}
        db = FakeDbService(rows=[wide_row])
        svc = DataProfilingService(db_service=db)
        svc.full_profile("cat.schema.tbl", sample_rows=1)

        assert captured["interactions"] == {"continuous": False}
