-- §21.1: the reconciliation jobs' entire premise is avoiding duplicated state,
-- which means there's no independent copy to cross-check if their logic breaks.
-- Each run therefore emits its own health signal; a run that stops changing
-- rows, or a join that previously matched rows suddenly matching zero, is a
-- strong signal of an upstream system-table schema change — surfaced as a
-- warning, not discovered months later.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.reconciliation_runs (
  run_id STRING NOT NULL COMMENT 'UUID',
  job_name STRING NOT NULL COMMENT 'which reconciliation pass ran',
  target_table STRING COMMENT 'the mlops.* table this pass maintains',
  rows_examined BIGINT,
  rows_changed BIGINT,
  status STRING NOT NULL COMMENT 'ok | warning | failed',
  detail STRING,
  run_timestamp TIMESTAMP NOT NULL,
  CONSTRAINT pk_reconciliation_runs PRIMARY KEY (run_id)
) COMMENT 'Self-monitoring health signals for scheduled reconciliation passes (§21.1)'
