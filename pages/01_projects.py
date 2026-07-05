"""Projects list — all models with status, owner, quick stats."""

from __future__ import annotations

import streamlit as st

from components.theme import apply_theme, page_header, path_chip, pill, render_sidebar
from config import get_config

st.set_page_config(page_title="Projects — MLOps", page_icon="📁", layout="wide")
apply_theme()

_STAGE_BORDER = {
    "production": "#10b981",
    "staging": "#f59e0b",
    "development": "#00d4ff",
    "created": "#00d4ff",
    "archived": "#475569",
    "deleted": "#ef4444",
}


def _project_card(p: dict) -> None:
    status = p.get("status", "created")
    border_color = _STAGE_BORDER.get(status, "#1a2740")
    name = p.get("project_name", "—")
    desc = (p.get("project_description") or "")[:140]
    owner = p.get("owner_email", "—")
    team = p.get("team_name", "—")
    updated = str(p.get("last_updated", p.get("created_timestamp", "")))[:10]
    uc_path = p.get("uc_schema_prod") or p.get("uc_schema_dev") or ""
    github_url = p.get("github_repo_url", "")
    project_id = p.get("project_id", "")

    path_html = path_chip(uc_path) if uc_path else ""
    pill_html = pill(status)

    card = f"""
<div style="background:#111827;border:1px solid #1a2740;border-radius:8px;
            border-left:2px solid {border_color};padding:20px;
            display:flex;flex-direction:column;gap:14px;
            transition:border-color 180ms ease,box-shadow 180ms ease;"
     onmouseover="this.style.borderColor='#243456';this.style.boxShadow='0 4px 16px rgba(0,0,0,0.45)'"
     onmouseout="this.style.borderColor='#1a2740';this.style.boxShadow='none'">

  <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
    <span style="font-size:17px;font-weight:600;color:#f4f8ff">{name}</span>
    {pill_html}
  </div>

  {"<p style='font-size:13px;color:#64748b;line-height:1.45;margin:0'>" + desc + "</p>" if desc else ""}

  <div style="display:flex;flex-wrap:wrap;gap:8px 20px">
    <div style="display:flex;flex-direction:column;gap:3px">
      <span style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#46546e;font-weight:600">Owner</span>
      <span style="font-size:12px;color:#a9b6cc;font-family:'JetBrains Mono',monospace">{owner}</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:3px">
      <span style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#46546e;font-weight:600">Team</span>
      <span style="font-size:12px;color:#a9b6cc">{team}</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:3px">
      <span style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:#46546e;font-weight:600">Updated</span>
      <span style="font-size:12px;color:#a9b6cc;font-family:'JetBrains Mono',monospace">{updated}</span>
    </div>
  </div>

  <div style="display:flex;align-items:center;gap:8px;padding-top:12px;border-top:1px solid #1a2740">
    {path_html}
  </div>
</div>"""

    st.markdown(card, unsafe_allow_html=True)

    # Streamlit action buttons below each card
    btn_cols = st.columns([1, 1, 4])
    with btn_cols[0]:
        if st.button("Open →", key=f"open_{project_id}", use_container_width=True):
            st.session_state["dashboard_project_id"] = project_id
            st.switch_page("pages/06_project_dashboard.py")
    with btn_cols[1]:
        if github_url:
            st.link_button("GitHub ↗", github_url, use_container_width=True)


def _main() -> None:
    render_sidebar()

    st.markdown(
        page_header(
            "Model Registry",
            "Projects",
            "Every model across dev, staging, and production.",
        ),
        unsafe_allow_html=True,
    )

    cfg = get_config()
    if not cfg.is_connected:
        st.warning("Connect to Databricks to view projects.", icon="⚠️")
        return

    btn_col, _ = st.columns([2, 5])
    with btn_col:
        if st.button("＋ New Project", use_container_width=True, type="primary"):
            st.switch_page("pages/02_new_project.py")

    status_filter = st.selectbox(
        "Filter by status",
        ["All", "production", "staging", "development", "created", "archived"],
        index=0,
    )

    st.markdown("---")

    try:
        from services.state_service import StateService

        svc = StateService()
        include_archived = status_filter == "archived"
        projects = svc.list_projects(include_archived=include_archived)

        if status_filter not in ("All", "archived"):
            projects = [p for p in projects if p.get("status") == status_filter]

        if not projects:
            st.markdown(
                """
<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
            gap:12px;padding:64px 24px;text-align:center;
            border:1px dashed #2f4368;border-radius:8px;background:#070a12">
  <div style="width:48px;height:48px;display:grid;place-content:center;border-radius:8px;
              background:#161f33;border:1px solid #243456;color:#64748b;font-size:20px">▦</div>
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">No projects yet</div>
  <div style="font-size:13px;color:#64748b;max-width:380px">
    Create your first ML project to start tracking models through dev, staging, and production.</div>
</div>""",
                unsafe_allow_html=True,
            )
            return

        total = len(projects)
        prod_count = sum(1 for p in projects if p.get("status") == "production")
        st.caption(f"Showing {total} project{'s' if total != 1 else ''} · {prod_count} in production")
        st.markdown("")

        # Two-column card grid
        cols = st.columns(2, gap="medium")
        for i, p in enumerate(projects):
            with cols[i % 2]:
                _project_card(p)

    except Exception as exc:
        st.error(f"Failed to load projects: {exc}")
        with st.expander("Troubleshooting"):
            st.markdown(
                "1. Check `.env` has `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, "
                "`DATABRICKS_WAREHOUSE_ID`\n"
                "2. Run `python -m db.setup`\n"
                "3. Verify the warehouse is running"
            )


_main()
