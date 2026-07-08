#!/usr/bin/env python3
"""Live verification — phase 10 streaming round-trip against the synthetic source.

Proves the §9.4 streaming deployment shape end-to-end on the live workspace:
source-table precheck → generate → validate → plan → deploy → SDK read-back
(job exists AND carries a continuous trigger) → destroy. Safe to re-run;
everything it creates, it destroys.

Synthetic source sanctioned per owner decision 2026-07-07 (fake-data pilot);
re-verify against a real governed stream before any production streaming claim.

Usage:
    python scripts/verify_live_streaming.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config  # noqa: E402
from services.bundle_service import BundleService  # noqa: E402

PROJECT = "ctrl_plane_stream_smoke"
SCORER_JOB_NAME = f"[dev] {PROJECT} — streaming scorer"


def main() -> int:
    cfg = get_config()
    source_table = f"{cfg.projects_catalog}.demo_streaming.events"

    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient(host=cfg.databricks_host, token=cfg.databricks_token)

    # §9.4 boundary: the governed source must already exist — never authored here
    try:
        ws.tables.get(full_name=source_table)
        print(f"precheck: source table exists: {source_table}")
    except Exception as exc:
        print(f"FAILED precheck: {source_table} not found ({exc})")
        print("Seed it first: python scripts/seed_demo_data.py")
        return 1

    svc = BundleService(cfg)
    print("CLI health:", svc.health_check())

    with tempfile.TemporaryDirectory(prefix="mlops_live_stream_") as tmp:
        bundle_dir = svc.generate(
            project_name=PROJECT,
            team_name="mlops_platform",
            owner_email="dylan.austin.ai@gmail.com",
            interview_responses={
                "inference_type": "streaming",
                "streaming_source_table": source_table,
            },
            output_dir=Path(tmp),
        )
        print("generated:", bundle_dir)

        svc.validate(bundle_dir, "dev")
        print("validate: ok")

        plan = svc.plan(bundle_dir, "dev")
        print(f"plan: {len(plan.actions)} action(s), hash {plan.plan_hash[:12]}")
        for action in plan.actions:
            print("  ", action["action"], action["resource"])

        try:
            svc.deploy(bundle_dir, plan)
            print("deploy: ok (from reviewed plan file)")

            failures = 0
            for check in svc.verify(bundle_dir, "dev"):
                mark = "✓" if check.exists else "✗"
                print(f"verify {mark} [{check.resource_type}] {check.resource_key}: {check.detail}")
                failures += 0 if check.exists else 1

            # Phase-10-specific read-back: the scorer must be a continuous job
            continuous_seen = False
            for job in ws.jobs.list(name=SCORER_JOB_NAME):
                settings = ws.jobs.get(job_id=job.job_id).settings
                if settings and settings.continuous is not None:
                    continuous_seen = True
                    print(
                        f"verify ✓ [job] continuous trigger confirmed (pause_status={settings.continuous.pause_status})"
                    )
            if not continuous_seen:
                print("verify ✗ [job] streaming scorer not found or not continuous")
                failures += 1

            if failures:
                print(f"FAILED: {failures} check(s)")
                return 1
        finally:
            svc.destroy(bundle_dir, "dev")
            print("destroy: ok — workspace state cleaned")

    print(
        "\nStreaming round-trip verified (synthetic source): "
        "generate → validate → plan → deploy → continuous read-back → destroy"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
