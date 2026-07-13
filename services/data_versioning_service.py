"""DataVersioningService — Delta CLONE training-data snapshots (owner
request 2026-07-13: "The training data needs to be versioned and persisted
so it can be faithfully recreated at a later date").

DEEP CLONE, not SHALLOW: a shallow clone only copies metadata/pointers to
the source table's existing data files, so it breaks once the source is
VACUUMed or the files it points to are deleted — useless for "faithfully
recreated months later." A deep clone physically copies the data, so the
snapshot survives independently of whatever happens to the source table
afterward.

Snapshots one table at a time, per (project_id, source_table) — a project's
first Step 3 completion snapshots every training dataset; a later dataset
list change only snapshots the NEW table(s), not ones already captured.
Re-snapshotting an unchanged source on purpose (e.g. to capture drift in the
underlying data) is a deliberate future action, not automatic here.
"""

from __future__ import annotations

import re

from config import AppConfig, get_config
from services.db_service import DbService
from services.state_service import StateService

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){0,2}$")


class DataVersioningError(RuntimeError):
    """Raised when a snapshot operation fails or preconditions aren't met."""


class DataVersioningService:
    def __init__(
        self,
        config: AppConfig | None = None,
        db: DbService | None = None,
        state: StateService | None = None,
    ) -> None:
        self._cfg = config or get_config()
        self._db = db or DbService()
        self._state = state or StateService(self._cfg)

    def _source_delta_version(self, table_path: str) -> int | None:
        try:
            rows = self._db._exec(f"DESCRIBE HISTORY {table_path} LIMIT 1")
            if rows and rows[0].get("version") is not None:
                return int(rows[0]["version"])
        except Exception:
            pass  # non-Delta table, or history unavailable -- version stays unknown, not fatal
        return None

    def _row_count(self, table_path: str) -> int:
        rows = self._db._exec(f"SELECT count(*) AS n FROM {table_path}")
        return int(rows[0]["n"]) if rows else 0

    def snapshot_training_data(
        self,
        project_id: str,
        source_table: str,
        dest_schema: str,
        created_by: str,
    ) -> dict[str, object] | None:
        """Deep-clones source_table into dest_schema if it hasn't already
        been snapshotted for this project. Returns the snapshot record dict,
        or None if skipped (already snapshotted) or source_table is unsafe."""
        if not _IDENTIFIER_RE.match(source_table) or not _IDENTIFIER_RE.match(dest_schema):
            raise DataVersioningError(f"Unsafe table identifier: {source_table!r} / {dest_schema!r}")

        existing = self._state.latest_training_data_snapshot(project_id, source_table)
        if existing:
            return None  # already have a faithful copy of this source table for this project

        short_name = source_table.rsplit(".", 1)[-1]
        timestamp = self._db._exec("SELECT date_format(current_timestamp(), 'yyyyMMdd_HHmmss') AS ts")[0]["ts"]
        snapshot_name = f"snapshot_{short_name}_{timestamp}"
        snapshot_table = f"{dest_schema}.{snapshot_name}"

        self._db._exec(f"CREATE TABLE {snapshot_table} DEEP CLONE {source_table}", timeout_s=50)

        source_delta_version = self._source_delta_version(source_table)
        row_count = self._row_count(snapshot_table)

        snapshot_id = self._state.record_training_data_snapshot(
            project_id,
            source_table,
            snapshot_table,
            created_by,
            source_delta_version=source_delta_version,
            row_count=row_count,
        )
        return {
            "snapshot_id": snapshot_id,
            "source_table": source_table,
            "snapshot_table": snapshot_table,
            "source_delta_version": source_delta_version,
            "row_count": row_count,
        }

    def snapshot_all(
        self,
        project_id: str,
        source_tables: list[str],
        dest_schema: str,
        created_by: str,
    ) -> list[dict[str, object]]:
        """Snapshots every not-yet-snapshotted table in source_tables.
        Best-effort per table — one failure doesn't block the others."""
        results: list[dict[str, object]] = []
        for table in source_tables:
            try:
                result = self.snapshot_training_data(project_id, table, dest_schema, created_by)
                if result:
                    results.append(result)
            except Exception as exc:
                results.append({"source_table": table, "error": str(exc)})
        return results
