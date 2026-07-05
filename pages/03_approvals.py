"""Approval Center — pending and completed approval requests."""

from __future__ import annotations

import json

import streamlit as st

from components.theme import apply_theme, page_header, pill, render_sidebar
from config import get_config

st.set_page_config(page_title="Approvals — MLOps", page_icon="✅", layout="wide")
apply_theme()

_GATE_LABELS = {
    "code_review": "Code Review",
    "fairness_review": "Fairness / Legal Review",
    "legal_review": "Legal Review",
    "business_approval": "Business Approval",
    "security_scan": "Security Scan",
    "end_to_end_test": "End-to-End Test",
}


def _approval_card(approval: dict, svc: object) -> None:
    approval_id = approval["approval_id"]
    gate = approval.get("approval_gate", approval.get("approval_type", "unknown"))
    gate_label = _GATE_LABELS.get(gate, gate.replace("_", " ").title())
    project_name = approval.get("project_name", "unknown project")
    approved = int(approval.get("approved_count") or 0)
    required = int(approval.get("required_count") or 1)
    requested_by = approval.get("requested_by", "—")
    requested_at = str(approval.get("requested_timestamp", ""))[:16]

    try:
        responses = json.loads(approval.get("approval_responses") or "[]")
    except Exception:
        responses = []

    # Progress pips
    pip_html = "".join(
        f'<span style="width:28px;height:6px;border-radius:999px;'
        f"background:{'#10b981;box-shadow:0 0 14px rgba(16,185,129,0.45)' if i < approved else '#2f4368'}"
        f'"></span>'
        for i in range(required)
    )

    # Existing approver responses
    chain_html = ""
    for r in responses:
        dec = r.get("approval_decision", "")
        dec_color = "#5eead4" if dec == "approve" else "#fca5a5"
        initials = "".join(w[0].upper() for w in r.get("approved_by", "?").split("@")[0].split(".")[:2])
        chain_html += f"""
<div style="display:flex;align-items:center;gap:12px;padding:10px;
            border-radius:5px;background:#070a12;border:1px solid rgba(16,185,129,0.25);">
  <span style="width:28px;height:28px;flex:none;border-radius:50%;display:grid;
               place-content:center;font-size:11px;font-weight:600;
               font-family:'JetBrains Mono',monospace;
               background:rgba(16,185,129,0.15);color:#5eead4;
               border:1px solid rgba(16,185,129,0.4)">{initials}</span>
  <span style="display:flex;flex-direction:column;gap:2px;line-height:1.2">
    <span style="font-size:13px;color:#e2e8f0">{r.get("approved_by", "—")}</span>
    <span style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;
                 color:{dec_color}">{dec}</span>
  </span>
  <span style="margin-left:auto;font-size:11px;color:#64748b;
               font-family:'JetBrains Mono',monospace">{r.get("comment", "")[:50]}</span>
</div>"""

    # Waiting slot
    chain_html += f"""
<div style="display:flex;align-items:center;gap:12px;padding:10px;
            border-radius:5px;background:#070a12;border:1px dashed #1a2740;opacity:.7">
  <span style="width:28px;height:28px;flex:none;border-radius:50%;display:grid;
               place-content:center;font-size:11px;font-weight:600;
               background:#111827;color:#46546e;border:1px solid #2f4368">··</span>
  <span style="display:flex;flex-direction:column;gap:2px;line-height:1.2">
    <span style="font-size:13px;color:#e2e8f0">You</span>
    <span style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;
                 color:#46546e">awaiting decision</span>
  </span>
  <span style="margin-left:auto;font-size:11px;color:#64748b;
               font-family:'JetBrains Mono',monospace">required to promote</span>
</div>"""

    card_border = "border:1px solid #1a2740;position:relative;overflow:hidden;"
    top_glow = (
        "content:'';position:absolute;inset:0 0 auto 0;height:2px;"
        "background:linear-gradient(90deg,transparent,#00d4ff,transparent);"
        "box-shadow:0 0 12px #00d4ff;opacity:.8;"
    )

    st.markdown(
        f"""
<div style="background:#111827;{card_border}border-radius:8px;padding:20px;
            display:flex;flex-direction:column;gap:16px;">
  <span style="display:block;{top_glow}"></span>

  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
    <div style="display:flex;flex-direction:column;gap:6px">
      <span style="display:inline-flex;align-items:center;gap:6px;height:24px;
                   padding:0 10px;border-radius:5px;font-size:12px;font-weight:600;
                   font-family:'JetBrains Mono',monospace;color:#a9b6cc;
                   background:#161f33;border:1px solid #243456">⛬ {gate_label}</span>
      <span style="font-size:17px;font-weight:600;color:#f4f8ff">{project_name}</span>
      <span style="font-size:12px;color:#64748b;font-family:'JetBrains Mono',monospace">
        requested by {requested_by} · {requested_at}</span>
    </div>
    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:8px">
      {pill("pending")}
      <div style="display:flex;align-items:center;gap:10px">
        <div style="display:flex;gap:4px">{pip_html}</div>
        <span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#a9b6cc">
          {approved} / {required} approvals</span>
      </div>
    </div>
  </div>

  <div style="display:flex;flex-direction:column;gap:6px">
    <span style="font-size:11px;font-weight:600;text-transform:uppercase;
                 letter-spacing:0.12em;color:#64748b">Approval chain</span>
    <div style="display:flex;flex-direction:column;gap:4px">{chain_html}</div>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    col_email, col_comment = st.columns(2)
    with col_email:
        approver_email = st.text_input("Your email", key=f"approver_{approval_id}", placeholder="you@company.com")
    with col_comment:
        comment = st.text_area("Comment (required)", key=f"comment_{approval_id}", height=80)

    btn_cols = st.columns(3)
    with btn_cols[0]:
        if st.button("✓ Approve", key=f"approve_{approval_id}", use_container_width=True, type="primary"):
            _submit(svc, approval_id, "approve", approver_email, comment)
    with btn_cols[1]:
        if st.button("⟲ Changes", key=f"changes_{approval_id}", use_container_width=True):
            _submit(svc, approval_id, "request_changes", approver_email, comment)
    with btn_cols[2]:
        if st.button("✕ Reject", key=f"reject_{approval_id}", use_container_width=True):
            _submit(svc, approval_id, "reject", approver_email, comment)

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)


def _submit(svc: object, approval_id: str, decision: str, email: str, comment: str) -> None:
    if not email or "@" not in email:
        st.error("Enter a valid email address.", icon="❌")
        return
    if not comment.strip():
        st.error("A comment is required for all decisions.", icon="❌")
        return
    try:
        svc.submit_approval_decision(approval_id, decision, email, comment)
        label = {"approve": "approved", "reject": "rejected", "request_changes": "flagged for changes"}[decision]
        st.success(f"Decision recorded: {label}.", icon="✅")
        st.rerun()
    except Exception as exc:
        st.error(f"Failed: {exc}", icon="❌")


def _history_table(history: list[dict]) -> None:
    if not history:
        st.caption("No completed approvals yet.")
        return
    rows = []
    for a in history:
        gate = a.get("approval_gate", a.get("approval_type", "—"))
        status = a.get("status", "—")
        rows.append(
            {
                "Project": a.get("project_name", "—"),
                "Gate": _GATE_LABELS.get(gate, gate),
                "Status": status.replace("_", " ").title(),
                "Approvals": f"{a.get('approved_count', 0)}/{a.get('required_count', 1)}",
                "Completed": str(a.get("completed_timestamp", ""))[:16],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _test_request_form(svc: object, projects: list[dict]) -> None:
    with st.expander("Create test approval request", expanded=False):
        st.caption("Generate a real approval request without a live training pipeline.")
        if not projects:
            st.warning("No projects found.")
            return
        proj_names = [p["project_name"] for p in projects]
        selected_proj = st.selectbox("Project", proj_names, key="test_proj")
        gate_type = st.selectbox("Gate type", list(_GATE_LABELS.keys()), key="test_gate")
        requester = st.text_input("Requested by", key="test_requester", placeholder="ds@company.com")
        required_count = st.number_input("Required approvals", min_value=1, max_value=5, value=1, key="test_count")
        if st.button("Create test request", type="primary"):
            proj = next(p for p in projects if p["project_name"] == selected_proj)
            try:
                model_id = _ensure_placeholder_model(svc, proj)
                svc.create_approval_request(
                    model_id=model_id,
                    approval_type=gate_type,
                    approval_gate=gate_type,
                    requested_by=requester or "test@platform",
                    required_count=int(required_count),
                )
                st.success("Test approval request created.", icon="✅")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed: {exc}", icon="❌")


def _ensure_placeholder_model(svc: object, project: dict) -> str:
    rows = svc._exec(f"SELECT model_id FROM {svc._tbl('models')} WHERE project_id = '{project['project_id']}' LIMIT 1")
    if rows:
        return rows[0]["model_id"]
    import uuid
    from datetime import datetime, timezone

    model_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    svc._exec(f"""
    INSERT INTO {svc._tbl("models")}
      (model_id, project_id, model_name, status, is_production,
       owner_email, team_name, created_timestamp, created_by, last_updated, last_updated_by)
    VALUES
      ('{model_id}', '{project["project_id"]}', '{project["project_name"]}',
       'development', false,
       '{project.get("owner_email", "")}', '{project.get("team_name", "")}',
       '{now}', '{project.get("owner_email", "")}', '{now}', '{project.get("owner_email", "")}')
    """)
    return model_id


def _main() -> None:
    render_sidebar()

    st.markdown(
        page_header("Promotion Gates", "Approval Center", "Review and decide on model-promotion requests."),
        unsafe_allow_html=True,
    )

    cfg = get_config()
    if not cfg.is_connected:
        st.warning("Connect to Databricks to view approvals.", icon="⚠️")
        return

    try:
        from services.state_service import StateService

        svc = StateService()
        projects = svc.list_projects()
        pending = svc.list_pending_approvals()
        history = svc.list_approval_history(limit=25)
    except Exception as exc:
        st.error(f"Failed to load approvals: {exc}")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Pending", len(pending))
    with col2:
        st.metric("Approved (recent)", sum(1 for a in history if a.get("status") == "approved"))
    with col3:
        st.metric("Rejected (recent)", sum(1 for a in history if a.get("status") == "rejected"))

    st.markdown("---")
    tab_pending, tab_history, tab_test = st.tabs(["Pending", "History", "Test"])

    with tab_pending:
        if not pending:
            st.markdown(
                """
<div style="display:flex;flex-direction:column;align-items:center;gap:12px;
            padding:64px 24px;text-align:center;
            border:1px dashed #2f4368;border-radius:8px;background:#070a12">
  <div style="font-size:24px">✓</div>
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">No pending approvals</div>
  <div style="font-size:13px;color:#64748b">All promotion gates are clear.</div>
</div>""",
                unsafe_allow_html=True,
            )
        else:
            for approval in pending:
                _approval_card(approval, svc)

    with tab_history:
        _history_table(history)

    with tab_test:
        _test_request_form(svc, projects)


_main()
