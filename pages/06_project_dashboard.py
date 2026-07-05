"""Per-project dashboard — overview, config, governance tabs."""

from __future__ import annotations

import json

import streamlit as st

from components.theme import apply_theme, kv_row, page_header, path_chip, pill, render_sidebar
from config import get_config

st.set_page_config(page_title="Project Dashboard — MLOps", page_icon="🔬", layout="wide")
apply_theme()


def _resolve_project_id() -> str | None:
    pid = st.session_state.get("dashboard_project_id")
    if not pid:
        params = st.query_params
        pid = params.get("project_id")
    return pid


def _overview_tab(project: dict, config: dict | None) -> None:
    col1, col2, col3, col4 = st.columns(4)
    status = project.get("status", "created")
    with col1:
        st.metric("Status", status.title())
    with col2:
        st.metric("Owner", project.get("owner_email", "—"))
    with col3:
        st.metric("Team", project.get("team_name", "—"))
    with col4:
        created = str(project.get("created_timestamp", ""))[:10]
        st.metric("Created", created or "—")

    st.markdown("---")
    col_left, col_right = st.columns(2)

    with col_left:
        if project.get("project_description"):
            st.markdown(
                f'<p style="font-size:14px;color:#a9b6cc;line-height:1.55">{project["project_description"]}</p>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<span style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#64748b">Quick links</span>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        if project.get("github_repo_url"):
            st.link_button("⎇  GitHub Repo ↗", project["github_repo_url"], use_container_width=True)
        if project.get("mlflow_experiment_id"):
            cfg = get_config()
            mlflow_url = f"{cfg.databricks_host}/#mlflow/experiments/{project['mlflow_experiment_id']}"
            st.link_button("MLflow Experiment ↗", mlflow_url, use_container_width=True)

    with col_right:
        st.markdown(
            '<span style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#64748b">Infrastructure</span>',
            unsafe_allow_html=True,
        )
        st.markdown("")

        infra = [
            ("UC dev", project.get("uc_schema_dev", "—")),
            ("UC staging", project.get("uc_schema_staging", "—")),
            ("UC prod", project.get("uc_schema_prod", "—")),
            ("Secret scope", project.get("secret_scope_name", "—")),
        ]
        for label, value in infra:
            chip = (
                path_chip(value) if value and value != "—" else f'<span style="font-size:13px;color:#46546e">—</span>'
            )
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:8px 0;border-bottom:1px solid #1a2740">'
                f'<span style="font-size:12px;color:#64748b">{label}</span>{chip}</div>',
                unsafe_allow_html=True,
            )

        if config:
            raw_resp = config.get("interview_responses", "{}")
            try:
                resp = json.loads(raw_resp) if isinstance(raw_resp, str) else raw_resp
            except Exception:
                resp = {}
            st.markdown("")
            st.markdown(
                '<span style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#64748b">Model</span>',
                unsafe_allow_html=True,
            )
            st.markdown("")
            inference = config.get("inference_type", "—")
            meta_rows: list[tuple[str, str]] = [("Inference", inference)]
            if config.get("batch_frequency"):
                meta_rows.append(("Batch frequency", config["batch_frequency"]))
            if config.get("sla_latency_ms"):
                meta_rows.append(("P95 latency target", f"{config['sla_latency_ms']} ms"))
            # Framework(s) — read from interview_responses blob
            fws = resp.get("model_frameworks", [resp.get("model_type", "")])
            fws_str = ", ".join(f for f in fws if f)
            if fws_str:
                meta_rows.append(("Framework(s)", fws_str))
            for k, v in meta_rows:
                st.markdown(kv_row(k, str(v)), unsafe_allow_html=True)


def _config_tab(config: dict | None) -> None:
    if not config:
        st.info("No configuration saved yet.")
        return

    raw = config.get("interview_responses", "{}")
    try:
        responses = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        responses = {}

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("**Model Specs**")
            frameworks = responses.get("model_frameworks", [])
            if not frameworks and responses.get("model_type"):
                frameworks = [responses["model_type"]]
            frameworks_str = ", ".join(frameworks) if frameworks else "—"
            for k, v in [
                ("Inference type", responses.get("inference_type", "—")),
                ("Batch frequency", responses.get("batch_frequency", "—")),
                ("Framework(s)", frameworks_str),
            ]:
                st.markdown(kv_row(k, str(v)), unsafe_allow_html=True)
            if responses.get("sla_latency_ms"):
                st.markdown(kv_row("P95 latency target", f"{responses['sla_latency_ms']} ms"), unsafe_allow_html=True)
            if responses.get("batch_schedule"):
                tz = responses.get("retraining_timezone", "UTC")
                st.markdown(kv_row("Schedule", f"`{responses['batch_schedule']}` ({tz})"), unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("**Data**")
            datasets = responses.get("training_datasets", [])
            if not datasets and responses.get("input_data_location"):
                datasets = [responses["input_data_location"]]
            src_str = datasets[0] if len(datasets) == 1 else f"{len(datasets)} tables"
            st.markdown(kv_row("Source", src_str if src_str else "—", mono=True), unsafe_allow_html=True)
            st.markdown(
                kv_row("Target variable", responses.get("target_variable", "—"), mono=True), unsafe_allow_html=True
            )
            features = responses.get("feature_columns", [])
            st.markdown(kv_row("Features", f"{len(features)} columns"), unsafe_allow_html=True)
            clf = responses.get("data_classification", "internal")
            st.markdown(kv_row("Classification", clf), unsafe_allow_html=True)
            if responses.get("contains_pii"):
                pii = responses.get("pii_columns", [])
                st.markdown(kv_row("PII columns", ", ".join(pii), mono=True, last=True), unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("**Deployment**")
            st.markdown(kv_row("Retraining", responses.get("retraining_strategy", "—")), unsafe_allow_html=True)
            if responses.get("retraining_schedule"):
                st.markdown(kv_row("Schedule", responses["retraining_schedule"], mono=True), unsafe_allow_html=True)
            canary = responses.get("canary_percentage", 0)
            st.markdown(kv_row("Canary", f"{int(canary)}%" if canary else "disabled"), unsafe_allow_html=True)
            shadow = responses.get("shadow_mode", False)
            st.markdown(
                kv_row(
                    "Shadow mode",
                    f"{responses.get('shadow_mode_duration_days', 7)} days" if shadow else "disabled",
                    last=True,
                ),
                unsafe_allow_html=True,
            )

    with col2:
        with st.container(border=True):
            st.markdown("**Monitoring**")
            monitors = [
                k
                for k, v in [
                    ("Data drift", responses.get("monitor_data_drift")),
                    ("Performance", responses.get("monitor_performance_drift")),
                    ("Endpoint uptime", responses.get("monitor_endpoint_uptime")),
                ]
                if v
            ]
            st.markdown(kv_row("Enabled", ", ".join(monitors) or "none"), unsafe_allow_html=True)
            perf_metric = responses.get("performance_metric_type", "accuracy")
            perf_thresh = responses.get(
                "performance_alert_threshold_pct", responses.get("alert_threshold_deviation_pct", 5.0)
            )
            st.markdown(kv_row("Primary metric", f"{perf_metric} (>{perf_thresh}% drop)"), unsafe_allow_html=True)
            configs = responses.get("alert_destination_configs", [])
            if configs:
                dests = [c.get("destination", "—") for c in configs]
            else:
                dests = responses.get("alert_destinations", [])
            st.markdown(kv_row("Alerts via", ", ".join(dests) if dests else "—", last=True), unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("**Approval Gates**")
            gates_map = {
                "require_code_review": f"Code review ({responses.get('code_review_count', 2)} reviewers)",
                "require_security_scan": "Security scan",
                "require_end_to_end_test": "End-to-end test",
                "require_legal_review": "Legal review",
                "require_business_approval": "Business approval",
            }
            for key, label in gates_map.items():
                enabled = responses.get(key, True)
                icon = "✓" if enabled else "○"
                color = "#5eead4" if enabled else "#46546e"
                st.markdown(
                    f'<div style="display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid #1a2740">'
                    f"<span style=\"color:{color};font-family:'JetBrains Mono',monospace;font-size:12px\">{icon}</span>"
                    f'<span style="font-size:13px;color:{"#a9b6cc" if enabled else "#46546e"}">{label}</span></div>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                kv_row("Test coverage", f"{responses.get('testing_threshold_pct', 100)}% min", last=True),
                unsafe_allow_html=True,
            )


def _governance_tab(config: dict | None) -> None:
    if not config:
        st.info("No configuration saved yet.")
        return

    raw = config.get("interview_responses", "{}")
    try:
        responses = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        responses = {}

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Fairness Testing**")
        attrs = responses.get("fairness_attributes", [])
        # bias_test_types (new) or bias_test_type (legacy single value)
        frameworks_list = responses.get("bias_test_types", [responses.get("bias_test_type", "aif360")])
        threshold = responses.get("fairness_threshold_pct", 10)
        override_requested = responses.get("fairness_override_requested", False)

        with st.container(border=True):
            if attrs:
                st.markdown(kv_row("Protected attributes", ", ".join(attrs)), unsafe_allow_html=True)
            elif override_requested:
                st.warning("Override requested — no protected attributes declared. Requires Legal + MLOps approval.")
            else:
                st.caption("No protected attributes specified.")

            proxies = responses.get("proxy_variables", [])
            if proxies:
                proxy_cols = [p.get("column", "—") for p in proxies]
                st.markdown(kv_row("Proxy variables", ", ".join(proxy_cols)), unsafe_allow_html=True)

            st.markdown(
                kv_row("Framework(s)", ", ".join(frameworks_list) if frameworks_list else "—", mono=True),
                unsafe_allow_html=True,
            )
            st.markdown(kv_row("Max disparity", f"{threshold}%"), unsafe_allow_html=True)
            st.markdown(
                '<span style="font-size:12px;color:#64748b;display:block;padding:8px 0 4px">Tests that will run:</span>',
                unsafe_allow_html=True,
            )
            for test in ["Demographic parity", "Equalized odds", "Calibration"]:
                st.markdown(
                    f'<div style="font-size:13px;color:#a9b6cc;padding:4px 0">· {test}</div>',
                    unsafe_allow_html=True,
                )

    with col2:
        st.markdown("**Data Quality Gates**")
        required = responses.get("data_quality_required_fields", [])
        acceptable = responses.get("data_quality_acceptable_issues", [])
        with st.container(border=True):
            st.markdown(
                '<span style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#64748b">Must pass quality checks</span>',
                unsafe_allow_html=True,
            )
            for col in required or ["All columns"]:
                st.markdown(
                    f"<div style=\"font-size:13px;color:#a9b6cc;font-family:'JetBrains Mono',monospace;padding:4px 0\">· {col}</div>",
                    unsafe_allow_html=True,
                )
            if acceptable:
                st.markdown(
                    '<span style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#64748b;display:block;padding-top:12px">Issues acceptable in</span>',
                    unsafe_allow_html=True,
                )
                for col in acceptable:
                    st.markdown(
                        f"<div style=\"font-size:13px;color:#64748b;font-family:'JetBrains Mono',monospace;padding:4px 0\">· {col}</div>",
                        unsafe_allow_html=True,
                    )

    st.markdown("---")
    success_metric = responses.get("success_metric", "—")
    st.markdown(
        f'<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.2);'
        f'border-radius:8px;padding:16px 20px">'
        f'<span style="font-size:11px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:.12em;color:#7de8ff;display:block;margin-bottom:8px">Success Metric</span>'
        f'<span style="font-size:14px;color:#e2e8f0">{success_metric}</span></div>',
        unsafe_allow_html=True,
    )


def _drift_tab(project: dict, config: dict | None) -> None:
    """Field-level drift monitoring — pandas-profiling style with time series."""
    if not config:
        st.info("No configuration saved yet.")
        return

    raw = config.get("interview_responses", "{}")
    try:
        responses = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        responses = {}

    feature_columns: list[str] = responses.get("feature_columns", [])
    target_variable: str = responses.get("target_variable", "")

    # Resolve catalog + schema from project infrastructure
    uc_dev = project.get("uc_schema_dev", "")
    catalog = uc_dev.split(".")[0] if "." in uc_dev else ""
    project_schema = uc_dev.split(".", 1)[1] if "." in uc_dev else ""

    # Try to load drift and baseline data
    drift_data: dict = {}
    baseline: dict = {}
    if catalog and project_schema:
        try:
            from services.db_service import DbService

            db = DbService()
            drift_data = db.get_field_drift_data(catalog, project_schema)
            baseline = db.get_baseline_stats(catalog, project_schema)
        except Exception as exc:
            st.caption(f"Could not load monitoring data: {exc}")

    if not drift_data and not baseline:
        # No data yet — show configuration and expected schema
        st.info(
            "Drift monitoring data will appear here after the first monitoring job run. "
            "The scaffold configures a daily Databricks Workflow that computes field-level "
            "statistics and compares against the training baseline.",
            icon="ℹ️",
        )

        if feature_columns:
            st.markdown("**Features being tracked** — drift will be computed for each:")
            cols_per_row = 4
            for i in range(0, len(feature_columns), cols_per_row):
                chunk = feature_columns[i : i + cols_per_row]
                cc = st.columns(len(chunk))
                for col_widget, name in zip(cc, chunk):
                    with col_widget:
                        dtype_map: dict = st.session_state.get("step3_inferred_types", {})
                        dtype = dtype_map.get(name, "")
                        dtype_badge = (
                            f'<span style="font-size:10px;color:#64748b;margin-left:4px">{dtype}</span>'
                            if dtype
                            else ""
                        )
                        st.markdown(
                            f'<div style="background:#0f1929;border:1px solid #1a2740;border-radius:6px;'
                            f'padding:8px 12px;font-family:monospace;font-size:12px;color:#a9b6cc">'
                            f"{name}{dtype_badge}</div>",
                            unsafe_allow_html=True,
                        )
            st.markdown("")

        st.markdown("**Monitoring tables the scaffold creates:**")
        for tbl, desc in [
            (
                "monitoring_baseline",
                "Per-field training statistics: mean, std, min, max, null%, unique count, top values",
            ),
            (
                "monitoring_drift_log",
                "Daily drift metrics per field: PSI score, KS p-value, null%, n_rows, window_date",
            ),
        ]:
            st.markdown(
                f'<div style="display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #1a2740">'
                f'<code style="font-size:12px;color:#7de8ff;white-space:nowrap">{tbl}</code>'
                f'<span style="font-size:13px;color:#64748b">{desc}</span></div>',
                unsafe_allow_html=True,
            )
        return

    # ── Has data — render pandas-profiling style output ───────────────────────

    all_fields = list(baseline.keys()) or list(drift_data.keys())

    # Summary table
    st.markdown("**Field-level summary**")

    def _psi_color(psi: float | None) -> str:
        if psi is None:
            return "#64748b"
        if psi < 0.1:
            return "#5eead4"  # green — no drift
        if psi < 0.2:
            return "#f59e0b"  # amber — moderate
        return "#ef4444"  # red — significant drift

    summary_rows = []
    for field in all_fields:
        b = baseline.get(field, {})
        recent = drift_data.get(field, [{}])[-1] if drift_data.get(field) else {}
        psi = recent.get("psi_score")
        psi_str = f"{psi:.3f}" if psi is not None else "—"
        psi_col = _psi_color(psi)
        null_pct = b.get("null_pct")
        summary_rows.append(
            {
                "Field": field,
                "Mean (baseline)": f"{b.get('mean', '—'):.4g}" if b.get("mean") is not None else "—",
                "Std": f"{b.get('stddev', '—'):.4g}" if b.get("stddev") is not None else "—",
                "Min": f"{b.get('min', '—'):.4g}" if b.get("min") is not None else "—",
                "Max": f"{b.get('max', '—'):.4g}" if b.get("max") is not None else "—",
                "Null %": f"{null_pct:.1f}%" if null_pct is not None else "—",
                "Unique": str(b.get("unique_count", "—")),
                "PSI (latest)": psi_str,
                "_psi_color": psi_col,
            }
        )

    if summary_rows:
        import pandas as pd

        df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in summary_rows])
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Per-field drilldown ───────────────────────────────────────────────────
    st.markdown("")
    st.markdown("**Field drilldown** — click a field to see historical drift:")

    selected_field = st.selectbox(
        "Select field",
        options=all_fields,
        label_visibility="collapsed",
    )

    if selected_field and drift_data.get(selected_field):
        field_history = drift_data[selected_field]
        import pandas as pd

        df_field = pd.DataFrame(field_history)
        df_field["window_date"] = pd.to_datetime(df_field["window_date"])
        df_field = df_field.sort_values("window_date")

        col_stat, col_psi = st.columns(2)

        with col_stat:
            st.markdown(f"**`{selected_field}` — mean over time**")
            if "mean_value" in df_field.columns:
                st.line_chart(df_field.set_index("window_date")["mean_value"])

        with col_psi:
            st.markdown(f"**`{selected_field}` — PSI drift score**")
            if "psi_score" in df_field.columns:
                st.line_chart(df_field.set_index("window_date")["psi_score"])
                st.caption("PSI < 0.1 = no drift · 0.1–0.2 = moderate · > 0.2 = significant drift")

        # Baseline vs current comparison
        b = baseline.get(selected_field, {})
        recent = field_history[-1] if field_history else {}
        if b:
            st.markdown(f"**Baseline vs current ({recent.get('window_date', 'latest')})**")
            compare_rows = []
            for stat_key, label in [
                ("mean", "Mean"),
                ("stddev", "Std dev"),
                ("min", "Min"),
                ("max", "Max"),
                ("null_pct", "Null %"),
            ]:
                base_val = b.get(stat_key)
                curr_val = recent.get(f"{stat_key}_value")
                if base_val is not None or curr_val is not None:
                    delta = ""
                    if base_val is not None and curr_val is not None:
                        try:
                            pct_change = ((float(curr_val) - float(base_val)) / float(base_val)) * 100
                            delta = f"{pct_change:+.1f}%"
                        except (ZeroDivisionError, TypeError):
                            pass
                    compare_rows.append(
                        {
                            "Statistic": label,
                            "Baseline": f"{base_val:.4g}" if base_val is not None else "—",
                            "Current": f"{curr_val:.4g}" if curr_val is not None else "—",
                            "Change": delta,
                        }
                    )
            if compare_rows:
                import pandas as pd

                st.dataframe(pd.DataFrame(compare_rows), use_container_width=True, hide_index=True)


def _explainability_tab(project: dict, config: dict | None) -> None:
    """SHAP and LIME model explainability with LLM-generated interpretation."""
    if not config:
        st.info("No configuration saved yet.")
        return

    raw = config.get("interview_responses", "{}")
    try:
        responses = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        responses = {}

    project_name = project.get("project_name", "")
    mlflow_experiment_id = project.get("mlflow_experiment_id", "")
    target_variable = responses.get("target_variable", "the target")
    protected_classes = responses.get("fairness_attributes", [])

    # Try to load SHAP values from MLflow
    shap_values: dict[str, float] = {}
    mlflow_run_id = ""
    if mlflow_experiment_id:
        try:
            import mlflow

            mlflow.set_tracking_uri("databricks")
            runs = mlflow.search_runs(
                experiment_ids=[mlflow_experiment_id],
                filter_string="attributes.status = 'FINISHED'",
                order_by=["attributes.end_time DESC"],
                max_results=1,
            )
            if not runs.empty:
                mlflow_run_id = runs.iloc[0]["run_id"]
                # Look for shap_summary artifact
                client = mlflow.tracking.MlflowClient()
                artifacts = [a.path for a in client.list_artifacts(mlflow_run_id)]
                if "shap_summary.json" in artifacts:
                    import json as _json

                    raw_shap = client.download_artifacts(mlflow_run_id, "shap_summary.json")
                    with open(raw_shap) as f:
                        shap_values = _json.load(f)
        except Exception:
            pass

    if not shap_values:
        # No MLflow data yet — show instructions
        st.info(
            "SHAP and LIME explanations will appear here after your first model training run. "
            "The scaffold generates `src/explain.py` which logs SHAP values as MLflow artifacts "
            "automatically at the end of each training job.",
            icon="ℹ️",
        )
        st.markdown("**What the scaffold generates:**")
        for item in [
            "`shap_summary.json` — global mean |SHAP| per feature, logged as MLflow artifact",
            "`shap_waterfall_*.png` — per-prediction waterfall plots for a sample of rows",
            "`lime_local_*.json` — LIME local explanations for the same sample",
            "`explain.py` — importable function for on-demand inference-time explanations",
        ]:
            st.markdown(f"- {item}")

        st.markdown("")
        st.markdown("**Interpreting SHAP values:**")
        st.markdown(
            "- **Positive SHAP** → feature pushes prediction higher (toward the positive class)\n"
            "- **Negative SHAP** → feature pushes prediction lower\n"
            "- **Mean |SHAP|** → overall feature importance regardless of direction\n"
            "- A feature with high mean |SHAP| is influential but may push in either direction depending on its value"
        )
        return

    # ── Has SHAP data — render ────────────────────────────────────────────────

    col_chart, col_interp = st.columns([2, 3])

    with col_chart:
        st.markdown("**Global feature importance (mean |SHAP|)**")
        import pandas as pd

        sorted_shap = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)[:15]
        df_shap = pd.DataFrame(sorted_shap, columns=["Feature", "Mean |SHAP|"])
        df_shap = df_shap.sort_values("Mean |SHAP|")
        st.bar_chart(df_shap.set_index("Feature"))

        if mlflow_run_id:
            cfg = get_config()
            run_url = f"{cfg.databricks_host}/#mlflow/experiments/{mlflow_experiment_id}/runs/{mlflow_run_id}"
            st.link_button("View MLflow run ↗", run_url)

    with col_interp:
        st.markdown("**LLM Interpretation**")
        interp_key = f"shap_interp_{mlflow_run_id}"
        cached_interp = st.session_state.get(interp_key, "")

        if cached_interp:
            st.markdown(cached_interp)
        else:
            st.caption(
                "Click 'Interpret' to generate a plain-language explanation of these feature importances "
                "tailored for business stakeholders."
            )

        if st.button("Generate interpretation", type="primary" if not cached_interp else "secondary"):
            with st.spinner("Generating interpretation via LLM..."):
                try:
                    from services.ai_service import AiService

                    interp = AiService().interpret_shap(
                        shap_values=dict(sorted_shap),
                        model_name=project_name,
                        target_variable=target_variable,
                        protected_classes=protected_classes or None,
                    )
                    st.session_state[interp_key] = interp
                    st.rerun()
                except Exception as exc:
                    st.error(f"Interpretation failed: {exc}")

    # ── SHAP guidance ─────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("How to interpret SHAP values"):
        st.markdown(
            "**SHAP (SHapley Additive exPlanations)** measures how much each feature contributed to a "
            "specific prediction compared to the model's average prediction.\n\n"
            "| Value | Meaning |\n"
            "|-------|----------|\n"
            "| Positive SHAP | Feature pushes prediction **higher** (toward positive class) |\n"
            "| Negative SHAP | Feature pushes prediction **lower** |\n"
            "| Mean \\|SHAP\\| | Overall importance — larger = more influential |\n\n"
            "**Fairness note:** If a protected class attribute (or a known proxy) appears in the top 5 "
            "features by importance, this warrants review — it may indicate the model is relying on "
            "demographic signals even if those columns weren't explicitly included as training features."
        )

    with st.expander("About LIME"):
        st.markdown(
            "**LIME (Local Interpretable Model-agnostic Explanations)** explains individual predictions "
            "by fitting a simple linear model around the specific data point being predicted. "
            "Unlike SHAP (global), LIME shows why the model made *this specific prediction* for *this row*.\n\n"
            "LIME artifacts are logged per-run in `lime_local_*.json`. To generate a LIME explanation "
            "for a specific row in production, call `explain.lime_explain(row_dict)` from the "
            "generated `src/explain.py`."
        )


def _main() -> None:
    project_id = _resolve_project_id()

    if not project_id:
        render_sidebar()
        st.markdown(page_header("Project", "Dashboard", "No project selected."), unsafe_allow_html=True)
        st.warning("No project selected. Go to [Projects](/01_projects) and open one.")
        if st.button("← Back to Projects"):
            st.switch_page("pages/01_projects.py")
        return

    cfg = get_config()
    if not cfg.is_connected:
        render_sidebar()
        st.warning("Not connected to Databricks.", icon="⚠️")
        return

    try:
        from services.state_service import StateService

        svc = StateService()
        project = svc.get_project(project_id)
        if not project:
            render_sidebar()
            st.error(f"Project `{project_id}` not found.")
            return
        config = svc.get_latest_project_config(project_id)
    except Exception as exc:
        render_sidebar()
        st.error(f"Failed to load project: {exc}")
        return

    render_sidebar()

    status = project.get("status", "created")
    st.markdown(
        page_header(
            project.get("team_name", "Project"),
            project["project_name"],
            f"Owner: {project.get('owner_email', '—')}",
        ),
        unsafe_allow_html=True,
    )

    pill_col, *_ = st.columns([1, 5])
    with pill_col:
        st.markdown(pill(status), unsafe_allow_html=True)

    if project.get("github_repo_url"):
        st.link_button("⎇  GitHub ↗", project["github_repo_url"])

    st.markdown("---")

    tab_overview, tab_config, tab_governance, tab_drift, tab_explain = st.tabs(
        ["Overview", "Configuration", "Governance", "Drift Monitoring", "Explainability"]
    )
    with tab_overview:
        _overview_tab(project, config)
    with tab_config:
        _config_tab(config)
    with tab_governance:
        _governance_tab(config)
    with tab_drift:
        _drift_tab(project, config)
    with tab_explain:
        _explainability_tab(project, config)


_main()
