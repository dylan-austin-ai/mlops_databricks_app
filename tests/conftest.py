"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the app root importable without installation
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def valid_step1() -> dict:
    return {
        "project_name": "customer_churn",
        "problem_statement": "Predict which customers will churn in the next 30 days",
        "success_metric": "AUC-ROC >= 0.85 on holdout validation set",
        "team_name": "retention_team",
        "owner_email": "alice@company.com",
    }


@pytest.fixture
def valid_step2_batch() -> dict:
    return {
        "inference_type": "batch",
        "batch_frequency": "daily",
        "model_frameworks": ["xgboost"],
    }


@pytest.fixture
def valid_step2_realtime() -> dict:
    return {
        "inference_type": "real_time",
        "sla_latency_ms": 200,
        "sla_uptime_pct": 99.9,
        "expected_qps": 50,
        "model_frameworks": ["sklearn"],
    }


@pytest.fixture
def valid_step3() -> dict:
    return {
        "training_datasets": ["feature_store.customer.training_data"],
        "target_variable": "churn_flag",
        "feature_columns": ["age", "tenure_months", "monthly_charges"],
        "training_data_size_rows": 1_000_000,
        "contains_pii": True,
        "pii_columns": ["customer_id", "email"],
        "data_classification": "internal",
    }


@pytest.fixture
def valid_step4() -> dict:
    return {
        "fairness_attributes": ["Age", "Sex / Gender"],
        "fairness_threshold_pct": 10,
        "bias_test_types": ["aif360", "fairlearn"],
        "data_quality_required_fields": ["age", "monthly_charges"],
        "data_quality_acceptable_issues": [],
        "proxy_variables": [],
        "column_justifications": {},
    }


@pytest.fixture
def valid_step5() -> dict:
    return {
        "retraining_strategy": "hybrid",
        "retraining_schedule": "0 2 * * *",
        "retraining_drift_threshold": 5.0,
        "rollback_enabled": True,
        "rollback_trigger_types": ["inference_errors", "latency_breach"],
        "rollback_error_threshold": 10,
        "rollback_time_window_minutes": 5,
        "canary_percentage": 10.0,
        "shadow_mode": True,
        "shadow_mode_duration_days": 7,
    }


@pytest.fixture
def valid_step6() -> dict:
    return {
        "monitor_data_drift": True,
        "monitor_performance_drift": True,
        "monitor_endpoint_uptime": True,
        "performance_metric_type": "accuracy",
        "performance_alert_threshold_pct": 5.0,
        "custom_monitoring_metrics": "",
        "alert_destination_configs": [{"destination": "email", "email_addresses": ["mlops@company.com"]}],
        "alert_threshold_deviation_pct": 5.0,
    }


@pytest.fixture
def valid_step7() -> dict:
    return {
        "code_review_count": 2,
        "testing_threshold_pct": 100,
    }
