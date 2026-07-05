"""Settings — org-level configuration, personas, approval workflows, monitoring defaults."""

from __future__ import annotations

import json

import streamlit as st

from components.theme import apply_theme, page_header, render_sidebar
from config import get_config

st.set_page_config(page_title="Settings — MLOps", page_icon="⚙️", layout="wide")
apply_theme()

_INDUSTRIES = ["None / Other", "Financial Services", "Healthcare", "Insurance", "Retail", "Technology", "Government"]
_CLOUDS = ["AWS", "Azure", "GCP"]
_DEPLOYMENT_PATTERNS = ["single_workspace", "dual_workspace", "multi_cloud"]
_COMPLIANCE = ["SOX", "GDPR", "HIPAA", "PCI-DSS", "FedRAMP", "CCPA"]

_DEFAULT_PERSONAS = {
    "data_scientists": {"permissions": ["train", "experiment", "register"], "description": "Build and train models"},
    "ml_engineers": {
        "permissions": ["train", "experiment", "register", "deploy", "override", "configure"],
        "description": "Deploy models, manage infrastructure",
    },
    "legal_reviewers": {
        "permissions": ["approve_fairness", "approve_governance"],
        "description": "Review and approve fairness results",
    },
    "business_stakeholders": {
        "permissions": ["approve_production", "view_dashboards"],
        "description": "Approve production deployments",
    },
    "security": {
        "permissions": ["audit", "override", "manage_secrets"],
        "description": "Audit and security management",
    },
    "admin": {"permissions": ["all"], "description": "Full platform administration"},
}

_DEFAULT_APPROVAL_WORKFLOWS = {
    "dev_to_staging": ["code_review", "unit_tests", "security_scan", "fairness_tests"],
    "staging_to_prod_new_model": [
        "code_review",
        "fairness_review",
        "legal_review",
        "business_approval",
        "end_to_end_test",
    ],
    "staging_to_prod_update": ["code_review", "unit_tests", "security_scan"],
    "retraining_prod": ["automatic"],
    "model_deletion": ["mlops_approval"],
}

_DEFAULT_MONITORING = {
    "enable_data_drift": True,
    "enable_performance_drift": True,
    "enable_fairness_monitoring": True,
    "data_drift_ks_threshold": 0.1,
    "performance_drift_pct": 5.0,
    "endpoint_down_minutes": 5,
    "error_rate_threshold_pct": 1.0,
    "alert_destinations": ["email"],
}


def _load_config(svc: object) -> dict:
    existing = svc.get_installation_config()
    if not existing:
        return {}
    result = dict(existing)
    for json_field in ("persona_config", "monitoring_defaults", "approval_workflow_defaults"):
        raw = result.get(json_field)
        if raw:
            try:
                result[json_field] = json.loads(raw)
            except Exception:
                result[json_field] = {}
    return result


def _installation_tab(cfg_data: dict, svc: object, actor_email: str) -> None:
    st.markdown("### Organisation Configuration")
    current_version = cfg_data.get("config_version", 0)
    if current_version:
        st.caption(f"Current version: **v{current_version}**")

    with st.form("installation_form"):
        c1, c2 = st.columns(2)
        with c1:
            org_name = st.text_input("Organisation name *", value=cfg_data.get("org_name", ""), placeholder="Acme Corp")
            regulated_industry = st.selectbox(
                "Regulated industry",
                _INDUSTRIES,
                index=_INDUSTRIES.index(cfg_data.get("regulated_industry", "None / Other"))
                if cfg_data.get("regulated_industry") in _INDUSTRIES
                else 0,
            )
            compliance_frameworks = st.multiselect(
                "Compliance frameworks",
                _COMPLIANCE,
                default=[f for f in (cfg_data.get("compliance_frameworks") or []) if f in _COMPLIANCE],
            )
            support_email = st.text_input(
                "MLOps support email", value=cfg_data.get("support_email", ""), placeholder="mlops@company.com"
            )
        with c2:
            deployment_pattern = st.selectbox(
                "Deployment pattern",
                _DEPLOYMENT_PATTERNS,
                index=_DEPLOYMENT_PATTERNS.index(cfg_data.get("deployment_pattern", "single_workspace"))
                if cfg_data.get("deployment_pattern") in _DEPLOYMENT_PATTERNS
                else 0,
            )
            primary_cloud = st.selectbox(
                "Primary cloud",
                _CLOUDS,
                index=_CLOUDS.index(cfg_data.get("primary_cloud", "AWS"))
                if cfg_data.get("primary_cloud") in _CLOUDS
                else 0,
            )
            github_org = st.text_input(
                "GitHub organisation", value=cfg_data.get("github_org", ""), placeholder="acme-mlops"
            )

        submitted = st.form_submit_button("💾 Save Installation Config", type="primary")

    if submitted:
        if not org_name:
            st.error("Organisation name is required.", icon="❌")
            return
        try:
            new_cfg = {
                "org_name": org_name,
                "regulated_industry": regulated_industry,
                "compliance_frameworks": compliance_frameworks,
                "support_email": support_email,
                "deployment_pattern": deployment_pattern,
                "primary_cloud": primary_cloud,
                "github_org": github_org,
                "personas": cfg_data.get("persona_config", _DEFAULT_PERSONAS),
                "monitoring_defaults": cfg_data.get("monitoring_defaults", _DEFAULT_MONITORING),
                "approval_workflow_defaults": cfg_data.get("approval_workflow_defaults", _DEFAULT_APPROVAL_WORKFLOWS),
            }
            svc.save_installation_config(new_cfg, actor_email)
            st.success("Installation config saved.", icon="✅")
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}", icon="❌")


def _personas_tab(cfg_data: dict, svc: object, actor_email: str) -> None:
    st.markdown("### Personas & Groups")
    st.caption("Groups map to Databricks workspace groups. Permissions are cumulative.")

    personas = cfg_data.get("persona_config") or _DEFAULT_PERSONAS
    if isinstance(personas, str):
        try:
            personas = json.loads(personas)
        except Exception:
            personas = _DEFAULT_PERSONAS

    updated_personas: dict = {}
    _ALL_PERMS = [
        "train",
        "experiment",
        "register",
        "deploy",
        "override",
        "configure",
        "approve_fairness",
        "approve_governance",
        "approve_production",
        "view_dashboards",
        "audit",
        "manage_secrets",
        "all",
    ]

    for group_name, group_cfg in personas.items():
        with st.container(border=True):
            st.markdown(f"**{group_name}**")
            st.caption(group_cfg.get("description", ""))
            perms = group_cfg.get("permissions", [])
            with st.expander("Edit permissions", expanded=False):
                new_perms = st.multiselect(
                    "Permissions",
                    _ALL_PERMS,
                    default=[p for p in perms if p in _ALL_PERMS],
                    key=f"perms_{group_name}",
                )
                new_desc = st.text_input(
                    "Description", value=group_cfg.get("description", ""), key=f"desc_{group_name}"
                )
                updated_personas[group_name] = {"permissions": new_perms, "description": new_desc}

    if updated_personas and st.button("💾 Save Personas", type="primary"):
        try:
            current = _load_config(svc)
            current["personas"] = updated_personas
            current.setdefault("org_name", cfg_data.get("org_name", ""))
            current.setdefault("monitoring_defaults", _DEFAULT_MONITORING)
            current.setdefault("approval_workflow_defaults", _DEFAULT_APPROVAL_WORKFLOWS)
            svc.save_installation_config(current, actor_email)
            st.success("Personas saved.", icon="✅")
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}", icon="❌")


def _approval_workflows_tab(cfg_data: dict, svc: object, actor_email: str) -> None:
    st.markdown("### Approval Workflow Defaults")
    st.caption("Default gates applied to all new projects. Individual projects can override.")

    workflows = cfg_data.get("approval_workflow_defaults") or _DEFAULT_APPROVAL_WORKFLOWS
    if isinstance(workflows, str):
        try:
            workflows = json.loads(workflows)
        except Exception:
            workflows = _DEFAULT_APPROVAL_WORKFLOWS

    _GATE_OPTIONS = [
        "code_review",
        "unit_tests",
        "integration_tests",
        "security_scan",
        "fairness_tests",
        "fairness_review",
        "legal_review",
        "business_approval",
        "end_to_end_test",
        "automatic",
        "mlops_approval",
    ]
    _TRANSITION_LABELS = {
        "dev_to_staging": "Dev → Staging",
        "staging_to_prod_new_model": "Staging → Production (new model)",
        "staging_to_prod_update": "Staging → Production (update)",
        "retraining_prod": "Production retraining",
        "model_deletion": "Model deletion",
    }

    updated_workflows: dict = {}
    with st.form("workflows_form"):
        for transition, label in _TRANSITION_LABELS.items():
            current_gates = workflows.get(transition, [])
            updated_workflows[transition] = st.multiselect(
                label,
                _GATE_OPTIONS,
                default=[g for g in current_gates if g in _GATE_OPTIONS],
                key=f"wf_{transition}",
            )
        if st.form_submit_button("💾 Save Approval Workflows", type="primary"):
            try:
                current = _load_config(svc)
                current["approval_workflow_defaults"] = updated_workflows
                current.setdefault("org_name", cfg_data.get("org_name", ""))
                current.setdefault("personas", _DEFAULT_PERSONAS)
                current.setdefault("monitoring_defaults", _DEFAULT_MONITORING)
                svc.save_installation_config(current, actor_email)
                st.success("Approval workflows saved.", icon="✅")
                st.rerun()
            except Exception as exc:
                st.error(f"Save failed: {exc}", icon="❌")


def _monitoring_defaults_tab(cfg_data: dict, svc: object, actor_email: str) -> None:
    st.markdown("### Monitoring Defaults")
    st.caption("Default alert thresholds applied to all new projects.")

    mon = cfg_data.get("monitoring_defaults") or _DEFAULT_MONITORING
    if isinstance(mon, str):
        try:
            mon = json.loads(mon)
        except Exception:
            mon = _DEFAULT_MONITORING

    with st.form("monitoring_form"):
        c1, c2 = st.columns(2)
        with c1:
            enable_drift = st.checkbox("Enable data drift monitoring", value=mon.get("enable_data_drift", True))
            enable_perf = st.checkbox(
                "Enable performance drift monitoring", value=mon.get("enable_performance_drift", True)
            )
            enable_fairness = st.checkbox(
                "Enable fairness monitoring", value=mon.get("enable_fairness_monitoring", True)
            )
            alert_destinations = st.multiselect(
                "Default alert destinations", ["email", "slack"], default=mon.get("alert_destinations", ["email"])
            )
        with c2:
            ks_threshold = st.number_input(
                "Data drift KS threshold",
                min_value=0.01,
                max_value=1.0,
                value=float(mon.get("data_drift_ks_threshold", 0.1)),
                step=0.01,
                format="%.2f",
            )
            perf_drift_pct = st.number_input(
                "Performance drift threshold (%)",
                min_value=1.0,
                max_value=50.0,
                value=float(mon.get("performance_drift_pct", 5.0)),
                step=0.5,
            )
            endpoint_down_min = st.number_input(
                "Endpoint down alert (minutes)",
                min_value=1,
                max_value=60,
                value=int(mon.get("endpoint_down_minutes", 5)),
            )
            error_rate_pct = st.number_input(
                "Error rate alert threshold (%)",
                min_value=0.1,
                max_value=50.0,
                value=float(mon.get("error_rate_threshold_pct", 1.0)),
                step=0.1,
                format="%.1f",
            )

        if st.form_submit_button("💾 Save Monitoring Defaults", type="primary"):
            try:
                new_mon = {
                    "enable_data_drift": enable_drift,
                    "enable_performance_drift": enable_perf,
                    "enable_fairness_monitoring": enable_fairness,
                    "alert_destinations": alert_destinations,
                    "data_drift_ks_threshold": ks_threshold,
                    "performance_drift_pct": perf_drift_pct,
                    "endpoint_down_minutes": endpoint_down_min,
                    "error_rate_threshold_pct": error_rate_pct,
                }
                current = _load_config(svc)
                current["monitoring_defaults"] = new_mon
                current.setdefault("org_name", cfg_data.get("org_name", ""))
                current.setdefault("personas", _DEFAULT_PERSONAS)
                current.setdefault("approval_workflow_defaults", _DEFAULT_APPROVAL_WORKFLOWS)
                svc.save_installation_config(current, actor_email)
                st.success("Monitoring defaults saved.", icon="✅")
                st.rerun()
            except Exception as exc:
                st.error(f"Save failed: {exc}", icon="❌")


def _retention_tab(cfg_data: dict) -> None:
    st.markdown("### Data Retention")
    cfg = get_config()
    with st.container(border=True):
        st.markdown("**Current defaults**")
        for label, value in [
            ("MLflow experiments", "90 days"),
            ("Inference tables", "180 days"),
            ("Model artifacts", "365 days"),
            ("Audit logs", "2,555 days (7 years)"),
        ]:
            col_a, col_b = st.columns([2, 3])
            with col_a:
                st.caption(f"**{label}**")
            with col_b:
                st.caption(value)

    with st.container(border=True):
        st.markdown("**Active schema locations**")
        st.caption(f"MLOps catalog: `{cfg.catalog}`")
        st.caption(f"MLOps schema: `{cfg.schema}`")
        st.caption(f"Per-project: `{cfg.catalog}.{{project_name}}_dev/staging/prod`")

    st.info(
        "To change values, update `MLOPS_CATALOG` and `MLOPS_SCHEMA` in `.env` and re-run `python -m db.setup`.",
        icon="ℹ️",
    )


def _main() -> None:
    render_sidebar()

    st.markdown(
        page_header("Platform Administration", "Settings", "Organisation configuration, personas, and defaults."),
        unsafe_allow_html=True,
    )

    cfg_app = get_config()
    if not cfg_app.is_connected:
        st.warning("Connect to Databricks to manage settings.", icon="⚠️")
        return

    try:
        from services.state_service import StateService

        svc = StateService()
        cfg_data = _load_config(svc)
    except Exception as exc:
        st.error(f"Failed to load settings: {exc}")
        return

    actor_email = f"admin@workspace"

    if cfg_data:
        st.caption(
            f"Org: **{cfg_data.get('org_name', '—')}** · "
            f"Industry: {cfg_data.get('regulated_industry', '—')} · "
            f"Pattern: {cfg_data.get('deployment_pattern', '—')} · "
            f"Config v{cfg_data.get('config_version', 1)}"
        )
    else:
        st.info("No installation config found. Complete the Installation tab to get started.", icon="🚀")

    st.markdown("---")

    tabs = st.tabs(["Installation", "Personas & Groups", "Approval Workflows", "Monitoring Defaults", "Data Retention"])
    with tabs[0]:
        _installation_tab(cfg_data, svc, actor_email)
    with tabs[1]:
        _personas_tab(cfg_data, svc, actor_email)
    with tabs[2]:
        _approval_workflows_tab(cfg_data, svc, actor_email)
    with tabs[3]:
        _monitoring_defaults_tab(cfg_data, svc, actor_email)
    with tabs[4]:
        _retention_tab(cfg_data)


_main()
