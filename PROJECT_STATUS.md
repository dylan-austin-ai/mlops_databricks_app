# MLOps Databricks App — Project Status

**Last updated:** 2026-07-13 (sixth session)

---

## 2026-07-13 sixth session — org-configured toolkit auto-import + EDA scaffold

Grew out of a simulated end-to-end wizard walkthrough with the owner (a P&C
real-time home-risk-at-quote model was used as the running example). The
retrospective at Step 6 surfaced a real gap: everything automated so far is
project *infrastructure* — GitHub repo, UC schemas, MLflow experiment,
Budget Policy, the DAB scaffold — but the actual EDA/feature-selection/
training starting point was a bare `train.py` that immediately
`raise NotImplementedError`. No EDA notebook existed at all.

**Owner's ask:** generate structured `.py`/`.ipynb`-shaped files pre-wired
to Databricks compute, the project's catalog.schema, and MLflow experiment
tracking — plus pre-import each org's own MLOps/DS toolkit(s). Investigated
whether a specific sibling project (`~/ai/mlops_toolkit`, package
`databricks_mlops`) was the intended toolkit — it's real and substantial,
but this *app* already depended on it once (the old scaffold generator) and
deliberately cut that dependency in the 2026-07-07 third session
(`DECISIONS_NEEDED.md` #4, `PROJECT_STATUS.md` gap #3) after finding "no
fallback if missing." Owner's actual direction, given this app will be
open-sourced: **no hardcoded toolkit** — org-configurable, since every
company will bring their own MLOps/DS/other internal packages.

**Design:** mirrors `policy_packs/` exactly — PR-reviewed YAML in a new
`toolkits/` directory is the source of truth, not a wizard field or `.env`
value, and not a DB-synced table (toolkits have no runtime governance
meaning; policy packs need DB sync because the saga/reconciliation services
look them up at runtime, toolkits are pure build-time config read once at
bundle-render time). Ships with zero toolkits configured — no universal
"generic" default makes sense here the way `generic_tiering_v1` did for
risk tiers — only an inert `toolkits/org_toolkits.yaml.example`.

| What | Where |
|------|-------|
| `load_toolkits()` — globs `toolkits/*.y*ml`, validates strictly (fail closed on malformed entries, same posture as `policy_pack_service.load_packs`), no DB/state dependency | `services/toolkit_config_service.py` |
| `templates/bundle/src/eda.py.j2` — Databricks source-format notebook (`# Databricks notebook source` / `# COMMAND ----------` cell markers — git-mergeable, opens natively via Repos; deliberately **not** raw `.ipynb`, which doesn't diff or merge cleanly). Widget-based catalog/schema (an interactive notebook isn't bundle-deployed, so `${var.catalog}` substitution doesn't apply the way it does in `train.py`'s CLI args) defaulting to the project's dev schema. Points at the *same* MLflow experiment path `ProjectInfrastructureGenerator._create_mlflow_experiment()` already creates. Placeholder EDA and feature-selection sections. Always rendered — not inference-type-specific. | `templates/bundle/src/eda.py.j2` |
| Toolkit imports injected into `train.py` and `eda.py` only — deliberately **not** `batch_score.py`/`stream_score.py`, which weren't part of the EDA/feature-selection/training ask | `templates/bundle/src/train.py.j2`, `templates/bundle/src/eda.py.j2` |
| `requirements.txt.j2` — new, **conditionally rendered only when ≥1 toolkit is configured** (no invented baseline dependency-pinning for the zero-toolkit default state) | `templates/bundle/requirements.txt.j2`, wired in `services/bundle_service.py` |

`BundleService.generate()` gained a `toolkits_dir` constructor override (injectable for tests, defaults to the real `toolkits/` directory) — no new required parameter, so every existing caller is unaffected; the default open-source state (only the inert `.example` ships) makes `load_toolkits()` return `[]` everywhere nothing was explicitly configured.

**378 tests passing** (was 355; +23: 15 `test_toolkit_config_service.py`, 8 `test_bundle_service.py`). `ruff check` clean.

**Not done / worth knowing:**
- No live verification that a real `.py`-as-notebook file with `# Databricks notebook source` header actually opens correctly via Databricks Repos in this owner's workspace — the cell-marker format is well-documented and stable, but this project's own convention is "verify live before trusting further," and that hasn't happened yet for this specific file.
- `pip_spec` and `import_statement` are free-text, validated only for non-emptiness — no check that a `pip_spec` is installable or an `import_statement` is syntactically valid Python. A malformed entry fails at `pip install`/import time inside the generated project, not at config-load time. Acceptable for a first pass; worth a lint/dry-run check later if this sees real use.
- Nothing surfaces which toolkits are active anywhere in the app UI (Settings page would be the natural spot) — currently only discoverable by reading `toolkits/*.yaml` directly or opening a generated project.

**Same session, continued — owner request: 5 more "force multiplier" items
from the walkthrough retrospective** (evaluate.py, auto-profile, feature
catalog coercion, real Feature Engineering client integration, AutoML/
hyperparameter search accelerants). Each verified beyond just "renders and
parses" — see the per-item detail below for what was actually executed.

**1. `evaluate.py` — was referenced in 3 places, never generated.**
`interview_service.py`'s Custom-metric label, the Step 6 help text, and
`generator_service.py`'s CI change-scope script (`SUBSTANTIVE_PREFIXES`)
all pointed at `src/evaluate.py` as if it existed; no template rendered it.
New `templates/bundle/src/evaluate.py.j2` generates real, runnable
`compute_performance_metrics()` (only the metrics Step 6 selected —
sklearn), `compute_fairness_metrics()` (real `fairlearn.metrics
.demographic_parity_difference`/`equalized_odds_difference` calls when
`fairlearn` is selected; `aif360` gets an honest scaffold-only comment
since `ClassificationMetric` needs privileged/unprivileged group *values*
per attribute — a policy call this app can't infer, not something to fake),
`enforce_fairness_gate()` (fails closed — raises past the configured
disparity threshold), and `compute_training_explainability()` (§12.1,
SHAP/LIME per `explainability_config.default_method()`). **Verified beyond
rendering**: temporarily installed `fairlearn`, actually imported and
executed the *generated* `evaluate.py` against synthetic data — real
sklearn/fairlearn calls ran, the fairness gate correctly passed on small
synthetic disparity and correctly raised `FairnessGateFailure` on a forced
large one. Uninstalled `fairlearn` again afterward (shared venv with
`mlops_toolkit`, per the existing documented fragility risk — left it as I
found it).

**2. Auto-profile — "I like pandas-profiling's output."** Checked what that
tool is called today rather than trusting training data: it's been renamed
*twice* — pandas-profiling → ydata-profiling (2023) → **fg-data-profiling
(2026-04)**, confirmed live against the current PyPI listing this session.
New `services/data_profiling_service.py` has two deliberately separate
operations: `quick_stats()` (fast SQL aggregate — null%/distinct count per
column, safe to run automatically, feeds a new default-suggestion pass on
Step 4's Data Quality Gates — a column already frequently null in real
sampled data now defaults to "Acceptable" instead of "Required") and
`full_profile()` (the real `fg-data-profiling` HTML report on a capped
sample, explicit opt-in via a new "📊 Profile Data" button in Step 3,
compact summary shown inline, full report offered as an `st.download_button`
HTML file). `fg-data-profiling>=4.18.4` added to `requirements.txt` —
**not yet installed or pip-audited** in this environment; do both before
relying on this feature (CLAUDE.md dependency-security requirement).
Reaching into the report object's internal description/alerts structure
wasn't independently verified, so the compact summary (row/column count,
missing-cells %, duplicate-rows %) is computed directly from the sampled
pandas DataFrame instead — verified pandas calls instead of a guess at
unfamiliar internals.

**Same session, continued — pip install, pip-audit, and live verification.**
`fg-data-profiling` installed and `pip-audit` run clean (no known
vulnerabilities). Installing it downgraded `numpy`/`scipy`/`matplotlib` in
the shared `mlops_toolkit` venv — the previously-documented shared-venv
fragility risk materializing; app's own 411-test suite still passed
afterward. `full_profile()` failed live with `ModuleNotFoundError: No module
named 'pkg_resources'` — `fg-data-profiling` imports it directly but doesn't
declare `setuptools` as a dependency, and `setuptools>=81` dropped the
`pkg_resources` shim. Fixed by pinning `setuptools<81` in `requirements.txt`.
With that fix, `quick_stats()` and `full_profile()` both verified live
against a real table (`mlops.mlops.reconciliation_runs`), and
`FeatureContractService.catalog_search()` (the Step 3 coercion lookup)
verified live against the app's own DB. Submitted a real one-time Databricks
job to verify the two pieces that need Spark/Runtime ML and can't be checked
from this SQL-warehouse-only dev environment: `FeatureLookup` +
`create_training_set()` **passed live** on serverless job compute (exact
generated-code path — a feature table created, joined, returned the correct
4 rows/columns); `automl.classify()` **could not be tested** — the workspace
policy is serverless-only (`InvalidParameterValue: Only serverless compute
is supported in the workspace`) and AutoML classify/regress requires classic
Dedicated-access-mode compute per current docs, so the `automl_baseline.py`
accelerant is a dead end in this specific workspace regardless of how it's
written. Worth surfacing to the data scientist at Step 2 before they check
the AutoML box, not after a failed job run — not yet built.

**Same session, continued — full_profile() report-size fix.** Re-walking
Steps 2–4 against a real synthetic 12-column demo table
(`mlops.mlops.zz_demo_home_risk_training`, live-created for the walkthrough)
surfaced a real problem: `full_profile()` produced a 45MB HTML report and
took 2+ minutes for just 12 columns and 500 rows — almost entirely the
pairwise-interactions scatter matrix, which is ~O(columns²). Owner's call:
sacrifice the scatter matrix (decorative, doesn't scale) rather than the
analytically useful parts. New `MAX_COLUMNS_FOR_INTERACTIONS = 10` constant
in `data_profiling_service.py` — above that column count,
`interactions={"continuous": False}` is passed to `ProfileReport`; narrow
tables are unaffected. Re-verified live against the same table:
**45MB → 1.04MB, 140s+ → 25.7s**, identical core stats (row/column count,
missing-cells %, duplicate-rows %) since those come from the raw DataFrame,
not the interactions section. Two new tests
(`test_narrow_table_keeps_interactions_enabled`,
`test_wide_table_disables_interactions`). **413 tests passing.**

**3. Feature Catalog coercion (Step 3).** A structural nudge, not a hard
block: any selected feature column matching an existing shared Feature
Catalog entry (`FeatureContractService.catalog_search()`, already
existed) now surfaces the match with owner/reuse-count/table, defaults to
"use the established one," and requires a justification to opt for a new
ad-hoc definition instead — same pattern as the PII justification block
already on this step. The resolution (`feature_catalog_resolutions`) is
what item 4 below consumes.

**4. Real Databricks Feature Engineering client integration.** Previously
zero `FeatureLookup`/`create_training_set` usage anywhere — the Feature
Catalog was bookkeeping-only, exactly the gap the IMG_1412 triage flagged.
Confirmed the current API live (`FeatureLookup(table_name=, feature_names=,
lookup_key=)`, `fe.create_training_set(df=, feature_lookups=, label=)`,
`fe.log_model(...)`) rather than trusting the design doc's already-cited
version. `train.py.j2` now generates real `FeatureLookup` blocks grouped by
source table (one lookup per table, not per column) for every feature Step
3 resolved to a shared catalog entry, falling back to a plain `spark.table`
read when none are catalog-backed. `lookup_key` is left as an honest TODO —
the app tracks what a feature *is*, not what entity key joins it to a given
project's training data, and guessing would be worse than asking.
**Found and fixed a real bug while building this**: an early version used
Jinja `{{ catalog }}`/`{{ schema }}` template syntax for the base-table
fallback, but `catalog`/`schema` are Python *runtime function parameters*
of the generated `train()`, not Jinja context variables — this broke
`StrictUndefined` rendering for every existing test until caught by the
regression run and fixed to use a Python f-string instead.

**5. AutoML + hyperparameter search accelerants (§9.5, design-doc-specified,
never built).** Two new optional Step 2 checkboxes, purely additive per the
original spec framing. Confirmed live: `databricks.automl.classify()`/
`.regress()` take `target_col`/`timeout_minutes` (the older `max_trials` is
deprecated/unsupported on current runtimes). New `automl_baseline.py.j2`
routes to `classify` or `regress` based on whether Step 6's selected
performance metrics look like regression (`rmse`/`mae` — same
classification logic `saga_engine.py`'s monitor-attach step already used,
reused rather than reinvented). New `hyperparameter_search.py.j2` has a
real Optuna trial loop + nested-MLflow-run logging + best-trial reporting;
only the model-specific search space and training/scoring body are stubs.
`optuna>=3.6.0` added to `requirements.txt` only when this accelerant is on.

**411 tests passing** (was 378; +33: 12 `test_data_profiling_service.py`,
21 `test_bundle_service.py` across coercion/FE-client/evaluate.py/
accelerant coverage). `ruff check` clean on every touched file.

**Not done / worth knowing:**
- `fg-data-profiling` and `fairlearn`/`aif360`/`optuna` are all *generated-
  project* or *this-app* dependencies that need real installation + a
  `pip-audit` pass before any of items 1/2/5 are actually usable — none of
  that happened this session beyond the temporary, cleaned-up `fairlearn`
  verification install for evaluate.py.
- No live verification against a real Databricks workspace for any of the
  five — `FeatureLookup`/`automl.classify`/`fg-data-profiling`'s Spark
  sampling path all need a real cluster/warehouse to exercise beyond
  template rendering and (for evaluate.py's metrics/fairness logic
  specifically) synthetic-data execution.
- `quick_stats()`'s DQ-gate auto-suggestion only fires if "📊 Profile Data"
  was clicked before reaching Step 4 — there's no prompt nudging a DS who
  skips straight past it, so the manual "Required by default" behavior
  silently remains the norm unless profiling is actually run first.

---

## 2026-07-12 fifth session — closed stale gap-list entries, IMG_1412 triage + build

**Housekeeping first:** `PROJECT_STATUS.md`'s "Known gaps / next work" list
(bottom of this file) still listed the American English audit, the
`st.columns` top-alignment CSS fix, and column-classification attestation
persistence as open — all three were actually closed in the 2026-07-07
second session; the list just never got updated after. Re-verified all
three against the live code (not re-taken on faith) and struck them through
with accurate closure notes. One genuine leftover found during the
re-sweep: `app.py`'s "initialise the schema" caption — fixed to "initialize".

**IMG_1412.txt triage:** the owner's photographed review notes
("Partially Covered Items" / "Not-covered items" / "General strategy") were
transcribed (`IMG_1412.txt`) and triaged against the real code — not the
design doc's claims — via a background fork. Full results in the
conversation; punch list highlights below. Two items were put to the owner
rather than built speculatively — both declined, recorded in
`DECISIONS_NEEDED.md`'s 2026-07-12 section: the RACI/ownership matrix page
(PM's role, not an app feature) and problem intake/prioritization
(reaffirms the design doc's own §1/§30 decision).

**Built, in triage-recommended order:**

| # | What | Where |
|---|------|-------|
| 1 | **Notification Delivery Service** — email (smtplib/SMTP), Slack + Teams (incoming webhooks); admin-set credentials in config, never in a wizard field; unset channel reports `not_configured` rather than failing. Foundational — 3 and 6 below route through it. | `services/notification_service.py` |
| 2 | **`attach_inference_monitor()` wired in** — was built (phase 6) but never called anywhere. Now a best-effort saga step 6.6 (never blocks promotion, same posture as model-card assembly), real-time projects only. `prediction_col`/`problem_type` inferred from the project's performance-metric config; skipped cleanly for batch/streaming. | `services/saga_engine.py` (`attach_default_monitor`) |
| 3 | **`budget_alerts` table wired up** — was defined in schema, read/written nowhere. Wizard step 6 gains an opt-in per-project budget (period/threshold/alert-at-%); `ReconciliationService.reconcile_budget_alerts()` checks rolling-window spend against it, de-duped per period bucket, notifies via #1. | `services/state_service.py`, `pages/02_new_project.py`, `services/reconciliation_service.py`, migration `012_budget_alert_dedup.sql` |
| 4 | **`data_quality_assessments` table wired up** — also defined, never used. New `DataQualityService.run_assessment()` runs the null/uniqueness checks a contract's columns already declare (`quality_rules.null_check`/`uniqueness_check` — the shape `07_data_contracts.py` actually authors, not a bigger unbuilt rules DSL) against the real table, scores it, records PII columns. Surfaced as a "Run quality assessment" action + latest-result summary on the contract page. | `services/data_quality_service.py`, `pages/07_data_contracts.py` |
| 5 | **`cost_rollup()` grouping extended** — by team (join to `projects.team_name`) and deployment type (join to latest `project_configurations.inference_type`), plus the existing project grouping, selectable via a radio in Portfolio Analytics. Environment and per-model slices deliberately **not** built this pass — `system.billing.usage` isn't tagged by environment today (would need bundle-template + `reconcile_costs` changes, not just this query), and `cost_tracking.model_id` is always `'project_scope'` (this app is one model per project), so a "by model" slice would just reproduce "by project". | `services/portfolio_analytics_service.py`, `pages/10_portfolio_analytics.py` |
| 6 | **Notification wiring for alerts/approvals/HITL** — three separate gaps closed: (a) `ReconciliationService.reconcile_performance_alerts()` — a breach was tracked in `model_performance` but `alert_history` was read, never written, and nobody was ever told; reuses the saga's own canary threshold, de-duped 24h per alert. (b) `ApprovalService.request_approval()` — new gates previously had no real call site at all (only `03_approvals.py`'s manual test form called `create_approval_request` directly); now notifies the gate-type's configured contact email from wizard step 7 (`legal_contact_email` etc.), best-effort. (c) `HITLReviewService.escalate_sla_breaches()` — SLA breaches were marked escalated in the DB and nothing else; now notifies the project's configured alert destinations (no dedicated "backup reviewer" field exists in the data model, so this reuses the one "who to tell about an operational problem" concept that does). All three: notification failure never blocks the underlying write. | `services/reconciliation_service.py`, `services/approval_service.py`, `services/hitl_review_service.py`, `pages/03_approvals.py` |

**334 tests passing** (was 290 at the top of this session; +44: 3 saga
monitor-attach, 11 notification service, 7 budget alerts, 8 data quality,
2 cost-rollup grouping, 6 performance alerts, 4 approval notify, 3 HITL
escalation notify). `ruff check` clean on every touched file.

**Not done / worth knowing:**
- `MLOPS_SMTP_*`/`MLOPS_SLACK_WEBHOOK_URL`/`MLOPS_TEAMS_WEBHOOK_URL` are new
  config (see `.env.example`) — all unset in `.env` today, so every
  notification call currently reports `not_configured` rather than actually
  sending until the owner sets real credentials/webhooks.
- `reconcile_performance_alerts()` and `reconcile_budget_alerts()` are wired
  into `ReconciliationService.run_all()` but that's still a method to call
  from a scheduled job — no job scheduler has been wired up in any session
  so far; these run when triggered manually or via whatever calls
  `run_all()`.

**Same session, continued — owner request: attribute cost to a Databricks
Budget Policy per project (with an app-wide default)**

Migration 012 applied live (`python -m db.setup`) — verified via
`DESCRIBE TABLE` that `last_alerted_period`/`last_alerted_timestamp` landed
on `mlops.mlops.budget_alerts`.

The owner's ask was specifically to use Databricks' *native* Budget Policy
feature, not another app-side cost table. Before writing any code, this was
verified live against the actually-installed CLI rather than trusted from
scraped docs (design tenet 8): `databricks bundle schema` (pinned v1.6.0)
confirms `budget_policy_id` is a real, top-level `[Public Preview]` field on
both `resources.jobs.<name>` and `resources.model_serving_endpoints.<name>`.
Databricks' own docs confirm budget policies are **serverless-only** ("do
not apply tags to classic compute resources") — not a blocker, since this
app is already serverless-first (§17.1), but worth knowing if "clusters"
ever means classic compute for a future ask.

Owner explicitly chose the higher-privilege option when asked: the app
**creates and manages** budget policies itself, not just references
pre-existing ones. That requires **account-level** Databricks credentials
(`AccountClient`, OAuth M2M service principal) — a materially different,
higher-privilege credential than the workspace token every other service in
this app has ever needed. Confirmed live (construction reached real OAuth
discovery against `https://.../oidc/accounts/{account_id}/...` before
failing on fake creds) that the auth shape is right; there is no way to
confirm the full create/list round-trip without real account credentials,
which don't exist in this dev environment — **this needs a live check with
real `DATABRICKS_ACCOUNT_*` credentials before the owner relies on it.**

| What | Where |
|------|-------|
| `BudgetPolicyService` — `ensure_policy(name, tags)` idempotent by name (lists and matches client-side; no server-side duplicate-detection API is documented), `ensure_default_policy()` (uses a pre-set `MLOPS_DEFAULT_BUDGET_POLICY_ID` as-is, else ensures a named default). `BudgetPolicyUnavailable` when account credentials aren't configured — same §25 graceful-degradation posture as `MonitoringService` | `services/budget_policy_service.py` |
| Account-level credential config, kept as its own group distinct from the workspace credentials | `config.py` (`databricks_account_*`, `default_budget_policy_id`/`_name`), `.env.example` |
| Per-project `budget_policy_id` persisted on `projects` (mirrors `mlflow_experiment_id`/`secret_scope_name`) | migration `013_project_budget_policy.sql` (applied live), `StateService.update_project_budget_policy` |
| Resolution wired into project creation as a new best-effort step 0 (must run before the bundle renders): wizard override → per-project policy (created/reused) → control-plane default → skipped — never blocks project creation at any layer | `ProjectInfrastructureGenerator._resolve_budget_policy`, `services/generator_service.py` |
| `budget_policy_id` threaded through to the bundle templates, conditional (omitted entirely when unresolved) | `services/bundle_service.py`, `templates/bundle/resources/jobs.yml.j2` (all 4 job defs), `model_serving.yml.j2` |
| Wizard step 6 gains an optional "Budget policy ID" field — blank uses the auto-resolution above | `pages/02_new_project.py` |

**355 tests passing** (was 334; +21: 12 `test_budget_policy_service.py`,
6 `test_generator_service.py`, 3 `test_bundle_service.py`).

**Not done / worth knowing:**
- Zero live verification of the account-level API round-trip (create/list a
  real policy) — no account credentials exist in this environment. First
  live test should be a scratch `ensure_policy()` call against a real
  account, the same "verify before trusting further" pattern this project
  already used for `@champion` alias behavior and the Week 0 schema spike.
- `[Public Preview]` on the Jobs `budget_policy_id` field — re-verify this
  hasn't changed shape before leaning on it for anything contractual.
- No UI surfaces the *resolved* per-project policy anywhere yet (e.g. the
  project dashboard) — it's only visible via `projects.budget_policy_id` or
  the generation-step log at creation time.
- `ensure_policy()`'s idempotent-by-name lookup lists *all* account budget
  policies on every call — fine at today's scale (one call per project
  creation), worth revisiting if the account accumulates hundreds of
  policies.

---

## 2026-07-08 fourth session (continued) — deployed as a native Databricks App

Owner asked to test the app hosted inside their own Databricks account, not
just run locally against it. This is real new ground (design roadmap phase
15, "auth cutover to native Databricks App hosting," §23) — scoped down
deliberately: this deploys today's PAT-based app onto native Apps hosting
as-is, **not** the full OAuth-passthrough-per-user auth model §23 describes.
That fuller cutover (per-user SSO identity → per-user UC permissions) is
still open and still gated on real multi-user need; this is a single-owner
test deployment.

What shipped:
- Secret scope `mlops_app_secrets` (workspace-level, via SDK — never via CLI
  args, so tokens never touched bash history) holding `databricks_token` and
  `github_token`.
- `app.yaml` — `command: ['streamlit', 'run', 'app.py']`; non-secret config
  (`DATABRICKS_HOST`, `DATABRICKS_WAREHOUSE_ID`, `MLOPS_CATALOG`,
  `MLOPS_SCHEMA`, empty `GITHUB_ORG`) as plain `value`s; both tokens bound via
  `valueFrom` to the secret-scope resources — no plaintext secret anywhere in
  a file. Verified against current Databricks docs and the installed SDK's
  `apps.AppResourceSecret`/`AppResource` schema directly (not assumed from
  training data — the design doc's own stale `databricks apps publish
  --workspace-url` example in `DATABRICKS_MLOPS_APP_SPECIFICATION.md` doesn't
  match the current CLI at all, confirming why).
- App `mlops-databricks-app` created via SDK with both secrets attached as
  `AppResource` entries (READ permission).
- Source synced to
  `/Workspace/Users/dylan.austin.ai@gmail.com/mlops-databricks-app` via
  `databricks sync --exclude-from .gitignore --exclude .git` — dry-run
  checked first to confirm `.env` was excluded before the real upload (it
  was; only `.env.example` went up).
- Deployed (`w.apps.deploy_and_wait`) — **SUCCEEDED**, app RUNNING, compute
  ACTIVE, URL responds 200: `https://mlops-databricks-app-7474651926930548.aws.databricksapps.com`

**Not done / worth knowing:**
- No code changes were needed — `config.py`'s existing `load_dotenv()` +
  `os.getenv()` pattern reads Apps-injected env vars identically to a local
  `.env`, and the services still construct `WorkspaceClient(host=, token=)`
  explicitly rather than relying on Apps' own auto-injected OAuth identity —
  this is the PAT-based interim, not the §23 end-state.
- Redeploying after further code changes means re-running `databricks sync`
  + `w.apps.deploy_and_wait` (or the CLI `databricks apps deploy` equivalent)
  — no CI/CD or auto-redeploy-on-push is wired up.
- `app.yaml` has no secrets in it and is safe to commit if the owner wants
  it tracked (currently untracked, like `db/migrations/011_*.sql` etc. from
  earlier this session).

---

Per DECISIONS_NEEDED's owner-approved build order (2026-07-07 evening), phase
13 next: **Capacity Service and control-plane budget (§17.4, §19.2)**.

- `services/capacity_service.py` — new service, sibling to (not merged into)
  ReconciliationService per §27.2's "run alongside" framing:
  - `snapshot_capacity()` — counts workspace-wide jobs/serving
    endpoints/concurrent runs via the SDK, compares endpoint count against
    `MLOPS_CAPACITY_ENDPOINT_WARN_THRESHOLD` (default 50, §19.2 — no
    published per-workspace ceiling, so this is an internally-set alert, not
    a discovered limit), writes a row to `capacity_snapshots`. Write path,
    meant for the scheduled-job pattern like reconciliation.
  - `latest_capacity_snapshot()` — cheap read of the most recent row, for
    Portfolio Analytics to render without hitting the Jobs/Serving Endpoints
    APIs on every page load.
  - `reconcile_control_plane_cost()` — MERGEs `system.billing.usage` tagged
    `component=control_plane` into `control_plane_costs`, dated and keyed
    like `ReconciliationService.reconcile_costs`'s per-project MERGE, but
    kept structurally separate from `mlops.cost_tracking` (§17.4 — the
    control plane's own overhead shouldn't hide inside a project's bill).
  - `control_plane_budget_status()` — reads the rolled-up cost and compares
    to `MLOPS_CONTROL_PLANE_BUDGET_WARN`/`_CRIT` (owner-approved placeholder
    defaults $50/$100 per month, DECISIONS_NEEDED #3, evening 2026-07-07);
    returned status carries `is_placeholder=True` so callers never present
    the threshold as a real number.
- Migration `011_capacity_and_control_plane_budget.sql` — `capacity_snapshots`
  + `control_plane_costs` tables, same shape/conventions as
  `006_reconciliation_runs.sql`.
- `config.py` gains the three env-driven fields above.
- Portfolio Analytics page (`pages/10_portfolio_analytics.py`) gains a
  "Workspace capacity & control-plane budget" section: endpoint count vs.
  threshold with a warning banner at/over threshold, and control-plane
  30-day cost vs. warn/crit with the PLACEHOLDER caveat surfaced inline.
**290 tests passing** (was 277; +10 `test_capacity_service.py` — threshold
boundaries, empty-state reads, MERGE tagging, budget status tiers; +3
`test_generator_service.py` — GitHub owner resolution, see below).

**Deferred, not built this session** (§19.2 item 3): the documented
single→multi-workspace "graduation" playbook. The design calls for writing
it "now, not improvised under pressure later," but no capacity pressure
exists yet to motivate it and it's a doc, not code — revisit once the
Capacity Service's own snapshots show sustained pressure, or on request.

**Live-verified against the owner's personal workspace** after a credential
gap was found and the owner restored `.env` (see incident note below):
`db.setup` applied migration 011 cleanly (`capacity_snapshots` +
`control_plane_costs` created, migrations 001–010 correctly skipped as
already-applied). `CapacityService.snapshot_capacity()` ran for real:
0 jobs, **15 serving endpoints** (ok, under the 50 warn threshold), 0
concurrent runs, row written. `reconcile_control_plane_cost()` ran the live
MERGE against `system.billing.usage`/`list_prices` — 0 rows changed, expected
since no resource is yet tagged `component=control_plane` (same cold-start
shape as `reconcile_costs` before any project-tagged spend exists).
`control_plane_budget_status()` read back correctly: $0.00, ok,
`is_placeholder=True`.

**GitHub personal-account fix (found while restoring live credentials):**
`_create_github_repo` unconditionally called `gh.get_organization(GITHUB_ORG)`
— GitHub's API has no "organization" for a personal account, so this would
404 for anyone without an org, and `generate()` additionally required
`GITHUB_ORG` truthy just to attempt the step at all, skipping repo creation
outright for personal-account users. Fixed: `GITHUB_ORG` is now optional —
unset, `_create_github_repo` resolves the owner via `gh.get_user()` (the
authenticated user) instead of `gh.get_organization()`; `generate()`'s gate
now only requires `GITHUB_TOKEN`. Verified live: the owner's `GITHUB_TOKEN`
resolves to `dylan-austin-ai` (type `User`), confirming the fallback path is
exactly what their setup needs. `.env`'s `GITHUB_ORG` set to empty. **+3
tests** in `test_generator_service.py::TestGithubRepoOwnerResolution`
(org path, personal-account fallback, `generate()`'s gate no longer requiring
org).

**Incident note — credential gap found and resolved this session:** partway
through this session, `.env`'s `DATABRICKS_HOST`/`DATABRICKS_TOKEN`/
`DATABRICKS_WAREHOUSE_ID`/`GITHUB_TOKEN` were found reverted to
`.env.example`'s literal placeholder values, and the project's shared `.venv`
(a symlink to `../mlops_toolkit/.venv`) was separately found missing
`pytest`. Neither was a change made by this session's tooling. `.env` is
git-ignored (no history to recover from); root cause of the reset is unknown.
The owner restored real credentials by hand; `pytest` was reinstalled into
the shared venv (not pinned in either project's `requirements.txt` — it was
present ad hoc before, so its disappearance tracks with a from-scratch env
rebuild). **Open risk, not investigated further this session:** the shared
venv between `mlops_databricks_app` and `mlops_toolkit` means dependency
changes in one project can silently affect the other's test tooling — worth
a look if this recurs.

---

## 2026-07-07 third session — scaffold cutover to Bundle Service — DONE

Wizard scaffold path (DECISIONS_NEEDED #4, approved 2026-07-07) cut over:

- `_scaffold_code` now renders projects via `BundleService.generate()` (the
  same Jinja2 templates as the round-trip-verified bundles) instead of the
  external `databricks_mlops` package — **gap #3 closed**; projects created
  through the wizard now get real deployable bundles.
- `.mlops/` platform files unchanged; the scaffold is git-initialized on
  `main` with an initial commit (`--no-verify` — host commit-msg hooks must
  not gate machine-generated scaffold commits) so the GitHub push step
  still works.
- **Latent bug exposed + fixed:** `_check_scope_script`'s outer f-string left
  the generated script's own placeholders unescaped (`{PROJECT_NAME}`,
  `{manifest_hash}`, `{len(changed)}`, …) → NameError at scaffold time. Never
  seen before because the old path always failed at the `databricks_mlops`
  import before reaching it. A test now `compile()`s the generated script.
- GitHub/UC/MLflow/secret-scope steps untouched, per the decision.

**264 tests passing** (was 259; +5 scaffold tests: real template render,
serving variant, .mlops files + script compile, git init, failure path).

**Evening (same session) — owner approved all six punch-list decisions;
phase 10 built + two live verifications:**

- **Phase 10 (streaming) DONE** — the gap was wizard-side only (bundle layer
  was already streaming-ready): step 2 gains the `streaming` inference type
  with a required, three-part-validated `streaming_source_table`; §9.4
  boundary in the help text. **Live round-trip passed**
  (`scripts/verify_live_streaming.py`): synthetic-source precheck → generate →
  validate → plan → deploy → SDK read-back incl. continuous-trigger
  confirmation (UNPAUSED) → destroy. Synthetic-source caveat stands: re-verify
  against a real governed stream before production streaming claims.
- **DECISIONS #3 RESOLVED — `@champion` is numeric-only.** Owner-approved
  scratch probe (`scripts/verify_champion_alias.py`): the serving API rejects
  aliases in `entity_version` ("Entity version must be a number").
  Consequence implemented: saga step 6 updates the endpoint's champion entity
  to the numeric candidate version after the alias move
  (`RegistryService.update_champion_serving_version`), champion re-point
  compensation on failure, skipped for projects without an endpoint.
- **Live-found fix #4:** MLflow does not create parent workspace directories —
  `/Shared/mlops` missing made `create_experiment` 404; generator's MLflow
  step now `mkdirs` first.
- Remaining §27.2 order per owner decision: phase 13 next; 12/14/15 deferred
  to their trigger events; quota conversation deferred.

**277 tests passing** (+4 interview streaming validation, +1 streaming
scaffold, +4 registry endpoint-version, +4 saga endpoint-update).

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

Remaining §27.2 phases: ~~10 streaming~~ (done 2026-07-07 evening, against
the sanctioned synthetic source), ~~11 policy packs + revalidation trigger~~
(done 2026-07-07), 13 capacity service + control-plane budget (**next**, per
owner decision), 12 network hardening / 14 API layer / 15 auth cutover
(deferred to their trigger events), 16 interview optimizer/telemetry.
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
| `services/generator_service.py` | Bundle scaffold via `BundleService.generate()` → git init → GitHub repo push; UC schemas (dev/staging/prod); MLflow experiment; secret scope; CI/CD change-scope script injected into scaffold; `.mlops/approval_record.json` with per-approver manifest hash |
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

411 passing — cover all services, Pydantic step models, step-level
validation, and the generator.

Run with the project venv — the system `python3` fails test collection
(cross-test imports like `from tests.test_approval_service import ...` don't
resolve outside `.venv`):

```
.venv/bin/python -m pytest tests/
```

---

## Same session, continued — agile/progressive provisioning (owner request 2026-07-13)

Grew out of the demo walkthrough retrospective on sequencing: the owner
wanted infrastructure to fire "as they progress" (agile) instead of one
waterfall `_create_project()` call after all 7 wizard steps + Review
(waterfall). Full rundown of proposed trigger points was reviewed and
approved with six specific corrections/decisions before building:

1. `eda.py` renders at Step 1 (only needs catalog/schema, already true) but
   the DS may not touch it for days/weeks — no change needed, just a
   workflow-expectation alignment.
2. Secret scope creation questioned ("what is it doing?") — traced every
   reference, found **zero consumers**. Removed from eager Step 1
   provisioning entirely; stays available for whenever a real consumer
   exists (none does yet).
3. Training data needs versioning for later faithful reproduction — new
   Delta **DEEP CLONE** snapshot mechanism (not SHALLOW — survives the
   source table's own VACUUM/retention).
4. Low-friction dev/QA self-deploy, friction reserved for prod via CI/CD —
   new `deploy_dev.yml.j2` (no gate) / `deploy_prod.yml.j2` (gated) +
   a QA/dev reaper to prevent prod inheriting exploration clutter.
5. Non-prod catalog convention: **shared non-prod catalog, per-project
   schema** (not one shared schema for all projects) — `_create_uc_schemas`
   was hardcoding `cfg.catalog` for all three envs despite
   `projects_catalog_for()` already existing and already being used
   correctly in `bundle_service.py`'s `databricks.yml.j2` rendering; this
   was a real pre-existing inconsistency, now fixed.
6. Project name gets locked (with a visible "🔒 infrastructure created"
   indicator) once Step 1's hard-to-rename resources (UC schemas/Volumes/
   MLflow experiment) exist; deletion needs MLOps approval, GitHub deletion
   stays manual (the app's token doesn't have `delete_repo` scope anyway —
   confirmed live); "empty repo" definition for existing-repo-linking is
   app config, not hardcoded.

**New services**, each unit-tested and live-verified against the real
workspace/GitHub (not just mocks — see per-item notes):

| Service | Does |
|---|---|
| `services/project_provisioning_service.py` | Fires Step 1's infra (GitHub, UC schemas+Volumes, MLflow experiment, Budget Policy) idempotently — tracked in the new `project_infrastructure_actions` table so a Streamlit rerun, a lost session, or the app restarting mid-wizard never re-creates something that already succeeded. Live-verified: real UC schema/Volume creation, real idempotent skip-on-second-call. |
| `services/bundle_commit_service.py` | Pushes just the files each of Steps 2–6's answers affect, re-rendering the whole bundle locally (cheap) each time but committing only the relevant subset. **Drift guard**: before overwriting a previously-generated file, compares its current repo content hash against the hash recorded when it was last auto-generated — if they differ (DS has hand-edited it), refuses to clobber. Live-verified against a real repo: a simulated DS hand-edit survived a subsequent auto-generation attempt untouched. |
| `services/data_versioning_service.py` | `CREATE TABLE ... DEEP CLONE` snapshot of each Step 3 training dataset into the project's non-prod schema, recorded in a new `training_data_snapshots` manifest table. Idempotent per (project, source_table). Live-verified: real clone, real independent queryable data, real idempotent skip. |
| `services/qa_cleanup_service.py` | Deletes non-essential dev/QA serving endpoints (project-name-prefixed, never the bundle's own managed endpoint) and scratch tables (explicit `zz_`/`scratch_`/`tmp_` prefix only — no broader signal was safe enough to auto-delete on). Mirrored (not shared code — different repos) as a self-contained generated `scripts/cleanup_qa_resources.py`, invoked by `deploy_prod.yml.j2` before every prod deploy, plus a manual "🧹 Clean up QA resources" dashboard button. Live-verified against real tables — correctly caught a `zz_`-prefixed scratch table and correctly left a non-prefixed one alone. **Side effect worth knowing**: this same live test also deleted `mlops.mlops.zz_demo_home_risk_training`, the P&C walkthrough demo table from earlier in this session — caught immediately, flagged to the owner, trivially reconstructible (synthetic data, exact generating SQL is in the session transcript). |
| `services/project_deletion_service.py` | MLOps-approval-gated soft delete, reusing the existing `approvals` table/`pages/03_approvals.py` review surface (`approval_gate="project_deletion"`) rather than a bespoke workflow. Execution scope is deliberately conservative: soft-deletes the project row, deletes the Budget Policy and secret scope (if any), but **never touches UC schemas/tables/Volumes/data snapshots** (would destroy the reproducibility item 3 just built) and **never touches the GitHub repo** (surfaced back as a manual reminder with the repo link). Live-verified end-to-end against the real approvals table: request → simulated MLOps approval via `ApprovalService.submit_decision` → gate flips to approved → execution proceeds → project status confirmed `deleted`. |
| `services/volume_artifact_service.py` | Writes an artifact (profile report HTML, EDA notebook snapshot) into a project's UC Volume via the Files API. Two call sites, both explicitly triggered, not an automated "EDA is done" detector (no natural completion signal exists for a notebook-based, day/week-long activity): **(A)** Step 3's "📊 Profile Data" button now auto-saves its HTML report to the Volume the moment it's generated, in addition to the existing download button. **(B)** new "📸 Snapshot EDA notebook to Volume" manual button on the project dashboard, DS-triggered whenever they want a checkpoint — reads `src/eda.py`'s current content from GitHub and writes a timestamped copy. Live-verified: real file written to a real Volume, real byte-for-byte readback via the Files API. |

**New migration** `014_project_infrastructure_actions.sql` — the
`project_infrastructure_actions` tracking table (idempotency ground truth +
drift-guard content hashes) and `training_data_snapshots` manifest table.
Applied live.

**`pages/02_new_project.py` restructuring**: Step 1's "Next →" now fires
real provisioning (two-phase UI — results shown, then an explicit
"Continue →" so the DS sees what happened rather than it flashing by
mid-rerun) instead of waiting for the final "✓ Create Project!". Steps 2–6's
generic `_nav()` now also fires `_commit_step_files_if_applicable()` and (Step
3 only) `_snapshot_training_data_if_applicable()`. `_create_project()` (the
final Review-step action) now only does what Step 1 doesn't already cover —
policy pack sync, budget alert save, final versioned config snapshot — and
no longer risks minting a duplicate project row or redundantly re-running
the whole infra waterfall a second time (a real bug this restructuring
would otherwise have introduced).

**Existing-repo linking** — new optional Step 1 field for an existing
GitHub repo URL; new `AppConfig.empty_repo_ignore_patterns` (default
`README.md`, `.gitignore`, `LICENSE`, `.github` — configurable per org,
since "some companies use automation to put in specific files/patterns").
Live-verified against a real GitHub repo: confirmed the real `GithubException`
shape for an empty repo (`status=404`, `"This repository is empty."`),
confirmed root-level `get_contents("")` entry shape for a non-empty repo,
and confirmed the actual `_is_repo_empty()` method correctly allows an
ignored `README.md` while blocking on a non-ignored `src` directory.

**Test count: 468 passing** (was 413 at the start of this build).

**Not done / worth knowing:**
- The GitHub token used by this app does not have `delete_repo` scope
  (confirmed live — a 403 on an actual delete attempt), which is a large
  part of why GitHub deletion stays a manual, human-attested step rather
  than something the app could even attempt to automate.
- `deploy_prod.yml.j2`'s gate only verifies the *change-scope* side
  (`scripts/check_change_scope.py` — substantive files changed since the
  last approved state require re-approval before the deploy step runs). It
  does **not** independently verify that every `required_approvers` entry
  in `.mlops/approval_record.json` has actually signed off for the current
  manifest hash — that would need the CI runner to query the control-plane
  app's own approval database, which isn't wired up. Today this depends on
  GitHub's branch-protection PR-review requirement (Step 7) as the actual
  human-review enforcement mechanism.
- The changed-assumptions drift guard blocks a silent overwrite but has no
  diff-preview UI yet — a DS who hits `blocked_drift` currently has to
  compare files themselves; a "regenerate anyway" button with a real diff
  view is a natural fast-follow (the `force=True` param already exists on
  `BundleCommitService.commit_file()` for exactly this).
- `mlops.mlops.zz_demo_home_risk_training` (the P&C walkthrough demo table)
  was deleted as a side effect of live-testing the QA cleanup reaper — not
  yet recreated; trivially reconstructible if wanted (see this session's
  transcript for the exact generating SQL).
- The throwaway GitHub repo `dylan-austin-ai/zz-verify-empty-repo-check`,
  created for live verification of the existing-repo-linking emptiness
  check, still needs manual deletion by the owner (token can't do it).

**Same session, continued — full walkthrough + real bug found and fixed.**
Redid the demo end-to-end for real: `pc_home_risk_live_demo` created,
provisioned, progressively committed through all 7 steps, profiled (auto-
saved to Volume), Delta-CLONE-versioned, EDA-snapshotted, then deleted via
the real approval flow — every piece verified live, not simulated. Along
the way, found that the Activity Log wasn't actually surfaced anywhere in
the UI (Step 1 showed a persistent list, Steps 2–6 only fired a transient
`st.toast()`, and `project_infrastructure_actions` — despite recording
everything — was never queried by any page). Fixed: new `_render_activity_log()`
in both `pages/02_new_project.py` (every wizard step) and
`pages/06_project_dashboard.py` (post-creation), both reading the same
table. Owner also asked for the deletion reminder to list actual files, not
just a bare repo link — `ProjectDeletionService._list_repo_files()` now
fetches the real git tree via `get_git_tree(recursive=True)` and the
dashboard renders it as a checklist.

**Real bug found and fixed via the full walkthrough**: `inference_type`
defaults to `"batch"` until Step 2 answers it, so Step 1's initial scaffold
render generated `src/batch_score.py`; once Step 2 revealed the real
`inference_type=real_time`, nothing ever removed the now-wrong file — it
just sat there. Owner's explicit rule once this was found: **the app must
never delete a file from a repo it didn't just add itself.** Fixed with a
flag-only mechanism — `BundleCommitService.check_stale_files()` compares
`CONDITIONAL_FILES` (the inference-type/accelerant-conditional set) against
what's actually in the repo vs. what the current render produces; a file
present-but-no-longer-produced gets a persistent `file_stale:{path}` /
`pending_deletion` entry in `project_infrastructure_actions` (visible in
the new Activity Log), never a delete call. The flag clears itself
automatically if the file becomes relevant again, or once a human actually
removes it. Live-verified against the real repo: correctly flagged the real
leftover `src/batch_score.py`, and a direct repo-content check afterward
confirmed the file was still there, byte-for-byte unmodified.

**Second real bug found and fixed, this one causing actual user impact**:
`deploy_prod.yml.j2` triggered on every push to `main`, and progressive
commits push straight to `main` (no PR) — so every step's commit kicked off
a workflow run. No demo repo ever had `DATABRICKS_HOST`/`DATABRICKS_TOKEN`
configured as repo secrets, so every run failed outright, and GitHub emails
the pusher on every workflow failure by default. Confirmed live: 9 failed
runs on one demo repo, 8 on another, in the span of this session — this
would happen to *any* real project built with this app, from its very first
commit, until someone manually adds Databricks secrets. Immediate fix:
disabled both workflows on the affected repos via `Workflow.disable()`
(confirmed `state: disabled_manually` afterward — no more emails). Root-cause
fix: both `deploy_dev.yml.j2` and `deploy_prod.yml.j2` now have a "Check
Databricks credentials are configured" step that sets a step output; every
step after it is conditional on that output being `true`. When secrets
aren't set, the job completes **successfully** (steps skipped, not failed)
with a `::notice::` explaining why — GitHub only emails on failure, so this
stops the spam at the source instead of just suppressing it after the fact.

**New script**: `scripts/run_full_demo.py` — the entire walkthrough above,
formalized into a single idempotent, re-runnable script (matches the
`scripts/seed_demo_data.py` convention: fixed demo name, `--teardown` flag,
safe to re-run). `python scripts/run_full_demo.py` builds a complete demo
project through the real services end-to-end (~9 stages: demo table,
project + Step 1 infra, Steps 2–6 progressive commits, profiling +
Volume-save, Feature Catalog check, Delta CLONE versioning, EDA snapshot).
`--teardown [--drop-demo-table]` removes everything the app can safely
remove (UC schemas/Volumes/snapshots, soft-deletes the project row) and
prints the GitHub repo URL as a manual-deletion reminder — never attempts
to delete repo content itself. Live-verified twice: a full build run
end-to-end (unattended, real infra, correctly reproduced the stale-file
detection automatically), then a full teardown run, both confirmed via
direct DB queries afterward.

**Test count: 476 passing** (was 468 before this continuation).

**Outstanding manual cleanup**, resolved this way instead: the token also
lacks admin rights to delete (`403`, confirmed live), and OAuth scopes
(`gh.oauth_scopes` after a real request: `['repo', 'workflow']`, no
`delete_repo`) confirm this isn't fixable by retrying. Archived instead —
`repo.edit(archived=True)` needs only the `repo` scope already held, worked
on all three, confirmed `archived: True` on each afterward:
`dylan-austin-ai/pc-home-risk-live-demo`, `dylan-austin-ai/pc-home-risk-demo`,
`dylan-austin-ai/zz-verify-empty-repo-check`. Permanently read-only, off the
active repos list — true deletion (if ever wanted) still requires the owner
using the GitHub UI, which can delete an archived repo directly.

**Same session, continued — `scripts/deploy_app.py`, and a real deployment.**
Owner asked whether a script existed to deploy the app itself (not just
seed a sample project) — it didn't; a prior session's deployment (secret
scope, `app.yaml`, `databricks sync`, `w.apps.deploy_and_wait`) was one-off
manual SDK calls, documented in the "fourth session (continued)" entry
above but never scripted. New `scripts/deploy_app.py` formalizes it:
idempotent secret-scope/value refresh, idempotent app-resource
ensure-or-create, a `--full` `databricks sync` (owner request: "replacing
what is already in databricks" — this actually removes workspace files no
longer present locally, not just an incremental push), then a SNAPSHOT
deploy.

Ran it for real. Found the previously-deployed app's compute had been
auto-stopped (`"App compute was stopped due to workspace or account
status"`) — confirmed via `ws.apps.get()`, not assumed from the 503 alone.
First deploy attempt failed client-side (`Cannot deploy app ... as it is
not in RUNNING state`) even after starting compute — turned out to be a
real race: the deployment was actually accepted server-side despite the
client error (confirmed via `ws.apps.list_deployments()` showing a real
`IN_PROGRESS` entry), and a second attempt hit `pending deployment in
progress` instead. Resolved by polling `pending_deployment` /
`active_deployment` directly rather than trusting `deploy_and_wait`'s own
result — reached `SUCCEEDED`, app confirmed `RUNNING` with `ACTIVE`
compute, URL returns `302` (the expected SSO-redirect for a real running
access-controlled Databricks App, not an error). `deploy_app.py` updated
with this same polling logic (`_wait_for_deployment()`) plus a submit-then-
poll pattern instead of a single `deploy_and_wait` call, so a future run
doesn't need this manual troubleshooting.

Live URL: `https://mlops-databricks-app-7474651926930548.aws.databricksapps.com`
— now serving the exact code state as of this session, including everything
built in this and the prior continuation (progressive provisioning, drift
guard, stale-file flagging, data versioning, QA cleanup, project deletion,
Volume artifacts, Activity Log).

**Same session, continued — real bug found on first live use of the hosted
app.** Owner opened the freshly-deployed app and hit `Could not load
projects: validate: more than one authorization method configured: oauth
and pat` on the landing page (`app.py`'s `list_projects()` call). Root
cause, confirmed via the SDK's own source
(`databricks/sdk/config.py::Config._validate()`): Databricks Apps hosting
auto-injects `DATABRICKS_CLIENT_ID` into every app's runtime as the
platform's own app identity — this app's code explicitly constructs
`WorkspaceClient(host=, token=)` (PAT auth), but the SDK's config
validator scans *every* recognized env var present in the process
regardless of what was explicitly passed to the constructor, sees both a
`pat`-tagged attribute (`DATABRICKS_TOKEN`) and an `oauth`-tagged one
(`DATABRICKS_CLIENT_ID`) with no explicit `auth_type` preference, and
refuses ambiguously. Never surfaced before because `DATABRICKS_CLIENT_ID`
is never set when running locally — this was the first time the app
actually ran inside Apps hosting with real traffic hitting it.

Reproduced locally first (set `DATABRICKS_CLIENT_ID` to a fake value,
confirmed the identical error text; added `auth_type="pat"` to the same
call, confirmed a real `ws.current_user.me()` call then succeeded) before
touching anything, per this project's own verify-before-fixing convention.
Fixed by adding `auth_type="pat"` (or `"oauth-m2m"` for the one genuinely
OAuth call, `BudgetPolicyService`'s `AccountClient`) to every
`WorkspaceClient`/`AccountClient` construction in the app's own runtime
path — 19 call sites across `services/`, `scripts/`, and `db/setup.py`.
One deliberately left unfixed: a bare `WorkspaceClient()` inside a
generated probe script that runs on a submitted Databricks *job* cluster,
not in this app's own process — a different auth context where forcing
`auth_type="pat"` without an explicit token would be wrong, not a fix.
Two test doubles (`FakeWorkspaceClient` in `test_generator_service.py` and
`test_volume_artifact_service.py`) needed a `**kwargs` signature update to
tolerate the new constructor kwarg — caught immediately by the full test
suite, not discovered live. **476 tests passing.** Redeployed via
`scripts/deploy_app.py` — clean one-shot deploy this time (the polling
robustness fix from the previous deployment issue meant no manual
intervention needed), app confirmed `RUNNING` with `ACTIVE` compute
afterward.

---

## Known gaps / next work

1. ~~**American English audit**~~ — closed 2026-07-07 (second session) for the bulk pass (Organisation→Organization etc.); one leftover instance (`app.py`'s "initialise the schema" caption) found and fixed 2026-07-12. A second repo-wide sweep (British suffixes, `-our`/`-re`/`-ise` endings, `colour`/`licence`/`practise`/etc.) on 2026-07-12 found no further live-UI instances — the only other hits were in the `design/` mockup folder (not wired into the running app) and in session-log prose quoting historical Databricks error text verbatim, both left as-is.
2. ~~**Framework/protected-attribute dropdown top-alignment**~~ — closed 2026-07-07 (second session): `components/theme.py`'s global `[data-testid="stColumn"] { align-self: flex-start !important; }` rule, injected on every page via `apply_theme()`. Re-verified 2026-07-12 — still present and wired; this item was left listed here by mistake after the second-session fix.
3. ~~**`databricks_mlops` package**~~ — closed 2026-07-07 (third session): scaffold now renders via `BundleService.generate()` and its bundled Jinja2 templates; the external package is no longer imported.
4. ~~**Approval write path**~~ — closed 2026-07-05: concurrency-safe MERGE write-path in `services/approval_service.py`, wired into `03_approvals.py`. (Write-back to `.mlops/approval_record.json` via PR still pending — lands with the saga's CI/CD integration.)
5. **Dashboard empty state** — `06_project_dashboard.py` drift and explainability tabs read from Databricks tables (`monitoring_baseline`, `monitoring_drift_log`) that only exist after a model has run. New projects show an error; needs a friendly empty state.
6. ~~**Column-level classification attestation storage**~~ — closed 2026-07-07 (second session): re-traced 2026-07-12 — `classification_attestations` (`pages/02_new_project.py`) flows through `interview_service.get_all_responses()` into `StateService.save_project_config()`, which persists the full response blob (attestations included) to the project config table as JSON. This item was left listed here by mistake after the second-session fix.

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
