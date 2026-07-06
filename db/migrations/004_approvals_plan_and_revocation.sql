-- §15.1: the approval record carries the exact plan file (path + hash) that was
-- reviewed, so the Saga Engine can deploy precisely what was approved.
-- §15.4: approvals are append-only — a revocation is a new record pointing at
-- the approval it revokes, never an edit or delete of the original.
ALTER TABLE {catalog}.{schema}.approvals ADD COLUMNS (
  plan_path STRING COMMENT 'path of the reviewed bundle plan file (§15.1)',
  plan_hash STRING COMMENT 'sha256 of the reviewed plan file — deploy refuses drift',
  revokes_approval_id STRING COMMENT 'set on approval_type=revocation rows: the approval being revoked (§15.4)'
)
