"""Tests for DataVersioningService — Delta CLONE training-data snapshots
(owner request 2026-07-13: "training data needs to be versioned and
persisted so it can be faithfully recreated at a later date")."""

from __future__ import annotations

import pytest

from services.data_versioning_service import DataVersioningError, DataVersioningService


class FakeDbService:
    def __init__(self, history_version: int = 7, row_count: int = 500):
        self.queries: list[str] = []
        self.history_version = history_version
        self.row_count = row_count

    def _exec(self, sql: str, timeout_s: int = 30):
        self.queries.append(sql)
        if sql.startswith("DESCRIBE HISTORY"):
            return [{"version": self.history_version}]
        if sql.startswith("SELECT date_format"):
            return [{"ts": "20260713_140530"}]
        if sql.startswith("SELECT count(*)"):
            return [{"n": self.row_count}]
        return []  # CREATE TABLE ... DEEP CLONE


class FakeStateService:
    def __init__(self):
        self.snapshots: dict[tuple[str, str], dict] = {}
        self.record_calls: list[tuple] = []

    def latest_training_data_snapshot(self, project_id, source_table):
        return self.snapshots.get((project_id, source_table))

    def record_training_data_snapshot(
        self, project_id, source_table, snapshot_table, created_by, source_delta_version=None, row_count=None
    ):
        snapshot_id = f"snap-{len(self.record_calls)}"
        self.record_calls.append((project_id, source_table, snapshot_table))
        self.snapshots[(project_id, source_table)] = {
            "snapshot_id": snapshot_id,
            "snapshot_table": snapshot_table,
            "source_delta_version": source_delta_version,
            "row_count": row_count,
        }
        return snapshot_id


def _svc(db=None, state=None):
    from config import AppConfig

    cfg = AppConfig(
        databricks_host="https://test.cloud.databricks.com", databricks_token="dapi-test", warehouse_id="wh123"
    )
    return DataVersioningService(cfg, db=db or FakeDbService(), state=state or FakeStateService())


class TestSnapshotTrainingData:
    def test_rejects_unsafe_source_identifier(self):
        svc = _svc()
        with pytest.raises(DataVersioningError):
            svc.snapshot_training_data("proj-1", "cat.schema.tbl; DROP TABLE x", "cat.dev_schema", "owner@example.com")

    def test_rejects_unsafe_dest_identifier(self):
        svc = _svc()
        with pytest.raises(DataVersioningError):
            svc.snapshot_training_data("proj-1", "cat.schema.tbl", "cat.dev_schema; DROP TABLE x", "owner@example.com")

    def test_clones_and_records_snapshot(self):
        db = FakeDbService(history_version=12, row_count=500)
        state = FakeStateService()
        svc = DataVersioningService(_svc()._cfg, db=db, state=state)

        result = svc.snapshot_training_data("proj-1", "cat.src.training_data", "cat.proj_dev", "owner@example.com")

        assert result is not None
        assert result["source_table"] == "cat.src.training_data"
        assert result["snapshot_table"] == "cat.proj_dev.snapshot_training_data_20260713_140530"
        assert result["source_delta_version"] == 12
        assert result["row_count"] == 500
        clone_stmts = [q for q in db.queries if "DEEP CLONE" in q]
        assert clone_stmts == [
            "CREATE TABLE cat.proj_dev.snapshot_training_data_20260713_140530 DEEP CLONE cat.src.training_data"
        ]

    def test_skips_when_already_snapshotted(self):
        db = FakeDbService()
        state = FakeStateService()
        svc = DataVersioningService(_svc()._cfg, db=db, state=state)
        svc.snapshot_training_data("proj-1", "cat.src.training_data", "cat.proj_dev", "owner@example.com")
        db.queries.clear()

        result = svc.snapshot_training_data("proj-1", "cat.src.training_data", "cat.proj_dev", "owner@example.com")

        assert result is None
        assert not any("DEEP CLONE" in q for q in db.queries)  # never re-hit the warehouse

    def test_non_delta_source_history_failure_is_not_fatal(self):
        class RaisingHistoryDb(FakeDbService):
            def _exec(self, sql, timeout_s=30):
                if sql.startswith("DESCRIBE HISTORY"):
                    raise RuntimeError("not a Delta table")
                return super()._exec(sql, timeout_s)

        svc = DataVersioningService(_svc()._cfg, db=RaisingHistoryDb(), state=FakeStateService())

        result = svc.snapshot_training_data("proj-1", "cat.src.training_data", "cat.proj_dev", "owner@example.com")

        assert result is not None
        assert result["source_delta_version"] is None


class TestSnapshotAll:
    def test_snapshots_only_new_tables(self):
        db = FakeDbService()
        state = FakeStateService()
        svc = DataVersioningService(_svc()._cfg, db=db, state=state)
        svc.snapshot_training_data("proj-1", "cat.src.table_a", "cat.proj_dev", "owner@example.com")

        results = svc.snapshot_all(
            "proj-1", ["cat.src.table_a", "cat.src.table_b"], "cat.proj_dev", "owner@example.com"
        )

        assert len(results) == 1  # table_a already snapshotted, only table_b is new
        assert results[0]["source_table"] == "cat.src.table_b"

    def test_one_failure_does_not_block_others(self):
        class FlakyDb(FakeDbService):
            def _exec(self, sql, timeout_s=30):
                if "table_a" in sql and "DEEP CLONE" in sql:
                    raise RuntimeError("warehouse timeout")
                return super()._exec(sql, timeout_s)

        svc = DataVersioningService(_svc()._cfg, db=FlakyDb(), state=FakeStateService())

        results = svc.snapshot_all(
            "proj-1", ["cat.src.table_a", "cat.src.table_b"], "cat.proj_dev", "owner@example.com"
        )

        assert len(results) == 2
        assert "error" in results[0]
        assert results[1]["source_table"] == "cat.src.table_b"
