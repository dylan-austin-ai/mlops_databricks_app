-- §20: model risk tiering + declarative policy packs, and §20.5's revalidation
-- trigger state. One policy_packs row per (pack, tier): §20.3's YAML authors
-- tiers inside a pack, so the §20.2 table gains a risk_tier column and a
-- composite key — the loader flattens each pack's tiers into rows.
ALTER TABLE {catalog}.{schema}.projects ADD COLUMNS (
  risk_tier STRING COMMENT 'org-defined tier, e.g. tier_1/tier_2/tier_3 (§20.1)',
  risk_tier_justification STRING COMMENT 'required one-line justification — governance-consequential field, never auto-collapsed (§29.3)',
  regulatory_frameworks ARRAY<STRING> COMMENT 'policy packs applied (§20.2)'
);

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.policy_packs (
  policy_pack_id STRING NOT NULL,
  risk_tier STRING NOT NULL COMMENT 'tier within the pack this row applies to',
  name STRING,
  required_approval_gates ARRAY<STRING>,
  required_contract_fields ARRAY<STRING>,
  min_documentation_fields ARRAY<STRING>,
  audit_log_retention_days INT,
  revalidation_frequency_days INT COMMENT 'NULL = no periodic revalidation for this tier',
  on_revalidation_due STRING COMMENT 'warn, block_new_traffic, or block_all_traffic (§20.5)',
  allows_override BOOLEAN,
  source_file STRING COMMENT 'YAML file of record — GitHub is source of truth (§20.3)',
  synced_timestamp TIMESTAMP,
  CONSTRAINT pk_policy_packs PRIMARY KEY (policy_pack_id, risk_tier)
) COMMENT 'Declarative regulatory/risk policy packs, selected per project (§20.2); synced from policy_packs/*.yaml';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.revalidation_flags (
  project_id STRING NOT NULL,
  uc_full_name STRING NOT NULL,
  champion_version INT,
  promoted_timestamp TIMESTAMP COMMENT 'from the §7.4 promoted_timestamp tag the check ran against',
  frequency_days INT NOT NULL COMMENT 'the lapsed revalidation window',
  on_due_action STRING NOT NULL COMMENT 'strictest on_revalidation_due across lapsed pack rows (§20.5)',
  status STRING NOT NULL COMMENT 'due | in_revalidation | cleared',
  revalidation_approval_ids ARRAY<STRING> COMMENT 'gate re-run approvals opened for this flag (§20.5)',
  due_since TIMESTAMP NOT NULL,
  cleared_timestamp TIMESTAMP,
  last_checked_timestamp TIMESTAMP,
  CONSTRAINT pk_revalidation_flags PRIMARY KEY (project_id, uc_full_name)
) COMMENT 'Production models whose policy-pack revalidation window has lapsed (§20.5)'
