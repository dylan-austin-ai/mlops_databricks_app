# MLOps Databricks App — Project Status

**Last updated:** 2026-06-15

---

## What the app is

A Streamlit multi-page governance wizard that guides a data scientist through creating an ML project on Databricks. Covers naming, model specs, data governance, fairness testing, deployment strategy, monitoring, and multi-party approvals with full audit trail.

---

## Pages

| Page | Status | Description |
|------|--------|-------------|
| `01_projects.py` | ✅ Done | Card grid of all projects, status filter, New Project button above filter |
| `02_new_project.py` | ✅ Done | 7-step wizard (2,126 lines) |
| `03_approvals.py` | ✅ Done | Pending approval queue UI — no write path yet (see gaps) |
| `04_monitoring.py` | ✅ Done | Global monitoring overview |
| `05_settings.py` | ✅ Done | Databricks/GitHub connection config |
| `06_project_dashboard.py` | ✅ Done | Per-project dashboard: overview, config, governance, drift monitoring, explainability (SHAP/LIME) |
| `07_data_contracts.py` | ✅ Done | Data contract editor |

---

## 7-step wizard — step detail

| Step | Feature | Status |
|------|---------|--------|
| 1 — Basic Info | Model name auto-sanitizes live on change ("I'm testing this" → `im_testing_this`) | ✅ |
| | Team dropdown loaded from Databricks; falls back to free-text input | ✅ |
| 2 — Model Specs | Frequency-driven cron builder reacts when batch frequency changes | ✅ |
| | Frequencies: hourly / daily / weekdays / weekly / monthly / quarterly / custom | ✅ |
| | Custom cron alignment fixed (removed `help=` tooltip that caused widget offset) | ✅ |
| 3 — Data Specs | Schema inference button — queries Unity Catalog, populates column selectors | ✅ |
| | LLM PII column scan — conservative, flags anything suspicious | ✅ |
| | Column-level data classification (not dataset-level); LLM auto-scan available | ✅ |
| | Dataset classification auto-computes to most restricted column in set | ✅ |
| | PII suppression: multiselect (Delta mask default); blocks Next until justification + suppression filled | ✅ |
| 4 — Governance | Per-protected-attribute justification block for each selected protected class | ✅ |
| | Proxy variable "protected class" field is multiselect (one column can proxy for multiple classes) | ✅ |
| | LLM scan button auto-suggests proxy variables from feature list + declared protected classes | ✅ |
| | DQ gates: two-box reconciliation UI — all columns shown, click ✕ to move between Required / Acceptable | ✅ |
| 5 — Deployment | Per-trigger rollback config (⚙ button per trigger opens threshold controls) | ✅ |
| | Shadow production indefinitely option — model never graduates to canary | ✅ |
| | Drift threshold help text: perf drift = degradation-only vs labeled window; input drift = PSI/KS per field | ✅ |
| 6 — Monitoring | Performance metric is multiselect; per-metric alert threshold configurable | ✅ |
| 7 — Approval Gates | Legal, compliance, internal audit sign-off with contact emails | ✅ |
| | SHA-256 manifest hash ties every approver to the exact config version they reviewed | ✅ |

---

## Services

| Service | Description |
|---------|-------------|
| `services/interview_service.py` | Pydantic v2 models for all 7 steps; step-level validation |
| `services/state_service.py` | Databricks SQL CRUD for project configs; stores manifest hash alongside responses |
| `services/generator_service.py` | Scaffold → GitHub repo push; UC schemas (dev/staging/prod); MLflow experiment; secret scope; CI/CD change-scope script injected into scaffold; `.mlops/approval_record.json` with per-approver manifest hash |
| `services/ai_service.py` | LLM calls via Databricks Model Serving REST API; PII check, column classification, SHAP/LIME interpretation |
| `services/db_service.py` | UC schema inference, org teams, drift log queries, baseline stats |

---

## Infrastructure wired up per project on creation

- **GitHub repo** — CookieCutter-style scaffold pushed; branch protection set (required reviews = code_review_count)
- **Unity Catalog schemas** — `{catalog}.{project}_dev`, `_staging`, `_prod`
- **MLflow experiment** — created at `/Shared/mlops/{project_name}`
- **Secret scope** — `mlops-{project_name}`
- **CI/CD change scope** — `scripts/check_change_scope.py` in scaffold; classifies bug-fix vs substantive change; substantive changes emit a re-approval request with diff against last approved git SHA
- **Approval versioning** — `.mlops/manifest_hash.txt` (SHA-256 of canonical wizard responses); `.mlops/approval_record.json` names every required approver tied to that hash

---

## Tests

82 passing — cover all Pydantic step models, step-level validation, and generator service.

```
python3 -m pytest tests/
```

---

## Known gaps / next work

1. **American English audit** — UI text not systematically reviewed; a few British spellings may remain.
2. **Framework/protected-attribute dropdown top-alignment** — CSS fix needed for multiselect widgets rendered inside `st.columns`; they currently don't align to the top of their column when another column has more content.
3. **`databricks_mlops` package** — `generator_service.py` imports `databricks_mlops.generation.project_generator` for scaffold generation. If that package isn't installed the scaffold step fails gracefully (status = "failed") but there is no built-in template fallback. Needs either a bundled Jinja2 template system or a pre-install check in settings.
4. **Approval write path** — `03_approvals.py` shows pending approvals but there is no path to write an approval back to `.mlops/approval_record.json` or the Databricks state table from the app. This is the next logical workflow to build.
5. **Dashboard empty state** — `06_project_dashboard.py` drift and explainability tabs read from Databricks tables (`monitoring_baseline`, `monitoring_drift_log`) that only exist after a model has run. New projects show an error; needs a friendly empty state.
6. **Column-level classification attestation storage** — attestations are stored in session state during the wizard but need to be persisted to the project config table on save.

---

## Running the app

```bash
cd ~/ai/mlops_databricks_app
# Requires .env with: DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID
# Optional: GITHUB_TOKEN, GITHUB_ORG, LLM_ENDPOINT_NAME (defaults to databricks-meta-llama-3-1-70b-instruct)
python3 -m streamlit run app.py
```

If you get a permissions error on the streamlit binary:
```bash
chmod +x ~/.local/bin/streamlit
python3 -m streamlit run app.py
```
