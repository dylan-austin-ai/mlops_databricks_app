-- §5.2/§24: every bundle deploy is recorded with the exact reviewed plan it ran from,
-- so "what got approved" and "what got deployed" are provably the same artifact (§15.1).
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.bundle_deployments (
  deployment_id STRING NOT NULL COMMENT 'UUID',
  project_id STRING NOT NULL COMMENT 'FK → projects',
  target STRING NOT NULL COMMENT 'dev / staging / prod',
  plan_path STRING COMMENT 'path of the reviewed plan file',
  plan_hash STRING COMMENT 'sha256 of the reviewed plan file — matches approval record',
  actions_json STRING COMMENT 'JSON array of {resource, action} from the plan',
  status STRING NOT NULL COMMENT 'planned / deployed / verify_failed / failed / destroyed',
  detail STRING COMMENT 'error text or verification summary',
  actor_email STRING NOT NULL COMMENT 'who triggered it — OAuth identity, never the app',
  created_timestamp TIMESTAMP NOT NULL,
  CONSTRAINT pk_bundle_deployments PRIMARY KEY (deployment_id)
) COMMENT 'Bundle deploy audit trail — one row per plan/deploy/destroy operation'
