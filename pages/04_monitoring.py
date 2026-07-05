"""Monitoring Dashboard — drift, performance, alerts, fairness."""

from __future__ import annotations

import streamlit as st

from components.theme import apply_theme, page_header, pill, render_sidebar, sev_badge
from config import get_config

st.set_page_config(page_title="Monitoring — MLOps", page_icon="📊", layout="wide")
apply_theme()


def _sidebar_extra(projects: list[dict]) -> tuple[str | None, str]:
    """Project selector in sidebar; returns (selected_name, extra_html)."""
    if not projects:
        return None, ""
    names = [p["project_name"] for p in projects]
    default = st.session_state.get("monitoring_project_name", names[0])
    idx = names.index(default) if default in names else 0
    selected = st.sidebar.selectbox("Project", names, index=idx, label_visibility="collapsed")
    st.session_state["monitoring_project_name"] = selected
    return selected, ""


def _get_model_id(svc: object, project_id: str) -> str | None:
    rows = svc._exec(
        f"SELECT model_id FROM {svc._tbl('models')} "
        f"WHERE project_id = '{project_id}' ORDER BY created_timestamp DESC LIMIT 1"
    )
    return rows[0]["model_id"] if rows else None


def _performance_tab(svc: object, model_id: str) -> None:
    import plotly.graph_objects as go

    rows = svc.list_performance_history(model_id, limit=60)
    if not rows:
        st.markdown(
            """<div style="display:flex;flex-direction:column;align-items:center;gap:12px;
            padding:64px 24px;text-align:center;border:1px dashed #2f4368;
            border-radius:8px;background:#070a12">
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">No performance data yet</div>
  <div style="font-size:13px;color:#64748b;max-width:380px">
    Performance metrics are written here once the model is deployed and making predictions.</div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    latest = rows[0]
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        acc = latest.get("accuracy")
        delta = latest.get("accuracy_vs_baseline_delta")
        st.metric("Accuracy", f"{acc:.3f}" if acc else "—", delta=f"{delta:+.3f}" if delta else None)
    with col2:
        st.metric("AUC-ROC", f"{latest.get('auc_roc', 0):.3f}" if latest.get("auc_roc") else "—")
    with col3:
        err = latest.get("error_rate_pct")
        st.metric("Error rate", f"{err:.2f}%" if err is not None else "—")
    with col4:
        lat = latest.get("latency_p95_ms")
        st.metric("P95 latency", f"{lat:.0f} ms" if lat else "—")

    timestamps = [r.get("measurement_timestamp", "") for r in rows]
    accuracy = [r.get("accuracy") for r in rows]
    error_rate = [r.get("error_rate_pct") for r in rows]

    _LAYOUT = dict(
        paper_bgcolor="#070a12",
        plot_bgcolor="#070a12",
        font=dict(family="JetBrains Mono, monospace", color="#64748b", size=11),
        margin=dict(l=0, r=0, t=36, b=0),
        height=240,
        xaxis=dict(gridcolor="#1a2740", showgrid=True, zeroline=False),
        yaxis=dict(gridcolor="#1a2740", showgrid=True, zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
    )

    if any(v is not None for v in accuracy):
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=accuracy,
                name="Accuracy",
                mode="lines",
                line=dict(color="#00d4ff", width=2),
                fill="tozeroy",
                fillcolor="rgba(0,212,255,0.07)",
            )
        )
        fig.update_layout(title=dict(text="Accuracy over time", font=dict(color="#a9b6cc", size=13)), **_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

    if any(v is not None for v in error_rate):
        fig2 = go.Figure()
        fig2.add_trace(
            go.Scatter(
                x=timestamps,
                y=error_rate,
                name="Error rate %",
                mode="lines",
                line=dict(color="#ef4444", width=2),
                fill="tozeroy",
                fillcolor="rgba(239,68,68,0.06)",
            )
        )
        fig2.update_layout(title=dict(text="Error rate %", font=dict(color="#a9b6cc", size=13)), **_LAYOUT)
        st.plotly_chart(fig2, use_container_width=True)


def _drift_tab(svc: object, model_id: str) -> None:
    import plotly.graph_objects as go

    rows = svc.list_recent_drift_results(model_id, limit=100)
    if not rows:
        st.markdown(
            """<div style="display:flex;flex-direction:column;align-items:center;gap:12px;
            padding:64px 24px;text-align:center;border:1px dashed #2f4368;
            border-radius:8px;background:#070a12">
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">No drift data yet</div>
  <div style="font-size:13px;color:#64748b;max-width:380px">
    Drift detection runs automatically once the model is serving predictions.</div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    latest_per_field: dict[str, dict] = {}
    for r in rows:
        f = r.get("field_name", "unknown")
        if f not in latest_per_field:
            latest_per_field[f] = r

    # Summary table with HTML badges
    header = (
        '<div style="display:grid;grid-template-columns:1fr 100px 90px 120px 130px;'
        "gap:8px;padding:8px 12px;background:#070a12;border-radius:5px 5px 0 0;"
        "font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#46546e;"
        'border:1px solid #1a2740;border-bottom:1px solid #2f4368">'
        "<span>Field</span><span>Detected</span><span>KS score</span>"
        "<span>Severity</span><span>Measured</span></div>"
    )
    rows_html = ""
    for field, r in sorted(latest_per_field.items()):
        detected = "Yes" if r.get("drift_detected") else "No"
        detected_color = "#ef4444" if r.get("drift_detected") else "#5eead4"
        ks = f"{r.get('drift_score', 0):.3f}" if r.get("drift_score") is not None else "—"
        sev = r.get("drift_severity", "none")
        badge = sev_badge(sev)
        ts = str(r.get("measurement_timestamp", ""))[:16]
        rows_html += (
            f'<div style="display:grid;grid-template-columns:1fr 100px 90px 120px 130px;'
            f"gap:8px;padding:10px 12px;border:1px solid #1a2740;border-top:none;"
            f'transition:background 120ms ease" '
            f"onmouseover=\"this.style.background='#161f33'\" "
            f"onmouseout=\"this.style.background='transparent'\">"
            f'<span style="font-size:13px;color:#e2e8f0;font-weight:500">{field}</span>'
            f"<span style=\"font-size:13px;color:{detected_color};font-family:'JetBrains Mono',monospace\">{detected}</span>"
            f"<span style=\"font-size:13px;color:#a9b6cc;font-family:'JetBrains Mono',monospace\">{ks}</span>"
            f"<span>{badge}</span>"
            f"<span style=\"font-size:12px;color:#64748b;font-family:'JetBrains Mono',monospace\">{ts}</span>"
            f"</div>"
        )

    st.markdown(header + rows_html, unsafe_allow_html=True)
    st.markdown("")

    top_fields = list(latest_per_field.keys())[:6]
    if top_fields:
        fig = go.Figure()
        for field in top_fields:
            field_rows = [r for r in rows if r.get("field_name") == field]
            fig.add_trace(
                go.Scatter(
                    x=[r.get("measurement_timestamp") for r in field_rows],
                    y=[r.get("drift_score") for r in field_rows],
                    name=field,
                    mode="lines+markers",
                    marker=dict(size=4),
                )
            )
        fig.add_hline(
            y=0.1,
            line_dash="dash",
            line_color="#f59e0b",
            annotation_text="threshold 0.10",
            annotation_font=dict(color="#fcd34d", size=11),
        )
        fig.update_layout(
            paper_bgcolor="#070a12",
            plot_bgcolor="#070a12",
            font=dict(family="JetBrains Mono, monospace", color="#64748b", size=11),
            title=dict(text="KS statistic over time", font=dict(color="#a9b6cc", size=13)),
            xaxis=dict(gridcolor="#1a2740"),
            yaxis=dict(gridcolor="#1a2740"),
            margin=dict(l=0, r=0, t=36, b=0),
            height=260,
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig, use_container_width=True)


def _alerts_tab(svc: object, model_id: str) -> None:
    import plotly.graph_objects as go
    from collections import Counter

    rows = svc.list_recent_alerts(model_id, limit=50)
    if not rows:
        st.markdown(
            """<div style="display:flex;flex-direction:column;align-items:center;gap:12px;
            padding:64px 24px;text-align:center;border:1px dashed #2f4368;
            border-radius:8px;background:#070a12">
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">No alerts fired</div>
  <div style="font-size:13px;color:#64748b">All clear — no thresholds breached.</div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Recent alerts", len(rows))
    with col2:
        st.metric("Critical", sum(1 for r in rows if r.get("severity") == "critical"))
    with col3:
        st.metric("Unresolved", sum(1 for r in rows if not r.get("resolved")))

    st.markdown("---")
    table_rows = []
    for r in rows:
        sev = r.get("severity", "info")
        table_rows.append(
            {
                "Alert": r.get("alert_name", "—"),
                "Metric": r.get("metric_name", "—"),
                "Value": f"{r.get('alert_value', ''):.3f}" if r.get("alert_value") is not None else "—",
                "Severity": sev.upper(),
                "Triggered": str(r.get("triggered_timestamp", ""))[:16],
                "Resolved": "Yes" if r.get("resolved") else "No",
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    if len(rows) >= 3:
        day_counts = Counter(str(r.get("triggered_timestamp", ""))[:10] for r in rows if r.get("triggered_timestamp"))
        days = sorted(day_counts)
        fig = go.Figure(
            go.Bar(
                x=days,
                y=[day_counts[d] for d in days],
                marker=dict(color="#1e3a5f", line=dict(color="#00d4ff", width=1)),
            )
        )
        fig.update_layout(
            paper_bgcolor="#070a12",
            plot_bgcolor="#070a12",
            font=dict(family="JetBrains Mono, monospace", color="#64748b", size=11),
            title=dict(text="Alert frequency by day", font=dict(color="#a9b6cc", size=13)),
            xaxis=dict(gridcolor="#1a2740"),
            yaxis=dict(gridcolor="#1a2740"),
            margin=dict(l=0, r=0, t=36, b=0),
            height=220,
        )
        st.plotly_chart(fig, use_container_width=True)


def _fairness_tab(svc: object, model_id: str) -> None:
    import plotly.graph_objects as go

    rows = svc.list_performance_history(model_id, limit=30)
    rows_with_fairness = [
        r
        for r in rows
        if r.get("fairness_demographic_parity") is not None or r.get("fairness_equalized_odds") is not None
    ]
    if not rows_with_fairness:
        st.markdown(
            """<div style="display:flex;flex-direction:column;align-items:center;gap:12px;
            padding:64px 24px;text-align:center;border:1px dashed #2f4368;
            border-radius:8px;background:#070a12">
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">No fairness metrics yet</div>
  <div style="font-size:13px;color:#64748b;max-width:380px">
    Fairness metrics are computed during model validation and written after each training run.</div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    latest = rows_with_fairness[0]
    col1, col2, col3 = st.columns(3)
    with col1:
        dp = latest.get("fairness_demographic_parity")
        st.metric("Demographic parity", f"{dp:.3f}" if dp is not None else "—")
    with col2:
        eo = latest.get("fairness_equalized_odds")
        st.metric("Equalized odds", f"{eo:.3f}" if eo is not None else "—")
    with col3:
        passed = latest.get("fairness_test_passed")
        if passed is not None:
            st.markdown(pill("approved" if passed else "rejected"), unsafe_allow_html=True)

    times = [r.get("measurement_timestamp") for r in rows_with_fairness]
    dp_vals = [r.get("fairness_demographic_parity") for r in rows_with_fairness]
    eo_vals = [r.get("fairness_equalized_odds") for r in rows_with_fairness]

    fig = go.Figure()
    if any(v is not None for v in dp_vals):
        fig.add_trace(
            go.Scatter(
                x=times, y=dp_vals, name="Demographic parity", mode="lines+markers", line=dict(color="#00d4ff", width=2)
            )
        )
    if any(v is not None for v in eo_vals):
        fig.add_trace(
            go.Scatter(
                x=times, y=eo_vals, name="Equalized odds", mode="lines+markers", line=dict(color="#818cf8", width=2)
            )
        )
    fig.add_hline(
        y=0.1,
        line_dash="dash",
        line_color="#f59e0b",
        annotation_text="threshold 0.10",
        annotation_font=dict(color="#fcd34d", size=11),
    )
    fig.update_layout(
        paper_bgcolor="#070a12",
        plot_bgcolor="#070a12",
        font=dict(family="JetBrains Mono, monospace", color="#64748b", size=11),
        title=dict(text="Fairness metrics over time", font=dict(color="#a9b6cc", size=13)),
        xaxis=dict(gridcolor="#1a2740"),
        yaxis=dict(gridcolor="#1a2740"),
        margin=dict(l=0, r=0, t=36, b=0),
        height=300,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _main() -> None:
    cfg = get_config()

    if not cfg.is_connected:
        render_sidebar()
        st.warning("Connect to Databricks to view monitoring.", icon="⚠️")
        return

    try:
        from services.state_service import StateService

        svc = StateService()
        projects = svc.list_projects()
    except Exception as exc:
        render_sidebar()
        st.error(f"Failed to load projects: {exc}")
        return

    # Project selector lives in sidebar — must run before render_sidebar
    if not projects:
        render_sidebar()
        st.markdown(
            page_header("Runtime Health", "Monitoring", "Create a project first to view monitoring data."),
            unsafe_allow_html=True,
        )
        return

    names = [p["project_name"] for p in projects]
    default = st.session_state.get("monitoring_project_name", names[0])
    idx = names.index(default) if default in names else 0

    # Inject project picker into sidebar via extra_html label + render main nav
    render_sidebar(
        extra_html=(
            '<div style="margin-top:16px;padding-top:16px;border-top:1px solid #1a2740">'
            '<p style="font-size:11px;font-weight:600;text-transform:uppercase;'
            'letter-spacing:0.12em;color:#46546e;padding:4px 0 8px">Monitoring scope</p>'
            "</div>"
        )
    )
    # Selectbox must be in sidebar context
    with st.sidebar:
        selected_name = st.selectbox("Project", names, index=idx, label_visibility="collapsed")
        st.session_state["monitoring_project_name"] = selected_name

    project = next((p for p in projects if p["project_name"] == selected_name), None)
    if not project:
        return

    status = project.get("status", "—")
    st.markdown(
        page_header(
            "Runtime Health",
            "Monitoring",
            f"Live model performance for <span style='font-family:JetBrains Mono,monospace;"
            f"color:#a9b6cc'>{selected_name}</span>.",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(pill(status), unsafe_allow_html=True)
    st.markdown("---")

    model_id = _get_model_id(svc, project["project_id"])
    if not model_id:
        st.info(
            "No model registered for this project yet. "
            "Models appear here after the first training run is logged to MLflow.",
            icon="🤖",
        )
        return

    tab_perf, tab_drift, tab_alerts, tab_fairness = st.tabs(["Performance", "Data Drift", "Alerts", "Fairness"])
    with tab_perf:
        _performance_tab(svc, model_id)
    with tab_drift:
        _drift_tab(svc, model_id)
    with tab_alerts:
        _alerts_tab(svc, model_id)
    with tab_fairness:
        _fairness_tab(svc, model_id)


_main()
