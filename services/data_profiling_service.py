"""Data Profiling Service — auto-profile for Step 3 (owner request 2026-07-13).

Two deliberately separate operations:
  quick_stats()   fast SQL-aggregate null%/distinct-count per column — cheap
                   enough to run automatically, feeds Step 4's Data Quality
                   Gates Required/Acceptable default suggestion
  full_profile()  a real pandas-profiling-style HTML report — explicit
                   opt-in, heavier, never run automatically

Both operate on a LIMIT-capped sample, never the full table — profiling a
production-scale table directly would be slow and expensive, and this is
exploration tooling, not a production quality gate (that's
data_quality_service.py, which runs against the real table via a different,
narrower set of checks).

Package note (design-tenet-8 caution, confirmed live 2026-07-13): the
"pandas-profiling" library the owner referenced has been renamed twice —
pandas-profiling -> ydata-profiling (2023) -> fg-data-profiling (2026-04,
confirmed against the current PyPI listing). This uses the current name and
import path (`from data_profiling import ProfileReport`). The report
object's internal description/alerts structure was not independently
verified, so the compact summary below is computed directly from the
sampled pandas DataFrame instead of parsed out of that internal object —
verified, boring pandas calls instead of a guess at unfamiliar internals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.db_service import DbService

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){0,2}$")
_COLUMN_RE = re.compile(r"^[A-Za-z0-9_]+$")

DEFAULT_SAMPLE_ROWS = 5000
# A column already this null in real data is suggested for the "Acceptable
# Issues" box instead of "Required" (§4 Governance) — already-messy data
# probably shouldn't hard-block training on the exact issue it already has.
ACCEPTABLE_NULL_PCT_THRESHOLD = 5.0
# The pairwise interactions (scatter matrix) section renders one plot per
# column pair — cost is ~O(columns^2). Verified live (owner request
# 2026-07-13): a 12-column, 500-row sample took 2+ minutes and produced a
# 45MB report almost entirely made of scatter plots. Above this threshold,
# skip interactions and keep the analytically useful parts (per-column
# stats, correlations, missing-value diagrams).
MAX_COLUMNS_FOR_INTERACTIONS = 10


class DataProfilingError(RuntimeError):
    """Raised when a profiling operation fails or preconditions aren't met."""


@dataclass
class ColumnStats:
    column: str
    null_pct: float
    distinct_count: int
    suggested_dq_box: str  # "required" | "acceptable"


@dataclass
class ProfileResult:
    html: str
    row_count: int
    column_count: int
    missing_cells_pct: float
    duplicate_rows_pct: float


class DataProfilingService:
    def __init__(self, db_service: Any = None) -> None:
        self._db = db_service or DbService()

    # ── quick_stats: cheap, SQL-only, safe to run automatically ──────────────

    def quick_stats(
        self, table_path: str, columns: list[str], sample_rows: int = DEFAULT_SAMPLE_ROWS
    ) -> dict[str, ColumnStats]:
        if not _IDENTIFIER_RE.match(table_path):
            raise DataProfilingError(f"Unsafe table identifier: {table_path!r}")
        safe_columns = [c for c in columns if _COLUMN_RE.match(c)]
        if not safe_columns:
            return {}

        exprs = ", ".join(
            f"sum(case when {c} is null then 1 else 0 end) as {c}__nulls, approx_count_distinct({c}) as {c}__distinct"
            for c in safe_columns
        )
        rows = self._db._exec(
            f"""SELECT count(*) AS __n, {exprs}
                FROM (SELECT * FROM {table_path} LIMIT {int(sample_rows)})"""
        )
        if not rows:
            return {}
        row = rows[0]
        n = int(row.get("__n") or 0)

        results: dict[str, ColumnStats] = {}
        for c in safe_columns:
            nulls = int(row.get(f"{c}__nulls") or 0)
            distinct = int(row.get(f"{c}__distinct") or 0)
            null_pct = (nulls / n * 100.0) if n else 0.0
            results[c] = ColumnStats(
                column=c,
                null_pct=null_pct,
                distinct_count=distinct,
                suggested_dq_box="acceptable" if null_pct > ACCEPTABLE_NULL_PCT_THRESHOLD else "required",
            )
        return results

    # ── full_profile: heavier, explicit opt-in ────────────────────────────────

    def full_profile(self, table_path: str, sample_rows: int = DEFAULT_SAMPLE_ROWS) -> ProfileResult:
        if not _IDENTIFIER_RE.match(table_path):
            raise DataProfilingError(f"Unsafe table identifier: {table_path!r}")

        rows = self._db._exec(f"SELECT * FROM {table_path} LIMIT {int(sample_rows)}")
        if not rows:
            raise DataProfilingError(f"{table_path} returned no rows to profile.")

        import pandas as pd

        df = pd.DataFrame(rows)

        try:
            from data_profiling import ProfileReport  # fg-data-profiling (renamed from ydata-profiling, 2026-04)
        except ImportError as exc:
            raise DataProfilingError(
                "fg-data-profiling is not installed — add it to requirements.txt and `pip install fg-data-profiling`."
            ) from exc

        report_kwargs: dict[str, Any] = {}
        if len(df.columns) > MAX_COLUMNS_FOR_INTERACTIONS:
            report_kwargs["interactions"] = {"continuous": False}

        report = ProfileReport(df, title=f"{table_path} — profile", minimal=len(df) > 20_000, **report_kwargs)

        return ProfileResult(
            html=report.to_html(),
            row_count=len(df),
            column_count=len(df.columns),
            missing_cells_pct=float(df.isnull().to_numpy().mean() * 100.0) if df.size else 0.0,
            duplicate_rows_pct=float(df.duplicated().mean() * 100.0) if len(df) else 0.0,
        )
