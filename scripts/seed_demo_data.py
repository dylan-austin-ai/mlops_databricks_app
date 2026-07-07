#!/usr/bin/env python3
"""Seed a coherent, teardown-able demo dataset into the live control plane.

Owner decision 2026-07-07: everything must be pilotable and demoable on fake
data. This seeds one fully-governed demo project (config, model, versions,
approvals, deployments, performance, costs, business impact, features,
revalidation flag, HITL queue) plus a synthetic streaming source that stands
in for an upstream producer.

Demo rows use fixed `demo-` IDs and the `demo_` name prefix, so seeding is
idempotent (teardown-then-seed) and teardown removes exactly what seeding
created. Audit-log rows are intentionally left in place — the audit trail is
append-only, even for demos.

Usage:
    python scripts/seed_demo_data.py             # teardown + seed everything
    python scripts/seed_demo_data.py --tick      # append a fresh micro-batch
                                                 # to the streaming source
    python scripts/seed_demo_data.py --teardown  # remove all demo data
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config  # noqa: E402
from services.policy_pack_service import PolicyPackService  # noqa: E402
from services.state_service import StateService  # noqa: E402

PROJECT = "demo_churn"
TEAM = "demo_team"
OWNER = "demo.owner@example.com"

PID = "demo-project-0001"
MID = "demo-model-0001"
V1 = "demo-version-0001"
V2 = "demo-version-0002"
F1 = "demo-feature-0001"
F2 = "demo-feature-0002"
PLAN_HASH = "demo-plan-hash-0001"

STREAM_SCHEMA = "demo_streaming"
STREAM_TABLE = "events"

FEATURES = ["age", "tenure_months", "monthly_charges", "support_tickets_90d"]

INTERVIEW_RESPONSES = {
    "project_name": PROJECT,
    "problem_statement": "Demo: predict which customers will churn in the next 30 days",
    "success_metric": "AUC-ROC >= 0.85 on holdout",
    "team_name": TEAM,
    "owner_email": OWNER,
    "inference_type": "batch",
    "batch_frequency": "daily",
    "batch_schedule": "0 2 * * *",
    "model_frameworks": ["xgboost"],
    "training_datasets": ["mlops.demo_streaming.events"],
    "target_variable": "churn_flag",
    "feature_columns": FEATURES,
    "training_data_size_rows": 500,
    "contains_pii": False,
    "pii_columns": [],
    "data_classification": "internal",
    "fairness_attributes": ["Age"],
    "fairness_threshold_pct": 10,
    "bias_test_types": ["aif360", "fairlearn"],
    "protected_attribute_justifications": {"Age": "Demo: age is a direct model feature."},
    "data_quality_required_fields": FEATURES,
    "data_quality_acceptable_issues": [],
    "risk_tier": "tier_2",
    "risk_tier_justification": "Demo project — moderate materiality churn scoring.",
    "applied_policy_packs": ["generic_tiering_v1"],
    "retraining_strategy": "hybrid",
    "retraining_schedule": "0 3 * * 0",
    "monitor_data_drift": True,
    "monitor_performance_drift": True,
    "performance_metric_type": "accuracy",
    "performance_alert_threshold_pct": 5.0,
    "alert_destination_configs": [{"destination": "email", "email_addresses": [OWNER]}],
    "code_review_count": 2,
    "testing_threshold_pct": 100,
}


def _uc_model(cfg) -> str:
    return f"{cfg.projects_catalog_for('prod')}.{PROJECT}_prod.{PROJECT}"


def teardown(state: StateService, cfg) -> None:
    """Delete exactly the rows seeding creates (audit_logs deliberately kept)."""
    tbl = state._tbl
    statements = [
        (f"DELETE FROM {tbl('hitl_reviews')} WHERE project_id = :pid", {"pid": PID}),
        (f"DELETE FROM {tbl('revalidation_flags')} WHERE project_id = :pid", {"pid": PID}),
        (f"DELETE FROM {tbl('business_impact')} WHERE project_id = :pid", {"pid": PID}),
        (f"DELETE FROM {tbl('business_value_fns')} WHERE project_id = :pid", {"pid": PID}),
        (f"DELETE FROM {tbl('feature_lineage')} WHERE feature_id IN ('{F1}', '{F2}')", None),
        (f"DELETE FROM {tbl('features')} WHERE feature_id IN ('{F1}', '{F2}')", None),
        (f"DELETE FROM {tbl('cost_tracking')} WHERE project_id = :pid", {"pid": PID}),
        (f"DELETE FROM {tbl('model_performance')} WHERE model_id = :mid", {"mid": MID}),
        (f"DELETE FROM {tbl('bundle_deployments')} WHERE project_id = :pid", {"pid": PID}),
        (f"DELETE FROM {tbl('approvals')} WHERE model_id = :mid", {"mid": MID}),
        (f"DELETE FROM {tbl('model_versions')} WHERE model_id = :mid", {"mid": MID}),
        (f"DELETE FROM {tbl('models')} WHERE project_id = :pid", {"pid": PID}),
        (f"DELETE FROM {tbl('reconciliation_runs')} WHERE run_id LIKE 'demo-%'", None),
        (f"DELETE FROM {tbl('project_configurations')} WHERE project_id = :pid", {"pid": PID}),
        (f"DELETE FROM {tbl('projects')} WHERE project_id = :pid", {"pid": PID}),
    ]
    for sql, params in statements:
        state._exec(sql, params)
    state._exec(f"DROP SCHEMA IF EXISTS {cfg.projects_catalog}.{STREAM_SCHEMA} CASCADE")
    print("teardown: demo rows and streaming schema removed")


def seed(state: StateService, cfg) -> None:
    tbl = state._tbl
    uc_model = _uc_model(cfg)

    # ── project + config + tier ─────────────────────────────────────────────
    state._exec(
        f"""INSERT INTO {tbl("projects")}
            (project_id, project_name, project_description, created_timestamp,
             created_by, owner_email, owner_name, team_name, status,
             requires_human_review, hitl_mode, hitl_sla_minutes)
            VALUES (:pid, :name, :descr, current_timestamp() - INTERVAL 45 DAYS,
                    :owner, :owner, 'Demo Owner', :team, 'production',
                    true, 'asynchronous', 240)""",
        {"pid": PID, "name": PROJECT, "descr": "Demo churn model (fake data)", "owner": OWNER, "team": TEAM},
    )
    state.save_project_config(project_id=PID, interview_responses=INTERVIEW_RESPONSES, created_by=OWNER)
    PolicyPackService(state=state).assign_to_project(
        PID,
        risk_tier="tier_2",
        pack_ids=["generic_tiering_v1"],
        justification="Demo project — moderate materiality churn scoring.",
        actor_email=OWNER,
    )

    # ── model + versions (v2 is champion) ───────────────────────────────────
    state._exec(
        f"""INSERT INTO {tbl("models")}
            (model_id, project_id, model_name, model_type, framework, status,
             is_production, owner_email, team_name, created_timestamp, created_by)
            VALUES (:mid, :pid, :name, 'xgboost', 'xgboost', 'production',
                    true, :owner, :team, current_timestamp() - INTERVAL 40 DAYS, :owner)""",
        {"mid": MID, "pid": PID, "name": PROJECT, "owner": OWNER, "team": TEAM},
    )
    for vid, vnum, aliases, days in ((V1, 1, "array()", 40), (V2, 2, "array('champion')", 20)):
        state._exec(
            f"""INSERT INTO {tbl("model_versions")}
                (version_id, model_id, version_number, mlflow_stage, accuracy, auc_roc,
                 fairness_test_passed, status, created_timestamp, created_by,
                 uc_full_name, uc_version, current_aliases, last_reconciled_timestamp)
                VALUES (:vid, :mid, :vnum, 'Production', :acc, :auc,
                        true, 'deployed', current_timestamp() - INTERVAL {days} DAYS, :owner,
                        :uc_model, :vnum, {aliases}, current_timestamp())""",
            {
                "vid": vid,
                "mid": MID,
                "vnum": vnum,
                "acc": 0.83 + vnum * 0.02,
                "auc": 0.86 + vnum * 0.02,
                "owner": OWNER,
                "uc_model": uc_model,
            },
        )

    # ── approvals: the tier_2 gate set approved for v2, one pending for vNext ─
    gates = [
        ("code_review", "approved", 34),
        ("legal_review", "approved", 32),
        ("business_approval", "approved", 30),
        ("legal_review", "pending", 2),
    ]
    for gate, status, days_ago in gates:
        completed_expr = (
            f"current_timestamp() - INTERVAL {days_ago} DAYS" if status == "approved" else "NULL"
        )
        responses = (
            [{"approver_email": f"demo.{gate}@example.com", "approval_decision": "approve"}]
            if status == "approved"
            else []
        )
        state._exec(
            f"""INSERT INTO {tbl("approvals")}
                (approval_id, model_id, approval_type, approval_gate,
                 requested_timestamp, requested_by, required_count, approval_responses,
                 approved_count, rejected_count, status, completed_timestamp,
                 created_timestamp, plan_hash)
                VALUES (:aid, :mid, :gate, :gate,
                        current_timestamp() - INTERVAL {days_ago + 1} DAYS, :owner, 1, :responses,
                        :approved, 0, :status,
                        {completed_expr},
                        current_timestamp() - INTERVAL {days_ago + 1} DAYS, :plan_hash)""",
            {
                "aid": f"demo-approval-{gate}-{days_ago}",
                "mid": MID,
                "gate": gate,
                "owner": OWNER,
                "responses": json.dumps(responses),
                "approved": 1 if status == "approved" else 0,
                "status": status,
                # 1:1 with the prod deploy so the §14.1 speed join counts one promotion
                "plan_hash": PLAN_HASH if gate == "business_approval" and status == "approved" else None,
            },
        )

    # ── deployments: joined to approvals by plan_hash (speed metric, §14.1) ──
    deploys = [("dev", "deployed", 29), ("staging", "deployed", 25), ("prod", "deployed", 20), ("dev", "failed", 8)]
    for target, status, days_ago in deploys:
        state._exec(
            f"""INSERT INTO {tbl("bundle_deployments")}
                (deployment_id, project_id, target, plan_hash, status, detail,
                 actor_email, created_timestamp)
                VALUES (:did, :pid, :target, :plan_hash, :status, 'demo seed',
                        :owner, current_timestamp() - INTERVAL {days_ago} DAYS)""",
            {
                "did": f"demo-deploy-{target}-{days_ago}",
                "pid": PID,
                "target": target,
                "plan_hash": PLAN_HASH if target == "prod" else f"demo-plan-hash-{target}-{days_ago}",
                "status": status,
                "owner": OWNER,
            },
        )

    # ── performance: healthy champion, one degraded blip ────────────────────
    perf = [(V2, 0.85, 1.2, False, 15), (V2, 0.84, 2.8, False, 10), (V2, 0.79, 6.4, True, 5), (V2, 0.85, 0.9, False, 1)]
    for vid, acc, degradation, degraded, days_ago in perf:
        state._exec(
            f"""INSERT INTO {tbl("model_performance")}
                (performance_id, version_id, model_id, measurement_timestamp,
                 measurement_window, predictions_count, accuracy,
                 performance_degraded, degradation_pct, created_timestamp)
                VALUES (:perf_id, :vid, :mid, current_timestamp() - INTERVAL {days_ago} DAYS,
                        'last_24h', :n, :acc, :degraded, :degradation,
                        current_timestamp() - INTERVAL {days_ago} DAYS)""",
            {
                "perf_id": f"demo-perf-{days_ago}",
                "vid": vid,
                "mid": MID,
                "n": 4200,
                "acc": acc,
                "degraded": degraded,
                "degradation": degradation,
            },
        )

    # ── costs: 14 days of spend ──────────────────────────────────────────────
    for day in range(1, 15):
        total = round(3.5 + (day % 5) * 1.7, 2)
        state._exec(
            f"""INSERT INTO {tbl("cost_tracking")}
                (cost_id, model_id, project_id, date, compute_cost_usd,
                 total_cost_usd, billing_tag, created_timestamp)
                VALUES (:cid, :mid, :pid, date_sub(current_date(), {day}), :cost,
                        :cost, 'project_id', current_timestamp())""",
            {"cid": f"demo-cost-{day}", "mid": MID, "pid": PID, "cost": total},
        )

    # ── business impact with a recently-reviewed value fn (high confidence) ──
    state._exec(
        f"""INSERT INTO {tbl("business_value_fns")}
            (project_id, definition_json, assumption_source, reviewed_by,
             last_reviewed_date, created_timestamp)
            VALUES (:pid, :definition, 'Demo finance assumptions', :owner,
                    date_sub(current_date(), 30), current_timestamp())""",
        {"pid": PID, "definition": json.dumps({"true_positive_usd": 120, "false_positive_usd": -8}), "owner": OWNER},
    )
    for period in range(3):
        start, end = 30 * (period + 1), 30 * period
        state._exec(
            f"""INSERT INTO {tbl("business_impact")}
                (project_id, period_start, period_end, revenue_lift_usd,
                 loss_avoided_usd, automation_rate_pct, computed_timestamp)
                VALUES (:pid, date_sub(current_date(), {start}), date_sub(current_date(), {end}),
                        :lift, :avoided, 62.0, current_timestamp())""",
            {"pid": PID, "lift": 18500.0 + period * 2400, "avoided": 6200.0},
        )

    # ── shared features with multi-consumer lineage (reuse metric, §8.5) ─────
    for fid, name in ((F1, "tenure_months"), (F2, "monthly_charges")):
        state._exec(
            f"""INSERT INTO {tbl("features")}
                (feature_id, project_id, feature_name, feature_type, owner_email,
                 owner_team, is_active, is_shared, created_timestamp, created_by)
                VALUES (:fid, :pid, :name, 'numeric', :owner, :team, true, true,
                        current_timestamp(), :owner)""",
            {"fid": fid, "pid": PID, "name": name, "owner": OWNER, "team": TEAM},
        )
        state._exec(
            f"""INSERT INTO {tbl("feature_lineage")}
                (lineage_id, feature_id, source_table_name, downstream_model_ids,
                 created_timestamp, created_by)
                VALUES (:lid, :fid, :source, array('{MID}', 'demo-other-model'),
                        current_timestamp(), :owner)""",
            {
                "lid": f"demo-lineage-{fid}",
                "fid": fid,
                "source": f"{cfg.projects_catalog}.{STREAM_SCHEMA}.{STREAM_TABLE}",
                "owner": OWNER,
            },
        )

    # ── one revalidation flag (warn) so §20.5 surfaces are demoable ──────────
    state._exec(
        f"""INSERT INTO {tbl("revalidation_flags")}
            (project_id, uc_full_name, champion_version, frequency_days,
             on_due_action, status, revalidation_approval_ids, due_since,
             last_checked_timestamp)
            VALUES (:pid, :uc_model, 2, 365, 'warn', 'due', array(),
                    current_timestamp() - INTERVAL 3 DAYS, current_timestamp())""",
        {"pid": PID, "uc_model": uc_model},
    )

    # ── HITL queue: pending, decided, escalated (§11) ────────────────────────
    hitl = [
        ("demo-pred-001", None, False, 2),
        ("demo-pred-002", None, False, 1),
        ("demo-pred-003", "approved", False, 3),
        ("demo-pred-004", None, True, 6),
    ]
    for pred_id, decision, escalated, hours_ago in hitl:
        state._exec(
            f"""INSERT INTO {tbl("hitl_reviews")}
                (prediction_id, project_id, presented_timestamp, reviewer_email,
                 decision, decision_timestamp, escalated)
                VALUES (:pred_id, :pid, current_timestamp() - INTERVAL {hours_ago} HOURS,
                        :reviewer, :decision,
                        {"current_timestamp() - INTERVAL 2 HOURS" if decision else "NULL"},
                        :escalated)""",
            {
                "pred_id": pred_id,
                "pid": PID,
                "reviewer": "demo.reviewer@example.com" if decision else None,
                "decision": decision,
                "escalated": escalated,
            },
        )

    # ── reconciliation health history (§21.1) ────────────────────────────────
    for i, job in enumerate(("model_alias_reconcile", "cost_reconcile", "revalidation_check")):
        state._exec(
            f"""INSERT INTO {tbl("reconciliation_runs")}
                (run_id, job_name, target_table, rows_examined, rows_changed,
                 status, detail, run_timestamp)
                VALUES (:rid, :job, 'demo', 12, 3, 'ok', '',
                        current_timestamp() - INTERVAL {i + 1} HOURS)""",
            {"rid": f"demo-recon-{i}", "job": job},
        )

    print(f"seed: demo project '{PROJECT}' written ({PID})")


def seed_stream(state: StateService, cfg, rows: int = 500) -> None:
    """Create the synthetic streaming source — a stand-in upstream producer."""
    full = f"{cfg.projects_catalog}.{STREAM_SCHEMA}.{STREAM_TABLE}"
    state._exec(f"CREATE SCHEMA IF NOT EXISTS {cfg.projects_catalog}.{STREAM_SCHEMA}")
    state._exec(
        f"""CREATE TABLE IF NOT EXISTS {full} (
              event_ts TIMESTAMP,
              customer_id STRING,
              age INT,
              tenure_months INT,
              monthly_charges DOUBLE,
              support_tickets_90d INT,
              churn_flag INT
            ) COMMENT 'Synthetic demo source — stands in for an upstream producer (fake data)'"""
    )
    tick(state, cfg, rows=rows, backfill_minutes=60 * 24)
    print(f"seed: streaming source {full} ready with {rows} rows")


def tick(state: StateService, cfg, rows: int = 25, backfill_minutes: int = 0) -> None:
    """Append one micro-batch of synthetic events — what an upstream would do."""
    full = f"{cfg.projects_catalog}.{STREAM_SCHEMA}.{STREAM_TABLE}"
    state._exec(
        f"""INSERT INTO {full}
            SELECT
              current_timestamp() - make_interval(0, 0, 0, 0, 0, CAST(rand() * {backfill_minutes} AS INT), 0),
              concat('cust_', CAST(CAST(rand() * 100000 AS INT) AS STRING)),
              CAST(21 + rand() * 60 AS INT),
              CAST(1 + rand() * 96 AS INT),
              ROUND(20 + rand() * 180, 2),
              CAST(rand() * 6 AS INT),
              CAST(rand() < 0.18 AS INT)
            FROM range({rows})"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed/teardown demo data (fake) for pilots and demos")
    parser.add_argument("--teardown", action="store_true", help="remove all demo data and exit")
    parser.add_argument("--tick", action="store_true", help="append a fresh micro-batch to the streaming source")
    parser.add_argument("--rows", type=int, default=None, help="row count for seed (default 500) or tick (default 25)")
    args = parser.parse_args()

    cfg = get_config()
    state = StateService()

    if args.teardown:
        teardown(state, cfg)
        return 0
    if args.tick:
        tick(state, cfg, rows=args.rows or 25)
        print(f"tick: appended {args.rows or 25} synthetic events")
        return 0

    teardown(state, cfg)  # idempotent: always reseed from clean
    seed(state, cfg)
    seed_stream(state, cfg, rows=args.rows or 500)
    print("\nDemo data ready — every page now has something to show. Fake data throughout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
