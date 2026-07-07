# Decisions Needed — Owner Punch List

**Created:** 2026-07-05. Each item says what's blocked, what I recommend, and
what happens if you do nothing. Items are ordered by urgency. When you decide,
note it here (or just tell the build session) — several change code paths.

---

## 1. Databricks workspace — reactivated 2026-07-07, but two new constraints ⚠️

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

## 2. Catalog naming convention — I made a call, you should ratify it

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

## 3. Can serving endpoints route on `@champion`, or numeric versions only?

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

## 4. Wizard scaffold path — cut over to Bundle Service?

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

- **De novo baseline (§26.4):** someone measures how long repo+schemas+endpoint
  +monitoring takes by hand — the number Interview Speed is judged against.
- **Policy pack tiers (§20.3):** phase 11 landed 2026-07-07 — the mechanism is
  live and `policy_packs/generic_tiering.yaml` is the shipped placeholder.
  **Now actionable:** PR your real tiers/gates as YAML into `policy_packs/`
  (tier names and gate names are free-form data; `on_revalidation_due` must be
  warn / block_new_traffic / block_all_traffic).
- **Canary window metrics (§15.2 step 5):** which metrics and thresholds gate
  champion promotion. Until decided, the saga records the canary step as
  *skipped* (never silently passed). Phase 6's monitoring service gives the
  mechanism; the thresholds are a business call.
- **Streaming go/no-go (§29.2):** phase 10 starts only when a real governed
  source stream exists — synthetic sources deliberately don't count.
  (Checked 2026-07-07: the workspace contains only the control plane's own
  tables — gate stays closed, build order skipped to phase 11.)
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
