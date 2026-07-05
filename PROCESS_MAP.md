# Databricks MLOps App: Complete Process Map

## Overview

This process map defines the end-to-end workflow for data scientists and MLOps teams using the Databricks MLOps App, from initial project conception through production monitoring and eventual retirement.

---

## Phase 0: System Installation & Setup

**Timeline**: One-time (Day 1)
**Actors**: MLOps Admin, DevOps Engineer
**Approval Required**: Enterprise Architecture, Security

### Entry Criteria
- Organization has Databricks account(s) configured
- GitHub organization exists or will be created
- Team structure and roles defined
- Compliance/regulatory requirements documented

### Process Steps

#### Step 0.1: Launch Installation Interview
```
INPUT REQUIRED:
├── Organization Info
│   ├── Org name
│   ├── Regulated industry (financial, healthcare, etc.)
│   ├── Compliance frameworks (SOX, GDPR, HIPAA, etc.)
│   ├── Support email
│   └── Primary business domain
│
├── Deployment Configuration
│   ├── Deployment pattern (single_workspace, dual_workspace, multi_cloud)
│   ├── Primary cloud (AWS, Azure, GCP)
│   ├── Regions
│   ├── Dev workspace ID (if dual)
│   ├── Prod workspace ID (if dual)
│   └── Multi-cloud mapping (if applicable)
│
├── Databricks Infrastructure
│   ├── Default catalogs (mlops, feature_store, data)
│   ├── Dev cluster name & config
│   ├── Prod cluster name & config
│   ├── Default warehouse ID
│   ├── Compute autoscaling preferences
│   └── Network/VPC details
│
├── GitHub Configuration
│   ├── Org name/URL
│   ├── Branch protection rules
│   ├── Required code reviewers (default: 2)
│   ├── Status check requirements
│   └── CODEOWNERS template
│
├── Team & Personas
│   ├── Define persona groups:
│   │   ├── data_scientists (members, permissions)
│   │   ├── ml_engineers (members, permissions)
│   │   ├── legal_reviewers (members, permissions)
│   │   ├── business_stakeholders (members, permissions)
│   │   ├── security (members, permissions)
│   │   └── admin (members, permissions)
│   └── Default permissions per role
│
├── Data Governance Defaults
│   ├── Experiment retention (days)
│   ├── Inference table retention (days)
│   ├── Audit log retention (days)
│   ├── Model artifact retention (days)
│   └── Archive schedule
│
├── Approval Workflow Defaults
│   ├── dev_to_staging gates
│   ├── staging_to_prod_new_model gates
│   ├── staging_to_prod_update gates
│   ├── retraining_prod gates
│   └── model_deletion gates
│
├── Monitoring & Alerting Defaults
│   ├── Enable data drift monitoring (bool)
│   ├── Enable performance drift (bool)
│   ├── Enable fairness monitoring (bool)
│   ├── Alert destinations (Slack, email, both)
│   ├── Slack webhook URL (if applicable)
│   └── Email distribution lists
│
├── Secrets & Security
│   ├── Secret rotation schedule (days)
│   ├── Service account naming convention
│   ├── Secret scope naming convention
│   └── Cloud provider integrations (skip for now)
│
├── Feature Store Config
│   ├── Feature store catalog name
│   ├── Default TTL (days)
│   ├── Point-in-time support (bool)
│   └── Feature discovery sharing rules
│
└── Cost Tracking
    ├── Enable cost tracking (bool)
    ├── Cost center tagging strategy
    ├── Budget alert enabled (bool)
    ├── Monthly warning threshold (USD)
    └── Monthly critical threshold (USD)
```

#### Step 0.2: Auto-Generate Infrastructure
```
AUTOMATION TRIGGERED:
├── Create UC catalog structure
│   ├── Create mlops catalog with default schema
│   ├── Create feature_store catalog
│   ├── Create data catalog
│   └── Create archive catalog
│
├── Create State Management Tables
│   ├── mlops.projects
│   ├── mlops.models
│   ├── mlops.experiments
│   ├── mlops.data_versioning
│   ├── mlops.approvals
│   ├── mlops.secrets_management
│   ├── mlops.alerts
│   ├── mlops.cost_tracking
│   ├── mlops.audit_logs
│   ├── mlops.feature_definitions
│   ├── mlops.monitoring_configs
│   └── mlops.governance_rules
│
├── Create GitHub Organization Setup
│   ├── Create GitHub org (if not exists)
│   ├── Set branch protection on main (require 2 reviews, status checks)
│   ├── Create CODEOWNERS file template
│   ├── Create PR template
│   └── Create org-level GitHub Actions secrets
│
├── Create Databricks Resources
│   ├── Create dev cluster (if specified)
│   ├── Create prod cluster (if specified)
│   ├── Create serving endpoints (if applicable)
│   └── Configure autoscaling policies
│
├── Create Service Accounts & Secrets
│   ├── Create MLOps service account
│   ├── Create GitHub Actions service account
│   ├── Create secret scope: mlops-admin
│   ├── Create GitHub token secret
│   ├── Create Databricks API token secret
│   └── Create Slack webhook secret (if applicable)
│
├── Create RBAC & Group Mappings
│   ├── Create Databricks workspace groups
│   ├── Create GitHub organization teams
│   ├── Assign members to groups
│   ├── Configure workspace permissions
│   └── Configure repo permissions
│
└── Create Monitoring Infrastructure
    ├── Create default monitoring dashboard
    ├── Create alert notification channels
    ├── Configure email alerts
    ├── Configure Slack alerts
    └── Set up alert frequency rules
```

#### Step 0.3: Store Configuration
```
STORAGE:
├── Save installation_config.json to mlops catalog
├── Version control in UC
├── Document in Confluence/wiki
├── Distribute to admin team
└── Set up notification that setup is complete
```

### Outputs
- Installation config stored in UC
- Databricks workspace infrastructure created
- GitHub organization configured
- Service accounts and secrets created
- RBAC groups and permissions configured
- Monitoring dashboards deployed
- All actions logged in audit trail

### Approval Step
```
WHO APPROVES: MLOps Lead + Security Team
APPROVAL METHOD: In-app checkbox confirmation
APPROVAL CAPTURES:
├── Approver name & email
├── Timestamp
├── IP address
└── Comments/exceptions
```

---

## Phase 1: Project Initialization

**Timeline**: 30 minutes per model
**Actors**: Data Scientist (primary), MLOps Engineer (oversight), Team Lead (approval)
**Approval Required**: Team Lead (context), optional MLOps for non-standard requests

### Entry Criteria
- Data scientist is part of organization
- They have access to Databricks workspace
- They have idea for model (business problem understood)
- Training data exists or is being created

### Process Flow Diagram

```
START (Data Scientist Clicks "New Model")
    ↓
INTERVIEW PHASE 1: Basic Info (required)
├─ Model name
├─ Business problem
├─ Success metrics
├─ Team ownership
└─ Primary owner email
    ↓
INTERVIEW PHASE 2: Model Specs (required)
├─ Batch or real-time? ──→ [DECISION: Splits into two paths]
│   ├─ BATCH BRANCH
│   │  └─ How often? (hourly/daily/weekly/monthly)
│   │
│   └─ REAL-TIME BRANCH
│      ├─ P95 latency target
│      ├─ Uptime %
│      └─ Expected QPS
│
├─ Model type (auto-detect from training code, or manual select)
└─ Framework selection (sklearn, XGBoost, TensorFlow, etc.)
    ↓
INTERVIEW PHASE 3: Data Specs (required)
├─ Training data location
├─ Target variable
├─ Feature columns (auto or manual)
├─ Data size
├─ Contains PII? ──→ [DECISION]
│   ├─ YES: Which columns?
│   └─ NO: Skip
    ↓
INTERVIEW PHASE 4: Governance (required, with defaults)
├─ Fairness attributes ──→ [DECISION]
│   ├─ Include age, gender, race, custom?
│   ├─ Min fairness threshold
│   └─ Test framework (aif360, fairlearn, custom)
│
├─ Data quality required fields
└─ Data quality acceptable issues
    ↓
INTERVIEW PHASE 5: Deployment (required, with defaults)
├─ Retraining strategy ──→ [DECISION: manual/on_drift/scheduled/hybrid]
│   ├─ MANUAL BRANCH: No additional config needed
│   ├─ ON_DRIFT BRANCH: Drift threshold %
│   ├─ SCHEDULED BRANCH: Cron schedule
│   └─ HYBRID BRANCH: Both threshold & schedule
│
├─ Rollback configuration
│   ├─ Rollback on X errors? (Y/N, default 10)
│   └─ Time window (minutes)
│
├─ Canary deployment %
└─ Shadow mode first? (Y/N, default yes)
    ↓
INTERVIEW PHASE 6: Monitoring (required, with defaults)
├─ Monitor data drift? (default yes)
├─ Monitor performance? (default yes)
├─ Monitor endpoint uptime? (default yes)
├─ Custom metrics? (optional)
├─ Alert destinations (email/Slack/both)
└─ Alert threshold (% drop)
    ↓
INTERVIEW PHASE 7: Approval Gates (required, with defaults)
├─ Require code review? (default yes)
├─ Require business approval? (default yes)
├─ Require legal review? (default yes)
├─ Require security scan? (default yes)
├─ Require end-to-end test? (default yes)
└─ Min test coverage %? (default 100)
    ↓
REVIEW & SUBMIT
├─ DS reviews all answers
├─ App shows summary of implications
│   ├─ "This will require X approval(s)"
│   ├─ "Test coverage must be 100%"
│   ├─ "Fairness tests required: age, gender, race"
│   ├─ "Retraining strategy: hybrid (scheduled + drift-triggered)"
│   └─ "Staging soak time: 7 days minimum"
│
├─ DS confirms & submits
└─ App validates all required fields
    ↓
END (Auto-Generation Triggered)
```

### Step 1.1: Basic Info Collection

**Questions to Ask:**
```
1. "What's the name of your model?"
   └─ Validation: Alphanumeric + underscores, 3-50 chars
   └─ Check: Name not already in use
   └─ Auto-generated: GitHub repo name will be: mlops-{model_name}

2. "What business problem does it solve?"
   └─ Validation: Min 20 chars, max 500 chars
   └─ Purpose: Used in model card & documentation

3. "How do you measure success?"
   └─ Validation: Min 20 chars, max 500 chars
   └─ Purpose: Primary metric for acceptance tests

4. "Which team owns this?"
   └─ Type: Select from org teams (configured at setup)
   └─ Purpose: Team-level dashboards, cost allocation

5. "Who's the primary owner?"
   └─ Type: Email select (must be in organization)
   └─ Purpose: Notifications, approval routing, handoff tracking
   └─ Auto-check: Is this person part of data_scientists group?
```

**Automations Triggered:**
- Validate model name uniqueness
- Check email is valid Databricks user
- Check team exists in config
- Store answers to session state

**Outputs:**
```json
{
  "project_name": "customer_churn_prediction",
  "problem_statement": "Predict which customers are likely to churn in next 30 days",
  "success_metric": "AUC-ROC >= 0.85 on holdout test set",
  "team_name": "retention_team",
  "owner_email": "alice@acme.com"
}
```

### Step 1.2: Model Specifications

**Questions to Ask:**
```
1. "Will this model make batch or real-time predictions?"
   └─ Options: [batch] [real_time] [both]
   └─ This is a DECISION POINT that affects subsequent questions
   └─ Purpose: Determines serving infrastructure, monitoring, SLAs

BATCH PATH:
2a. "How often should this run?"
    └─ Options: [hourly] [daily] [weekly] [monthly]
    └─ Purpose: Schedule inference jobs, monitoring windows
    └─ SLA tracking: Define latency expectations

REAL-TIME PATH:
2b. "What's your target P95 latency? (ms)"
    └─ Type: Integer, default 500
    └─ Validation: Min 50, max 10000
    └─ Purpose: Endpoint config, alerting threshold

2c. "What's your target uptime %?"
    └─ Type: Float, default 99.9
    └─ Validation: Min 95.0, max 99.99
    └─ Purpose: SLA definition, alert thresholds

2d. "Expected queries per second (QPS)?"
    └─ Type: Integer, default 10
    └─ Validation: Min 1, max 100000
    └─ Purpose: Auto-scaling config for endpoint

BOTH PATHS:
3. "Model type (auto-detect or manual)?"
   └─ Auto-detect: "Upload training code or point to notebook?"
   └─ Manual select: [sklearn] [xgboost] [lightgbm] [tensorflow] [pytorch] [huggingface] [other]
   └─ Purpose: Test generation, artifact serialization, serving config
```

**Automations Triggered:**
```
IF real_time THEN
  └─ Flag for Databricks Model Serving deployment
  └─ Enable endpoint uptime monitoring
  └─ Enable latency monitoring
  └─ Create inference table

IF batch THEN
  └─ Flag for Databricks Jobs scheduling
  └─ Enable job duration monitoring
  └─ Create inference table with timestamp partitioning

IF model_type provided THEN
  └─ Store for test skeleton generation
  └─ Store for serialization logic
  └─ Store for inference code template
```

**Outputs:**
```json
{
  "inference_type": "batch",
  "batch_frequency": "daily",
  "sla_latency_ms": null,
  "sla_uptime_pct": null,
  "expected_qps": null,
  "model_type": "xgboost"
}
```

### Step 1.3: Data Specifications

**Questions to Ask:**
```
1. "Where's your training data?"
   └─ Options: [UC path] [local file upload] [external database]
   └─ Validation: Path must exist or file must be CSV/Parquet
   └─ Next action: App reads schema from data
   └─ Purpose: Validate features available, detect data types

2. "What's your target variable?"
   └─ Type: Column selector (from detected schema)
   └─ Validation: Must be numeric or binary
   └─ Purpose: Used for data quality checks, fairness testing

3. "Which columns are features (auto-detect or manual)?"
   └─ Auto-detect: App shows all non-target columns, DS accepts/rejects
   └─ Manual: DS selects from available columns
   └─ Purpose: Used for feature store schema, data quality checks

4. "Approximately how many rows in training data?"
   └─ Type: Integer
   └─ Purpose: Inform test data split ratios, performance expectations

5. "Does this data contain PII (Personally Identifiable Information)?"
   └─ Type: Yes/No
   └─ If YES:
      ├─ Follow-up: "Which columns contain PII?"
      ├─ Multi-select from all columns
      ├─ Auto-suggest: email, phone, ssn, name patterns
      └─ Purpose: Enable encryption, access controls, audit logging
```

**Automations Triggered:**
```
├─ Read data schema from UC or uploaded file
├─ Detect data types (numeric, string, date, etc.)
├─ Sample data for distribution analysis
├─ Generate data quality checks (nulls, ranges, distributions)
├─ Create table contract JSON (see next section)
├─ Detect potential fairness attributes (age, gender, etc.)
└─ Flag unusual patterns (high cardinality, outliers, etc.)
```

**Automations - Table Contract Auto-Generation:**
```
FOR EACH COLUMN:
├─ Generate description (using LLM cluster + DS context)
├─ Classify PII level (none, low, medium, high)
├─ Classify data sensitivity (public, internal, sensitive, restricted)
├─ Generate quality rules based on data type & distribution:
│  ├─ null_check: max acceptable null %
│  ├─ range_check: min/max values (for numeric)
│  ├─ uniqueness_check: must_be_unique?
│  ├─ format_check: regex pattern (for string)
│  ├─ outlier_detection: IQR threshold
│  └─ distribution_check: expected mean, tolerance %
│
└─ Mark if column is required for quality validation

RESULT: Auto-generated table contract JSON (DS reviews & edits)
```

**Outputs:**
```json
{
  "input_data_location": "feature_store.customer.training_data_v1",
  "target_variable": "churn_flag",
  "feature_columns": ["age", "lifetime_value", "purchase_frequency_30d", ...],
  "training_data_size_rows": 1000000,
  "contains_pii": true,
  "pii_columns": ["customer_id", "email"],
  "table_contract": {
    "columns": [
      {
        "name": "age",
        "type": "int",
        "nullable": true,
        "pii_level": "medium",
        "classification": "internal",
        "quality_rules": {
          "null_check": {"max_null_pct": 5.0},
          "range_check": {"min": 18, "max": 120},
          "outlier_detection": {"method": "iqr", "threshold": 3.0}
        }
      },
      ...
    ]
  }
}
```

### Step 1.4: Governance Configuration

**Questions to Ask:**
```
1. "Should we test fairness on protected attributes?"
   └─ Yes/No (default: Yes if regulated industry)
   └─ If YES, follow-up questions:

2. "Which attributes should we test?"
   └─ Multi-select: [age] [gender] [race] [custom]
   └─ Purpose: Define protected classes for fairness testing

3. "What's the minimum fairness threshold? (% disparity)"
   └─ Type: Integer, range 0-50, default 10
   └─ Interpretation: "Maximum % difference in outcomes between groups"
   └─ Purpose: Determines if fairness tests pass/fail

4. "Which fairness testing framework?"
   └─ Options: [aif360] [fairlearn] [custom]
   └─ Default: aif360 (if available)
   └─ Purpose: Determines fairness test implementation

5. "Which fields MUST pass data quality tests?"
   └─ Multi-select from features
   └─ Default: All feature columns
   └─ Purpose: Block training if these fields degrade
   └─ DS override: Can mark as "warnings only"

6. "Which fields can have quality issues? (DS will accept)"
   └─ Multi-select from features
   └─ Default: None
   └─ Purpose: Allow training to proceed even with issues in these columns
   └─ Caveat: Issues still logged, still monitored
```

**Automations Triggered:**
```
├─ Determine fairness testing framework setup
├─ Generate fairness test skeletons
├─ Configure protected attribute mapping
├─ Create data quality thresholds JSON
├─ Generate data quality tests for required fields
└─ Flag override strategy for acceptable-issue fields
```

**Outputs:**
```json
{
  "fairness_attributes": ["age", "gender"],
  "fairness_threshold_pct": 10,
  "bias_test_type": "aif360",
  "data_quality_required_fields": ["age", "lifetime_value"],
  "data_quality_acceptable_issues": ["custom_feature_1"],
  "fairness_tests": [
    "demographic_parity",
    "equalized_odds",
    "calibration"
  ]
}
```

### Step 1.5: Deployment Configuration

**Questions to Ask:**
```
1. "How should this model be retrained?"
   └─ Options: [manual] [on_drift] [scheduled] [hybrid]
   └─ This is a DECISION POINT

MANUAL BRANCH:
  └─ No additional config, DS triggers retraining manually

ON_DRIFT BRANCH:
2a. "What drift threshold triggers retraining? (%)"
    └─ Type: Float, range 0-50, default 5.0
    └─ Interpretation: "If performance drops >5%, retrain"

SCHEDULED BRANCH:
2b. "What's the retraining schedule? (cron)"
    └─ Type: Cron expression, default "0 2 * * *" (2 AM daily)
    └─ Purpose: Trigger retraining on fixed schedule

HYBRID BRANCH:
2c. Both above: "Schedule cron + drift threshold"

3. "Rollback configuration: Rollback on X errors? (Y/N)"
   └─ If YES:
      ├─ How many errors trigger rollback? (default 10)
      ├─ In what time window? (minutes, default 5)
      └─ Implementation: Monitor error_rate in production
   └─ If NO: Manual rollback only

4. "Canary deployment: Start with % traffic? (Y/N)"
   └─ If YES: "What % of traffic? (default 0, optional 5-20)"
   └─ Purpose: Gradual rollout before full deployment
   └─ Implementation: Route X% traffic to new model, (100-X)% to current

5. "Shadow mode first? (Y/N)"
   └─ Default: Yes (especially for first-time models)
   └─ Purpose: Run new model alongside current, collect metrics, no traffic impact
   └─ Duration: Configurable, default 7 days
```

**Automations Triggered:**
```
├─ Generate retraining job template (schedule-based)
├─ Generate drift detection logic
├─ Configure rollback triggers & automation
├─ Generate canary deployment playbook
├─ Create shadow mode configuration
├─ Set up inference monitoring for gradual rollout
└─ Generate promotion automation rules
```

**Outputs:**
```json
{
  "retraining_strategy": "hybrid",
  "retraining_drift_threshold": 5.0,
  "retraining_schedule": "0 2 * * *",
  "rollback_enabled": true,
  "rollback_error_threshold": 10,
  "rollback_time_window_minutes": 5,
  "canary_percentage": 10.0,
  "shadow_mode": true,
  "shadow_mode_duration_days": 7
}
```

### Step 1.6: Monitoring & Alerting Configuration

**Questions to Ask:**
```
1. "Monitor input data drift? (Y/N)"
   └─ Default: Yes
   └─ Purpose: Detect when training data distribution changes
   └─ Metric: Kolmogorov-Smirnov statistic

2. "Monitor model performance drift? (Y/N)"
   └─ Default: Yes
   └─ Purpose: Detect when model accuracy degrades
   └─ Metric: Accuracy, AUC, custom metric

3. "Monitor endpoint uptime? (Y/N)"
   └─ Default: Yes (especially for real-time)
   └─ Purpose: Alert if endpoint is down
   └─ Metric: Endpoint health check

4. "Any custom metrics to monitor?"
   └─ Optional: Free-form text describing metrics
   └─ Examples: "True positive rate for fraud", "P95 latency"
   └─ Purpose: Define domain-specific success measures

5. "Alert destinations? (email/Slack/both)"
   └─ Options: [email] [slack] [both]
   └─ Default: email
   └─ For Slack: Use org-wide webhook (configured at setup)
   └─ For email: Use org distribution list

6. "Alert threshold: Drop in performance triggers alert? (%)"
   └─ Type: Float, range 1-50, default 5.0
   └─ Interpretation: "If performance drops >5%, send alert"
   └─ Purpose: Define sensitivity of monitoring
```

**Automations Triggered:**
```
├─ Create monitoring dashboard (per model)
├─ Configure standard alerts:
│  ├─ Data drift alert
│  ├─ Performance drift alert
│  ├─ Endpoint down alert
│  ├─ Error rate alert
│  ├─ Latency alert
│  └─ Volume anomaly alert
│
├─ Create custom metric monitoring (if specified)
├─ Configure alert routing:
│  ├─ To email list or Slack channel
│  └─ With frequency & severity levels
│
└─ Create alert escalation rules
```

**Outputs:**
```json
{
  "monitor_data_drift": true,
  "monitor_performance_drift": true,
  "monitor_endpoint_uptime": true,
  "custom_monitoring_metrics": "True positive rate >0.95",
  "alert_destinations": ["email", "slack"],
  "alert_threshold_deviation_pct": 5.0,
  "monitoring_config": {
    "data_drift_ks_threshold": 0.1,
    "performance_drift_pct": 5.0,
    "endpoint_down_threshold_minutes": 5,
    "error_rate_threshold_pct": 1.0,
    "latency_threshold_multiplier": 2.0,
    "volume_anomaly_sigma": 3.0
  }
}
```

### Step 1.7: Approval Gates Configuration

**Questions to Ask:**
```
1. "Require code review before staging? (Y/N)"
   └─ Default: Yes
   └─ If YES: How many reviewers? (default 2)
   └─ Purpose: Ensure code quality, knowledge sharing

2. "Require business approval for prod? (Y/N)"
   └─ Default: Yes
   └─ Purpose: Business stakeholders sign off on model deployment

3. "Require legal/fairness review? (Y/N)"
   └─ Default: Yes (auto-yes if regulated industry)
   └─ Purpose: Legal team reviews fairness results
   └─ Caveat: Cannot be disabled in regulated industries

4. "Require security scan? (Y/N)"
   └─ Default: Yes
   └─ Purpose: pip-audit for vulnerable dependencies
   └─ Auto-enforce: Weekly rescans for production models

5. "Require end-to-end test? (Y/N)"
   └─ Default: Yes
   └─ Purpose: Model must successfully train & infer in staging
   └─ Gate: Cannot promote to prod without this

6. "Minimum test coverage %?"
   └─ Type: Integer, range 50-100, default 100
   └─ Purpose: Require comprehensive unit/integration tests
   └─ Override: Requires DS + MLOps approval
```

**Automations Triggered:**
```
├─ Store approval gate configuration
├─ Generate approval workflow templates
├─ Configure GitHub PR requirements
├─ Generate CI/CD gates
└─ Set up approval tracking in audit logs
```

**Outputs:**
```json
{
  "require_code_review": true,
  "code_review_count": 2,
  "require_business_approval": true,
  "require_legal_review": true,
  "require_security_scan": true,
  "require_end_to_end_test": true,
  "testing_threshold_pct": 100,
  "approval_gates": [
    "code_review",
    "unit_tests",
    "integration_tests",
    "fairness_tests",
    "data_quality_validation",
    "security_scan",
    "end_to_end_test",
    "business_approval",
    "legal_approval"
  ]
}
```

### Step 1.8: Review & Submit

**App Shows Summary:**
```
SUMMARY OF YOUR CHOICES:
════════════════════════════════════════════════════════════

Model: customer_churn_prediction
├─ Owner: alice@acme.com
├─ Team: retention_team
└─ Business Goal: Reduce churn by 20%

Inference:
├─ Type: Batch (daily at 9 AM)
├─ Model Type: XGBoost
└─ Serving: Databricks Model Serving

Data:
├─ Source: feature_store.customer.training_data_v1
├─ Rows: 1,000,000
├─ Target: churn_flag
├─ Contains PII: Yes (customer_id, email)
└─ Quality Required Fields: age, lifetime_value

Governance:
├─ Fairness Testing: aif360 (age, gender)
├─ Fairness Threshold: 10% max disparity
├─ Quality Required Fields: age, lifetime_value
└─ Can Accept Issues In: None

Deployment:
├─ Retraining: Hybrid (daily at 2 AM + on 5% drift)
├─ Rollback: Auto-rollback if >10 errors in 5 min
├─ Canary: 10% traffic rollout
└─ Shadow Mode: 7 days before full traffic

Monitoring:
├─ Data Drift: Yes (KS > 0.1)
├─ Performance Drift: Yes (>5% drop)
├─ Endpoint Uptime: Yes
└─ Alerts: Email + Slack

Requirements:
├─ Code Review: 2 reviewers required
├─ Test Coverage: 100% minimum
├─ Fairness Tests: Must pass
├─ Legal Review: Required
├─ Business Approval: Required
└─ End-to-End Test: Required in staging

════════════════════════════════════════════════════════════

IMPLICATIONS:
✓ Will require legal approval before production
✓ All unit & integration tests must pass
✓ Cannot skip fairness testing
✓ Will need 7-day staging soak time
✓ Automatic retraining enabled (hybrid)
✓ Automatic rollback on errors (10 error threshold)

APPROVE & CREATE?
[✓ Create Model] [← Go Back]
```

**DS Confirms & Submits:**
```
- DS reviews summary
- DS clicks "Create Model"
- App validates all required fields
- App shows "Creating your model infrastructure..."
```

### Step 1.9: Auto-Generation (Backend)

**Automations Executed:**

```
1. CREATE PROJECT METADATA
   ├─ Generate project_id (UUID)
   ├─ Create entry in mlops.projects table
   ├─ Store all interview responses as JSON
   ├─ Set initial status: "created"
   └─ Log in audit trail

2. CREATE GITHUB REPOSITORY
   ├─ Create GitHub repo: acme-mlops/{model_name}
   ├─ Initialize with opinionated template structure:
   │  ├─ .github/workflows/ (CI/CD pipelines)
   │  ├─ src/ (training, preprocessing, inference code)
   │  ├─ tests/ (unit, integration, model validation)
   │  ├─ notebooks/ (EDA, feature engineering skeletons)
   │  ├─ docs/ (model card, architecture, runbook)
   │  ├─ monitoring/ (dashboard configs, alert configs)
   │  ├─ requirements.txt (empty, DS fills in)
   │  ├─ pyproject.toml (linting, type checking config)
   │  ├─ README.md (auto-generated from interview)
   │  ├─ .gitignore (Python standard)
   │  ├─ CONTRIBUTING.md (team guidelines)
   │  ├── .pre-commit-config.yaml (linting, formatting hooks)
   │  └─ CODEOWNERS (set based on team/owner)
   │
   ├─ Add GitHub branch protection on main
   ├─ Require 2 code reviewers (configurable)
   ├─ Require status checks to pass before merge
   ├─ Dismiss stale reviews on new commits
   ├─ Require admin review before merge (if applicable)
   └─ Grant team members access

3. GENERATE SKELETON CODE
   ├─ src/train.py
   │  ├─ MLflow integration boilerplate
   │  ├─ Data loading & validation skeleton
   │  ├─ Feature engineering template (based on data analysis)
   │  ├─ Model training skeleton (based on model_type)
   │  ├─ Model evaluation & fairness testing
   │  ├─ Model registration to MLflow
   │  └─ TODO comments for DS to fill in
   │
   ├─ src/preprocess.py
   │  ├─ Data validation functions (based on table contract)
   │  ├─ Quality assessment functions
   │  ├─ PII handling (if applicable)
   │  ├─ Feature engineering stub
   │  └─ TODO comments
   │
   ├─ src/evaluate.py
   │  ├─ Model evaluation metrics
   │  ├─ Fairness test implementation (using configured framework)
   │  ├─ Regression testing vs baseline
   │  ├─ Performance reporting
   │  └─ TODO comments
   │
   ├─ src/inference.py
   │  ├─ Model serving boilerplate (for Model Serving)
   │  ├─ Input validation
   │  ├─ Prediction logic
   │  └─ Response formatting
   │
   ├─ src/config.py
   │  ├─ All interview responses as Python constants
   │  ├─ Model hyperparameters (placeholders)
   │  ├─ Data quality thresholds
   │  ├─ Fairness test thresholds
   │  ├─ Alert thresholds
   │  └─ Retraining/rollback config
   │
   └─ src/utils.py
      ├─ Helper functions
      ├─ Logging setup
      ├─ Notification helpers
      └─ Utility stubs

4. GENERATE TEST SKELETONS
   ├─ tests/unit/
   │  ├─ test_preprocess.py
   │  │  ├─ test_null_values()
   │  │  ├─ test_range_validation()
   │  │  ├─ test_uniqueness_check()
   │  │  └─ TODO stubs based on table contract
   │  │
   │  └─ test_evaluate.py
   │     ├─ test_accuracy_threshold()
   │     ├─ test_fairness_tests()
   │     └─ TODO stubs
   │
   ├─ tests/integration/
   │  └─ test_pipeline.py
   │     ├─ test_end_to_end_training()
   │     ├─ test_data_to_model()
   │     └─ TODO stubs
   │
   └─ tests/model/
      ├─ test_accuracy.py
      │  └─ test_accuracy_threshold_on_holdout()
      │
      ├─ test_fairness.py
      │  ├─ test_demographic_parity()
      │  ├─ test_equalized_odds()
      │  └─ test_calibration()
      │
      └─ test_regression.py
         └─ test_no_regression_vs_baseline()

5. GENERATE CI/CD PIPELINES
   ├─ .github/workflows/lint.yml
   │  ├─ pylint (score >= 8.0)
   │  ├─ black (formatting)
   │  ├─ isort (import sorting)
   │  ├─ mypy (type checking)
   │  ├─ pydocstyle (docstrings)
   │  └─ Check for unused variables
   │
   ├─ .github/workflows/security.yml
   │  └─ pip-audit (fail on critical vulns)
   │
   ├─ .github/workflows/test.yml
   │  ├─ pytest unit tests (100% coverage required or override)
   │  ├─ pytest integration tests
   │  └─ Upload to codecov
   │
   ├─ .github/workflows/model-validation.yml
   │  ├─ Train model on test data
   │  ├─ Validate accuracy threshold
   │  ├─ Fairness tests (aif360 or fairlearn)
   │  └─ Regression test vs baseline
   │
   ├─ .github/workflows/deploy-staging.yml
   │  ├─ Trigger on merge to main
   │  ├─ Register model to MLflow Staging
   │  ├─ Deploy to Model Serving (staging)
   │  ├─ Run end-to-end test in staging
   │  └─ Set model tag: "staging"
   │
   ├─ .github/workflows/deploy-prod.yml
   │  ├─ Manual trigger (approval required)
   │  ├─ Register model to MLflow Production
   │  ├─ Deploy to Model Serving (prod)
   │  ├─ Set model tag: "previous" (on old version)
   │  ├─ Set model tag: "current" (on new version)
   │  └─ Start monitoring
   │
   └─ .github/workflows/monitoring.yml
      ├─ Weekly pip-audit rescan
      └─ Weekly drift detection

6. GENERATE DOCUMENTATION
   ├─ README.md
   │  ├─ Model name & purpose
   │  ├─ Quick start guide
   │  ├─ Data requirements
   │  ├─ Model type & framework
   │  ├─ SLA definitions
   │  ├─ Links to docs
   │  └─ Contribution guidelines
   │
   ├─ docs/MODEL_CARD.md
   │  ├─ Model Overview
   │  │  ├─ Description
   │  │  ├─ Owner
   │  │  ├─ Created Date
   │  │  ├─ Last Updated
   │  │  └─ Version
   │  │
   │  ├─ Intended Use
   │  │  ├─ Primary Use Case
   │  │  ├─ Primary Users
   │  │  ├─ Out-of-scope use cases
   │  │  └─ Limitations
   │  │
   │  ├─ Factors
   │  │  ├─ Relevant Factors
   │  │  ├─ Evaluation Factors
   │  │  ├─ Fairness Evaluation
   │  │  └─ Performance Thresholds
   │  │
   │  ├─ Metrics
   │  │  ├─ Model Performance
   │  │  ├─ Fairness Metrics
   │  │  ├─ Data Quality Metrics
   │  │  └─ Monitoring Metrics
   │  │
   │  ├─ Data
   │  │  ├─ Training Data
   │  │  ├─ Evaluation Data
   │  │  ├─ Data Preprocessing
   │  │  ├─ Data Quality Assessment
   │  │  └─ Data Lineage
   │  │
   │  ├─ Explainability
   │  │  ├─ Feature Importance
   │  │  ├─ Decision Tree (if applicable)
   │  │  ├─ SHAP Values
   │  │  └─ Known Biases
   │  │
   │  └─ Caveats & Recommendations
   │     ├─ Recommended Use Practices
   │     ├─ Known Failure Cases
   │     ├─ Maintenance & Monitoring
   │     └─ Future Improvements
   │
   ├─ docs/ARCHITECTURE.md
   │  ├─ System Architecture Diagram
   │  ├─ Data Flow
   │  ├─ Model Pipeline
   │  ├─ Inference Process
   │  ├─ Infrastructure
   │  └─ Dependencies
   │
   ├─ docs/DATA_DICTIONARY.md
   │  ├─ Auto-generated from table contract
   │  ├─ Feature descriptions
   │  ├─ Data types
   │  ├─ Quality rules
   │  ├─ PII levels
   │  └─ Classifications
   │
   ├─ docs/RUNBOOK.md
   │  ├─ How to train locally
   │  ├─ How to train on Databricks
   │  ├─ How to deploy to staging
   │  ├─ How to deploy to production
   │  ├─ How to monitor
   │  ├─ How to debug issues
   │  └─ Emergency rollback procedures
   │
   └─ docs/GOVERNANCE.md
      ├─ Approval Workflows
      ├─ Roles & Permissions
      ├─ Data Access Controls
      ├─ Fairness & Compliance
      ├─ Audit Logging
      └─ Escalation Procedures

7. CREATE DATABRICKS INFRASTRUCTURE
   ├─ Create UC schemas
   │  ├─ {team}.{model_name}_dev
   │  ├─ {team}.{model_name}_staging
   │  └─ {team}.{model_name}_prod
   │
   ├─ Create feature store tables (if applicable)
   │  ├─ Detect features from training data
   │  ├─ Create feature store tables
   │  └─ Generate feature computation SQL
   │
   ├─ Create monitoring tables
   │  ├─ Create inference table
   │  ├─ Create drift detection table
   │  ├─ Create performance table
   │  └─ Create cost tracking table
   │
   └─ Create initial MLflow experiment
      └─ /Models/{model_name}

8. CREATE SERVICE ACCOUNTS & SECRETS
   ├─ Create service account: sa-{model_name}-{workspace}
   ├─ Create secret scope: mlops-{model_name}
   ├─ Create GitHub token secret (PAT for repo commits)
   ├─ Create Databricks API token (for training jobs)
   ├─ Create rotation schedule entry in audit logs
   └─ Configure secret rotation (default: 365 days)

9. CREATE PROJECT RECORD IN STATE
   ├─ Insert into mlops.projects table:
   │  ├─ project_id
   │  ├─ project_name
   │  ├─ owner_email
   │  ├─ team_name
   │  ├─ created_timestamp
   │  ├─ github_repo_url
   │  ├─ configuration (JSON)
   │  ├─ status: "project_created"
   │  └─ deployment_pattern
   │
   └─ Log creation in audit trail

10. SEND NOTIFICATIONS
    ├─ Email to DS:
    │  ├─ "Project created successfully!"
    │  ├─ GitHub repo URL
    │  ├─ Next steps (clone repo, implement train.py)
    │  ├─ Link to documentation
    │  └─ Link to model dashboard
    │
    ├─ Email to team lead:
    │  ├─ "New model project created"
    │  ├─ Model name & owner
    │  ├─ Approval gates configured
    │  └─ Next: Review when model is ready for staging
    │
    └─ Slack (if configured):
       └─ @{team} New model: {model_name} by {owner}

11. CREATE MONITORING DASHBOARD
    ├─ Create Databricks dashboard
    ├─ Add tiles for:
    │  ├─ Model status (development, staging, production)
    │  ├─ Data quality score
    │  ├─ Model performance (placeholder)
    │  ├─ Fairness metrics (placeholder)
    │  ├─ Inference volume (placeholder)
    │  ├─ Cost tracking
    │  └─ Approval status
    │
    └─ Make accessible to team
```

### Outputs of Phase 1

```json
{
  "project_id": "proj_abc123def456",
  "project_name": "customer_churn_prediction",
  "status": "project_created",
  "github_repo_url": "https://github.com/acme-mlops/customer_churn_prediction",
  "github_repo_name": "customer_churn_prediction",
  "infrastructure_created": {
    "uc_schemas": [
      "retention_team.customer_churn_prediction_dev",
      "retention_team.customer_churn_prediction_staging",
      "retention_team.customer_churn_prediction_prod"
    ],
    "service_account": "sa-customer_churn_prediction-{workspace}",
    "secret_scope": "mlops-customer_churn_prediction",
    "mlflow_experiment": "/Models/customer_churn_prediction",
    "monitoring_dashboard": "customer_churn_prediction_monitoring"
  },
  "interview_responses": { ... },
  "table_contract": { ... },
  "approval_gates": [
    "code_review",
    "unit_tests",
    "integration_tests",
    "fairness_tests",
    "data_quality_validation",
    "security_scan",
    "end_to_end_test",
    "business_approval",
    "legal_approval"
  ],
  "created_timestamp": "2024-01-15T10:30:00Z",
  "created_by": "alice@acme.com"
}
```

---

## Phase 2: Development & Experimentation

**Timeline**: 2-8 weeks (iterative)
**Actors**: Data Scientist (primary), ML Engineer (optional), MLOps (oversight)
**Approval Required**: None (DS has full autonomy)

### Entry Criteria
- Project has been created (Phase 1 complete)
- GitHub repo cloned locally
- Training data accessible
- Development environment ready

### Process Flow

```
START (DS Clones Repo & Begins Development)
    ↓
STEP 1: Local Development
├─ DS implements train.py, preprocess.py, evaluate.py
├─ DS implements fairness tests
├─ DS adds unit tests
├─ DS fills in requirements.txt
└─ DS tests locally

STEP 2: Commit to Feature Branch
├─ Create feature branch: git checkout -b feature/{feature_name}
├─ Pre-commit hooks run:
│  ├─ black (formatting) - auto-fixes
│  ├─ isort (import sorting) - auto-fixes
│  ├─ pylint (linting, score >= 8.0) - must pass
│  ├─ mypy (type checking) - must pass
│  ├─ pydocstyle (docstrings) - must pass
│  └─ pip-audit (no critical vulns) - must pass
│
└─ If all pass: git push

STEP 3: Create Pull Request (GitHub)
├─ DS creates PR against main
├─ CI/CD automatically triggered:
│  ├─ GitHub Actions: lint.yml
│  │  └─ All checks re-run (pylint, black, isort, mypy, pydocstyle)
│  │
│  ├─ GitHub Actions: security.yml
│  │  └─ pip-audit scan
│  │
│  ├─ GitHub Actions: test.yml
│  │  ├─ pytest unit tests (fail if <100% coverage)
│  │  ├─ pytest integration tests
│  │  └─ Upload coverage to codecov
│  │
│  ├─ GitHub Actions: model-validation.yml
│  │  ├─ Train model on test data (against dev workspace)
│  │  ├─ Validate accuracy >= threshold
│  │  ├─ Fairness tests: must pass
│  │  ├─ Regression test vs baseline
│  │  └─ All metrics logged to PR
│  │
│  └─ GitHub PR Status Checks
│     ├─ lint-check: ✓ passed
│     ├─ security-check: ✓ passed
│     ├─ unit-tests: ✓ passed (100% coverage)
│     ├─ integration-tests: ✓ passed
│     └─ model-validation: ✓ passed
│
├─ PR Details Comment Posted:
│  │ **Model Validation Results**
│  │ - Accuracy: 0.87 (threshold: >=0.85) ✓
│  │ - AUC: 0.92 ✓
│  │ - Fairness (Demographic Parity): PASS ✓
│  │ - Fairness (Equalized Odds): PASS ✓
│  │ - Data Quality Score: 0.98 ✓
│  │ - Test Coverage: 100% ✓
│  │
│  └─ Ready for review!
│
└─ DS requests 2 code reviewers (REQUIRED)

STEP 4: Code Review
├─ Team members review PR
├─ Comments & suggestions
├─ DS responds & makes changes (if needed)
│  └─ Return to Step 2 for additional commits
│
├─ Once satisfied: Reviewers approve (2 required)
└─ All status checks still passing

STEP 5: Merge to Main
├─ DS merges PR (or reviewer merges)
├─ Merge triggers deploy-staging.yml:
│  ├─ Register model to MLflow Staging stage
│  ├─ Deploy to Model Serving (staging endpoint)
│  ├─ Set tag: "staging"
│  ├─ Run end-to-end test in staging
│  └─ Create inference table
│
└─ Model is now in Staging phase (see Phase 3)

STEP 6: Development Continues (if needed)
├─ DS creates new feature branch for next iteration
├─ Repeat Steps 1-5 as needed
└─ Each merge increments version (semantic versioning)
```

### What Happens Locally (Pre-commit Hooks)

```
$ git commit -m "Add fairness tests"

Running pre-commit hooks...

1. black (code formatting)
   └─ ✓ No changes needed

2. isort (import sorting)
   └─ ✓ Imports already sorted

3. pylint (linting)
   └─ ✓ src/: 8.5/10

4. mypy (type checking)
   └─ ✓ Success

5. pydocstyle (docstrings)
   └─ ✓ All functions documented

6. pip-audit (dependency security)
   └─ ✓ No vulnerabilities found

✓ All pre-commit checks passed!

$ git push origin feature/fairness-tests
```

### What Happens on GitHub (CI/CD)

```
[GitHub PR Created]
    ↓
Status Checks Started...
    ├─ lint / pylint              [running]
    ├─ lint / black               [running]
    ├─ lint / isort               [running]
    ├─ lint / mypy                [running]
    ├─ lint / pydocstyle          [running]
    ├─ security / pip-audit       [running]
    ├─ test / unit-tests          [running]
    ├─ test / integration-tests   [running]
    └─ model-validation / train   [running]

[After ~5-10 minutes]
    ├─ lint / pylint              ✓ passed (8.5/10)
    ├─ lint / black               ✓ passed
    ├─ lint / isort               ✓ passed
    ├─ lint / mypy                ✓ passed
    ├─ lint / pydocstyle          ✓ passed
    ├─ security / pip-audit       ✓ passed
    ├─ test / unit-tests          ✓ passed (100% coverage)
    ├─ test / integration-tests   ✓ passed
    └─ model-validation / train   ✓ passed
       ├─ Accuracy: 0.87
       ├─ AUC: 0.92
       ├─ Fairness Tests: PASS
       ├─ Data Quality: 0.98
       └─ Inference Time: 50ms

All checks passed! Ready for review.
```

### Automations in Phase 2

```
CONTINUOUS (while DS develops):
├─ Code quality checks (local & GitHub)
├─ Security scanning (dependencies)
├─ Test execution & coverage tracking
├─ Model validation (train & evaluate)
├─ Fairness test execution
└─ Artifact logging to MLflow (dev experiment)

ON PR CREATION:
├─ Run all CI/CD checks
├─ Generate model validation report
├─ Post results to PR
├─ Request code reviewers
└─ Lock PR (cannot merge until approved)

ON APPROVAL & MERGE:
├─ Register model to MLflow Staging
├─ Deploy to staging endpoint
├─ Run end-to-end test
├─ Create inference table
├─ Update model card
├─ Log deployment to audit trail
└─ Notify team
```

---

## Phase 3: Staging & Acceptance Testing

**Timeline**: 7-14 days minimum (soak time)
**Actors**: Data Scientist, ML Engineer, Business Stakeholder (approval), Legal (approval)
**Approval Required**: Business + Legal (for new models)

### Entry Criteria
- Model merged to main (Phase 2 complete)
- Model deployed to staging via CI/CD
- End-to-end test passed
- All tests & checks passing

### Process Flow

```
START (Model Deployed to Staging)
    ↓
[GitHub Actions: deploy-staging.yml]
├─ Register model to MLflow Staging
├─ Deploy model to Databricks Model Serving (staging)
├─ Run end-to-end inference test
├─ Create inference table: {team}.{model}_staging
├─ Set tag: "staging"
└─ Create notification

STEP 1: Shadow Mode (Optional, Default: Yes)
├─ IF shadow_mode == true:
│  ├─ Run new model alongside current (if exists)
│  ├─ Route 0% traffic to new model (shadow only)
│  ├─ Collect predictions for X days (default 7)
│  ├─ Compare to current model output
│  ├─ No impact on actual predictions
│  └─ Goal: Validate in "real-world" scenario
│
└─ ELSE: Skip to Step 2

STEP 2: Run Acceptance Tests
├─ DS runs manual tests (if defined)
├─ Validate model behavior
├─ Check predictions make sense
├─ Verify data quality in production
├─ Test edge cases & error handling
└─ Document results

STEP 3: Performance Validation
├─ Check accuracy on recent data
├─ Compare to baseline / current model
├─ Verify latency / throughput (for real-time)
├─ Check cost tracking (per inference)
└─ Document results

STEP 4: Fairness Validation
├─ Run fairness tests on production data
├─ Validate demographic parity
├─ Validate equalized odds
├─ Validate calibration
├─ Compare to baseline
├─ Document results (sent to legal)

STEP 5: Data Quality Validation
├─ Monitor inference data quality in production
├─ Verify quality_score is acceptable
├─ Check for data drift
├─ Validate no unexpected patterns
└─ Document results

STEP 6: Waiting Period (Soak Time)
├─ Default: 7 days (configurable)
├─ Purpose: Observe model in shadow mode
├─ Monitor for:
│  ├─ Data drift
│  ├─ Model instability
│  ├─ Unexpected patterns
│  ├─ System issues
│  └─ Model failures
│
├─ Daily automated monitoring:
│  ├─ Run drift detection
│  ├─ Compare shadow vs current predictions
│  ├─ Check for anomalies
│  ├─ Log results to dashboard
│  └─ Alert if threshold exceeded
│
└─ At end of soak period: Auto-advance to approval gates

STEP 7: Approval Gates
├─ Legal Review (REQUIRED if regulated)
│  ├─ Legal team notified
│  ├─ Opens approval UI in app
│  ├─ Sees:
│  │  ├─ Model card
│  │  ├─ Fairness test results
│  │  ├─ Data quality assessment
│  │  └─ Governance checklist
│  │
│  ├─ Options: [✓ Approve] [✗ Reject] [? Request Changes]
│  ├─ Must comment (why approved/rejected)
│  └─ Signature captured (user + timestamp + IP)
│
├─ Business Approval (REQUIRED)
│  ├─ Business stakeholder notified
│  ├─ Opens approval UI in app
│  ├─ Sees:
│  │  ├─ Model performance metrics
│  │  ├─ Comparison to baseline
│  │  ├─ Business impact projection
│  │  └─ Cost estimate
│  │
│  ├─ Options: [✓ Approve] [✗ Reject] [? Request Changes]
│  ├─ Must comment
│  └─ Signature captured
│
└─ Both approvals required to proceed

STEP 8: Decision Point
├─ IF both approvals received:
│  └─ Ready for Production Promotion (Phase 4)
│
├─ IF rejected or changes requested:
│  ├─ Notification sent to DS
│  ├─ Details of feedback provided
│  ├─ DS can:
│  │  ├─ Fix issues & resubmit (create new PR → Phase 2)
│  │  ├─ Request meeting with legal/business
│  │  └─ Override (requires MLOps approval)
│  │
│  └─ If override requested:
│     ├─ Create override request in app
│     ├─ Send to MLOps team
│     ├─ MLOps reviews & approves/rejects
│     ├─ If approved: proceed to production
│     ├─ All captured in audit trail
│     └─ Post-mortem required afterward

END STAGING (Ready for Production or Rejected)
```

### Approval Interface

```
┌──────────────────────────────────────────────────────┐
│          LEGAL REVIEW APPROVAL                       │
├──────────────────────────────────────────────────────┤
│                                                      │
│ Model: customer_churn_prediction                    │
│ Version: 1.2.3                                      │
│ Owner: alice@acme.com                               │
│ Team: retention_team                                │
│                                                      │
│ ── FAIRNESS ASSESSMENT ──                           │
│ Protected Attributes: age, gender                   │
│ Fairness Framework: aif360                          │
│                                                      │
│ ✓ Demographic Parity: PASS                          │
│   Age: 9.5% disparity (threshold: 10%) ✓            │
│   Gender: 8.2% disparity (threshold: 10%) ✓         │
│                                                      │
│ ✓ Equalized Odds: PASS                              │
│   Age TPR diff: 4.1% ✓                              │
│   Gender TPR diff: 3.8% ✓                           │
│                                                      │
│ ✓ Calibration: PASS                                 │
│   Overall calibration error: 0.03 ✓                 │
│                                                      │
│ ── DATA QUALITY ──                                  │
│ ✓ Quality Score: 0.98                               │
│ ✓ No concerning data drift detected                 │
│ ✓ All required fields passing quality tests         │
│                                                      │
│ ── GOVERNANCE CHECKLIST ──                          │
│ [✓] Model card complete                            │
│ [✓] Architecture documented                        │
│ [✓] Data lineage tracked                           │
│ [✓] Fairness tests passing                         │
│ [✓] Audit logging enabled                          │
│                                                      │
│ ── YOUR DECISION ──                                 │
│                                                      │
│ [ ] ✓ Approve                                      │
│ [ ] ✗ Reject                                       │
│ [ ] ? Request Changes                              │
│                                                      │
│ Comments (required):                                │
│ ┌──────────────────────────────────────────────┐   │
│ │ Fairness tests pass regulatory requirements. │   │
│ │ No discriminatory bias detected. Ready for   │   │
│ │ production from legal perspective.           │   │
│ └──────────────────────────────────────────────┘   │
│                                                      │
│              [Submit Approval]                      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Automations in Phase 3

```
ON ENTRY:
├─ Start shadow mode (if enabled)
├─ Create inference table in staging
├─ Deploy model to staging endpoint
├─ Run end-to-end test
└─ Notify team

DAILY (during soak period):
├─ Monitor data drift
├─ Compare shadow vs current predictions
├─ Check inference latency
├─ Verify no errors/crashes
├─ Update monitoring dashboard
└─ Alert if issues detected

ON SOAK COMPLETION:
├─ Calculate fairness metrics
├─ Calculate performance metrics
├─ Generate comparison report
├─ Send approval requests to legal & business
├─ Update app UI with approval interface

ON APPROVAL:
├─ Log approval in audit trail
├─ Capture approver signature
├─ Mark model as "approved for production"
├─ Proceed to Phase 4

ON REJECTION:
├─ Log rejection in audit trail
├─ Notify DS with feedback
├─ Mark model as "needs changes"
└─ Return to Phase 2 or allow override request
```

---

## Phase 4: Production Deployment

**Timeline**: Same day as approval
**Actors**: ML Engineer (deployment), Data Scientist (monitoring), MLOps (oversight)
**Approval Required**: Manual trigger (no additional approval needed if Phase 3 passed)

### Entry Criteria
- Model approved in staging (Phase 3 complete)
- All legal & business approvals received
- Soak time completed without issues
- Ready for live traffic

### Process Flow

```
START (DS/MLOps Ready to Deploy to Production)
    ↓
STEP 1: Pre-Deployment Checklist
├─ Confirm all approvals received
├─ Confirm soak period completed
├─ Confirm no critical issues in staging
├─ Confirm current model is stable
└─ Manual gate: MLOps clicks "Deploy to Production"

STEP 2: Deploy to Production
├─ GitHub Actions: deploy-prod.yml triggered
├─ Register model to MLflow Production stage
├─ Create production inference table
├─ Choose deployment strategy:
│  ├─ IF canary_percentage > 0:
│  │  └─ Canary deployment (next)
│  │
│  ├─ IF canary_percentage == 0:
│  │  └─ Direct deployment (skip to Step 4)
│  │
│  └─ IF blue_green:
│     └─ Blue-green deployment (alternative)

STEP 3: Canary Deployment (if configured)
├─ Route X% of traffic to new model
├─ Route (100-X)% to current model
├─ Monitor metrics closely:
│  ├─ Error rate
│  ├─ Latency
│  ├─ Prediction distribution
│  ├─ Model failures
│  └─ User-level metrics
│
├─ If metrics look good after 1-2 hours:
│  ├─ Gradually increase traffic
│  ├─ 10% → 25% → 50% → 100%
│  └─ Continue to Step 4
│
└─ If issues detected:
   ├─ Auto-rollback to previous version
   ├─ Alert MLOps immediately
   ├─ Log incident in app
   └─ Go to Step 5 (Rollback)

STEP 4: Full Traffic Migration
├─ Set new model tag: "current"
├─ Set old model tag: "previous"
├─ Update MLflow Production stage: current version
├─ Stop routing traffic to old model
├─ Archive old inference table (keep for X days)
└─ Model is now LIVE

STEP 5: Post-Deployment Monitoring
├─ Intensive monitoring (first 24 hours)
├─ Monitor:
│  ├─ Error rate (alert if >1%)
│  ├─ Latency (alert if >2x baseline)
│  ├─ Data drift (alert if >threshold)
│  ├─ Performance drift (alert if >5% drop)
│  ├─ Volume anomalies (alert if unusual)
│  └─ Endpoint uptime (alert if down)
│
├─ Automated alerts:
│  ├─ Critical: Page oncall
│  ├─ Warning: Email team
│  ├─ Info: Log to dashboard
│  └─ Escalation: If repeated alerts
│
└─ Standard monitoring (ongoing)
   ├─ Daily drift detection
   ├─ Weekly performance review
   ├─ Monthly fairness re-validation
   └─ Continuous cost tracking

END (Model in Production)
```

### Deployment Configuration Options

```
STRATEGY 1: Canary Deployment (RECOMMENDED)
├─ 0% → 10% → 25% → 50% → 100%
├─ Duration: 2-4 hours
├─ Monitoring: Intensive
├─ Rollback: Automatic on threshold
└─ Risk: Low

STRATEGY 2: Direct Deployment
├─ 0% → 100% immediately
├─ Duration: Minutes
├─ Monitoring: Intensive
├─ Rollback: Manual or on threshold
└─ Risk: Medium

STRATEGY 3: Blue-Green Deployment
├─ Deploy to separate endpoint (green)
├─ Test thoroughly (0% production traffic)
├─ Switch traffic (blue → green)
├─ Keep old endpoint running for quick rollback
└─ Risk: Low
```

### Rollback Triggers

```
AUTOMATIC ROLLBACK (triggered by system):
├─ Error rate > 10% in 5 minutes
├─ Latency > 5x baseline for >1 minute
├─ Model returning null predictions
├─ Endpoint completely down
└─ Manual trigger by MLOps

ON AUTOMATIC ROLLBACK:
├─ Immediately revert to previous version
├─ Stop new canary traffic
├─ Route all traffic to previous version
├─ Alert MLOps, Data Science, OnCall
├─ Create incident in app
├─ Log to audit trail
├─ Trigger post-mortem process
└─ Send detailed error report to team
```

### Automations in Phase 4

```
ON DEPLOYMENT:
├─ Register model to MLflow Production
├─ Update model tags (current/previous)
├─ Create production inference table
├─ Deploy to Model Serving endpoint
├─ Configure auto-scaling (if batch)
├─ Start intensive monitoring
└─ Send deployment notification

CONTINUOUS MONITORING:
├─ Error rate tracking (real-time)
├─ Latency tracking (real-time)
├─ Data drift detection (hourly)
├─ Performance monitoring (daily)
├─ Fairness monitoring (weekly)
├─ Cost tracking (real-time)
└─ Alert routing & escalation

ON ERRORS/ISSUES:
├─ Auto-rollback if thresholds exceeded
├─ Alert oncall/team immediately
├─ Create incident tracking
├─ Log detailed error info
└─ Begin investigation
```

---

## Phase 5: Production Monitoring & Operations

**Timeline**: Ongoing (days, months, years)
**Actors**: Data Scientist (primary), ML Engineer, MLOps
**Approval Required**: MLOps (for retraining, configuration changes)

### Entry Criteria
- Model deployed and live in production (Phase 4 complete)
- Monitoring active
- Alerts configured

### Process Flow

```
START (Model Running in Production)
    ↓
CONTINUOUS MONITORING
├─ Standard Alerts (always enabled):
│  ├─ Endpoint down (critical)
│  ├─ Error rate > 1% (critical)
│  ├─ Latency > 2x baseline (warning)
│  ├─ Data drift > threshold (warning)
│  ├─ Performance drift > 5% (warning)
│  └─ Volume anomaly (info)
│
├─ Custom Alerts (configured by DS):
│  ├─ True positive rate < threshold
│  ├─ False positive rate > threshold
│  ├─ Business metric targets
│  └─ Domain-specific KPIs
│
└─ Monitoring Dashboard
   ├─ Real-time metrics
   ├─ Historical trends
   ├─ Comparison to baseline
   ├─ Fairness metrics
   ├─ Cost tracking
   └─ Alert history

DECISION POINT 1: Issues Detected?
├─ IF errors/crashes:
│  └─ Go to Incident Response (below)
│
├─ IF data drift detected:
│  └─ Monitor closely, assess if retrain needed
│
├─ IF performance drift detected:
│  └─ Trigger retraining (see Retraining)
│
└─ IF all normal:
   └─ Continue monitoring

DECISION POINT 2: Retraining Trigger?
├─ Scheduled retraining (based on cron):
│  ├─ {schedule} automatically triggers retraining
│  └─ Go to Retraining (below)
│
├─ Drift-triggered retraining:
│  ├─ Performance drops > threshold → Auto retrain
│  ├─ Data drift > threshold → Auto retrain (if hybrid)
│  └─ Go to Retraining (below)
│
└─ Manual retraining (DS requested):
   ├─ DS clicks "Retrain Model" in app
   └─ Go to Retraining (below)

DECISION POINT 3: Model Obsolete?
├─ IF model_lifetime > retention_days:
│  └─ Archive model (Go to Archival)
│
└─ ELSE: Continue monitoring

END MONITORING (ongoing until archival)
```

### Sub-Process: Retraining

```
TRIGGER: Retraining Initiated (scheduled, drift, or manual)
    ↓
STEP 1: Preparation
├─ DS reviews: Is retrain needed?
│  ├─ Check data quality
│  ├─ Check recent performance
│  ├─ Check for distribution shifts
│  └─ Confirm it's not a false alarm
│
└─ DS can approve or cancel retrain

STEP 2: Gather Training Data
├─ Fetch recent production data
│  ├─ Default: Last 30 days (configurable)
│  ├─ Filter: Only recent predictions
│  ├─ Join: With ground truth labels (if available)
│  └─ Validate: Check data quality
│
├─ Create new data version:
│  ├─ data_version_id
│  ├─ Source tables & versions
│  ├─ Processing pipeline version
│  ├─ Quality assessment
│  └─ Row-level quality metadata
│
└─ Quality check:
   ├─ IF quality_score < acceptable:
   │  ├─ Flag warning to DS
   │  └─ DS can proceed (accepts risk) or cancel
   │
   └─ ELSE: Continue

STEP 3: Retrain Model
├─ Launch training job
│  ├─ Use same code as original training
│  ├─ Use same features & preprocessing
│  ├─ Use same hyperparameters (or DS overrides)
│  ├─ Use new training data
│  └─ Log all hyperparameters to MLflow
│
├─ Model training:
│  ├─ Train/validation split
│  ├─ Model training
│  ├─ Model evaluation
│  ├─ Fairness testing
│  ├─ Log metrics to MLflow
│  └─ Log artifacts (model, plots, etc.)
│
└─ Compare to current production model:
   ├─ Performance comparison
   ├─ Fairness comparison
   ├─ Data quality comparison
   └─ Determine if improvement

STEP 4: Decision Point
├─ IF new model is better:
│  ├─ Register to MLflow Staging
│  ├─ Deploy to staging endpoint
│  ├─ Run end-to-end test
│  ├─ Go through approval gates (Phase 3)
│  └─ Proceed to production promotion (Phase 4)
│
├─ IF new model is similar (within tolerance):
│  ├─ Option 1: Skip, keep current model
│  ├─ Option 2: Deploy anyway (for data refresh)
│  └─ Go to Phase 4 if deploying
│
└─ IF new model is worse:
   ├─ Log results
   ├─ Alert DS
   ├─ Do NOT deploy
   ├─ Investigate what went wrong
   └─ Attempt retrain with different hyperparams

END RETRAINING (model promoted or rejected)
```

### Sub-Process: Incident Response

```
TRIGGER: Critical Alert (error >10%, endpoint down, etc.)
    ↓
STEP 1: Detection & Alert
├─ Automated detection (system)
├─ Alert sent:
│  ├─ To oncall engineer
│  ├─ To data science team
│  ├─ To Slack #alerts channel
│  └─ Severity: CRITICAL
│
├─ Incident created in app:
│  ├─ incident_id
│  ├─ detected_timestamp
│  ├─ trigger_metric
│  ├─ threshold & actual value
│  └─ Status: "OPEN"
│
└─ Escalation: If not acknowledged in 5 min

STEP 2: Immediate Response
├─ MLOps/Engineer acknowledges incident
├─ Assesses severity:
│  ├─ CRITICAL: Immediate auto-rollback
│  ├─ HIGH: Manual rollback decision
│  └─ MEDIUM: Monitor & investigate
│
├─ Option 1: Auto-Rollback (if configured)
│  ├─ System automatically reverts to previous version
│  ├─ All traffic routed back to old model
│  ├─ New inference table archive
│  ├─ Alert team that rollback occurred
│  └─ Continue to Step 3
│
└─ Option 2: Manual Investigation
   ├─ Engineer investigates root cause
   ├─ Check logs, error rates, data quality
   ├─ Decide: Fix, Rollback, or Accept
   └─ Continue to Step 3

STEP 3: Root Cause Analysis
├─ What went wrong?
│  ├─ Model issue
│  ├─ Data issue
│  ├─ Infrastructure issue
│  ├─ Integration issue
│  └─ Other
│
├─ Gather data:
│  ├─ Error logs
│  ├─ Model metrics during incident
│  ├─ Inference data quality
│  ├─ Recent changes
│  └─ External factors
│
└─ Document in incident record

STEP 4: Remediation
├─ If data issue:
│  ├─ Fix data quality issue
│  ├─ Retrain model with clean data
│  └─ Deploy new version
│
├─ If model issue:
│  ├─ Investigate model logic
│  ├─ Revert recent changes
│  ├─ Retrain with different approach
│  └─ Deploy new version
│
├─ If infrastructure issue:
│  ├─ Fix infrastructure
│  ├─ Restart endpoint if needed
│  ├─ Monitor for stability
│  └─ Continue if stable
│
└─ If nothing wrong found:
   └─ Return to production, monitor closely

STEP 5: Post-Incident
├─ Close incident when stable
├─ Schedule post-mortem (within 24 hours)
├─ Post-mortem includes:
│  ├─ What happened
│  ├─ Why it happened
│  ├─ How we'll prevent it
│  ├─ Action items with owners
│  └─ Lessons learned
│
├─ Update monitoring/alerts if needed
├─ Implement preventive measures
├─ Log all actions to audit trail
└─ Review in team standup

END INCIDENT RESPONSE
```

### Automations in Phase 5

```
CONTINUOUS:
├─ Standard monitoring (endpoint, error rate, latency)
├─ Data drift detection (hourly)
├─ Performance monitoring (daily)
├─ Fairness monitoring (weekly)
├─ Cost tracking (real-time)
├─ Alert routing & escalation
└─ Dashboard updates

SCHEDULED (based on configuration):
├─ Retraining (if scheduled strategy)
├─ Security scanning (weekly pip-audit)
├─ Data quality checks
├─ Fairness re-validation
├─ Model performance reports
└─ Cost reports

ON DRIFT DETECTION:
├─ IF on_drift strategy AND drift > threshold:
│  ├─ Trigger retraining
│  ├─ Alert DS
│  └─ Begin retraining process
│
└─ Otherwise: Log & monitor

ON ALERTS:
├─ Route based on severity
├─ Send to configured channels (email, Slack)
├─ Create incident record
├─ Escalate if not acknowledged
└─ Log all alerts to audit trail
```

---

## Phase 6: Model Archival & Retirement

**Timeline**: When retention period expires
**Actors**: MLOps, Data Scientist (optional)
**Approval Required**: MLOps approval required to delete

### Entry Criteria
- Model past retention date (default 365 days in prod)
- Model being replaced by newer version
- Model no longer used in production

### Process Flow

```
START (Model Nearing Retirement)
    ↓
STEP 1: Deprecation Notice
├─ 30 days before archival:
│  ├─ Send notice to owner
│  ├─ "Model will be archived on {date}"
│  ├─ "All production traffic must migrate"
│  └─ "Review retention policy"
│
└─ Options:
   ├─ Continue model (extend retention)
   ├─ Prepare replacement model
   └─ Let it retire

STEP 2: Archive Preparation
├─ No new traffic routed to model
├─ Run final health check
├─ Export final metrics & performance
├─ Document any lessons learned
├─ Capture final state
└─ Remove from monitoring (optional alerts only)

STEP 3: Move to Archive
├─ Move model from prod to archive stage (MLflow)
├─ Copy model artifacts to archive storage
├─ Archive inference table
├─ Archive monitoring data
├─ Archive cost tracking data
└─ Create final snapshot

STEP 4: Audit Retention
├─ Keep all audit logs (7 years minimum)
├─ Keep model card & documentation
├─ Keep training data version info
├─ Keep approval chain
├─ Keep change history
└─ Make searchable/queryable

STEP 5: Deletion Decision (After Retention)
├─ IF compliance requires keep (7+ years):
│  ├─ Archive indefinitely
│  └─ Make immutable
│
├─ IF OK to delete:
│  ├─ Create deletion request in app
│  ├─ Requires MLOps approval
│  ├─ MLOps reviews & confirms
│  ├─ MLOps approves/rejects
│  └─ If approved: proceed to Step 6
│
└─ IF uncertain:
   └─ Extend archive (another year)

STEP 6: Final Deletion
├─ Delete model artifacts (from artifact store)
├─ Delete inference tables (after grace period)
├─ Delete training data (if not needed by other models)
├─ Keep audit logs (immutable)
├─ Keep documentation (immutable)
├─ Keep approval records (immutable)
└─ Mark model as "deleted" in state

END (Model Retired & Archived)
```

### Automations in Phase 6

```
30 DAYS BEFORE RETENTION:
├─ Send deprecation notice to owner
├─ Update monitoring dashboard
└─ Create archival task

ON ARCHIVAL:
├─ Move to archive MLflow stage
├─ Export final metrics
├─ Create snapshot of model & data
├─ Archive monitoring data
└─ Log archival to audit trail

ON DELETION (after approval):
├─ Delete model artifacts
├─ Delete inference tables
├─ Keep audit logs (immutable)
├─ Mark as deleted in state
└─ Log deletion to audit trail
```

---

## Cross-Cutting Concerns

### Approval Workflow (All Phases)

```
APPROVAL PATTERN:
├─ Stage Transition: Automatic if all gates pass
│  └─ dev → staging: Auto if tests pass
│  └─ staging → prod: Requires manual + legal + business
│
├─ Override Request (when approval denied):
│  1. DS creates override request in app
│  2. Specifies:
│     ├─ Reason for override
│     ├─ Risk assessment
│     ├─ Mitigation plan
│     └─ Approval request
│
│  3. Sent to MLOps team
│  4. MLOps reviews & decides:
│     ├─ Approve: Proceed with override
│     ├─ Reject: Request changes
│     └─ Request more info
│
│  5. If approved:
│     ├─ Proceed to next stage
│     ├─ Log override in audit trail
│     ├─ Flag for post-mortem
│     └─ Create action item for root cause
│
└─ All approvals capture:
   ├─ Approver name & email
   ├─ Timestamp
   ├─ IP address / location
   ├─ Comments
   └─ Approval reason
```

### Audit Logging (All Phases)

```
CAPTURED FOR EVERY ACTION:
├─ Who: User email & role
├─ What: Action type & details
├─ When: Timestamp (ISO 8601)
├─ Where: System/workspace
├─ Why: Comments, approval reason
├─ Result: Success/failure, error messages
└─ Impact: What changed

STORED IN:
├─ mlops.audit_logs (main storage)
├─ Immutable after creation
├─ Queryable by app
└─ 7-year retention (regulated industries)

SEARCHABLE BY:
├─ Model name
├─ User email
├─ Action type
├─ Date range
├─ Project/team
└─ Status (approved, rejected, overridden)
```

### Communication & Notifications (All Phases)

```
NOTIFICATION CHANNELS:
├─ Email (default, always on)
├─ Slack (if configured)
└─ In-app notifications (dashboard)

TRIGGERS FOR NOTIFICATIONS:
├─ Project created (to DS, team lead)
├─ PR ready for review (to code reviewers)
├─ PR approved (to DS)
├─ PR merged (to team, ops)
├─ Model deployed to staging (to team)
├─ Approval needed (to approvers)
├─ Approval received (to DS)
├─ Model deployed to prod (to team)
├─ Alert triggered (to team, escalation)
├─ Incident created (to oncall)
├─ Rollback occurred (to team, ops)
└─ Model archived (to DS, team lead)

NOTIFICATION CONTENT:
├─ What happened
├─ When it happened
├─ Who did it
├─ What action is needed
├─ Link to app for details
└─ Escalation if needed
```

---

## Timeline Summary

```
PHASE           DURATION        KEY GATES                ACTORS
─────────────────────────────────────────────────────────────────
0: Setup        1 day           Enterprise archi        MLOps
                               Security approval

1: Init         30 min          None (auto approval)    DS

2: Dev          2-8 weeks       Unit tests, linting,    DS,
                               fairness tests,         Reviewers,
                               code review             MLOps

3: Staging      7-14 days       Soak time,              DS,
                               legal approval,         Legal,
                               business approval       Business

4: Deploy       Same day        Manual approval         MLOps,
                                                       DS

5: Monitor      Days-years      Alert thresholds,       DS,
                               retraining gates,       MLOps,
                               incident response       Oncall

6: Archive      Post-retention  MLOps approval          MLOps,
                               to delete               DS (optional)
─────────────────────────────────────────────────────────────────

Total: ~3-4 weeks from interview to production (minimum)
       ~2-8 weeks from start of development to production
```

---

## Decision Trees

### Deployment Strategy Decision

```
START
  ↓
Has canary_percentage > 0?
  ├─ YES → Canary deployment (phased rollout)
  │         ├─ Monitor closely
  │         ├─ Auto-rollback if issues
  │         └─ Gradually increase traffic
  │
  └─ NO → Direct deployment (100% immediately)
           ├─ Monitor closely
           ├─ Manual rollback if needed
           └─ Full traffic shift
```

### Retraining Strategy Decision

```
START
  ↓
Retraining strategy configured?
  ├─ MANUAL
  │  └─ Only retrain if DS manually triggers
  │
  ├─ SCHEDULED
  │  └─ Retrain on cron schedule (e.g., daily)
  │
  ├─ ON_DRIFT
  │  └─ Retrain if drift > threshold
  │
  └─ HYBRID
     ├─ Retrain on schedule OR
     └─ Retrain if drift > threshold
```

### Approval Gate Decision

```
START
  ↓
Model going to production?
  ├─ YES, NEW model
  │  └─ Requires:
  │     ├─ Code review (2 reviewers)
  │     ├─ Fairness/Legal review
  │     ├─ Business approval
  │     ├─ All tests passing (100% coverage)
  │     ├─ End-to-end test in staging (7 days)
  │     └─ Manual deployment approval
  │
  └─ YES, UPDATE to existing model
     └─ Requires:
        ├─ Code review (1 reviewer, optional 2nd)
        ├─ Legal review (if fairness config changed)
        ├─ All tests passing
        ├─ No end-to-end test if same codebase
        └─ MLOps approval to deploy
```

---

## Error Handling & Recovery

### Training Job Fails

```
TRIGGER: Training job error
  ↓
RESPONSE:
├─ Automatic retry (3x, exponential backoff)
├─ Clean up partial artifacts
├─ Alert DS with error message
├─ Log to audit trail
└─ Options:
   ├─ Fix issue & retrain
   ├─ Adjust hyperparameters
   └─ Investigate data quality
```

### Model Crashes in Production

```
TRIGGER: Error rate > 10% in 5 minutes
  ↓
RESPONSE:
├─ IMMEDIATE: Auto-rollback to previous version
├─ IMMEDIATE: Alert oncall & team (critical)
├─ Create incident in app
├─ Route all traffic to previous version
├─ Begin incident investigation
└─ Schedule post-mortem within 24 hours
```

### Data Quality Degradation

```
TRIGGER: Data quality_score < 0.5
  ↓
RESPONSE (if training):
├─ Flag warning to DS
├─ DS can proceed (accepts risk) or cancel
├─ If proceed: log decision in audit trail

RESPONSE (if inference):
├─ Alert monitoring dashboard
├─ Flag low quality predictions
├─ Alert DS team
├─ Consider pausing inference (depending on config)
└─ Investigate source of degradation
```

---

## Summary: Complete Process Map

The process map defines:

1. **Phase 0: Installation** - One-time setup of infrastructure, personas, config
2. **Phase 1: Initialization** - DS answers interview questions, infra auto-generated
3. **Phase 2: Development** - DS develops code, CI/CD validates, code review
4. **Phase 3: Staging** - Shadow mode, acceptance testing, approval gates (legal + business)
5. **Phase 4: Deployment** - Production deployment with canary/direct options
6. **Phase 5: Monitoring** - Continuous monitoring, retraining, incident response
7. **Phase 6: Archival** - Retirement and deletion with full audit retention

Each phase has:
- **Entry criteria**: What must be true to start
- **Process steps**: Detailed flow with decisions
- **Required approvals**: Who must sign off
- **Automations**: What happens automatically
- **Outputs**: What's created/updated
- **Error handling**: What if something fails

All actions are logged in audit trail, captured with user signatures, and tied to compliance frameworks.
