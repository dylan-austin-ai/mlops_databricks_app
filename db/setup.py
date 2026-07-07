"""Run the UC DDL schema against a Databricks SQL warehouse.

Usage:
    python -m db.setup
    python -m db.setup --catalog mlops --schema default
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from config import get_config


def _exec_one(ws: Any, warehouse_id: str, sql: str) -> None:
    """Execute a single SQL statement; raise on failure."""
    from databricks.sdk.service.sql import StatementState

    response = ws.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
        wait_timeout="30s",
    )
    exec_id = response.statement_id
    state = response.status.state if response.status else None
    while state not in (StatementState.SUCCEEDED, StatementState.FAILED, StatementState.CANCELED):
        time.sleep(1)
        response = ws.statement_execution.get_statement(exec_id)
        state = response.status.state if response.status else None
    if state != StatementState.SUCCEEDED:
        err = response.status.error if response.status else "unknown"
        raise RuntimeError(f"SQL failed: {err}\nSQL: {sql[:120]}")


def _split_statements(sql: str) -> list[str]:
    """Split rendered SQL on ';' — but never inside a quoted string or a
    `--` line comment (COMMENT clauses legitimately contain semicolons;
    found live when migration 003 was cut mid-string)."""
    statements: list[str] = []
    buf: list[str] = []
    in_string = False
    in_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_comment:
            buf.append(ch)
            if ch == "\n":
                in_comment = False
        elif in_string:
            buf.append(ch)
            if ch == "'":
                if sql[i + 1 : i + 2] == "'":  # escaped '' stays inside the string
                    buf.append("'")
                    i += 1
                else:
                    in_string = False
        elif ch == "'":
            in_string = True
            buf.append(ch)
        elif ch == "-" and sql[i : i + 2] == "--":
            in_comment = True
            buf.append(ch)
        elif ch == ";":
            statements.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    statements.append("".join(buf))
    return [s.strip() for s in statements if s.strip()]


def run_setup(catalog: str | None = None, schema: str | None = None) -> None:
    cfg = get_config()
    catalog = catalog or cfg.catalog
    schema = schema or cfg.schema

    if not cfg.is_connected:
        missing = ", ".join(cfg.missing_vars())
        raise RuntimeError(f"Missing required env vars: {missing}")

    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient(host=cfg.databricks_host, token=cfg.databricks_token)

    # Create catalog and schema first — tables can't exist without them.
    # Default Storage workspaces reject plain CREATE CATALOG via SQL/API;
    # MLOPS_MANAGED_LOCATION supplies the required location (decision 2026-07-07).
    create_catalog = f"CREATE CATALOG IF NOT EXISTS {catalog}"
    if cfg.managed_location:
        location = cfg.managed_location.replace("'", "''")
        create_catalog += f" MANAGED LOCATION '{location}'"
    _exec_one(ws, cfg.warehouse_id, create_catalog)
    print(f"Catalog '{catalog}' ready.")
    _exec_one(ws, cfg.warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    print(f"Schema '{catalog}.{schema}' ready.")

    sql_path = Path(__file__).parent / "schema.sql"
    raw = sql_path.read_text()
    rendered = raw.replace("{catalog}", catalog).replace("{schema}", schema)

    # Split on statement boundaries — each CREATE TABLE is one statement
    statements = _split_statements(rendered)

    print(f"Creating {len(statements)} tables in {catalog}.{schema} ...")

    for i, stmt in enumerate(statements, 1):
        # Skip pure comment blocks
        lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
        if not any(ln.strip() for ln in lines):
            continue
        # Extract table name for readable output
        words = stmt.split()
        tbl = next((words[j + 1] for j, w in enumerate(words) if w.upper() == "EXISTS"), "?")
        try:
            _exec_one(ws, cfg.warehouse_id, stmt)
            print(f"  [{i}/{len(statements)}] OK — {tbl}")
        except RuntimeError as exc:
            print(f"  [{i}/{len(statements)}] FAILED — {exc}")

    run_migrations(ws, cfg.warehouse_id, catalog, schema)

    print("Schema setup complete.")


def _fetch_applied_versions(ws: Any, warehouse_id: str, catalog: str, schema: str) -> set[int]:
    from databricks.sdk.service.sql import StatementState

    response = ws.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=f"SELECT version FROM {catalog}.{schema}.schema_migrations",
        wait_timeout="30s",
    )
    if response.status and response.status.state == StatementState.SUCCEEDED and response.result:
        return {int(row[0]) for row in (response.result.data_array or [])}
    return set()


def run_migrations(ws: Any, warehouse_id: str, catalog: str, schema: str) -> None:
    """Apply db/migrations/NNN_*.sql in order, tracked in schema_migrations (§21).

    Each migration runs at most once; already-applied versions are skipped.
    """
    _exec_one(
        ws,
        warehouse_id,
        f"""CREATE TABLE IF NOT EXISTS {catalog}.{schema}.schema_migrations (
              version INT NOT NULL,
              name STRING NOT NULL,
              applied_timestamp TIMESTAMP NOT NULL,
              CONSTRAINT pk_schema_migrations PRIMARY KEY (version)
            ) COMMENT 'Applied numbered migrations — one row per db/migrations file'""",
    )
    applied = _fetch_applied_versions(ws, warehouse_id, catalog, schema)

    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.exists():
        return

    for path in sorted(migrations_dir.glob("[0-9]*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version in applied:
            print(f"  migration {path.name}: already applied, skipping")
            continue
        rendered = path.read_text().replace("{catalog}", catalog).replace("{schema}", schema)
        for stmt in _split_statements(rendered):
            _exec_one(ws, warehouse_id, stmt)
        _exec_one(
            ws,
            warehouse_id,
            f"INSERT INTO {catalog}.{schema}.schema_migrations VALUES ({version}, '{path.stem}', current_timestamp())",
        )
        print(f"  migration {path.name}: applied")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up MLOps UC schema")
    parser.add_argument("--catalog", default=None)
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()
    run_setup(catalog=args.catalog, schema=args.schema)
