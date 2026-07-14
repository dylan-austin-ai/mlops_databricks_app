# MLOps Control Plane for Databricks

A Streamlit app that runs a data scientist through a governed 7-step wizard
— problem, model specs, data, fairness/governance, deployment, monitoring,
approval gates — and turns the answers into a real, running project: a
GitHub repo, Unity Catalog schemas and Volumes, an MLflow experiment, a
Databricks Asset Bundle with generated training/evaluation/serving code,
CI/CD workflows, and monitoring/alerting wiring. The goal is to take the
infrastructure and administrative overhead off a data scientist's plate so
they can spend their time on the actual modeling problem.

Everything provisions **progressively** as you go through the wizard, not
as one batch at the end — Step 1 creates real infrastructure immediately,
and each later step commits the specific generated files its own answers
affect. A drift guard protects any file you've hand-edited from being
overwritten, and nothing the app creates is ever silently deleted — files
and repos the app no longer thinks are needed get flagged for your review,
never removed automatically.

## What it automates

- **Project scaffolding** — GitHub repo (new or an existing empty one you
  link), Unity Catalog schemas/Volumes, MLflow experiment, CI/CD workflows
- **EDA & feature selection** — a pre-wired Databricks notebook, auto data
  profiling with a downloadable HTML report, Feature Catalog reuse
  suggestions with lineage, org toolkit auto-import
- **Training & evaluation** — real `train.py`/`evaluate.py` matching your
  declared frameworks, fairness tests, and quality gates (not a generic
  stub); optional AutoML baseline and hyperparameter-search accelerants
- **Data reproducibility** — Delta CLONE snapshots of training data,
  independent of the source table's own retention
- **Governance** — fairness/bias testing (AIF360, Fairlearn), risk-tiered
  policy packs, PII handling, multi-party approval gates
- **Deployment** — low-friction dev/QA self-deploy, a gated and
  credentials-aware CI/CD path to prod, non-essential-resource cleanup
- **Monitoring & cost** — drift detection, performance alerts, budget
  alerts, per-project Databricks Budget Policy attribution
- **Lifecycle** — an Activity Log of everything the app has done for a
  project, and MLOps-approval-gated project deletion that preserves your
  data and never touches GitHub without you

## Quickstart

```bash
git clone <this-repo>
cd mlops_databricks_app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in DATABRICKS_HOST / DATABRICKS_TOKEN / DATABRICKS_WAREHOUSE_ID
python -m db.setup
streamlit run app.py
```

Then verify your setup end-to-end with a real demo project:

```bash
python scripts/run_full_demo.py
```

**New to Databricks entirely, or want it hosted inside your workspace
instead of running locally?** See [`HOW_TO_USE.md`](HOW_TO_USE.md) — it
covers brand-new-workspace setup, the full configuration surface, and
deploying as a native Databricks App (`scripts/deploy_app.py`).

## Docs

| Doc | What's in it |
|---|---|
| [`HOW_TO_USE.md`](HOW_TO_USE.md) | The complete step-by-step guide — setup, every wizard step, every platform page, troubleshooting |
| [`PROJECT_STATUS.md`](PROJECT_STATUS.md) | Session-by-session build history and what's been live-verified |
| [`DECISIONS_NEEDED.md`](DECISIONS_NEEDED.md) | Open questions and a record of owner decisions made along the way |
| [`MLOPS_CONTROL_PLANE_DESIGN.md`](MLOPS_CONTROL_PLANE_DESIGN.md) | Architecture and design rationale |
| [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) | Control-plane table reference |

## Bring your own toolkit

Built to be open-sourced and adapted: no org-specific MLOps/DS toolkit is
hardcoded. Drop a YAML file in `toolkits/` (see
`toolkits/org_toolkits.yaml.example`) and generated projects auto-import
your org's own internal packages.

## Tests

```bash
.venv/bin/python -m pytest
```
