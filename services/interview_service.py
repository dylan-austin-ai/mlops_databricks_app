"""Interview step data models and validation.

Process Map order (canonical):
  1. Basic Info      — name, problem, success metric, team, owner
  2. Model Specs     — use case, frameworks, inference type, latency/QPS, schedule
  3. Data Specs      — datasets, schema inference, target, features, PII, classification
  4. Governance      — fairness (always on), proxy vars, quality gates, justifications
  5. Deployment      — retraining, per-field drift, rollback triggers, canary, shadow
  6. Monitoring      — metrics, performance indicator, alert destinations with details
  7. Approval Gates  — reviewer count and coverage only (all gates locked on)
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Constants ─────────────────────────────────────────────────────────────────

PROTECTED_CLASSES = [
    "Race / Ethnicity",
    "Color",
    "Religion",
    "National Origin",
    "Sex / Gender",
    "Age",
    "Disability Status",
    "Genetic Information",
    "Sexual Orientation",
    "Gender Identity",
]

MODEL_FRAMEWORKS = {
    "sklearn": {
        "label": "Scikit-learn",
        "preferred": True,
        "desc": "General-purpose ML. MLflow sklearn flavor; first-class Databricks support.",
    },
    "xgboost": {
        "label": "XGBoost",
        "preferred": True,
        "desc": "Gradient boosting. MLflow xgboost flavor; native Databricks Model Serving.",
    },
    "lightgbm": {
        "label": "LightGBM",
        "preferred": True,
        "desc": "Fast gradient boosting. MLflow lightgbm flavor; native Databricks support.",
    },
    "catboost": {
        "label": "CatBoost",
        "preferred": False,
        "desc": "Gradient boosting with categorical support. Packaged as pyfunc in MLflow.",
    },
    "tensorflow": {
        "label": "TensorFlow / Keras",
        "preferred": False,
        "desc": "Deep learning. MLflow tensorflow flavor; requires custom serving config.",
    },
    "pytorch": {
        "label": "PyTorch",
        "preferred": False,
        "desc": "Deep learning. MLflow pytorch flavor; manual serialization recommended.",
    },
    "huggingface": {
        "label": "Hugging Face",
        "preferred": True,
        "desc": "Transformers / LLMs. MLflow transformers flavor; best with Databricks Model Serving GPU.",
    },
    "statsmodels": {
        "label": "Statsmodels",
        "preferred": False,
        "desc": "Statistical models (GLM, ARIMA, etc.). Packaged as pyfunc.",
    },
    "prophet": {"label": "Prophet", "preferred": False, "desc": "Time-series forecasting. Packaged as pyfunc."},
    "other": {
        "label": "Other",
        "preferred": False,
        "desc": "Custom framework. Must implement MLflow pyfunc interface for Databricks serving.",
    },
}

ROLLBACK_TRIGGER_OPTIONS = {
    "inference_errors": "Inference errors (5xx responses from endpoint)",
    "data_quality": "Data quality failures (input fails contract validation)",
    "latency_breach": "Latency SLA breach (P95 exceeds threshold for sustained period)",
    "prediction_anomaly": "Prediction distribution anomaly (output drift beyond threshold)",
}

PERFORMANCE_METRICS = {
    "accuracy": "Accuracy — fraction of correct predictions",
    "auc_roc": "AUC-ROC — area under receiver operating curve",
    "f1_score": "F1 Score — harmonic mean of precision and recall",
    "precision": "Precision — positive predictive value",
    "recall": "Recall — true positive rate / sensitivity",
    "rmse": "RMSE — root mean squared error (regression)",
    "mae": "MAE — mean absolute error (regression)",
    "error_rate": "Error rate — fraction of failed predictions",
    "custom": "Custom metric — defined in src/evaluate.py",
}


# ── Step models ───────────────────────────────────────────────────────────────


class Step1BasicInfo(BaseModel):
    project_name: str
    problem_statement: str
    success_metric: str
    team_name: str
    owner_email: str
    existing_repo_url: str = ""  # optional — blank = app creates a new repo

    @field_validator("project_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip().lower().replace(" ", "_")
        if not re.match(r"^[a-z0-9][a-z0-9_]{1,48}[a-z0-9]$", v):
            raise ValueError(
                "Name must be 3–50 chars, lowercase alphanumeric + underscores, no leading/trailing underscores."
            )
        return v

    @field_validator("team_name")
    @classmethod
    def validate_team(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Team name is required.")
        return v.strip()

    @field_validator("problem_statement", "success_metric")
    @classmethod
    def min_length(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError("Must be at least 20 characters.")
        return v.strip()

    @field_validator("owner_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("existing_repo_url")
    @classmethod
    def validate_existing_repo_url(cls, v: str) -> str:
        # Same pattern generator_service.py parses at provisioning time —
        # kept in sync deliberately so a URL that passes here won't fail there.
        v = v.strip()
        if v and not re.match(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", v):
            raise ValueError("Must be a https://github.com/<owner>/<repo> URL, or left blank.")
        return v


class Step2ModelSpecs(BaseModel):
    inference_type: Literal["batch", "real_time", "both", "streaming"]
    # Batch
    batch_frequency: Literal["hourly", "daily", "weekly", "monthly", "quarterly"] | None = None
    batch_schedule: str | None = None  # full cron expression including time
    # Real-time
    sla_latency_ms: int | None = None
    sla_uptime_pct: float | None = None  # default 99.99
    expected_qps: int | None = None
    # Streaming — the scorer reads an existing governed table; it never
    # authors the upstream pipeline (§9.4 boundary)
    streaming_source_table: str | None = None
    # Frameworks — multi-select
    model_frameworks: list[str] = []

    @model_validator(mode="after")
    def cross_validate(self) -> Step2ModelSpecs:
        if self.inference_type in ("batch", "both") and not self.batch_frequency:
            raise ValueError("batch_frequency is required for batch inference.")
        if self.inference_type in ("real_time", "both"):
            if self.sla_latency_ms is None:
                raise ValueError("sla_latency_ms is required for real-time inference.")
            if self.sla_uptime_pct is None:
                raise ValueError("sla_uptime_pct is required for real-time inference.")
        if self.inference_type == "streaming":
            parts = (self.streaming_source_table or "").split(".")
            if len(parts) != 3 or not all(parts):
                raise ValueError(
                    "streaming_source_table is required for streaming inference and "
                    "must be fully qualified: catalog.schema.table."
                )
        if not self.model_frameworks:
            raise ValueError("Select at least one model framework.")
        return self


class TrainingDataset(BaseModel):
    location: str
    description: str = ""


class Step3DataSpecs(BaseModel):
    data_complete: bool = True  # False = DS will fill in later
    training_datasets: list[str] = []  # UC paths
    target_variable: str = ""
    feature_columns: list[str] = []
    training_data_size_rows: int | None = None
    contains_pii: bool = False
    pii_columns: list[str] = []
    pii_justifications: dict[str, str] = {}  # column → justification
    pii_suppression_methods: dict[str, list[str]] = {}  # column → "none"|"suppress_logs"|"delta_mask"
    data_classification: str = "internal"  # public|internal|sensitive|restricted
    field_justifications: dict[str, str] = {}  # any scrutinized field → justification
    column_classifications: dict[str, str] = {}  # column → "public"|"internal"|"sensitive"|"restricted"
    sensitive_columns: list[str] = []
    restricted_columns: list[str] = []
    classification_attestations: dict[str, dict] = {}  # column → {decision, notes, timestamp}

    @model_validator(mode="after")
    def validate_when_complete(self) -> Step3DataSpecs:
        if not self.data_complete:
            return self  # skip all validations — DS will fill in later
        if not self.training_datasets:
            raise ValueError("At least one training dataset location is required.")
        if not self.target_variable.strip():
            raise ValueError("Target variable is required.")
        if not self.feature_columns:
            raise ValueError("At least one feature column is required.")
        if self.contains_pii and not self.pii_columns:
            raise ValueError("Specify which columns contain PII.")
        return self


class ProxyVariableSpec(BaseModel):
    column: str
    protected_class: str
    justification: str


class Step4Governance(BaseModel):
    # Fairness is always on — no toggle.
    # Empty fairness_attributes is valid only via override (legal + MLOps sign-off).
    fairness_attributes: list[str] = []
    proxy_variables: list[dict[str, str]] = []  # [{column, protected_class, justification}]
    fairness_threshold_pct: int = 10
    bias_test_types: list[str] = ["aif360", "fairlearn"]  # all selected by default
    column_justifications: dict[str, str] = {}  # col → justification for any scrutinized field
    data_quality_required_fields: list[str] = []
    data_quality_acceptable_issues: list[str] = []
    fairness_override_requested: bool = False  # set when DS declares no protected attributes
    protected_attribute_justifications: dict[str, str] = {}  # attribute → justification text
    governance_attestations: dict[str, dict] = {}  # column → {decision, notes}
    # §20.1: risk tier against org-authored tier definitions only. Governance-
    # consequential (§29.3): an explicit choice plus a one-line justification —
    # validate_default so omission fails, never silently passes.
    risk_tier: str = Field(default="", validate_default=True)
    risk_tier_justification: str = Field(default="", validate_default=True)
    applied_policy_packs: list[str] = Field(default=["generic_tiering_v1"], validate_default=True)

    @field_validator("bias_test_types")
    @classmethod
    def at_least_one_framework(cls, v: list[str]) -> list[str]:
        valid = {"aif360", "fairlearn", "custom"}
        invalid = [x for x in v if x not in valid]
        if invalid:
            raise ValueError(f"Invalid fairness frameworks: {invalid}")
        return v

    @field_validator("fairness_threshold_pct")
    @classmethod
    def validate_threshold(cls, v: int) -> int:
        if not 1 <= v <= 50:
            raise ValueError("Fairness threshold must be between 1 and 50.")
        return v

    @field_validator("risk_tier")
    @classmethod
    def tier_chosen(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Risk tier is required — select the org-defined tier for this model (§20.1).")
        return v

    @field_validator("risk_tier_justification")
    @classmethod
    def tier_justified(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("A one-line justification for the risk tier is required (§29.3).")
        return v

    @field_validator("applied_policy_packs")
    @classmethod
    def at_least_one_pack(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one policy pack must be applied (§20.1).")
        return v


class DriftFieldConfig(BaseModel):
    field_name: str
    threshold: float = 0.1


class Step5Deployment(BaseModel):
    retraining_strategy: Literal["manual", "scheduled", "on_drift", "hybrid"] = "hybrid"
    retraining_schedule: str = "0 2 * * *"
    retraining_timezone: str = "America/New_York"
    drift_field_configs: list[dict[str, Any]] = []  # [{field_name, threshold}]
    retraining_drift_threshold: float = 5.0  # global fallback
    rollback_enabled: bool = True
    rollback_trigger_types: list[str] = ["inference_errors", "latency_breach"]
    rollback_error_threshold: int = 10
    rollback_time_window_minutes: int = 5
    canary_percentage: float = 0.0
    shadow_mode: bool = True
    shadow_mode_duration_days: int = 7
    shadow_indefinitely: bool = False  # never graduate to canary; shadow only
    rollback_trigger_configs: dict[str, dict] = {}  # per-trigger config dicts


class AlertDestinationConfig(BaseModel):
    destination: Literal["email", "slack", "teams"]
    email_addresses: list[str] = []
    channel_name: str = ""
    webhook_url: str = ""


class Step6Monitoring(BaseModel):
    monitor_data_drift: bool = True
    monitor_performance_drift: bool = True
    monitor_endpoint_uptime: bool = True
    performance_metric_type: str = "accuracy"  # which metric to watch
    performance_alert_threshold_pct: float = 5.0  # % drop in primary metric
    performance_metric_types: list[str] = []  # multiselect; non-empty overrides performance_metric_type
    performance_alert_thresholds: dict[str, float] = {}  # metric → alert threshold pct
    custom_monitoring_metrics: str = ""
    alert_destination_configs: list[dict[str, Any]] = []  # [{destination, email_addresses, channel_name}]
    alert_threshold_deviation_pct: float = 5.0  # legacy compat alias

    @field_validator("alert_destination_configs")
    @classmethod
    def at_least_one(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one alert destination is required.")
        return v

    @field_validator("performance_metric_type")
    @classmethod
    def valid_metric(cls, v: str) -> str:
        if v and v not in PERFORMANCE_METRICS:
            raise ValueError(f"Invalid metric: {v}")
        return v


class Step7ApprovalGates(BaseModel):
    # All gates locked ON. Only adjustable: reviewer count and coverage threshold.
    code_review_count: int = 2
    testing_threshold_pct: int = 100
    # Optional suggested contacts for each required approver role
    legal_contact_email: str = ""
    business_contact_email: str = ""
    security_contact_email: str = ""
    compliance_contact_email: str = ""
    internal_audit_contact_email: str = ""

    @field_validator("code_review_count")
    @classmethod
    def min_one_reviewer(cls, v: int) -> int:
        if v < 1:
            raise ValueError("At least 1 code reviewer is required.")
        if v > 10:
            raise ValueError("Maximum 10 reviewers.")
        return v

    @field_validator("testing_threshold_pct")
    @classmethod
    def validate_coverage(cls, v: int) -> int:
        if not 50 <= v <= 100:
            raise ValueError("Test coverage must be between 50 and 100.")
        return v


# ── Session state keys ────────────────────────────────────────────────────────

INTERVIEW_KEY = "interview_data"
CURRENT_STEP_KEY = "interview_step"
TOTAL_STEPS = 7


def init_session(session_state: Any) -> None:
    if INTERVIEW_KEY not in session_state:
        session_state[INTERVIEW_KEY] = {}
    if CURRENT_STEP_KEY not in session_state:
        session_state[CURRENT_STEP_KEY] = 1


def get_step(session_state: Any) -> int:
    return session_state.get(CURRENT_STEP_KEY, 1)


def set_step(session_state: Any, step: int) -> None:
    session_state[CURRENT_STEP_KEY] = max(1, min(step, TOTAL_STEPS + 1))


def save_step_data(session_state: Any, step: int, data: dict[str, Any]) -> None:
    session_state[INTERVIEW_KEY][f"step{step}"] = data


def get_step_data(session_state: Any, step: int) -> dict[str, Any]:
    return session_state.get(INTERVIEW_KEY, {}).get(f"step{step}", {})


def get_all_responses(session_state: Any) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    for step_data in session_state.get(INTERVIEW_KEY, {}).values():
        combined.update(step_data)
    return combined


def validate_step(step: int, data: dict[str, Any]) -> list[str]:
    model_map = {
        1: Step1BasicInfo,
        2: Step2ModelSpecs,
        3: Step3DataSpecs,
        4: Step4Governance,
        5: Step5Deployment,
        6: Step6Monitoring,
        7: Step7ApprovalGates,
    }
    model_cls = model_map.get(step)
    if model_cls is None:
        return []
    try:
        model_cls.model_validate(data)
        return []
    except Exception as exc:
        errors = getattr(exc, "errors", None)
        if callable(errors):
            return [f"{' → '.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors()]
        return [str(exc)]


def is_step_complete(session_state: Any, step: int) -> bool:
    data = get_step_data(session_state, step)
    return len(data) > 0 and len(validate_step(step, data)) == 0


def completed_steps(session_state: Any) -> list[int]:
    return [s for s in range(1, TOTAL_STEPS + 1) if is_step_complete(session_state, s)]


def to_project_manifest_kwargs(session_state: Any) -> dict[str, Any]:
    r = get_all_responses(session_state)
    inference_type = r.get("inference_type", "batch")
    # model_frameworks (new) or legacy model_type
    frameworks = r.get("model_frameworks", [r.get("model_type", "sklearn")])
    features: list[str] = []
    if r.get("fairness_attributes"):
        features.append("fairness")
    if r.get("monitor_data_drift"):
        features.append("monitoring")
    return {
        "name": r.get("project_name", ""),
        "project_type": ("realtime-model" if inference_type == "real_time" else "batch-pipeline"),
        "features": features,
        "frameworks": frameworks,
    }
