"""Data Contract Manager — define, edit, and version column schemas per project."""

from __future__ import annotations

import json

import streamlit as st

from components.theme import apply_theme, page_header, pii_badge, render_sidebar, tag
from config import get_config

st.set_page_config(page_title="Data Contracts — MLOps", page_icon="📋", layout="wide")
apply_theme()

_PII_LEVELS = ["none", "low", "medium", "high"]
_CLASSIFICATIONS = ["public", "internal", "sensitive", "restricted"]
_DATA_TYPES = [
    "string",
    "int",
    "bigint",
    "float",
    "double",
    "boolean",
    "date",
    "timestamp",
    "array<string>",
    "map<string,string>",
    "struct",
]
_CONTRACT_TYPES = ["input_data", "output_data", "feature_table", "staging_table"]


def _llm_suggest_columns(table_path: str, existing_columns: list[dict]) -> list[dict]:
    cfg = get_config()
    try:
        import mlflow.deployments

        client = mlflow.deployments.get_deploy_client("databricks")
        col_info = [{"name": c["name"], "type": c["data_type"]} for c in existing_columns]
        prompt = f"""You are a data governance expert. Given these table columns from '{table_path}':
{json.dumps(col_info, indent=2)}

For each column return a JSON array where each item has:
- "name": column name (unchanged)
- "description": concise 1-sentence description
- "pii_level": one of "none", "low", "medium", "high"
- "data_classification": one of "public", "internal", "sensitive", "restricted"
- "is_fairness_attribute": true if protected demographic attribute, else false

Return ONLY the JSON array, no explanation."""
        response = client.predict(
            endpoint=cfg.llm_endpoint,
            inputs={"messages": [{"role": "user", "content": prompt}]},
        )
        content = response["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        suggestions = json.loads(content)
        suggestion_map = {s["name"]: s for s in suggestions}
        return [
            {
                **col,
                **{
                    k: suggestion_map.get(col["name"], {}).get(k, col.get(k))
                    for k in ("description", "pii_level", "data_classification", "is_fairness_attribute")
                },
            }
            for col in existing_columns
        ]
    except Exception as exc:
        st.warning(f"LLM suggestions unavailable: {exc}", icon="⚠️")
        return existing_columns


def _render_column_editor(columns: list[dict], key_prefix: str) -> list[dict]:
    updated = []
    for i, col in enumerate(columns):
        pii = col.get("pii_level", "none")
        pii_html = pii_badge(pii)
        with st.expander(
            f"`{col.get('name', '—')}` — {col.get('data_type', 'string')}",
            expanded=False,
        ):
            st.markdown(pii_html, unsafe_allow_html=True)
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                name = st.text_input("Column name", value=col.get("name", ""), key=f"{key_prefix}_name_{i}")
                data_type = st.selectbox(
                    "Type",
                    _DATA_TYPES,
                    index=_DATA_TYPES.index(col.get("data_type", "string"))
                    if col.get("data_type") in _DATA_TYPES
                    else 0,
                    key=f"{key_prefix}_type_{i}",
                )
                description = st.text_input(
                    "Description", value=col.get("description", ""), key=f"{key_prefix}_desc_{i}"
                )
            with c2:
                pii_level = st.selectbox(
                    "PII level",
                    _PII_LEVELS,
                    index=_PII_LEVELS.index(col.get("pii_level", "none")),
                    key=f"{key_prefix}_pii_{i}",
                )
                classification = st.selectbox(
                    "Classification",
                    _CLASSIFICATIONS,
                    index=_CLASSIFICATIONS.index(col.get("data_classification", "internal")),
                    key=f"{key_prefix}_class_{i}",
                )
            with c3:
                is_nullable = st.checkbox("Nullable", value=col.get("is_nullable", True), key=f"{key_prefix}_null_{i}")
                is_fairness = st.checkbox(
                    "Fairness attr", value=col.get("is_fairness_attribute", False), key=f"{key_prefix}_fair_{i}"
                )
                is_required_quality = st.checkbox(
                    "Quality required", value=col.get("is_required_for_quality", True), key=f"{key_prefix}_qreq_{i}"
                )

            with st.expander("Quality rules", expanded=False):
                qr = col.get("quality_rules", {})
                qc1, qc2 = st.columns(2)
                with qc1:
                    max_null_pct = st.number_input(
                        "Max null %",
                        min_value=0.0,
                        max_value=100.0,
                        value=float(qr.get("null_check", {}).get("max_null_pct", 5.0)),
                        key=f"{key_prefix}_null_pct_{i}",
                    )
                with qc2:
                    must_be_unique = st.checkbox(
                        "Must be unique",
                        value=qr.get("uniqueness_check", {}).get("must_be_unique", False),
                        key=f"{key_prefix}_unique_{i}",
                    )

            updated.append(
                {
                    "name": name,
                    "data_type": data_type,
                    "description": description,
                    "is_nullable": is_nullable,
                    "pii_level": pii_level,
                    "data_classification": classification,
                    "is_fairness_attribute": is_fairness,
                    "is_required_for_quality": is_required_quality,
                    "monitor_for_drift": True,
                    "quality_rules": {
                        "null_check": {"max_null_pct": max_null_pct},
                        **({"uniqueness_check": {"must_be_unique": True}} if must_be_unique else {}),
                    },
                }
            )
    return updated


def _new_contract_form(project_id: str, owner_email: str) -> None:
    st.markdown("### New Contract")
    c1, c2 = st.columns(2)
    with c1:
        contract_name = st.text_input("Contract name *", placeholder="training_input")
        contract_type = st.selectbox("Contract type *", _CONTRACT_TYPES)
    with c2:
        uc_path = st.text_input("UC table path", placeholder="catalog.schema.table_name")
        purpose = st.text_input("Purpose", placeholder="Training data for churn model")

    if "new_contract_columns" not in st.session_state:
        st.session_state["new_contract_columns"] = []

    st.markdown("---")
    st.markdown("**Columns**")

    col_add, col_llm = st.columns([1, 3])
    with col_add:
        if st.button("+ Add column"):
            st.session_state["new_contract_columns"].append(
                {
                    "name": "",
                    "data_type": "string",
                    "description": "",
                    "is_nullable": True,
                    "pii_level": "none",
                    "data_classification": "internal",
                    "is_fairness_attribute": False,
                    "is_required_for_quality": True,
                    "monitor_for_drift": True,
                    "quality_rules": {"null_check": {"max_null_pct": 5.0}},
                }
            )
            st.rerun()
    with col_llm:
        if uc_path and st.button("✨ Suggest with LLM"):
            if st.session_state["new_contract_columns"]:
                with st.spinner("Calling foundation model…"):
                    st.session_state["new_contract_columns"] = _llm_suggest_columns(
                        uc_path, st.session_state["new_contract_columns"]
                    )
                st.rerun()
            else:
                st.warning("Add columns first, then use LLM to enrich them.")

    if st.session_state["new_contract_columns"]:
        updated_cols = _render_column_editor(st.session_state["new_contract_columns"], "new")
        st.session_state["new_contract_columns"] = updated_cols

    st.markdown("---")
    if st.button("💾 Save Contract", type="primary", disabled=not contract_name):
        try:
            from services.state_service import StateService

            svc = StateService()
            contract_id = svc.create_contract(
                project_id=project_id,
                contract_name=contract_name,
                contract_type=contract_type,
                uc_path=uc_path,
                owner_email=owner_email,
                purpose=purpose,
            )
            if st.session_state["new_contract_columns"]:
                svc.save_contract_columns(contract_id, st.session_state["new_contract_columns"], owner_email)
            st.success(f"Contract `{contract_name}` saved!", icon="✅")
            st.session_state.pop("new_contract_columns", None)
            st.session_state.pop("show_new_contract_form", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to save contract: {exc}", icon="❌")


def _existing_contract(contract: dict, owner_email: str) -> None:
    from services.state_service import StateService

    svc = StateService()
    contract_id = contract["contract_id"]
    columns = svc.get_contract_columns(contract_id)

    ctype = contract.get("contract_type", "input_data")
    tag_html = tag(ctype.replace("_", " "), ctype)
    validated = contract.get("is_validated")
    v_html = (
        '<span style="font-size:11px;font-weight:600;color:#5eead4">✓ Validated</span>'
        if validated
        else '<span style="font-size:11px;color:#64748b">⏳ Draft</span>'
    )

    st.markdown(
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px">'
        f'<div style="display:flex;flex-direction:column;gap:6px">'
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<span style="font-size:17px;font-weight:600;color:#f4f8ff">{contract["contract_name"]}</span>'
        f"{tag_html}"
        f"<span style=\"font-size:12px;color:#46546e;font-family:'JetBrains Mono',monospace\">"
        f"v{contract.get('contract_version', 1)}</span></div>"
        f"{"<span style='font-size:12px;color:#64748b;font-family:JetBrains Mono,monospace'>" + contract['uc_path'] + '</span>' if contract.get('uc_path') else ''}"
        f"{"<span style='font-size:13px;color:#64748b'>" + contract.get('purpose', '') + '</span>' if contract.get('purpose') else ''}"
        f"</div><div>{v_html}</div></div>",
        unsafe_allow_html=True,
    )

    if not columns:
        st.caption("No columns defined yet.")
    else:
        # Render summary with PII badges
        header_html = (
            '<div style="display:grid;grid-template-columns:1fr 100px 80px 80px;gap:8px;'
            "padding:8px 12px;background:#070a12;border-radius:5px 5px 0 0;"
            "font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#46546e;"
            'border:1px solid #1a2740;border-bottom:1px solid #2f4368">'
            "<span>Column</span><span>Type</span><span>PII</span><span>Quality</span></div>"
        )
        rows_html = ""
        for c in columns:
            pii = c.get("pii_level", "none")
            pii_html = pii_badge(pii)
            req = "Required" if c.get("is_required_for_quality") else "Optional"
            req_color = "#5eead4" if c.get("is_required_for_quality") else "#64748b"
            rows_html += (
                f'<div style="display:grid;grid-template-columns:1fr 100px 80px 80px;gap:8px;'
                f"padding:10px 12px;border:1px solid #1a2740;border-top:none;"
                f'transition:background 120ms ease" '
                f"onmouseover=\"this.style.background='#161f33'\" "
                f"onmouseout=\"this.style.background='transparent'\">"
                f'<span style="font-size:13px;color:#e2e8f0;font-weight:500;'
                f"font-family:'JetBrains Mono',monospace\">{c['column_name']}</span>"
                f"<span style=\"font-size:12px;color:#64748b;font-family:'JetBrains Mono',monospace\">"
                f"{c.get('data_type', '—')}</span>"
                f"<span>{pii_html}</span>"
                f'<span style="font-size:11px;color:{req_color}">{req}</span>'
                f"</div>"
            )
        st.markdown(header_html + rows_html, unsafe_allow_html=True)
        st.markdown("")

    key = f"edit_{contract_id}"
    if st.button("✏️ Edit columns", key=key):
        st.session_state[f"editing_{contract_id}"] = True

    if st.session_state.get(f"editing_{contract_id}"):
        st.markdown("**Edit columns**")
        edit_cols = st.session_state.get(
            f"edit_cols_{contract_id}",
            [
                {
                    "name": c["column_name"],
                    "data_type": c.get("data_type", "string"),
                    "description": c.get("column_description", ""),
                    "is_nullable": c.get("is_nullable", True),
                    "pii_level": c.get("pii_level", "none"),
                    "data_classification": c.get("data_classification", "internal"),
                    "is_fairness_attribute": c.get("is_fairness_attribute", False),
                    "is_required_for_quality": c.get("is_required_for_quality", True),
                    "monitor_for_drift": c.get("monitor_for_drift", True),
                    "quality_rules": json.loads(c.get("quality_rules") or "{}"),
                }
                for c in columns
            ],
        )

        if st.button("+ Add column", key=f"add_{contract_id}"):
            edit_cols.append(
                {
                    "name": "",
                    "data_type": "string",
                    "description": "",
                    "is_nullable": True,
                    "pii_level": "none",
                    "data_classification": "internal",
                    "is_fairness_attribute": False,
                    "is_required_for_quality": True,
                    "monitor_for_drift": True,
                    "quality_rules": {"null_check": {"max_null_pct": 5.0}},
                }
            )
            st.session_state[f"edit_cols_{contract_id}"] = edit_cols
            st.rerun()

        updated = _render_column_editor(edit_cols, f"edit_{contract_id}")
        st.session_state[f"edit_cols_{contract_id}"] = updated

        save_col, cancel_col = st.columns(2)
        with save_col:
            if st.button("💾 Save changes", key=f"save_{contract_id}", type="primary"):
                try:
                    svc.save_contract_columns(contract_id, updated, owner_email)
                    svc.bump_contract_version(contract_id, owner_email, "column edits")
                    st.success("Contract updated.", icon="✅")
                    for k in [f"editing_{contract_id}", f"edit_cols_{contract_id}"]:
                        st.session_state.pop(k, None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Save failed: {exc}", icon="❌")
        with cancel_col:
            if st.button("Cancel", key=f"cancel_{contract_id}"):
                for k in [f"editing_{contract_id}", f"edit_cols_{contract_id}"]:
                    st.session_state.pop(k, None)
                st.rerun()


def _main() -> None:
    cfg = get_config()
    if not cfg.is_connected:
        render_sidebar()
        st.warning("Connect to Databricks to manage data contracts.", icon="⚠️")
        return

    try:
        from services.state_service import StateService

        svc = StateService()
        projects = svc.list_projects()
    except Exception as exc:
        render_sidebar()
        st.error(f"Failed to load projects: {exc}")
        return

    if not projects:
        render_sidebar()
        st.markdown(
            page_header("Schema Management", "Data Contracts", "Create a project first."), unsafe_allow_html=True
        )
        return

    names = [p["project_name"] for p in projects]
    default = st.session_state.get("contracts_project_name", names[0])
    idx = names.index(default) if default in names else 0

    render_sidebar(
        extra_html=(
            '<div style="margin-top:16px;padding-top:16px;border-top:1px solid #1a2740">'
            '<p style="font-size:11px;font-weight:600;text-transform:uppercase;'
            'letter-spacing:0.12em;color:#46546e;padding:4px 0 8px">Contract scope</p>'
            "</div>"
        )
    )
    with st.sidebar:
        selected_name = st.selectbox("Project", names, index=idx, label_visibility="collapsed")
        st.session_state["contracts_project_name"] = selected_name

    project = next((p for p in projects if p["project_name"] == selected_name), None)
    if not project:
        return

    project_id = project["project_id"]
    owner_email = project.get("owner_email", "unknown")

    st.markdown(
        page_header("Schema Management", "Data Contracts", f"Column schemas and quality rules for {selected_name}."),
        unsafe_allow_html=True,
    )

    col_title, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("+ New Contract", type="primary", use_container_width=True):
            st.session_state["show_new_contract_form"] = True
            st.session_state.pop("new_contract_columns", None)

    if st.session_state.get("show_new_contract_form"):
        with st.container(border=True):
            _new_contract_form(project_id, owner_email)
        st.markdown("---")

    try:
        contracts = svc.list_contracts_for_project(project_id)
    except Exception as exc:
        st.error(f"Failed to load contracts: {exc}")
        return

    if not contracts:
        st.markdown(
            """<div style="display:flex;flex-direction:column;align-items:center;gap:12px;
            padding:64px 24px;text-align:center;border:1px dashed #2f4368;
            border-radius:8px;background:#070a12">
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">No data contracts yet</div>
  <div style="font-size:13px;color:#64748b;max-width:380px">
    Click <strong>+ New Contract</strong> to define the schema for your training data,
    features, or model outputs.</div>
</div>""",
            unsafe_allow_html=True,
        )
        return

    st.caption(f"{len(contracts)} contract{'s' if len(contracts) != 1 else ''}")
    for contract in contracts:
        with st.container(border=True):
            _existing_contract(contract, owner_email)


_main()
