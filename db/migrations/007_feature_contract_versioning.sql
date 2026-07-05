-- §8.6: shared feature tables carry semantic versions with breakage protection.
-- Per the accepted §29.3 suggestion, a breaking change to a feature with
-- consumers requires acknowledgment from every consuming project's owner
-- BEFORE it may release — notify-after-the-fact is not enough for shared
-- features. Non-breaking changes release immediately.
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.feature_contract_changes (
  change_id STRING NOT NULL COMMENT 'UUID',
  feature_id STRING NOT NULL COMMENT 'FK → features',
  from_version STRING COMMENT 'features.feature_version at proposal time',
  to_version STRING NOT NULL,
  is_breaking BOOLEAN NOT NULL COMMENT 'column removed/type changed/semantics changed',
  description STRING,
  status STRING NOT NULL COMMENT 'pending_acks | released | rejected',
  proposed_by STRING NOT NULL,
  created_timestamp TIMESTAMP NOT NULL,
  released_timestamp TIMESTAMP,
  CONSTRAINT pk_feature_contract_changes PRIMARY KEY (change_id)
) COMMENT 'Proposed/released feature contract version changes (§8.6)';

CREATE TABLE IF NOT EXISTS {catalog}.{schema}.feature_change_acks (
  change_id STRING NOT NULL COMMENT 'FK → feature_contract_changes',
  project_id STRING NOT NULL COMMENT 'consuming project acknowledging the change',
  acked_by STRING NOT NULL,
  acked_timestamp TIMESTAMP NOT NULL,
  CONSTRAINT pk_feature_change_acks PRIMARY KEY (change_id, project_id)
) COMMENT 'Consumer acknowledgments required before a breaking change releases (§29.3)'
