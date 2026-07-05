-- §10: label quality & feedback loops.
-- A label source is just a data contract with a declared arrival-latency SLA
-- (§10.1) — contract_type='label_source' plus the columns below.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.label_feedback (
  prediction_id STRING NOT NULL COMMENT 'client_request_id captured at serving time (§9.2)',
  project_id STRING NOT NULL COMMENT 'FK → projects',
  model_version_id STRING COMMENT 'FK → model_versions, when resolvable',
  predicted_value STRING,
  actual_label STRING,
  label_source_table STRING NOT NULL COMMENT 'UC table the ground truth arrived in',
  prediction_timestamp TIMESTAMP,
  label_arrived_timestamp TIMESTAMP,
  latency_days FLOAT COMMENT 'observed prediction→label latency',
  correct BOOLEAN COMMENT 'predicted_value = actual_label',
  created_timestamp TIMESTAMP NOT NULL,
  CONSTRAINT pk_label_feedback PRIMARY KEY (prediction_id)
) COMMENT 'Closes the loop between predictions and eventual ground truth (§10.2)';

ALTER TABLE {catalog}.{schema}.data_contracts ADD COLUMNS (
  label_source_table STRING COMMENT 'UC table where ground truth lands (§10.1)',
  label_source_column STRING COMMENT 'column holding the outcome value',
  label_join_key STRING COMMENT 'column matching predictions, default client_request_id',
  label_latency_days FLOAT COMMENT 'expected prediction→label arrival latency SLA'
);

ALTER TABLE {catalog}.{schema}.model_performance ADD COLUMNS (
  live_accuracy FLOAT COMMENT 'accuracy against joined ground truth, not training holdout (§10.3)',
  live_accuracy_labels_count BIGINT COMMENT 'how many labeled predictions back the live_accuracy figure'
)
