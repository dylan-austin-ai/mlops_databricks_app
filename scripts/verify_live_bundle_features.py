#!/usr/bin/env python3
"""Live verification — force-multiplier session 2026-07-13, item 4/5: does the
FeatureLookup / create_training_set block generated into train.py.j2, and the
databricks.automl.classify() call in automl_baseline.py.j2, actually work
against real Databricks compute?

Neither can be exercised from this dev machine (no databricks-connect, no
Spark session — confirmed by direct import failure) or from a SQL warehouse
(both need a Spark DataFrame / Databricks Runtime ML). This submits a
one-time two-task job:

  - feature_engineering_probe: runs on SERVERLESS job compute (confirmed via
    docs.databricks.com that databricks-feature-engineering supports
    serverless — unlike AutoML, see below), matching how the generated
    project's own training job is actually deployed (jobs.yml.j2 uses
    environment_key/environment_version, not a classic cluster).
  - automl_probe: runs on a small single-node classic cluster with a Dedicated
    (SINGLE_USER) access mode LTS ML runtime, because AutoML classify/regress
    is documented as requiring Dedicated/No-isolation-shared access mode and
    does NOT support serverless.

Each probe task creates only clearly-named scratch resources
(catalog.schema.zz_verify_*, /Shared/mlops/_verification_probes/...) and
deletes them itself in a finally block, mirroring verify_champion_alias.py.
This script additionally deletes the uploaded probe source files.

Usage:
    python scripts/verify_live_bundle_features.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config  # noqa: E402

PROBE_DIR = "/Shared/mlops/_verification_probes"
FE_PROBE_PATH = f"{PROBE_DIR}/probe_feature_engineering.py"
AUTOML_PROBE_PATH = f"{PROBE_DIR}/probe_automl.py"

FE_PROBE_SOURCE = """
import sys

CATALOG = "mlops"
SCHEMA = "mlops"
FEATURE_TABLE = f"{CATALOG}.{SCHEMA}.zz_verify_feature_table"


def main() -> int:
    from pyspark.sql import SparkSession
    from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup

    spark = SparkSession.builder.getOrCreate()
    fe = FeatureEngineeringClient()

    result = "FAIL not-run"
    try:
        spark.sql(f"DROP TABLE IF EXISTS {FEATURE_TABLE}")
        feature_df = spark.createDataFrame(
            [(1, 10.0, 100.0), (2, 20.0, 200.0), (3, 30.0, 300.0), (4, 40.0, 400.0)],
            ["entity_id", "feat_a", "feat_b"],
        )
        fe.create_table(
            name=FEATURE_TABLE,
            primary_keys=["entity_id"],
            df=feature_df,
            description="live verification probe -- deleted at end of run",
        )

        training_df = spark.createDataFrame([(1, 0), (2, 1), (3, 0), (4, 1)], ["entity_id", "label"])
        lookups = [
            FeatureLookup(table_name=FEATURE_TABLE, feature_names=["feat_a", "feat_b"], lookup_key="entity_id")
        ]
        training_set = fe.create_training_set(
            df=training_df, feature_lookups=lookups, label="label", exclude_columns=["entity_id"]
        )
        materialized = training_set.load_df()
        row_count = materialized.count()
        cols = sorted(materialized.columns)

        assert row_count == 4, f"expected 4 rows got {row_count}"
        assert "feat_a" in cols and "feat_b" in cols, f"lookup cols missing: {cols}"
        result = f"PASS row_count={row_count} cols={cols}"
    except Exception as exc:
        result = f"FAIL {type(exc).__name__}: {exc}"
    finally:
        try:
            spark.sql(f"DROP TABLE IF EXISTS {FEATURE_TABLE}")
        except Exception as cleanup_exc:
            print(f"PROBE_CLEANUP_WARNING: {cleanup_exc}")

    print(f"PROBE_RESULT: FEATURE_ENGINEERING={result}")
    return 0 if result.startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
"""

AUTOML_PROBE_SOURCE = """
import sys

EXPERIMENT_DIR = "/Shared/mlops/_verification_probes/zz_automl_experiment"


def main() -> int:
    import numpy as np
    import pandas as pd
    from pyspark.sql import SparkSession
    from databricks import automl
    import mlflow

    spark = SparkSession.builder.getOrCreate()

    result = "FAIL not-run"
    exp_id = None
    try:
        rng = np.random.default_rng(42)
        n = 200
        pdf = pd.DataFrame(
            {
                "x1": rng.normal(size=n),
                "x2": rng.normal(size=n),
                "x3": rng.integers(0, 5, size=n),
            }
        )
        pdf["target"] = (pdf["x1"] + 0.5 * pdf["x2"] > 0).astype(int)
        automl_df = spark.createDataFrame(pdf)

        summary = automl.classify(
            dataset=automl_df,
            target_col="target",
            timeout_minutes=5,
            experiment_dir=EXPERIMENT_DIR,
        )
        exp_id = getattr(getattr(summary, "experiment", None), "experiment_id", None)
        n_trials = len(getattr(summary, "trials", []) or [])
        assert exp_id, "no experiment_id returned"
        assert n_trials > 0, "no trials completed"
        result = f"PASS experiment_id={exp_id} trials={n_trials}"
    except Exception as exc:
        result = f"FAIL {type(exc).__name__}: {exc}"
    finally:
        if exp_id:
            try:
                mlflow.set_tracking_uri("databricks")
                mlflow.MlflowClient().delete_experiment(exp_id)
            except Exception as cleanup_exc:
                print(f"PROBE_CLEANUP_WARNING: experiment delete failed: {cleanup_exc}")
        try:
            from databricks.sdk import WorkspaceClient

            WorkspaceClient().workspace.delete(path=EXPERIMENT_DIR, recursive=True)
        except Exception as cleanup_exc:
            print(f"PROBE_CLEANUP_WARNING: workspace dir delete failed: {cleanup_exc}")

    print(f"PROBE_RESULT: AUTOML={result}")
    return 0 if result.startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
"""


def main() -> int:
    cfg = get_config()

    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.compute import ClusterSpec, DataSecurityMode, Environment
    from databricks.sdk.service.jobs import JobEnvironment, SparkPythonTask, SubmitTask
    from databricks.sdk.service.workspace import ImportFormat

    ws = WorkspaceClient(host=cfg.databricks_host, token=cfg.databricks_token, auth_type="pat")

    print(f"uploading probe sources to {PROBE_DIR} ...")
    ws.workspace.mkdirs(PROBE_DIR)
    ws.workspace.upload(FE_PROBE_PATH, FE_PROBE_SOURCE.encode(), format=ImportFormat.AUTO, overwrite=True)
    ws.workspace.upload(AUTOML_PROBE_PATH, AUTOML_PROBE_SOURCE.encode(), format=ImportFormat.AUTO, overwrite=True)

    fe_task = SubmitTask(
        task_key="feature_engineering_probe",
        spark_python_task=SparkPythonTask(python_file=FE_PROBE_PATH),
        environment_key="fe_probe_env",
    )
    automl_task = SubmitTask(
        task_key="automl_probe",
        spark_python_task=SparkPythonTask(python_file=AUTOML_PROBE_PATH),
        new_cluster=ClusterSpec(
            spark_version="16.4.x-cpu-ml-scala2.12",
            node_type_id="r5.large",
            num_workers=0,
            data_security_mode=DataSecurityMode.SINGLE_USER,
            spark_conf={"spark.databricks.cluster.profile": "singleNode", "spark.master": "local[*]"},
            custom_tags={"ResourceClass": "SingleNode"},
            autotermination_minutes=30,
        ),
    )

    # Workspace policy rejects classic compute entirely ("Only serverless
    # compute is supported in the workspace" -- InvalidParameterValue on the
    # first submit attempt with automl_task's new_cluster included). AutoML
    # requires classic Dedicated-access-mode compute (confirmed against
    # current docs) and cannot run here regardless of cluster spec, so only
    # the serverless feature_engineering_probe is submitted.
    del automl_task
    print(
        "submitting one-time run (feature_engineering_probe: serverless only -- automl_probe skipped, see comment) ..."
    )
    waiter = ws.jobs.submit(
        run_name="zz_verify_bundle_features",
        tasks=[fe_task],
        environments=[
            JobEnvironment(
                environment_key="fe_probe_env",
                spec=Environment(environment_version="2", dependencies=["databricks-feature-engineering>=0.13.0"]),
            )
        ],
    )
    run_id = waiter.run_id
    print(f"submitted run_id={run_id} -- polling ...")

    terminal_states = {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}
    last_state = None
    start = time.monotonic()
    while True:
        run = ws.jobs.get_run(run_id=run_id)
        state = run.state
        life_cycle = state.life_cycle_state.value if state and state.life_cycle_state else "?"
        if life_cycle != last_state:
            elapsed = int(time.monotonic() - start)
            print(f"  [{elapsed}s] life_cycle_state={life_cycle}")
            last_state = life_cycle
        if life_cycle in terminal_states:
            break
        if time.monotonic() - start > 1800:
            print("TIMEOUT after 30 minutes -- aborting poll (run may still be active in the workspace)")
            break
        time.sleep(15)

    result_state = run.state.result_state.value if run.state and run.state.result_state else "?"
    print(f"\nfinal result_state={result_state}")

    exit_code = 0
    for task in run.tasks or []:
        print(f"\n--- task: {task.task_key} ---")
        try:
            output = ws.jobs.get_run_output(run_id=task.run_id)
            logs = (output.logs or "") + (output.error or "")
            for line in logs.splitlines():
                if "PROBE_RESULT" in line or "PROBE_CLEANUP_WARNING" in line:
                    print(" ", line.strip())
                    if "FAIL" in line:
                        exit_code = 1
            if not logs.strip():
                print("  (no logs captured -- task state:", task.state.result_state if task.state else "?", ")")
                if task.state and task.state.result_state and task.state.result_state.value != "SUCCESS":
                    exit_code = 1
        except Exception as exc:
            print(f"  could not fetch output: {exc}")
            exit_code = 1

    print("\ncleanup: deleting uploaded probe source files ...")
    for path in (FE_PROBE_PATH, AUTOML_PROBE_PATH):
        try:
            ws.workspace.delete(path=path)
        except Exception as exc:
            print(f"  cleanup WARNING: failed to delete {path}: {exc}")

    print(f"\nrun URL: {cfg.databricks_host}/jobs/runs/{run_id}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
