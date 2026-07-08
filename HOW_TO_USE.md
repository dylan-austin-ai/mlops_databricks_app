# Databricks MLOps App: Complete How-To Guide

A step-by-step walkthrough for setting up and using the MLOps platform on Databricks, from initial deployment through creating and monitoring your first model.

**Table of Contents**
1. [Prerequisites](#prerequisites)
2. [Part 1: Local Setup & Databricks Connection](#part-1-local-setup--databricks-connection)
3. [Part 2: Initial Configuration](#part-2-initial-configuration)
4. [Part 3: Creating Your First Project (End-to-End Demo)](#part-3-creating-your-first-project-end-to-end-demo)
5. [Part 4: Platform Features & Workflows](#part-4-platform-features--workflows)
6. [Part 5: Monitoring, Approvals & Governance](#part-5-monitoring-approvals--governance)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before you start, ensure you have:

### Required
- **Databricks Workspace** with admin access
- **SQL Warehouse** (any size; used for DDL and state queries)
- **Databricks PAT Token** (Personal Access Token from User Settings)
- **Python 3.10+** installed locally
- **Git** installed and configured

### Nice to Have
- GitHub account & organization (for auto-generated repos)
- Slack workspace (for alerts)

---

## Part 1: Local Setup & Databricks Connection

### Step 1.1: Clone or Extract the App

```bash
cd /path/to/your/workspace
# If you have the app already, navigate to it:
cd mlops_databricks_app
```

### Step 1.2: Create a Virtual Environment

```bash
# Create and activate venv
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip setuptools
```

### Step 1.3: Install Dependencies

```bash
pip install -r requirements.txt
```

**Expected output:** ~30 packages installed (streamlit, databricks-sdk, mlflow, pandas, etc.)

### Step 1.4: Set Up Your `.env` File

**Copy the example:**
```bash
cp .env.example .env
```

**Edit `.env` with your Databricks credentials:**
```bash
# Your Databricks workspace URL (no trailing slash)
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net

# Personal access token from Databricks User Settings > Developer Tools
DATABRICKS_TOKEN=dapi1234567890abcdef

# SQL warehouse ID (from Databricks UI > SQL > Warehouses)
DATABRICKS_WAREHOUSE_ID=abc123def456789

# (Optional) Unity Catalog settings
MLOPS_CATALOG=mlops              # Will be created if it doesn't exist
MLOPS_SCHEMA=mlops               # Schema within the catalog

# (Optional) GitHub for auto-repo creation
GITHUB_TOKEN=ghp_1234567890abcdef
GITHUB_ORG=my-org

# (Optional) LLM endpoint for AI-powered suggestions
DATABRICKS_LLM_ENDPOINT=databricks-meta-llama-3-1-70b-instruct
```

**Finding your Databricks credentials:**
- **Host:** Top-right corner of Databricks UI → workspace name → copy workspace URL
- **Token:** User Settings (profile icon) → Developer Tools → Generate new token
- **Warehouse ID:** SQL → Warehouses → click any warehouse → copy ID from URL

### Step 1.5: Initialize the Database Schema

This creates all necessary tables in your Databricks workspace.

```bash
python -m db.setup
```

**Expected output:**
```
Catalog 'mlops' ready.
Schema 'mlops.mlops' ready.
Creating 23 tables in mlops.mlops ...
  [1/23] OK — mlops.mlops.projects
  [2/23] OK — mlops.mlops.project_configurations
  ...
  [23/23] OK — mlops.mlops.installation_config
Schema setup complete.
```

### Step 1.6: Launch the App

```bash
streamlit run app.py
```

**Expected output:**
```
Uvicorn server started on :::8501

You can now view your Streamlit app in your browser.

Local URL: http://localhost:8501
Network URL: http://192.168.x.x:8501
External URL: http://your.external.ip:8501
```

**Open your browser:** Visit `http://localhost:8501`

You should see the **MLOps Platform "Command Center"** with:
- Project metrics (Total Projects: 0, In Production: 0, In Development: 0)
- A message: "No projects yet. Create your first project."

---

## Part 2: Initial Configuration

### Step 2.1: Settings Page (Optional but Recommended)

Navigate to **Settings** (page 5 in the sidebar).

This is where you configure:
- **Organization Info** — Name, industry, compliance frameworks
- **Deployment Pattern** — Single workspace vs. multi-workspace setup
- **Team & Roles** — Define data scientists, ML engineers, approvers, etc.
- **Monitoring Defaults** — Drift detection, alerting thresholds
- **Approval Workflows** — How many reviewers for different stages
- **Cost Tracking** — Enable budget alerts and cost center tagging

**For a demo/test setup:**
- Organization: "Demo MLOps"
- Industry: "Technology"
- Deployment: "Single Workspace"
- Teams: Leave defaults or add yourself to all roles

---

## Part 3: Creating Your First Project (End-to-End Demo)

This section walks through creating a **credit risk prediction model** from start to finish.

### Step 3.1: Navigate to "New Project"

Click **➕ New Project** in the sidebar (or visit `/02_new_project`).

You'll see a **7-step interview wizard**:

```
┌─────────────────────────────────────────┐
│ Step 1/7: Basic Info                    │
│ Step 2/7: Model Specs                   │
│ Step 3/7: Data Specs                    │
│ Step 4/7: Governance                    │
│ Step 5/7: Deployment                    │
│ Step 6/7: Monitoring                    │
│ Step 7/7: Approval Gates                │
│ Review & Create                         │
└─────────────────────────────────────────┘
```

### Step 3.2: Complete Step 1 — Basic Info

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Project Name** | `credit_risk_v1` | Slug-style name (no spaces) |
| **Problem Statement** | `Predict credit default risk for loan applications` | Plain English description |
| **Success Metric** | `AUC > 0.85 on holdout test set` | How you'll measure success |
| **Team Name** | `Data Science` | Which team owns this project |
| **Owner Email** | `your-email@company.com` | Primary point of contact |
| **Use Case Category** | `Classification` | Regression, Classification, Ranking, Forecasting |
| **Priority** | `High` | High, Medium, Low |

**Click "Next" to continue.**

### Step 3.3: Complete Step 2 — Model Specs

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Inference Type** | `Real-time API` | Batch, Real-time API, Streaming |
| **Target Latency** | `100ms` | How fast predictions need to be |
| **Queries Per Second (QPS)** | `50` | Expected throughput |
| **Model Framework(s)** | `XGBoost` | XGBoost, LightGBM, Random Forest, Neural Net, etc. |
| **Primary Framework** | `XGBoost` | Which framework to start with |
| **Retraining Frequency** | `Monthly` | How often to retrain (Hourly/Daily/Weekly/Monthly/Quarterly/Manual) |
| **Max Model Age** | `60 days` | If model is older than this, alert |

**Click "Next" to continue.**

### Step 3.4: Complete Step 3 — Data Specs

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Input Data Location** | `catalog.schema.raw_loan_applications` | Path to your training data table |
| **Target Column** | `is_default` | Name of your label column |
| **Feature List** | `credit_score, loan_amount, term, debt_to_income, age, employment_length` | Comma-separated feature names |
| **PII Columns** | `social_security, phone_number, address` | Any personally identifiable info to handle carefully |
| **Data Classification** | `Sensitive` | Public, Internal, Sensitive, Restricted |
| **Train/Validation/Test Split** | `60/20/20` | Percentage split for each set |
| **Min Data Freshness** | `1 day` | How fresh data must be for training |

**Click "Next" to continue.**

### Step 3.5: Complete Step 4 — Governance

This is where fairness & bias protections are configured.

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Enable Fairness Testing** | `Enabled` | Always on — detects bias in predictions |
| **Protected Attributes** | `age, race, gender` | Which demographic variables to monitor |
| **Fairness Metric** | `Demographic Parity` | How to measure fairness (Equal Opportunity, Demographic Parity, Calibration, etc.) |
| **Fairness Threshold** | `0.1` | Max allowed disparity (0–1, where 0 = identical) |
| **Quality Gates** | `Precision >= 0.75, Recall >= 0.70` | Hard stop conditions before deployment |

**Click "Next" to continue.**

### Step 3.6: Complete Step 5 — Deployment

Configure how your model moves from dev → staging → production.

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Dev Environment** | `dev-compute` | Cluster for experimentation |
| **Staging Environment** | `staging-compute` | Cluster for pre-prod validation |
| **Retraining Frequency** | `Monthly` | Automate retraining schedule |
| **Retraining Drift Trigger** | `Data drift > 0.2` | Auto-retrain if drift detected |
| **Rollback Trigger** | `Prediction latency > 500ms, Fairness metric decline > 5%` | When to auto-rollback to previous version |
| **Canary Rollout %** | `10` | Start with 10% of traffic |
| **Canary Duration** | `7 days` | Monitor canary for 1 week before full rollout |

**Click "Next" to continue.**

### Step 3.7: Complete Step 6 — Monitoring

Set up alerts for model health.

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Performance Metric** | `AUC` | Metric to track (AUC, Accuracy, Precision, Recall, F1, Custom) |
| **Performance Threshold** | `AUC < 0.80` | Alert if model performance drops below this |
| **Data Drift Detection** | `Enabled` | Monitor for distribution shift in input features |
| **Drift Threshold** | `0.15` | Alert if drift > 15% |
| **Monitoring Frequency** | `Daily` | How often to check metrics |
| **Alert Destination** | `Slack` | Where to send alerts (Slack, Email, Both) |
| **Slack Channel** | `#ml-alerts` | Which channel to notify |
| **Alert Recipients (Email)** | `your-email@company.com, team@company.com` | Email list for notifications |

**Click "Next" to continue.**

### Step 3.8: Complete Step 7 — Approval Gates

Define who needs to approve deployments.

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Dev → Staging Approvals** | `1 reviewer from ml_engineers` | Who reviews code/model before staging |
| **Staging → Prod Approvals** | `2 reviewers (1 ml_engineer, 1 business_stakeholder)` | Who approves production deployment |
| **Require Fairness Sign-Off** | `Yes` | Legal/compliance review required |
| **Require Governance Review** | `Yes` | Security/audit review required |
| **Auto-Approve After X Days** | `14` | If not rejected in 14 days, auto-approve (optional) |

**Click "Review & Create" to finish.**

### Step 3.9: Review & Create

You'll see a summary of all your answers. Review for accuracy.

**Click "Create Project"** to finalize.

**Expected output:**
```
✅ Project created: credit_risk_v1
   - Created repository on GitHub: acme-mlops/credit-risk-v1
   - Schema prepared: mlops_projects.credit_risk_v1
   - MLflow experiment: /Users/your-email/credit_risk_v1
   - Deployment workflow saved
```

---

## Part 4: Platform Features & Workflows

Once your project is created, you can interact with it across multiple pages.

### 4.1: Projects Page

**Path:** `01_projects.py` (default home after creating a project)

**What you see:**
- List of all projects
- Status for each (development, staging, production)
- Owner, team, creation date
- Quick actions: View Details, Edit, Archive

**Actions:**
- Click on a project to view its dashboard
- Use search to filter by name, team, or status
- Sort by status, priority, or last updated

### 4.2: Project Dashboard

**Path:** `06_project_dashboard.py`

**Shows (for your selected project):**
- **Metadata:** Team, owner, problem statement, success metric
- **Model Versions:** All trained models, current production version, staging version
- **Recent Experiments:** Training runs with parameters and metrics
- **Performance Metrics:** AUC, Accuracy, Fairness score over time
- **Data Drift:** Feature distribution changes
- **Cost Tracking:** Compute spend for training and inference
- **Incidents:** Performance drops, fairness violations, failed deployments

**Actions:**
- Promote a model from staging to production
- Trigger a manual retraining run
- View detailed experiment logs
- Download model artifacts

### 4.3: Data Contracts Page

**Path:** `07_data_contracts.py`

**Purpose:** Define and enforce data quality requirements.

**What you can do:**
- View input data schema and expected distributions
- Set data quality thresholds (null %, outliers %, column stats)
- Monitor compliance: which data loads meet the contract
- Auto-reject data that violates the contract

**Example:**
```
Data Contract: credit_risk_v1 input data
├── credit_score: int, range [300–850], null_rate <= 0.01
├── loan_amount: float, range [$500–$500k], null_rate <= 0.01
├── term: int, values in [12, 24, 36, 48], null_rate = 0
├── debt_to_income: float, range [0–1], null_rate <= 0.02
└── age: int, range [18–100], null_rate <= 0.05
```

### 4.4: Feature Catalog Page

**Path:** `08_feature_catalog.py`

**Purpose:** Discover, version, and govern features across your organization.

**What you can do:**
- View all available features (from all projects)
- See which projects use each feature
- Track feature versions and transformations
- Reuse features across projects to reduce redundancy

**Example:**
```
Feature: customer_credit_score
├── Owner: Data Science team
├── Latest Version: v2.1
├── Projects Using: [credit_risk_v1, churn_prediction, pricing_model]
├── Last Updated: 2024-01-15
├── Quality Score: 9.2/10
└── Documentation: "Customer's FICO credit score from Equifax"
```

### 4.5: HITL Review Page (Human-in-the-Loop)

**Path:** `09_hitl_review.py`

**Purpose:** Review and provide feedback on model predictions before they go live.

**What you can do:**
- View sampled predictions from staging models
- Flag incorrect or suspicious predictions
- Provide corrective feedback (is this prediction right?)
- Use feedback to improve models

**Workflow:**
```
1. Model is deployed to staging
2. HITL page samples 100 predictions
3. You review: "Is this credit decision fair? Correct?"
4. Flag ~5 suspicious cases
5. Feedback is logged and used to retrain
6. Model improves, then moves to production
```

### 4.6: Approvals Page

**Path:** `03_approvals.py`

**Purpose:** Centralized approval workflow for model promotions.

**What you see:**
- Pending approvals (models waiting for sign-off)
- Approval history (past decisions)
- Approval chains (who needs to sign off)

**Workflow:**
```
1. Data Scientist trains model, requests staging approval
2. ML Engineer reviews → clicks "Approve"
3. System requests Business Stakeholder sign-off
4. Business Stakeholder reviews performance → clicks "Approve"
5. Model auto-promotes to production
6. All approvals logged in audit trail
```

**Approval Gates (from your project config):**
- Dev → Staging: 1 ML Engineer
- Staging → Prod: 1 ML Engineer + 1 Business Stakeholder
- Fairness Review: Legal/Compliance (if regulated)
- Governance Review: Security/Audit

### 4.7: Monitoring & Alerts Page

**Path:** `04_monitoring.py`

**Purpose:** Real-time dashboards for model health.

**What you see:**
- **Performance Drift:** Is AUC declining? Precision dropping?
- **Data Drift:** Are input features changing?
- **Fairness Metrics:** Are demographic groups treated equally?
- **Infrastructure:** Model serving latency, throughput, errors
- **Cost:** How much are you spending to run this model?

**Alert Examples:**
```
🔴 CRITICAL — credit_risk_v1
   AUC dropped to 0.76 (threshold: 0.80)
   Action: Review staging model or retrain

🟡 WARNING — credit_risk_v1
   Data drift detected in `debt_to_income` (shift = 0.18)
   Action: Check recent loan portfolio changes; consider retraining

🟢 OK — credit_risk_v1
   Fairness: demographic parity maintained (gap < 0.05)
   Performance: AUC 0.86, Precision 0.82, Recall 0.79
```

### 4.8: Portfolio Analytics Page

**Path:** `10_portfolio_analytics.py`

**Purpose:** Organization-wide view of all models.

**What you see:**
- Total model count, by status (dev/staging/prod)
- Total compute spend (by team, by model, over time)
- Highest-risk models (fairness violations, performance drift)
- Most expensive models
- Models due for retraining

**Example Dashboard:**
```
Portfolio Summary
├── Total Models: 23
│   ├── Development: 8
│   ├── Staging: 4
│   └── Production: 11
├── Monthly Spend: $12,450
│   ├── Training: $5,200
│   ├── Serving: $4,100
│   └── Monitoring: $3,150
└── Risk Summary
    ├── High Risk (fairness): 2 models
    ├── Medium Risk (performance): 4 models
    └── Low Risk: 17 models
```

---

## Part 5: Monitoring, Approvals & Governance

### 5.1: Triggering a Training Run

Once your project is created, you can train models.

**From Project Dashboard:**
1. Click **Trigger Retraining**
2. Select parameters:
   - Data version (which snapshot of data to use)
   - Train/val/test split
   - Hyperparameters (XGBoost depth, learning rate, etc.)
3. Click **Start Training**

**Expected flow:**
```
Training Run: credit_risk_v1 #42
├── [In Progress] Fetching data from mlops_projects.credit_risk_v1.raw_data
├── [In Progress] Validating against data contract
├── [Queued] Building features
├── [Queued] Training XGBoost model
├── [Queued] Running fairness tests
├── [Queued] Performance validation
└── [Queued] Auto-promote to staging (if quality gates pass)
```

After ~5–10 minutes:
```
Training Run: credit_risk_v1 #42 ✅ COMPLETE
├── AUC: 0.862 ✓ (target: > 0.85)
├── Fairness Gap: 0.042 ✓ (threshold: < 0.10)
├── Data Drift: Minimal ✓
└── → Model auto-promoted to staging

Next: Request production approval from stakeholders
```

### 5.2: Requesting Production Approval

Once a model is in staging, request production approval.

**From Approvals Page:**
1. Click **+ Request Approval**
2. Select project: `credit_risk_v1`
3. Select destination: `Production`
4. Add optional note: "Ready for production. AUC 0.862, fairness validated."
5. Click **Submit for Approval**

**Expected flow:**
```
Approval Chain for credit_risk_v1 → Production
├── Step 1: ML Engineer Review
│   ├── Reviewer: carlos@company.com
│   ├── Status: Pending (sent yesterday)
│   └── View: [Experiment Details] [Model Card]
├── Step 2: Business Stakeholder Approval
│   ├── Reviewers: eve@company.com, frank@company.com
│   ├── Status: Waiting for Step 1 to complete
│   └── (Will receive email once ML Engineer approves)
└── Step 3: Auto-Promotion
    └── (Once all approvals complete, model auto-deploys)
```

**Reviewers see:**
- Model performance metrics (AUC, precision, recall, F1)
- Fairness dashboard (demographic parity, predictive equality)
- Data quality report (missing values, outliers)
- Cost estimate for production inference
- Experiment parameters and reproducibility info

### 5.3: Monitoring After Production Deployment

Once deployed to production, your model is continuously monitored.

**Typical Daily Workflow:**

**Morning Check (via Monitoring Page):**
```
🟢 All Systems Operational
├── Performance (AUC): 0.860 (target: > 0.80) ✓
├── Data Drift: Minimal (0.03) ✓
├── Fairness Gap: 0.038 (target: < 0.10) ✓
├── Serving Latency: 95ms (target: < 100ms) ✓
├── Throughput: 42 QPS (capacity: 50) ✓
└── Errors: 0.2% (SLA: < 1%) ✓
```

**Alert Scenario (1 Week Later):**
```
🟡 WARNING — Data Drift Detected
├── Feature: debt_to_income
│   ├── Previous distribution: μ=0.35, σ=0.12
│   ├── Current distribution: μ=0.42, σ=0.15
│   └── Drift score: 0.21 (threshold: 0.15)
├── Root Cause: Economic conditions (interest rates rising)
└── Action: Retrain model with latest data (scheduled for tonight)
```

**Auto-Recovery:**
```
1. Platform detects drift
2. Triggers automatic retraining
3. Tests new model against holdout set
4. If performance OK: promotes to staging
5. Notifies you: "New version deployed to staging, ready for production approval"
```

---

## Part 6: Real Workflow Example (Complete Scenario)

Here's a day-in-the-life of using the MLOps app:

### Monday Morning (9 AM)

**You:** "Let me check if credit_risk_v1 is still healthy."

```bash
# 1. Open http://localhost:8501
# 2. Click Projects → credit_risk_v1
# 3. View dashboard
```

**Dashboard shows:**
- Production model: `credit_risk_v1@v2.4` (deployed 3 weeks ago)
- Performance: AUC 0.86 ✓
- Data drift: 0.04 (OK)
- Fairness: All checks passing ✓
- Cost: $450/day for serving
- Incidents: None

**Verdict:** ✅ All green. No action needed.

### Tuesday Afternoon (3 PM)

**Alert:** You receive an email/Slack:
```
⚠️  Performance Drift Alert: credit_risk_v1
   AUC declined to 0.77 (target: > 0.80)
   Recommendation: Review or retrain model
```

**You:**
```
1. Open Monitoring page
2. Drill into credit_risk_v1 performance chart
3. See: AUC was 0.86 last week, now 0.77
4. Check data drift: Yes, drift_score=0.18
5. Check fairness: Fairness gap increased (0.04 → 0.08)
```

**Root cause:** Recent regulatory changes mean new types of applicants (different demographics, credit profiles).

**Action:**
```
1. Click "Trigger Retraining"
2. Select data version: Latest (includes last 3 weeks of new loans)
3. Click "Start Training"
```

### Wednesday Morning (10 AM)

**Email:** "Training Run Complete: credit_risk_v1 #45"

```
Results:
├── AUC: 0.842 ✓ (regression from 0.86, but expected given new data mix)
├── Fairness: Demographic parity gap = 0.053 ✓ (improved from 0.08)
├── Data Quality: All checks pass ✓
└── → Promoted to staging automatically
```

**You:**
```
1. Open Approvals page
2. Click "+ Request Approval"
3. Select: credit_risk_v1 → Production
4. Note: "Retrained on latest data after drift. Fairness improved."
5. Submit
```

### Thursday (1 PM)

**Email:** "Approval Requested: credit_risk_v1 v2.5 → Production"

Your ML Engineering lead (Carlos) receives the approval request.

Carlos opens the approval link and sees:
```
Model Comparison: v2.4 (current prod) vs v2.5 (staging)
├── AUC: 0.860 → 0.842 (slight regression)
├── Precision: 0.82 → 0.85 (+3%, good!)
├── Recall: 0.79 → 0.76 (-3%, concern)
├── Fairness: 0.04 gap → 0.053 gap (slightly worse)
└── Data: Uses data from last 3 weeks (more recent portfolios)

Carlos' Assessment:
   "AUC regression is expected given new data distribution.
    Precision improvement is significant. Fairness is still within
    threshold. I recommend approval for gradual rollout."

Action: Carlos clicks [Approve]
```

**Friday (9 AM)**

System now needs Business Stakeholder approval.

Eve (VP of Lending) receives email with deployment summary:
```
Model: credit_risk_v1 v2.5
Status: ML Engineering approved, awaiting Business approval
Previous Model: v2.4 (in production 3 weeks)

Key Metrics:
├── Expected Approval Rate: +2% (business impact)
├── Expected Default Prevention: +5% (good risk reduction)
├── Processing Time: 85ms (meets SLA)
├── Daily Cost: $455 (+$5 vs current)
└── Fairness Impact: All demographics treated fairly

Eve's Assessment:
   "Slight revenue increase, fairness maintained, minimal cost impact.
    Good to go."

Action: Eve clicks [Approve]
```

**Friday (1 PM)**

```
✅ Approval Chain Complete
   Approval 1 (ML Engineer): Carlos → Approved
   Approval 2 (Business): Eve → Approved
   
   → Model v2.5 auto-promotes to production
   → Canary rollout: 10% of traffic for 7 days
   → Auto-monitor for issues
   → Auto-rollback if problems detected
```

### Following Week

**Monday Morning:**
```
credit_risk_v1 v2.5 Production Deployment Status
├── Canary: Day 3 of 7
├── Traffic: 10% on v2.5, 90% on v2.4
├── Performance Comparison:
│   ├── v2.5 AUC: 0.841 (expected: 0.84) ✓
│   ├── v2.4 AUC: 0.860
│   └── Difference: -0.019 (within tolerance)
├── Fairness (v2.5): Gap = 0.052 ✓
├── Latency (v2.5): 87ms (target: <100ms) ✓
└── Errors: 0% (perfect)

Verdict: Canary performing well. Auto-scaling to 25% traffic tomorrow.
```

**Friday:**
```
credit_risk_v1 v2.5 Production Deployment Complete
├── Canary ended: Day 7
├── Performance validation: PASSED
├── Fairness validation: PASSED
├── Cost validation: PASSED
└── → Full production promotion: 100% traffic

credit_risk_v1 v2.4 → Archived
credit_risk_v1 v2.5 → Production (active)

Alert: Scheduled for monthly monitoring review next Friday.
```

---

## Part 7: Advanced Features

### 7.1: Data Contracts & Quality Gates

Ensure input data meets requirements before training.

**Example:**
```yaml
data_contract:
  table: mlops_projects.credit_risk_v1.raw_data
  freshness: max 1 day
  rows: min 10,000
  columns:
    credit_score:
      type: integer
      range: [300, 850]
      null_rate: <= 0.01
    loan_amount:
      type: decimal
      range: [500, 500000]
      null_rate: <= 0.01
    # ... more columns
  quality_checks:
    - duplicate_rate: <= 0.01
    - outlier_rate: <= 0.05
```

**Auto-enforcement:**
```
Training run requests data from raw_data table
   ↓
Platform checks data contract
   ├─ Is it fresh? Yes ✓
   ├─ Does it have enough rows? Yes (15,000) ✓
   ├─ Are all columns present? Yes ✓
   ├─ Do columns match schema? Yes ✓
   └─ Quality checks: All pass ✓
   
   → Training proceeds
```

### 7.2: Feature Store & Reuse

Reuse computed features across projects to reduce redundancy.

**Example:**
```
Feature: customer_annual_income
├── Owner: Data Science
├── Defined in: credit_risk_v1
├── Computation: SELECT customer_id, MAX(annual_salary) FROM hr_data
├── Version: v1.2 (updated monthly)
├── TTL: 30 days
├── Used by: [credit_risk_v1, churn_prediction, fraud_detection]
├── Quality Score: 9.5/10
└── Last Computed: 2024-01-14 (fresh)
```

**In new projects:**
Instead of redefining `customer_annual_income`, you can just reference it:
```
Features to use:
├── customer_annual_income (from feature_store.features.customer_annual_income)
├── customer_credit_score (own computation)
└── customer_payment_history (from churn_prediction project)
```

### 7.3: Fairness & Bias Testing

Automatically detect and prevent unfair model behavior.

**How it works:**
```
1. After training, run fairness tests
2. Compare model predictions across protected groups (age, gender, race)
3. Compute fairness metrics:
   ├─ Demographic Parity: P(Y=1 | Group=A) == P(Y=1 | Group=B)
   ├─ Equalized Odds: FPR(A) == FPR(B) AND TPR(A) == TPR(B)
   ├─ Calibration: Predicted prob == actual prob within groups
   └─ Individual Fairness: Similar people get similar predictions

4. Compare to threshold (e.g., "gap < 0.10")
5. If violated:
   ├─ Flag model as "Fairness Concerns"
   ├─ Require legal/compliance approval before production
   └─ Suggest mitigation (rebalance data, adjust thresholds, etc.)
```

**Example Output:**
```
Fairness Test Results: credit_risk_v1 v2.5
├── Demographic Parity
│   ├─ Age < 30: 45% approval rate
│   ├─ Age 30-50: 52% approval rate
│   ├─ Age > 50: 48% approval rate
│   └─ Gap: 7% (threshold: 10%) ✓ PASS
├── Equalized Odds
│   ├─ Gender=M: TPR=0.80, FPR=0.15
│   ├─ Gender=F: TPR=0.78, FPR=0.17
│   └─ Gap: ±2% (threshold: 5%) ✓ PASS
└── Overall Verdict: ✓ No significant fairness violations detected
```

### 7.4: Automatic Retraining & Rollback

Models automatically retrain when drift is detected, and auto-rollback if performance degrades.

**Retraining Triggers:**
```
Daily checks:
├─ Data Drift > 0.15 → Retrain
├─ Performance Drift > 5% → Retrain
├─ Fairness gap increase > 0.05 → Retrain
└─ Weekly schedule (every Monday) → Retrain
```

**Rollback Triggers:**
```
If new model fails ANY of these:
├─ Performance drops > 10% from previous → ROLLBACK
├─ Latency > 2x SLA → ROLLBACK
├─ Error rate > 1% → ROLLBACK
├─ Fairness gap increases > 0.10 → ROLLBACK (require review)
└─ Cost > 2x estimate → ROLLBACK (manual approval)

If rollback triggered:
1. New version immediately removed from production
2. Previous version restored
3. Incident logged with root cause
4. Notifications sent to team
5. Manual investigation required
```

### 7.5: Audit Logging

Every action is logged for compliance and debugging.

**Audit Trail Example:**
```
credit_risk_v1 Audit Log
├── 2024-01-14 09:15 — Training started by alice@company.com
├── 2024-01-14 10:22 — Training completed, AUC=0.842
├── 2024-01-14 10:23 — Data contract validation passed
├── 2024-01-14 10:24 — Fairness tests passed (gap=0.053)
├── 2024-01-14 10:25 — Auto-promoted to staging
├── 2024-01-14 14:30 — Production approval requested by alice@company.com
├── 2024-01-15 09:00 — Approved by carlos@company.com (ML Engineer)
├── 2024-01-15 13:45 — Approved by eve@company.com (Business Stakeholder)
├── 2024-01-15 14:00 — Canary deployment started (10% traffic)
├── 2024-01-22 09:00 — Canary validation complete
├── 2024-01-22 09:05 — Full production promotion (100% traffic)
└── 2024-01-22 09:06 — Incident log created (AUC drift from 0.86→0.84)
```

**Query capability:**
```sql
-- Who approved this model?
SELECT * FROM mlops.approvals 
WHERE project_id = 'credit_risk_v1' 
AND model_version = 'v2.5' 
AND status = 'approved';

-- What changed from v2.4 to v2.5?
SELECT * FROM mlops.model_versions 
WHERE project_id = 'credit_risk_v1' 
AND version_id IN ('v2.4', 'v2.5');

-- All actions by a specific user
SELECT timestamp, action, resource_id, result 
FROM mlops.audit_logs 
WHERE user_email = 'alice@company.com' 
ORDER BY timestamp DESC;
```

---

## Part 8: Troubleshooting

### Issue: "Not connected to Databricks"

**Symptoms:**
```
⚠️ Not connected to Databricks.
   Set `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, and `DATABRICKS_WAREHOUSE_ID` 
   in your `.env` file, then restart.
```

**Solutions:**
1. Verify `.env` has correct values:
   ```bash
   cat .env | grep DATABRICKS
   ```
2. Ensure no trailing slashes or extra spaces:
   ```
   ✓ DATABRICKS_HOST=https://adb-123456789.azuredatabricks.net
   ✗ DATABRICKS_HOST=https://adb-123456789.azuredatabricks.net/
   ```
3. Verify PAT token is still valid (tokens can expire):
   - Databricks UI → User Settings → Developer Tools → check expiration
4. Reload Streamlit (hard refresh in browser or restart app):
   ```bash
   Ctrl+C to stop
   streamlit run app.py  # restart
   ```

### Issue: "No projects yet" even after creating one

**Symptoms:**
Dashboard shows "No projects yet" after you click "Create Project."

**Solutions:**
1. Check if creation actually succeeded:
   - Look for error message at the end of Step 7
   - Check browser console (F12 → Console tab)
2. Verify database connection:
   ```bash
   # Query the database directly
   databricks sql query "SELECT * FROM mlops.projects LIMIT 1" --warehouse-id abc123
   ```
3. Refresh the page (browser: F5 or Cmd+R)
4. Check Streamlit logs:
   - Terminal where `streamlit run app.py` is running
   - Look for error messages

### Issue: Training runs are slow

**Symptoms:**
Training takes 20+ minutes when expected to take 5 minutes.

**Solutions:**
1. Check data size:
   ```sql
   SELECT COUNT(*) as row_count FROM [your_data_table];
   ```
   - If > 10M rows, consider sampling for dev/staging
2. Check cluster config:
   - Is it using a large enough machine type?
   - Try: `node_type_id=i3.2xlarge` (larger instance)
3. Check if other jobs are running:
   - Databricks UI → Clusters → Check utilization
4. Consider caching intermediate results:
   - Train on a smaller sample first
   - Use `CACHE TABLE` in Databricks SQL

### Issue: Monitoring page shows no data

**Symptoms:**
Monitoring page is empty or shows "No data available."

**Solutions:**
1. Ensure model is in production:
   - Only production models have monitoring active
   - Check Projects page → status should be "production"
2. Wait for data to accumulate:
   - Monitoring requires at least 100 predictions
   - First 24 hours may show minimal data
3. Check if model is actually serving:
   ```sql
   SELECT COUNT(*) FROM [your_model_serving_table]
   WHERE timestamp > CURRENT_TIMESTAMP() - INTERVAL 1 DAY;
   ```
   - If count is 0, model isn't serving predictions
4. Check serving endpoint status:
   - Databricks UI → Model Serving → Your endpoint
   - Should show "Ready" with 0 errors

### Issue: Approvals are stuck in "Pending"

**Symptoms:**
Approval request created but reviewers report they never received email.

**Solutions:**
1. Check email alert destination in Settings:
   - Email addresses must be valid Databricks workspace members
2. Check spam/junk folder for approval emails
3. Manually notify reviewers:
   - Copy approval link from Approvals page
   - Send them directly via Slack/email
4. Check if reviewer has permission:
   - They must be in the correct role (ml_engineers, business_stakeholders, etc.)
   - Verify in Settings → Team & Roles

### Issue: "Permission denied" when creating project

**Symptoms:**
```
ERROR: PermissionDenied
   You do not have permission to create projects.
```

**Solutions:**
1. Check your role in Settings:
   - Must be in: data_scientists, ml_engineers, or admin role
   - View Settings → Team & Roles
2. Have an admin add you to the correct role
3. Ensure your email matches Databricks account:
   - Databricks UI → User Settings → Account email
   - Should match email in Settings → Team & Roles

---

## Part 9: Next Steps & Best Practices

### Recommended First Projects

1. **Regression model** (e.g., demand forecasting)
   - Simpler than classification
   - Good practice for governance
   - Real business value

2. **Classification model** (e.g., churn prediction)
   - Requires fairness testing
   - Good for learning approval workflow
   - Common use case

3. **Real-time vs. batch**
   - Start with batch (simpler to set up)
   - Graduate to real-time API serving

### Best Practices

**Data Preparation:**
- Always version your input data (not just final tables)
- Document data lineage (where does it come from?)
- Set up data contracts before training

**Model Development:**
- Start with simple models (linear regression, decision trees)
- Graduate to complex models once workflow is smooth
- Always validate on holdout test set

**Governance:**
- Enable fairness testing for all models
- Require at least 1 human approval before production
- Review audit logs monthly for compliance

**Monitoring:**
- Set realistic thresholds (not too strict, not too loose)
- Check dashboards daily during first month
- Adjust monitoring rules based on false positives

**Rollback Readiness:**
- Always keep previous version running during canary
- Practice rollback procedure in staging first
- Maintain playbook for incident response

---

## Part 10: Support & Documentation

### Further Reading

- `DATABRICKS_MLOPS_APP_SPECIFICATION.md` — Architecture deep-dive
- `PROCESS_MAP.md` — Detailed workflow documentation
- `DATABASE_SCHEMA.md` — Table schemas and relationships
- `MLOPS_CONTROL_PLANE_DESIGN.md` — Governance & approval system

### Getting Help

1. Check logs:
   ```bash
   # Streamlit logs (where app is running)
   # Look for error messages
   
   # Databricks job logs (for training runs)
   # Databricks UI → Jobs → click job → view run logs
   ```

2. Query state tables:
   ```sql
   -- Check all projects
   SELECT project_name, status, created_at FROM mlops.projects;
   
   -- Check model versions
   SELECT model_id, version_id, status FROM mlops.model_versions;
   
   -- Check approval history
   SELECT * FROM mlops.approvals ORDER BY updated_at DESC;
   ```

3. Enable debug mode:
   ```bash
   # Add to .env
   DEBUG=true
   LOG_LEVEL=DEBUG
   
   # Restart app
   streamlit run app.py
   ```

---

## Summary

You now have a fully functional MLOps platform for Databricks! Here's what you can do:

✅ Set up Databricks connection
✅ Create projects via interview wizard
✅ Train models with automatic fairness testing
✅ Set up approval workflows
✅ Monitor production models for drift
✅ Auto-retrain and auto-rollback on failures
✅ Track costs and governance audit logs
✅ Collaborate with teams using shared features and dashboards

**Next:** Go create your first project! Start with the credit risk example above, then adapt for your own use cases.

Happy modeling! 🚀
