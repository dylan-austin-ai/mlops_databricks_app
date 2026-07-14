"""DemoStore — in-memory, session-scoped state for Demo Mode.

Everything lives in st.session_state so Demo Mode never touches a real SQL
warehouse, resets when the browser session ends, and needs no setup of any
kind (owner request: droppable into a bare Databricks Apps deployment with
zero config).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import streamlit as st

_STORE_KEY = "_demo_store"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _empty_store() -> dict[str, Any]:
    return {
        "projects": {},
        "project_configs": {},
        "infrastructure_actions": {},
        "training_data_snapshots": {},
        "budget_alerts": {},
    }


def _seed(store: dict[str, Any]) -> None:
    """One example in-progress project so Home isn't empty before the
    visitor has run the wizard themselves."""
    project_id = _uuid()
    now = _now()
    store["projects"][project_id] = {
        "project_id": project_id,
        "project_name": "churn_prediction",
        "project_description": "Identify customers likely to churn in the next 30 days to enable proactive retention.",
        "created_timestamp": now,
        "created_by": "demo@example.com",
        "owner_email": "demo@example.com",
        "team_name": "retention_team",
        "github_repo_url": "https://github.com/demo-org/churn-prediction",
        "github_repo_name": "churn-prediction",
        "mlflow_experiment_id": "demo-10001",
        "status": "development",
        "uc_schema_dev": "mlops.churn_prediction_dev",
        "uc_schema_staging": "mlops.churn_prediction_staging",
        "uc_schema_prod": "mlops.churn_prediction_prod",
        "secret_scope_name": "",
        "budget_policy_id": "demo-budget-churn_prediction",
        "last_updated": now,
        "last_updated_by": "demo@example.com",
        "is_archived": False,
    }
    store["infrastructure_actions"][project_id] = [
        {
            "action_id": _uuid(),
            "project_id": project_id,
            "action_name": name,
            "status": "ok",
            "detail": detail,
            "resource_id": resource_id,
            "content_hash": None,
            "created_at": now,
        }
        for name, detail, resource_id in [
            (
                "github_repo",
                "(demo) created https://github.com/demo-org/churn-prediction",
                "https://github.com/demo-org/churn-prediction",
            ),
            (
                "uc_schemas",
                "(demo) created mlops.churn_prediction_dev/_staging/_prod",
                "mlops.churn_prediction_dev",
            ),
            (
                "uc_volumes",
                "(demo) created artifacts volume(s)",
                "mlops.churn_prediction_dev.artifacts",
            ),
            (
                "mlflow_experiment",
                "(demo) created /Shared/mlops/churn_prediction",
                "demo-10001",
            ),
        ]
    ]


def get_store() -> dict[str, Any]:
    if _STORE_KEY not in st.session_state:
        store = _empty_store()
        _seed(store)
        st.session_state[_STORE_KEY] = store
    return st.session_state[_STORE_KEY]


def reset_store() -> None:
    store = _empty_store()
    _seed(store)
    st.session_state[_STORE_KEY] = store
