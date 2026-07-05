# Databricks MLOps App: UI Wireframes & Mockups

## Overview

This document presents wireframes for all major screens in the app, designed with simplicity and Apple-like aesthetics in mind.

---

## Table of Contents

1. [Setup Interview Flow](#setup-interview-flow)
2. [Project Creation Interview](#project-creation-interview)
3. [Data Contract Manager](#data-contract-manager)
4. [Project Dashboard (One-Stop Shop)](#project-dashboard-one-stop-shop)
5. [Model Performance Dashboard](#model-performance-dashboard)
6. [Approval Center](#approval-center)
7. [Development Templates](#development-templates)
8. [Monitoring & Drift Dashboard](#monitoring--drift-dashboard)

---

## Setup Interview Flow

### Screen 1: Welcome & Use Case Selection

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  🚀 Welcome to Databricks MLOps                                 │
│                                                                  │
│  Let's set up your MLOps platform. First, what would you like   │
│  to accomplish?                                                  │
│                                                                  │
│  Select one or more:                                            │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  ☐ Data Ingestion                                              │
│    └─ Build a data pipeline that ingests data from sources     │
│       into Databricks, with validation and quality checks      │
│                                                                  │
│  ☐ Online Model (Real-time Inference)                          │
│    └─ Deploy a model that serves predictions in real-time      │
│       via a REST API, with ultra-low latency requirements      │
│                                                                  │
│  ☐ Batch Model                                                  │
│    └─ Train and score on large datasets on a schedule or       │
│       on-demand, with outputs written to tables                │
│                                                                  │
│  ☐ Lookup Service                                               │
│    └─ Fast feature table queries (keys → values) that return   │
│       pre-computed aggregations or lookups, ideal for          │
│       real-time enrichment                                     │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│                                      [Continue] [Skip Setup]    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Screen 2: Organization Configuration

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  SETUP: Organization Configuration                              │
│                                                                  │
│  ▼ Organization Info                                            │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  Organization Name *                                            │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Acme Corp                                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│  Help: The name of your company or department                 │
│                                                                  │
│  Regulated Industry *                                           │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Select industry... ▼                                        │ │
│  │  □ Financial Services (SOX, Fair Lending)                 │ │
│  │  □ Healthcare (HIPAA, FDA)                                │ │
│  │  ☑ None/Other                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│  Help: Determines governance & compliance requirements         │
│                                                                  │
│  ▶ Deployment Pattern                        [Uses defaults]    │
│    └─ single_workspace (all dev/prod in one workspace)          │
│                                                                  │
│  ▶ GitHub Configuration                      [Uses defaults]    │
│    └─ github.com/acme-mlops                                     │
│                                                                  │
│  ▶ Data Retention Policies                   [Uses defaults]    │
│    └─ Experiments: 90 days | Audit logs: 7 years               │
│                                                                  │
│  ▶ Personas & Groups                         [Uses defaults]    │
│    └─ data_scientists, ml_engineers, legal_reviewers, ...       │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                       [Previous] [Next: Personas] [Skip Setup]  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Screen 3: Personas & Groups

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  SETUP: Personas & Access Control                               │
│                                                                  │
│  This section will define which groups of users, based on their │
│  Unity Catalog permission group membership, will have specific   │
│  permissions within the platform. Users might have membership   │
│  in more than one group.                                        │
│                                                                  │
│  ▼ Data Scientists                                              │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  Permissions:                                                    │
│  ☑ Train models       ☑ Run experiments                        │
│  ☑ Register models    ☐ Deploy to prod                         │
│  ☐ Approve releases   ☐ Override approvals                     │
│                                                                  │
│  Members (by email or Databricks group):                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ alice@acme.com                                [✕]         │ │
│  │ bob@acme.com                                  [✕]         │ │
│  │ [+ Add member]                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ▼ ML Engineers / MLOps                                          │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  Permissions:                                                    │
│  ☑ Train models       ☑ Run experiments                        │
│  ☑ Register models    ☑ Deploy to prod                         │
│  ☑ Approve releases   ☑ Override approvals                     │
│  ☑ Delete models      ☑ Manage infrastructure                  │
│                                                                  │
│  Members:                                                        │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ carlos@acme.com                                [✕]         │ │
│  │ [+ Add member]                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ▶ Legal Reviewers                           [1 member]         │
│  ▶ Business Stakeholders                     [2 members]        │
│  ▶ Security & Audit                          [1 member]         │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                       [Previous] [Next: Infrastructure]          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Project Creation Interview

### Screen 1: Project Basics

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📋 New Project                                                  │
│  Customer Churn Prediction                                       │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  STEP 1 OF 7: Basics                              [██░░░░░░] 14% │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  Model Name *                                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ customer_churn_prediction                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│  Help: Lowercase, underscores, letters/numbers only. GitHub repo │
│        will be created with this name.                          │
│                                                                  │
│  Business Problem *                                              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Identify customers likely to churn in next 30 days to      │ │
│  │ enable proactive retention campaigns                       │ │
│  │                                                             │ │
│  │                                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│  Help: Why does your business need this model?                 │
│                                                                  │
│  Success Metric *                                                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Achieve AUC-ROC ≥ 0.85 on holdout validation set           │ │
│  └────────────────────────────────────────────────────────────┘ │
│  Help: How will you know if this model succeeds?               │
│                                                                  │
│  Team Owner *                                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Retention Team ▼                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Primary Owner *                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ alice@acme.com ▼                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│             [← Back] [Next: Use Cases →] [Save & Exit]          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Screen 2: Use Cases (Multi-select)

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📋 New Project: customer_churn_prediction                       │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  STEP 2 OF 7: Use Cases                         [████░░░░░░] 28% │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  Which capabilities do you need? (Select one or more)           │
│                                                                  │
│  ☑ Batch Model Inference                                        │
│    └─ Run predictions on large datasets on a schedule          │
│       Results written to tables for downstream consumption      │
│       └─ Frequency: Daily                                       │
│                                                                  │
│  ☐ Online Model Serving                                         │
│    └─ Real-time REST API for single/batch predictions          │
│       Ultra-low latency requirement                            │
│       └─ (Configure if selected)                               │
│                                                                  │
│  ☐ Lookup Service                                                │
│    └─ Fast key-value lookups returning pre-computed values     │
│       Ideal for real-time feature enrichment                   │
│       └─ (Configure if selected)                               │
│                                                                  │
│  ☐ Data Ingestion Pipeline                                      │
│    └─ Ingest data from external sources with validation        │
│       └─ (Configure if selected)                               │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│             [← Back] [Next: Model Details →]                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Screen 3: Model & Data (Collapsed Defaults)

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📋 New Project: customer_churn_prediction                       │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  STEP 3 OF 7: Data & Model                      [██████░░░░] 42% │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  ▼ Training Data                                                │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  Data Location *                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ feature_store.customer.training_data_v1    [Browse]       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Target Variable (what we're predicting) *                       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ churn_flag ▼                                                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Features (auto-detected, accept or customize) *                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ ✓ 47 features detected (customize below)        [Edit] │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ▶ Data Quality & Governance                 [Using defaults]   │
│    └─ Fairness: aif360 on (age, gender)                         │
│    └─ Quality: All fields must pass checks                      │
│                                                                  │
│  ▶ Advanced Data Options                     [Using defaults]   │
│    └─ PII handling, classification, custom rules                │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│             [← Back] [Next: Deployment →]                       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Screen 4: Deployment & Retraining

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📋 New Project: customer_churn_prediction                       │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  STEP 4 OF 7: Deployment & Retraining          [████████░░] 56% │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  ▼ Retraining Strategy *                                        │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  How should this model be automatically retrained?             │
│                                                                  │
│  ○ Manual Only       – Retrain only when you trigger it        │
│  ○ Scheduled         – Retrain on a fixed schedule (e.g. daily)│
│  ● Hybrid (Default)  – Retrain on schedule OR if drift detected│
│  ○ On Drift Only     – Retrain immediately if performance drops│
│                                                                  │
│  If Hybrid selected:                                            │
│  Schedule:  [0 2 * * *] (Daily at 2 AM)                        │
│  Drift Threshold: [5.0]% performance drop                       │
│                                                                  │
│  ▼ Rollback Configuration                                       │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  ☑ Auto-rollback if model crashes in production                │
│    Error threshold: [10] errors in [5] minutes                 │
│                                                                  │
│  ▶ Deployment Options                        [Using defaults]   │
│    └─ Canary: 10% traffic | Shadow: 7 days | Scale-to-zero: Off│
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│             [← Back] [Next: Monitoring →]                       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Screen 5: Monitoring & Alerts

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📋 New Project: customer_churn_prediction                       │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  STEP 5 OF 7: Monitoring & Alerts               [█████████░] 70% │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  ▼ Data & Performance Monitoring                                │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  ☑ Monitor for data drift (input distribution changes)         │
│  ☑ Monitor for performance drift (accuracy drops)              │
│  ☑ Monitor endpoint uptime and health                          │
│                                                                  │
│  Alert if performance drops more than: [5]%                    │
│                                                                  │
│  ▼ Alert Destinations                                           │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  ☑ Email alerts       ☑ Slack alerts                           │
│    └─ alice@acme.com     └─ #data-science-alerts               │
│    └─ [+ Add recipient]  └─ [+ Add channel]                    │
│                                                                  │
│  ▶ Custom Monitoring Metrics                  [Optional]        │
│    └─ Add domain-specific metrics to monitor                    │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│             [← Back] [Next: Governance →]                       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Screen 6: Governance & Approvals

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📋 New Project: customer_churn_prediction                       │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  STEP 6 OF 7: Governance & Approvals            [██████████] 84% │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  ▼ Approval Requirements (Required for production)              │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  ☑ Code review by 2 peers (from data_scientists group)        │
│  ☑ Fairness/bias testing (aif360 framework)                    │
│  ☑ Legal review (from legal_reviewers group)                   │
│  ☑ Business approval (from business_stakeholders group)        │
│  ☑ Security scan (pip-audit for vulnerable dependencies)       │
│  ☑ End-to-end test in staging (7 day minimum soak time)        │
│                                                                  │
│  ▼ Testing Requirements                                         │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  Minimum test coverage required: [100]%                         │
│  Help: Unit + integration tests. Lower coverage requires        │
│        DS + MLOps approval.                                     │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│             [← Back] [Review & Create →]                        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Screen 7: Review & Create

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📋 New Project: customer_churn_prediction                       │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  STEP 7 OF 7: Review                           [███████████] 100%│
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  SUMMARY OF YOUR CONFIGURATION                                  │
│  ═══════════════════════════════════════════════════════════   │
│                                                                  │
│  ✓ Model Basics                                                 │
│    └─ customer_churn_prediction by alice@acme.com              │
│    └─ Owned by Retention Team                                  │
│    └─ Goal: AUC ≥ 0.85                                          │
│                                                                  │
│  ✓ Deployment                                                   │
│    └─ Batch inference daily                                    │
│    └─ Retrain: Hybrid (daily + on 5% drift)                    │
│    └─ Auto-rollback: 10 errors in 5 minutes                    │
│                                                                  │
│  ✓ Monitoring                                                   │
│    └─ Data drift + performance drift + endpoint uptime         │
│    └─ Alert if performance drops >5%                           │
│    └─ Alerts to: alice@acme.com, #data-science-alerts          │
│                                                                  │
│  ✓ Governance (Will be enforced)                                │
│    └─ Code review (2 reviewers) required                        │
│    └─ Fairness testing (aif360 on age, gender)                 │
│    └─ Legal + Business approval for production                 │
│    └─ 100% test coverage required                              │
│    └─ 7-day staging soak time minimum                          │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  WHAT HAPPENS NEXT:                                             │
│  ═══════════════════════════════════════════════════════════   │
│                                                                  │
│  1. GitHub repo created: github.com/acme-mlops/                │
│     customer_churn_prediction                                  │
│                                                                  │
│  2. Training skeleton generated (src/train.py, tests/, etc.)   │
│                                                                  │
│  3. CI/CD pipelines configured in .github/workflows/           │
│                                                                  │
│  4. UC schemas created for dev/staging/prod data               │
│                                                                  │
│  5. Service account + secrets created                          │
│                                                                  │
│  6. Monitoring dashboard deployed                              │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                    [← Back] [✓ Create Project!]                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Contract Manager

### Data Contract Editor (Table View)

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📊 Data Contracts: customer_churn_prediction                    │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  Training Input Data  v1.2                                       │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  Table: feature_store.customer.training_data_v1                 │
│  Owner: alice@acme.com                                          │
│  Status: ✓ Validated by alice on 2024-01-15                    │
│  Version History: [v1.0] [v1.1] [v1.2 current]                 │
│                                                                  │
│  ┌─ Columns (scroll to see all) ────────────────────────────── ┐ │
│  │                                                             │ │
│  │ Col# │ Name            │ Type     │ Nullable │ Unique │ PII  │
│  │─────┼─────────────────┼──────────┼──────────┼────────┼────  │
│  │  1  │ customer_id     │ string   │    No    │  Yes   │HIGH  │
│  │  2  │ age             │ int      │   Yes    │   No   │MED   │
│  │  3  │ purchase_freq   │ float    │   Yes    │   No   │NONE  │
│  │  4  │ churn_flag      │ boolean  │    No    │   No   │NONE  │
│  │  ... │ (47 total)      │          │          │        │      │
│  │                                                             │
│  └─────────────────────────────────────────────────────────── ┘
│                                                                  │
│  [+ Add Column] [Edit Selected] [Import CSV] [View JSON]        │
│                                                                  │
│  Detailed View (click row to expand):                           │
│  ┌─────────────────────────────────────────────────────────── ┐ │
│  │ customer_id (string)                                      │ │
│  │                                                           │ │
│  │ Description:                                             │ │
│  │ ┌──────────────────────────────────────────────────────┐ │ │
│  │ │ Unique customer identifier                           │ │ │
│  │ └──────────────────────────────────────────────────────┘ │ │
│  │                                                           │ │
│  │ Constraints:                                              │ │
│  │ ┌──────────────────────────────────────────────────────┐ │ │
│  │ │ [✓] Not null  [✓] Unique  [✓] Pattern: CUST_*    │ │ │
│  │ │ Quality Tests: [✓] null_check  [✓] uniqueness      │ │ │
│  │ └──────────────────────────────────────────────────────┘ │ │
│  │                                                           │ │
│  │ Classification: Sensitive | PII Level: High              │ │
│  │ Is Fairness Attribute: ☐                                 │ │
│  │ Required for Quality: ☑                                  │ │
│  │ Monitor for Drift: ☑  (drift_type: value_drift)          │ │
│  │                                                           │ │
│  │ [Save Changes] [Delete Column] [Close]                   │ │
│  └─────────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  Version 1.2 Change Log:                                        │
│  └─ 2024-01-15: Added age fairness monitoring (commit abc123)  │
│  └─ 2024-01-10: Increased purchase_freq range (alice)          │
│  └─ 2024-01-05: Initial version (alice)                        │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  [+ New Contract] [Save as JSON] [Commit Changes] [Cancel]     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Project Dashboard (One-Stop Shop)

### Main Project Dashboard

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  🏠 customer_churn_prediction                                    │
│  Batch model to predict customer churn in next 30 days           │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  ╔═══════════════╦═══════════════╦═══════════════╦════════════╗ │
│  ║ STATUS        ║ OWNER         ║ TEAM          ║ CREATED    ║ │
│  ╠═══════════════╬═══════════════╬═══════════════╬════════════╣ │
│  ║ 🟢 Production ║ alice@acme.com║ Retention     ║ 2024-01-15 ║ │
│  ╚═══════════════╩═══════════════╩═══════════════╩════════════╝ │
│                                                                  │
│  ═══════════════════════════════════════════════════════════   │
│  TAB: [Overview] [Performance] [Data Quality] [Governance]      │
│  ═════════════════════════════════════════════════════════════ │
│                                                                  │
│  ▼ QUICK STATS                                                  │
│  ═════════════════════════════════════════════════════════════ │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ LIVE VERSION │  │  STAGING     │  │   PREVIOUS   │          │
│  │              │  │              │  │              │          │
│  │ v1.3.0       │  │ v1.2.0       │  │ v1.1.2       │          │
│  │ (current)    │  │ (shadow)     │  │ (backup)     │          │
│  │              │  │ 5 days old   │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  Performance:      Daily Inferences:    Monthly Cost:           │
│  AUC-ROC: 0.87     45.2K predictions    $1,240 USD              │
│  Accuracy: 0.85    ↑ 5% vs last week    Budget: $2,000          │
│  ▲ +0.02 vs prev   ⚠️  5K errors (0.01%)Budget Alert: ⚠️ 62%   │
│                                                                  │
│  ▼ RECENT ALERTS (Last 7 days)                                  │
│  ═════════════════════════════════════════════════════════════ │
│  ✓ 2024-01-20 10:30  Data drift detected (KS=0.12)   [Resolved]│
│  ⚠️  2024-01-19 14:20  Endpoint latency >2x baseline   [Ignored] │
│  ✓ 2024-01-18 22:15  Auto-retraining completed       [Success] │
│                                                                  │
│  ▼ QUICK LINKS                                                  │
│  ═════════════════════════════════════════════════════════════ │
│                                                                  │
│  📊 [Full Performance Dashboard]  📝 [Model Card]               │
│  🔗 [GitHub Repository]           📋 [Data Contracts]           │
│  🔐 [Model Registry (MLflow)]      ⚙️  [Configuration]           │
│  📈 [Monitoring & Drift Dashboard] ✅ [Approvals & History]     │
│  💰 [Cost Breakdown]               🚀 [Development Templates]   │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Model Performance Dashboard

### Performance Tab (Tabbed Interface)

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  📊 Performance: customer_churn_prediction v1.3.0               │
│                                                                  │
│  TAB: [Overview] [Performance] [Data Quality] [Governance]      │
│                                                                  │
│  Time Range: [Last 24h ▼]  Live Data: [On ▼]                   │
│                                                                  │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  ┌─ Accuracy Over Time ──────────────────────────────────────┐ │
│  │                                                           │ │
│  │   0.88 ┤                         ╱╲                       │ │
│  │   0.86 ┤        ╱╲      ╱╲      ╱  ╲  ╱╲                 │ │
│  │   0.84 ┤  ╱╲   ╱  ╲    ╱  ╲    ╱    ╲╱  ╲        ╱╲     │ │
│  │        ├ ╱──╲─╱────╲──╱────╲──╱──────────╲──────╱──╲────│ │
│  │   0.82 ┤                                  ╲____╱      ╲    │ │
│  │        └───────────────────────────────────────────────── │
│  │              Baseline: 0.85 ────────────────────────────  │ │
│  │                                                           │ │
│  │  Current: 0.87 [▲ +0.02] vs Baseline                     │ │
│  │  Trend: Stable (no drift detected)                       │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  ┌─ Inference Volume ────────────────────────────────────────┐ │
│  │                                                           │ │
│  │  Current QPS: 12.5 (target: 10)                          │ │
│  │  Daily predictions: 45.2K  ↑ 5% vs last week            │ │
│  │  Error rate: 0.01% (45 errors)                           │ │
│  │                                                           │ │
│  │  Latency (ms):     p50: 42ms   p95: 156ms   p99: 298ms   │ │
│  │  Target latency:   p95 ≤ 500ms   ✓ PASS                  │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  ┌─ Fairness Metrics ────────────────────────────────────────┐ │
│  │                                                           │ │
│  │  Demographic Parity (age):      8.2% disparity ✓ PASS    │ │
│  │  Equalized Odds (gender):       4.1% disparity ✓ PASS    │ │
│  │  Calibration (overall):         0.03 error   ✓ PASS      │ │
│  │                                                           │ │
│  │  Last test: 2024-01-20 08:00   [Full Report]             │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Data Quality Tab

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  🔍 Data Quality: customer_churn_prediction                      │
│                                                                  │
│  TAB: [Overview] [Performance] [Data Quality] [Governance]      │
│                                                                  │
│  Time Range: [Last 7d ▼]                                        │
│                                                                  │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  Overall Quality Score: 0.97 (Excellent)                        │
│  ├─ Training Data:   0.98                                       │
│  ├─ Inference Data:  0.96 (⚠️  slightly lower)                 │
│  └─ Monitoring:      Data quality assessed 48 times             │
│                                                                  │
│  ┌─ Column Quality Scores ───────────────────────────────────┐ │
│  │                                                           │ │
│  │  Column Name              Score   Status   Issues        │ │
│  │  ─────────────────────────────────────────────────────── │ │
│  │  customer_id              1.00    ✓ OK    None           │ │
│  │  age                      0.98    ✓ OK    5 nulls        │ │
│  │  purchase_frequency_30d   0.95    ⚠️ OK   12 outliers    │ │
│  │  contract_length          0.92    ⚠️ OK   28 nulls       │ │
│  │  monthly_charges          0.89    🔴 LOW  156 outliers   │ │
│  │                                                           │ │
│  │  [Show all 47 columns]                                    │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  ┌─ Data Drift Detection ────────────────────────────────────┐ │
│  │                                                           │ │
│  │  Field                Drift Status    KS Statistic       │ │
│  │  ─────────────────────────────────────────────────────── │ │
│  │  age                  ✓ No drift      0.06              │ │
│  │  purchase_frequency   ✓ No drift      0.08              │ │
│  │  contract_length      ⚠️ Possible drift 0.15            │ │
│  │  monthly_charges      🔴 DRIFT DETECTED 0.22             │ │
│  │                                                           │ │
│  │  Threshold: 0.1   Last check: 2024-01-20 08:00          │ │
│  │  Recommendation: Review monthly_charges distribution    │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Approval Center

### Pending Approvals

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ✅ Approvals Center                                             │
│                                                                  │
│  Filter: [All ▼] [Pending ▼] [My Role: Legal Reviewer]        │
│                                                                  │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  PENDING APPROVALS (3)                                          │
│                                                                  │
│  ┌─ customer_churn_v1.4.0 → Production ─────────────────────┐ │
│  │ APPROVAL: Fairness Review (Legal)                        │ │
│  │                                                          │ │
│  │ Status: Waiting for 1 approval                           │ │
│  │ ├─ Code Review (2/2 approved) ✓                         │ │
│  │ ├─ Fairness Review (0/1 approved) ⏳                     │ │
│  │ ├─ Business Approval (1/1 approved) ✓                   │ │
│  │                                                          │ │
│  │ [Review & Approve]  [Request Info]  [Reject]            │ │
│  │                                                          │ │
│  └──────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  ┌─ inventory_forecast_v2.1.0 → Staging ──────────────────────┐ │
│  │ APPROVAL: Code Review                                      │ │
│  │                                                            │ │
│  │ Status: Waiting for 2 approvals                            │ │
│  │ ├─ Code Review (1/2 approved) ⏳                           │ │
│  │                                                            │ │
│  │ [Review & Approve]  [Request Info]                         │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  COMPLETED APPROVALS (Last 7 days)                              │
│                                                                  │
│  ✓ 2024-01-20  customer_churn_v1.3.0 → Production               │
│    Legal: Approved by diana@acme.com                           │
│    Business: Approved by eve@acme.com                          │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Approval Detail

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ✅ Review & Approve: Fairness Review                            │
│  customer_churn_prediction v1.4.0 → Production                  │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  📋 MODEL INFORMATION                                            │
│  ─────────────────────────────────────────────────────────────  │
│  Owner: alice@acme.com | Team: Retention | Version: 1.4.0      │
│                                                                  │
│  📊 FAIRNESS TEST RESULTS                                        │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Protected Attributes: age, gender                              │
│  Framework: aif360                                              │
│  Test Date: 2024-01-20 08:00                                   │
│                                                                  │
│  ✓ Demographic Parity                                           │
│    └─ age: 8.5% disparity (threshold: 10%) ✓ PASS             │
│    └─ gender: 7.2% disparity (threshold: 10%) ✓ PASS          │
│                                                                  │
│  ✓ Equalized Odds                                               │
│    └─ age TPR diff: 3.8% ✓ PASS                               │
│    └─ gender TPR diff: 2.9% ✓ PASS                            │
│                                                                  │
│  ✓ Calibration                                                  │
│    └─ Overall calibration error: 0.032 ✓ PASS                 │
│                                                                  │
│  📄 DATA QUALITY                                                 │
│  ─────────────────────────────────────────────────────────────  │
│  Training Data Quality: 0.98 (excellent)                        │
│  No concerning PII exposure detected                            │
│  All required fields passing validation                         │
│                                                                  │
│  ✅ GOVERNANCE CHECKLIST                                        │
│  ─────────────────────────────────────────────────────────────  │
│  [✓] Model card complete                                        │
│  [✓] Fairness tests passing                                    │
│  [✓] Data lineage documented                                   │
│  [✓] Audit logging enabled                                     │
│                                                                  │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  YOUR DECISION:                                                 │
│                                                                  │
│  ○ ✓ Approve                                                   │
│  ○ 🔄 Request Changes                                          │
│  ○ ✗ Reject                                                    │
│                                                                  │
│  Comments (required):                                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Fairness tests pass regulatory requirements. No         │   │
│  │ discriminatory bias detected in either demographic      │   │
│  │ group. Ready for production deployment from legal       │   │
│  │ perspective.                                           │   │
│  │                                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                      [Submit Decision] [Cancel]                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Development Templates

### Template Selection & Quickstart

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  🚀 Development Templates: customer_churn_prediction             │
│                                                                  │
│  Your GitHub repository is ready. Choose your development       │
│  environment and get started:                                   │
│                                                                  │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  ┌─ Databricks Notebooks (Recommended) ─────────────────────┐ │
│  │                                                          │ │
│  │  ✓ Pre-configured with MLflow tracking                  │ │
│  │  ✓ Access to cluster compute                            │ │
│  │  ✓ UC and Delta Lake integration                        │ │
│  │  ✓ Integrated approval workflow                         │ │
│  │                                                          │ │
│  │  [01_EDA.ipynb]      - Exploratory Data Analysis        │ │
│  │  [02_Feature_Eng.ipynb] - Feature Engineering          │ │
│  │  [03_Train.ipynb]    - Model Training                  │ │
│  │  [04_Evaluate.ipynb] - Validation & Fairness Tests     │ │
│  │                                                          │ │
│  │  [Open in Databricks]                                   │ │
│  │                                                          │ │
│  └──────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  ┌─ VS Code / Local Development ──────────────────────────────┐ │
│  │                                                            │ │
│  │  ✓ Full .devcontainer.json setup                          │ │
│  │  ✓ All dependencies pre-configured                        │ │
│  │  ✓ Makefile for common tasks                             │ │
│  │  ✓ Pre-commit hooks (linting, formatting)                │ │
│  │                                                            │ │
│  │  Requirements.txt generated with pinned versions          │ │
│  │  MLflow configured to connect to workspace               │ │
│  │  Git hooks configured for validation                     │ │
│  │                                                            │ │
│  │  Quick Start:                                             │ │
│  │  $ git clone https://github.com/acme-mlops/...            │ │
│  │  $ code .                                                 │ │
│  │  $ make setup                                              │ │
│  │  $ make train-local                                        │ │
│  │                                                            │ │
│  │  [Clone Repository]  [View README]  [View Makefile]       │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  QUICK REFERENCE:                                               │
│  ─────────────────────────────────────────────────────────────  │
│  Repository: github.com/acme-mlops/customer_churn_prediction   │
│  Branch: main (PR-only workflow)                               │
│  Cluster: dev-compute (pre-configured)                         │
│  MLflow Experiment: /Models/customer_churn_prediction          │
│                                                                  │
│  Key Files:                                                      │
│  └─ src/train.py (main training script, skeleton provided)     │
│  └─ src/evaluate.py (fairness + performance tests)             │
│  └─ requirements.txt (all dependencies)                        │
│  └─ .devcontainer.json (VS Code container)                     │
│  └─ Makefile (common tasks: train, test, lint, etc.)           │
│  └─ README.md (comprehensive project guide)                    │
│                                                                  │
│  NEXT STEPS:                                                     │
│  ─────────────────────────────────────────────────────────────  │
│  1. Clone the repo and open in your preferred environment      │
│  2. Read README.md for project structure and guidelines        │
│  3. Implement your training logic in src/train.py             │
│  4. Add unit tests in tests/unit/                              │
│  5. Create a feature branch and submit a PR                    │
│  6. CI/CD will automatically run linting & model validation    │
│                                                                  │
│  [← Back to Dashboard]                                          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Monitoring & Drift Dashboard

### Drift Monitoring

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  🔔 Monitoring & Drift Detection                                 │
│                                                                  │
│  Filter: [All Models ▼] [Last 7d ▼]                            │
│                                                                  │
│  ════════════════════════════════════════════════════════════  │
│                                                                  │
│  customer_churn_prediction (v1.3.0)                             │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  ┌─ Data Drift by Feature ───────────────────────────────────┐ │
│  │                                                           │ │
│  │  Feature              Drift?  KS Stat  Severity  Action   │ │
│  │  ─────────────────────────────────────────────────────── │ │
│  │  age                  ✓       0.06     None     Monitor  │ │
│  │  purchase_freq        ✓       0.08     None     Monitor  │ │
│  │  contract_length      ⚠️      0.15     Medium   Monitor  │ │
│  │  monthly_charges      ✗       0.22     High     🔴 Alert │ │
│  │  tenure_months        ✓       0.05     None     Monitor  │ │
│  │                                                           │ │
│  │  Threshold: 0.1   Checked: Every 1 hour                   │ │
│  │  Last Check: 2024-01-20 08:00                             │ │
│  │                                                           │ │
│  └───────────────────────────────────────────────────────── ┘ │
│                                                                  │
│  🔴 ALERT: Drift Detected in monthly_charges                    │
│                                                                  │
│  Details:                                                        │
│  ├─ Field: monthly_charges (input feature)                     │
│  ├─ Drift Type: Data Distribution Shift                        │
│  ├─ Detected: 2024-01-20 08:00                                │
│  ├─ Severity: High (KS=0.22 > threshold 0.1)                 │
│  │                                                             │
│  └─ Comparison:                                                 │
│     Baseline Mean: $65.42  → Current Mean: $72.18 (+9.4%)     │
│     Baseline Std:  $25.10  → Current Std:  $31.50 (+25.5%)    │
│                                                                 │
│  Recommended Actions:                                           │
│  ☐ Investigate root cause (pricing change? seasonality?)       │
│  ☐ [Trigger Retraining Now]                                    │
│  ☐ [Acknowledge & Monitor]                                     │
│  ☐ [Ignore (requires approval)]                                │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Design Principles

These wireframes follow Apple-like design principles:

1. **Simplicity**: Minimal UI elements, lots of whitespace
2. **Progressive Disclosure**: Details hidden until needed, collapsible sections
3. **Clear Hierarchy**: Important info prominent, less important info accessible
4. **Consistent Layout**: Same patterns across screens
5. **Helpful Language**: Tooltips on hover, contextual help
6. **Friendly Defaults**: Most configurations pre-filled, DS overrides as needed
7. **Beautiful Typography**: Clear labels, good contrast
8. **Task-Focused**: Each screen has a single primary purpose
9. **Reassuring Status**: Visual indicators (✓, ⚠️, 🔴) convey status instantly

---

## Implementation Notes

**Colors & Styling**:
- ✓ Green: Success, pass, approved
- ⚠️ Orange/Yellow: Warning, possible issue, attention needed
- 🔴 Red: Critical, failure, action required
- 🟢 Live status: Green dot for active/running
- ⏳ Gray: Pending, waiting for approval

**Interactions**:
- Collapsible sections default to collapsed if all defaults valid
- Hover shows help tooltips on all fields
- Inline validation (red text under field)
- Expandable rows for detailed views
- Modal dialogs for approvals and confirmations

**Responsive Design**:
- Wireframes shown for desktop (1400px+)
- Mobile view: Stacked layout, simplified tables
- Tablet: Intermediate between mobile and desktop

