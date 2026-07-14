#!/usr/bin/env python3
"""Live verification — DECISIONS_NEEDED #3: does Model Serving accept `@champion`?

The bundle schema accepts any string in `entity_version`, but whether the
*API* accepts a UC registry alias decides promotion mechanics: alias accepted
means promotion is an alias re-point and endpoints never change; numeric-only
means every promotion adds an endpoint-config update step to the saga.

Probe: register a trivial pyfunc model in UC → set `@champion` alias → create
a scratch serving endpoint with `entity_version="@champion"` → classify the
API response → tear everything down. The endpoint never needs to reach READY;
acceptance/rejection happens at config submission.

Usage:
    python scripts/verify_champion_alias.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config  # noqa: E402

PROBE_MODEL = "ctrl_plane_alias_probe"
PROBE_ENDPOINT = "ctrl-plane-alias-probe"


def main() -> int:
    cfg = get_config()
    os.environ.setdefault("DATABRICKS_HOST", cfg.databricks_host)
    os.environ.setdefault("DATABRICKS_TOKEN", cfg.databricks_token)
    model_full_name = f"{cfg.catalog}.{cfg.schema}.{PROBE_MODEL}"

    import mlflow
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput
    from mlflow.models import ModelSignature
    from mlflow.types import ColSpec, Schema

    ws = WorkspaceClient(host=cfg.databricks_host, token=cfg.databricks_token, auth_type="pat")

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    # MLflow does not create parent workspace directories
    ws.workspace.mkdirs("/Shared/mlops")
    mlflow.set_experiment(f"/Shared/mlops/{PROBE_MODEL}")

    class Echo(mlflow.pyfunc.PythonModel):
        def predict(self, context, model_input, params=None):
            return model_input

    print(f"registering probe model {model_full_name} ...")
    with mlflow.start_run(run_name="alias_probe"):
        # Explicit signature instead of input_example: this venv carries a
        # broken pyspark shim that crashes MLflow's example-saving path
        signature = ModelSignature(
            inputs=Schema([ColSpec("double", "x")]),
            outputs=Schema([ColSpec("double", "x")]),
        )
        info = mlflow.pyfunc.log_model(
            name="model",
            python_model=Echo(),
            signature=signature,
            registered_model_name=model_full_name,
            pip_requirements=["mlflow", "pandas"],
        )
    version = info.registered_model_version
    client = mlflow.MlflowClient()
    client.set_registered_model_alias(model_full_name, "champion", version)
    print(f"registered v{version}, alias @champion set")

    endpoint_created = False
    verdict = "INCONCLUSIVE"
    detail = ""
    try:
        try:
            ws.serving_endpoints.create(
                name=PROBE_ENDPOINT,
                config=EndpointCoreConfigInput(
                    name=PROBE_ENDPOINT,
                    served_entities=[
                        ServedEntityInput(
                            entity_name=model_full_name,
                            entity_version="@champion",
                            workload_size="Small",
                            scale_to_zero_enabled=True,
                        )
                    ],
                ),
            )
            endpoint_created = True
            ep = ws.serving_endpoints.get(name=PROBE_ENDPOINT)
            served = (ep.pending_config or ep.config).served_entities or []
            detail = f"read-back entity_version={served[0].entity_version if served else '?'}"
            verdict = "ACCEPTED"
        except Exception as exc:
            msg = str(exc)
            lowered = msg.lower()
            endpoint_created = "already exists" in lowered
            if any(k in lowered for k in ("version", "alias", "invalid")):
                verdict = "REJECTED"
            detail = msg[:500]
    finally:
        if endpoint_created:
            try:
                ws.serving_endpoints.delete(name=PROBE_ENDPOINT)
                print("cleanup: endpoint deleted")
            except Exception as exc:
                print(f"cleanup WARNING: endpoint delete failed: {exc}")
        try:
            client.delete_registered_model(model_full_name)
            print("cleanup: registered model deleted")
        except Exception as exc:
            print(f"cleanup WARNING: model delete failed: {exc}")

    print(f"\n@champion in entity_version: {verdict}")
    print(f"detail: {detail}")
    if verdict == "ACCEPTED":
        print("→ promotion = alias re-point; endpoints never change (no extra saga step)")
    elif verdict == "REJECTED":
        print("→ numeric-only: saga step 4/6 gains an endpoint-config update on promotion")
    return 0 if verdict != "INCONCLUSIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
