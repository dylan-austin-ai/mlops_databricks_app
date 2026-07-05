-- =============================================================================
-- Databricks MLOps App — Unity Catalog DDL
-- * No DEFAULT column values (requires delta.feature.allowColumnDefaults)
-- * No TBLPROPERTIES (requires spark.databricks.delta.allowArbitraryProperties)
-- * FOREIGN KEY constraints are informational only in UC (not enforced)
-- Run via: python -m db.setup
-- =============================================================================

-- ── Project Management ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.projects (
  project_id           STRING    NOT NULL COMMENT 'UUID',
  project_name         STRING    NOT NULL COMMENT 'Unique model/project name',
  project_description  STRING    COMMENT 'Brief description',
  created_timestamp    TIMESTAMP NOT NULL COMMENT 'UTC creation time',
  created_by           STRING    NOT NULL COMMENT 'Creator email',
  owner_email          STRING    NOT NULL COMMENT 'Primary owner email',
  owner_name           STRING    COMMENT 'Owner full name',
  team_name            STRING    NOT NULL COMMENT 'Owning team',
  team_id              STRING    COMMENT 'Team UUID reference',
  github_repo_url      STRING    COMMENT 'GitHub repository URL',
  github_repo_name     STRING    COMMENT 'GitHub repository name',
  mlflow_experiment_id   STRING  COMMENT 'MLflow experiment ID',
  mlflow_experiment_name STRING  COMMENT 'MLflow experiment path',
  status               STRING    NOT NULL COMMENT 'created|development|staging|production|archived|deleted',
  deployment_pattern   STRING    COMMENT 'single_workspace|dual_workspace|multi_cloud',
  dev_workspace_id     STRING    COMMENT 'Dev workspace ID',
  prod_workspace_id    STRING    COMMENT 'Prod workspace ID',
  uc_schema_dev        STRING    COMMENT 'Dev UC schema path',
  uc_schema_staging    STRING    COMMENT 'Staging UC schema path',
  uc_schema_prod       STRING    COMMENT 'Prod UC schema path',
  service_account_name STRING    COMMENT 'Service account for this project',
  secret_scope_name    STRING    COMMENT 'Secret scope for this project',
  last_updated         TIMESTAMP COMMENT 'Last modification timestamp',
  last_updated_by      STRING    COMMENT 'Last modifier email',
  is_archived          BOOLEAN   COMMENT 'Soft delete flag',
  archived_timestamp   TIMESTAMP COMMENT 'Archival timestamp',
  CONSTRAINT pk_projects PRIMARY KEY (project_id)
) COMMENT 'Core project metadata for all MLOps models';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.project_configurations (
  config_id          STRING    NOT NULL COMMENT 'UUID',
  project_id         STRING    NOT NULL COMMENT 'FK → projects',
  config_version     INT       NOT NULL COMMENT 'Sequential version number',
  created_timestamp  TIMESTAMP NOT NULL,
  created_by         STRING    NOT NULL,
  change_reason      STRING    COMMENT 'Why the config changed',
  interview_responses STRING   COMMENT 'Full interview answers as JSON',
  use_cases          ARRAY<STRING> COMMENT 'data_ingestion|online_model|batch_model|lookup_service',
  inference_type     STRING    COMMENT 'batch|real_time|both',
  batch_frequency    STRING    COMMENT 'hourly|daily|weekly|monthly',
  sla_latency_ms     INT       COMMENT 'P95 latency target (real-time)',
  sla_uptime_pct     FLOAT     COMMENT 'Uptime target %',
  retraining_strategy STRING   COMMENT 'manual|on_drift|scheduled|hybrid',
  retraining_schedule STRING   COMMENT 'Cron expression',
  retraining_drift_threshold FLOAT COMMENT 'Drift % that triggers retrain',
  approval_gates     ARRAY<STRING> COMMENT 'List of required gates',
  code_review_count  INT       COMMENT 'Required code reviewer count',
  require_legal_review      BOOLEAN,
  require_business_approval BOOLEAN,
  require_security_scan     BOOLEAN,
  require_end_to_end_test   BOOLEAN,
  testing_threshold_pct     INT COMMENT 'Min test coverage %',
  monitor_data_drift        BOOLEAN,
  monitor_performance_drift BOOLEAN,
  monitor_endpoint_uptime   BOOLEAN,
  alert_destinations ARRAY<STRING> COMMENT 'email|slack',
  alert_threshold_deviation_pct FLOAT,
  fairness_attributes        ARRAY<STRING> COMMENT 'Protected attributes',
  fairness_threshold_pct     FLOAT,
  bias_test_type     STRING    COMMENT 'aif360|fairlearn|custom',
  data_quality_required_fields   ARRAY<STRING>,
  data_quality_acceptable_issues ARRAY<STRING>,
  canary_percentage  FLOAT,
  shadow_mode        BOOLEAN,
  shadow_mode_duration_days  INT,
  rollback_error_threshold   INT,
  rollback_time_window_minutes INT,
  budget_alerts_enabled BOOLEAN,
  monthly_warning_usd   FLOAT,
  monthly_critical_usd  FLOAT,
  CONSTRAINT pk_project_configs PRIMARY KEY (config_id),
  CONSTRAINT fk_project_configs_projects FOREIGN KEY (project_id) REFERENCES {catalog}.{schema}.projects(project_id)
) COMMENT 'Versioned project configuration';

-- ── Use Cases ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.project_use_cases (
  use_case_id     STRING    NOT NULL COMMENT 'UUID',
  project_id      STRING    NOT NULL COMMENT 'FK → projects',
  use_case_type   STRING    NOT NULL COMMENT 'data_ingestion|online_model|batch_model|lookup_service',
  is_primary      BOOLEAN,
  configuration   STRING    COMMENT 'Use-case specific config as JSON',
  lookup_request_fields  ARRAY<STRING>,
  lookup_response_fields ARRAY<STRING>,
  lookup_key_fields      ARRAY<STRING>,
  online_features        ARRAY<STRING>,
  online_inference_latency_ms INT,
  batch_schedule_cron    STRING,
  ingestion_source_type  STRING,
  ingestion_frequency    STRING,
  created_timestamp TIMESTAMP,
  created_by        STRING,
  CONSTRAINT pk_use_cases PRIMARY KEY (use_case_id),
  CONSTRAINT fk_use_cases_projects FOREIGN KEY (project_id) REFERENCES {catalog}.{schema}.projects(project_id)
) COMMENT 'Selected use cases per project';

-- ── Data Contracts ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.data_contracts (
  contract_id       STRING    NOT NULL COMMENT 'UUID',
  project_id        STRING    NOT NULL COMMENT 'FK → projects',
  contract_type     STRING    NOT NULL COMMENT 'input_data|output_data|feature_table|staging_table',
  contract_name     STRING    NOT NULL,
  contract_version  INT       NOT NULL,
  table_name        STRING,
  table_catalog     STRING,
  table_schema      STRING,
  uc_path           STRING    COMMENT 'catalog.schema.table',
  purpose           STRING,
  owner_email       STRING,
  owner_team        STRING,
  freshness_hours   INT,
  availability_pct  FLOAT,
  max_latency_seconds INT,
  requires_pii_encryption     BOOLEAN,
  requires_row_level_security BOOLEAN,
  audit_logging_enabled       BOOLEAN,
  lineage_tracking_enabled    BOOLEAN,
  retention_days    INT,
  archive_after_days INT,
  created_timestamp TIMESTAMP,
  created_by        STRING,
  last_updated      TIMESTAMP,
  last_updated_by   STRING,
  change_description STRING,
  is_active         BOOLEAN,
  is_validated      BOOLEAN,
  validated_by      STRING,
  validated_timestamp TIMESTAMP,
  CONSTRAINT pk_data_contracts PRIMARY KEY (contract_id),
  CONSTRAINT fk_data_contracts_projects FOREIGN KEY (project_id) REFERENCES {catalog}.{schema}.projects(project_id)
) COMMENT 'Data contract definitions';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.data_contract_columns (
  column_id           STRING    NOT NULL COMMENT 'UUID',
  contract_id         STRING    NOT NULL COMMENT 'FK → data_contracts',
  column_order        INT,
  column_name         STRING    NOT NULL,
  column_description  STRING,
  data_type           STRING    NOT NULL,
  is_nullable         BOOLEAN,
  is_unique           BOOLEAN,
  is_partition_column BOOLEAN,
  is_key_column       BOOLEAN,
  allowed_values      ARRAY<STRING>,
  min_value           FLOAT,
  max_value           FLOAT,
  pattern_regex       STRING,
  quality_rules       STRING    COMMENT 'JSON: null_check, range_check, etc.',
  pii_level           STRING    COMMENT 'none|low|medium|high',
  data_classification STRING    COMMENT 'public|internal|sensitive|restricted',
  is_fairness_attribute  BOOLEAN,
  is_required_for_quality BOOLEAN,
  can_have_quality_issues BOOLEAN,
  monitor_for_drift   BOOLEAN,
  drift_type          STRING,
  drift_threshold     FLOAT,
  source_system       STRING,
  transformation_logic STRING,
  created_timestamp   TIMESTAMP,
  created_by          STRING,
  last_updated        TIMESTAMP,
  last_updated_by     STRING,
  CONSTRAINT pk_data_contract_columns PRIMARY KEY (column_id),
  CONSTRAINT fk_data_contract_columns FOREIGN KEY (contract_id) REFERENCES {catalog}.{schema}.data_contracts(contract_id)
) COMMENT 'Column specifications for data contracts';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.data_contract_versions (
  version_id         STRING    NOT NULL COMMENT 'UUID',
  contract_id        STRING    NOT NULL COMMENT 'FK → data_contracts',
  version_number     INT       NOT NULL,
  created_timestamp  TIMESTAMP,
  created_by         STRING,
  change_type        STRING    COMMENT 'created|updated|column_added|column_removed|column_modified',
  change_description STRING,
  git_commit_hash    STRING,
  contract_snapshot  STRING    COMMENT 'Full contract JSON snapshot',
  columns_snapshot   STRING    COMMENT 'All columns JSON snapshot',
  CONSTRAINT pk_data_contract_versions PRIMARY KEY (version_id),
  CONSTRAINT fk_data_contract_versions FOREIGN KEY (contract_id) REFERENCES {catalog}.{schema}.data_contracts(contract_id)
) COMMENT 'Version history for data contracts';

-- ── Model Management ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.models (
  model_id               STRING    NOT NULL COMMENT 'UUID',
  project_id             STRING    NOT NULL COMMENT 'FK → projects',
  model_name             STRING    NOT NULL,
  mlflow_model_uri       STRING,
  current_version_id     STRING,
  current_production_tag STRING    COMMENT 'current|shadow|canary|ab_test|previous',
  model_type             STRING    COMMENT 'sklearn|xgboost|tensorflow|pytorch|huggingface|other',
  framework              STRING,
  framework_version      STRING,
  status                 STRING    COMMENT 'development|testing|staging|production|archived',
  is_production          BOOLEAN,
  owner_email            STRING,
  team_name              STRING,
  created_timestamp      TIMESTAMP,
  created_by             STRING,
  last_updated           TIMESTAMP,
  last_updated_by        STRING,
  CONSTRAINT pk_models PRIMARY KEY (model_id),
  CONSTRAINT fk_models_projects FOREIGN KEY (project_id) REFERENCES {catalog}.{schema}.projects(project_id)
) COMMENT 'Core model registry';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.model_versions (
  version_id                 STRING    NOT NULL COMMENT 'UUID',
  model_id                   STRING    NOT NULL COMMENT 'FK → models',
  version_number             INT,
  version_string             STRING,
  mlflow_version_id          STRING,
  mlflow_stage               STRING    COMMENT 'None|Staging|Production|Archived',
  training_timestamp         TIMESTAMP,
  training_duration_seconds  INT,
  training_data_version_id   STRING,
  training_code_commit       STRING,
  model_artifact_uri         STRING,
  model_serialization_format STRING,
  feature_names              ARRAY<STRING>,
  accuracy                   FLOAT,
  auc_roc                    FLOAT,
  precision                  FLOAT,
  recall                     FLOAT,
  f1_score                   FLOAT,
  custom_metrics             MAP<STRING, FLOAT>,
  fairness_demographic_parity FLOAT,
  fairness_equalized_odds     FLOAT,
  fairness_calibration        FLOAT,
  fairness_test_passed        BOOLEAN,
  training_data_quality_score FLOAT,
  status                     STRING    COMMENT 'registered|approved|deployed|deprecated',
  tags                       ARRAY<STRING>,
  approved_by                STRING,
  approved_timestamp         TIMESTAMP,
  approval_comment           STRING,
  created_timestamp          TIMESTAMP,
  created_by                 STRING,
  CONSTRAINT pk_model_versions PRIMARY KEY (version_id),
  CONSTRAINT fk_model_versions_models FOREIGN KEY (model_id) REFERENCES {catalog}.{schema}.models(model_id)
) COMMENT 'Versioned model artifacts and metadata';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.model_performance (
  performance_id             STRING    NOT NULL COMMENT 'UUID',
  version_id                 STRING    NOT NULL COMMENT 'FK → model_versions',
  model_id                   STRING    NOT NULL COMMENT 'FK → models',
  measurement_timestamp      TIMESTAMP,
  measurement_window         STRING    COMMENT 'last_1h|last_24h|last_7d|etc.',
  predictions_count          BIGINT,
  error_count                INT,
  error_rate_pct             FLOAT,
  accuracy                   FLOAT,
  auc_roc                    FLOAT,
  precision                  FLOAT,
  recall                     FLOAT,
  accuracy_vs_baseline_delta FLOAT,
  performance_degraded       BOOLEAN,
  degradation_pct            FLOAT,
  fairness_demographic_parity FLOAT,
  fairness_equalized_odds     FLOAT,
  fairness_test_passed        BOOLEAN,
  latency_p50_ms             FLOAT,
  latency_p95_ms             FLOAT,
  latency_p99_ms             FLOAT,
  throughput_qps             FLOAT,
  data_quality_score         FLOAT,
  has_data_drift             BOOLEAN,
  data_drift_ks_stat         FLOAT,
  created_timestamp          TIMESTAMP,
  CONSTRAINT pk_model_performance PRIMARY KEY (performance_id),
  CONSTRAINT fk_model_performance_versions FOREIGN KEY (version_id) REFERENCES {catalog}.{schema}.model_versions(version_id)
) COMMENT 'Production performance metrics over time';

-- ── Approvals & Governance ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.approvals (
  approval_id                  STRING    NOT NULL COMMENT 'UUID',
  model_id                     STRING    NOT NULL COMMENT 'FK → models',
  approval_type                STRING    COMMENT 'code_review|fairness_review|legal_review|business_approval|security_scan|end_to_end_test',
  approval_gate                STRING    COMMENT 'Gate in the promotion workflow',
  requested_timestamp          TIMESTAMP,
  requested_by                 STRING,
  required_count               INT,
  approval_responses           STRING    COMMENT 'JSON array of individual decisions',
  approved_count               INT,
  rejected_count               INT,
  status                       STRING    COMMENT 'pending|approved|rejected|needs_changes',
  completed_timestamp          TIMESTAMP,
  override_requested           BOOLEAN,
  override_requested_by        STRING,
  override_requested_timestamp TIMESTAMP,
  override_approved_by         STRING,
  override_approval_timestamp  TIMESTAMP,
  override_reason              STRING,
  created_timestamp            TIMESTAMP,
  CONSTRAINT pk_approvals PRIMARY KEY (approval_id),
  CONSTRAINT fk_approvals_models FOREIGN KEY (model_id) REFERENCES {catalog}.{schema}.models(model_id)
) COMMENT 'Approval request and decision tracking';

-- ── Data Quality ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.data_quality_assessments (
  assessment_id          STRING    NOT NULL COMMENT 'UUID',
  project_id             STRING    NOT NULL COMMENT 'FK → projects',
  contract_id            STRING    COMMENT 'FK → data_contracts',
  assessment_timestamp   TIMESTAMP,
  assessment_type        STRING    COMMENT 'training_data|inference_data|production_data',
  data_version_id        STRING,
  table_name             STRING,
  row_count              BIGINT,
  quality_score          FLOAT,
  quality_status         STRING    COMMENT 'excellent|good|acceptable|poor|critical',
  column_quality_scores  MAP<STRING, FLOAT>,
  failed_checks          STRING    COMMENT 'JSON array of failed check details',
  null_issues_found          INT,
  range_issues_found         INT,
  uniqueness_issues_found    INT,
  format_issues_found        INT,
  outlier_issues_found       INT,
  distribution_issues_found  INT,
  pii_columns_detected   ARRAY<STRING>,
  created_timestamp      TIMESTAMP,
  created_by             STRING,
  CONSTRAINT pk_data_quality PRIMARY KEY (assessment_id),
  CONSTRAINT fk_data_quality_projects FOREIGN KEY (project_id) REFERENCES {catalog}.{schema}.projects(project_id)
) COMMENT 'Data quality assessment results';

-- ── Drift Detection ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.drift_monitoring_config (
  config_id              STRING    NOT NULL COMMENT 'UUID',
  model_id               STRING    NOT NULL COMMENT 'FK → models',
  field_name             STRING    NOT NULL,
  field_type             STRING    COMMENT 'feature|target|context',
  monitor_data_drift     BOOLEAN,
  monitor_quality_drift  BOOLEAN,
  monitor_value_drift    BOOLEAN,
  data_drift_ks_threshold  FLOAT,
  quality_drift_threshold  FLOAT,
  value_drift_threshold    FLOAT,
  alert_on_drift         BOOLEAN,
  alert_recipients       ARRAY<STRING>,
  alert_severity         STRING    COMMENT 'info|warning|critical',
  is_enabled             BOOLEAN,
  created_timestamp      TIMESTAMP,
  created_by             STRING,
  last_updated           TIMESTAMP,
  CONSTRAINT pk_drift_config PRIMARY KEY (config_id),
  CONSTRAINT fk_drift_config_models FOREIGN KEY (model_id) REFERENCES {catalog}.{schema}.models(model_id)
) COMMENT 'Drift monitoring configuration per field';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.drift_detection_results (
  result_id              STRING    NOT NULL COMMENT 'UUID',
  model_id               STRING    NOT NULL COMMENT 'FK → models',
  config_id              STRING    NOT NULL COMMENT 'FK → drift_monitoring_config',
  measurement_timestamp  TIMESTAMP,
  measurement_period     STRING,
  field_name             STRING,
  drift_type             STRING    COMMENT 'data_drift|quality_drift|value_drift',
  drift_detected         BOOLEAN,
  drift_score            FLOAT,
  drift_severity         STRING    COMMENT 'none|low|medium|high|critical',
  baseline_distribution  STRING    COMMENT 'Statistical summary JSON',
  current_distribution   STRING    COMMENT 'Statistical summary JSON',
  alert_triggered        BOOLEAN,
  alert_timestamp        TIMESTAMP,
  investigation_notes    STRING,
  action_taken           STRING,
  created_timestamp      TIMESTAMP,
  CONSTRAINT pk_drift_results PRIMARY KEY (result_id),
  CONSTRAINT fk_drift_results_models FOREIGN KEY (model_id) REFERENCES {catalog}.{schema}.models(model_id)
) COMMENT 'Drift detection results over time';

-- ── Alerting ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.alerts (
  alert_id                 STRING    NOT NULL COMMENT 'UUID',
  model_id                 STRING    NOT NULL COMMENT 'FK → models',
  alert_name               STRING    NOT NULL,
  alert_type               STRING    COMMENT 'standard|custom',
  metric_name              STRING,
  threshold_value          FLOAT,
  comparison_operator      STRING    COMMENT '>|<|>=|<=|==|!=',
  monitoring_interval      STRING    COMMENT 'realtime|15m|hourly|daily',
  severity                 STRING    COMMENT 'info|warning|critical',
  alert_destinations       ARRAY<STRING>,
  recipient_emails         ARRAY<STRING>,
  recipient_slack_channels ARRAY<STRING>,
  is_enabled               BOOLEAN,
  created_timestamp        TIMESTAMP,
  created_by               STRING,
  CONSTRAINT pk_alerts PRIMARY KEY (alert_id),
  CONSTRAINT fk_alerts_models FOREIGN KEY (model_id) REFERENCES {catalog}.{schema}.models(model_id)
) COMMENT 'Alert configurations';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.alert_history (
  event_id               STRING    NOT NULL COMMENT 'UUID',
  alert_id               STRING    NOT NULL COMMENT 'FK → alerts',
  model_id               STRING    NOT NULL,
  triggered_timestamp    TIMESTAMP,
  alert_value            FLOAT,
  alert_severity         STRING,
  notification_sent      BOOLEAN,
  notification_timestamp TIMESTAMP,
  notification_channel   STRING,
  resolved               BOOLEAN,
  resolved_timestamp     TIMESTAMP,
  resolution_notes       STRING,
  created_timestamp      TIMESTAMP,
  CONSTRAINT pk_alert_history PRIMARY KEY (event_id),
  CONSTRAINT fk_alert_history_alerts FOREIGN KEY (alert_id) REFERENCES {catalog}.{schema}.alerts(alert_id)
) COMMENT 'Alert firing events and resolutions';

-- ── Feature Store & Lineage ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.features (
  feature_id          STRING    NOT NULL COMMENT 'UUID',
  project_id          STRING    COMMENT 'FK → projects (null if shared)',
  feature_name        STRING    NOT NULL,
  feature_description STRING,
  feature_type        STRING    COMMENT 'numeric|categorical|text|datetime',
  feature_table_name  STRING,
  feature_column_name STRING,
  owner_email         STRING,
  owner_team          STRING,
  freshness_hours     INT,
  availability_pct    FLOAT,
  feature_version     STRING,
  is_active           BOOLEAN,
  is_shared           BOOLEAN,
  shared_with_teams   ARRAY<STRING>,
  created_timestamp   TIMESTAMP,
  created_by          STRING,
  last_updated        TIMESTAMP,
  CONSTRAINT pk_features PRIMARY KEY (feature_id)
) COMMENT 'Feature store feature definitions';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.feature_lineage (
  lineage_id               STRING    NOT NULL COMMENT 'UUID',
  feature_id               STRING    NOT NULL COMMENT 'FK → features',
  source_table_name        STRING,
  source_table_version     STRING,
  transformation_logic     STRING,
  transformation_code_hash STRING,
  dependent_feature_ids    ARRAY<STRING>,
  downstream_model_ids     ARRAY<STRING>,
  created_timestamp        TIMESTAMP,
  created_by               STRING,
  CONSTRAINT pk_feature_lineage PRIMARY KEY (lineage_id),
  CONSTRAINT fk_feature_lineage_features FOREIGN KEY (feature_id) REFERENCES {catalog}.{schema}.features(feature_id)
) COMMENT 'Feature lineage and dependencies';

-- ── Secrets & Infrastructure ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.secrets_management (
  secret_id              STRING    NOT NULL COMMENT 'UUID',
  project_id             STRING    NOT NULL COMMENT 'FK → projects',
  secret_name            STRING,
  secret_scope_name      STRING,
  secret_type            STRING    COMMENT 'api_token|personal_access_token|github_token',
  created_timestamp      TIMESTAMP,
  rotation_schedule_days INT,
  last_rotated_timestamp TIMESTAMP,
  next_rotation_timestamp TIMESTAMP,
  used_for               STRING,
  permissions            ARRAY<STRING>,
  rotation_history       STRING    COMMENT 'JSON array of rotation events',
  is_active              BOOLEAN,
  is_compromised         BOOLEAN,
  last_updated           TIMESTAMP,
  CONSTRAINT pk_secrets PRIMARY KEY (secret_id),
  CONSTRAINT fk_secrets_projects FOREIGN KEY (project_id) REFERENCES {catalog}.{schema}.projects(project_id)
) COMMENT 'Secret and rotation management';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.infrastructure_config (
  config_id         STRING    NOT NULL COMMENT 'UUID',
  project_id        STRING    NOT NULL,
  config_type       STRING    COMMENT 'cluster|warehouse|endpoint|job',
  resource_name     STRING,
  configuration     STRING    COMMENT 'Full resource config as JSON',
  is_active         BOOLEAN,
  status            STRING,
  last_updated      TIMESTAMP,
  last_status_check TIMESTAMP,
  CONSTRAINT pk_infrastructure PRIMARY KEY (config_id),
  CONSTRAINT fk_infrastructure_projects FOREIGN KEY (project_id) REFERENCES {catalog}.{schema}.projects(project_id)
) COMMENT 'Compute and infrastructure configuration tracking';

-- ── Cost Tracking ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.cost_tracking (
  cost_id            STRING    NOT NULL COMMENT 'UUID',
  model_id           STRING    NOT NULL,
  project_id         STRING    NOT NULL,
  date               DATE      NOT NULL,
  training_cost_usd  FLOAT,
  inference_cost_usd FLOAT,
  storage_cost_usd   FLOAT,
  compute_cost_usd   FLOAT,
  other_cost_usd     FLOAT,
  total_cost_usd     FLOAT,
  cost_center        STRING,
  billing_tag        STRING,
  created_timestamp  TIMESTAMP,
  CONSTRAINT pk_cost_tracking PRIMARY KEY (cost_id),
  CONSTRAINT fk_cost_tracking_models FOREIGN KEY (model_id) REFERENCES {catalog}.{schema}.models(model_id)
) COMMENT 'Daily cost tracking per model';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.budget_alerts (
  budget_id            STRING    NOT NULL COMMENT 'UUID',
  project_id           STRING    NOT NULL,
  budget_period        STRING    COMMENT 'monthly|quarterly|annual',
  budget_threshold_usd FLOAT,
  alert_at_pct         FLOAT,
  enabled              BOOLEAN,
  alert_recipients     ARRAY<STRING>,
  created_timestamp    TIMESTAMP,
  CONSTRAINT pk_budget_alerts PRIMARY KEY (budget_id),
  CONSTRAINT fk_budget_alerts_projects FOREIGN KEY (project_id) REFERENCES {catalog}.{schema}.projects(project_id)
) COMMENT 'Budget threshold configuration';

-- ── Audit Logging ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.audit_logs (
  audit_id        STRING    NOT NULL COMMENT 'UUID',
  event_timestamp TIMESTAMP NOT NULL COMMENT 'UTC event time',
  action_type     STRING    NOT NULL COMMENT 'model_created|approval_requested|deployment|configuration_changed|etc.',
  model_id        STRING    COMMENT 'FK → models (if applicable)',
  project_id      STRING    COMMENT 'FK → projects',
  approval_id     STRING    COMMENT 'FK → approvals (if applicable)',
  actor_email     STRING    COMMENT 'Who performed the action',
  actor_role      STRING    COMMENT 'data_scientist|ml_engineer|legal|etc.',
  actor_ip_address STRING,
  resource_type   STRING    COMMENT 'model|approval|configuration|etc.',
  resource_id     STRING,
  change_details  STRING    COMMENT 'JSON describing what changed',
  old_value       STRING,
  new_value       STRING,
  action_status   STRING    COMMENT 'success|failure|pending',
  error_message   STRING,
  context_info    STRING    COMMENT 'Additional context JSON',
  is_immutable    BOOLEAN,
  CONSTRAINT pk_audit_logs PRIMARY KEY (audit_id)
) COMMENT 'Immutable audit trail of all actions';

-- ── Installation Config ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.installation_config (
  config_id             STRING    NOT NULL COMMENT 'UUID',
  config_version        INT       NOT NULL,
  created_timestamp     TIMESTAMP,
  created_by            STRING,
  org_name              STRING,
  regulated_industry    STRING,
  compliance_frameworks ARRAY<STRING>,
  support_email         STRING,
  deployment_pattern    STRING,
  primary_cloud         STRING,
  github_org            STRING,
  persona_config        STRING    COMMENT 'JSON: group → permissions mapping',
  monitoring_defaults   STRING    COMMENT 'JSON: alert thresholds, destinations',
  approval_workflow_defaults STRING COMMENT 'JSON: gate requirements per transition',
  is_active             BOOLEAN,
  CONSTRAINT pk_installation_config PRIMARY KEY (config_id)
) COMMENT 'Organisation-level installation configuration';
