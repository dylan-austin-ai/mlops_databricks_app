#!/usr/bin/env python3
"""Builds a complete demo project end-to-end through the app's real
services — the P&C "home risk at time of quote" walkthrough used to verify
progressive/agile provisioning (owner request 2026-07-13). This is not a
simulation: it creates a real GitHub repo, real UC schemas/Volumes, a real
MLflow experiment, real progressive file commits, a real Delta CLONE data
snapshot, and real Volume artifacts (profile report + EDA notebook
snapshot) — the same sequence run interactively to validate
project_provisioning_service.py, bundle_commit_service.py,
data_versioning_service.py, and volume_artifact_service.py.

Idempotent by design: uses a fixed demo project name and the same
idempotent service calls the real wizard UI uses, so re-running picks up
where a prior run left off (skips already-provisioned infrastructure)
instead of duplicating anything. Also idempotent in the CREATE OR REPLACE
sense for the synthetic training table — fixed rand() seeds mean re-running
regenerates identical data.

--teardown drops what this script CAN safely remove (UC schemas/Volumes —
which also removes the Delta CLONE snapshot and saved artifacts inside
them — and soft-deletes the project row). It deliberately does NOT delete
the GitHub repo: same rule as every other deletion path in this app
(services/project_deletion_service.py) — the app never deletes GitHub
content, only reminds you to. It also does not touch the shared
zz_demo_home_risk_training fixture table by default (other demos/sessions
may still want it) — pass --drop-demo-table to remove that too.

Usage:
    python scripts/run_full_demo.py
    python scripts/run_full_demo.py --project-name my_demo_project
    python scripts/run_full_demo.py --teardown
    python scripts/run_full_demo.py --teardown --drop-demo-table
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config  # noqa: E402
from services.bundle_commit_service import BundleCommitService  # noqa: E402
from services.data_profiling_service import DataProfilingService  # noqa: E402
from services.data_versioning_service import DataVersioningService  # noqa: E402
from services.feature_contract_service import FeatureContractService  # noqa: E402
from services.project_provisioning_service import ProjectProvisioningService  # noqa: E402
from services.state_service import StateService  # noqa: E402
from services.volume_artifact_service import VolumeArtifactService  # noqa: E402

DEFAULT_PROJECT_NAME = "pc_home_risk_demo"
TEAM_NAME = "pc-underwriting-ds"
OWNER_EMAIL = "pc-risk-ds@insurer.example"
DEMO_TABLE = "mlops.mlops.zz_demo_home_risk_training"

FEATURE_COLUMNS = [
    "zip_code",
    "home_value_usd",
    "year_built",
    "roof_age_years",
    "distance_to_coast_miles",
    "construction_type",
    "prior_claims_count",
    "credit_based_insurance_score",
    "fire_station_distance_miles",
    "flood_zone_flag",
]


def ensure_demo_table() -> None:
    from services.db_service import DbService

    print(f"[1/9] ensuring synthetic training table {DEMO_TABLE} ...")
    db = DbService()
    db._exec(
        f"""
        CREATE OR REPLACE TABLE {DEMO_TABLE} AS
        SELECT
          id AS policy_quote_id,
          LPAD(CAST(10000 + (id % 500) AS STRING), 5, '0') AS zip_code,
          CAST(120000 + (rand(42) * 880000) AS DOUBLE) AS home_value_usd,
          CAST(1950 + (rand(43) * 74) AS INT) AS year_built,
          CASE WHEN rand(44) < 0.09 THEN NULL ELSE CAST(rand(45) * 40 AS DOUBLE) END AS roof_age_years,
          CAST(rand(46) * 60 AS DOUBLE) AS distance_to_coast_miles,
          CASE CAST(rand(47) * 3 AS INT)
            WHEN 0 THEN 'frame' WHEN 1 THEN 'masonry' ELSE 'mixed' END AS construction_type,
          CASE WHEN rand(48) < 0.06 THEN NULL ELSE CAST(rand(49) * 5 AS INT) END AS prior_claims_count,
          CAST(580 + (rand(50) * 270) AS INT) AS credit_based_insurance_score,
          CAST(rand(51) * 15 AS DOUBLE) AS fire_station_distance_miles,
          CASE WHEN rand(52) < 0.12 THEN 1 ELSE 0 END AS flood_zone_flag,
          CASE WHEN rand(53) < 0.18 THEN 1 ELSE 0 END AS high_risk_label
        FROM (SELECT explode(sequence(1, 500)) AS id)
        """,
        timeout_s=50,
    )
    print("      ok — 500 rows")


def ensure_project(state: StateService, project_name: str, step1_data: dict) -> str:
    existing = state.get_project_by_name(project_name)
    if existing:
        print(f"[2/9] reusing existing project {project_name} ({existing['project_id']})")
        return existing["project_id"]
    project_id = state.create_project(
        project_name=project_name,
        owner_email=OWNER_EMAIL,
        team_name=TEAM_NAME,
        problem_statement=step1_data["problem_statement"],
        created_by=OWNER_EMAIL,
    )
    state.save_project_config(project_id=project_id, interview_responses=step1_data, created_by=OWNER_EMAIL)
    state.update_project_status(project_id, "development", OWNER_EMAIL)
    print(f"[2/9] created project {project_name} ({project_id})")
    return project_id


def print_steps(steps: list[dict], prefix: str = "      ") -> None:
    for s in steps:
        icon = {
            "ok": "OK",
            "skipped": "SKIP",
            "unchanged": "=",
            "blocked_drift": "BLOCKED",
            "pending_deletion": "STALE",
            "failed": "FAIL",
        }.get(s.get("status", ""), s.get("status", ""))
        name = s.get("name") or s.get("path", "")
        detail = s.get("detail", "")
        print(f"{prefix}[{icon}] {name}" + (f" — {detail[:90]}" if detail else ""))


def build(project_name: str) -> str:
    cfg = get_config()
    state = StateService(cfg)

    ensure_demo_table()

    step1_data = {
        "project_name": project_name,
        "team_name": TEAM_NAME,
        "owner_email": OWNER_EMAIL,
        "problem_statement": (
            "Predict riskiness of a home location at time of quote to support real-time underwriting decisions."
        ),
        "success_metric": "AUC-ROC >= 0.78 on held-out quotes; recall >= 0.65 on high-value homes.",
        "existing_repo_url": "",
    }
    project_id = ensure_project(state, project_name, step1_data)

    print("[3/9] Step 1 provisioning (GitHub repo, UC schemas+Volumes, MLflow experiment, Budget Policy) ...")
    provisioning = ProjectProvisioningService(cfg, state=state)
    result = provisioning.provision_step1(project_id, project_name, OWNER_EMAIL, step1_data)
    print_steps(result.steps)
    repo_url = result.github_repo_url or (state.get_project(project_id) or {}).get("github_repo_url", "")
    if not repo_url:
        print("      no GitHub repo (GITHUB_TOKEN not set?) — steps 4-8 need one, stopping here.")
        return project_id
    match_owner, match_repo = repo_url.rsplit("/", 2)[-2:]
    repo_full_name = f"{match_owner}/{match_repo}"

    base_responses = dict(
        step1_data,
        inference_type="real_time",
        sla_latency_ms=150,
        sla_uptime_pct=99.95,
        expected_qps=40,
        model_frameworks=["xgboost"],
        use_automl_baseline=True,
        use_hyperparameter_search=True,
        data_complete=True,
        training_datasets=[DEMO_TABLE],
        target_variable="high_risk_label",
        feature_columns=FEATURE_COLUMNS,
        feature_catalog_resolutions={},
        fairness_attributes=["Race / Ethnicity"],
        bias_test_types=["aif360", "fairlearn"],
        fairness_threshold_pct=10,
        proxy_variables=[
            {
                "column": "zip_code",
                "protected_classes": ["Race / Ethnicity"],
                "justification": "Zip code is a documented proxy for race/national origin in P&C underwriting.",
            },
            {
                "column": "credit_based_insurance_score",
                "protected_classes": ["Race / Ethnicity"],
                "justification": "Credit-based insurance scores are a debated proxy in several state DOI rulings.",
            },
        ],
        retraining_schedule="0 3 * * 0",
        retraining_strategy="hybrid",
        performance_metric_type="auc_roc",
        performance_metric_types=["auc_roc", "recall"],
        custom_monitoring_metrics="False negative rate on high-value homes (home_value_usd > $500k).",
    )
    commits = BundleCommitService(cfg, state=state)

    print("[4/9] Step 2 commit (model specs) ...")
    print_steps(
        commits.commit_step_files(project_id, repo_full_name, 2, project_name, TEAM_NAME, OWNER_EMAIL, base_responses)
    )

    print(
        "[5/9] Step 3: schema inference + profiling (auto-saved to Volume) "
        "+ Feature Catalog check + commit + data versioning ..."
    )
    profiler = DataProfilingService()
    profile = profiler.full_profile(DEMO_TABLE)
    missing_pct = round(profile.missing_cells_pct, 2)
    print(f"      profile: rows={profile.row_count} cols={profile.column_count} missing%={missing_pct}")
    vol_action = state.get_last_infrastructure_action(project_id, "uc_volumes")
    if vol_action and vol_action["resource_id"]:
        saved = VolumeArtifactService(cfg).save_profile_report(vol_action["resource_id"], DEMO_TABLE, profile.html)
        print(f"      profile report saved: {saved}")

    shared = FeatureContractService().catalog_search(shared_only=True)
    matches = {c for c in FEATURE_COLUMNS if c.lower() in {str(f["feature_name"]).lower() for f in shared}}
    print(f"      Feature Catalog matches: {matches or '(none)'}")

    print_steps(
        commits.commit_step_files(project_id, repo_full_name, 3, project_name, TEAM_NAME, OWNER_EMAIL, base_responses)
    )

    uc_schemas_action = state.get_last_infrastructure_action(project_id, "uc_schemas")
    if uc_schemas_action and uc_schemas_action["resource_id"]:
        snaps = DataVersioningService(cfg, state=state).snapshot_all(
            project_id, [DEMO_TABLE], uc_schemas_action["resource_id"], OWNER_EMAIL
        )
        for s in snaps:
            print(f"      snapshot: {s}")

    print("[6/9] Step 4 commit (governance / fairness) ...")
    print_steps(
        commits.commit_step_files(project_id, repo_full_name, 4, project_name, TEAM_NAME, OWNER_EMAIL, base_responses)
    )

    print("[7/9] Step 5 commit (deployment / retraining) ...")
    print_steps(
        commits.commit_step_files(project_id, repo_full_name, 5, project_name, TEAM_NAME, OWNER_EMAIL, base_responses)
    )

    print("[8/9] Step 6 commit (monitoring) ...")
    print_steps(
        commits.commit_step_files(project_id, repo_full_name, 6, project_name, TEAM_NAME, OWNER_EMAIL, base_responses)
    )

    print("[9/9] EDA notebook snapshot to Volume ...")
    try:
        from github import Github

        gh = Github(cfg.github_token)
        eda_content = gh.get_repo(repo_full_name).get_contents("src/eda.py").decoded_content.decode()
        if vol_action and vol_action["resource_id"]:
            eda_saved = VolumeArtifactService(cfg).save_eda_snapshot(vol_action["resource_id"], eda_content)
            print(f"      eda snapshot saved: {eda_saved}")
    except Exception as exc:
        print(f"      skipped: {exc}")

    print()
    print("Full activity log:")
    for a in state.list_infrastructure_actions(project_id):
        print(f"  {a['status']:16s} {a['action_name']:40s} {a['detail'][:60]}")
    print()
    print(f"Done. Project: {project_name} ({project_id})")
    print(f"GitHub repo: {repo_url}")
    return project_id


def teardown(project_name: str, drop_demo_table: bool) -> None:
    cfg = get_config()
    state = StateService(cfg)
    project = state.get_project_by_name(project_name)
    if not project:
        print(f"No project named {project_name!r} found — nothing to tear down.")
    else:
        from services.db_service import DbService

        db = DbService(cfg)
        for env in ("dev", "staging", "prod"):
            schema = project.get(f"uc_schema_{env}", "")
            if schema:
                db._exec(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
                print(f"dropped schema (and everything in it, incl. Volumes/snapshots): {schema}")
        state.update_project_status(project["project_id"], "deleted", OWNER_EMAIL)
        print(f"project row soft-deleted: {project['project_id']}")

        repo_url = project.get("github_repo_url", "")
        if repo_url:
            print()
            print(f"MANUAL ACTION NEEDED — delete or archive this yourself (app has no delete_repo scope): {repo_url}")

    if drop_demo_table:
        from services.db_service import DbService

        DbService(cfg)._exec(f"DROP TABLE IF EXISTS {DEMO_TABLE}")
        print(f"dropped {DEMO_TABLE}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--teardown", action="store_true", help="Tear down what this script can safely remove.")
    parser.add_argument(
        "--drop-demo-table", action="store_true", help="With --teardown, also drop the shared demo training table."
    )
    args = parser.parse_args()

    if args.teardown:
        teardown(args.project_name, args.drop_demo_table)
    else:
        build(args.project_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
