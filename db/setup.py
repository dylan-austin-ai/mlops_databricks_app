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


def run_setup(catalog: str | None = None, schema: str | None = None) -> None:
    cfg = get_config()
    catalog = catalog or cfg.catalog
    schema = schema or cfg.schema

    if not cfg.is_connected:
        missing = ", ".join(cfg.missing_vars())
        raise RuntimeError(f"Missing required env vars: {missing}")

    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient(host=cfg.databricks_host, token=cfg.databricks_token)

    # Create catalog and schema first — tables can't exist without them
    _exec_one(ws, cfg.warehouse_id, f"CREATE CATALOG IF NOT EXISTS {catalog}")
    print(f"Catalog '{catalog}' ready.")
    _exec_one(ws, cfg.warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    print(f"Schema '{catalog}.{schema}' ready.")

    sql_path = Path(__file__).parent / "schema.sql"
    raw = sql_path.read_text()
    rendered = raw.replace("{catalog}", catalog).replace("{schema}", schema)

    # Split on statement boundaries — each CREATE TABLE is one statement
    statements = [s.strip() for s in rendered.split(";") if s.strip()]

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

    print("Schema setup complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up MLOps UC schema")
    parser.add_argument("--catalog", default=None)
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()
    run_setup(catalog=args.catalog, schema=args.schema)
