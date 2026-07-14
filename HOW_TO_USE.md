# Databricks MLOps App: Complete How-To Guide

A step-by-step walkthrough for setting up and using the MLOps platform on Databricks, from initial deployment through creating and monitoring your first model.

**Table of Contents**
1. [Prerequisites](#prerequisites)
2. [Part 1: Local Setup & Databricks Connection](#part-1-local-setup--databricks-connection)
3. [Part 2: Initial Configuration](#part-2-initial-configuration)
4. [Part 3: Creating Your First Project (End-to-End Demo)](#part-3-creating-your-first-project-end-to-end-demo)
5. [Part 4: Platform Features & Workflows](#part-4-platform-features--workflows)
6. [Part 5: Monitoring, Approvals & Governance](#part-5-monitoring-approvals--governance)
7. [Part 6: Real Workflow Example (Complete Scenario)](#part-6-real-workflow-example-complete-scenario)
8. [Part 7: Advanced Features](#part-7-advanced-features)
9. [Part 8: Troubleshooting](#part-8-troubleshooting)
10. [Part 9: Next Steps & Best Practices](#part-9-next-steps--best-practices)
11. [Part 10: Support & Documentation](#part-10-support--documentation)

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

### Step 1.0: New to Databricks? Set Up a Workspace First

Skip this step if you already have a Databricks workspace with Unity Catalog
and a SQL warehouse. If you're starting completely from scratch:

1. **Create an account and workspace** — [Databricks free trial](https://www.databricks.com/try-databricks)
   or your cloud provider's Databricks offering (AWS/Azure/GCP marketplace).
   Workspace creation takes a few minutes.
2. **Confirm Unity Catalog is enabled** — new workspaces have it on by
   default; check under **Catalog** in the left sidebar. If you see a
   catalog picker, you're set. (This app creates its own catalog/schema
   automatically on first run — you don't need to pre-create one.)
3. **Create a SQL warehouse** — **SQL → Warehouses → Create SQL Warehouse**.
   Any size works; this app only issues DDL and small state queries against
   it, never large scans. A **Serverless** warehouse starts fastest.
4. **Generate a personal access token** — profile icon (top right) →
   **Settings → Developer → Access tokens → Generate new token**. Copy it
   immediately; it's shown only once.

You now have everything `DATABRICKS_HOST` / `DATABRICKS_TOKEN` /
`DATABRICKS_WAREHOUSE_ID` need (Step 1.4 below).

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

**`.env.example` is the authoritative, fully-commented list of every config
option** — copy it once and treat it as your reference; this section only
calls out what's actually required to start, plus the gotchas that are easy
to miss.

**Required — the app won't connect without these three:**
```bash
DATABRICKS_HOST=https://your-workspace.azuredatabricks.net
DATABRICKS_TOKEN=dapi1234567890abcdef
DATABRICKS_WAREHOUSE_ID=abc123def456789
```

**Finding these:**
- **Host:** Top-right corner of Databricks UI → workspace name → copy workspace URL
- **Token:** User Settings (profile icon) → Developer Tools → Generate new token
- **Warehouse ID:** SQL → Warehouses → click any warehouse → copy ID from URL

**Everything else in `.env.example` is optional and the app degrades
gracefully when unset** — GitHub auto-repo creation, notification delivery
(SMTP/Slack/Teams), Budget Policy attribution, per-environment catalog
overrides, existing-repo-linking emptiness-check patterns, and
control-plane cost/capacity thresholds. Two things worth knowing before you
skip past them:

- **`GITHUB_TOKEN` scopes**: grant exactly `repo` and `workflow` when you
  generate the token — **not** `delete_repo`. Confirmed live: this app
  never deletes a GitHub repo or its contents under any circumstance, only
  creates/updates files and (separately, for project deletion) reminds a
  human to delete or archive it themselves. A token with `delete_repo`
  grants nothing this app uses and is unnecessary exposure.
- **`DATABRICKS_ACCOUNT_*` (Budget Policy attribution) are a different,
  higher-privilege credential class than everything else** — they
  authenticate against your Databricks *account* (which can span multiple
  workspaces), not the single workspace the token above talks to. Use a
  dedicated service principal scoped to budget-policy management only, not
  a shared admin identity. Leave these four unset entirely if you don't
  need per-project cost attribution — nothing else in the app depends on
  them.

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

### Step 1.7: Verify Your Setup (Recommended)

The fastest way to confirm everything above is actually wired correctly —
real credentials, real permissions, real connectivity — is to build a
complete real demo project through the app's own services, end to end:

```bash
python scripts/run_full_demo.py
```

This creates a synthetic training table, a real project with real
infrastructure (GitHub repo, UC schemas + Volumes, MLflow experiment),
walks it through all 7 wizard steps' worth of progressive file commits,
profiles the data, versions it (Delta CLONE snapshot), and saves an EDA
notebook snapshot — roughly nine stages, each printed as it completes. If
any of your config is wrong (bad token, missing warehouse permission,
insufficient GitHub scope), you'll find out here in under a minute rather
than partway through your first real project in the UI.

It's idempotent and safe to run more than once. When you're done looking
at what it built, tear it down:

```bash
python scripts/run_full_demo.py --teardown --drop-demo-table
```

This removes everything it created **except the GitHub repo** — the app
never deletes GitHub content under any circumstance (see the `GITHUB_TOKEN`
scopes note in Step 1.4); teardown prints the repo URL as a reminder to
delete or archive it yourself if you don't want to keep it.

### Step 1.8: Deploy as a Native Databricks App (Optional)

Running locally (`streamlit run app.py`) is enough to use and develop the
app. If you want it hosted *inside* your Databricks workspace instead —
one URL, no local process to keep running, native workspace auth — deploy
it as a [Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/):

```bash
python scripts/deploy_app.py
```

This is idempotent and safe to re-run any time you want to push a new code
version — each run:

1. Creates (or reuses) a workspace **secret scope** (`mlops_app_secrets`)
   holding your `DATABRICKS_TOKEN` and `GITHUB_TOKEN`, refreshing both
   values from your current `.env` every time — handy if a token rotated
   since the last deploy.
2. Creates (or reuses) the **App resource** itself, with both secrets
   attached as read-only bindings — matches what `app.yaml` expects via its
   `valueFrom` references.
3. Runs `databricks sync --full`, which makes the workspace copy of this
   repo **exactly match** your local directory — not just an incremental
   push, a true replace.
4. Starts the app's compute if it isn't already running, then triggers a
   snapshot deployment and waits for it to finish.

When it completes, it prints the app's live URL. First deploy typically
takes a couple of minutes (starting compute from cold); redeploys after
that are faster.

**Customizing the app name:**
```bash
python scripts/deploy_app.py --app-name my-mlops-app
```

**Note on non-secret config:** `app.yaml` sets `DATABRICKS_HOST`,
`DATABRICKS_WAREHOUSE_ID`, `MLOPS_CATALOG`, `MLOPS_SCHEMA`, and
`GITHUB_ORG` as plain (non-secret) values — edit `app.yaml` directly if
those differ from your `.env`. Only the two tokens flow through the secret
scope; every other optional variable from `.env.example` (notifications,
budget policy account credentials, per-environment catalog overrides, etc.)
needs adding to `app.yaml`'s `env:` list the same way if you want the
hosted app to pick it up — it does **not** read your local `.env` file.

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

**This isn't a "fill in 7 forms, then click Create at the end" wizard.**
Real infrastructure gets created progressively as you go — Step 1 fires
immediately (GitHub repo, UC schemas, MLflow experiment), and each later
step pushes the specific generated files its own answers affect straight
to that repo. By the time you reach Review, almost everything already
exists; "Create Project!" there just finalizes the approved config. A
**📋 Activity Log** panel (visible on every step once Step 1 has fired)
shows exactly what's happened so far, in order — see §3.9 and §4.2.

### Step 3.2: Complete Step 1 — Basic Info

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Model Name** | `credit_risk_v1` | Auto-corrected to lowercase + underscores as you type. Becomes your GitHub repo name and UC schema prefix — **locked after this step provisions infrastructure** (see below), since renaming afterward wouldn't rename the already-created repo/schemas. |
| **What business problem does it solve?** | `Predict credit default risk for loan applications` | Minimum 20 characters |
| **How do you measure success?** | `Achieve AUC-ROC >= 0.85 on holdout validation set with <10% disparity across demographic groups` | Minimum 20 characters — becomes the primary CI acceptance criterion |
| **Team** | `Data Science` | Loaded from org config if configured; otherwise free text |
| **Primary owner email** | `your-email@company.com` | Monitoring alerts and approval requests go here |
| **Existing GitHub repo (optional)** | *(leave blank)* | Leave blank and the app creates a new private repo. Paste a `https://github.com/org/repo` URL to push into an existing one instead — it must be empty (a README/.gitignore/LICENSE/.github stamped in by your org's repo-creation automation is fine; anything else blocks it, configurable via `MLOPS_EMPTY_REPO_IGNORE_PATTERNS`). |

**Click "Next →" — this is the step that actually provisions
infrastructure.** You'll see a spinner, then a results list (✅/⏭️/⚠️ per
action: GitHub repo, UC schemas + Volumes, MLflow experiment, Budget
Policy), then a **"Continue →"** button. This two-phase flow is
deliberate — you see exactly what got created before moving on, instead of
it flashing by. Safe to revisit: going back to this step later shows the
model name locked with a **🔒 Infrastructure already created** notice
rather than the editable field.

### Step 3.3: Complete Step 2 — Model Specs

**Fields to fill:**

| Field | Example Value | Notes |
|-------|---------------|-------|
| **Inference type** | `Real-time` | Batch, Real-time, Both, or Streaming — each renders different generated files (e.g. real-time gets `resources/model_serving.yml`, batch/both gets `src/batch_score.py`) |
| **Batch frequency / schedule** | *(shown for Batch/Both)* | Hourly/Daily/Weekly/Monthly/Quarterly + a cron builder |
| **Target P95 latency (ms)** | `150` | *(shown for Real-time/Both)* — sets the Model Serving endpoint alert threshold |
| **Target uptime %** | `99.95` | *(shown for Real-time/Both)* |
| **Expected QPS** | `50` | *(shown for Real-time/Both)* — sizes autoscaling |
| **Streaming source table** | `catalog.schema.table` | *(shown for Streaming)* — must already exist and be governed |
| **Framework(s)** | `XGBoost` | Multi-select — each selected framework generates matching MLflow-flavor code |

**Accelerants (optional, purely additive)** — your own `train.py` logic
stays authoritative either way:
- **AutoML baseline** — generates `automl_baseline.py`, a disposable first
  model via `databricks.automl.classify()`/`.regress()` (picked
  automatically based on your Step 6 performance metrics). Keep it as a
  score to beat, or delete the file. **Confirmed live**: AutoML requires
  classic Dedicated-access-mode compute and does not run on serverless-only
  workspaces — if your workspace policy is serverless-only (check with your
  admin), this file will render but the accelerant itself won't run there.
- **Hyperparameter search scaffold** — generates `hyperparameter_search.py`
  with a real Optuna trial loop and MLflow logging (works fine on
  serverless — no special compute requirement); the search space and your
  model's training/scoring are left as TODOs since those are specific to
  what you're building.

**Click "Next →"** — pushes the files this step's answers affect
(`resources/model_serving.yml`, `requirements.txt`, the accelerant files,
`src/train.py`) to your repo. If a file that used to apply (e.g.
`src/batch_score.py`, rendered under Step 1's temporary default before you
got here) no longer does, it's flagged in the Activity Log as needing your
manual review — **the app never deletes a file from your repo itself**,
only flags it.

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

**📊 Profile Data** — after entering a dataset, this samples it and runs a
full profiling report (row/column counts, missing %, duplicate %, plus a
downloadable HTML report with distributions and correlations). Also feeds a
default suggestion into Step 4's Data Quality Gates — a column that's
already frequently null in the real sampled data defaults to "Acceptable"
instead of "Required," so you're not hand-tuning defaults for columns whose
real behavior you can already see. The report is also saved automatically
to this project's UC Volume (`profile_reports/`) the moment it's generated
— not just offered as a download. Wide tables (10+ columns) skip the
pairwise-interactions scatter matrix automatically to keep the report a
reasonable size — everything else (per-column stats, correlations,
missing-value diagrams) still renders.

**Feature Catalog matches** — if a feature column you typed matches an
existing shared feature, it's surfaced here with its owner and reuse count.
Reusing it is the default; keeping a separate ad-hoc definition instead
requires a one-line justification, same pattern as the PII justification
block below it.

**Click "Next →"** — commits `src/train.py`'s data-loading section to your
repo, and takes a **Delta CLONE snapshot** of each training dataset into
this project's own UC schema (`training_data_snapshots` table tracks
source table, snapshot table, source Delta version, and row count) — a
physically independent copy that survives even if the source table is
later modified or vacuumed, so the exact data this project trained on can
always be faithfully reproduced. Skipped automatically on a revisit if the
dataset list hasn't changed since the last snapshot.

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
| **Enable budget alerts** | `Yes` | Optional — get notified when this project's spend crosses a threshold |
| **Budget period** | `Monthly` | Monthly, quarterly, or annual |
| **Budget threshold (USD)** | `500` | Spend ceiling for the period |
| **Alert at (% of threshold)** | `80` | Notify once spend reaches this percentage |
| **Budget policy ID** | *(leave blank)* | Optional — attributes this project's serverless usage to a specific Databricks Budget Policy for billing |

Budget alerts reuse the email addresses you configured above as the alert
destination — add an email destination first if you want to receive them.
Alerts and budget breaches are actually delivered (email/Slack/Teams) only
if the corresponding `MLOPS_SMTP_*`/`MLOPS_SLACK_WEBHOOK_URL`/
`MLOPS_TEAMS_WEBHOOK_URL` variables are set in `.env` (Step 1.4) — otherwise
the breach is still recorded, just not sent anywhere.

**Budget policy ID is a different thing from budget alerts above** — budget
alerts are the app notifying *you*; the budget policy ID is Databricks'
*own* native billing attribution mechanism (serverless compute only —
jobs and serving endpoints, which is everything this app generates).
Leave it blank and the app automatically creates (or reuses) a policy for
this project — that only actually happens if the account-level credentials
in `.env` (Step 1.4) are configured; otherwise this is silently skipped and
the project just has no policy attribution, with no error shown.

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
| **Legal / Business / Security / Compliance / Internal Audit contact email** | `legal@company.com` | Optional per-gate contact — if set, that person is notified automatically when the corresponding gate opens (see Approvals page, §4.6) |

**Click "Review & Create" to finish.**

### Step 3.9: Review & Create

You'll see a summary of all your answers, plus two lists — **"Already
provisioned (Step 1)"** (GitHub repo, UC schemas + Volumes, MLflow
experiment, Budget Policy — all real, created back at Step 1) and **"What
'Create Project!' still does"** (record the final approved config version
with its manifest hash, sync risk tier + policy packs, save the budget
alert config). This is intentionally a much smaller list than it used to
be — almost everything already happened progressively as you went through
Steps 1–6.

**Click "✓ Create Project!"** to finish.

**Expected output:**
```
✅ Project `credit_risk_v1` created! (ID: a1b2c3d4-...)
Infrastructure steps (provisioned progressively as you completed the wizard):
✅ Budget Policy — created: mlops-credit_risk_v1
✅ Github Repo — https://github.com/acme-mlops/credit-risk-v1
✅ Uc Schemas — mlops.credit_risk_v1_dev, mlops.credit_risk_v1_staging, mlops.credit_risk_v1_prod
✅ Uc Volumes — mlops.credit_risk_v1_dev.artifacts, mlops.credit_risk_v1_staging.artifacts
✅ Mlflow Experiment — /Shared/mlops/credit_risk_v1
```

(If account-level Budget Policy credentials aren't configured, that line
reads `⏭️ Budget Policy — Account-level credentials not configured` instead
— the project is created fine either way, just without cost attribution.)

For the full chronological record of every action taken — including each
individual file commit and any files flagged for your manual cleanup —
expand **📋 Activity Log** (visible on every wizard step and on the project
dashboard afterward; see §4.2).

The generated repo's `src/` folder has:
- **`train.py`** — the job entry point the training/retraining workflow
  actually runs. If any Step 3 feature columns resolved to a shared Feature
  Catalog entry, this includes real `FeatureLookup`/`create_training_set`
  code (grouped by source table) — only the join key is left as a TODO,
  since the app tracks what a feature *is*, not what column joins it to
  your specific training data.
- **`eda.py`** — a Databricks-notebook-shaped starting point for
  exploration and feature selection, pre-wired to this project's dev
  catalog/schema and the same MLflow experiment `train.py` logs to.
- **`evaluate.py`** — real, runnable performance-metric and fairness-check
  code matching exactly what Steps 4/6 declared (not a generic metrics
  dump), plus training-time SHAP/LIME. The fairness gate fails closed —
  it raises if measured disparity exceeds your configured threshold, it
  doesn't just log a warning. Only the model/holdout-data loading is a stub.
- **`automl_baseline.py`** / **`hyperparameter_search.py`** — only if you
  opted into those accelerants in Step 2.

See §7.6 for org toolkit auto-import into `train.py`/`eda.py`/the
accelerant files, and §7.7 for auto-profiling and Feature Catalog reuse.

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

**📋 Activity Log** — a chronological, expandable list of every
infrastructure action the app has taken for this project: GitHub repo
creation, UC schemas/Volumes, MLflow experiment, Budget Policy, each file
commit (with a link back to what changed), and any file flagged
`pending_deletion` (see §7.8). Same underlying record the wizard's own
Activity Log shows mid-creation — this is where you look it up again
afterward.

**📸 Snapshot EDA notebook to Volume** — a manual checkpoint button. EDA
happens in a Databricks notebook over days or weeks with no natural "done"
signal the app can detect, so this is DS-triggered whenever you want one:
reads the current `src/eda.py` from GitHub and writes a timestamped copy to
the project's UC Volume (`eda_snapshots/`).

**🧹 Clean up QA resources** — deletes non-essential dev/QA serving
endpoints (anything prefixed with your project name that isn't the
bundle's own managed endpoint) and scratch tables (only ones explicitly
prefixed `zz_`/`scratch_`/`tmp_` — nothing else is ever touched). The same
reaper runs automatically, best-effort, before every prod deploy; this
button lets you run it manually any time, e.g. after a burst of
experimentation.

**⚠️ Danger Zone → project deletion** — requires MLOps approval before
anything happens (reuses the same Approvals page every other governance
gate uses). Once approved, deletion:
- soft-deletes the project (status flips to `deleted`, the row itself is
  never removed — audit trail stays intact)
- deletes the Budget Policy and secret scope, if either was provisioned
- **preserves all UC data** — schemas, tables, Volumes, and training-data
  snapshots are never touched, since destroying those would defeat the
  whole point of the Delta CLONE reproducibility snapshots (§3.4)
- **never touches the GitHub repo** — instead lists every file currently in
  it as a checklist for you to review and delete or archive yourself. The
  app's GitHub token deliberately doesn't have `delete_repo` scope (§1.4).

### 4.3: Data Contracts Page

**Path:** `07_data_contracts.py`

**Purpose:** Define and enforce data quality requirements.

**What you can do:**
- View input data schema and expected distributions
- Set data quality thresholds (null %, outliers %, column stats)
- Monitor compliance: which data loads meet the contract
- Auto-reject data that violates the contract
- **Run a quality assessment** — click "▶ Run quality assessment" on any
  contract to actually execute the null/uniqueness checks its columns
  declare against the real Unity Catalog table (not just view the declared
  rules). Records a scored result (excellent/good/acceptable/poor/critical)
  with which checks failed and which columns carry PII, shown inline on the
  contract going forward.

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

**SLA escalation:** a pending review that sits past its configured SLA
window is marked escalated (never auto-approved) and notifies the
project's configured alert destinations (Step 3.7) — so a stuck review
gets surfaced, not silently missed.

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

**Approver notification:** when a new gate opens, its configured contact
email (Step 3.8's per-gate contact fields) is notified automatically, if
one was set and a notification channel is configured (Step 1.4). Gates
with no natural human contact (code review, end-to-end test — CI-driven
checks) aren't notified.

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
- Total compute spend — toggle grouping between **project**, **team**, or
  **deployment type** (batch/real-time/streaming) via the radio above the
  cost table
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

**What's real vs. bookkeeping:** the catalog above (owner, version, used-by
count) is tracked metadata. What generates real code is Step 3's Feature
Catalog coercion — when a feature column you type matches a shared entry,
choosing to reuse it means `train.py` gets an actual
`databricks.feature_engineering.FeatureLookup`/`create_training_set` call
for that feature table, not just a note that it exists. Multiple reused
features from the same table are grouped into one lookup.

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

**What actually runs this:** the generated `evaluate.py` — real
`fairlearn.metrics.demographic_parity_difference`/
`equalized_odds_difference` calls (when `fairlearn` is your selected
framework) against exactly the protected attributes/proxy variables you
declared in Step 4. The gate fails closed: exceeding your configured
disparity threshold raises `FairnessGateFailure`, not just a logged
warning. (`aif360` needs privileged/unprivileged group *values* per
attribute that this app can't infer, so choosing it generates a scaffold
with that TODO rather than a guess.) `evaluate.py` also logs training-time
SHAP/LIME as an MLflow artifact.

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

### 7.6: Org Toolkit Auto-Import

Every generated project gets a `src/eda.py` (exploration/feature-selection
notebook) and `src/train.py` (the job that actually runs). By default
neither imports anything beyond the standard library and MLflow — this app
ships with **zero toolkits configured**, since there's no universal "the"
MLOps or Data Science toolkit every org would want. You configure your own.

**To add one:** create a YAML file in `toolkits/` (repo root, sibling to
`policy_packs/`) — same convention: PR-reviewed, GitHub is the source of
truth, not a wizard field or `.env` value. A starting template ships at
`toolkits/org_toolkits.yaml.example` — copy it, drop the `.example` suffix,
and edit:

```yaml
toolkits:
  - toolkit_id: mlops_toolkit
    name: "Acme MLOps Toolkit"
    pip_spec: "acme-mlops-toolkit>=2.0"
    import_statement: "import acme_mlops_toolkit as mlops"

  - toolkit_id: ds_toolkit
    name: "Acme Data Science Toolkit"
    pip_spec: "git+https://github.com/acme-corp/ds-toolkit.git@main"
    import_statement: "from acme_ds_toolkit import eda, features as ds_features"
```

**What happens with this configured:**
- Every new project's `requirements.txt` gets both `pip_spec` lines (no
  `requirements.txt` is generated at all if zero toolkits are configured —
  nothing to put in it)
- `train.py` and `eda.py` both get the `import_statement` lines injected at
  the top
- `batch_score.py`/`stream_score.py` (inference-time scripts) are **not**
  touched — this is scoped to EDA/feature-selection/training code

Multiple toolkits are fine — order in the YAML is preserved in generated
files. `toolkit_id` must be unique across every `toolkits/*.yaml` file (one
big flat namespace, same as policy pack IDs).

**Validation is intentionally light:** `pip_spec` and `import_statement`
are just required to be non-empty strings — there's no check that the pip
spec actually installs or the import statement is valid Python. A mistake
here surfaces at `pip install` or import time inside a generated project,
not at config-load time.

---

### 7.7: Data Profiling

Step 3's **📊 Profile Data** button (next to "⟳ Infer Schema") samples the
first training dataset and produces two things:

1. **A compact summary shown inline**: rows sampled, column count, missing
   cells %, duplicate rows %.
2. **A full HTML profiling report**, offered as a download — distributions,
   correlations, cardinality, the kind of output pandas-profiling is known
   for. That library has actually been renamed twice since — it's currently
   `fg-data-profiling` (was `ydata-profiling`, was `pandas-profiling`) —
   confirmed against the live PyPI listing when this was built, not assumed
   from an older name.

Profiling always runs against a **capped sample** (5,000 rows by default),
never the full table — this is exploration tooling, not a production
quality check (that's the Data Contracts page's "Run quality assessment,"
§7.1, which runs against the real table).

**The per-column stats feed Step 4 automatically**: a column that's already
frequently null in the sampled data (>5%) defaults into the Data Quality
Gates' "Acceptable Issues" box instead of "Required" — you're not
hand-tuning a default for a column whose real behavior you can already see.
This only happens if you clicked "📊 Profile Data" before reaching Step 4;
skipping it leaves every column defaulting to "Required," same as before
this feature existed.

**Requires `fg-data-profiling` installed** (`pip install -r
requirements.txt`) — installed and `pip-audit`ed clean as of when this was
built. Note if you're on a newer `setuptools`: `fg-data-profiling` imports
`pkg_resources` directly without declaring `setuptools` as a dependency,
and `setuptools>=81` dropped that shim — `requirements.txt` pins
`setuptools<81` for exactly this reason. If profiling fails with
`ModuleNotFoundError: No module named 'pkg_resources'`, that pin is
missing or got overridden.

### 7.8: Progressive Provisioning, the Drift Guard, and Stale Files

Covered in context throughout Part 3, collected here for reference.

**Provisioning fires per-step, not all at once.** Step 1's "Next →" creates
real infrastructure immediately (GitHub repo, UC schemas + Volumes, MLflow
experiment, Budget Policy) — idempotent and tracked, so revisiting Step 1
or a Streamlit rerun never re-creates anything that already succeeded.
Steps 2–6 each push only the files their own answers affect, re-rendering
the whole bundle locally (cheap) but committing just the relevant subset.

**The changed-assumptions drift guard** protects any file you've hand-edited
from being silently overwritten by a later step's commit. Before pushing an
update to a previously-generated file, the app compares the file's current
content hash in your repo against the hash recorded when it was last
auto-generated. Match → safe to overwrite. Mismatch → you've edited it —
the push is skipped and recorded as `blocked_drift` in the Activity Log
instead. There's no diff-preview UI yet; if you hit this, compare the files
yourself. (A force-regenerate path exists at the service layer for a future
UI addition, not exposed in the wizard today.)

**Stale files are flagged, never deleted.** A file can become inapplicable
as later steps reveal more — the clearest example: Step 1's initial render
doesn't know your `inference_type` yet (nothing has asked), so it defaults
to `batch` and generates `src/batch_score.py`; if Step 2 then says
`real_time`, that file no longer applies. **The app will never delete it
for you** — instead it's flagged `pending_deletion` in the Activity Log
with an explanation, and stays flagged until you remove the file yourself
(or it clears automatically if a later answer makes it relevant again).
This is the same "app creates, humans delete" principle used for GitHub
repo deletion (§4.2) — applied at the file level instead of the whole-repo
level.

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

### Issue: Alerts/budget breaches/approver notifications aren't arriving

**Symptoms:**
Budget alerts, performance alerts, new-gate notifications, or HITL SLA
escalations show up in the app (dashboard, audit log) but no email/Slack/
Teams message ever arrives.

**Solutions:**
1. Check `.env` has the relevant channel configured (Step 1.4):
   `MLOPS_SMTP_HOST`/`MLOPS_SMTP_FROM_EMAIL` for email,
   `MLOPS_SLACK_WEBHOOK_URL` for Slack, `MLOPS_TEAMS_WEBHOOK_URL` for Teams.
   An unset channel silently reports `not_configured` — this is intentional
   (never crashes on a missing secret), but it does mean nothing was sent.
2. For email specifically, confirm at least one recipient address is
   actually configured on the project (Step 3.7's alert destinations —
   budget alerts and performance alerts reuse this list).
3. For approver notifications, confirm the gate type has a contact email
   set in Step 3.8 — gates with no contact configured (or no natural human
   contact, like code review) are skipped by design.
4. Notification failures never block the underlying action (a budget
   breach is still recorded, a gate still opens, an SLA escalation still
   happens) — so "nothing arrived" doesn't mean anything else broke.

### Issue: New projects have no Budget Policy attributed

**Symptoms:**
`projects.budget_policy_id` is empty for a newly created project, and the
generated `jobs.yml`/`model_serving.yml` have no `budget_policy_id` field.

**Solutions:**
1. Confirm all four account-level variables are set in `.env` (Step 1.4):
   `DATABRICKS_ACCOUNT_HOST`, `DATABRICKS_ACCOUNT_ID`,
   `DATABRICKS_ACCOUNT_CLIENT_ID`, `DATABRICKS_ACCOUNT_CLIENT_SECRET`. All
   four are required — this is a different credential than the workspace
   `DATABRICKS_TOKEN`. Missing any one of them disables the feature
   entirely, silently (no error in the UI) — check the project-creation
   step log ("Infrastructure steps") for a `budget_policy` line reading
   `skipped`.
2. Confirm the service principal behind those credentials actually has
   permission to create/list Budget Policies at the account level — a
   permissions error also shows as `skipped` there, with the underlying
   error in the detail text.
3. This never blocks project creation either way — a skipped budget policy
   step just means that project's serverless usage won't be attributed to
   a policy, not that anything else failed.

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
