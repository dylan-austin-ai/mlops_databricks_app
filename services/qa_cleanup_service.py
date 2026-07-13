"""QaCleanupService — removes non-essential dev/QA-only resources (owner
request 2026-07-13: "DS should be able to deploy endpoints/tables by
themselves into QA without friction... there needs to be a cleanup mechanism
that removes all non-essential endpoints and tables before [prod deploy]
(to eliminate qa_model_endpoint_v25)").

Two independently-scoped, deliberately conservative rules — a reaper with a
false-positive delete is much worse than one that leaves some clutter:

  Endpoints: any serving endpoint whose name starts with "{project_name}"
  but ISN'T the bundle-managed endpoint for a given target (the exact name
  model_serving.yml.j2 creates) is a candidate. This catches ad hoc
  exploration endpoints (`{project_name}_v25`, `{project_name}_test`, ...)
  while never touching the bundle's own real endpoint.

  Tables: only tables in the project's OWN non-prod schema whose name starts
  with an explicit scratch prefix (zz_, scratch_, tmp_ — the same convention
  used throughout this project's own scratch/verification tables) are
  candidates. Arbitrary tables without that prefix are never touched — no
  naming signal strong enough to safely auto-delete on.

This same logic is duplicated (not shared/imported — different repos) in
generator_service.py's generated scripts/cleanup_qa_resources.py, which runs
inside each project's own CI, not this app.
"""

from __future__ import annotations

from typing import Any

from config import AppConfig, get_config

SCRATCH_TABLE_PREFIXES = ("zz_", "scratch_", "tmp_")


class QaCleanupService:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._cfg = config or get_config()
        self._ws: Any = None

    def _workspace(self) -> Any:
        if self._ws is None:
            from databricks.sdk import WorkspaceClient

            self._ws = WorkspaceClient(host=self._cfg.databricks_host, token=self._cfg.databricks_token)
        return self._ws

    def _bundle_managed_endpoint_names(self, project_name: str) -> set[str]:
        """The exact endpoint name(s) model_serving.yml.j2 creates — see
        `name: {{ project_name }}-${bundle.target}` in that template. Never
        candidates for deletion regardless of what else matches."""
        return {f"{project_name}-dev", f"{project_name}-staging", f"{project_name}-prod"}

    def find_non_essential_endpoints(self, project_name: str) -> list[str]:
        keep = self._bundle_managed_endpoint_names(project_name)
        ws = self._workspace()
        candidates = []
        for ep in ws.serving_endpoints.list():
            if ep.name in keep:
                continue
            if ep.name.startswith(f"{project_name}_") or ep.name.startswith(f"{project_name}-"):
                candidates.append(ep.name)
        return candidates

    def find_scratch_tables(self, schema_path: str) -> list[str]:
        """schema_path: catalog.schema (the project's non-prod schema)."""
        ws = self._workspace()
        catalog, schema = schema_path.split(".", 1)
        candidates = []
        for table in ws.tables.list(catalog_name=catalog, schema_name=schema):
            if any(table.name.startswith(p) for p in SCRATCH_TABLE_PREFIXES):
                candidates.append(f"{schema_path}.{table.name}")
        return candidates

    def cleanup_non_essential(self, project_name: str, schema_paths: list[str]) -> list[dict[str, str]]:
        """Deletes every non-essential endpoint and scratch table found.
        Best-effort per resource — one failure doesn't block the rest."""
        ws = self._workspace()
        results: list[dict[str, str]] = []

        for name in self.find_non_essential_endpoints(project_name):
            try:
                ws.serving_endpoints.delete(name=name)
                results.append({"resource": f"endpoint:{name}", "status": "deleted"})
            except Exception as exc:
                results.append({"resource": f"endpoint:{name}", "status": "failed", "detail": str(exc)})

        for schema_path in schema_paths:
            try:
                tables = self.find_scratch_tables(schema_path)
            except Exception as exc:
                results.append({"resource": f"schema:{schema_path}", "status": "failed", "detail": str(exc)})
                continue
            for table_path in tables:
                try:
                    self._exec_drop(table_path)
                    results.append({"resource": f"table:{table_path}", "status": "deleted"})
                except Exception as exc:
                    results.append({"resource": f"table:{table_path}", "status": "failed", "detail": str(exc)})

        return results

    def _exec_drop(self, table_path: str) -> None:
        from services.db_service import DbService

        DbService(self._cfg)._exec(f"DROP TABLE IF EXISTS {table_path}")
