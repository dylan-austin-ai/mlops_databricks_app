# MLOps Databricks App — Project Status

**Last updated:** 2026-07-07 (second session)

---

## 2026-07-07 second session — live verification DONE, owner decisions executed

**Live verification backlog cleared** (the workspace's serverless capacity
freed up mid-day):

- `python -m db.setup` — base schema + **migrations 001–010 applied** against
  `mlops.mlops`. Found + fixed live: the migration runner split SQL on every
  `;`, cutting statements mid-COMMENT-string (003/006/008 affected); splitter
  is now quote/line-comment-aware.
- **Policy packs synced live** to `mlops.policy_packs` (3 tier rows verified).
  Found + fixed live: `StateService._exec` stringified every parameter, so
  `None`/`True` arrived as literal `'None'`/`'True'` strings; params now bind
  NULL and typed BOOLEAN/BIGINT/DOUBLE.
- **Week 1 round-trip proof PASSED** end-to-end on the live workspace:
  generate → validate → plan → deploy → verify (3 jobs + project schema via
  SDK read-back) → destroy.

**Owner decisions (2026-07-07) executed:**

| Decision | What landed |
|----------|-------------|
| Schema-per-project in a configurable catalog (+ managed location, option B) | Templates emit `${var.catalog}.${var.schema}` with a declarative `schemas` resource; `MLOPS_PROJECTS_CATALOG` (+ per-env overrides) and `MLOPS_MANAGED_LOCATION` in config; db.setup passes MANAGED LOCATION when set |
| Canary default = step-6 primary metric + alert threshold | `make_default_canary_check` in `saga_engine.py`; skips (never passes) without config or monitoring rows |
| De novo baseline placeholder 10 days | `portfolio_analytics_service.py` + portfolio page, marked PLACEHOLDER (§26.4) |
| Scaffold cutover to Bundle Service | **Approved — next build session** |
| Org policy pack | `policy_packs/org_pack.yaml.example` drafted (inert until renamed); owner fills tiers/gates |

**Gaps closed:** drift-tab empty state (raw SQL error suppressed on
missing monitoring tables), American English audit (Organisation→Organization
etc.), st.columns top-alignment CSS. Attestation persistence (old gap 6)
verified already wired end-to-end — removed from the gap list.

**258 tests passing.** Remaining §27.2 phases: 10 (unblocked — see below),
12–16.

**Evening additions (owner decisions):**

- **Generic tiering is permanent** — `generic_tiering_v1` is the org's real
  framework, not a placeholder; the org-pack template draft was removed.
- **Fake-data pilot sanctioned** — everything must be demoable on synthetic
  data. `scripts/seed_demo_data.py` seeds a coherent, teardown-able demo
  project (config, tiered governance, model + champion version, approvals
  joined to deployments, performance incl. one degraded blip, 14 days of
  costs, reviewed business-value fn + impact, shared features with
  multi-consumer lineage, a warn-severity revalidation flag, HITL queue,
  reconciliation history) plus a synthetic streaming source
  `{catalog}.demo_streaming.events` with `--tick` simulating the upstream
  producer. Verified live: portfolio speed/reliability/reuse/impact/
  revalidation, policy gate union, and the streaming table all light up.
  `--teardown` removes exactly what seeding created (audit rows kept).
- This **supersedes the phase 10 gate for pilot/demo purposes**: streaming
  builds against the synthetic source; re-verify against a real governed
  stream before production streaming claims (rationale preserved in
  DECISIONS_NEEDED).
- Live-found fix #3 this session: typed INT params — `date_sub()`/
  `make_interval()` reject BIGINT arguments, so small ints now bind as INT.

---

## Phase 11 — Policy packs + risk tiering with revalidation trigger (§20) — DONE 2026-07-07

| What landed | Where |
|-------------|-------|
| Pack YAML loader/validator + sync to `mlops.policy_packs` (one row per pack tier); shipped `generic_tiering_v1` default | `services/policy_pack_service.py`, `policy_packs/generic_tiering.yaml` |
| Risk tier as a required, never-defaulted interview field with mandatory justification (§20.1/§29.3); wizard step 4 UI + assignment on project creation | `services/interview_service.py`, `pages/02_new_project.py` |
| Saga step 1 takes the union of pack-required gates as data (§28) and aborts under a blocking revalidation flag | `services/saga_engine.py` |
| §20.5 revalidation trigger as behavior, not a stub: reconciliation pass compares §7.4 `promoted_timestamp` tags against pack windows, clock resets on cleared re-reviews, unknown provenance fails closed | `services/reconciliation_service.py`, `db/migrations/010_policy_packs.sql` |
| Revalidation = gate re-runs against the live version; flag clears only when every re-run gate approves | `services/policy_pack_service.py` |
| Dashboard "revalidation due" banner + governance-coverage penalty rollup (§14.1) | `pages/06_project_dashboard.py`, `services/portfolio_analytics_service.py` |

**241 tests passing** (was 214). Migration 010 queued behind 001–009.

**Phase 10 (streaming) remains gated** — assessed 2026-07-07: no governed
source stream/table exists in the workspace (only the control plane's own
managed tables), and the decision of record (DECISIONS_NEEDED #6) forbids
synthetic sources. Build order therefore skipped to phase 11 per §27.2's
"sequenced, not scheduled".

**Workspace status changed (2026-07-07):** the org is **no longer cancelled**
— auth, reads, catalog/schema/table listings all work, and resource creation
returns real errors instead of the old "cancelled or is not active" 403.
Two new constraints found:
1. **Serverless capacity:** the SQL warehouse fails to launch with
   `RESOURCE_EXHAUSTED: Cannot create the resource, please try again later`
   (retried for ~2h). Migrations (`python -m db.setup`, now 001–010) and
   `scripts/verify_live_roundtrip.py` stay blocked until a warehouse starts.
2. **Default Storage:** `CREATE CATALOG` via API/SQL requires a
   `MANAGED LOCATION` on this workspace ("Default Storage is enabled in your
   account"); catalog creation otherwise happens via the UI. Affects the
   per-project catalog convention (DECISIONS_NEEDED #2) and any bundle
   template that creates catalogs. The existing `mlops` catalog survived and
   still holds the pre-migration base tables.

---

## Control-plane build (MLOPS_CONTROL_PLANE_DESIGN.md §27.1 MVP + Phase 5) — DONE 2026-07-05

Built per the design doc, one commit per phase (`git log --oneline`):

| Phase | What landed | Where |
|-------|-------------|-------|
| Week 0 | CLI v1.6.0 pinned + §29.1 schema verification: `route_optimized` top-level, `ai_gateway.inference_table_config` sub-fields confirmed live, `continuous` top-level | — |
| Week 1 | Bundle Service: generate/validate/plan/deploy/verify/destroy, JSON plan flow, plan-hash tamper guard, unix→Quartz cron (dow renumbering found via live deploy) | `services/bundle_service.py`, `templates/bundle/` |
| Week 2 | Registry Service: @champion/@challenger alias moves with §7.4 audit tags, rollback from tags, cross-catalog copy; tracked migrations runner | `services/registry_service.py`, `db/migrations/` |
| Week 3 | Approval write-path as single conditional MERGE (replaces racy read-modify-write), Saga Engine with compensations, revocation with segregation of duties | `services/approval_service.py`, `services/saga_engine.py` |
| Week 4 | Label feedback loop: prediction↔label MERGE join, live_accuracy, data-availability retrain trigger | `services/feedback_join_service.py` |
| Phase 5 | Reconciliation Service (aliases + costs) with §21.1 self-monitoring | `services/reconciliation_service.py` |

**Phases 6–9 also done (2026-07-05, same session):**

| Phase | What landed | Where |
|-------|-------------|-------|
| 6 | Lakehouse Monitoring attach/label-upgrade/retire, §25 graceful degradation | `services/monitoring_service.py` |
| 7 | Feature Catalog discovery + breakage-protected contract versioning (consumer acks fail closed) | `services/feature_contract_service.py`, `pages/08_feature_catalog.py` |
| 8 | HITL review queue (decision-IS-NULL MERGE, SLA escalate-never-approve) + explainability sync/async resolver with structural demotion | `services/hitl_review_service.py`, `services/explainability_config.py`, `pages/09_hitl_review.py` |
| 9 | Portfolio Analytics with §14.4 confidence-split impact rollups | `services/portfolio_analytics_service.py`, `pages/10_portfolio_analytics.py` |

**214 tests passing** (was 82). Migrations 001–009 queued for `python -m db.setup`.

Remaining §27.2 phases: 10 streaming (gated on a real governed source —
DECISIONS_NEEDED #6; still no source as of 2026-07-07), ~~11 policy packs +
revalidation trigger~~ (done 2026-07-07), 12 network hardening, 13 capacity
service + control-plane budget, 14 API layer, 15 auth cutover to native Apps
hosting, 16 interview optimizer/telemetry.
See `DECISIONS_NEEDED.md` for owner decisions, several of which gate these.

**⚠ Live verification still pending** (see the 2026-07-07 workspace note at
the top — blocker is now serverless capacity, not account cancellation).
Once a warehouse starts, run:

```bash
python scripts/verify_live_roundtrip.py   # Week 1 round-trip proof
python -m db.setup                        # applies migrations 001–010
```

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
4. ~~**Approval write path**~~ — closed 2026-07-05: concurrency-safe MERGE write-path in `services/approval_service.py`, wired into `03_approvals.py`. (Write-back to `.mlops/approval_record.json` via PR still pending — lands with the saga's CI/CD integration.)
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
