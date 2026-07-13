-- Owner request 2026-07-13: progressive per-step provisioning replaces the
-- former single waterfall at project creation. This table tracks each
-- individually-triggerable action (idempotency ground truth: "has this
-- already fired for this project?") and, for generated-file commits, the
-- content hash at commit time so a later step change can detect whether the
-- DS has since hand-edited the file (changed-assumptions drift guard) before
-- ever silently overwriting it.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.project_infrastructure_actions (
  action_id STRING NOT NULL COMMENT 'uuid',
  project_id STRING NOT NULL COMMENT 'FK → projects',
  action_name STRING NOT NULL COMMENT 'e.g. github_repo, uc_schema_dev, uc_volume_dev, mlflow_experiment, budget_policy, file_commit:src/train.py',
  status STRING NOT NULL COMMENT 'ok | skipped | failed',
  detail STRING COMMENT 'free-text outcome detail (resource id, url, error message)',
  resource_id STRING COMMENT 'the created resource identifier, when applicable (schema path, repo url, policy id, etc.)',
  content_hash STRING COMMENT 'SHA-256 of file content at commit time, only set for action_name LIKE file_commit:% — drift guard input',
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT pk_project_infrastructure_actions PRIMARY KEY (action_id)
) COMMENT 'Progressive per-step provisioning log — idempotency ground truth + drift-guard hashes (owner request 2026-07-13)';

-- Small manifest for Delta CLONE training-data snapshots (§ Step 3 data
-- versioning — "training data needs to be versioned and persisted so it can
-- be faithfully recreated at a later date"). DEEP CLONE, not SHALLOW, so the
-- snapshot survives independently of the source table's own retention/VACUUM.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.training_data_snapshots (
  snapshot_id STRING NOT NULL COMMENT 'uuid',
  project_id STRING NOT NULL COMMENT 'FK → projects',
  source_table STRING NOT NULL COMMENT 'the training dataset table path as entered in Step 3',
  snapshot_table STRING NOT NULL COMMENT 'fully-qualified DEEP CLONE destination table path',
  source_delta_version BIGINT COMMENT 'source table Delta version at clone time, when available',
  row_count BIGINT,
  created_at TIMESTAMP NOT NULL,
  created_by STRING NOT NULL,
  CONSTRAINT pk_training_data_snapshots PRIMARY KEY (snapshot_id)
) COMMENT 'Delta CLONE snapshots of training data for later faithful reproduction (owner request 2026-07-13)';
