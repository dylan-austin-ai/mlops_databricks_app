"""Portfolio Analytics — program-level rollups with comparability indicator (§14)."""

from __future__ import annotations

import streamlit as st

from components.theme import apply_theme, page_header, render_sidebar
from config import get_config

st.set_page_config(page_title="Portfolio — MLOps", page_icon="📊", layout="wide")
apply_theme()


def main() -> None:
    render_sidebar()
    st.markdown(
        page_header(
            "Program View",
            "Portfolio Analytics",
            "Rollups across every governed project — impact figures split by confidence, never blended.",
        ),
        unsafe_allow_html=True,
    )

    cfg = get_config()
    if not cfg.is_connected:
        st.warning("Connect to Databricks to view portfolio analytics.", icon="⚠️")
        return

    try:
        from services.portfolio_analytics_service import PortfolioAnalyticsService

        svc = PortfolioAnalyticsService()
        speed = svc.speed_metrics()
        reliability = svc.reliability_metrics()
        reuse = svc.reuse_metrics()
        impact = svc.business_impact_rollup()
        costs = svc.cost_rollup()
        revalidation = svc.revalidation_metrics()
    except Exception as exc:
        st.error(f"Failed to load portfolio metrics: {exc}")
        return

    try:
        from services.capacity_service import CapacityService

        capacity_svc = CapacityService()
        capacity = capacity_svc.latest_capacity_snapshot()
        budget = capacity_svc.control_plane_budget_status()
    except Exception as exc:
        st.error(f"Failed to load capacity/budget metrics: {exc}")
        capacity, budget = None, None

    # §14.3: the roadmap phase is an org claim, not a computed metric
    st.caption("Program phase banner: org-configured, not derived from data (§14.3) — set it in Settings.")

    row1 = st.columns(4)
    with row1[0]:
        st.metric("Promotions (90d)", speed["promotions"])
    with row1[1]:
        hours = speed["avg_approval_to_deploy_hours"]
        st.metric("Approval → deploy", f"{hours:.1f} h" if hours is not None else "—")
    with row1[2]:
        rate = reliability["failure_rate_pct"]
        st.metric(
            "Deploy failure rate",
            f"{rate:.1f} %" if rate is not None else "—",
            help="failed + verify_failed over all bundle deployments (90d)",
        )
    with row1[3]:
        st.metric(
            "Shared features reused",
            f"{reuse['multi_consumer_features']} / {reuse['shared_features']}",
            help="shared features with ≥2 consuming models (§8.5 lineage counts)",
        )

    baseline_note = " (PLACEHOLDER — unmeasured)" if speed["de_novo_baseline_is_placeholder"] else ""
    st.caption(
        f"Interview Speed is judged against a de novo by-hand baseline of "
        f"{speed['de_novo_baseline_days']} days{baseline_note} (§26.4)."
    )

    if revalidation["governance_coverage_penalty"]:
        st.warning(
            f"Governance coverage penalty: {revalidation['revalidation_due']} model(s) revalidation-due, "
            f"{revalidation['in_revalidation']} in re-review, "
            f"{revalidation['promotion_blocked']} blocking promotion (§20.5).",
            icon="⏰",
        )

    st.markdown("---")
    st.subheader("Business impact (§14.4 — by confidence)")
    col_high, col_low = st.columns(2)
    with col_high:
        st.metric(
            f"High confidence · {impact.high_confidence_projects} project(s)",
            f"${impact.high_confidence_usd:,.0f}",
            help="business_value_fn reviewed within 365 days",
        )
    with col_low:
        st.metric(
            f"Low confidence · {impact.low_confidence_projects} project(s)",
            f"${impact.low_confidence_usd:,.0f}",
            help="value function unreviewed or review older than a year — treat with caution",
        )
    if impact.unreviewed_projects:
        st.warning(
            "Projects needing a business_value_fn review: " + ", ".join(impact.unreviewed_projects),
            icon="🔍",
        )

    st.markdown("---")
    st.subheader("Cost (30d)")
    group_by = st.radio(
        "Group by",
        options=["project", "team", "deployment_type"],
        format_func=lambda k: {"project": "Project", "team": "Team", "deployment_type": "Deployment type"}[k],
        horizontal=True,
        label_visibility="collapsed",
    )
    if group_by != "project":
        try:
            costs = svc.cost_rollup(group_by=group_by)
        except Exception as exc:
            st.error(f"Failed to load cost rollup: {exc}")
            costs = []
    label_key = {"project": "project_id", "team": "team_name", "deployment_type": "deployment_type"}[group_by]
    label_col = {"project": "Project", "team": "Team", "deployment_type": "Deployment type"}[group_by]
    if costs:
        st.dataframe(
            [{label_col: r.get(label_key, "—"), "Total USD": float(r.get("total_usd") or 0)} for r in costs],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption(
            "No tagged cost rows yet — costs appear once the Reconciliation Service "
            "runs against a live workspace with project-tagged resources (§17.3)."
        )

    st.markdown("---")
    st.subheader("Workspace capacity & control-plane budget (§17.4 / §19.2)")
    col_cap, col_budget = st.columns(2)
    with col_cap:
        if capacity:
            st.metric(
                "Serving endpoints",
                f"{capacity.endpoint_count} / {capacity.endpoint_warn_threshold}",
                help="workspace-wide count vs internally-set alert threshold — no hard limit is published (§19.2)",
            )
            st.caption(f"Jobs: {capacity.job_count} · Concurrent runs: {capacity.concurrent_run_count}")
            if capacity.status == "warning":
                st.warning(capacity.detail, icon="⚠️")
        else:
            st.caption("No capacity snapshot yet — appears once the Capacity Service runs (§19.2).")
    with col_budget:
        if budget:
            label = "Control-plane cost (30d)" + (" · PLACEHOLDER thresholds" if budget.is_placeholder else "")
            st.metric(
                label,
                f"${budget.total_cost_usd:,.2f}",
                help=f"warn ${budget.warn_threshold_usd:,.0f} / crit ${budget.crit_threshold_usd:,.0f} per month",
            )
            if budget.status == "critical":
                st.error(f"Control-plane spend at/above critical threshold (${budget.crit_threshold_usd:,.0f}/mo).")
            elif budget.status == "warning":
                st.warning(f"Control-plane spend at/above warn threshold (${budget.warn_threshold_usd:,.0f}/mo).")
        else:
            st.caption("No control-plane cost rows yet — appears once cost reconciliation runs (§17.4).")


main()
