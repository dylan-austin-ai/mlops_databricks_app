"""Feature Catalog — cross-project feature discovery and contract versioning (§8.5, §8.6)."""

from __future__ import annotations

import streamlit as st

from components.theme import apply_theme, page_header, render_sidebar
from config import get_config

st.set_page_config(page_title="Feature Catalog — MLOps", page_icon="🧩", layout="wide")
apply_theme()


def _results_table(rows: list[dict]) -> None:
    if not rows:
        st.markdown(
            """
<div style="display:flex;flex-direction:column;align-items:center;gap:12px;
            padding:64px 24px;text-align:center;
            border:1px dashed #2f4368;border-radius:8px;background:#070a12">
  <div style="font-size:24px">🧩</div>
  <div style="font-size:17px;font-weight:600;color:#e2e8f0">No features found</div>
  <div style="font-size:13px;color:#64748b">Search before declaring a new feature —
  reuse beats reinvention (§8.5).</div>
</div>""",
            unsafe_allow_html=True,
        )
        return
    st.dataframe(
        [
            {
                "Feature": r.get("feature_name", "—"),
                "Description": (r.get("feature_description") or "")[:80],
                "Table": r.get("feature_table_name", "—"),
                "Owner team": r.get("owner_team", "—"),
                "Version": r.get("feature_version", "—"),
                "Shared": "yes" if r.get("is_shared") in (True, "true") else "no",
                "Used by N models": int(r.get("used_by_models") or 0),
                "Freshness (h)": r.get("freshness_hours", "—"),
            }
            for r in rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def _version_change_panel(svc) -> None:
    from services.feature_contract_service import FeatureContractError

    st.caption(
        "Breaking changes to shared features require acknowledgment from every "
        "consuming project before release (§8.6) — notify-after-the-fact is not enough."
    )
    change_id = st.text_input("Change ID", key="fc_change_id", placeholder="uuid of a proposed change")
    if not change_id:
        return
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Show pending acknowledgments", key="fc_pending"):
            try:
                missing = svc.pending_acks(change_id)
                if missing:
                    st.warning(f"Awaiting acks from: {', '.join(missing)}", icon="⏳")
                else:
                    st.success("All consumers acknowledged — ready to release.", icon="✅")
            except FeatureContractError as exc:
                st.error(str(exc))
    with col_b:
        actor = st.text_input("Your email", key="fc_actor", placeholder="you@company.com")
        if st.button("Release change", key="fc_release", type="primary"):
            if not actor or "@" not in actor:
                st.error("Enter a valid email address.", icon="❌")
            else:
                try:
                    svc.release(change_id, actor)
                    st.success("Change released; feature version bumped.", icon="✅")
                except FeatureContractError as exc:
                    st.error(str(exc), icon="🚫")


def main() -> None:
    render_sidebar()
    st.markdown(
        page_header(
            "Reuse, Not Reinvention",
            "Feature Catalog",
            "Find existing features before building new ones — usage counts come from live lineage.",
        ),
        unsafe_allow_html=True,
    )

    cfg = get_config()
    if not cfg.is_connected:
        st.warning("Connect to Databricks to browse the feature catalog.", icon="⚠️")
        return

    try:
        from services.feature_contract_service import FeatureContractService

        svc = FeatureContractService()
    except Exception as exc:
        st.error(f"Failed to initialize feature catalog: {exc}")
        return

    col_q, col_s = st.columns([3, 1])
    with col_q:
        query = st.text_input("Search", placeholder="name, description, or owning team")
    with col_s:
        shared_only = st.toggle("Shared only", value=False)

    try:
        rows = svc.catalog_search(query, shared_only=shared_only)
    except Exception as exc:
        st.error(f"Search failed: {exc}")
        return

    _results_table(rows)

    with st.expander("Contract version changes (§8.6)", expanded=False):
        _version_change_panel(svc)


main()
