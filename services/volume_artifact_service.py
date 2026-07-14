"""VolumeArtifactService — saves generated artifacts (profile reports, EDA
notebook checkpoints) into a project's UC Volume (owner request
2026-07-13). Two call sites, both explicitly DS/event-triggered, not an
automated "EDA is done" detector — EDA has no natural completion signal
since it happens in a Databricks notebook, decoupled from this app's
session state:

  A. Step 3's "Profile Data" button auto-saves the HTML report the moment
     it's generated (wired in pages/02_new_project.py).
  B. A manual "Snapshot EDA notebook to Volume" button on the project
     dashboard the DS clicks whenever they want a checkpoint (wired in
     pages/06_project_dashboard.py) — reads the current eda.py content from
     GitHub via the API and writes a timestamped copy.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from config import AppConfig, get_config

_VOLUME_PATH_RE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")


class VolumeArtifactError(RuntimeError):
    """Raised when a Volume artifact write fails or preconditions aren't met."""


class VolumeArtifactService:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._cfg = config or get_config()
        self._ws_client = None

    def _workspace(self):
        if self._ws_client is None:
            from databricks.sdk import WorkspaceClient

            self._ws_client = WorkspaceClient(
                host=self._cfg.databricks_host, token=self._cfg.databricks_token, auth_type="pat"
            )
        return self._ws_client

    def save_artifact(self, volume_path: str, sub_path: str, content: bytes) -> str:
        """volume_path: catalog.schema.volume (dot-separated, as stored in
        project_infrastructure_actions' uc_volumes resource_id). sub_path:
        the file's path within the volume, e.g. "profile_reports/foo.html".
        Returns the full /Volumes/... path written."""
        if not _VOLUME_PATH_RE.match(volume_path):
            raise VolumeArtifactError(f"Unsafe or malformed volume path: {volume_path!r}")
        catalog, schema, volume = volume_path.split(".")
        full_path = f"/Volumes/{catalog}/{schema}/{volume}/{sub_path.lstrip('/')}"

        import io

        self._workspace().files.upload(full_path, io.BytesIO(content), overwrite=True)
        return full_path

    def save_profile_report(self, volume_path: str, table_path: str, html: str) -> str:
        table_short = table_path.rsplit(".", 1)[-1]
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return self.save_artifact(volume_path, f"profile_reports/{table_short}_{timestamp}.html", html.encode())

    def save_eda_snapshot(self, volume_path: str, eda_content: str) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return self.save_artifact(volume_path, f"eda_snapshots/eda_{timestamp}.py", eda_content.encode())
