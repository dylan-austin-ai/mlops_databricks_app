-- §19.2: Capacity Service — workspace-level job/endpoint/concurrent-run
-- counts against an internally-set alert threshold, so pressure is flagged
-- before a real Model Serving ceiling is hit (not published per-workspace),
-- not discovered by hitting it.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.capacity_snapshots (
  snapshot_id             STRING    NOT NULL COMMENT 'UUID',
  measured_timestamp      TIMESTAMP NOT NULL,
  job_count               BIGINT,
  endpoint_count          BIGINT,
  concurrent_run_count    BIGINT,
  endpoint_warn_threshold BIGINT,
  status                  STRING    NOT NULL COMMENT 'ok | warning',
  detail                  STRING,
  CONSTRAINT pk_capacity_snapshots PRIMARY KEY (snapshot_id)
) COMMENT 'Workspace resource utilization vs known limits (§19.2)';

-- §17.4: Reconciliation/Feedback Join/Portfolio Analytics/Feature Catalog
-- jobs+warehouses (tagged component=control_plane) are cost that scales with
-- the whole portfolio, not any one project — kept out of per-project
-- mlops.cost_tracking and given its own budget threshold.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.control_plane_costs (
  control_plane_cost_id STRING    NOT NULL COMMENT 'UUID',
  date                   DATE      NOT NULL,
  total_cost_usd         FLOAT,
  created_timestamp      TIMESTAMP,
  CONSTRAINT pk_control_plane_costs PRIMARY KEY (control_plane_cost_id)
) COMMENT 'Control-plane overhead cost, distinct from per-project costs (§17.4)';
