"""Approval Saga Engine — PromoteToProduction with compensating actions (§15.2).

The saga deploys the exact plan file recorded on the approval (§15.1) — it
re-hashes the file and aborts on drift rather than deploying anything that
wasn't reviewed. Step 7 (audit record) always runs, even on failure, so the
audit trail records exactly what state was reached.

Step semantics per §15.2:
  1. verify gates          read-only; abort if unsatisfied. Includes the union
                           of the project's policy-pack-required gates (§20.2 —
                           which gates are required is data, never a hardcoded
                           list, §28) and refuses promotion while a blocking
                           revalidation flag is active (§20.5)
  2. bundle deploy --plan  abort on failure, nothing to compensate
  3. register to prod      on failure: bundle deployed but no traffic change —
                           safe; alert MLOps and stop
  4. @challenger + canary  on failure: re-point champion back (compensate)
  5. canary window         pluggable check; on breach: compensate step 4,
                           no promotion. Default when no monitoring is attached
                           yet: skip with a logged reason — never silently pass.
  6. promote @champion     on failure: manual rollback runbook alert
  6.5 assemble model card  failure logs a governance-coverage penalty,
                           never blocks promotion (§12.3)
  7. audit record          always runs

§29.3 refinement implemented in handle_approved_revocation(): revoking the
approval behind the *current* champion triggers rollback; revoking a
historical, superseded approval opens an investigation record instead —
no automatic model action.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.bundle_service import BundleService, PlanSummary
from services.policy_pack_service import PolicyPackService
from services.registry_service import CHALLENGER, CHAMPION, RegistryService
from services.state_service import StateService


class SagaAborted(RuntimeError):
    """Saga stopped before completing promotion; state recorded in the log."""


@dataclass
class SagaStepResult:
    name: str
    status: str  # ok | failed | compensated | skipped
    detail: str = ""


@dataclass
class SagaResult:
    saga_id: str
    promoted: bool
    steps: list[SagaStepResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append(SagaStepResult(name, status, detail))


class PromoteToProductionSaga:
    def __init__(
        self,
        state: StateService | None = None,
        bundles: BundleService | None = None,
        registry: RegistryService | None = None,
        canary_check: Callable[[str], bool | None] | None = None,
        policy: PolicyPackService | None = None,
    ) -> None:
        """canary_check(uc_full_name) returns True (healthy), False (breach),
        or None (no monitoring attached — logged as skipped, not passed).
        When omitted, the step-6 default applies (decision 2026-07-07): the
        project's primary performance metric with its alert threshold as the
        breach condition — see make_default_canary_check()."""
        self._state = state or StateService()
        self._bundles = bundles or BundleService()
        self._registry = registry or RegistryService()
        self._canary_check = canary_check
        self._policy = policy or PolicyPackService(state=self._state)

    def run(
        self,
        *,
        project_id: str,
        approval_id: str,
        bundle_dir: Path,
        uc_full_name: str,
        candidate_version: int,
        actor_email: str,
        approval_manifest_hash: str = "",
        fairness_test_result: str = "",
    ) -> SagaResult:
        saga_id = str(uuid.uuid4())
        result = SagaResult(saga_id=saga_id, promoted=False)
        prior_champion = self._registry.alias_version(uc_full_name, CHAMPION)

        try:
            # 1 — verify gates (read-only)
            approval = self._state.get_approval(approval_id)
            if approval is None or str(approval.get("status")) != "approved":
                result.add("verify_gates", "failed", f"approval {approval_id} not approved")
                raise SagaAborted("approval gates not satisfied")
            missing = sorted(self._policy.unsatisfied_gates(project_id))
            if missing:
                result.add("verify_gates", "failed", f"policy-pack gates not approved: {missing}")
                raise SagaAborted("policy-pack gates not satisfied (§20.2)")
            block = self._policy.revalidation_block(project_id)
            if block in ("block_new_traffic", "block_all_traffic"):
                result.add("verify_gates", "failed", f"revalidation due — {block} in force (§20.5)")
                raise SagaAborted("revalidation due — promotion blocked until re-review completes")
            result.add("verify_gates", "ok")

            # 2 — deploy the exact reviewed plan (§15.1)
            plan_path = str(approval.get("plan_path") or "")
            plan_hash = str(approval.get("plan_hash") or "")
            if not plan_path or not plan_hash:
                result.add("bundle_deploy", "failed", "approval has no reviewed plan attached")
                raise SagaAborted("no reviewed plan on approval record")
            plan_file = Path(plan_path)
            if not plan_file.exists():
                result.add("bundle_deploy", "failed", f"plan file missing: {plan_path}")
                raise SagaAborted("reviewed plan file missing")
            current_hash = hashlib.sha256(plan_file.read_bytes()).hexdigest()
            if current_hash != plan_hash:
                result.add("bundle_deploy", "failed", "plan file hash drifted since review")
                raise SagaAborted("plan drift — refusing to deploy unreviewed plan")
            plan = PlanSummary(target="prod", plan_path=plan_file, plan_hash=plan_hash)
            try:
                self._bundles.deploy(bundle_dir, plan)
                result.add("bundle_deploy", "ok")
            except Exception as exc:
                result.add("bundle_deploy", "failed", str(exc))
                raise SagaAborted("bundle deploy failed — aborted, no further steps") from exc

            # 3 — model version registered into prod catalog (precondition
            # checked here; the copy happens upstream in the promotion flow)
            try:
                aliases = self._registry.alias_map(uc_full_name)
                result.add("register_prod_model", "ok", f"aliases now: {aliases}")
            except Exception as exc:
                result.add("register_prod_model", "failed", str(exc))
                raise SagaAborted("bundle deployed, no traffic change yet — safe; alert MLOps") from exc

            # 4 — challenger alias + canary traffic
            try:
                self._registry.promote(
                    uc_full_name,
                    candidate_version,
                    CHALLENGER,
                    actor_email=actor_email,
                    approval_manifest_hash=approval_manifest_hash,
                    fairness_test_result=fairness_test_result,
                )
                result.add("set_challenger_canary", "ok")
            except Exception as exc:
                result.add("set_challenger_canary", "failed", str(exc))
                raise SagaAborted("challenger alias failed — champion untouched") from exc

            # 5 — canary window
            check = self._canary_check or make_default_canary_check(self._state, self._registry, project_id)
            canary = check(uc_full_name)
            if canary is False:
                self._compensate_challenger(uc_full_name, actor_email, result)
                raise SagaAborted("canary threshold breach — promotion cancelled")
            result.add(
                "canary_window",
                "ok" if canary else "skipped",
                "" if canary else "no monitoring attached — skipped, not passed (§15.2)",
            )

            # 6 — promote champion
            try:
                self._registry.promote(
                    uc_full_name,
                    candidate_version,
                    CHAMPION,
                    actor_email=actor_email,
                    approval_manifest_hash=approval_manifest_hash,
                    fairness_test_result=fairness_test_result,
                    promoted_from_alias=CHALLENGER,
                    # Ties the live champion back to the exact approval that
                    # authorized it — what §29.3 revocation handling checks.
                    extra_tags={"approval_id": approval_id},
                )
                result.add("promote_champion", "ok")
                result.promoted = True
            except Exception as exc:
                result.add("promote_champion", "failed", f"manual rollback runbook: {exc}")
                raise SagaAborted("champion promotion failed — manual runbook") from exc

            # 6.5 — model card assembly: never blocks promotion (§12.3)
            try:
                card_path = assemble_model_card(
                    bundle_dir,
                    project_id=project_id,
                    uc_full_name=uc_full_name,
                    version=candidate_version,
                    approval=approval,
                    fairness_test_result=fairness_test_result,
                )
                result.add("assemble_model_card", "ok", str(card_path))
            except Exception as exc:
                result.add(
                    "assemble_model_card",
                    "failed",
                    f"governance-coverage penalty, promotion unaffected: {exc}",
                )

        except SagaAborted as exc:
            result.add("saga_outcome", "failed", str(exc))
        finally:
            # 7 — always record exactly what state was reached
            self._state.log_audit(
                action_type="promotion_saga",
                actor_email=actor_email,
                actor_role="saga_engine",
                resource_type="model",
                resource_id=uc_full_name,
                project_id=project_id,
                approval_id=approval_id,
                change_details={
                    "saga_id": saga_id,
                    "promoted": result.promoted,
                    "prior_champion": prior_champion,
                    "candidate_version": candidate_version,
                    "steps": [{"name": s.name, "status": s.status, "detail": s.detail} for s in result.steps],
                },
                action_status="success" if result.promoted else "failure",
            )
        return result

    def _compensate_challenger(self, uc_full_name: str, actor_email: str, result: SagaResult) -> None:
        try:
            client = self._registry._client()
            client.delete_registered_model_alias(name=uc_full_name, alias=CHALLENGER)
            result.add("set_challenger_canary", "compensated", "challenger alias removed")
        except Exception as exc:
            result.add("set_challenger_canary", "failed", f"compensation failed: {exc}")


def make_default_canary_check(
    state: StateService, registry: RegistryService, project_id: str
) -> Callable[[str], bool | None]:
    """Default canary gate (decision of record 2026-07-07): breach when the
    challenger's primary performance metric — the one chosen in wizard step 6 —
    degrades past that step's alert threshold. Missing config or no
    monitoring rows yet returns None: skipped and logged, never silently
    passed (§15.2)."""

    def check(uc_full_name: str) -> bool | None:
        rows = state._exec(
            f"""SELECT interview_responses, alert_threshold_deviation_pct
                FROM {state._tbl("project_configurations")}
                WHERE project_id = :project_id
                ORDER BY config_version DESC LIMIT 1""",
            {"project_id": project_id},
        )
        if not rows:
            return None
        threshold: float | None = None
        try:
            responses = json.loads(str(rows[0].get("interview_responses") or "{}"))
            raw = responses.get("performance_alert_threshold_pct")
            threshold = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            threshold = None
        if threshold is None and rows[0].get("alert_threshold_deviation_pct") is not None:
            threshold = float(rows[0]["alert_threshold_deviation_pct"])
        if threshold is None:
            return None

        challenger = registry.alias_version(uc_full_name, CHALLENGER)
        if challenger is None:
            return None

        perf = state._exec(
            f"""SELECT max(CASE WHEN p.performance_degraded THEN 1 ELSE 0 END) AS degraded,
                       max(p.degradation_pct) AS worst_degradation_pct,
                       count(*) AS n
                FROM {state._tbl("model_performance")} p
                JOIN {state._tbl("model_versions")} v ON v.version_id = p.version_id
                WHERE v.uc_full_name = :uc_full_name AND v.uc_version = :version""",
            {"uc_full_name": uc_full_name, "version": challenger},
        )
        row = perf[0] if perf else {}
        if not int(row.get("n") or 0):
            return None  # no monitoring rows for the candidate yet
        degraded = int(row.get("degraded") or 0) == 1
        worst = float(row.get("worst_degradation_pct") or 0.0)
        return not (degraded or worst >= threshold)

    return check


def handle_approved_revocation(
    *,
    state: StateService,
    registry: RegistryService,
    original_approval: dict[str, Any],
    uc_full_name: str,
    actor_email: str,
    reason: str,
) -> str:
    """§29.3: rollback only if the revoked approval backs the current champion.

    Returns "rolled_back" or "investigation_opened".
    """
    champion_version = registry.alias_version(uc_full_name, CHAMPION)
    original_id = str(original_approval.get("approval_id") or "")

    is_current = False
    if champion_version is not None and original_id:
        client = registry._client()
        mv = client.get_model_version(name=uc_full_name, version=str(champion_version))
        tags = getattr(mv, "tags", None) or {}
        is_current = tags.get("approval_id") == original_id

    if is_current and champion_version is not None:
        registry.rollback_champion(uc_full_name, actor_email=actor_email, reason=reason)
        state.log_audit(
            action_type="revocation_rollback",
            actor_email=actor_email,
            actor_role="saga_engine",
            resource_type="model",
            resource_id=uc_full_name,
            approval_id=str(original_approval.get("approval_id") or ""),
            change_details={"reason": reason, "rolled_back_version": champion_version},
        )
        return "rolled_back"

    state.log_audit(
        action_type="revocation_investigation_opened",
        actor_email=actor_email,
        actor_role="saga_engine",
        resource_type="approval",
        resource_id=str(original_approval.get("approval_id") or ""),
        change_details={
            "reason": reason,
            "note": "historical approval revoked — no automatic model action (§29.3)",
        },
    )
    return "investigation_opened"


def assemble_model_card(
    bundle_dir: Path,
    *,
    project_id: str,
    uc_full_name: str,
    version: int,
    approval: dict[str, Any],
    fairness_test_result: str = "",
) -> Path:
    """Mechanically assemble docs/MODEL_CARD.md at promotion (§12.3).

    v1 populates the sections the control plane already has data for; later
    phases add live-accuracy, drift, and business-impact sections.
    """
    responses = approval.get("approval_responses") or "[]"
    try:
        approvers = [r.get("approver_email", "?") for r in json.loads(responses) if isinstance(r, dict)]
    except (TypeError, ValueError):
        approvers = []

    lines = [
        f"# Model Card — {uc_full_name} v{version}",
        "",
        f"*Assembled automatically at promotion on "
        f"{datetime.now(UTC).isoformat(timespec='seconds')} — do not edit by hand (§12.3).*",
        "",
        "## Governance",
        f"- Project: `{project_id}`",
        f"- Approval gate: `{approval.get('approval_gate', '')}` ({approval.get('approval_type', '')})",
        f"- Approved by: {', '.join(approvers) if approvers else '(recorded in approval record)'}",
        f"- Reviewed plan hash: `{approval.get('plan_hash', '')}`",
        "",
        "## Factors",
        f"- Fairness test result: {fairness_test_result or 'not recorded at promotion time'}",
        "",
        "## Metrics",
        "- Live accuracy: pending label feedback (§10) — populated once the",
        "  Feedback Join Service has joined predictions to ground truth.",
        "",
    ]
    card_path = bundle_dir / "docs" / "MODEL_CARD.md"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text("\n".join(lines))
    return card_path
