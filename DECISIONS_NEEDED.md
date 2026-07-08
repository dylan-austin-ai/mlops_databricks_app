# Decisions Needed — Owner Punch List

**Created:** 2026-07-05. Each item says what's blocked, what I recommend, and
what happens if you do nothing. Items are ordered by urgency. When you decide,
note it here (or just tell the build session) — several change code paths.

---

## Owner decisions 2026-07-07 (evening, third session) — all six approved

1. **Build order:** phase 10 (streaming, against the synthetic source) next,
   then phase 13 (capacity service + control-plane budget). Phases 12/14/15
   deferred until their trigger events (regulated deployment; external API
   consumers) are actually planned.
2. **`@champion` verification (item #3):** scratch serving-endpoint
   deploy → read-back → destroy cycle approved to settle whether
   `entity_version` accepts the alias.
3. **Control-plane budget (phase 13):** ship config-driven
   (`MLOPS_CONTROL_PLANE_BUDGET_WARN/_CRIT`) with placeholder defaults
   $50/$100 per month, marked PLACEHOLDER in the UI.
4. **Model Serving quota conversation (item #5):** deferred — no double-digit
   real-time model count planned; capacity service (phase 13) will flag
   pressure first.
5. **De novo baseline:** 10-day placeholder stands until 2–3 real (non-demo)
   projects exist to measure.
6. **Cost figures:** list prices stand; revisit only when absolute dollars go
   to a budget owner.

---

## 1. ~~Databricks workspace~~ — RESOLVED 2026-07-07 (second session)

Serverless capacity freed up; warehouse verified RUNNING. Migrations 001–010
applied, policy packs synced, and the Week 1 round-trip proof passed live.
The Default Storage catalog constraint is handled by decision #2 below
(schema-per-project + `MLOPS_MANAGED_LOCATION`). Historical detail follows.

## 1-old. Databricks workspace — reactivated 2026-07-07, but two new constraints

~~The org returns "cancelled or is not active yet".~~ **Resolved:** as of
2026-07-07 the workspace answers normally (auth, reads, listings, real errors
on resource creation). Two follow-on issues, checked live:

1. **Serverless capacity:** the `Serverless Starter Warehouse` fails to launch
   with `RESOURCE_EXHAUSTED: Cannot create the resource, please try again
   later` — retried for ~2 hours on 2026-07-07. Looks transient/platform-side,
   but until a warehouse starts, `python -m db.setup` (migrations 001–010) and
   `scripts/verify_live_roundtrip.py` stay blocked. Retry these first thing
   next session; if it persists for days, it's a support-ticket item, not a
   code problem.
2. **Default Storage:** `CREATE CATALOG` via API/SQL now demands a
   `MANAGED LOCATION` ("Default Storage is enabled in your account") — catalog
   creation otherwise goes through the UI. This directly affects decision #2
   below: the built `{team}_{project}_{env}` catalog-per-project convention
   cannot be provisioned declaratively on this workspace as-is. Options:
   pre-create catalogs in the UI, add a managed-location variable to the
   bundle templates, or fall back to schemas inside the existing `mlops`
   catalog (the wizard's original shape) for this workspace.

**If nothing:** everything built since 2026-07-05 stays unverified against a
real workspace, and each further phase stacks more unverified surface — the
design's own tenet 8 says don't let that run long.

---

## 2. ~~Catalog naming convention~~ — DECIDED by owner 2026-07-07

**Decision:** all projects in the production workspace; one configurable
catalog (`mlops`, via `MLOPS_PROJECTS_CATALOG`) with a distinct schema per
project per environment (`{project}_{env}`); option B managed-location
support for catalog creation (`MLOPS_MANAGED_LOCATION`). Implemented and
round-trip-verified live the same day. Per-env catalog overrides
(`MLOPS_PROJECTS_CATALOG_DEV/_STAGING/_PROD`) keep catalog-per-env at 100+
projects a config change. Original discussion follows for the record.

## 2-old. Catalog naming convention — I made a call, you should ratify it

The design doc uses two conventions: §5.1/§9.1 use a catalog per
project+environment (`retention_team_customer_churn_prediction_prod` with a
`monitoring` schema), while §7.2's older examples use a team catalog
(`retention_team.customer_churn_prediction_prod.model`). The existing wizard
creates a third shape: schemas inside one shared catalog
(`{MLOPS_CATALOG}.{project}_dev`).

**I built:** catalog = `{team}_{project}_{env}`, with `ml` and `monitoring`
schemas inside it (templates + registry naming). Rationale: catalog-per-env is
a locked §0 decision and both rev-5-verified YAML examples use it.

**Decide:** keep this, or switch to team-catalogs (`{team}.{project}_{env}`)?
Note: catalog-per-project-per-env means every project creates 3 catalogs —
at 100 projects that's 300 catalogs; team-catalogs stay flatter. Metastore
catalog-creation permissions also differ from schema-creation permissions.

**If nothing:** the built convention stands; changing later means editing
`templates/bundle/*.j2` and re-scaffolding, not a data migration (nothing
deployed yet).

---

## 3. ~~Can serving endpoints route on `@champion`?~~ — RESOLVED 2026-07-07: numeric-only

Live-probed (scripts/verify_champion_alias.py, owner-approved scratch deploy):
the Model Serving API rejects aliases in `entity_version` — **"Entity version
must be a number."** Consequence implemented the same day: saga step 6 now
updates the serving endpoint's champion entity to the numeric candidate
version after the alias move, with champion re-point compensation on failure
(`RegistryService.update_champion_serving_version`). Batch/streaming projects
(no endpoint) record the step as skipped.

Follow-up noted, not built: endpoint-level canary *traffic splits* (step 4)
would likewise need served-entity config updates; today's canary is
metrics-based (step-6 default check), so nothing is inconsistent — revisit
when real traffic-split canaries are wanted. Original context follows.

## 3-old. Can serving endpoints route on `@champion`, or numeric versions only?

§7.2 shows `entity_version: "@champion"` in the serving config. The bundle
schema accepts any string, but I could not verify the *API* accepts an alias
here — and it decides real promotion mechanics:

- **If aliases work:** promotion = re-point the alias; endpoints never change.
- **If numeric-only:** every promotion must also update the endpoint config
  (a bundle deploy or endpoints API call) — the saga gains a step.

**I built:** templates take `champion_version` as a variable (defaults to a
numeric version), so both paths work without rework.

**Decide/verify:** first live serving deploy (Week 2 item in
`PROJECT_STATUS.md`) — try `@champion`; if rejected, the saga's step 4/6 gains
an endpoint-config update. Nothing to decide *before* the workspace is back.

---

## 4. Wizard scaffold path — DONE 2026-07-07 (third session)

Owner approved the cutover 2026-07-07; built the same day: `_scaffold_code`
internals replaced with `BundleService.generate()` + the existing `.mlops/`
files + git init/initial commit, GitHub/UC/MLflow/secret-scope steps kept
as-is. See PROJECT_STATUS.md third-session entry. Original context follows.

## 4-old. Wizard scaffold path — cut over to Bundle Service?

`services/generator_service.py` still scaffolds via the external
`databricks_mlops` package (PROJECT_STATUS gap #3: no fallback if missing).
The Bundle Service can now render a complete deployable bundle, but the wizard
doesn't call it yet — new projects created through the UI don't get bundles.

**Recommendation:** replace the `_scaffold_code` internals with
`BundleService.generate()` (plus the existing `.mlops/` files), keeping
GitHub/UC/MLflow/secret-scope steps as-is. ~1 session of work incl. tests.

**If nothing:** two parallel scaffold mechanisms drift; bundles exist only for
projects created outside the wizard.

---

## 5. Start the Model Serving quota conversation (§29.2 — only you can)

Endpoint quotas per workspace aren't published; the design says engage your
Databricks account team *now*, in parallel with the build, since that
conversation has lead time. Relevant once >~20 real-time models are plausible.

---

## 6. Business/process items the app can't decide (later phases)

- **De novo baseline (§26.4):** owner set a **10-day placeholder** on
  2026-07-07 (surfaced as PLACEHOLDER in Portfolio Analytics). Still worth a
  real by-hand measurement eventually; replace `DE_NOVO_BASELINE_DAYS` and
  its placeholder flag together in `portfolio_analytics_service.py`.
- **Policy pack tiers (§20.3):** DECIDED 2026-07-07 (evening) — the generic
  three-tier structure is the org's **permanent** framework, not a
  placeholder. `generic_tiering_v1` stands; future changes arrive as PRs to
  `policy_packs/generic_tiering.yaml` (or sibling pack files).
- **Canary window metrics (§15.2 step 5):** DECIDED 2026-07-07 — defaults to
  the wizard step-6 primary performance metric with its alert threshold as
  the breach condition (`make_default_canary_check`). A project can still
  inject a custom check; without config or monitoring rows the step stays
  *skipped*, never silently passed.
- **Streaming go/no-go (§29.2):** SUPERSEDED 2026-07-07 (evening) — owner
  wants everything pilotable/demoable on fake data. Phase 10 may proceed
  against the synthetic source (`{catalog}.demo_streaming.events`, seeded by
  `scripts/seed_demo_data.py`, with `--tick` simulating the upstream
  producer). Honest caveat retained from the original rationale: a synthetic
  source validates the *mechanism* (continuous job, checkpointing, scoring,
  monitoring attach), not real-source integration risk (schema drift, gaps,
  latency variance, upstream ownership) — re-verify against the first real
  governed stream before any production streaming claim.
- **Cost figures use list prices** (`system.billing.list_prices` default):
  ignores negotiated discounts. Fine for trends; decide whether absolute
  dollars matter enough to feed real rates in later.

---

## Already decided (by you, 2026-07-05) — recorded for the record

- Build scope: as much as possible, MVP first, then §27.2 dependency order.
- Build location: evolve `mlops_databricks_app` in place (not the `_fable` dir).
- Verification: install CLI + live verify (executed until the workspace died).
- All §29 open-item **Suggestions accepted** as decisions of record — including
  SHAP/TreeExplainer default, DiCE for counterfactuals, escalate-never-auto-approve
  on HITL SLA breach, per-environment online tables, consumer acks for breaking
  feature changes, and governance fields exempt from auto-collapse.
