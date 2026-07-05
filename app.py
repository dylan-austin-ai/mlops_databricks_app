"""Databricks MLOps App — Streamlit entry point."""

from __future__ import annotations

import streamlit as st

from components.theme import apply_theme, page_header, pill, render_sidebar
from config import get_config

st.set_page_config(
    page_title="MLOps Platform",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()


def _home() -> None:
    render_sidebar()

    cfg = get_config()

    st.markdown(
        page_header(
            "Command Center",
            "MLOps Platform",
            "Interview-driven MLOps for Databricks — interview, generate, govern.",
        ),
        unsafe_allow_html=True,
    )

    if not cfg.is_connected:
        st.warning(
            "**Not connected to Databricks.** "
            "Set `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, and `DATABRICKS_WAREHOUSE_ID` "
            "in your `.env` file, then restart.",
            icon="⚠️",
        )
        with st.expander("Setup instructions"):
            st.code(
                "cp .env.example .env\n# fill in your workspace details\nstreamlit run app.py",
                language="bash",
            )
        return

    st.markdown("---")

    try:
        from services.state_service import StateService

        svc = StateService()
        projects = svc.list_projects()

        by_status: dict[str, int] = {}
        for p in projects:
            s = p.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Projects", len(projects))
        with col2:
            st.metric("In Production", by_status.get("production", 0))
        with col3:
            st.metric(
                "In Development",
                by_status.get("development", 0) + by_status.get("staging", 0),
            )

        st.markdown("---")
        st.markdown("**Recent projects**")

        if not projects:
            st.info("No projects yet. [Create your first project](/02_new_project).")
        else:
            for p in projects[:5]:
                status = p.get("status", "created")
                col_a, col_b, col_c = st.columns([3, 2, 1])
                with col_a:
                    st.markdown(f"**{p['project_name']}**")
                with col_b:
                    st.caption(f"{p.get('team_name', '—')} · {p.get('owner_email', '—')}")
                with col_c:
                    st.markdown(pill(status), unsafe_allow_html=True)

    except Exception as exc:
        st.error(f"Could not load projects: {exc}")
        st.caption("Run `python -m db.setup` to initialise the schema.")


_home()
