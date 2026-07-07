"""New Project — 7-step interview wizard.

Steps follow the Process Map (canonical order):
  1. Basic Info      — name, problem, success metric, team, owner
  2. Model Specs     — inference type, latency/QPS, model framework(s), batch schedule
  3. Data Specs      — datasets, target, features, PII, classification
  4. Governance      — fairness (always on), proxy vars, quality gates, justifications
  5. Deployment      — retraining, per-field drift, rollback triggers, canary, shadow
  6. Monitoring      — performance metric, drift, alerts with destination details
  7. Approval Gates  — reviewer count and coverage (all gates locked on)
  →  Review & Create
"""

from __future__ import annotations

import re

import streamlit as st

from components.theme import apply_theme, page_header, render_sidebar, wizard_steps
from config import get_config
from services import interview_service as iv

st.set_page_config(page_title="New Project — MLOps", page_icon="➕", layout="wide")
apply_theme()

_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Anchorage",
    "America/Honolulu",
    "UTC",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Asia/Kolkata",
    "Australia/Sydney",
]

_DATA_CLASSIFICATIONS = ["public", "internal", "sensitive", "restricted"]

_ROLLBACK_TRIGGERS = iv.ROLLBACK_TRIGGER_OPTIONS


# ── Helpers ───────────────────────────────────────────────────────────────────


def _cron_builder(
    key_prefix: str,
    prev_schedule: str,
    prev_tz: str,
    frequency: str | None = None,
) -> tuple[str, str]:
    """Render a schedule builder. frequency drives which controls appear.

    Args:
        key_prefix: Unique prefix for all widget keys.
        prev_schedule: Previously saved cron string (used as default).
        prev_tz: Previously saved timezone string.
        frequency: If provided (from batch_frequency dropdown), skip the
                   internal frequency selector and show controls for this
                   specific frequency. If None, show a full selector.

    Returns:
        (cron_string, timezone)
    """
    _DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    _ORDINALS = ["First", "Second", "Third", "Fourth", "Last"]
    _ORDINAL_RANGES = {"First": "1-7", "Second": "8-14", "Third": "15-21", "Fourth": "22-28", "Last": "22-28"}
    _FREQ_DISPLAY_OPTIONS = [
        "Hourly",
        "Daily",
        "Weekdays (Mon–Fri)",
        "Weekly",
        "Monthly",
        "Quarterly",
        "Custom",
    ]
    _INTERNAL_TO_DISPLAY = {
        "hourly": "Hourly",
        "daily": "Daily",
        "weekly": "Weekly",
        "monthly": "Monthly",
        "quarterly": "Quarterly",
    }

    tz_idx = _TIMEZONES.index(prev_tz) if prev_tz in _TIMEZONES else 0
    cron = prev_schedule or "0 2 * * *"

    # Determine which frequency to render
    if frequency is not None:
        freq = _INTERNAL_TO_DISPLAY.get(frequency, "Daily")
    else:
        freq = st.selectbox(
            "Frequency",
            _FREQ_DISPLAY_OPTIONS,
            key=f"{key_prefix}_freq",
        )

    # Controls column + timezone column — no help= on text inputs to avoid (?) misalignment
    col_ctrl, col_tz_col = st.columns([4, 2])

    with col_tz_col:
        st.markdown(" ")  # align with first row of controls
        timezone = st.selectbox("Timezone", _TIMEZONES, index=tz_idx, key=f"{key_prefix}_tz")

    with col_ctrl:
        if freq == "Hourly":
            prev_min = int(cron.split()[0]) if cron.split() and cron.split()[0].isdigit() else 0
            minute = st.number_input(
                "Run at minute (0–59)",
                min_value=0,
                max_value=59,
                value=prev_min,
                step=5,
                key=f"{key_prefix}_min",
            )
            cron = f"{minute} * * * *"

        elif freq in ("Daily", "Weekdays (Mon–Fri)"):
            parts = cron.split()
            prev_min = int(parts[0]) if parts and parts[0].isdigit() else 0
            prev_hr = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
            c1, c2 = st.columns(2)
            with c1:
                hour = st.number_input(
                    "Hour (0–23)", min_value=0, max_value=23, value=prev_hr, key=f"{key_prefix}_hour"
                )
            with c2:
                minute = st.number_input(
                    "Minute (0–59)", min_value=0, max_value=59, value=prev_min, step=5, key=f"{key_prefix}_min"
                )
            cron = f"{minute} {hour} * * *" if freq == "Daily" else f"{minute} {hour} * * 1-5"

        elif freq == "Weekly":
            parts = cron.split()
            prev_min = int(parts[0]) if parts and parts[0].isdigit() else 0
            prev_hr = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
            c1, c2, c3 = st.columns(3)
            with c1:
                dow = st.selectbox("Day of week", _DOW, index=1, key=f"{key_prefix}_dow")
            with c2:
                hour = st.number_input(
                    "Hour (0–23)", min_value=0, max_value=23, value=prev_hr, key=f"{key_prefix}_hour"
                )
            with c3:
                minute = st.number_input(
                    "Minute (0–59)", min_value=0, max_value=59, value=prev_min, step=5, key=f"{key_prefix}_min"
                )
            cron = f"{minute} {hour} * * {_DOW.index(dow)}"

        elif freq == "Monthly":
            day_mode = st.radio(
                "Day selection",
                ["By date", "By day of week"],
                horizontal=True,
                key=f"{key_prefix}_daymode",
            )
            parts = cron.split()
            prev_min = int(parts[0]) if parts and parts[0].isdigit() else 0
            prev_hr = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
            if day_mode == "By date":
                c1, c2, c3 = st.columns(3)
                with c1:
                    dom = st.number_input(
                        "Day of month (1–28)", min_value=1, max_value=28, value=1, key=f"{key_prefix}_dom"
                    )
                with c2:
                    hour = st.number_input(
                        "Hour (0–23)", min_value=0, max_value=23, value=prev_hr, key=f"{key_prefix}_hour"
                    )
                with c3:
                    minute = st.number_input(
                        "Minute (0–59)", min_value=0, max_value=59, value=prev_min, step=5, key=f"{key_prefix}_min"
                    )
                cron = f"{minute} {hour} {dom} * *"
            else:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    ordinal = st.selectbox("Which", _ORDINALS, key=f"{key_prefix}_ord")
                with c2:
                    dow = st.selectbox("Weekday", _DOW[1:], key=f"{key_prefix}_dow")
                with c3:
                    hour = st.number_input(
                        "Hour (0–23)", min_value=0, max_value=23, value=prev_hr, key=f"{key_prefix}_hour"
                    )
                with c4:
                    minute = st.number_input(
                        "Minute (0–59)", min_value=0, max_value=59, value=prev_min, step=5, key=f"{key_prefix}_min"
                    )
                day_range = _ORDINAL_RANGES.get(ordinal, "1-7")
                dow_num = _DOW.index(dow)
                cron = f"{minute} {hour} {day_range} * {dow_num}"
                st.caption(f"Approximation: '{ordinal} {dow}' maps to days {day_range} in standard cron.")

        elif freq == "Quarterly":
            _QUARTER_MONTHS = {
                "1st month of quarter (Jan / Apr / Jul / Oct)": "1,4,7,10",
                "2nd month of quarter (Feb / May / Aug / Nov)": "2,5,8,11",
                "3rd month of quarter (Mar / Jun / Sep / Dec)": "3,6,9,12",
            }
            month_label = st.selectbox("Month in quarter", list(_QUARTER_MONTHS.keys()), key=f"{key_prefix}_miq")
            months = _QUARTER_MONTHS[month_label]
            day_mode = st.radio(
                "Day selection",
                ["By date", "By day of week"],
                horizontal=True,
                key=f"{key_prefix}_daymode",
            )
            parts = cron.split()
            prev_min = int(parts[0]) if parts and parts[0].isdigit() else 0
            prev_hr = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
            if day_mode == "By date":
                c1, c2, c3 = st.columns(3)
                with c1:
                    dom = st.number_input(
                        "Day of month (1–28)", min_value=1, max_value=28, value=1, key=f"{key_prefix}_dom"
                    )
                with c2:
                    hour = st.number_input(
                        "Hour (0–23)", min_value=0, max_value=23, value=prev_hr, key=f"{key_prefix}_hour"
                    )
                with c3:
                    minute = st.number_input(
                        "Minute (0–59)", min_value=0, max_value=59, value=prev_min, step=5, key=f"{key_prefix}_min"
                    )
                cron = f"{minute} {hour} {dom} {months} *"
            else:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    ordinal = st.selectbox("Which", _ORDINALS, key=f"{key_prefix}_ord")
                with c2:
                    dow = st.selectbox("Weekday", _DOW[1:], key=f"{key_prefix}_dow")
                with c3:
                    hour = st.number_input(
                        "Hour (0–23)", min_value=0, max_value=23, value=prev_hr, key=f"{key_prefix}_hour"
                    )
                with c4:
                    minute = st.number_input(
                        "Minute (0–59)", min_value=0, max_value=59, value=prev_min, step=5, key=f"{key_prefix}_min"
                    )
                day_range = _ORDINAL_RANGES.get(ordinal, "1-7")
                dow_num = _DOW.index(dow)
                cron = f"{minute} {hour} {day_range} {months} {dow_num}"

        else:  # Custom — no help= parameter to avoid (?) alignment issues
            cron = st.text_input(
                "Cron expression (minute hour day month weekday)",
                value=prev_schedule or "0 2 * * *",
                key=f"{key_prefix}_cron",
            )
            st.caption("Format: `minute hour day-of-month month day-of-week` — [crontab.guru](https://crontab.guru)")

    st.caption(f"Generated schedule: `{cron}` ({timezone})")
    return cron, timezone


def _progress_header(step: int, title: str) -> None:
    pct = step / (iv.TOTAL_STEPS + 1)
    st.markdown(
        f"""
<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:8px">
  <span style="font-size:11px;font-weight:600;text-transform:uppercase;
               letter-spacing:0.12em;color:#7de8ff">Guided Setup</span>
  <h1 style="font-size:30px;font-weight:700;letter-spacing:-0.01em;
             line-height:1.15;color:#f4f8ff;margin:0">New ML Project</h1>
  <span style="font-size:13px;color:#64748b">Step {step} of {iv.TOTAL_STEPS} — {title}</span>
</div>""",
        unsafe_allow_html=True,
    )
    st.progress(pct)
    st.markdown("---")


def _nav(step: int, errors: list[str], step_data: dict) -> None:
    st.markdown("---")
    col_back, col_spacer, col_next = st.columns([1, 4, 1])
    with col_back:
        if step > 1:
            if st.button("← Back", use_container_width=True):
                iv.set_step(st.session_state, step - 1)
                st.rerun()
    with col_next:
        label = "Next →" if step < iv.TOTAL_STEPS else "Review →"
        btn_type = "primary" if not errors else "secondary"
        if st.button(label, use_container_width=True, type=btn_type):
            if errors:
                for e in errors:
                    st.error(e)
            else:
                iv.save_step_data(st.session_state, step, step_data)
                iv.set_step(st.session_state, step + 1)
                st.rerun()


def _validation_box(errors: list[str]) -> None:
    if errors:
        for e in errors:
            st.error(e, icon="❌")


# ── Step 1: Basic Info ────────────────────────────────────────────────────────


def _step1() -> None:
    _progress_header(1, "Basic Info")

    prev = iv.get_step_data(st.session_state, 1)

    _name_key = "p1_project_name"

    def _sanitize_name() -> None:
        raw = st.session_state.get(_name_key, "")
        cleaned = re.sub(r"[^a-z0-9]", "_", raw.strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        st.session_state[_name_key] = cleaned

    if _name_key not in st.session_state:
        st.session_state[_name_key] = prev.get("project_name", "")

    project_name = st.text_input(
        "Model name *",
        key=_name_key,
        on_change=_sanitize_name,
        placeholder="customer_churn_prediction",
        help=(
            "Auto-corrected to lowercase alphanumeric + underscores on each keystroke. "
            "Becomes your GitHub repo name and UC schema prefix."
        ),
    )

    problem_statement = st.text_area(
        "What business problem does it solve? *",
        value=prev.get("problem_statement", ""),
        placeholder="Identify customers likely to churn in next 30 days to enable proactive retention campaigns.",
        height=100,
        help="Minimum 20 characters. Used in model card and documentation.",
    )

    success_metric = st.text_area(
        "How do you measure success? *",
        value=prev.get("success_metric", ""),
        placeholder="Achieve AUC-ROC ≥ 0.85 on holdout validation set with <10% disparity across demographic groups.",
        height=80,
        help="Minimum 20 characters. Becomes the primary acceptance criterion in CI.",
    )

    # Load teams from installation config; fall back to free text on connection failure
    _org_teams: list[str] = []
    try:
        from services.db_service import DbService

        if get_config().is_connected:
            _org_teams = DbService().get_org_teams()
    except Exception:
        pass

    if _org_teams:
        _team_options = _org_teams + ["Other (enter manually)"]
        _prev_team = prev.get("team_name", "")
        _team_idx = _team_options.index(_prev_team) if _prev_team in _team_options else 0
        _team_sel = st.selectbox(
            "Team *",
            _team_options,
            index=_team_idx,
            help="Teams loaded from your org's installation config. Choose 'Other' to enter a custom name.",
        )
        if _team_sel == "Other (enter manually)":
            team_name = st.text_input(
                "Custom team name",
                value="" if _prev_team in _org_teams else _prev_team,
                placeholder="retention_team",
            )
        else:
            team_name = _team_sel
    else:
        team_name = st.text_input(
            "Team *",
            value=prev.get("team_name", ""),
            placeholder="retention_team",
            help="The team that owns this model. Used for GitHub CODEOWNERS, alert routing, and cost tagging.",
        )

    owner_email = st.text_input(
        "Primary owner email *",
        value=prev.get("owner_email", ""),
        placeholder="alice@company.com",
        help="Primary contact for monitoring alerts and approval requests.",
    )

    data = {
        "project_name": project_name,  # already sanitized by on_change callback
        "problem_statement": problem_statement.strip(),
        "success_metric": success_metric.strip(),
        "team_name": team_name.strip(),
        "owner_email": owner_email.strip().lower(),
    }
    errors = iv.validate_step(1, data) if any(data.values()) else []
    _validation_box(errors)
    _nav(1, errors, data)


# ── Step 2: Model Specs ───────────────────────────────────────────────────────


def _step2() -> None:
    _progress_header(2, "Model Specs")

    prev = iv.get_step_data(st.session_state, 2)

    st.markdown("**How will this model make predictions?**")
    inference_type = st.radio(
        "Inference type *",
        options=["batch", "real_time", "both"],
        format_func=lambda x: {
            "batch": "Batch — score large datasets on a schedule",
            "real_time": "Real-time — REST API with low-latency requirements",
            "both": "Both — batch jobs and a real-time endpoint",
        }[x],
        index=["batch", "real_time", "both"].index(prev.get("inference_type", "batch")),
        label_visibility="collapsed",
    )

    data: dict = {"inference_type": inference_type}

    # Batch options
    if inference_type in ("batch", "both"):
        st.markdown("")
        st.markdown("**Batch schedule**")
        _batch_freq_opts = ["hourly", "daily", "weekly", "monthly", "quarterly"]
        _prev_freq = prev.get("batch_frequency", "daily")
        if _prev_freq not in _batch_freq_opts:
            _prev_freq = "daily"
        batch_frequency = st.selectbox(
            "Batch frequency *",
            _batch_freq_opts,
            index=_batch_freq_opts.index(_prev_freq),
            help="How often should the batch job run? Used to configure the Databricks Workflow trigger.",
        )
        data["batch_frequency"] = batch_frequency

        with st.expander("Configure schedule", expanded=True):
            cron, tz = _cron_builder(
                "batch",
                prev.get("batch_schedule", "0 2 * * *"),
                prev.get("retraining_timezone", "America/New_York"),
                frequency=batch_frequency,
            )
            data["batch_schedule"] = cron
            data["retraining_timezone"] = tz

    # Real-time options
    if inference_type in ("real_time", "both"):
        st.markdown("")
        st.markdown("**Service Level Agreement**")
        col1, col2, col3 = st.columns(3)
        with col1:
            sla_latency = st.number_input(
                "Target P95 latency (ms) *",
                min_value=50,
                max_value=10000,
                value=int(prev.get("sla_latency_ms", 500)),
                step=50,
                help="Sets the alert threshold on the Model Serving endpoint.",
            )
            data["sla_latency_ms"] = sla_latency
        with col2:
            sla_uptime = st.number_input(
                "Target uptime % *",
                min_value=95.0,
                max_value=99.99,
                value=float(prev.get("sla_uptime_pct", 99.99)),
                step=0.01,
                format="%.2f",
                help="SLA tracking metric and alert threshold.",
            )
            data["sla_uptime_pct"] = sla_uptime
        with col3:
            expected_qps = st.number_input(
                "Expected QPS",
                min_value=1,
                max_value=100000,
                value=int(prev.get("expected_qps", 10)),
                step=1,
                help="Drives min/max provisioned throughput for autoscaling.",
            )
            data["expected_qps"] = expected_qps

    st.markdown("---")
    st.markdown("**Model framework(s)**")
    st.caption(
        "Select all frameworks this project will use. "
        "⭐ = Databricks-native first-class MLflow flavor and Model Serving support."
    )

    # Build framework choices from the service registry
    all_fw = list(iv.MODEL_FRAMEWORKS.keys())

    def _fw_label(k: str) -> str:
        info = iv.MODEL_FRAMEWORKS[k]
        star = " ⭐" if info.get("preferred") else ""
        return f"{info['label']}{star}"

    # Preserve previous selection; handle backward compat with old model_type field
    prev_frameworks = prev.get("model_frameworks", [])
    if not prev_frameworks and prev.get("model_type"):
        prev_frameworks = [prev["model_type"]]
    prev_frameworks = [f for f in prev_frameworks if f in all_fw]
    if not prev_frameworks:
        prev_frameworks = ["xgboost"]

    model_frameworks = st.multiselect(
        "Framework(s) *",
        options=all_fw,
        default=prev_frameworks,
        format_func=_fw_label,
        help="Each selected framework generates appropriate MLflow flavor code and requirements.txt entries.",
        label_visibility="collapsed",
    )

    if model_frameworks:
        for fw in model_frameworks:
            info = iv.MODEL_FRAMEWORKS[fw]
            st.caption(f"**{info['label']}** — {info['desc']}")

    data["model_frameworks"] = model_frameworks

    errors = iv.validate_step(2, data)
    _validation_box(errors)
    _nav(2, errors, data)


# ── Step 3: Data Specs ────────────────────────────────────────────────────────


def _step3() -> None:
    _progress_header(3, "Data Specs")

    prev = iv.get_step_data(st.session_state, 3)

    # Data availability toggle
    data_complete = st.checkbox(
        "Training data is already available",
        value=prev.get("data_complete", True),
        help="Uncheck if you haven't created the training datasets yet — you can complete this step later.",
    )

    if not data_complete:
        st.info(
            "You can create the project scaffold now and return to fill in data specs once your "
            "training datasets are ready. All data-dependent gates will be blocked until this step is complete.",
            icon="ℹ️",
        )
        data = {
            "data_complete": False,
            "training_datasets": prev.get("training_datasets", []),
            "target_variable": prev.get("target_variable", ""),
            "feature_columns": prev.get("feature_columns", []),
            "training_data_size_rows": prev.get("training_data_size_rows"),
            "contains_pii": prev.get("contains_pii", False),
            "pii_columns": prev.get("pii_columns", []),
            "pii_justifications": prev.get("pii_justifications", {}),
            "pii_suppression_methods": prev.get("pii_suppression_methods", {}),
            "data_classification": prev.get("data_classification", "internal"),
            "field_justifications": prev.get("field_justifications", {}),
        }
        _nav(3, [], data)
        return

    # ── Training datasets (multi) ──────────────────────────────────────────────
    st.markdown("**Training data location(s)**")
    st.caption(
        "Unity Catalog paths (catalog.schema.table). Add multiple tables if your training data "
        "spans more than one source."
    )

    if "step3_datasets" not in st.session_state:
        existing = prev.get("training_datasets", [])
        st.session_state["step3_datasets"] = existing if existing else [""]

    datasets: list[str] = st.session_state["step3_datasets"]

    for i, ds in enumerate(datasets):
        col_input, col_remove = st.columns([5, 1])
        with col_input:
            val = st.text_input(
                f"Dataset {i + 1}",
                value=ds,
                placeholder="catalog.schema.table_name",
                key=f"dataset_{i}",
                label_visibility="collapsed",
            )
            datasets[i] = val
        with col_remove:
            if len(datasets) > 1 and st.button("✕", key=f"rm_ds_{i}"):
                datasets.pop(i)
                st.session_state["step3_datasets"] = datasets
                st.rerun()

    if st.button("+ Add dataset"):
        datasets.append("")
        st.session_state["step3_datasets"] = datasets
        st.rerun()

    training_datasets = [d.strip() for d in datasets if d.strip()]

    # ── Schema inference ───────────────────────────────────────────────────────
    inferred_cols: list[str] = st.session_state.get("step3_inferred_columns", [])

    infer_col, infer_status = st.columns([2, 5])
    with infer_col:
        if st.button(
            "⟳ Infer Schema",
            help="Query the first dataset in Unity Catalog to auto-detect column names.",
            disabled=not training_datasets,
        ):
            first_table = training_datasets[0] if training_datasets else ""
            if first_table:
                with st.spinner(f"Querying `{first_table}`..."):
                    try:
                        from services.db_service import DbService

                        cols = DbService().infer_table_schema(first_table)
                        st.session_state["step3_inferred_columns"] = [c["name"] for c in cols]
                        st.session_state["step3_inferred_types"] = {c["name"]: c["data_type"] for c in cols}
                        inferred_cols = st.session_state["step3_inferred_columns"]
                    except Exception as exc:
                        st.session_state["step3_infer_error"] = str(exc)
    with infer_status:
        if inferred_cols:
            st.success(f"{len(inferred_cols)} columns loaded from `{training_datasets[0]}`", icon="✓")
        elif st.session_state.get("step3_infer_error"):
            st.warning(f"Schema inference failed: {st.session_state['step3_infer_error']}")

    st.markdown("---")

    # ── Target variable & features — selectbox if schema inferred, text otherwise ─
    if inferred_cols:
        prev_target = prev.get("target_variable", "")
        target_idx = inferred_cols.index(prev_target) if prev_target in inferred_cols else 0
        target_variable = st.selectbox(
            "Target variable (column to predict) *",
            inferred_cols,
            index=target_idx,
            help="The column your model will learn to predict. Used in generated train.py and fairness tests.",
        )
        available_features = [c for c in inferred_cols if c != target_variable]
        prev_features = prev.get("feature_columns", [])
        feature_columns = st.multiselect(
            "Feature columns *",
            options=available_features,
            default=[c for c in prev_features if c in available_features],
            help="Each column gets its own drift monitor. Select all columns the model will train on.",
        )
    else:
        target_variable = st.text_input(
            "Target variable (column to predict) *",
            value=prev.get("target_variable", ""),
            placeholder="churn_flag",
            help="The column your model will learn to predict. Click 'Infer Schema' to load from UC.",
        )
        features_raw = st.text_area(
            "Feature columns *",
            value=", ".join(prev.get("feature_columns", [])),
            placeholder="age, tenure_months, monthly_charges, contract_type, ...",
            height=80,
            help="Comma-separated list. Click 'Infer Schema' to load from UC automatically.",
        )
        feature_columns = [f.strip() for f in features_raw.split(",") if f.strip()]

    training_data_size_rows = st.number_input(
        "Approximate training rows",
        min_value=0,
        value=int(prev.get("training_data_size_rows", 0)),
        step=1000,
        help="Optional. Sizes test splits and cluster config in the generated job.",
    )

    st.markdown("---")
    st.markdown("**Column-level data classification**")
    st.caption(
        "Classify each column individually. The dataset's overall classification defaults to the most "
        "restricted level in the set. Use the LLM scanner to auto-suggest classifications."
    )

    _CLF_LEVELS = ["public", "internal", "sensitive", "restricted"]
    _CLF_ORDER = {c: i for i, c in enumerate(_CLF_LEVELS)}
    _CLF_COLORS = {
        "public": "#22c55e",
        "internal": "#3b82f6",
        "sensitive": "#f59e0b",
        "restricted": "#ef4444",
    }

    prev_col_clf: dict[str, str] = prev.get("column_classifications", {})
    col_classifications: dict[str, str] = {}
    classification_attestations: dict[str, dict] = prev.get("classification_attestations", {})

    if feature_columns:
        clf_scan_col, clf_status_col = st.columns([2, 5])
        with clf_scan_col:
            if st.button("🔍 Scan columns for sensitivity"):
                with st.spinner("Classifying columns via LLM..."):
                    try:
                        from services.ai_service import AiService

                        ai = AiService()
                        scan_result = ai._chat(
                            system=(
                                "You are a data governance expert. Classify each column name as "
                                "public / internal / sensitive / restricted based on the potential "
                                "to identify individuals or expose confidential information. "
                                "Reply with ONLY a JSON object mapping column_name -> classification. "
                                "Be conservative: if in doubt, classify higher."
                            ),
                            user="Columns: "
                            + ", ".join(feature_columns + ([target_variable] if target_variable else [])),
                        )
                        import json as _json

                        suggested_clf = _json.loads(scan_result)
                        st.session_state["step3_clf_suggestions"] = {
                            k: v for k, v in suggested_clf.items() if v in _CLF_LEVELS
                        }
                    except Exception as exc:
                        st.session_state["step3_clf_error"] = str(exc)

        clf_suggestions: dict[str, str] = st.session_state.get("step3_clf_suggestions", {})
        if clf_suggestions:
            with clf_status_col:
                st.success(f"LLM suggested classifications for {len(clf_suggestions)} columns", icon="✓")
        elif st.session_state.get("step3_clf_error"):
            with clf_status_col:
                st.warning(f"Scan failed: {st.session_state['step3_clf_error']}")

        all_clf_cols = feature_columns + ([target_variable] if target_variable else [])
        sensitive_columns: list[str] = []
        restricted_columns: list[str] = []

        for col in all_clf_cols:
            suggested = clf_suggestions.get(col, "internal")
            default_clf = prev_col_clf.get(col, suggested)
            with st.container(border=True):
                c_label, c_sel, c_attest = st.columns([3, 2, 2])
                with c_label:
                    st.markdown(f"`{col}`")
                with c_sel:
                    clf_val = st.selectbox(
                        "Level",
                        _CLF_LEVELS,
                        index=_CLF_LEVELS.index(default_clf) if default_clf in _CLF_LEVELS else 1,
                        key=f"clf_{col}",
                        label_visibility="collapsed",
                    )
                col_classifications[col] = clf_val
                if clf_val in ("sensitive", "restricted"):
                    if clf_val == "sensitive":
                        sensitive_columns.append(col)
                    else:
                        restricted_columns.append(col)
                    with c_attest:
                        if st.button("Attest", key=f"attest_{col}"):
                            import datetime as _dt

                            classification_attestations[col] = {
                                "decision": clf_val,
                                "timestamp": _dt.datetime.now(_dt.UTC).isoformat(),
                                "attested": True,
                            }
                    if col in classification_attestations:
                        st.caption(
                            f"Attested as {clf_val} at {classification_attestations[col].get('timestamp', '')[:10]}"
                        )

        # Dataset-level summary: most restricted classification in the set
        if col_classifications:
            top_level = max(col_classifications.values(), key=lambda v: _CLF_ORDER.get(v, 0))
            color = _CLF_COLORS.get(top_level, "#64748b")
            flagged = sensitive_columns + restricted_columns
            flagged_html = (
                f'<span style="font-size:12px;color:#64748b"> — sensitive/restricted: {", ".join(flagged)}</span>'
                if flagged
                else ""
            )
            st.markdown(
                f'<div style="margin-top:8px;padding:8px 12px;border-radius:4px;background:#111827;'
                f'border-left:3px solid {color}">'
                f'<span style="font-size:12px;color:#64748b">Dataset classification: </span>'
                f'<span style="font-size:13px;font-weight:600;color:{color};'
                f'text-transform:uppercase">{top_level}</span>'
                f"{flagged_html}</div>",
                unsafe_allow_html=True,
            )
        data_classification = (
            max(col_classifications.values(), key=lambda v: _CLF_ORDER.get(v, 0)) if col_classifications else "internal"
        )
    else:
        clf_idx = _DATA_CLASSIFICATIONS.index(prev.get("data_classification", "internal"))
        data_classification = st.selectbox(
            "Classification level",
            _DATA_CLASSIFICATIONS,
            index=clf_idx,
            help="Infer schema first to enable column-level classification.",
            label_visibility="collapsed",
        )
        sensitive_columns = prev.get("sensitive_columns", [])
        restricted_columns = prev.get("restricted_columns", [])
        col_classifications = prev_col_clf

    # ── PII section ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**PII & Personally Identifiable Information**")
    contains_pii = st.checkbox(
        "This dataset contains PII",
        value=prev.get("contains_pii", False),
        help="Enables column-level encryption requirements, restricted access grants, and elevated audit logging.",
    )

    pii_columns: list[str] = []
    pii_justifications: dict[str, str] = prev.get("pii_justifications", {})
    pii_suppression_methods: dict[str, list[str]] = prev.get("pii_suppression_methods", {})

    all_col_options = feature_columns + ([target_variable] if target_variable else [])

    # LLM PII check — available whenever we have column names
    if feature_columns:
        pii_check_col, pii_status_col = st.columns([2, 5])
        with pii_check_col:
            if st.button(
                "🔍 Check columns for PII",
                help=(
                    "Send column names to the configured LLM to flag potential PII. "
                    "Conservative — flags anything suspicious."
                ),
            ):
                with st.spinner("Checking columns for PII..."):
                    try:
                        from services.ai_service import AiService

                        results = AiService().check_pii(feature_columns)
                        st.session_state["step3_pii_results"] = results
                        # Auto-suggest any high-confidence flags
                        suggested = [r["column"] for r in results if r.get("is_pii") and r.get("confidence") != "low"]
                        if suggested:
                            st.session_state["step3_pii_suggestions"] = suggested
                    except Exception as exc:
                        st.session_state["step3_pii_error"] = str(exc)

        pii_results: list[dict] = st.session_state.get("step3_pii_results", [])
        if pii_results:
            with pii_status_col:
                flagged_count = sum(1 for r in pii_results if r.get("is_pii"))
                if flagged_count:
                    st.warning(f"{flagged_count} column(s) flagged as potential PII", icon="⚠️")
                else:
                    st.success("No PII detected in column names", icon="✓")

            with st.expander(
                "PII check results", expanded=bool(flagged_count := sum(1 for r in pii_results if r.get("is_pii")))
            ):
                for r in pii_results:
                    col_name = r.get("column", "")
                    is_pii = r.get("is_pii", False)
                    reason = r.get("reason", "")
                    confidence = r.get("confidence", "")
                    icon = "⚠️" if is_pii else "✓"
                    conf_color = {"high": "#ef4444", "medium": "#f59e0b", "low": "#64748b"}.get(confidence, "#64748b")
                    st.markdown(
                        f'<div style="display:flex;gap:10px;align-items:flex-start;padding:6px 0;'
                        f'border-bottom:1px solid #1a2740">'
                        f'<span style="font-size:14px">{icon}</span>'
                        f'<div><span style="font-family:monospace;font-size:13px;color:#a9b6cc">{col_name}</span>'
                        f' <span style="font-size:11px;color:{conf_color};text-transform:uppercase">'
                        f"{confidence}</span>"
                        f'<br><span style="font-size:12px;color:#64748b">{reason}</span></div></div>',
                        unsafe_allow_html=True,
                    )
        elif st.session_state.get("step3_pii_error"):
            with pii_status_col:
                st.warning(f"PII check failed: {st.session_state['step3_pii_error']}")

    if contains_pii:
        if all_col_options:
            # Pre-select LLM suggestions if available
            pii_suggestions = st.session_state.get("step3_pii_suggestions", [])
            prev_pii = prev.get("pii_columns", [])
            default_pii = list(dict.fromkeys([c for c in (prev_pii + pii_suggestions) if c in all_col_options]))
            pii_columns = st.multiselect(
                "Which columns contain PII? *",
                options=all_col_options,
                default=default_pii,
                help="These will be marked for encryption and restricted access in Unity Catalog.",
            )
        else:
            pii_raw = st.text_input(
                "Which columns contain PII? *",
                value=", ".join(prev.get("pii_columns", [])),
                placeholder="customer_id, email, phone_number",
            )
            pii_columns = [c.strip() for c in pii_raw.split(",") if c.strip()]

        if pii_columns:
            st.markdown("")
            st.caption(
                "**Justification and suppression required** — both fields must be completed before you can advance."
            )

            _SUPPRESSION_OPTIONS = {
                "delta_mask": "Delta column mask — Unity Catalog column masking policy (recommended)",
                "suppress_logs": "Suppress from logs — exclude from inference logs and intermediate tables",
                "hash": "Hash / tokenize — store hashed representation only",
            }

            for col in pii_columns:
                with st.container(border=True):
                    st.markdown(f"**`{col}`**")
                    pii_justifications[col] = st.text_input(
                        "Why is this PII field necessary for the model?",
                        value=pii_justifications.get(col, ""),
                        placeholder="Required because the model predicts X, which depends on Y...",
                        key=f"pii_just_{col}",
                    )
                    prev_supp = pii_suppression_methods.get(col)
                    if isinstance(prev_supp, str):
                        prev_supp = [prev_supp] if prev_supp and prev_supp != "none" else ["delta_mask"]
                    elif not prev_supp:
                        prev_supp = ["delta_mask"]
                    chosen_supp = st.multiselect(
                        "Suppression method(s)",
                        options=list(_SUPPRESSION_OPTIONS.keys()),
                        default=[s for s in prev_supp if s in _SUPPRESSION_OPTIONS],
                        format_func=lambda k: _SUPPRESSION_OPTIONS[k].split(" — ")[0],
                        key=f"pii_supp_{col}",
                    )
                    if not chosen_supp:
                        chosen_supp = ["delta_mask"]
                        st.caption("Defaulting to Delta column mask.")
                    pii_suppression_methods[col] = chosen_supp
                    for s in chosen_supp:
                        st.caption(f"• {_SUPPRESSION_OPTIONS[s].split(' — ')[1]}")

    # PII blocking — require justification AND suppression for every PII column
    pii_errors: list[str] = []
    if contains_pii and pii_columns:
        for col in pii_columns:
            if not pii_justifications.get(col, "").strip():
                pii_errors.append(f"PII column `{col}`: justification is required before proceeding.")
            if not pii_suppression_methods.get(col):
                pii_errors.append(f"PII column `{col}`: select at least one suppression method.")

    data = {
        "data_complete": True,
        "training_datasets": training_datasets,
        "target_variable": target_variable.strip() if isinstance(target_variable, str) else target_variable,
        "feature_columns": feature_columns,
        "training_data_size_rows": training_data_size_rows if training_data_size_rows > 0 else None,
        "contains_pii": contains_pii,
        "pii_columns": pii_columns,
        "pii_justifications": pii_justifications,
        "pii_suppression_methods": pii_suppression_methods,
        "data_classification": data_classification,
        "column_classifications": col_classifications,
        "sensitive_columns": sensitive_columns,
        "restricted_columns": restricted_columns,
        "classification_attestations": classification_attestations,
        "field_justifications": {},
    }

    errors = (iv.validate_step(3, data) if (training_datasets or target_variable) else []) + pii_errors
    _validation_box(errors)
    _nav(3, errors, data)


# ── Step 4: Governance ────────────────────────────────────────────────────────


def _step4() -> None:
    _progress_header(4, "Governance")

    prev = iv.get_step_data(st.session_state, 4)
    step3_data = iv.get_step_data(st.session_state, 3)
    all_features = step3_data.get("feature_columns", [])
    target_var = step3_data.get("target_variable", "")
    all_columns = all_features + ([target_var] if target_var else [])

    # ── Risk tier (§20.1) — org-authored tier definitions only ────────────────
    st.markdown("**Model Risk Tier**")
    st.caption(
        "Tiers and their required gates come from your org's policy packs (PR-reviewed YAML) — "
        "the app ships the mechanism, not the framework. This field is never defaulted: "
        "an explicit choice and a one-line justification are required."
    )
    try:
        from services.policy_pack_service import PolicyPackService

        pack_options = PolicyPackService().pack_options()
    except Exception as exc:
        pack_options = {}
        st.error(f"Policy packs could not be loaded: {exc}", icon="🛑")

    applied_policy_packs = st.multiselect(
        "Policy packs applied",
        options=sorted(pack_options),
        default=[p for p in prev.get("applied_policy_packs", sorted(pack_options)) if p in pack_options],
        help="Multiple packs may apply; approval gates are the union across packs (§20.2).",
    )
    tier_options = sorted({t for p in applied_policy_packs for t in pack_options.get(p, [])})
    prev_tier = prev.get("risk_tier", "")
    risk_tier = st.selectbox(
        "Risk tier",
        options=tier_options,
        index=tier_options.index(prev_tier) if prev_tier in tier_options else None,
        placeholder="Select the org-defined tier…",
    )
    risk_tier_justification = st.text_input(
        "Justification — why this tier?",
        value=prev.get("risk_tier_justification", ""),
        placeholder="e.g. Influences credit decisions → high materiality per model risk policy.",
    )
    st.markdown("---")

    # ── Fairness — always on ───────────────────────────────────────────────────
    st.markdown("**Fairness Testing**")
    st.info(
        "Fairness testing is **always required** for all models. "
        "If no protected or proxy attributes apply to this model, you may request an override — "
        "this requires sign-off from both Legal and MLOps.",
        icon="⚖️",
    )

    fairness_override_requested = False
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Protected attributes**")
        st.caption("Select all protected classes that appear in or can be inferred from your feature set.")

        fairness_attributes = st.multiselect(
            "Protected attributes",
            options=iv.PROTECTED_CLASSES,
            default=[a for a in prev.get("fairness_attributes", []) if a in iv.PROTECTED_CLASSES],
            help="Columns or derivable information for each selected class will be tested for disparate impact.",
            label_visibility="collapsed",
        )

        if not fairness_attributes:
            fairness_override_requested = st.checkbox(
                "Request override — no protected attributes apply to this model",
                value=prev.get("fairness_override_requested", False),
                help="Requires Legal + MLOps approval before training can proceed.",
            )
            if fairness_override_requested:
                st.warning(
                    "An override request will be created. Legal and MLOps must approve before "
                    "this model can advance to staging.",
                    icon="⚠️",
                )

    with col2:
        st.markdown("**Fairness frameworks**")
        st.caption("All frameworks are run by default. Deselect only with MLOps approval.")

        bias_test_types = st.multiselect(
            "Frameworks",
            options=["aif360", "fairlearn", "custom"],
            default=prev.get("bias_test_types", ["aif360", "fairlearn"]),
            format_func=lambda x: {
                "aif360": "AI Fairness 360 (IBM)",
                "fairlearn": "Fairlearn (Microsoft)",
                "custom": "Custom (implement in src/evaluate.py)",
            }.get(x, x),
            label_visibility="collapsed",
        )

        fairness_threshold_pct = st.slider(
            "Max disparity threshold (%)",
            min_value=1,
            max_value=30,
            value=int(prev.get("fairness_threshold_pct", 10)),
            help=(
                "Models fail the fairness gate if disparity exceeds this value. "
                "Default 10% is stricter than the EEOC legal minimum (20%) and aligns with "
                "financial services model risk guidance."
            ),
        )

    # ── Protected attribute justifications ────────────────────────────────────
    if fairness_attributes:
        st.markdown("---")
        st.markdown("**Protected attribute justification**")
        st.caption(
            "For each selected protected attribute, explain why data related to this class is present "
            "or derivable from your feature set, and what mitigations are in place."
        )
        protected_attribute_justifications: dict[str, str] = prev.get("protected_attribute_justifications", {})
        for attr in fairness_attributes:
            with st.container(border=True):
                st.markdown(f"**{attr}**")
                protected_attribute_justifications[attr] = st.text_area(
                    "Justification",
                    value=protected_attribute_justifications.get(attr, ""),
                    placeholder=f"Why is {attr} present or derivable, and what fairness controls apply?",
                    height=70,
                    key=f"pa_just_{attr}",
                    label_visibility="collapsed",
                )
    else:
        protected_attribute_justifications = prev.get("protected_attribute_justifications", {})

    # ── Proxy variables ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Proxy Variables**")
    st.caption(
        "List any features that could serve as proxies for protected classes — e.g., zip code (race), "
        "surname (national origin). These are included in fairness tests even if the protected class "
        "column itself is absent."
    )

    if "step4_proxies" not in st.session_state:
        st.session_state["step4_proxies"] = prev.get("proxy_variables", [])

    proxies: list[dict] = st.session_state["step4_proxies"]

    if all_columns:
        col_add_proxy, col_llm_proxy = st.columns([2, 3])
        with col_add_proxy:
            if st.button("+ Add proxy variable"):
                proxies.append({"column": "", "protected_classes": [], "justification": ""})
                st.session_state["step4_proxies"] = proxies
                st.rerun()
        with col_llm_proxy:
            if st.button("🔍 LLM scan for proxies"):
                with st.spinner("Scanning for proxy variables..."):
                    try:
                        import json as _json

                        from services.ai_service import AiService

                        ai = AiService()
                        scan = ai._chat(
                            system=(
                                "You are a fairness and bias expert. Given a list of feature column names "
                                "and protected classes, identify columns that could act as proxies. "
                                "Return ONLY a JSON array like: "
                                '[{"column": "zip_code", "protected_classes": ["Race / Ethnicity"], '
                                '"justification": "..."}, ...]'
                            ),
                            user=(
                                f"Features: {', '.join(all_columns)}\n"
                                f"Protected classes declared: {', '.join(fairness_attributes) or 'none declared'}"
                            ),
                        )
                        suggested_proxies = _json.loads(scan)
                        st.session_state["step4_proxies"] = suggested_proxies
                        st.rerun()
                    except Exception as exc:
                        st.warning(f"LLM scan failed: {exc}")

    updated_proxies = []
    for i, pv in enumerate(proxies):
        with st.container(border=True):
            pc1, pc2 = st.columns(2)
            with pc1:
                col_opt = all_columns if all_columns else ["(enter manually below)"]
                col_val = st.selectbox(
                    "Feature column",
                    options=col_opt,
                    index=col_opt.index(pv["column"]) if pv.get("column") in col_opt else 0,
                    key=f"proxy_col_{i}",
                )
            with pc2:
                prev_pcs = pv.get("protected_classes", [pv.get("protected_class", "")])
                if isinstance(prev_pcs, str):
                    prev_pcs = [prev_pcs] if prev_pcs else []
                pc_vals = st.multiselect(
                    "Protected class(es) it may proxy for",
                    options=iv.PROTECTED_CLASSES,
                    default=[c for c in prev_pcs if c in iv.PROTECTED_CLASSES],
                    key=f"proxy_pc_{i}",
                )
            just_val = st.text_input(
                "Justification — why is this field necessary despite the proxy risk?",
                value=pv.get("justification", ""),
                key=f"proxy_just_{i}",
                placeholder="Necessary for X because... Alternative features considered: ...",
            )
            _, col_del = st.columns([5, 1])
            with col_del:
                if st.button("Remove", key=f"rm_proxy_{i}"):
                    proxies.pop(i)
                    st.session_state["step4_proxies"] = proxies
                    st.rerun()
            updated_proxies.append({"column": col_val, "protected_classes": pc_vals, "justification": just_val})

    st.session_state["step4_proxies"] = updated_proxies

    # ── Data Quality Gates ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Data Quality Gates**")
    st.caption(
        "Every column must appear in exactly one box. Columns in **Required** block training on failure; "
        "columns in **Acceptable Issues** log only. Click ✕ next to a column to move it to the other box."
    )

    if all_features:
        _dq_req_key = "step4_dq_required"
        _dq_acc_key = "step4_dq_acceptable"

        # Initialize from prev data or from all_features (all required by default)
        if _dq_req_key not in st.session_state:
            prev_req = prev.get("data_quality_required_fields", all_features)
            prev_acc = prev.get("data_quality_acceptable_issues", [])
            st.session_state[_dq_req_key] = [f for f in prev_req if f in all_features]
            st.session_state[_dq_acc_key] = [f for f in prev_acc if f in all_features]
            # Any features missing from both boxes go to required
            both = set(st.session_state[_dq_req_key]) | set(st.session_state[_dq_acc_key])
            for f in all_features:
                if f not in both:
                    st.session_state[_dq_req_key].append(f)

        dq_required: list[str] = st.session_state[_dq_req_key]
        dq_acceptable: list[str] = st.session_state[_dq_acc_key]

        box_req, box_acc = st.columns(2)
        with box_req:
            st.markdown(
                '<div style="font-size:12px;font-weight:600;color:#ef4444;text-transform:uppercase;'
                'letter-spacing:.08em;margin-bottom:6px">Required (blocks training)</div>',
                unsafe_allow_html=True,
            )
            with st.container(border=True):
                for feat in list(dq_required):
                    c_name, c_btn = st.columns([5, 1])
                    with c_name:
                        st.markdown(
                            f'<span style="font-size:13px;font-family:monospace;color:#a9b6cc">{feat}</span>',
                            unsafe_allow_html=True,
                        )
                    with c_btn:
                        if st.button("✕", key=f"dq_mv_req_{feat}"):
                            st.session_state[_dq_req_key].remove(feat)
                            st.session_state[_dq_acc_key].append(feat)
                            st.rerun()
                if not dq_required:
                    st.caption("(empty)")

        with box_acc:
            st.markdown(
                '<div style="font-size:12px;font-weight:600;color:#f59e0b;text-transform:uppercase;'
                'letter-spacing:.08em;margin-bottom:6px">Acceptable Issues (log only)</div>',
                unsafe_allow_html=True,
            )
            with st.container(border=True):
                for feat in list(dq_acceptable):
                    c_name, c_btn = st.columns([5, 1])
                    with c_name:
                        st.markdown(
                            f'<span style="font-size:13px;font-family:monospace;color:#a9b6cc">{feat}</span>',
                            unsafe_allow_html=True,
                        )
                    with c_btn:
                        if st.button("✕", key=f"dq_mv_acc_{feat}"):
                            st.session_state[_dq_acc_key].remove(feat)
                            st.session_state[_dq_req_key].append(feat)
                            st.rerun()
                if not dq_acceptable:
                    st.caption("(empty)")
    else:
        st.info("Complete Step 3 (Data Specs) first to configure column-level quality gates.")
        dq_required = prev.get("data_quality_required_fields", [])
        dq_acceptable = prev.get("data_quality_acceptable_issues", [])

    data = {
        "fairness_attributes": fairness_attributes,
        "proxy_variables": updated_proxies,
        "fairness_threshold_pct": fairness_threshold_pct,
        "bias_test_types": bias_test_types if bias_test_types else ["aif360", "fairlearn"],
        "column_justifications": {},
        "data_quality_required_fields": dq_required,
        "data_quality_acceptable_issues": dq_acceptable,
        "fairness_override_requested": fairness_override_requested,
        "protected_attribute_justifications": protected_attribute_justifications,
        "risk_tier": risk_tier or "",
        "risk_tier_justification": risk_tier_justification,
        "applied_policy_packs": applied_policy_packs,
    }

    errors = iv.validate_step(4, data)
    # Require at least one bias framework
    if not data["bias_test_types"]:
        errors = errors + ["bias_test_types: At least one fairness framework must be selected."]

    _validation_box(errors)
    _nav(4, errors, data)


# ── Step 5: Deployment ────────────────────────────────────────────────────────


def _step5() -> None:
    _progress_header(5, "Deployment")

    prev = iv.get_step_data(st.session_state, 5)
    step3_data = iv.get_step_data(st.session_state, 3)
    all_features = step3_data.get("feature_columns", [])

    st.markdown("**Retraining Strategy**")
    retraining_strategy = st.radio(
        "How should this model be retrained?",
        options=["manual", "scheduled", "on_drift", "hybrid"],
        format_func=lambda x: {
            "manual": "Manual — retrain only when you trigger it",
            "scheduled": "Scheduled — retrain on a fixed schedule",
            "on_drift": "On Drift — retrain when performance drops past threshold",
            "hybrid": "Hybrid (recommended) — scheduled + drift-triggered",
        }[x],
        index=["manual", "scheduled", "on_drift", "hybrid"].index(prev.get("retraining_strategy", "hybrid")),
        label_visibility="collapsed",
    )

    retraining_schedule = prev.get("retraining_schedule", "0 2 * * *")
    retraining_timezone = prev.get("retraining_timezone", "America/New_York")
    retraining_drift_threshold = prev.get("retraining_drift_threshold", 5.0)

    if retraining_strategy in ("scheduled", "hybrid"):
        st.markdown("")
        st.markdown("**Retraining schedule**")
        retraining_schedule, retraining_timezone = _cron_builder(
            "retrain",
            retraining_schedule,
            retraining_timezone,
        )

    if retraining_strategy in ("on_drift", "hybrid"):
        st.markdown("")
        retraining_drift_threshold = st.number_input(
            "Global performance drift threshold (%)",
            min_value=1.0,
            max_value=50.0,
            value=float(retraining_drift_threshold),
            step=0.5,
            help=(
                "Retraining fires when the PRIMARY PERFORMANCE METRIC drops by this percentage "
                "against the labeled reference window. Absolute and bidirectional for input feature "
                "drift (PSI/KS per field); degradation-only for model performance. "
                "Example: if accuracy was 0.85 and threshold is 5%, retraining fires when accuracy "
                "drops below 0.808. Individual feature drift uses PSI/KS thresholds set per-field below."
            ),
        )

    # ── Per-field drift thresholds ─────────────────────────────────────────────
    if retraining_strategy in ("on_drift", "hybrid") and all_features:
        st.markdown("---")
        st.markdown("**Per-field drift thresholds (optional)**")
        st.caption(
            "Override the global threshold for specific features. Leave blank to use the global threshold above."
        )

        prev_field_configs = {fc["field_name"]: fc["threshold"] for fc in prev.get("drift_field_configs", [])}
        drift_field_configs = []
        for feat in all_features[:10]:  # cap at 10 to keep UI manageable
            col_name, col_thresh = st.columns([3, 1])
            with col_name:
                st.caption(f"`{feat}`")
            with col_thresh:
                thresh = st.number_input(
                    "Threshold %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(prev_field_configs.get(feat, 0.0)),
                    step=0.5,
                    key=f"drift_{feat}",
                    label_visibility="collapsed",
                )
                if thresh > 0:
                    drift_field_configs.append({"field_name": feat, "threshold": thresh})

        if len(all_features) > 10:
            st.caption(f"Showing first 10 of {len(all_features)} features. Edit remaining in the data contract.")
    else:
        drift_field_configs = prev.get("drift_field_configs", [])

    st.markdown("---")
    st.markdown("**Rollback Configuration**")
    rollback_enabled = st.checkbox(
        "Enable automatic rollback",
        value=prev.get("rollback_enabled", True),
        help="Rolls back to the previous model version when error conditions are detected.",
    )

    rollback_trigger_types: list[str] = prev.get("rollback_trigger_types", ["inference_errors", "latency_breach"])
    rollback_error_threshold = prev.get("rollback_error_threshold", 10)
    rollback_time_window_minutes = prev.get("rollback_time_window_minutes", 5)
    prev_trigger_configs: dict[str, dict] = prev.get("rollback_trigger_configs", {})
    rollback_trigger_configs: dict[str, dict] = {}

    if rollback_enabled:
        st.caption(
            "**Trigger conditions** — rollback fires if ANY checked condition is met. "
            "Each trigger has its own threshold config."
        )
        rollback_trigger_types = []

        _TRIGGER_DEFAULTS: dict[str, dict] = {
            "inference_errors": {"error_count": 10, "window_minutes": 5},
            "data_quality": {"failure_count": 3, "window_minutes": 15},
            "latency_breach": {"p95_ms": 2000, "sustained_minutes": 3},
            "prediction_anomaly": {"deviation_pct": 20.0, "window_minutes": 10},
        }

        for trig_key, trig_label in _ROLLBACK_TRIGGERS.items():
            prev_cfg = prev_trigger_configs.get(trig_key, _TRIGGER_DEFAULTS.get(trig_key, {}))
            checked = trig_key in prev.get("rollback_trigger_types", ["inference_errors", "latency_breach"])
            with st.container(border=True):
                trig_col, cfg_col = st.columns([5, 1])
                with trig_col:
                    is_checked = st.checkbox(trig_label, value=checked, key=f"rb_{trig_key}")
                if is_checked:
                    rollback_trigger_types.append(trig_key)
                    with cfg_col:
                        show_cfg = st.button(
                            "⚙", key=f"rb_cfg_btn_{trig_key}", help="Configure threshold for this trigger"
                        )
                        if show_cfg:
                            st.session_state[f"rb_cfg_open_{trig_key}"] = not st.session_state.get(
                                f"rb_cfg_open_{trig_key}", False
                            )

                    if st.session_state.get(f"rb_cfg_open_{trig_key}") or prev_cfg != _TRIGGER_DEFAULTS.get(
                        trig_key, {}
                    ):
                        trig_cfg: dict = {}
                        if trig_key == "inference_errors":
                            c1, c2 = st.columns(2)
                            with c1:
                                trig_cfg["error_count"] = st.number_input(
                                    "Error count",
                                    min_value=1,
                                    max_value=1000,
                                    value=int(prev_cfg.get("error_count", 10)),
                                    key=f"rb_{trig_key}_count",
                                    help="Errors within the window that trigger rollback.",
                                )
                            with c2:
                                trig_cfg["window_minutes"] = st.number_input(
                                    "Window (min)",
                                    min_value=1,
                                    max_value=60,
                                    value=int(prev_cfg.get("window_minutes", 5)),
                                    key=f"rb_{trig_key}_win",
                                )
                        elif trig_key == "data_quality":
                            c1, c2 = st.columns(2)
                            with c1:
                                trig_cfg["failure_count"] = st.number_input(
                                    "Failure count",
                                    min_value=1,
                                    max_value=100,
                                    value=int(prev_cfg.get("failure_count", 3)),
                                    key=f"rb_{trig_key}_count",
                                    help="Quality check failures that trigger rollback.",
                                )
                            with c2:
                                trig_cfg["window_minutes"] = st.number_input(
                                    "Window (min)",
                                    min_value=1,
                                    max_value=60,
                                    value=int(prev_cfg.get("window_minutes", 15)),
                                    key=f"rb_{trig_key}_win",
                                )
                        elif trig_key == "latency_breach":
                            c1, c2 = st.columns(2)
                            with c1:
                                trig_cfg["p95_ms"] = st.number_input(
                                    "P95 latency threshold (ms)",
                                    min_value=100,
                                    max_value=30000,
                                    value=int(prev_cfg.get("p95_ms", 2000)),
                                    key=f"rb_{trig_key}_p95",
                                    help="Rollback fires when P95 exceeds this value.",
                                )
                            with c2:
                                trig_cfg["sustained_minutes"] = st.number_input(
                                    "Sustained for (min)",
                                    min_value=1,
                                    max_value=30,
                                    value=int(prev_cfg.get("sustained_minutes", 3)),
                                    key=f"rb_{trig_key}_sustained",
                                    help="Must exceed threshold for this many consecutive minutes.",
                                )
                        elif trig_key == "prediction_anomaly":
                            c1, c2 = st.columns(2)
                            with c1:
                                trig_cfg["deviation_pct"] = st.number_input(
                                    "Output deviation (%)",
                                    min_value=1.0,
                                    max_value=100.0,
                                    value=float(prev_cfg.get("deviation_pct", 20.0)),
                                    step=1.0,
                                    key=f"rb_{trig_key}_dev",
                                    help=(
                                        "Rollback fires when prediction distribution "
                                        "deviates this much from baseline."
                                    ),
                                )
                            with c2:
                                trig_cfg["window_minutes"] = st.number_input(
                                    "Window (min)",
                                    min_value=1,
                                    max_value=60,
                                    value=int(prev_cfg.get("window_minutes", 10)),
                                    key=f"rb_{trig_key}_win",
                                )
                        rollback_trigger_configs[trig_key] = trig_cfg
                    else:
                        rollback_trigger_configs[trig_key] = prev_cfg

        rollback_error_threshold = rollback_trigger_configs.get("inference_errors", {}).get("error_count", 10)
        rollback_time_window_minutes = rollback_trigger_configs.get("inference_errors", {}).get("window_minutes", 5)

    st.markdown("---")
    st.markdown("**Traffic & Staging**")
    st.info(
        "Shadow mode runs first (zero traffic impact — requests are duplicated, responses discarded, "
        "metrics collected). Once shadow completes, canary begins routing live traffic at the configured "
        "percentage. They are sequential, not simultaneous.",
        icon="ℹ️",
    )

    col5, col6 = st.columns(2)
    with col5:
        shadow_mode = st.checkbox(
            "Run in shadow mode before serving traffic",
            value=prev.get("shadow_mode", True),
            help="New model runs alongside current, collecting metrics with no traffic impact.",
        )
        shadow_mode_duration_days = 7
        shadow_indefinitely = False
        if shadow_mode:
            shadow_indefinitely = st.checkbox(
                "Shadow production indefinitely (never graduate to canary)",
                value=prev.get("shadow_indefinitely", False),
                help=(
                    "Model stays in shadow mode permanently — useful for high-risk models "
                    "where live traffic exposure is never acceptable."
                ),
            )
            if not shadow_indefinitely:
                shadow_mode_duration_days = st.number_input(
                    "Shadow duration (days)",
                    min_value=1,
                    max_value=365,
                    value=int(prev.get("shadow_mode_duration_days", 7)),
                )
            else:
                st.caption(
                    "No canary graduation — model observes production traffic indefinitely "
                    "without serving live predictions."
                )

    with col6:
        canary_percentage = st.slider(
            "Canary traffic %",
            min_value=0,
            max_value=50,
            value=int(prev.get("canary_percentage", 10)) if not shadow_indefinitely else 0,
            step=5,
            help="After shadow completes, route this % of traffic to the new model before full promotion. 0 = direct.",
            disabled=shadow_indefinitely,
        )

    data = {
        "retraining_strategy": retraining_strategy,
        "retraining_schedule": retraining_schedule if retraining_strategy in ("scheduled", "hybrid") else "0 2 * * *",
        "retraining_timezone": retraining_timezone,
        "retraining_drift_threshold": retraining_drift_threshold
        if retraining_strategy in ("on_drift", "hybrid")
        else 5.0,
        "drift_field_configs": drift_field_configs,
        "rollback_enabled": rollback_enabled,
        "rollback_trigger_types": rollback_trigger_types,
        "rollback_trigger_configs": rollback_trigger_configs,
        "rollback_error_threshold": rollback_error_threshold,
        "rollback_time_window_minutes": rollback_time_window_minutes,
        "canary_percentage": float(canary_percentage),
        "shadow_mode": shadow_mode,
        "shadow_mode_duration_days": shadow_mode_duration_days,
        "shadow_indefinitely": shadow_indefinitely,
    }

    errors = iv.validate_step(5, data)
    _validation_box(errors)
    _nav(5, errors, data)


# ── Step 6: Monitoring ────────────────────────────────────────────────────────


def _step6() -> None:
    _progress_header(6, "Monitoring & Alerts")

    prev = iv.get_step_data(st.session_state, 6)

    st.markdown("**What to monitor**")
    col1, col2, col3 = st.columns(3)
    with col1:
        monitor_data_drift = st.checkbox(
            "Input data drift",
            value=prev.get("monitor_data_drift", True),
            help="Alert when feature distributions shift from training baseline (KS test).",
        )
    with col2:
        monitor_performance_drift = st.checkbox(
            "Model performance",
            value=prev.get("monitor_performance_drift", True),
            help="Alert when the primary metric drops past threshold.",
        )
    with col3:
        monitor_endpoint_uptime = st.checkbox(
            "Endpoint uptime",
            value=prev.get("monitor_endpoint_uptime", True),
            help="Alert if the serving endpoint becomes unreachable.",
        )

    st.markdown("---")
    st.markdown("**Performance metrics to monitor**")
    st.caption("Select all metrics to track. Configure an individual alert threshold for each.")

    perf_opts = list(iv.PERFORMANCE_METRICS.keys())
    prev_metric_types = prev.get("performance_metric_types", [prev.get("performance_metric_type", "accuracy")])
    if isinstance(prev_metric_types, str):
        prev_metric_types = [prev_metric_types]
    performance_metric_types = st.multiselect(
        "Metrics",
        options=perf_opts,
        default=[m for m in prev_metric_types if m in perf_opts],
        format_func=lambda k: iv.PERFORMANCE_METRICS[k],
        label_visibility="collapsed",
    )
    if not performance_metric_types:
        performance_metric_types = ["accuracy"]
        st.caption("Defaulting to Accuracy.")

    # Global fallback threshold
    performance_alert_threshold_pct = st.slider(
        "Default alert threshold — alert when metric drops more than (%)",
        min_value=1.0,
        max_value=30.0,
        value=float(prev.get("performance_alert_threshold_pct", prev.get("alert_threshold_deviation_pct", 5.0))),
        step=0.5,
    )

    # Per-metric thresholds
    prev_metric_thresholds: dict[str, float] = prev.get("performance_alert_thresholds", {})
    performance_alert_thresholds: dict[str, float] = {}
    if len(performance_metric_types) > 1:
        st.caption("Override threshold per metric (leave at 0 to use the default above):")
        for metric in performance_metric_types:
            c_label, c_thresh = st.columns([4, 2])
            with c_label:
                st.caption(iv.PERFORMANCE_METRICS[metric])
            with c_thresh:
                thresh = st.number_input(
                    "Threshold %",
                    min_value=0.0,
                    max_value=50.0,
                    value=float(prev_metric_thresholds.get(metric, 0.0)),
                    step=0.5,
                    key=f"perf_thresh_{metric}",
                    label_visibility="collapsed",
                )
                performance_alert_thresholds[metric] = thresh if thresh > 0 else performance_alert_threshold_pct

    # Backward-compat single metric
    performance_metric_type = performance_metric_types[0] if performance_metric_types else "accuracy"

    custom_metrics = st.text_area(
        "Custom metrics to monitor (optional)",
        value=prev.get("custom_monitoring_metrics", ""),
        placeholder="True positive rate > 0.90 for fraud detection",
        height=60,
        help="Free-text description of domain-specific metrics. Implemented in generated src/evaluate.py stubs.",
    )

    st.markdown("---")
    st.markdown("**Alert destinations**")
    st.caption("Select all channels that should receive alerts. Configure details for each.")

    dest_options = ["email", "slack", "teams"]
    prev_configs = prev.get("alert_destination_configs", [])
    prev_dests = (
        [c.get("destination") for c in prev_configs] if prev_configs else prev.get("alert_destinations", ["email"])
    )

    alert_destinations = st.multiselect(
        "Send alerts to",
        options=dest_options,
        default=[d for d in prev_dests if d in dest_options],
        format_func=lambda x: {"email": "Email", "slack": "Slack", "teams": "Microsoft Teams"}.get(x, x),
        label_visibility="collapsed",
    )

    # Rebuild lookup of previous config by destination
    prev_config_map = {c["destination"]: c for c in prev_configs}

    alert_destination_configs: list[dict] = []
    for dest in alert_destinations:
        with st.container(border=True):
            prev_dest = prev_config_map.get(dest, {})
            if dest == "email":
                st.caption("**Email**")
                emails_raw = st.text_input(
                    "Recipient email addresses",
                    value=", ".join(prev_dest.get("email_addresses", [])),
                    placeholder="mlops-alerts@company.com, oncall@company.com",
                    key="alert_emails",
                    help="Comma-separated list of email recipients.",
                )
                emails = [e.strip() for e in emails_raw.split(",") if e.strip()]
                alert_destination_configs.append({"destination": "email", "email_addresses": emails})

            elif dest == "slack":
                st.caption("**Slack**")
                channel = st.text_input(
                    "Channel name",
                    value=prev_dest.get("channel_name", ""),
                    placeholder="#mlops-alerts",
                    key="alert_slack_channel",
                    help="The Slack channel that will receive alert messages.",
                )
                alert_destination_configs.append({"destination": "slack", "channel_name": channel})

            elif dest == "teams":
                st.caption("**Microsoft Teams**")
                channel = st.text_input(
                    "Team / channel",
                    value=prev_dest.get("channel_name", ""),
                    placeholder="MLOps Alerts > General",
                    key="alert_teams_channel",
                    help="Teams channel or team name that will receive notifications.",
                )
                alert_destination_configs.append({"destination": "teams", "channel_name": channel})

    if not alert_destination_configs:
        alert_destination_configs = [{"destination": "email", "email_addresses": []}]

    data = {
        "monitor_data_drift": monitor_data_drift,
        "monitor_performance_drift": monitor_performance_drift,
        "monitor_endpoint_uptime": monitor_endpoint_uptime,
        "performance_metric_type": performance_metric_type,
        "performance_metric_types": performance_metric_types,
        "performance_alert_threshold_pct": performance_alert_threshold_pct,
        "performance_alert_thresholds": performance_alert_thresholds,
        "alert_threshold_deviation_pct": performance_alert_threshold_pct,  # compat alias
        "custom_monitoring_metrics": custom_metrics.strip(),
        "alert_destination_configs": alert_destination_configs,
        "alert_destinations": alert_destinations,  # kept for downstream compat
    }

    errors = iv.validate_step(6, data)
    _validation_box(errors)
    _nav(6, errors, data)


# ── Step 7: Approval Gates ────────────────────────────────────────────────────


def _step7() -> None:
    _progress_header(7, "Approval Gates")

    prev = iv.get_step_data(st.session_state, 7)

    st.markdown(
        "The following gates are **required for all models** and cannot be disabled. "
        "You may adjust the reviewer count and minimum test coverage below."
    )
    st.markdown("")

    # All required approval gates — locked on, cannot be disabled
    _REQUIRED_GATES = [
        ("Code review", "PR must pass peer review before merging to main."),
        ("Security scan (pip-audit)", "Fails if critical CVEs found in dependencies. Weekly rescan in production."),
        ("End-to-end test in staging", "Model must successfully train and serve predictions in staging."),
        ("Legal / fairness review", "Legal team reviews fairness test results before production deployment."),
        ("Business stakeholder approval", "Business owner sign-off required before going live."),
        ("Compliance review", "Compliance team confirms adherence to internal policies and regulatory obligations."),
        (
            "Internal audit sign-off",
            "Audit team verifies controls, lineage documentation, and approval evidence before promotion.",
        ),
    ]

    with st.container(border=True):
        st.markdown(
            '<span style="font-size:11px;font-weight:600;text-transform:uppercase;'
            'letter-spacing:.12em;color:#64748b">Required gates (locked)</span>',
            unsafe_allow_html=True,
        )
        for gate_name, gate_desc in _REQUIRED_GATES:
            st.markdown(
                f'<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;'
                f'border-bottom:1px solid #1a2740">'
                f'<span style="color:#5eead4;font-size:14px;flex:none">✓</span>'
                f'<div><span style="font-size:13px;color:#a9b6cc;font-weight:500">{gate_name}</span>'
                f'<br><span style="font-size:12px;color:#46546e">{gate_desc}</span></div>'
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("")
    col1, col2 = st.columns(2)

    with col1:
        code_review_count = st.number_input(
            "Required code reviewers (minimum 1)",
            min_value=1,
            max_value=10,
            value=int(prev.get("code_review_count", 2)),
            help="Sets GitHub branch protection required_approving_review_count.",
        )

    with col2:
        testing_threshold_pct = st.slider(
            "Minimum test coverage (%)",
            min_value=50,
            max_value=100,
            value=int(prev.get("testing_threshold_pct", 100)),
            help="Sets --cov-fail-under in the generated test.yml CI gate.",
        )
        if testing_threshold_pct < 100:
            st.warning(
                f"Coverage below 100% ({testing_threshold_pct}%) requires DS + MLOps override approval.",
                icon="⚠️",
            )

    # ── Approver contact emails ────────────────────────────────────────────────
    st.markdown("")
    st.markdown("**Approver contacts**")
    st.caption(
        "Optional — pre-fill who will be notified for each required sign-off. "
        "These are written into the generated `.mlops/approval_record.json` and used in CI/CD notifications."
    )

    with st.container(border=True):
        contact_pairs = [
            ("legal_contact_email", "Legal / Fairness contact"),
            ("business_contact_email", "Business stakeholder contact"),
            ("security_contact_email", "Security team contact"),
            ("compliance_contact_email", "Compliance team contact"),
            ("internal_audit_contact_email", "Internal audit contact"),
        ]
        col_a, col_b = st.columns(2)
        for idx, (field_key, label) in enumerate(contact_pairs):
            target_col = col_a if idx % 2 == 0 else col_b
            with target_col:
                prev.setdefault(field_key, "")
                prev[field_key] = st.text_input(
                    label,
                    value=prev.get(field_key, ""),
                    placeholder="name@company.com",
                    key=f"contact_{field_key}",
                )

    # ── Manifest hash info ─────────────────────────────────────────────────────
    st.info(
        "When you create this project, all wizard responses are hashed (SHA-256) to produce a unique "
        "**manifest identifier**. Every approval sign-off references this hash, so auditors can verify "
        "exactly what configuration each person approved. If you later make substantive model changes "
        "(new features, architecture edits), CI/CD will require new sign-offs and show approvers a diff "
        "against the previously approved state.",
        icon="🔒",
    )

    data = {
        "code_review_count": code_review_count,
        "testing_threshold_pct": testing_threshold_pct,
        # Contact emails for CI/CD notification routing
        "legal_contact_email": prev.get("legal_contact_email", ""),
        "business_contact_email": prev.get("business_contact_email", ""),
        "security_contact_email": prev.get("security_contact_email", ""),
        "compliance_contact_email": prev.get("compliance_contact_email", ""),
        "internal_audit_contact_email": prev.get("internal_audit_contact_email", ""),
        # Fixed gates for downstream consumers
        "require_code_review": True,
        "require_legal_review": True,
        "require_business_approval": True,
        "require_security_scan": True,
        "require_end_to_end_test": True,
        "require_compliance_review": True,
        "require_internal_audit": True,
    }

    errors = iv.validate_step(7, data)
    _validation_box(errors)
    _nav(7, errors, data)


# ── Review & Create ───────────────────────────────────────────────────────────


def _review() -> None:
    st.markdown(
        page_header("Guided Setup", "Review & Create", "Confirm your configuration before generating infrastructure."),
        unsafe_allow_html=True,
    )
    st.progress(1.0)
    st.markdown("---")

    all_responses = iv.get_all_responses(st.session_state)
    s1 = iv.get_step_data(st.session_state, 1)
    s2 = iv.get_step_data(st.session_state, 2)
    s3 = iv.get_step_data(st.session_state, 3)
    s4 = iv.get_step_data(st.session_state, 4)
    s5 = iv.get_step_data(st.session_state, 5)
    s6 = iv.get_step_data(st.session_state, 6)
    s7 = iv.get_step_data(st.session_state, 7)

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("**✓ Basics**")
            st.write(f"**{s1.get('project_name', '—')}**")
            st.caption(f"Owner: {s1.get('owner_email', '—')} · Team: {s1.get('team_name', '—')}")
            st.caption(f"Goal: {s1.get('success_metric', '—')[:80]}")

        with st.container(border=True):
            st.markdown("**✓ Model**")
            inference = s2.get("inference_type", "—")
            freq = s2.get("batch_frequency", "")
            label = f"{inference}" + (f" ({freq})" if freq else "")
            st.caption(f"Inference: {label}")
            frameworks = s2.get("model_frameworks", [])
            st.caption(f"Framework(s): {', '.join(frameworks) if frameworks else '—'}")
            if s2.get("sla_latency_ms"):
                st.caption(f"Latency: p95 ≤ {s2['sla_latency_ms']}ms · Uptime: {s2.get('sla_uptime_pct', 99.99)}%")
            if s2.get("batch_schedule"):
                tz = s2.get("retraining_timezone", "UTC")
                st.caption(f"Schedule: `{s2['batch_schedule']}` ({tz})")

        with st.container(border=True):
            st.markdown("**✓ Data**")
            if s3.get("data_complete", True):
                datasets = s3.get("training_datasets", [])
                st.caption(f"Source(s): {len(datasets)} table{'s' if len(datasets) != 1 else ''}")
                st.caption(f"Target: {s3.get('target_variable', '—')}")
                feats = s3.get("feature_columns", [])
                st.caption(f"Features: {len(feats)} column{'s' if len(feats) != 1 else ''}")
                st.caption(f"Classification: {s3.get('data_classification', 'internal')}")
                if s3.get("contains_pii"):
                    pii_cols = s3.get("pii_columns", [])
                    st.caption(f"PII: {', '.join(pii_cols)}")
            else:
                st.caption("Data specs deferred — will be completed when datasets are ready.")

        with st.container(border=True):
            st.markdown("**✓ Governance**")
            attrs = s4.get("fairness_attributes", [])
            if attrs:
                st.caption(f"Protected: {', '.join(attrs)}")
            elif s4.get("fairness_override_requested"):
                st.caption("Override requested — no protected attributes")
            frameworks_fair = s4.get("bias_test_types", [])
            st.caption(f"Frameworks: {', '.join(frameworks_fair)}")
            st.caption(f"Max disparity: ≤{s4.get('fairness_threshold_pct', 10)}%")
            proxies = s4.get("proxy_variables", [])
            if proxies:
                st.caption(f"Proxy variables: {len(proxies)} defined")

    with col2:
        with st.container(border=True):
            st.markdown("**✓ Deployment**")
            strategy = s5.get("retraining_strategy", "hybrid")
            st.caption(f"Retraining: {strategy}")
            if s5.get("retraining_schedule") and strategy in ("scheduled", "hybrid"):
                tz = s5.get("retraining_timezone", "UTC")
                st.caption(f"Schedule: `{s5['retraining_schedule']}` ({tz})")
            if s5.get("shadow_mode"):
                st.caption(f"Shadow mode: {s5.get('shadow_mode_duration_days', 7)} days → then canary")
            canary = s5.get("canary_percentage", 0)
            st.caption(f"Canary: {int(canary)}% traffic rollout" if canary else "Canary: direct deployment")
            rb_triggers = s5.get("rollback_trigger_types", [])
            if rb_triggers and s5.get("rollback_enabled"):
                st.caption(f"Rollback triggers: {', '.join(rb_triggers)}")

        with st.container(border=True):
            st.markdown("**✓ Monitoring**")
            monitors = []
            if s6.get("monitor_data_drift"):
                monitors.append("data drift")
            if s6.get("monitor_performance_drift"):
                monitors.append("performance")
            if s6.get("monitor_endpoint_uptime"):
                monitors.append("uptime")
            st.caption(f"Monitoring: {', '.join(monitors)}")
            perf_metric = s6.get("performance_metric_type", "accuracy")
            perf_thresh = s6.get("performance_alert_threshold_pct", 5.0)
            st.caption(f"Primary metric: {perf_metric} (alert if >{perf_thresh}% drop)")
            configs = s6.get("alert_destination_configs", [])
            dest_labels = [c["destination"] for c in configs]
            st.caption(f"Alerts via: {', '.join(dest_labels)}")

        with st.container(border=True):
            st.markdown("**✓ Approval Gates**")
            for gate in [
                "Code review",
                "Security scan",
                "E2E staging test",
                "Legal / fairness review",
                "Business approval",
                "Compliance review",
                "Internal audit sign-off",
            ]:
                st.caption(f"✓ {gate}")
            st.caption(f"Reviewers: {s7.get('code_review_count', 2)}")
            st.caption(f"Test coverage: {s7.get('testing_threshold_pct', 100)}% minimum")
            contacts = [
                (label, s7.get(key, ""))
                for key, label in [
                    ("legal_contact_email", "Legal"),
                    ("compliance_contact_email", "Compliance"),
                    ("internal_audit_contact_email", "Audit"),
                ]
                if s7.get(key)
            ]
            for label, email in contacts:
                st.caption(f"{label}: {email}")

    st.markdown("---")
    st.markdown("**What happens next:**")
    project_name = s1.get("project_name", "your-project")
    cfg = get_config()
    github_org = cfg.github_org or "your-org"
    items = [
        f"GitHub repo created: `github.com/{github_org}/{project_name}`",
        "Training skeleton generated (`src/train.py`, `src/preprocess.py`, tests/)",
        "CI/CD pipelines configured in `.github/workflows/`",
        f"UC schemas created: `{cfg.catalog}.{project_name}_dev` / `_staging` / `_prod`",
        "Service account and secret scope provisioned",
        "Monitoring dashboards and Databricks Workflows deployed",
    ]
    for item in items:
        st.write(f"1. {item}")

    st.markdown("---")
    col_back, col_spacer, col_create = st.columns([1, 4, 1])
    with col_back:
        if st.button("← Back", use_container_width=True):
            iv.set_step(st.session_state, iv.TOTAL_STEPS)
            st.rerun()
    with col_create:
        if st.button("✓ Create Project!", use_container_width=True, type="primary"):
            _create_project(all_responses, s1)


def _create_project(all_responses: dict, s1: dict) -> None:
    cfg = get_config()

    if not cfg.is_connected:
        st.error("Not connected to Databricks. Check your environment variables.", icon="❌")
        return

    project_name = s1["project_name"]
    owner_email = s1["owner_email"]

    with st.spinner("Creating project infrastructure..."):
        try:
            from services.generator_service import ProjectInfrastructureGenerator
            from services.state_service import StateService

            svc = StateService()

            project_id = svc.create_project(
                project_name=project_name,
                owner_email=owner_email,
                team_name=s1["team_name"],
                problem_statement=s1["problem_statement"],
                created_by=owner_email,
            )
            svc.save_project_config(
                project_id=project_id,
                interview_responses=all_responses,
                created_by=owner_email,
            )
            svc.update_project_status(project_id, "development", owner_email)

            # §20.1: record tier + packs on the project row (audited); sync
            # keeps mlops.policy_packs consistent with the YAML source of truth
            try:
                from services.policy_pack_service import PolicyPackService

                policy = PolicyPackService(state=svc)
                policy.sync_packs()
                policy.assign_to_project(
                    project_id,
                    risk_tier=all_responses.get("risk_tier", ""),
                    pack_ids=all_responses.get("applied_policy_packs", []),
                    justification=all_responses.get("risk_tier_justification", ""),
                    actor_email=owner_email,
                )
            except Exception as exc:
                st.warning(f"Risk tier could not be recorded: {exc}", icon="⚠️")

            gen = ProjectInfrastructureGenerator(cfg)
            gen_result = gen.generate(project_name, owner_email, all_responses)

            if gen_result.github_repo_url:
                svc.update_project_github(
                    project_id,
                    repo_url=gen_result.github_repo_url,
                    repo_name=gen_result.github_repo_name,
                    updated_by=owner_email,
                )
            if gen_result.uc_schema_dev:
                svc.update_project_schemas(
                    project_id,
                    uc_schema_dev=gen_result.uc_schema_dev,
                    uc_schema_staging=gen_result.uc_schema_staging,
                    uc_schema_prod=gen_result.uc_schema_prod,
                    mlflow_experiment_id=gen_result.mlflow_experiment_id,
                    secret_scope_name=gen_result.secret_scope_name,
                    updated_by=owner_email,
                )

            st.success(f"**Project `{project_name}` created!** (ID: `{project_id}`)", icon="✅")
            st.markdown("**Infrastructure steps:**")
            for step in gen_result.steps:
                icon = "✅" if step["status"] == "ok" else ("⏭️" if step["status"] == "skipped" else "⚠️")
                label = step["name"].replace("_", " ").title()
                detail = f" — {step['detail'][:80]}" if step.get("detail") else ""
                st.write(f"{icon} {label}{detail}")

            if gen_result.github_repo_url:
                st.link_button("Open GitHub Repo ↗", gen_result.github_repo_url)

            st.session_state["last_created_project_id"] = project_id
            for _key in [
                iv.INTERVIEW_KEY,
                iv.CURRENT_STEP_KEY,
                "step3_datasets",
                "step3_inferred_columns",
                "step3_inferred_types",
                "step3_pii_results",
                "step3_pii_suggestions",
                "step3_pii_error",
                "step3_infer_error",
                "step4_proxies",
            ]:
                st.session_state.pop(_key, None)

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("View Projects", use_container_width=True):
                    st.switch_page("pages/01_projects.py")
            with col_b:
                if st.button("Open Dashboard", use_container_width=True, type="primary"):
                    st.session_state["dashboard_project_id"] = project_id
                    st.switch_page("pages/06_project_dashboard.py")

        except Exception as exc:
            st.error(f"Project creation failed: {exc}", icon="❌")
            import traceback

            with st.expander("Error details"):
                st.code(traceback.format_exc())


# ── Router ────────────────────────────────────────────────────────────────────

iv.init_session(st.session_state)

step = iv.get_step(st.session_state)
_completed = iv.completed_steps(st.session_state)
render_sidebar(
    extra_html=(
        '<div style="margin-top:16px;padding-top:16px;border-top:1px solid #1a2740">'
        + wizard_steps(step, _completed)
        + "</div>"
    )
)

_STEP_RENDERERS = {
    1: _step1,
    2: _step2,
    3: _step3,
    4: _step4,
    5: _step5,
    6: _step6,
    7: _step7,
}

if step > iv.TOTAL_STEPS:
    _review()
elif step in _STEP_RENDERERS:
    _STEP_RENDERERS[step]()
