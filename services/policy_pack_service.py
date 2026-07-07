"""Policy Pack Service — declarative risk tiering + revalidation state (§20).

Packs are authored as YAML in policy_packs/ and reviewed via PR (§20.3) —
GitHub is the source of truth for governance rules; mlops.policy_packs is the
synced, queryable index (one row per pack tier). Which gates a tier requires
is data all the way down (§28): nothing here validates gate names against a
built-in list, so an org pack can add a `genai_eval` gate without code changes.

A project selects a risk tier and one or more packs at interview time (§20.1);
the Saga Engine takes the union of required gates across applied packs (§20.2)
and refuses promotion while a blocking revalidation flag is active (§20.5).
Revalidation itself is a re-run of the applicable approval gates against the
currently live version — re-review, not retraining (§20.5).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.state_service import StateService

PACKS_DIR = Path(__file__).parent.parent / "policy_packs"

# §20.5 severity ladder — comparisons always take the strictest (fail closed).
ON_DUE_ACTIONS = ("warn", "block_new_traffic", "block_all_traffic")
_SEVERITY = {action: rank for rank, action in enumerate(ON_DUE_ACTIONS)}

_SLUG_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class PolicyPackError(RuntimeError):
    """Raised when a pack is malformed or an assignment is invalid."""


@dataclass
class TierPolicy:
    """One (pack, tier) requirement row — the unit stored in mlops.policy_packs."""

    policy_pack_id: str
    risk_tier: str
    name: str = ""
    required_approval_gates: list[str] | None = None
    required_contract_fields: list[str] | None = None
    min_documentation_fields: list[str] | None = None
    audit_log_retention_days: int | None = None
    revalidation_frequency_days: int | None = None
    on_revalidation_due: str = "warn"
    allows_override: bool = True
    source_file: str = ""


def _slug_list(values: Any, context: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise PolicyPackError(f"{context}: expected a list of strings, got {values!r}")
    for v in values:
        if not _SLUG_RE.match(v):
            raise PolicyPackError(f"{context}: {v!r} is not a valid identifier")
    return values


def _sql_string_array(values: list[str]) -> str:
    """Array literal from already-slug-validated values (same pattern as the
    Reconciliation Service's alias literals — the regex is the injection guard)."""
    return "array(" + ", ".join(f"'{v}'" for v in values) + ")"


def load_packs(packs_dir: Path | None = None) -> list[TierPolicy]:
    """Parse and validate every pack YAML. Malformed packs raise — a governance
    rule that can't be parsed must never be silently skipped (fail closed)."""
    import yaml

    packs_dir = packs_dir or PACKS_DIR
    rows: list[TierPolicy] = []
    for path in sorted(packs_dir.glob("*.y*ml")):
        doc = yaml.safe_load(path.read_text())
        if not isinstance(doc, dict):
            raise PolicyPackError(f"{path.name}: not a mapping")
        pack_id = doc.get("policy_pack_id")
        if not isinstance(pack_id, str) or not _SLUG_RE.match(pack_id):
            raise PolicyPackError(f"{path.name}: missing or invalid policy_pack_id")
        tiers = doc.get("tiers")
        if not isinstance(tiers, dict) or not tiers:
            raise PolicyPackError(f"{path.name}: 'tiers' must be a non-empty mapping")

        for tier, spec in tiers.items():
            context = f"{path.name}: {pack_id}/{tier}"
            if not isinstance(tier, str) or not _SLUG_RE.match(tier):
                raise PolicyPackError(f"{context}: invalid tier name")
            if not isinstance(spec, dict):
                raise PolicyPackError(f"{context}: tier spec must be a mapping")
            freq = spec.get("revalidation_frequency_days")
            if freq is not None and (not isinstance(freq, int) or freq <= 0):
                raise PolicyPackError(f"{context}: revalidation_frequency_days must be a positive int or null")
            on_due = spec.get("on_revalidation_due", "warn")
            if on_due not in ON_DUE_ACTIONS:
                raise PolicyPackError(f"{context}: on_revalidation_due must be one of {ON_DUE_ACTIONS}")
            retention = spec.get("audit_log_retention_days")
            if retention is not None and (not isinstance(retention, int) or retention <= 0):
                raise PolicyPackError(f"{context}: audit_log_retention_days must be a positive int or null")
            rows.append(
                TierPolicy(
                    policy_pack_id=pack_id,
                    risk_tier=tier,
                    name=str(doc.get("name") or pack_id),
                    required_approval_gates=_slug_list(spec.get("required_approval_gates"), context),
                    required_contract_fields=_slug_list(spec.get("required_contract_fields"), context),
                    min_documentation_fields=_slug_list(spec.get("min_documentation_fields"), context),
                    audit_log_retention_days=retention,
                    revalidation_frequency_days=freq,
                    on_revalidation_due=on_due,
                    allows_override=bool(spec.get("allows_override", True)),
                    source_file=path.name,
                )
            )
    return rows


def strictest_action(actions: list[str]) -> str | None:
    known = [a for a in actions if a in _SEVERITY]
    if not known:
        return None
    return max(known, key=lambda a: _SEVERITY[a])


class PolicyPackService:
    def __init__(self, state: StateService | None = None, packs_dir: Path | None = None) -> None:
        self._state = state or StateService()
        self._packs_dir = packs_dir or PACKS_DIR

    def _tbl(self, name: str) -> str:
        return self._state._tbl(name)

    # ── §20.3: YAML → mlops.policy_packs index ──────────────────────────────

    def pack_options(self) -> dict[str, list[str]]:
        """pack_id → tiers, straight from the YAML source of truth (for the
        interview UI, which must offer org-authored tier definitions only, §20.1)."""
        options: dict[str, list[str]] = {}
        for row in load_packs(self._packs_dir):
            options.setdefault(row.policy_pack_id, []).append(row.risk_tier)
        return options

    def sync_packs(self) -> int:
        """Upsert every YAML pack tier into mlops.policy_packs. Idempotent."""
        rows = load_packs(self._packs_dir)
        for row in rows:
            self._state._exec(
                f"""MERGE INTO {self._tbl("policy_packs")} t
                    USING (SELECT :pack_id AS policy_pack_id, :tier AS risk_tier) s
                    ON t.policy_pack_id = s.policy_pack_id AND t.risk_tier = s.risk_tier
                    WHEN MATCHED THEN UPDATE SET
                      t.name = :name,
                      t.required_approval_gates = {_sql_string_array(row.required_approval_gates or [])},
                      t.required_contract_fields = {_sql_string_array(row.required_contract_fields or [])},
                      t.min_documentation_fields = {_sql_string_array(row.min_documentation_fields or [])},
                      t.audit_log_retention_days = :retention_days,
                      t.revalidation_frequency_days = :freq_days,
                      t.on_revalidation_due = :on_due,
                      t.allows_override = :allows_override,
                      t.source_file = :source_file,
                      t.synced_timestamp = current_timestamp()
                    WHEN NOT MATCHED THEN INSERT (
                      policy_pack_id, risk_tier, name, required_approval_gates,
                      required_contract_fields, min_documentation_fields,
                      audit_log_retention_days, revalidation_frequency_days,
                      on_revalidation_due, allows_override, source_file, synced_timestamp
                    ) VALUES (
                      :pack_id, :tier, :name,
                      {_sql_string_array(row.required_approval_gates or [])},
                      {_sql_string_array(row.required_contract_fields or [])},
                      {_sql_string_array(row.min_documentation_fields or [])},
                      :retention_days, :freq_days, :on_due, :allows_override,
                      :source_file, current_timestamp()
                    )""",
                {
                    "pack_id": row.policy_pack_id,
                    "tier": row.risk_tier,
                    "name": row.name,
                    "retention_days": row.audit_log_retention_days,
                    "freq_days": row.revalidation_frequency_days,
                    "on_due": row.on_revalidation_due,
                    "allows_override": row.allows_override,
                    "source_file": row.source_file,
                },
            )
        return len(rows)

    # ── §20.1/§29.3: tier assignment at interview time ──────────────────────

    def assign_to_project(
        self,
        project_id: str,
        *,
        risk_tier: str,
        pack_ids: list[str],
        justification: str,
        actor_email: str,
    ) -> None:
        """Record the project's tier + applied packs. The justification is
        mandatory — risk tier is a governance-consequential field and never
        gets a silent default (§29.3)."""
        if not justification.strip():
            raise PolicyPackError("Risk tier requires a one-line justification (§29.3).")
        if not pack_ids:
            raise PolicyPackError("At least one policy pack must be applied (§20.1).")
        options = self.pack_options()
        for pack_id in pack_ids:
            if pack_id not in options:
                raise PolicyPackError(f"Unknown policy pack {pack_id!r} — packs ship via PR (§20.3).")
            if risk_tier not in options[pack_id]:
                raise PolicyPackError(f"Pack {pack_id!r} does not define tier {risk_tier!r}.")

        self._state._exec(
            f"""UPDATE {self._tbl("projects")}
                SET risk_tier = :risk_tier,
                    risk_tier_justification = :justification,
                    regulatory_frameworks = {_sql_string_array(pack_ids)},
                    last_updated = current_timestamp(),
                    last_updated_by = :actor
                WHERE project_id = :project_id""",
            {
                "risk_tier": risk_tier,
                "justification": justification.strip(),
                "actor": actor_email,
                "project_id": project_id,
            },
        )
        self._state.log_audit(
            action_type="risk_tier_assigned",
            actor_email=actor_email,
            actor_role="interview",
            resource_type="project",
            resource_id=project_id,
            project_id=project_id,
            change_details={
                "risk_tier": risk_tier,
                "policy_packs": pack_ids,
                "justification": justification.strip(),
            },
        )

    # ── §20.2: effective policy for a project ───────────────────────────────

    def project_tier(self, project_id: str) -> tuple[str, list[str]]:
        """(risk_tier, applied pack ids) — ("", []) when never assigned."""
        rows = self._state._exec(
            f"""SELECT risk_tier, regulatory_frameworks
                FROM {self._tbl("projects")} WHERE project_id = :project_id""",
            {"project_id": project_id},
        )
        if not rows:
            return "", []
        tier = str(rows[0].get("risk_tier") or "")
        return tier, _as_string_list(rows[0].get("regulatory_frameworks"))

    def tier_rows_for_project(self, project_id: str) -> list[dict[str, Any]]:
        """The applied (pack, tier) requirement rows from the synced index."""
        tier, pack_ids = self.project_tier(project_id)
        if not tier or not pack_ids:
            return []
        for pack_id in pack_ids:
            if not _SLUG_RE.match(pack_id):
                raise PolicyPackError(f"Unsafe policy pack id on project row: {pack_id!r}")
        pack_literals = ", ".join(f"'{p}'" for p in pack_ids)
        return self._state._exec(
            f"""SELECT policy_pack_id, risk_tier, required_approval_gates,
                       revalidation_frequency_days, on_revalidation_due, allows_override
                FROM {self._tbl("policy_packs")}
                WHERE risk_tier = :tier AND policy_pack_id IN ({pack_literals})""",
            {"tier": tier},
        )

    def required_gates(self, project_id: str) -> set[str]:
        """Union of required gates across the project's applied packs (§20.2)."""
        gates: set[str] = set()
        for row in self.tier_rows_for_project(project_id):
            gates.update(_as_string_list(row.get("required_approval_gates")))
        return gates

    def unsatisfied_gates(self, project_id: str) -> set[str]:
        """Required gates with no approved gate record for this project."""
        required = self.required_gates(project_id)
        if not required:
            return set()
        rows = self._state._exec(
            f"""SELECT DISTINCT a.approval_gate
                FROM {self._tbl("approvals")} a
                JOIN {self._tbl("models")} m ON a.model_id = m.model_id
                WHERE m.project_id = :project_id AND a.status = 'approved'""",
            {"project_id": project_id},
        )
        approved = {str(r.get("approval_gate") or "") for r in rows}
        return required - approved

    # ── §20.5: revalidation flags ────────────────────────────────────────────

    def revalidation_block(self, project_id: str) -> str | None:
        """Strictest active on_due_action for the project, or None. The saga
        aborts promotion on block_new_traffic/block_all_traffic."""
        rows = self._state._exec(
            f"""SELECT on_due_action FROM {self._tbl("revalidation_flags")}
                WHERE project_id = :project_id AND status IN ('due', 'in_revalidation')""",
            {"project_id": project_id},
        )
        return strictest_action([str(r.get("on_due_action") or "") for r in rows])

    def start_revalidation(self, project_id: str, uc_full_name: str, *, requested_by: str) -> list[str]:
        """Open the applicable gate re-runs against the live version — the saga
        re-entered at step 1; re-review, not retraining (§20.5)."""
        gates = sorted(self.required_gates(project_id))
        if not gates:
            raise PolicyPackError(f"Project {project_id!r} has no policy-pack gates to re-run.")
        model_rows = self._state._exec(
            f"""SELECT DISTINCT m.model_id
                FROM {self._tbl("models")} m
                JOIN {self._tbl("model_versions")} v ON v.model_id = m.model_id
                WHERE m.project_id = :project_id AND v.uc_full_name = :uc_full_name""",
            {"project_id": project_id, "uc_full_name": uc_full_name},
        )
        if not model_rows:
            raise PolicyPackError(f"No tracked model for {uc_full_name!r} on project {project_id!r}.")
        model_id = str(model_rows[0]["model_id"])

        approval_ids: list[str] = []
        for gate in gates:
            approval_id = str(uuid.uuid4())
            self._state._exec(
                f"""INSERT INTO {self._tbl("approvals")}
                    (approval_id, model_id, approval_type, approval_gate,
                     requested_timestamp, requested_by, required_count,
                     approval_responses, approved_count, rejected_count,
                     status, created_timestamp)
                    VALUES
                    (:approval_id, :model_id, :gate, :gate,
                     current_timestamp(), :requested_by, 1,
                     :initial_responses, 0, 0,
                     'pending', current_timestamp())""",
                {
                    "approval_id": approval_id,
                    "model_id": model_id,
                    "gate": gate,
                    "requested_by": requested_by,
                    "initial_responses": json.dumps(
                        [{"requested_by": requested_by, "reason": "revalidation re-run (§20.5)"}]
                    ),
                },
            )
            approval_ids.append(approval_id)

        self._state._exec(
            f"""UPDATE {self._tbl("revalidation_flags")}
                SET status = 'in_revalidation',
                    revalidation_approval_ids = {_sql_string_array(approval_ids)},
                    last_checked_timestamp = current_timestamp()
                WHERE project_id = :project_id AND uc_full_name = :uc_full_name""",
            {"project_id": project_id, "uc_full_name": uc_full_name},
        )
        self._state.log_audit(
            action_type="revalidation_started",
            actor_email=requested_by,
            actor_role="mlops",
            resource_type="model",
            resource_id=uc_full_name,
            project_id=project_id,
            change_details={"gates": gates, "approval_ids": approval_ids},
        )
        return approval_ids

    def check_revalidation_complete(self, project_id: str, uc_full_name: str) -> bool:
        """Clear the flag once every re-run gate is approved. A rejected or
        still-pending gate keeps the flag active (fail closed)."""
        rows = self._state._exec(
            f"""SELECT revalidation_approval_ids FROM {self._tbl("revalidation_flags")}
                WHERE project_id = :project_id AND uc_full_name = :uc_full_name
                  AND status = 'in_revalidation'""",
            {"project_id": project_id, "uc_full_name": uc_full_name},
        )
        if not rows:
            return False
        approval_ids = _as_string_list(rows[0].get("revalidation_approval_ids"))
        if not approval_ids:
            return False
        for approval_id in approval_ids:
            approval = self._state.get_approval(approval_id)
            if approval is None or str(approval.get("status")) != "approved":
                return False

        self._state._exec(
            f"""UPDATE {self._tbl("revalidation_flags")}
                SET status = 'cleared',
                    cleared_timestamp = current_timestamp(),
                    last_checked_timestamp = current_timestamp()
                WHERE project_id = :project_id AND uc_full_name = :uc_full_name""",
            {"project_id": project_id, "uc_full_name": uc_full_name},
        )
        self._state.log_audit(
            action_type="revalidation_cleared",
            actor_email="system",
            actor_role="policy_pack_service",
            resource_type="model",
            resource_id=uc_full_name,
            project_id=project_id,
            change_details={"approval_ids": approval_ids},
        )
        return True


def _as_string_list(raw: Any) -> list[str]:
    """Array columns come back as lists from fakes and JSON strings from the
    statement-execution API — accept both."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(v) for v in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
    return []
