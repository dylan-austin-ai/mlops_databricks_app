#!/usr/bin/env python3
"""Live verification runbook — run once the workspace org is active again.

Proves the Week 1 success criterion end-to-end against the real workspace:
generate → validate → plan → deploy (from reviewed plan) → SDK read-back
verify → destroy. Safe to re-run; everything it creates, it destroys.

Usage:
    python scripts/verify_live_roundtrip.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.bundle_service import BundleService  # noqa: E402


def main() -> int:
    svc = BundleService()
    print("CLI health:", svc.health_check())

    with tempfile.TemporaryDirectory(prefix="mlops_live_verify_") as tmp:
        bundle_dir = svc.generate(
            project_name="ctrl_plane_smoke",
            team_name="mlops_platform",
            owner_email="dylan.austin.ai@gmail.com",
            interview_responses={
                "inference_type": "batch",
                "batch_schedule": "0 2 * * *",
                "retraining_schedule": "0 3 * * 0",
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
            if failures:
                print(f"FAILED: {failures} resource(s) missing on read-back")
                return 1
        finally:
            svc.destroy(bundle_dir, "dev")
            print("destroy: ok — workspace state cleaned")

    print("\nLive round-trip verified: generate → validate → plan → deploy → verify → destroy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
