-- §7.3: mlops.model_versions becomes a denormalized index over UC registry state,
-- refreshed by the Reconciliation Service — no longer the lifecycle source of truth.
ALTER TABLE {catalog}.{schema}.model_versions ADD COLUMNS (
  uc_full_name STRING COMMENT 'catalog.schema.model_name in the UC registry',
  uc_version INT COMMENT 'UC registry version number',
  current_aliases ARRAY<STRING> COMMENT 'aliases pointing at this version, synced from UC',
  last_reconciled_timestamp TIMESTAMP COMMENT 'when the Reconciliation Service last confirmed this row against UC'
)
