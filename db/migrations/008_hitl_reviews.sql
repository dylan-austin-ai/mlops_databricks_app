-- §11: per-prediction human review for high-stakes decisions — distinct from
-- approval gates on model promotion (§15). Decision writes use a conditional
-- MERGE (decision IS NULL guard) so two reviewers can't both decide.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.hitl_reviews (
  prediction_id STRING NOT NULL COMMENT 'client_request_id of the prediction under review',
  project_id STRING NOT NULL COMMENT 'FK → projects',
  presented_timestamp TIMESTAMP NOT NULL COMMENT 'when the item entered the queue — SLA clock',
  reviewer_email STRING,
  decision STRING COMMENT 'approved | overridden | rejected — NULL while pending',
  overridden_value STRING,
  decision_timestamp TIMESTAMP,
  comment STRING,
  escalated BOOLEAN COMMENT 'true once SLA breach escalated it (§29.3: never auto-approve)',
  CONSTRAINT pk_hitl_reviews PRIMARY KEY (prediction_id)
) COMMENT 'Per-prediction human review queue (§11.2)';

-- §11.1/§11.4: per-project oversight configuration. The mechanism is chosen to
-- fit the deployment pattern (§11.4 table), defaulted per the accepted §29.2
-- suggestion, and is a governance-consequential field the Smart Defaults
-- Engine must never auto-collapse (§29.3).
ALTER TABLE {catalog}.{schema}.projects ADD COLUMNS (
  requires_human_review BOOLEAN COMMENT 'per-prediction review required (§11.1)',
  hitl_confidence_threshold FLOAT COMMENT 'route only predictions below this confidence; NULL = all',
  hitl_mode STRING COMMENT 'synchronous | asynchronous | sampling | escalation | batch_audit (§11.4)',
  hitl_sla_minutes INT COMMENT 'async review SLA; breach escalates, never auto-approves'
)
