"""Tests for approval_service — MERGE write-path orchestration and revocation guards.

The MERGE's atomicity itself is Delta's guarantee and is exercised live; these
tests pin down what we send (guard conditions, parameters, marker format) and
how outcomes are interpreted (recorded vs. clearly-explained refusals).
"""

from __future__ import annotations

import json

import pytest

from services.approval_service import ApprovalService, ApprovalServiceError


class FakeState:
    def __init__(self):
        self.execs: list[tuple[str, dict | None]] = []
        self.approvals: dict[str, dict] = {}
        self.audits: list[dict] = []
        self.merge_affected = 1
        self.created_requests: list[dict] = []

    def _tbl(self, name: str) -> str:
        return name

    def _exec(self, sql: str, params: dict | None = None):
        self.execs.append((sql, params))
        if sql.strip().upper().startswith("MERGE"):
            return [{"num_affected_rows": self.merge_affected}]
        return []

    def get_approval(self, approval_id: str):
        return self.approvals.get(approval_id)

    def log_audit(self, **kwargs):
        self.audits.append(kwargs)

    def create_approval_request(self, model_id, approval_type, approval_gate, requested_by, required_count=1):
        approval_id = f"generated-{len(self.created_requests)}"
        self.created_requests.append(
            {
                "approval_id": approval_id,
                "model_id": model_id,
                "approval_type": approval_type,
                "approval_gate": approval_gate,
                "requested_by": requested_by,
                "required_count": required_count,
            }
        )
        return approval_id


@pytest.fixture
def state() -> FakeState:
    return FakeState()


@pytest.fixture
def svc(state) -> ApprovalService:
    return ApprovalService(state=state)


def _approval(**overrides) -> dict:
    base = {
        "approval_id": "ap1",
        "model_id": "m1",
        "approval_type": "legal_review",
        "approval_gate": "legal_review",
        "status": "pending",
        "approved_count": 0,
        "rejected_count": 0,
        "required_count": 2,
        "approval_responses": "[]",
        "requested_by": "requester@co.com",
    }
    base.update(overrides)
    return base


class TestSubmitDecision:
    def test_invalid_decision_rejected(self, svc):
        with pytest.raises(ApprovalServiceError, match="Invalid decision"):
            svc.submit_decision("ap1", "maybe", "a@co.com")

    def test_merge_sql_carries_atomicity_guards(self, svc, state):
        state.approvals["ap1"] = _approval(approved_count=1, status="pending")
        svc.submit_decision("ap1", "approve", "a@co.com")

        merge_sql, params = state.execs[0]
        # §15.1 guards evaluated SQL-side, not in Python
        assert "t.status = 'pending'" in merge_sql
        assert "coalesce(t.approved_count, 0) < coalesce(t.required_count, 1)" in merge_sql
        assert "NOT (coalesce(nullif(t.approval_responses, ''), '[]') LIKE :email_marker)" in merge_sql
        # Values travel as named parameters, never interpolated
        assert params["approval_id"] == "ap1"
        assert params["decision"] == "approve"
        assert '"approver_email": "a@co.com"' in params["email_marker"]
        entry = json.loads(params["response_entry"])
        assert entry["approval_decision"] == "approve"

    def test_recorded_outcome_and_audit(self, svc, state):
        state.approvals["ap1"] = _approval(approved_count=1)
        outcome = svc.submit_decision("ap1", "approve", "a@co.com", comment="lgtm")

        assert outcome.recorded is True
        assert state.audits[0]["action_type"] == "approval_approve"
        assert state.audits[0]["approval_id"] == "ap1"

    def test_already_voted_reason(self, svc, state):
        state.merge_affected = 0
        responses = json.dumps([{"approver_email": "a@co.com", "approval_decision": "approve"}])
        state.approvals["ap1"] = _approval(approved_count=1, approval_responses=responses)

        outcome = svc.submit_decision("ap1", "approve", "a@co.com")

        assert outcome.recorded is False
        assert "already submitted" in outcome.reason
        assert state.audits == []  # nothing recorded, nothing audited

    def test_gate_already_decided_reason(self, svc, state):
        state.merge_affected = 0
        state.approvals["ap1"] = _approval(status="approved", approved_count=2)

        outcome = svc.submit_decision("ap1", "approve", "b@co.com")

        assert outcome.recorded is False
        assert "already approved" in outcome.reason.lower()

    def test_gate_satisfied_reason(self, svc, state):
        state.merge_affected = 0
        state.approvals["ap1"] = _approval(status="pending", approved_count=2, required_count=2)

        outcome = svc.submit_decision("ap1", "approve", "b@co.com")

        assert outcome.recorded is False
        assert "already satisfied" in outcome.reason.lower()

    def test_missing_approval_raises(self, svc, state):
        state.merge_affected = 0
        with pytest.raises(ApprovalServiceError, match="not found"):
            svc.submit_decision("ghost", "approve", "a@co.com")


class TestRevocation:
    def test_request_requires_approved_original(self, svc, state):
        state.approvals["ap1"] = _approval(status="pending")
        with pytest.raises(ApprovalServiceError, match="Only approved"):
            svc.request_revocation("ap1", "bad approval", "whistle@co.com")

    def test_revocation_of_revocation_refused(self, svc, state):
        state.approvals["rev1"] = _approval(approval_id="rev1", approval_type="revocation", status="approved")
        with pytest.raises(ApprovalServiceError, match="cannot itself be revoked"):
            svc.request_revocation("rev1", "x", "a@co.com")

    def test_request_inserts_append_only_record(self, svc, state):
        state.approvals["ap1"] = _approval(status="approved")
        outcome = svc.request_revocation("ap1", "fairness data was stale", "whistle@co.com")

        assert outcome.recorded is True
        assert outcome.revocation_status == "pending"
        insert_sql, params = state.execs[-1]
        assert "INSERT INTO approvals" in insert_sql
        assert params["original_id"] == "ap1"
        assert params["requested_by"] == "whistle@co.com"
        # Original approval untouched — no UPDATE/DELETE against it
        assert not any("UPDATE" in s.upper() and "ap1" in str(p) for s, p in state.execs[:-1])
        assert state.audits[0]["action_type"] == "revocation_requested"

    def test_requester_cannot_approve_own_revocation(self, svc, state):
        state.approvals["ap1"] = _approval(status="approved")
        state.approvals["rev1"] = _approval(
            approval_id="rev1",
            approval_type="revocation",
            revokes_approval_id="ap1",
            requested_by="whistle@co.com",
        )
        with pytest.raises(ApprovalServiceError, match="requester cannot approve"):
            svc.decide_revocation("rev1", "approve", "whistle@co.com")

    def test_original_approver_cannot_decide_revocation(self, svc, state):
        responses = json.dumps([{"approver_email": "orig@co.com", "approval_decision": "approve"}])
        state.approvals["ap1"] = _approval(status="approved", approval_responses=responses)
        state.approvals["rev1"] = _approval(
            approval_id="rev1",
            approval_type="revocation",
            revokes_approval_id="ap1",
            requested_by="whistle@co.com",
        )
        with pytest.raises(ApprovalServiceError, match="Segregation of duties"):
            svc.decide_revocation("rev1", "approve", "orig@co.com")

    def test_independent_reviewer_can_decide(self, svc, state):
        state.approvals["ap1"] = _approval(status="approved")
        state.approvals["rev1"] = _approval(
            approval_id="rev1",
            approval_type="revocation",
            revokes_approval_id="ap1",
            requested_by="whistle@co.com",
            required_count=1,
        )
        outcome = svc.decide_revocation("rev1", "approve", "independent@co.com")

        assert outcome.recorded is True
        assert outcome.original_approval_id == "ap1"


class NotifyFakeState(FakeState):
    """FakeState with a canned interview_responses row for the approver
    contact-email lookup (_notify_approver's SELECT)."""

    def __init__(self, contact_row: dict | None = None):
        super().__init__()
        self._contact_row = contact_row

    def _exec(self, sql, params=None):
        self.execs.append((sql, params))
        if sql.strip().startswith("SELECT pc.interview_responses"):
            return [self._contact_row] if self._contact_row is not None else []
        if sql.strip().upper().startswith("MERGE"):
            return [{"num_affected_rows": self.merge_affected}]
        return []


class FakeNotifications:
    def __init__(self):
        self.sent: list[tuple] = []

    def send(self, destination_config, subject, message):
        self.sent.append((destination_config, subject, message))
        return None


class TestRequestApproval:
    """IMG_1412 gap: a new gate never told anyone it existed."""

    def test_creates_gate_and_notifies_configured_contact(self):
        state = NotifyFakeState({"interview_responses": json.dumps({"legal_contact_email": "legal@co.com"})})
        notifications = FakeNotifications()
        svc = ApprovalService(state=state, notifications=notifications)

        approval_id = svc.request_approval("m1", "legal_review", "legal_review", "ds@co.com")

        assert approval_id == "generated-0"
        assert state.created_requests[0]["model_id"] == "m1"
        assert len(notifications.sent) == 1
        dest, subject, message = notifications.sent[0]
        assert dest == {"destination": "email", "email_addresses": ["legal@co.com"]}
        assert "Legal Review" in subject
        assert approval_id in message

    def test_gate_with_no_contact_mapping_skips_notification(self):
        state = NotifyFakeState()
        notifications = FakeNotifications()
        svc = ApprovalService(state=state, notifications=notifications)

        svc.request_approval("m1", "code_review", "code_review", "ds@co.com")

        assert not notifications.sent

    def test_no_contact_email_on_file_skips_notification(self):
        state = NotifyFakeState({"interview_responses": json.dumps({})})
        notifications = FakeNotifications()
        svc = ApprovalService(state=state, notifications=notifications)

        svc.request_approval("m1", "security_scan", "security_scan", "ds@co.com")

        assert not notifications.sent

    def test_notification_failure_never_blocks_gate_creation(self):
        class ExplodingNotifications:
            def send(self, *a, **k):
                raise RuntimeError("smtp down")

        state = NotifyFakeState({"interview_responses": json.dumps({"legal_contact_email": "legal@co.com"})})
        svc = ApprovalService(state=state, notifications=ExplodingNotifications())

        approval_id = svc.request_approval("m1", "legal_review", "legal_review", "ds@co.com")

        assert approval_id == "generated-0"  # gate still created despite notification blowing up
