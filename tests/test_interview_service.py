"""Tests for interview_service — all 7 step validators."""

from __future__ import annotations

import pytest

from services.interview_service import (
    validate_step,
    init_session,
    save_step_data,
    get_step_data,
    get_all_responses,
    set_step,
    get_step,
    is_step_complete,
    completed_steps,
    to_project_manifest_kwargs,
    TOTAL_STEPS,
)


# ── Step 1: Basic Info ────────────────────────────────────────────────────────


class TestStep1:
    def test_valid(self, valid_step1):
        assert validate_step(1, valid_step1) == []

    def test_name_too_short(self, valid_step1):
        data = {**valid_step1, "project_name": "ab"}
        errors = validate_step(1, data)
        assert any("project_name" in e for e in errors)

    def test_name_uppercase_normalised(self, valid_step1):
        # Validator lowercases — "MyModel" → "mymodel" which is valid
        data = {**valid_step1, "project_name": "MyModel"}
        errors = validate_step(1, data)
        assert errors == []

    def test_name_spaces_normalised_to_underscores(self, valid_step1):
        # Validator converts spaces to underscores — "my model" → "my_model"
        data = {**valid_step1, "project_name": "my model"}
        errors = validate_step(1, data)
        assert errors == []

    def test_name_leading_underscore_rejected(self, valid_step1):
        data = {**valid_step1, "project_name": "_bad_name"}
        errors = validate_step(1, data)
        assert any("project_name" in e for e in errors)

    def test_problem_statement_too_short(self, valid_step1):
        data = {**valid_step1, "problem_statement": "Too short"}
        errors = validate_step(1, data)
        assert any("problem_statement" in e for e in errors)

    def test_success_metric_too_short(self, valid_step1):
        data = {**valid_step1, "success_metric": "AUC > 0.8"}
        errors = validate_step(1, data)
        assert any("success_metric" in e for e in errors)

    def test_invalid_email(self, valid_step1):
        data = {**valid_step1, "owner_email": "notanemail"}
        errors = validate_step(1, data)
        assert any("owner_email" in e for e in errors)

    def test_missing_team(self, valid_step1):
        data = {**valid_step1, "team_name": ""}
        errors = validate_step(1, data)
        assert len(errors) > 0

    def test_multiple_errors_reported(self):
        errors = validate_step(
            1,
            {
                "project_name": "x",
                "problem_statement": "short",
                "success_metric": "",
                "team_name": "",
                "owner_email": "bad",
            },
        )
        assert len(errors) >= 3


# ── Step 2: Model Specs ───────────────────────────────────────────────────────


class TestStep2:
    def test_valid_batch(self, valid_step2_batch):
        assert validate_step(2, valid_step2_batch) == []

    def test_valid_realtime(self, valid_step2_realtime):
        assert validate_step(2, valid_step2_realtime) == []

    def test_batch_missing_frequency(self):
        errors = validate_step(2, {"inference_type": "batch", "model_frameworks": ["sklearn"]})
        assert any("batch_frequency" in e for e in errors)

    def test_realtime_missing_latency(self):
        errors = validate_step(
            2,
            {
                "inference_type": "real_time",
                "sla_uptime_pct": 99.9,
                "model_frameworks": ["sklearn"],
            },
        )
        assert any("latency" in e.lower() or "sla_latency" in e for e in errors)

    def test_realtime_missing_uptime(self):
        errors = validate_step(
            2,
            {
                "inference_type": "real_time",
                "sla_latency_ms": 200,
                "model_frameworks": ["sklearn"],
            },
        )
        assert any("uptime" in e.lower() or "sla_uptime" in e for e in errors)

    def test_both_requires_batch_freq_and_latency(self):
        errors = validate_step(2, {"inference_type": "both", "model_frameworks": ["xgboost"]})
        assert len(errors) > 0

    def test_invalid_inference_type(self):
        errors = validate_step(
            2,
            {
                "inference_type": "streaming",
                "model_frameworks": ["sklearn"],
            },
        )
        assert len(errors) > 0

    def test_empty_frameworks_rejected(self):
        errors = validate_step(
            2,
            {
                "inference_type": "batch",
                "batch_frequency": "daily",
                "model_frameworks": [],
            },
        )
        assert any("framework" in e.lower() for e in errors)

    def test_multiple_frameworks_valid(self):
        errors = validate_step(
            2,
            {
                "inference_type": "batch",
                "batch_frequency": "daily",
                "model_frameworks": ["sklearn", "xgboost", "lightgbm"],
            },
        )
        assert errors == []


# ── Step 3: Data Specs ────────────────────────────────────────────────────────


class TestStep3:
    def test_valid(self, valid_step3):
        assert validate_step(3, valid_step3) == []

    def test_valid_no_pii(self):
        errors = validate_step(
            3,
            {
                "training_datasets": ["catalog.schema.table"],
                "target_variable": "label",
                "feature_columns": ["col1", "col2"],
                "contains_pii": False,
                "pii_columns": [],
            },
        )
        assert errors == []

    def test_data_complete_false_skips_validation(self):
        # When data_complete=False, all other fields are optional
        errors = validate_step(3, {"data_complete": False})
        assert errors == []

    def test_missing_training_datasets(self, valid_step3):
        data = {**valid_step3, "training_datasets": []}
        errors = validate_step(3, data)
        assert any("dataset" in e.lower() or "training" in e.lower() for e in errors)

    def test_no_feature_columns(self, valid_step3):
        data = {**valid_step3, "feature_columns": []}
        errors = validate_step(3, data)
        assert any("feature column" in e.lower() for e in errors)

    def test_pii_true_but_no_columns(self, valid_step3):
        data = {**valid_step3, "contains_pii": True, "pii_columns": []}
        errors = validate_step(3, data)
        assert any("pii" in e.lower() for e in errors)

    def test_pii_false_empty_columns_ok(self, valid_step3):
        data = {**valid_step3, "contains_pii": False, "pii_columns": []}
        assert validate_step(3, data) == []


# ── Step 4: Governance ────────────────────────────────────────────────────────


class TestStep4:
    def test_valid(self, valid_step4):
        assert validate_step(4, valid_step4) == []

    def test_no_attributes_still_valid(self, valid_step4):
        # Empty fairness_attributes is allowed — DS declares override via fairness_override_requested
        data = {**valid_step4, "fairness_attributes": []}
        errors = validate_step(4, data)
        assert errors == []

    def test_invalid_bias_framework_in_list(self, valid_step4):
        data = {**valid_step4, "bias_test_types": ["unknown_framework"]}
        errors = validate_step(4, data)
        assert len(errors) > 0

    def test_valid_all_bias_frameworks(self, valid_step4):
        data = {**valid_step4, "bias_test_types": ["aif360", "fairlearn", "custom"]}
        assert validate_step(4, data) == []

    def test_threshold_out_of_range(self, valid_step4):
        data = {**valid_step4, "fairness_threshold_pct": 0}
        errors = validate_step(4, data)
        assert any("threshold" in e.lower() for e in errors)


# ── Step 5: Deployment ────────────────────────────────────────────────────────


class TestStep5:
    def test_valid(self, valid_step5):
        assert validate_step(5, valid_step5) == []

    def test_all_strategies_valid(self):
        for strategy in ("manual", "scheduled", "on_drift", "hybrid"):
            errors = validate_step(
                5,
                {
                    "retraining_strategy": strategy,
                    "retraining_schedule": "0 2 * * *",
                    "retraining_drift_threshold": 5.0,
                    "rollback_enabled": False,
                    "rollback_error_threshold": 10,
                    "rollback_time_window_minutes": 5,
                    "canary_percentage": 0.0,
                    "shadow_mode": False,
                    "shadow_mode_duration_days": 7,
                },
            )
            assert errors == [], f"strategy '{strategy}' should be valid"

    def test_invalid_strategy(self):
        errors = validate_step(
            5,
            {
                "retraining_strategy": "always_on",
                "retraining_schedule": "0 2 * * *",
                "retraining_drift_threshold": 5.0,
                "rollback_enabled": False,
                "rollback_error_threshold": 10,
                "rollback_time_window_minutes": 5,
                "canary_percentage": 0.0,
                "shadow_mode": False,
                "shadow_mode_duration_days": 7,
            },
        )
        assert len(errors) > 0


# ── Step 6: Monitoring ────────────────────────────────────────────────────────


class TestStep6:
    def test_valid(self, valid_step6):
        assert validate_step(6, valid_step6) == []

    def test_valid_slack_destination(self):
        errors = validate_step(
            6,
            {
                "monitor_data_drift": True,
                "monitor_performance_drift": True,
                "monitor_endpoint_uptime": False,
                "performance_metric_type": "accuracy",
                "custom_monitoring_metrics": "",
                "alert_destination_configs": [{"destination": "slack", "channel_name": "#mlops-alerts"}],
                "alert_threshold_deviation_pct": 10.0,
            },
        )
        assert errors == []

    def test_valid_teams_destination(self):
        errors = validate_step(
            6,
            {
                "monitor_data_drift": True,
                "monitor_performance_drift": False,
                "monitor_endpoint_uptime": False,
                "performance_metric_type": "auc_roc",
                "custom_monitoring_metrics": "",
                "alert_destination_configs": [{"destination": "teams", "channel_name": "MLOps"}],
                "alert_threshold_deviation_pct": 5.0,
            },
        )
        assert errors == []

    def test_empty_alert_destination_configs_rejected(self, valid_step6):
        data = {**valid_step6, "alert_destination_configs": []}
        errors = validate_step(6, data)
        assert any("alert_destination" in e.lower() for e in errors)

    def test_invalid_performance_metric(self, valid_step6):
        data = {**valid_step6, "performance_metric_type": "not_a_metric"}
        errors = validate_step(6, data)
        assert len(errors) > 0

    def test_multiple_destinations_valid(self, valid_step6):
        data = {
            **valid_step6,
            "alert_destination_configs": [
                {"destination": "email", "email_addresses": ["a@b.com"]},
                {"destination": "slack", "channel_name": "#alerts"},
                {"destination": "teams", "channel_name": "MLOps"},
            ],
        }
        assert validate_step(6, data) == []


# ── Step 7: Approval Gates ────────────────────────────────────────────────────


class TestStep7:
    def test_valid(self, valid_step7):
        assert validate_step(7, valid_step7) == []

    def test_coverage_below_50(self, valid_step7):
        data = {**valid_step7, "testing_threshold_pct": 40}
        errors = validate_step(7, data)
        assert any("testing_threshold_pct" in e for e in errors)

    def test_coverage_above_100(self, valid_step7):
        data = {**valid_step7, "testing_threshold_pct": 105}
        errors = validate_step(7, data)
        assert any("testing_threshold_pct" in e for e in errors)

    def test_reviewer_count_zero(self, valid_step7):
        data = {**valid_step7, "code_review_count": 0}
        errors = validate_step(7, data)
        assert any("code_review_count" in e for e in errors)

    def test_reviewer_count_eleven(self, valid_step7):
        data = {**valid_step7, "code_review_count": 11}
        errors = validate_step(7, data)
        assert any("code_review_count" in e for e in errors)

    def test_min_one_reviewer_valid(self, valid_step7):
        data = {**valid_step7, "code_review_count": 1}
        assert validate_step(7, data) == []


# ── Unknown step ──────────────────────────────────────────────────────────────


class TestUnknownStep:
    def test_unknown_step_returns_no_errors(self):
        assert validate_step(99, {"anything": "goes"}) == []


# ── Session state helpers ─────────────────────────────────────────────────────


class TestSessionState:
    def test_init_sets_defaults(self):
        state = {}
        init_session(state)
        assert state["interview_step"] == 1
        assert state["interview_data"] == {}

    def test_init_does_not_overwrite_existing(self):
        state = {"interview_step": 3, "interview_data": {"step1": {"x": 1}}}
        init_session(state)
        assert state["interview_step"] == 3
        assert state["interview_data"]["step1"]["x"] == 1

    def test_save_and_get_step_data(self, valid_step1):
        state = {}
        init_session(state)
        save_step_data(state, 1, valid_step1)
        assert get_step_data(state, 1) == valid_step1

    def test_get_missing_step_returns_empty(self):
        state = {}
        init_session(state)
        assert get_step_data(state, 5) == {}

    def test_set_step_clamps_low(self):
        state = {}
        init_session(state)
        set_step(state, 0)
        assert get_step(state) == 1

    def test_set_step_clamps_high(self):
        # set_step allows TOTAL_STEPS+1 so the review page is reachable
        state = {}
        init_session(state)
        set_step(state, 99)
        assert get_step(state) == TOTAL_STEPS + 1

    def test_set_step_review_page_reachable(self):
        state = {}
        init_session(state)
        set_step(state, TOTAL_STEPS + 1)
        assert get_step(state) == TOTAL_STEPS + 1

    def test_is_step_complete_false_when_invalid(self, valid_step1):
        state = {}
        init_session(state)
        bad = {**valid_step1, "project_name": "x"}  # too short
        save_step_data(state, 1, bad)
        assert is_step_complete(state, 1) is False

    def test_is_step_complete_true_when_valid(self, valid_step1):
        state = {}
        init_session(state)
        save_step_data(state, 1, valid_step1)
        assert is_step_complete(state, 1) is True

    def test_completed_steps(self, valid_step1, valid_step2_batch):
        state = {}
        init_session(state)
        save_step_data(state, 1, valid_step1)
        save_step_data(state, 2, valid_step2_batch)
        done = completed_steps(state)
        assert 1 in done
        assert 2 in done
        assert 3 not in done

    def test_get_all_responses_merges_steps(self, valid_step1, valid_step2_batch):
        state = {}
        init_session(state)
        save_step_data(state, 1, valid_step1)
        save_step_data(state, 2, valid_step2_batch)
        merged = get_all_responses(state)
        assert merged["project_name"] == valid_step1["project_name"]
        assert merged["inference_type"] == "batch"


# ── Manifest conversion ───────────────────────────────────────────────────────


class TestToManifestKwargs:
    def test_batch_maps_to_batch_pipeline(self, valid_step1, valid_step2_batch):
        state = {}
        init_session(state)
        save_step_data(state, 1, valid_step1)
        save_step_data(state, 2, valid_step2_batch)
        kwargs = to_project_manifest_kwargs(state)
        assert kwargs["project_type"] == "batch-pipeline"
        assert kwargs["name"] == valid_step1["project_name"]

    def test_realtime_maps_to_realtime_model(self, valid_step1, valid_step2_realtime):
        state = {}
        init_session(state)
        save_step_data(state, 1, valid_step1)
        save_step_data(state, 2, valid_step2_realtime)
        kwargs = to_project_manifest_kwargs(state)
        assert kwargs["project_type"] == "realtime-model"

    def test_frameworks_included_in_kwargs(self, valid_step1, valid_step2_batch):
        state = {}
        init_session(state)
        save_step_data(state, 1, valid_step1)
        save_step_data(state, 2, valid_step2_batch)
        kwargs = to_project_manifest_kwargs(state)
        assert "xgboost" in kwargs["frameworks"]
