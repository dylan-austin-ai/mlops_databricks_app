# MLOps Databricks App — Project Status

**Last updated:** 2026-07-08 (fourth session)

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

259 passing — cover all services, Pydantic step models, step-level validation,
and the generator.

Run with the project venv — the system `python3` fails test collection
(cross-test imports like `from tests.test_approval_service import ...` don't
resolve outside `.venv`):

```
.venv/bin/python -m pytest tests/
```

---

## Known gaps / next work

1. **American English audit** — UI text not systematically reviewed; a few British spellings may remain.
2. **Framework/protected-attribute dropdown top-alignment** — CSS fix needed for multiselect widgets rendered inside `st.columns`; they currently don't align to the top of their column when another column has more content.
3. ~~**`databricks_mlops` package**~~ — closed 2026-07-07 (third session): scaffold now renders via `BundleService.generate()` and its bundled Jinja2 templates; the external package is no longer imported.
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
