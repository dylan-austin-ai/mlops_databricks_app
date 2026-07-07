"""Tests for policy_pack_service — YAML validation, sync, gate union, §20.5 flags.

Gates are data (§28): nothing here asserts against a built-in gate list, only
against what the pack YAML declares.
"""

from __future__ import annotations

import json

import pytest

from services.policy_pack_service import (
    PACKS_DIR,
    PolicyPackError,
    PolicyPackService,
    load_packs,
    strictest_action,
)
from tests.test_approval_service import FakeState


class PolicyFakeState(FakeState):
    """FakeState with prefix-routed SELECT results (same pattern as ReconFakeState)."""

    def __init__(self):
        super().__init__()
        self.rows_by_prefix: dict[str, list[dict]] = {}

    def _exec(self, sql: str, params: dict | None = None):
        self.execs.append((sql, params))
        stripped = sql.strip()
        for prefix, rows in self.rows_by_prefix.items():
            if stripped.startswith(prefix):
                return rows
        if stripped.upper().startswith("MERGE"):
            return [{"num_affected_rows": 1}]
        return []


@pytest.fixture
def state() -> PolicyFakeState:
    return PolicyFakeState()


@pytest.fixture
def svc(state) -> PolicyPackService:
    return PolicyPackService(state=state)


# ── §20.3: YAML loading ───────────────────────────────────────────────────────


class TestLoadPacks:
    def test_shipped_default_loads(self):
        rows = load_packs(PACKS_DIR)
        by_tier = {r.risk_tier: r for r in rows if r.policy_pack_id == "generic_tiering_v1"}
        assert set(by_tier) == {"tier_1", "tier_2", "tier_3"}
        assert by_tier["tier_1"].revalidation_frequency_days is None
        assert by_tier["tier_2"].revalidation_frequency_days == 365
        assert by_tier["tier_3"].required_approval_gates == [
            "code_review",
            "legal_review",
            "business_approval",
            "security_review",
        ]
        assert by_tier["tier_3"].allows_override is False
        assert by_tier["tier_3"].on_revalidation_due == "block_new_traffic"

    def test_org_gate_names_are_not_restricted_to_a_builtin_list(self, tmp_path):
        # §28: a genai_eval gate must work without code changes
        (tmp_path / "org.yaml").write_text(
            "policy_pack_id: org_pack\n"
            "tiers:\n"
            "  high_risk:\n"
            "    required_approval_gates: [genai_eval, conformity_assessment]\n"
            "    revalidation_frequency_days: 90\n"
            "    on_revalidation_due: block_all_traffic\n"
        )
        rows = load_packs(tmp_path)
        assert rows[0].required_approval_gates == ["genai_eval", "conformity_assessment"]

    def test_invalid_on_due_action_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("policy_pack_id: bad\ntiers:\n  t1: {on_revalidation_due: explode}\n")
        with pytest.raises(PolicyPackError, match="on_revalidation_due"):
            load_packs(tmp_path)

    def test_unsafe_gate_name_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text(
            'policy_pack_id: bad\ntiers:\n  t1: {required_approval_gates: ["x\'); DROP--"]}\n'
        )
        with pytest.raises(PolicyPackError, match="not a valid identifier"):
            load_packs(tmp_path)

    def test_missing_pack_id_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("tiers:\n  t1: {}\n")
        with pytest.raises(PolicyPackError, match="policy_pack_id"):
            load_packs(tmp_path)

    def test_negative_frequency_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("policy_pack_id: bad\ntiers:\n  t1: {revalidation_frequency_days: -5}\n")
        with pytest.raises(PolicyPackError, match="revalidation_frequency_days"):
            load_packs(tmp_path)


def test_strictest_action_ladder():
    assert strictest_action(["warn", "block_all_traffic", "block_new_traffic"]) == "block_all_traffic"
    assert strictest_action(["warn", "warn"]) == "warn"
    assert strictest_action(["nonsense"]) is None
    assert strictest_action([]) is None


# ── sync ─────────────────────────────────────────────────────────────────────


class TestSync:
    def test_sync_upserts_one_row_per_tier(self, svc, state):
        n = svc.sync_packs()
        merges = [(s, p) for s, p in state.execs if s.strip().startswith("MERGE")]
        assert n == 3 and len(merges) == 3
        tier3 = next(p for _, p in merges if p["tier"] == "tier_3")
        assert tier3["on_due"] == "block_new_traffic"
        assert tier3["allows_override"] is False
        tier3_sql = next(s for s, p in merges if p["tier"] == "tier_3")
        assert "array('code_review', 'legal_review', 'business_approval', 'security_review')" in tier3_sql


# ── §20.1/§29.3: assignment ──────────────────────────────────────────────────


class TestAssign:
    def test_assign_records_tier_and_audits(self, svc, state):
        svc.assign_to_project(
            "p1",
            risk_tier="tier_2",
            pack_ids=["generic_tiering_v1"],
            justification="Moderate materiality.",
            actor_email="ds@co.com",
        )
        update_sql, update_params = next((s, p) for s, p in state.execs if s.strip().startswith("UPDATE"))
        assert "array('generic_tiering_v1')" in update_sql
        assert update_params["risk_tier"] == "tier_2"
        assert state.audits and state.audits[-1]["action_type"] == "risk_tier_assigned"

    def test_empty_justification_rejected(self, svc):
        with pytest.raises(PolicyPackError, match="justification"):
            svc.assign_to_project(
                "p1",
                risk_tier="tier_2",
                pack_ids=["generic_tiering_v1"],
                justification="   ",
                actor_email="ds@co.com",
            )

    def test_unknown_pack_rejected(self, svc):
        with pytest.raises(PolicyPackError, match="Unknown policy pack"):
            svc.assign_to_project(
                "p1",
                risk_tier="tier_2",
                pack_ids=["not_installed"],
                justification="x",
                actor_email="ds@co.com",
            )

    def test_tier_not_in_pack_rejected(self, svc):
        with pytest.raises(PolicyPackError, match="does not define tier"):
            svc.assign_to_project(
                "p1",
                risk_tier="tier_99",
                pack_ids=["generic_tiering_v1"],
                justification="x",
                actor_email="ds@co.com",
            )

    def test_no_packs_rejected(self, svc):
        with pytest.raises(PolicyPackError, match="At least one policy pack"):
            svc.assign_to_project(
                "p1",
                risk_tier="tier_2",
                pack_ids=[],
                justification="x",
                actor_email="ds@co.com",
            )


# ── §20.2: effective policy ──────────────────────────────────────────────────


def _project_row(state, tier="tier_3", packs='["generic_tiering_v1", "org_pack"]'):
    # regulatory_frameworks arrives as a JSON string from the statement API
    state.rows_by_prefix["SELECT risk_tier, regulatory_frameworks"] = [
        {"risk_tier": tier, "regulatory_frameworks": packs}
    ]


class TestEffectivePolicy:
    def test_required_gates_is_union_across_packs(self, svc, state):
        _project_row(state)
        state.rows_by_prefix["SELECT policy_pack_id"] = [
            {"required_approval_gates": json.dumps(["code_review", "legal_review"])},
            {"required_approval_gates": ["legal_review", "genai_eval"]},  # list form too
        ]
        assert svc.required_gates("p1") == {"code_review", "legal_review", "genai_eval"}

    def test_unassigned_project_requires_nothing(self, svc, state):
        state.rows_by_prefix["SELECT risk_tier, regulatory_frameworks"] = [
            {"risk_tier": None, "regulatory_frameworks": None}
        ]
        assert svc.required_gates("p1") == set()
        assert svc.unsatisfied_gates("p1") == set()

    def test_unsatisfied_is_required_minus_approved(self, svc, state):
        _project_row(state)
        state.rows_by_prefix["SELECT policy_pack_id"] = [
            {"required_approval_gates": ["code_review", "legal_review", "security_review"]}
        ]
        state.rows_by_prefix["SELECT DISTINCT a.approval_gate"] = [
            {"approval_gate": "code_review"},
            {"approval_gate": "legal_review"},
        ]
        assert svc.unsatisfied_gates("p1") == {"security_review"}

    def test_unsafe_pack_id_on_project_row_fails_closed(self, svc, state):
        _project_row(state, packs='["ok_pack", "bad\'); DROP--"]')
        with pytest.raises(PolicyPackError, match="Unsafe policy pack id"):
            svc.tier_rows_for_project("p1")


# ── §20.5: revalidation flags ────────────────────────────────────────────────


class TestRevalidationFlags:
    def test_block_is_strictest_active_action(self, svc, state):
        state.rows_by_prefix["SELECT on_due_action"] = [
            {"on_due_action": "warn"},
            {"on_due_action": "block_new_traffic"},
        ]
        assert svc.revalidation_block("p1") == "block_new_traffic"

    def test_no_flags_no_block(self, svc, state):
        assert svc.revalidation_block("p1") is None

    def test_start_revalidation_opens_one_gate_rerun_per_required_gate(self, svc, state):
        _project_row(state, tier="tier_2", packs='["generic_tiering_v1"]')
        state.rows_by_prefix["SELECT policy_pack_id"] = [{"required_approval_gates": ["code_review", "legal_review"]}]
        state.rows_by_prefix["SELECT DISTINCT m.model_id"] = [{"model_id": "m1"}]

        approval_ids = svc.start_revalidation("p1", "cat.ml.churn", requested_by="mlops@co.com")

        inserts = [(s, p) for s, p in state.execs if s.strip().startswith("INSERT")]
        assert len(approval_ids) == 2 and len(inserts) == 2
        assert {p["gate"] for _, p in inserts} == {"code_review", "legal_review"}
        assert all(p["model_id"] == "m1" for _, p in inserts)
        flag_update = next(s for s, _ in state.execs if "in_revalidation" in s)
        assert all(a in flag_update for a in approval_ids)
        assert state.audits[-1]["action_type"] == "revalidation_started"

    def test_start_without_gates_refuses(self, svc, state):
        _project_row(state, tier=None, packs=None)
        with pytest.raises(PolicyPackError, match="no policy-pack gates"):
            svc.start_revalidation("p1", "cat.ml.churn", requested_by="mlops@co.com")

    def test_complete_requires_every_gate_approved(self, svc, state):
        state.rows_by_prefix["SELECT revalidation_approval_ids"] = [{"revalidation_approval_ids": '["a1", "a2"]'}]
        state.approvals["a1"] = {"status": "approved"}
        state.approvals["a2"] = {"status": "pending"}
        assert svc.check_revalidation_complete("p1", "cat.ml.churn") is False

        state.approvals["a2"] = {"status": "approved"}
        assert svc.check_revalidation_complete("p1", "cat.ml.churn") is True
        cleared = [s for s, _ in state.execs if "'cleared'" in s]
        assert cleared and state.audits[-1]["action_type"] == "revalidation_cleared"

    def test_complete_with_no_active_flag_is_false(self, svc, state):
        assert svc.check_revalidation_complete("p1", "cat.ml.churn") is False
