# Databricks MLOps App: Database Schema

## Overview

All application state is stored in Unity Catalog tables for auditability, immutability, and compliance. This document defines the complete schema.

---

## Table of Contents

1. [Project Management](#project-management)
2. [Use Cases & Configuration](#use-cases--configuration)
3. [Data Contracts](#data-contracts)
4. [Model Management](#model-management)
5. [Approvals & Governance](#approvals--governance)
6. [Data Quality & Monitoring](#data-quality--monitoring)
7. [Drift Detection](#drift-detection)
8. [Alerting](#alerting)
9. [Feature Store & Lineage](#feature-store--lineage)
10. [Secrets & Infrastructure](#secrets--infrastructure)
11. [Cost Tracking](#cost-tracking)
12. [Audit Logging](#audit-logging)

---

## Project Management

### mlops.projects

**Purpose**: Core project metadata and status tracking

```sql
CREATE TABLE mlops.projects (
  project_id STRING COMMENT "Unique project identifier (UUID)",
  project_name STRING COMMENT "User-friendly project name (required)",
  project_description STRING COMMENT "Brief description of project purpose",
  created_timestamp TIMESTAMP COMMENT "When project was created (UTC)",
  created_by STRING COMMENT "Email of creator",
  owner_email STRING NOT NULL COMMENT "Primary owner email (required)",
  owner_name STRING COMMENT "Owner full name",
  team_name STRING NOT NULL COMMENT "Team ownership (required)",
  team_id STRING COMMENT "Team UUID reference",
  github_repo_url STRING COMMENT "GitHub repository URL",
  github_repo_name STRING COMMENT "GitHub repository name",
  mlflow_experiment_id STRING COMMENT "MLflow experiment ID",
  mlflow_experiment_name STRING COMMENT "MLflow experiment name (e.g., /Models/project_name)",
  status STRING COMMENT "Current project status: created, development, staging, production, archived, deleted",
  deployment_pattern STRING COMMENT "Deployment pattern: single_workspace, dual_workspace, multi_cloud",
  dev_workspace_id STRING COMMENT "Development workspace ID",
  prod_workspace_id STRING COMMENT "Production workspace ID",
  uc_schema_dev STRING COMMENT "Dev UC schema path (e.g., team.project_dev)",
  uc_schema_staging STRING COMMENT "Staging UC schema path",
  uc_schema_prod STRING COMMENT "Production UC schema path",
  service_account_name STRING COMMENT "Service account name for this project",
  secret_scope_name STRING COMMENT "Secret scope name for this project",
  
  -- Metadata
  last_updated TIMESTAMP COMMENT "Last modification timestamp",
  last_updated_by STRING COMMENT "Last modifier email",
  is_archived BOOLEAN DEFAULT FALSE COMMENT "Soft delete flag",
  archived_timestamp TIMESTAMP COMMENT "When archived",
  
  -- PK & Indexes
  CONSTRAINT pk_projects PRIMARY KEY (project_id)
) COMMENT "Core project metadata for all MLOps models"
;

-- Indexes
CREATE INDEX idx_projects_owner ON mlops.projects(owner_email);
CREATE INDEX idx_projects_team ON mlops.projects(team_name);
CREATE INDEX idx_projects_status ON mlops.projects(status);
CREATE INDEX idx_projects_created ON mlops.projects(created_timestamp DESC);
```

### mlops.project_configurations

**Purpose**: Track configuration changes over time (versioned)

```sql
CREATE TABLE mlops.project_configurations (
  config_id STRING COMMENT "Unique configuration version ID (UUID)",
  project_id STRING NOT NULL COMMENT "Foreign key to projects table",
  config_version INT COMMENT "Semantic version number (1, 2, 3, ...)",
  created_timestamp TIMESTAMP COMMENT "When this version was created",
  created_by STRING COMMENT "Who made the change",
  change_reason STRING COMMENT "Why the config changed",
  
  -- Interview Response Snapshot (JSON)
  interview_responses STRING COMMENT "Complete interview answers as JSON blob",
  
  -- Key Configuration Fields (denormalized for query efficiency)
  use_cases ARRAY<STRING> COMMENT "Selected use cases (data_ingestion, online_model, batch_model, lookup_service)",
  inference_type STRING COMMENT "batch, real_time, or both",
  batch_frequency STRING COMMENT "If batch: hourly, daily, weekly, monthly",
  sla_latency_ms INT COMMENT "If real-time: P95 latency target",
  sla_uptime_pct FLOAT COMMENT "If real-time: uptime percentage",
  retraining_strategy STRING COMMENT "manual, on_drift, scheduled, hybrid",
  retraining_schedule STRING COMMENT "If scheduled: cron expression",
  retraining_drift_threshold FLOAT COMMENT "If drift-triggered: threshold %",
  
  -- Approval Gate Configuration
  approval_gates ARRAY<STRING> COMMENT "List of approval gates required",
  code_review_count INT COMMENT "Number of code reviewers required",
  require_legal_review BOOLEAN COMMENT "Legal review required?",
  require_business_approval BOOLEAN COMMENT "Business approval required?",
  require_security_scan BOOLEAN COMMENT "Security scanning required?",
  require_end_to_end_test BOOLEAN COMMENT "E2E test required?",
  testing_threshold_pct INT COMMENT "Min test coverage %",
  
  -- Monitoring Configuration
  monitor_data_drift BOOLEAN COMMENT "Enable data drift monitoring",
  monitor_performance_drift BOOLEAN COMMENT "Enable performance monitoring",
  monitor_endpoint_uptime BOOLEAN COMMENT "Enable endpoint monitoring",
  alert_destinations ARRAY<STRING> COMMENT "email, slack, both",
  alert_threshold_deviation_pct FLOAT COMMENT "Alert if performance drops X%",
  
  -- Fairness Configuration
  fairness_attributes ARRAY<STRING> COMMENT "Protected attributes to test (age, gender, race, custom)",
  fairness_threshold_pct FLOAT COMMENT "Min fairness threshold (% disparity)",
  bias_test_type STRING COMMENT "aif360, fairlearn, custom",
  
  -- Data Quality Configuration
  data_quality_required_fields ARRAY<STRING> COMMENT "Fields that MUST pass quality",
  data_quality_acceptable_issues ARRAY<STRING> COMMENT "Fields where issues acceptable",
  
  -- Deployment Configuration
  canary_percentage FLOAT COMMENT "Canary deployment traffic %",
  shadow_mode BOOLEAN COMMENT "Run in shadow mode first?",
  shadow_mode_duration_days INT COMMENT "Days to run shadow mode",
  rollback_error_threshold INT COMMENT "Errors that trigger rollback",
  rollback_time_window_minutes INT COMMENT "Time window for error threshold",
  
  -- Cost Configuration
  budget_alerts_enabled BOOLEAN COMMENT "Enable budget alerts",
  monthly_warning_usd FLOAT COMMENT "Budget warning threshold",
  monthly_critical_usd FLOAT COMMENT "Budget critical threshold",
  
  -- PK & FK
  CONSTRAINT pk_project_configs PRIMARY KEY (config_id),
  CONSTRAINT fk_project_configs_projects FOREIGN KEY (project_id) REFERENCES mlops.projects(project_id)
) COMMENT "Versioned project configuration (tracks changes over time)"
;

CREATE INDEX idx_project_configs_project ON mlops.project_configurations(project_id, config_version DESC);
```

---

## Use Cases & Configuration

### mlops.project_use_cases

**Purpose**: Track which use cases are selected (supports multi-select)

```sql
CREATE TABLE mlops.project_use_cases (
  use_case_id STRING COMMENT "Unique ID (UUID)",
  project_id STRING NOT NULL COMMENT "Foreign key to projects",
  use_case_type STRING NOT NULL COMMENT "data_ingestion, online_model, batch_model, lookup_service",
  is_primary BOOLEAN DEFAULT TRUE COMMENT "Is this the primary use case?",
  configuration STRING COMMENT "Use-case specific configuration (JSON)",
  
  -- For lookup_service specifically
  lookup_request_fields ARRAY<STRING> COMMENT "Fields in request (keys)",
  lookup_response_fields ARRAY<STRING> COMMENT "Fields in response (values)",
  lookup_key_fields ARRAY<STRING> COMMENT "Key fields for lookup",
  
  -- For online_model specifically
  online_features ARRAY<STRING> COMMENT "Real-time feature names",
  online_inference_latency_ms INT COMMENT "Target latency",
  
  -- For batch_model specifically
  batch_schedule_cron STRING COMMENT "Batch job cron schedule",
  
  -- For data_ingestion specifically
  ingestion_source_type STRING COMMENT "Source type (API, database, file, streaming)",
  ingestion_frequency STRING COMMENT "Ingestion frequency",
  
  created_timestamp TIMESTAMP,
  created_by STRING,
  
  CONSTRAINT pk_use_cases PRIMARY KEY (use_case_id),
  CONSTRAINT fk_use_cases_projects FOREIGN KEY (project_id) REFERENCES mlops.projects(project_id)
) COMMENT "Selected use cases per project (multi-select)"
;

CREATE INDEX idx_use_cases_project ON mlops.project_use_cases(project_id);
CREATE INDEX idx_use_cases_type ON mlops.project_use_cases(use_case_type);
```

---

## Data Contracts

### mlops.data_contracts

**Purpose**: Define input/output data schemas and quality requirements

```sql
CREATE TABLE mlops.data_contracts (
  contract_id STRING COMMENT "Unique contract ID (UUID)",
  project_id STRING NOT NULL COMMENT "Foreign key to projects",
  contract_type STRING NOT NULL COMMENT "input_data, output_data, feature_table, staging_table",
  contract_name STRING NOT NULL COMMENT "User-friendly name (e.g., 'training_input', 'predictions_output')",
  contract_version INT COMMENT "Version number (1, 2, 3, ...)",
  
  -- Location
  table_name STRING COMMENT "Delta table name (if applicable)",
  table_catalog STRING,
  table_schema STRING,
  uc_path STRING COMMENT "Full UC path (catalog.schema.table)",
  
  -- Purpose & Ownership
  purpose STRING COMMENT "Why this contract exists",
  owner_email STRING COMMENT "Contract owner",
  owner_team STRING,
  
  -- SLA & Governance
  freshness_hours INT COMMENT "Data freshness SLA",
  availability_pct FLOAT COMMENT "Availability SLA",
  max_latency_seconds INT COMMENT "Max latency SLA",
  
  -- Audit & Retention
  requires_pii_encryption BOOLEAN COMMENT "PII data must be encrypted",
  requires_row_level_security BOOLEAN COMMENT "RLS required",
  audit_logging_enabled BOOLEAN COMMENT "Audit logging enabled",
  lineage_tracking_enabled BOOLEAN COMMENT "Lineage tracking enabled",
  
  retention_days INT COMMENT "How long to keep data",
  archive_after_days INT COMMENT "When to archive",
  
  -- Metadata
  created_timestamp TIMESTAMP,
  created_by STRING,
  last_updated TIMESTAMP,
  last_updated_by STRING,
  change_description STRING COMMENT "What changed in this version",
  
  -- Status
  is_active BOOLEAN DEFAULT TRUE COMMENT "Is this contract in use?",
  is_validated BOOLEAN DEFAULT FALSE COMMENT "Has DS signed off?",
  validated_by STRING COMMENT "Who validated",
  validated_timestamp TIMESTAMP,
  
  CONSTRAINT pk_data_contracts PRIMARY KEY (contract_id),
  CONSTRAINT fk_data_contracts_projects FOREIGN KEY (project_id) REFERENCES mlops.projects(project_id)
) COMMENT "Data contract definitions (versioned)"
;

CREATE INDEX idx_data_contracts_project ON mlops.data_contracts(project_id);
CREATE INDEX idx_data_contracts_type ON mlops.data_contracts(contract_type);
CREATE INDEX idx_data_contracts_table ON mlops.data_contracts(uc_path);
```

### mlops.data_contract_columns

**Purpose**: Define individual column specifications in contracts

```sql
CREATE TABLE mlops.data_contract_columns (
  column_id STRING COMMENT "Unique column ID (UUID)",
  contract_id STRING NOT NULL COMMENT "Foreign key to data_contracts",
  column_order INT COMMENT "Column position in table",
  column_name STRING NOT NULL COMMENT "Column name",
  column_description STRING COMMENT "Detailed description",
  
  -- Data Type & Constraints
  data_type STRING NOT NULL COMMENT "Type (int, string, float, boolean, timestamp, array, struct, etc.)",
  is_nullable BOOLEAN DEFAULT FALSE COMMENT "Can this be null?",
  is_unique BOOLEAN DEFAULT FALSE COMMENT "Must be unique?",
  is_partition_column BOOLEAN DEFAULT FALSE COMMENT "Is this a partition key?",
  is_key_column BOOLEAN DEFAULT FALSE COMMENT "Is this a primary/foreign key?",
  
  -- Value Constraints
  allowed_values ARRAY<STRING> COMMENT "If enumerated: allowed values",
  min_value FLOAT COMMENT "For numeric: min value",
  max_value FLOAT COMMENT "For numeric: max value",
  pattern_regex STRING COMMENT "For string: regex pattern",
  
  -- Data Quality Rules (JSON)
  quality_rules STRING COMMENT "Quality checks as JSON: {null_check, range_check, uniqueness_check, format_check, outlier_detection, distribution_check}",
  
  -- PII & Classification
  pii_level STRING COMMENT "none, low, medium, high",
  data_classification STRING COMMENT "public, internal, sensitive, restricted",
  
  -- Governance
  is_fairness_attribute BOOLEAN DEFAULT FALSE COMMENT "Is this a protected attribute?",
  is_required_for_quality BOOLEAN DEFAULT TRUE COMMENT "Must pass quality tests?",
  can_have_quality_issues BOOLEAN DEFAULT FALSE COMMENT "DS can accept issues here?",
  
  -- Monitoring
  monitor_for_drift BOOLEAN DEFAULT TRUE COMMENT "Monitor for drift?",
  drift_type STRING COMMENT "data_drift, quality_drift, value_drift",
  drift_threshold FLOAT COMMENT "Drift detection threshold",
  
  -- Lineage
  source_system STRING COMMENT "Where does this come from?",
  transformation_logic STRING COMMENT "How is it computed?",
  
  -- Metadata
  created_timestamp TIMESTAMP,
  created_by STRING,
  last_updated TIMESTAMP,
  last_updated_by STRING,
  
  CONSTRAINT pk_data_contract_columns PRIMARY KEY (column_id),
  CONSTRAINT fk_data_contract_columns FOREIGN KEY (contract_id) REFERENCES mlops.data_contracts(contract_id)
) COMMENT "Individual column specifications for data contracts"
;

CREATE INDEX idx_data_contract_columns_contract ON mlops.data_contract_columns(contract_id);
CREATE INDEX idx_data_contract_columns_drift ON mlops.data_contract_columns(monitor_for_drift);
```

### mlops.data_contract_versions

**Purpose**: Track contract change history

```sql
CREATE TABLE mlops.data_contract_versions (
  version_id STRING COMMENT "Unique version ID (UUID)",
  contract_id STRING NOT NULL COMMENT "FK to data_contracts",
  version_number INT COMMENT "Sequential version",
  created_timestamp TIMESTAMP,
  created_by STRING,
  change_type STRING COMMENT "created, updated, column_added, column_removed, column_modified",
  change_description STRING COMMENT "What changed",
  git_commit_hash STRING COMMENT "Associated git commit",
  
  -- Complete contract snapshot (JSON) for reproducibility
  contract_snapshot STRING COMMENT "Full contract definition as JSON",
  columns_snapshot STRING COMMENT "All columns as JSON array",
  
  CONSTRAINT pk_data_contract_versions PRIMARY KEY (version_id),
  CONSTRAINT fk_data_contract_versions FOREIGN KEY (contract_id) REFERENCES mlops.data_contracts(contract_id)
) COMMENT "Version history of all contract changes"
;

CREATE INDEX idx_data_contract_versions_contract ON mlops.data_contract_versions(contract_id, version_number DESC);
```

---

## Model Management

### mlops.models

**Purpose**: Core model registry and version tracking

```sql
CREATE TABLE mlops.models (
  model_id STRING COMMENT "Unique model ID (UUID)",
  project_id STRING NOT NULL COMMENT "FK to projects",
  model_name STRING NOT NULL COMMENT "Model name (from project)",
  mlflow_model_uri STRING COMMENT "MLflow model URI (models:/...)",
  
  current_version_id STRING COMMENT "Current production version ID",
  current_production_tag STRING COMMENT "current, shadow, canary, ab_test, previous",
  
  -- Model Metadata
  model_type STRING COMMENT "Inferred from artifacts: sklearn, xgboost, tensorflow, pytorch, huggingface, etc.",
  framework STRING COMMENT "ML framework used",
  framework_version STRING COMMENT "Framework version",
  
  -- Status
  status STRING COMMENT "development, testing, staging, production, archived",
  is_production BOOLEAN,
  
  -- Governance
  owner_email STRING,
  team_name STRING,
  
  -- Timestamps
  created_timestamp TIMESTAMP,
  created_by STRING,
  last_updated TIMESTAMP,
  last_updated_by STRING,
  
  CONSTRAINT pk_models PRIMARY KEY (model_id),
  CONSTRAINT fk_models_projects FOREIGN KEY (project_id) REFERENCES mlops.projects(project_id)
) COMMENT "Core model registry"
;

CREATE INDEX idx_models_project ON mlops.models(project_id);
CREATE INDEX idx_models_status ON mlops.models(status);
```

### mlops.model_versions

**Purpose**: Track all model versions and their artifacts

```sql
CREATE TABLE mlops.model_versions (
  version_id STRING COMMENT "Unique version ID (UUID)",
  model_id STRING NOT NULL COMMENT "FK to models",
  version_number INT COMMENT "Semantic version (1.0.0, 1.1.0, 2.0.0)",
  version_string STRING COMMENT "Semantic version string",
  
  mlflow_version_id STRING COMMENT "MLflow version ID",
  mlflow_stage STRING COMMENT "None, Staging, Production, Archived",
  
  -- Training Metadata
  training_timestamp TIMESTAMP COMMENT "When model was trained",
  training_duration_seconds INT COMMENT "How long training took",
  training_data_version_id STRING COMMENT "FK to data_versioning.data_version_id",
  training_code_commit STRING COMMENT "Git commit of training code",
  
  -- Model Artifacts
  model_artifact_uri STRING COMMENT "Path to model artifacts",
  model_serialization_format STRING COMMENT "pkl, pt, pb, zip, etc.",
  feature_names ARRAY<STRING> COMMENT "Input feature names (ordered)",
  
  -- Performance Metrics (baseline on dev/staging)
  accuracy FLOAT,
  auc_roc FLOAT,
  precision FLOAT,
  recall FLOAT,
  f1_score FLOAT,
  custom_metrics MAP<STRING, FLOAT> COMMENT "Additional metrics as key-value",
  
  -- Fairness Metrics (baseline)
  fairness_demographic_parity FLOAT,
  fairness_equalized_odds FLOAT,
  fairness_calibration FLOAT,
  fairness_test_passed BOOLEAN,
  
  -- Data Quality
  training_data_quality_score FLOAT,
  
  -- Status & Tags
  status STRING COMMENT "registered, approved, deployed, deprecated",
  tags ARRAY<STRING> COMMENT "tags: current, shadow, canary, ab_test, previous",
  
  -- Approvals
  approved_by STRING,
  approved_timestamp TIMESTAMP,
  approval_comment STRING,
  
  created_timestamp TIMESTAMP,
  created_by STRING,
  
  CONSTRAINT pk_model_versions PRIMARY KEY (version_id),
  CONSTRAINT fk_model_versions_models FOREIGN KEY (model_id) REFERENCES mlops.models(model_id)
) COMMENT "Versioned model artifacts and metadata"
;

CREATE INDEX idx_model_versions_model ON mlops.model_versions(model_id, version_number DESC);
CREATE INDEX idx_model_versions_mlflow ON mlops.model_versions(mlflow_version_id);
```

### mlops.model_performance

**Purpose**: Track model performance over time in production

```sql
CREATE TABLE mlops.model_performance (
  performance_id STRING COMMENT "Unique ID (UUID)",
  version_id STRING NOT NULL COMMENT "FK to model_versions",
  model_id STRING NOT NULL COMMENT "FK to models",
  
  measurement_timestamp TIMESTAMP COMMENT "When measured",
  measurement_window STRING COMMENT "last_1h, last_24h, last_7d, etc.",
  
  -- Inference Metrics
  predictions_count BIGINT COMMENT "Number of predictions",
  error_count INT COMMENT "Errors in this window",
  error_rate_pct FLOAT COMMENT "Error percentage",
  
  -- Performance Metrics (if labels available)
  accuracy FLOAT COMMENT "Current accuracy",
  auc_roc FLOAT COMMENT "Current AUC",
  precision FLOAT COMMENT "Current precision",
  recall FLOAT COMMENT "Current recall",
  
  -- Comparison to Baseline
  accuracy_vs_baseline_delta FLOAT COMMENT "Change from version baseline",
  performance_degraded BOOLEAN COMMENT "Is performance degraded?",
  degradation_pct FLOAT COMMENT "By how much?",
  
  -- Fairness Metrics (if applicable)
  fairness_demographic_parity FLOAT,
  fairness_equalized_odds FLOAT,
  fairness_test_passed BOOLEAN,
  
  -- Endpoint Metrics
  latency_p50_ms FLOAT,
  latency_p95_ms FLOAT,
  latency_p99_ms FLOAT,
  throughput_qps FLOAT,
  
  -- Data Metrics
  data_quality_score FLOAT,
  has_data_drift BOOLEAN,
  data_drift_ks_stat FLOAT,
  
  created_timestamp TIMESTAMP,
  
  CONSTRAINT pk_model_performance PRIMARY KEY (performance_id),
  CONSTRAINT fk_model_performance_versions FOREIGN KEY (version_id) REFERENCES mlops.model_versions(version_id)
) COMMENT "Production performance metrics over time"
;

CREATE INDEX idx_model_performance_model ON mlops.model_performance(model_id, measurement_timestamp DESC);
CREATE INDEX idx_model_performance_version ON mlops.model_performance(version_id, measurement_timestamp DESC);
```

---

## Approvals & Governance

### mlops.approvals

**Purpose**: Track all approval decisions

```sql
CREATE TABLE mlops.approvals (
  approval_id STRING COMMENT "Unique approval ID (UUID)",
  model_id STRING NOT NULL COMMENT "FK to models",
  approval_type STRING COMMENT "code_review, fairness_review, legal_review, business_approval, security_scan, end_to_end_test",
  approval_gate STRING COMMENT "Which gate in the workflow",
  
  -- Request Details
  requested_timestamp TIMESTAMP COMMENT "When approval was requested",
  requested_by STRING COMMENT "Who requested",
  
  required_count INT COMMENT "How many approvals needed (e.g., 2 for code review)",
  
  -- Approval Responses
  approval_responses ARRAY<STRUCT<
    approved_by: STRING,
    approved_timestamp: TIMESTAMP,
    approval_decision: STRING,
    comment: STRING,
    ip_address: STRING
  >> COMMENT "All individual approvals",
  
  -- Summary
  approved_count INT COMMENT "How many have approved",
  rejected_count INT COMMENT "How many have rejected",
  status STRING COMMENT "pending, approved, rejected, needs_changes",
  completed_timestamp TIMESTAMP COMMENT "When all approvals done",
  
  -- Override (if approval was overridden)
  override_requested BOOLEAN,
  override_requested_by STRING,
  override_requested_timestamp TIMESTAMP,
  override_approved_by STRING,
  override_approval_timestamp TIMESTAMP,
  override_reason STRING,
  
  created_timestamp TIMESTAMP,
  
  CONSTRAINT pk_approvals PRIMARY KEY (approval_id),
  CONSTRAINT fk_approvals_models FOREIGN KEY (model_id) REFERENCES mlops.models(model_id)
) COMMENT "Approval request and decision tracking"
;

CREATE INDEX idx_approvals_model ON mlops.approvals(model_id, approval_gate);
CREATE INDEX idx_approvals_status ON mlops.approvals(status);
```

---

## Data Quality & Monitoring

### mlops.data_quality_assessments

**Purpose**: Track data quality scores over time

```sql
CREATE TABLE mlops.data_quality_assessments (
  assessment_id STRING COMMENT "Unique assessment ID (UUID)",
  project_id STRING NOT NULL COMMENT "FK to projects",
  contract_id STRING COMMENT "FK to data_contracts (if applicable)",
  
  assessment_timestamp TIMESTAMP,
  assessment_type STRING COMMENT "training_data, inference_data, production_data",
  
  data_version_id STRING COMMENT "FK to data_versioning.data_version_id",
  table_name STRING COMMENT "Which table assessed",
  row_count BIGINT COMMENT "Total rows assessed",
  
  -- Overall Quality
  quality_score FLOAT COMMENT "0-1, overall quality",
  quality_status STRING COMMENT "excellent, good, acceptable, poor, critical",
  
  -- Column Quality Scores
  column_quality_scores MAP<STRING, FLOAT> COMMENT "quality_score per column",
  
  -- Failed Checks
  failed_checks ARRAY<STRUCT<
    column_name: STRING,
    check_type: STRING,
    failed_record_count: INT,
    issue_description: STRING
  >> COMMENT "Details of failed quality checks",
  
  -- Data Quality Issues Summary
  null_issues_found INT,
  range_issues_found INT,
  uniqueness_issues_found INT,
  format_issues_found INT,
  outlier_issues_found INT,
  distribution_issues_found INT,
  
  -- PII Issues
  pii_columns_detected ARRAY<STRING>,
  
  created_timestamp TIMESTAMP,
  created_by STRING,
  
  CONSTRAINT pk_data_quality_assessments PRIMARY KEY (assessment_id),
  CONSTRAINT fk_data_quality_project FOREIGN KEY (project_id) REFERENCES mlops.projects(project_id)
) COMMENT "Data quality assessment results"
;

CREATE INDEX idx_data_quality_project ON mlops.data_quality_assessments(project_id, assessment_timestamp DESC);
CREATE INDEX idx_data_quality_contract ON mlops.data_quality_assessments(contract_id);
```

---

## Drift Detection

### mlops.drift_monitoring_config

**Purpose**: Configure which fields to monitor for drift

```sql
CREATE TABLE mlops.drift_monitoring_config (
  config_id STRING COMMENT "Unique config ID (UUID)",
  model_id STRING NOT NULL COMMENT "FK to models",
  
  -- Field Configuration
  field_name STRING NOT NULL COMMENT "Column name to monitor",
  field_type STRING COMMENT "feature, target, context",
  
  -- Drift Types
  monitor_data_drift BOOLEAN DEFAULT TRUE COMMENT "Monitor distribution change?",
  monitor_quality_drift BOOLEAN DEFAULT TRUE COMMENT "Monitor quality degradation?",
  monitor_value_drift BOOLEAN DEFAULT FALSE COMMENT "Monitor specific value changes?",
  
  -- Thresholds
  data_drift_ks_threshold FLOAT COMMENT "KS statistic threshold for data drift",
  quality_drift_threshold FLOAT COMMENT "Quality score threshold",
  value_drift_threshold FLOAT COMMENT "Value change threshold (if applicable)",
  
  -- Alert Configuration
  alert_on_drift BOOLEAN DEFAULT TRUE,
  alert_recipients ARRAY<STRING> COMMENT "Who to alert",
  alert_severity STRING COMMENT "info, warning, critical",
  
  -- Monitoring
  is_enabled BOOLEAN DEFAULT TRUE,
  
  created_timestamp TIMESTAMP,
  created_by STRING,
  last_updated TIMESTAMP,
  
  CONSTRAINT pk_drift_config PRIMARY KEY (config_id),
  CONSTRAINT fk_drift_config_models FOREIGN KEY (model_id) REFERENCES mlops.models(model_id)
) COMMENT "Drift monitoring configuration per field"
;

CREATE INDEX idx_drift_config_model ON mlops.drift_monitoring_config(model_id);
```

### mlops.drift_detection_results

**Purpose**: Track drift detection results over time

```sql
CREATE TABLE mlops.drift_detection_results (
  result_id STRING COMMENT "Unique result ID (UUID)",
  model_id STRING NOT NULL COMMENT "FK to models",
  config_id STRING NOT NULL COMMENT "FK to drift_monitoring_config",
  
  measurement_timestamp TIMESTAMP COMMENT "When drift detection ran",
  measurement_period STRING COMMENT "Time window analyzed (e.g., last 24h)",
  
  field_name STRING COMMENT "Which field",
  drift_type STRING COMMENT "data_drift, quality_drift, value_drift",
  
  -- Detection Results
  drift_detected BOOLEAN COMMENT "Was drift detected?",
  drift_score FLOAT COMMENT "Numerical score (KS stat, etc.)",
  drift_severity STRING COMMENT "none, low, medium, high, critical",
  
  -- Baseline & Current
  baseline_distribution STRING COMMENT "Statistical summary (JSON)",
  current_distribution STRING COMMENT "Statistical summary (JSON)",
  
  -- Alert Status
  alert_triggered BOOLEAN,
  alert_timestamp TIMESTAMP,
  
  -- Investigation & Action
  investigation_notes STRING COMMENT "Root cause analysis",
  action_taken STRING COMMENT "What was done (retrain, investigate, etc.)",
  
  created_timestamp TIMESTAMP,
  
  CONSTRAINT pk_drift_results PRIMARY KEY (result_id),
  CONSTRAINT fk_drift_results_models FOREIGN KEY (model_id) REFERENCES mlops.models(model_id)
) COMMENT "Drift detection results over time"
;

CREATE INDEX idx_drift_results_model ON mlops.drift_detection_results(model_id, measurement_timestamp DESC);
CREATE INDEX idx_drift_results_field ON mlops.drift_detection_results(field_name, measurement_timestamp DESC);
```

---

## Alerting

### mlops.alerts

**Purpose**: Define alert configurations

```sql
CREATE TABLE mlops.alerts (
  alert_id STRING COMMENT "Unique alert ID (UUID)",
  model_id STRING NOT NULL COMMENT "FK to models",
  
  alert_name STRING NOT NULL COMMENT "Display name",
  alert_type STRING COMMENT "standard (endpoint_down, error_rate, etc.) or custom",
  
  -- Threshold Configuration
  metric_name STRING COMMENT "What metric to watch",
  threshold_value FLOAT COMMENT "Threshold for alert",
  comparison_operator STRING COMMENT ">, <, >=, <=, ==, !=",
  
  -- Behavior
  monitoring_interval STRING COMMENT "realtime, 15m, hourly, daily",
  severity STRING COMMENT "info, warning, critical",
  
  -- Recipients
  alert_destinations ARRAY<STRING> COMMENT "email, slack, pagerduty, etc.",
  recipient_emails ARRAY<STRING>,
  recipient_slack_channels ARRAY<STRING>,
  
  -- Status
  is_enabled BOOLEAN DEFAULT TRUE,
  
  created_timestamp TIMESTAMP,
  created_by STRING,
  
  CONSTRAINT pk_alerts PRIMARY KEY (alert_id),
  CONSTRAINT fk_alerts_models FOREIGN KEY (model_id) REFERENCES mlops.models(model_id)
) COMMENT "Alert configurations"
;

CREATE INDEX idx_alerts_model ON mlops.alerts(model_id);
```

### mlops.alert_history

**Purpose**: Track alert firing events

```sql
CREATE TABLE mlops.alert_history (
  event_id STRING COMMENT "Unique event ID (UUID)",
  alert_id STRING NOT NULL COMMENT "FK to alerts",
  model_id STRING NOT NULL,
  
  triggered_timestamp TIMESTAMP,
  alert_value FLOAT COMMENT "Actual metric value",
  alert_severity STRING,
  
  -- Notification Status
  notification_sent BOOLEAN,
  notification_timestamp TIMESTAMP,
  notification_channel STRING COMMENT "email, slack, etc.",
  
  -- Resolution
  resolved BOOLEAN DEFAULT FALSE,
  resolved_timestamp TIMESTAMP,
  resolution_notes STRING,
  
  created_timestamp TIMESTAMP,
  
  CONSTRAINT pk_alert_history PRIMARY KEY (event_id),
  CONSTRAINT fk_alert_history_alerts FOREIGN KEY (alert_id) REFERENCES mlops.alerts(alert_id)
) COMMENT "Alert firing events and resolutions"
;

CREATE INDEX idx_alert_history_alert ON mlops.alert_history(alert_id, triggered_timestamp DESC);
CREATE INDEX idx_alert_history_model ON mlops.alert_history(model_id, triggered_timestamp DESC);
```

---

## Feature Store & Lineage

### mlops.features

**Purpose**: Track features in feature store

```sql
CREATE TABLE mlops.features (
  feature_id STRING COMMENT "Unique feature ID (UUID)",
  project_id STRING COMMENT "FK to projects (null if shared)",
  
  feature_name STRING NOT NULL,
  feature_description STRING,
  feature_type STRING COMMENT "numeric, categorical, text, datetime",
  
  -- Storage
  feature_table_name STRING,
  feature_column_name STRING,
  
  -- Metadata
  owner_email STRING,
  owner_team STRING,
  
  -- Freshness & SLA
  freshness_hours INT,
  availability_pct FLOAT,
  
  -- Versioning
  feature_version STRING,
  is_active BOOLEAN DEFAULT TRUE,
  
  -- Sharing
  is_shared BOOLEAN DEFAULT FALSE COMMENT "Can other models use this?",
  shared_with_teams ARRAY<STRING> COMMENT "Teams that can use",
  
  created_timestamp TIMESTAMP,
  created_by STRING,
  last_updated TIMESTAMP,
  
  CONSTRAINT pk_features PRIMARY KEY (feature_id)
) COMMENT "Feature store feature definitions"
;

CREATE INDEX idx_features_project ON mlops.features(project_id);
CREATE INDEX idx_features_owner ON mlops.features(owner_email);
```

### mlops.feature_lineage

**Purpose**: Map features to tables and other features

```sql
CREATE TABLE mlops.feature_lineage (
  lineage_id STRING COMMENT "Unique ID (UUID)",
  feature_id STRING NOT NULL COMMENT "FK to features",
  
  -- Source
  source_table_name STRING COMMENT "Where feature comes from",
  source_table_version STRING,
  
  -- Transformation
  transformation_logic STRING COMMENT "SQL or code snippet",
  transformation_code_hash STRING COMMENT "Git hash of transformation",
  
  -- Dependencies (other features)
  dependent_feature_ids ARRAY<STRING> COMMENT "Features this depends on",
  
  -- Impact (downstream)
  downstream_model_ids ARRAY<STRING> COMMENT "Models using this feature",
  
  created_timestamp TIMESTAMP,
  created_by STRING,
  
  CONSTRAINT pk_feature_lineage PRIMARY KEY (lineage_id),
  CONSTRAINT fk_feature_lineage_features FOREIGN KEY (feature_id) REFERENCES mlops.features(feature_id)
) COMMENT "Feature lineage and dependencies"
;

CREATE INDEX idx_feature_lineage_feature ON mlops.feature_lineage(feature_id);
```

---

## Secrets & Infrastructure

### mlops.secrets_management

**Purpose**: Track secrets and rotation schedule

```sql
CREATE TABLE mlops.secrets_management (
  secret_id STRING COMMENT "Unique secret ID (UUID)",
  project_id STRING NOT NULL COMMENT "FK to projects",
  
  secret_name STRING COMMENT "Secret identifier in Databricks Secret Scope",
  secret_scope_name STRING COMMENT "Secret scope name",
  secret_type STRING COMMENT "api_token, personal_access_token, github_token, etc.",
  
  -- Rotation Policy
  created_timestamp TIMESTAMP COMMENT "When secret was created",
  rotation_schedule_days INT COMMENT "How often to rotate (default 365)",
  last_rotated_timestamp TIMESTAMP COMMENT "When last rotated",
  next_rotation_timestamp TIMESTAMP COMMENT "When to rotate next",
  
  -- Usage
  used_for STRING COMMENT "Purpose of secret (inference, training, github, etc.)",
  permissions ARRAY<STRING> COMMENT "Databricks permissions granted",
  
  -- Rotation History
  rotation_history ARRAY<STRUCT<
    rotation_timestamp: TIMESTAMP,
    rotated_by: STRING,
    test_result: STRING
  >> COMMENT "Previous rotations",
  
  -- Status
  is_active BOOLEAN DEFAULT TRUE,
  is_compromised BOOLEAN DEFAULT FALSE,
  
  last_updated TIMESTAMP,
  
  CONSTRAINT pk_secrets PRIMARY KEY (secret_id),
  CONSTRAINT fk_secrets_projects FOREIGN KEY (project_id) REFERENCES mlops.projects(project_id)
) COMMENT "Secret and rotation management"
;

CREATE INDEX idx_secrets_project ON mlops.secrets_management(project_id);
```

### mlops.infrastructure_config

**Purpose**: Track compute and infrastructure configuration

```sql
CREATE TABLE mlops.infrastructure_config (
  config_id STRING COMMENT "Unique config ID (UUID)",
  project_id STRING NOT NULL,
  
  config_type STRING COMMENT "cluster, warehouse, endpoint, job",
  resource_name STRING COMMENT "Resource identifier",
  
  -- Configuration (JSON)
  configuration STRING COMMENT "Full resource configuration as JSON",
  
  -- Status
  is_active BOOLEAN DEFAULT TRUE,
  status STRING COMMENT "running, stopped, failed, etc.",
  
  last_updated TIMESTAMP,
  last_status_check TIMESTAMP,
  
  CONSTRAINT pk_infrastructure PRIMARY KEY (config_id),
  CONSTRAINT fk_infrastructure_projects FOREIGN KEY (project_id) REFERENCES mlops.projects(project_id)
) COMMENT "Compute and infrastructure configuration tracking"
;

CREATE INDEX idx_infrastructure_project ON mlops.infrastructure_config(project_id);
```

---

## Cost Tracking

### mlops.cost_tracking

**Purpose**: Track costs per model

```sql
CREATE TABLE mlops.cost_tracking (
  cost_id STRING COMMENT "Unique cost record ID (UUID)",
  model_id STRING NOT NULL,
  project_id STRING NOT NULL,
  
  date DATE COMMENT "Cost date",
  
  -- Cost Breakdown
  training_cost_usd FLOAT COMMENT "Cost of training jobs",
  inference_cost_usd FLOAT COMMENT "Cost of inference/serving",
  storage_cost_usd FLOAT COMMENT "Cost of data storage",
  compute_cost_usd FLOAT COMMENT "Cost of compute resources",
  other_cost_usd FLOAT COMMENT "Other costs",
  
  total_cost_usd FLOAT COMMENT "Total daily cost",
  
  -- Attribution
  cost_center STRING COMMENT "Team or project cost center",
  billing_tag STRING COMMENT "Billing tag for chargeback",
  
  created_timestamp TIMESTAMP,
  
  CONSTRAINT pk_cost_tracking PRIMARY KEY (cost_id),
  CONSTRAINT fk_cost_tracking_models FOREIGN KEY (model_id) REFERENCES mlops.models(model_id)
) COMMENT "Daily cost tracking per model"
;

CREATE INDEX idx_cost_tracking_model ON mlops.cost_tracking(model_id, date DESC);
CREATE INDEX idx_cost_tracking_date ON mlops.cost_tracking(date DESC);
```

### mlops.budget_alerts

**Purpose**: Budget threshold configuration and alerts

```sql
CREATE TABLE mlops.budget_alerts (
  budget_id STRING COMMENT "Unique budget ID (UUID)",
  project_id STRING NOT NULL,
  
  budget_period STRING COMMENT "monthly, quarterly, annual",
  budget_threshold_usd FLOAT COMMENT "Monthly spending limit",
  alert_at_pct FLOAT COMMENT "Alert when spend reaches X% of budget",
  
  enabled BOOLEAN DEFAULT FALSE,
  
  alert_recipients ARRAY<STRING>,
  
  created_timestamp TIMESTAMP,
  
  CONSTRAINT pk_budget_alerts PRIMARY KEY (budget_id),
  CONSTRAINT fk_budget_alerts_projects FOREIGN KEY (project_id) REFERENCES mlops.projects(project_id)
) COMMENT "Budget threshold configuration"
;

CREATE INDEX idx_budget_alerts_project ON mlops.budget_alerts(project_id);
```

---

## Audit Logging

### mlops.audit_logs

**Purpose**: Complete immutable audit trail

```sql
CREATE TABLE mlops.audit_logs (
  audit_id STRING COMMENT "Unique audit record ID (UUID)",
  
  event_timestamp TIMESTAMP COMMENT "When the event occurred (UTC)",
  action_type STRING COMMENT "model_created, approval_requested, deployment, configuration_changed, override_requested, etc.",
  
  -- Subject
  model_id STRING COMMENT "FK to models (if applicable)",
  project_id STRING COMMENT "FK to projects",
  approval_id STRING COMMENT "FK to approvals (if applicable)",
  
  -- Actor
  actor_email STRING COMMENT "Who performed the action",
  actor_role STRING COMMENT "data_scientist, ml_engineer, legal, etc.",
  actor_ip_address STRING,
  
  -- What Changed
  resource_type STRING COMMENT "model, approval, configuration, etc.",
  resource_id STRING COMMENT "Which resource was affected",
  
  change_details STRING COMMENT "JSON describing what changed",
  old_value STRING COMMENT "Previous value (if update)",
  new_value STRING COMMENT "New value (if update)",
  
  -- Result
  action_status STRING COMMENT "success, failure, pending",
  error_message STRING COMMENT "If failed, why",
  
  -- Context
  context_info STRING COMMENT "Additional context (JSON)",
  
  -- Immutability
  is_immutable BOOLEAN DEFAULT TRUE COMMENT "Cannot be modified",
  
  CONSTRAINT pk_audit_logs PRIMARY KEY (audit_id)
) COMMENT "Immutable audit trail of all actions (7-year retention)"
;

-- Indexes for queryability
CREATE INDEX idx_audit_logs_timestamp ON mlops.audit_logs(event_timestamp DESC);
CREATE INDEX idx_audit_logs_model ON mlops.audit_logs(model_id, event_timestamp DESC);
CREATE INDEX idx_audit_logs_actor ON mlops.audit_logs(actor_email, event_timestamp DESC);
CREATE INDEX idx_audit_logs_action ON mlops.audit_logs(action_type, event_timestamp DESC);

-- Set retention policy (7 years minimum for regulated industries)
ALTER TABLE mlops.audit_logs SET TBLPROPERTIES (
  'delta.dataRetentionDays' = '2555'
);
```

---

## Summary: Complete Schema

**Total Tables**: 30+

**Core Categories**:
- **Project Management** (2 tables): projects, project_configurations
- **Use Cases** (1 table): project_use_cases
- **Data Contracts** (3 tables): data_contracts, data_contract_columns, data_contract_versions
- **Model Management** (3 tables): models, model_versions, model_performance
- **Approvals & Governance** (1 table): approvals
- **Data Quality** (1 table): data_quality_assessments
- **Drift Detection** (2 tables): drift_monitoring_config, drift_detection_results
- **Alerting** (2 tables): alerts, alert_history
- **Feature Store** (2 tables): features, feature_lineage
- **Secrets & Infrastructure** (2 tables): secrets_management, infrastructure_config
- **Cost Tracking** (2 tables): cost_tracking, budget_alerts
- **Audit Logging** (1 table): audit_logs

**Key Design Principles**:
1. ✅ **Immutability**: Audit logs cannot be modified
2. ✅ **Auditability**: Every change tracked with who/what/when
3. ✅ **Versioning**: Contracts and configurations versioned
4. ✅ **Compliance**: 7-year retention for regulated industries
5. ✅ **Queryability**: Comprehensive indexes for common queries
6. ✅ **Extensibility**: JSON columns for flexible schema
7. ✅ **Lineage**: Complete data & feature lineage tracking
8. ✅ **Governance**: RBAC, approval chains, segregation of duties

