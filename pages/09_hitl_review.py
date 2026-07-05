"""HITL Review — per-prediction human review queue (§11.2, §11.4)."""

from __future__ import annotations

import streamlit as st

from components.theme import apply_theme, page_header, render_sidebar
from config import get_config

st.set_page_config(page_title="HITL Review — MLOps", page_icon="👤", layout="wide")
apply_theme()


def _review_card(item: dict, svc) -> None:
    prediction_id = item["prediction_id"]
    confidence = item.get("confidence_bucket") or "—"
    contributions = item.get("feature_contributions") or {}
    alias = item.get("resolved_alias") or "—"
    presented = str(item.get("presented_timestamp", ""))[:16]
    escalated = item.get("escalated") in (True, "true")

    with st.container(border=True):
        col_info, col_why = st.columns([1, 1])
        with col_info:
            st.markdown(f"**Prediction** `{prediction_id}`")
            st.caption(
                f"project {item.get('project_id', '—')} · served by @{alias} · queued {presented}"
                + (" · **⏰ SLA escalated**" if escalated else "")
            )
            st.markdown(f"Confidence: **{confidence}**")
        with col_why:
            # §11.2: a reviewer who can't see WHY can't do meaningful review
            if contributions:
                st.caption("Top feature contributions")
                st.json(contributions, expanded=False)
            else:
                st.caption(
                    "Explanation not yet available — async items land via the "
                    "background job (§12.2). Sync-only items are guaranteed at "
                    "review time only in synchronous HITL mode (§11.3)."
                )

        col_email, col_value, col_comment = st.columns(3)
        with col_email:
            reviewer = st.text_input("Your email", key=f"hitl_email_{prediction_id}")
        with col_value:
            overridden_value = st.text_input("Override value (only for Override)", key=f"hitl_val_{prediction_id}")
        with col_comment:
            comment = st.text_input("Comment", key=f"hitl_comment_{prediction_id}")

        col_a, col_o, col_r = st.columns(3)
        decisions = [
            (col_a, "✓ Approve", "approved", "primary"),
            (col_o, "✎ Override", "overridden", "secondary"),
            (col_r, "✕ Reject", "rejected", "secondary"),
        ]
        for col, label, decision, kind in decisions:
            with col:
                if st.button(label, key=f"hitl_{decision}_{prediction_id}", type=kind, use_container_width=True):
                    _decide(svc, prediction_id, reviewer, decision, overridden_value, comment)


def _decide(svc, prediction_id: str, reviewer: str, decision: str, overridden_value: str, comment: str) -> None:
    from services.hitl_review_service import HITLReviewError

    if not reviewer or "@" not in reviewer:
        st.error("Enter a valid email address.", icon="❌")
        return
    try:
        outcome = svc.decide(
            prediction_id=prediction_id,
            reviewer_email=reviewer,
            decision=decision,
            overridden_value=overridden_value,
            comment=comment,
        )
    except HITLReviewError as exc:
        st.error(str(exc), icon="❌")
        return
    if not outcome.recorded:
        st.warning(outcome.reason, icon="⚠️")  # §11.2: explained, never overwritten
        return
    st.success(f"Decision recorded: {decision}.", icon="✅")
    st.rerun()


def main() -> None:
    render_sidebar()
    st.markdown(
        page_header(
            "Human Oversight",
            "HITL Review Queue",
            "High-stakes predictions awaiting human decision — with the model's why alongside.",
        ),
        unsafe_allow_html=True,
    )

    cfg = get_config()
    if not cfg.is_connected:
        st.warning("Connect to Databricks to view the review queue.", icon="⚠️")
        return

    try:
        from services.hitl_review_service import HITLReviewService
        from services.state_service import StateService

        state = StateService()
        svc = HITLReviewService(state=state)
        projects = state.list_projects()
    except Exception as exc:
        st.error(f"Failed to load review queue: {exc}")
        return

    names = ["All projects"] + [p["project_name"] for p in projects]
    selected = st.selectbox("Project", names)
    project_id = None
    if selected != "All projects":
        project_id = next(p["project_id"] for p in projects if p["project_name"] == selected)

    try:
        pending = svc.pending(project_id)
    except Exception as exc:
        st.error(f"Failed to query pending reviews: {exc}")
        return

    st.metric("Pending reviews", len(pending))
    if not pending:
        st.markdown(
            """
<div style="display:flex;flex-direction:column;align-items:center;gap:12px;
            padding:64px 24px;text-align:center;
            border:1px dashed #2f4368;border-radius:8px;background:#070a12">
  <div style="font-size:24px">👤</div>
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">Queue is clear</div>
  <div style="font-size:13px;color:#64748b">No predictions awaiting human review.</div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    for item in pending:
        _review_card(item, svc)


main()
