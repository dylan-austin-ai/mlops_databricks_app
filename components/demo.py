"""Demo Mode — a zero-config walkthrough of the New Project wizard and
Project Dashboard, for early stakeholder demos before the real design
solidifies. Every real write (GitHub repo, Unity Catalog, MLflow, bundle
commits, ...) is replaced by a fabricated result plus a popup describing
what the real action would have done; every read comes from an in-memory,
session-scoped store (services/demo/store.py) instead of the real SQL
warehouse. See services/demo/ for the fake service implementations the
factories below construct.

Entry point: the "Try Demo Mode" button on the Settings page's
not-connected state. Session-only — resets when the browser session ends.
"""

from __future__ import annotations

import dataclasses

import streamlit as st

_MODE_KEY = "demo_mode"
_POPUP_KEY = "_demo_pending_popup"


def is_demo_active() -> bool:
    if st.session_state.get(_MODE_KEY):
        return True
    if st.query_params.get("demo") in ("1", "true", "True"):
        st.session_state[_MODE_KEY] = True
        return True
    return False


def enter_demo_mode() -> None:
    st.session_state[_MODE_KEY] = True


def exit_demo_mode() -> None:
    st.session_state.pop(_MODE_KEY, None)
    st.session_state.pop("_demo_store", None)
    st.session_state.pop(_POPUP_KEY, None)


def reset_demo_data() -> None:
    from services.demo.store import reset_store

    reset_store()


# ── "What this would do" popup ────────────────────────────────────────────────


def queue_action(title: str, description: str) -> None:
    """Record a simulated action to surface as a popup on the next rerun."""
    st.session_state[_POPUP_KEY] = {"title": title, "description": description}


@st.dialog("🎬 Demo Mode — Simulated Action")
def _popup_dialog(title: str, description: str) -> None:
    st.markdown(f"**{title}**")
    st.write(description)
    st.caption("Nothing was actually created or changed.")
    if st.button("OK", type="primary"):
        st.rerun()


def render_pending_popup() -> None:
    """Call once near the top of a page, alongside apply_theme()/render_sidebar()."""
    pending = st.session_state.get(_POPUP_KEY)
    if pending:
        st.session_state[_POPUP_KEY] = None
        _popup_dialog(pending["title"], pending["description"])


# ── Factories — return the Demo* variant when active, else the real service ──


def _demo_config():
    """Real AppConfig with github_token forced non-empty so the existing
    `if scaffold_dir and self._cfg.github_token:` gate in
    ProjectProvisioningService.provision_step1 takes the branch that reaches
    our fabricated _create_github_repo, instead of skipping with "GITHUB_TOKEN
    not set" -- Demo Mode must show the same popups regardless of what
    happens to be configured."""
    from config import get_config

    return dataclasses.replace(get_config(), github_token="demo-token")


def get_state_service():
    if is_demo_active():
        from services.demo.state_service import DemoStateService

        return DemoStateService()
    from services.state_service import StateService

    return StateService()


def get_db_service():
    if is_demo_active():
        from services.demo.db_service import DemoDbService

        return DemoDbService()
    from services.db_service import DbService

    return DbService()


def get_ai_service():
    if is_demo_active():
        from services.demo.ai_service import DemoAiService

        return DemoAiService()
    from services.ai_service import AiService

    return AiService()


def get_provisioning_service():
    if is_demo_active():
        from services.demo.generator import DemoProjectInfrastructureGenerator
        from services.demo.state_service import DemoStateService
        from services.project_provisioning_service import ProjectProvisioningService

        cfg = _demo_config()
        return ProjectProvisioningService(
            cfg, state=DemoStateService(), generator=DemoProjectInfrastructureGenerator(cfg)
        )
    from config import get_config
    from services.project_provisioning_service import ProjectProvisioningService

    return ProjectProvisioningService(get_config())


def get_bundle_commit_service():
    if is_demo_active():
        from services.demo.bundle_commit import DemoBundleCommitService

        return DemoBundleCommitService()
    from config import get_config
    from services.bundle_commit_service import BundleCommitService

    return BundleCommitService(get_config())


# ── Sidebar banner ─────────────────────────────────────────────────────────


def render_demo_banner() -> None:
    """Rendered inside components.theme.render_sidebar() when Demo Mode is
    active -- the one call site every page already shares, so this is the
    only place needed to make the indicator appear app-wide."""
    if not is_demo_active():
        return
    st.markdown(
        '<div style="margin-top:12px;padding:12px;border-radius:5px;'
        'background:rgba(245,158,11,0.10);border:1px solid rgba(245,158,11,0.35);">'
        '<span style="font-size:12px;font-weight:700;color:#f59e0b">🎬 DEMO MODE</span><br>'
        '<span style="font-size:11px;color:#a9b6cc">No changes are saved. All actions are simulated.</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    col_reset, col_exit = st.columns(2)
    with col_reset:
        if st.button("↺ Reset", use_container_width=True, help="Reset demo data", key="demo_reset_btn"):
            reset_demo_data()
            st.rerun()
    with col_exit:
        if st.button("✕ Exit", use_container_width=True, help="Exit demo mode", key="demo_exit_btn"):
            exit_demo_mode()
            st.rerun()
