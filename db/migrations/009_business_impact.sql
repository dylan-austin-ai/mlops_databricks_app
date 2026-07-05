-- §14.2: business outcome attribution — a business outcome is another form of
-- delayed ground truth with a dollar value attached (reuses the §10.2 join).
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.business_impact (
  project_id STRING NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  revenue_lift_usd FLOAT,
  loss_avoided_usd FLOAT,
  automation_rate_pct FLOAT COMMENT '% of decisions made without human review',
  risk_reduction_notes STRING,
  computed_timestamp TIMESTAMP NOT NULL,
  CONSTRAINT pk_business_impact PRIMARY KEY (project_id, period_start, period_end)
) COMMENT 'Business outcome attribution, rolled up into Portfolio Analytics (§14.1)';

-- §14.4: business_value_fn is governed like a policy pack, not arbitrary code —
-- declarative mapping with required review provenance, changed via PR review.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.business_value_fns (
  project_id STRING NOT NULL,
  definition_json STRING NOT NULL COMMENT 'declarative (predicted, actual) → USD mapping',
  assumption_source STRING NOT NULL COMMENT 'where the dollar assumptions come from',
  reviewed_by STRING COMMENT 'who last reviewed the assumptions',
  last_reviewed_date DATE COMMENT 'review older than 365d ⇒ low-confidence rollup (§14.4)',
  created_timestamp TIMESTAMP NOT NULL,
  CONSTRAINT pk_business_value_fns PRIMARY KEY (project_id)
) COMMENT 'Governed per-project business value functions (§14.4)'
