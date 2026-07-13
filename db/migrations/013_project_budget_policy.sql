-- Owner request 2026-07-12: per-project cost attribution via Databricks'
-- native serverless Budget Policy feature (services/budget_policy_service.py).
-- Mirrors the existing per-project infra-id columns (mlflow_experiment_id,
-- secret_scope_name) already on this table.
ALTER TABLE {catalog}.{schema}.projects ADD COLUMNS (
  budget_policy_id STRING COMMENT 'Databricks account-level Budget Policy id attributing this project''s serverless usage'
)
