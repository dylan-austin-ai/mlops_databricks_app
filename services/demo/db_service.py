"""DemoDbService — DbService's public interface without any real warehouse
call. Backs the New Project wizard's schema-inference/team-lookup buttons,
and is injected as the `db` for DataVersioningService's snapshot step so
"versioning" training data during the wizard doesn't need a real Unity
Catalog table either.

`_exec` is a narrow, pattern-matched fake for the handful of raw
statements DataVersioningService issues -- the only caller that reaches
this low-level method within Demo Mode's scope (see
services/data_versioning_service.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_FABRICATED_COLUMNS: list[dict[str, str]] = [
    {"name": "customer_id", "data_type": "string", "comment": ""},
    {"name": "signup_date", "data_type": "date", "comment": ""},
    {"name": "region", "data_type": "string", "comment": ""},
    {"name": "age", "data_type": "int", "comment": ""},
    {"name": "monthly_spend", "data_type": "double", "comment": ""},
    {"name": "email", "data_type": "string", "comment": ""},
    {"name": "phone_number", "data_type": "string", "comment": ""},
    {"name": "tenure_months", "data_type": "int", "comment": ""},
    {"name": "support_tickets_opened", "data_type": "int", "comment": ""},
    {"name": "churned", "data_type": "boolean", "comment": ""},
]

_FABRICATED_TEAMS = ["retention_team", "fraud_detection", "pricing_ml", "recommendations"]


class DemoDbService:
    def __init__(self, config: Any = None) -> None:
        pass

    def infer_table_schema(self, table_path: str) -> list[dict[str, str]]:
        return [dict(c) for c in _FABRICATED_COLUMNS]

    def get_org_teams(self) -> list[str]:
        return list(_FABRICATED_TEAMS)

    def get_field_drift_data(self, catalog: str, schema: str) -> dict[str, Any]:
        return {}  # no monitoring job has run yet -- same empty state a brand-new real project shows

    def get_baseline_stats(self, catalog: str, schema: str) -> dict[str, Any]:
        return {}

    def _exec(self, sql: str, timeout_s: int = 30) -> list[dict[str, Any]]:
        upper = sql.upper()
        if "DESCRIBE HISTORY" in upper:
            return [{"version": 0}]
        if "DATE_FORMAT(CURRENT_TIMESTAMP()" in upper:
            return [{"ts": datetime.now(UTC).strftime("%Y%m%d_%H%M%S")}]
        if "DEEP CLONE" in upper:
            return []
        if "COUNT(*)" in upper:
            return [{"n": 1000}]
        return []
