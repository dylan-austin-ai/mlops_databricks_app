#!/usr/bin/env python3
"""Deploys/redeploys this Streamlit app to Databricks Apps hosting (owner
request 2026-07-13). A prior session did this once by hand (secret scope
creation, app.yaml, `databricks sync`, `w.apps.deploy_and_wait` — see
PROJECT_STATUS.md "fourth session (continued) — deployed as a native
Databricks App"); this turns that one-off sequence into a reusable script.

Idempotent — safe to re-run. Reuses (creating only if missing):
  - Secret scope `mlops_app_secrets` holding `databricks_token` /
    `github_token` — both secret VALUES are refreshed from the current
    config on every run, in case tokens rotated since the last deploy.
  - The App resource itself (name below), with both secrets attached as
    READ-permission AppResources — matches app.yaml's `valueFrom` bindings.

Deploy step does a FULL `databricks sync` (owner request: "replacing what
is already in databricks") — the workspace copy is made to exactly match
this local directory, not just receive incremental changes, then a SNAPSHOT
deploy is triggered from that path and awaited to completion.

Usage:
    python scripts/deploy_app.py
    python scripts/deploy_app.py --app-name my-app
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config  # noqa: E402

APP_NAME = "mlops-databricks-app"
SECRET_SCOPE = "mlops_app_secrets"
REPO_ROOT = Path(__file__).parent.parent


def ensure_secrets(ws, cfg) -> str:
    scopes = {s.name for s in ws.secrets.list_scopes()}
    if SECRET_SCOPE not in scopes:
        ws.secrets.create_scope(scope=SECRET_SCOPE)
        print(f"[1/4] created secret scope {SECRET_SCOPE}")
    else:
        print(f"[1/4] secret scope {SECRET_SCOPE} already exists")

    ws.secrets.put_secret(scope=SECRET_SCOPE, key="databricks_token", string_value=cfg.databricks_token)
    ws.secrets.put_secret(scope=SECRET_SCOPE, key="github_token", string_value=cfg.github_token)
    print("      refreshed databricks_token / github_token secret values")
    return SECRET_SCOPE


def ensure_app(ws, app_name: str) -> str:
    from databricks.sdk.errors.platform import NotFound
    from databricks.sdk.service.apps import App, AppResource, AppResourceSecret, AppResourceSecretSecretPermission

    try:
        app = ws.apps.get(app_name)
        print(f"[2/4] app {app_name!r} already exists")
        return app.default_source_code_path

    except NotFound:
        print(f"[2/4] creating app {app_name!r} ...")
        app = ws.apps.create_and_wait(
            App(
                name=app_name,
                resources=[
                    AppResource(
                        name="databricks_token",
                        secret=AppResourceSecret(
                            scope=SECRET_SCOPE,
                            key="databricks_token",
                            permission=AppResourceSecretSecretPermission.READ,
                        ),
                    ),
                    AppResource(
                        name="github_token",
                        secret=AppResourceSecret(
                            scope=SECRET_SCOPE,
                            key="github_token",
                            permission=AppResourceSecretSecretPermission.READ,
                        ),
                    ),
                ],
            )
        )
        print(f"      created — source path: {app.default_source_code_path}")
        return app.default_source_code_path


def sync_source(cfg, workspace_path: str) -> None:
    print(f"[3/4] syncing {REPO_ROOT} -> {workspace_path} (--full, replaces what's there) ...")
    env = dict(os.environ, DATABRICKS_HOST=cfg.databricks_host, DATABRICKS_TOKEN=cfg.databricks_token)
    subprocess.run(
        [
            "databricks",
            "sync",
            str(REPO_ROOT),
            workspace_path,
            "--exclude-from",
            str(REPO_ROOT / ".gitignore"),
            "--full",
        ],
        env=env,
        check=True,
    )
    print("      sync complete")


def _wait_for_deployment(ws, app_name: str, timeout_s: int = 600) -> None:
    """Polls pending_deployment then active_deployment to a terminal state.
    Found live 2026-07-13: deploy_and_wait's own internal wait can raise a
    transient error ("not in RUNNING state" / "pending deployment in
    progress") even when the deployment is actually proceeding fine
    server-side — polling the app resource directly is what actually
    reflects ground truth."""
    from databricks.sdk.service.apps import AppDeploymentState

    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        app = ws.apps.get(app_name)
        deployment = app.pending_deployment or app.active_deployment
        if deployment is None:
            return
        state = deployment.status.state
        if state != last:
            print(f"      deployment state: {state} — {deployment.status.message}")
            last = state
        if state == AppDeploymentState.SUCCEEDED:
            return
        if state in (AppDeploymentState.FAILED, AppDeploymentState.CANCELLED):
            raise RuntimeError(f"deployment {state}: {deployment.status.message}")
        time.sleep(10)
    raise TimeoutError(f"deployment still not terminal after {timeout_s}s")


def deploy(ws, app_name: str, workspace_path: str) -> None:
    from databricks.sdk.service.apps import AppDeployment, AppDeploymentMode, ComputeState

    current = ws.apps.get(app_name)
    if current.compute_status and current.compute_status.state != ComputeState.ACTIVE:
        print(
            f"      compute is {current.compute_status.state} — starting it first (deploy requires RUNNING compute) ..."
        )
        ws.apps.start_and_wait(app_name)
        print("      compute started")

    print(f"[4/4] deploying (SNAPSHOT) from {workspace_path} ...")
    try:
        ws.apps.deploy(
            app_name=app_name,
            app_deployment=AppDeployment(source_code_path=workspace_path, mode=AppDeploymentMode.SNAPSHOT),
        )
    except Exception as exc:
        # Submission can race with compute just having started even though
        # start_and_wait already reported ACTIVE — found live. The
        # deployment frequently still gets accepted server-side despite the
        # client-side error, so fall through to polling ground truth rather
        # than failing here.
        print(f"      deploy submission raised ({exc}) — polling actual state instead of trusting this error")

    _wait_for_deployment(ws, app_name)

    app = ws.apps.get(app_name)
    print(f"      app URL: {app.url}")
    print(f"      app_status: {app.app_status}")
    print(f"      compute_status: {app.compute_status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", default=APP_NAME)
    args = parser.parse_args()

    cfg = get_config()
    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient(host=cfg.databricks_host, token=cfg.databricks_token)

    ensure_secrets(ws, cfg)
    workspace_path = ensure_app(ws, args.app_name)
    sync_source(cfg, workspace_path)
    deploy(ws, args.app_name, workspace_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
