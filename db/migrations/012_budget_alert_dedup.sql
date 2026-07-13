-- §17.3: budget_alerts existed in the base schema but nothing ever read or
-- wrote it — a dead table (IMG_1412 Cost Tracking gap). Wiring it up needs a
-- way to avoid re-notifying every reconciliation pass for the same breach;
-- these two columns are that de-dup key.
ALTER TABLE {catalog}.{schema}.budget_alerts ADD COLUMNS (
  last_alerted_period    STRING    COMMENT 'period identifier already notified for, e.g. 2026-07 (monthly)',
  last_alerted_timestamp TIMESTAMP COMMENT 'when the last breach notification was sent'
)
