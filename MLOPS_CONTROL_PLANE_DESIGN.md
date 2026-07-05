# Databricks MLOps Control Plane: System Design Document

**Status:** Ready for owner final review. Supersedes/extends `DATABRICKS_MLOPS_APP_SPECIFICATION.md`, `IMPLEMENTATION_SPEC.md`, `PROCESS_MAP.md`, `WIREFRAMES.md`, and `DATABASE_SCHEMA.md` where they conflict. The Week 0 verification spike this document itself called for (§29) has now been performed rather than deferred — see the rev. 5 note below for what that changed.
**Last updated:** 2026-07-04 (rev. 5 — Week 0 verification spike performed. Found and fixed three real schema errors that would have broken a straight implementation: `route_optimized` was nested in the wrong place, `auto_capture_config` is officially retired and needed replacing with `ai_gateway.inference_table_config`, and the streaming job's `continuous` trigger was wrapped in a nonexistent `trigger` key — all three corrected in §9.1/§9.4, with §29 updated to show exactly what was found. Also resolved the standing terminology question (§6/§8/§29): kept "Delta Sharing"/"Online Tables" as primary terms with current docs' actual names flagged inline, rather than renaming. Prior revision (4.2) added counterfactual explanations §12.4, a further adversarial pass, Databricks documentation citations throughout, and marked suggestions for every open item; rev. 4.1 restored content lost when rev. 4 compressed "unchanged" sections during a large rewrite.)

---

## 0. Document Purpose & How to Read This

Rev. 1–2 re-grounded the original governance workflow in Databricks-native primitives. Rev. 3 closed gaps found by cross-referencing against `black.md`'s org strategy outline. Rev. 4 was the result of an adversarial self-review: it fixed a real internal contradiction (route optimization vs. serving-time explainability), corrected a technical assumption that didn't hold up against actual Databricks documentation (Inference Table `extra_payload`), and — the biggest one — directly addressed the fact that this document had only ever *added* to the interview for three straight revisions, which is in tension with the org's own founding thesis (§26). Rev. 4.1 is a self-check pass: rewriting a ~700-line document twice in one session compressed several "unchanged" sections down to summaries that dropped real content, and broke one table outright. No design decisions changed in this revision — everything below is either restored rev. 1–3 content or an already-decided rev. 4 fix, now actually present.

Seven foundational architectural decisions (rev. 1–2, unchanged):

| Decision | Choice | Why |
|---|---|---|
| Workload scope | Classical ML only (batch/real-time/streaming predictive models) | GenAI/LLM MLOps is a distinct problem space. Out of scope for v1 — audited for non-blocking in §28. |
| Provisioning mechanism | Databricks Asset Bundles (DABs) | Declarative, diffable, environment-targeted. Every generated project *is* a bundle. |
| Model registry | Unity Catalog Model Registry (`catalog.schema.model`) | Cross-workspace governance, native lineage. "Stages" redesigned into environment-scoped catalogs + aliases + tags (§7). Confirmed against current docs: UC explicitly does not support legacy stages — aliases are the documented replacement (§7.4). |
| Hosting & auth | Native Databricks App (OAuth passthrough) | Every action runs as the actual logged-in user. |
| Deployment pattern default | Single workspace, catalog-per-environment | Simpler default; revisited explicitly at scale in §19. |
| Approval bot (Slack/Teams) | Deferred to v1.1 | API endpoint ships in v1 (§23); the bot itself doesn't. |
| Reference policy packs | Generic tiering mechanism only — no named frameworks shipped | Orgs author their own via §20.3. |

Rev. 3 decisions (unchanged):

| Decision | Choice | Why |
|---|---|---|
| Streaming inference | In scope, scoped to *scoring* only (§9.4) | Expected deployment pattern per org strategy; pipeline authoring stays out. |
| Problem intake & prioritization | Explicitly upstream of the app | Org-process question, not an app feature. |
| Persona set | Capped at the original six | Keeps v1 RBAC surface small; additive later if needed. |
| Route optimization + Inference Tables | Default-on for every real-time endpoint | Governance-by-default applied to serving config itself. |

Rev. 4 decisions (unchanged from rev. 4, now with full content restored in the sections below):

| Decision | Choice | Why |
|---|---|---|
| Interview cognitive load | Measured continuously as a first-class KPI, with a standing design gate on every future addition (§26) | A well-designed app is supposed to absorb complexity, not accumulate it as friction. |
| HITL applicability | One of several documented human-oversight mechanisms, chosen per deployment pattern (§11.4), not a single sync-only flag | Resolves the unresolved HITL-vs-streaming contradiction from rev. 3. |
| Explainability delivery | Per-item sync/async configuration with an automatic latency-budget demotion (§12.2) | Fixes a real contradiction between route optimization and serving-time SHAP. |
| Telemetry mechanism | Corrected: domain-specific enrichment goes to an app-owned table joined via `client_request_id`, not an assumed `extra_payload` Inference Table column (§9.2) | The assumed field doesn't appear in current Databricks documentation. |
| Bundle Service integration | Structured JSON plan/deploy (`bundle plan -o json`, `bundle deploy --plan`), read-back verification, pinned CLI version (§5.2) | Confirmed real commands replace an assumed, unconfirmed `bundle diff`. |
| Scaling strategy | Endpoint consolidation + a Capacity Service tracking real, documented limits (§19) | Makes the single-workspace-at-scale tension visible and actionable. |
| Control-plane cost | Its own tagged budget, tracked separately from project costs (§17.4) | Cross-project services have a cost footprint rev. 3 never accounted for. |
| Concurrency on approvals/HITL | Delta conditional MERGE (§15.1, §11.2) | Reuses a managed primitive instead of hand-rolled locking. |
| Near-term build plan | An honest, small "Weeks 1-4" scope distinct from the full multi-quarter roadmap (§27) | A two-person, few-week build needs a roadmap that says so plainly. |

---

## 1. Scope & Non-Goals

**In scope (v1):**
- Batch, real-time, and streaming inference for classical ML models (§9)
- Full lifecycle: interview → scaffold → develop → contract → validate → stage → approve → deploy → monitor → retrain → retire
- Data contracts and quality gates on Unity Catalog tables, including versioned, breakage-protected shared feature contracts (§8.6)
- Feature Engineering in Unity Catalog plus cross-project Feature Discovery (§8.5)
- Label quality and feedback-loop capture (§10)
- Human-in-the-loop review, expressed as a menu of oversight mechanisms fit to deployment pattern, not a single flag (§11)
- Explainability, with per-item sync/async delivery (§12), counterfactual explanations (§12.4), and mechanical model-card assembly (§12.3)
- Fairness/bias testing as a first-class, non-skippable gate
- Program/portfolio-level analytics, including an explicit comparability/confidence indicator (§14)
- Full audit trail reconciled against Databricks system tables, with self-monitoring on the reconciliation jobs themselves (§21)
- Multi-environment deployment patterns, with an explicit strategy and instrumentation for scaling past a single workspace (§19)
- Model risk tiering and regulatory policy packs, with a real revalidation trigger (§20)
- Network/deployment security posture for regulated environments
- A continuously measured, continuously optimized interview — not just a one-time UX pass (§26)

**Explicitly out of scope (v1) — see §30 for what changes if added later:**
- GenAI/LLM workloads (RAG, agents, prompt registries, Vector Search, AI Gateway)
- Authoring the *upstream* streaming/DLT ingestion pipeline itself — the app deploys streaming *inference* (§9.4) against a source that's already governed; it does not build the pipeline producing that source
- Multi-cloud active-active (multi-cloud is a supported *deployment pattern*, but cross-cloud replication/failover is not designed here)
- A general-purpose Terraform-based IaC path (DABs is the only supported mechanism)
- **Problem intake and prioritization** — which model ideas get built at all is decided upstream of this app. The interview's "business problem" field can optionally reference an external intake ticket ID for traceability, but the app implements no backlog, scoring, or prioritization UI.
- **Personas beyond the original six** (data_scientist, ml_engineer, legal_reviewer, business_stakeholder, security, admin) — deliberately not modeled in v1.

---

## 2. Design Tenets

1. **Databricks is the ground truth; the control plane is a governed view over it, not a shadow copy.**
2. **Declarative over imperative.** Infrastructure changes happen through bundle deploys with diffable state.
3. **Governance is structural, not a checklist.** Enforced by what the generated CI/CD pipeline, bundle, and serving config *can even do* — including serving defaults like route optimization and inference capture (§9.1), not just approval workflow.
4. **Every write is attributable to a real identity.** OAuth passthrough means `actor_email` is never "the app."
5. **The app fails loudly and safely.** Multi-step operations are sagas with compensating actions.
6. **Prefer the managed Databricks feature over hand-rolling it.**
7. **Metrics exist at the portfolio level, not only the project level.** If a number matters enough to be in the org's stated success criteria (`black.md` §4, §k), it belongs on a program dashboard, not buried in per-project tiles nobody rolls up (§14).
8. **Ground every technical claim in current Databricks documentation before building on it.** This surface moves fast (rev. 4 found a genuinely wrong assumption — §9.2 — and a case of the platform itself renaming an API mid-research, §13). A confident-sounding YAML snippet is not the same thing as a verified one.
9. **The interview's speed is a tracked metric, not a design aspiration.** New capability must earn its way past auto-inferred or defaulted (§26.2) before it's allowed to be a blocking question — this is a standing gate on every future revision of this document, not a one-time cleanup.

---

## 3. Reference Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    DATABRICKS APP (native hosting)                  │
│         OAuth passthrough — every request carries user identity      │
├──────────────────────────────────────────────────────────────────────┤
│  Streamlit UI (interview, dashboard, approvals, portfolio analytics,  │
│   feature catalog, HITL review)  │  REST API (/api routes)           │
├──────────────────────────────────────────────────────────────────────┤
│                     CONTROL PLANE SERVICES (Python)                  │
│ ┌────────────┐┌─────────────┐┌────────────────┐┌───────────────────┐│
│ │Bundle Svc  ││Registry Svc ││Reconciliation  ││Feature Engineering ││
│ │(plan/deploy││(alias+tag)  ││Svc (+ self-    ││Svc (+ Discovery +  ││
│ │ + verify)  ││             ││ monitoring)    ││ Contract Versioning)││
│ └────────────┘└─────────────┘└────────────────┘└───────────────────┘│
│ ┌────────────┐┌─────────────┐┌────────────────┐┌───────────────────┐│
│ │Approval    ││Contract Svc ││Secrets/SP Svc  ││Policy Pack Svc     ││
│ │Saga Engine ││             ││                ││(+ revalidation)    ││
│ │(+ concurrency-safe MERGE, + revocation)      ││                    ││
│ └────────────┘└─────────────┘└────────────────┘└───────────────────┘│
│ ┌────────────┐┌─────────────┐┌────────────────┐┌───────────────────┐│
│ │Feedback Join││HITL Review  ││Portfolio       ││Capacity Svc        ││
│ │Service      ││Svc (+ MERGE ││Analytics Svc   ││(workspace resource ││
│ │             ││ concurrency)││(+ comparability)││ limits, §19)       ││
│ └────────────┘└─────────────┘└────────────────┘└───────────────────┘│
│ ┌────────────┐                                                      │
│ │Interview    │  Smart Defaults Engine + interview telemetry (§26)   │
│ │Optimizer Svc│                                                      │
│ └────────────┘                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                          STATE (Unity Catalog)                       │
│  mlops.* control-plane tables  ⟷  reconciled against:                │
│    system.access.audit   │ system.billing.usage │ system.lineage.*   │
│    UC Model Registry     │ Lakehouse Monitoring  │ Job run history    │
│    Feature/Online Tables │ Genie Spaces / AI-BI  │ Inference Tables   │
├──────────────────────────────────────────────────────────────────────┤
│  GitHub (source of truth for code + DAB configs, PR-gated)           │
├──────────────────────────────────────────────────────────────────────┤
│  Network layer: Private Link, IP access lists, per-env catalogs      │
└────────────────────────────────────────────────────────────────────┘
```

The Feedback Join Service (§10.2), Portfolio Analytics Service (§14), Capacity Service (§19.2), and Interview Optimizer Service (§26) all run on the same scheduled-job pattern as the Reconciliation Service — none of them are called synchronously from the Streamlit request path.

---

## 4. Identity, Auth & RBAC

### 4.1 Authentication
App deployed via `databricks apps deploy`, native OAuth passthrough — no PAT tokens for end users. Scoped service principals back all automation: CI/CD deploy steps, the Reconciliation Service, scheduled retraining jobs.

Confirmed against current documentation: Databricks Apps explicitly supports two complementary identity models — a shared service-principal identity ("all users of the app share this identity") and user authorization via OAuth, where "after signing in through single sign-on (SSO), the app can use the user's credentials to access governed resources." This app uses the latter for all interactive Streamlit/API actions and the former only for scheduled automation (§16). See [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/) and [Key concepts in apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/key-concepts) (App authorization vs. User authorization).

### 4.2 Authorization model — two layers
**Layer 1 — App-level personas** (data_scientist, ml_engineer, legal_reviewer, business_stakeholder, security, admin — capped at six per §0/§1) control *what UI/actions are visible*.

**Layer 2 — UC grants** are the actual enforcement point:

```sql
GRANT USE CATALOG, USE SCHEMA, SELECT, MODIFY
  ON SCHEMA {team}.{project}_dev TO `data_scientists`;
GRANT USE CATALOG, USE SCHEMA, SELECT
  ON SCHEMA {team}.{project}_staging TO `data_scientists`;
GRANT USE CATALOG, USE SCHEMA, SELECT, MODIFY
  ON SCHEMA {team}.{project}_prod TO `ml_engineers`;
```

The app never emulates permission logic — if UC denies a query, the app surfaces that directly, rather than pretending to enforce access itself.

### 4.3 Group provisioning
Personas are backed by real Databricks/UC groups via SCIM from the org's IdP, not hardcoded email lists. The setup interview *selects existing groups*, it doesn't invent membership lists the app has to keep in sync by hand.

---

## 5. Infrastructure-as-Code Layer (Databricks Asset Bundles)

See [What are Declarative Automation Bundles?](https://docs.databricks.com/aws/en/dev-tools/bundles/) and [Declarative Automation Bundles resources](https://docs.databricks.com/aws/en/dev-tools/bundles/resources) for the current reference — note the "Declarative Automation Bundles" naming itself is what current docs use; this document still says "Databricks Asset Bundles (DABs)" throughout since that's the more widely recognized name at time of writing, but expect the docs' name to be the one that sticks going forward (another design-tenet-8 naming-churn data point).

### 5.1 Every generated project is a bundle

Default deployment pattern is **single workspace, catalog-per-environment** (§0): one workspace, three catalogs (`_dev`/`_staging`/`_prod`), isolation via UC grants. Dual-workspace remains supported/configurable, just not the default. See §19 for what changes at scale.

```
generated-repo/
├── databricks.yml
├── resources/
│   ├── jobs.yml                 # training/retraining/batch-scoring/streaming jobs (§9)
│   ├── model_serving.yml        # serving endpoint + traffic + route optimization + capture (§9.1)
│   ├── feature_engineering.yml  # feature table + online table defs (§8)
│   └── permissions.yml
├── src/  ├── tests/  └── ...
```

```yaml
bundle:
  name: customer_churn_prediction
targets:
  dev:
    workspace: {host: ${WORKSPACE_URL}}      # same workspace for all targets (default pattern)
    variables: {catalog: retention_team_customer_churn_prediction_dev}
  staging:
    workspace: {host: ${WORKSPACE_URL}}
    variables: {catalog: retention_team_customer_churn_prediction_staging}
  prod:
    workspace: {host: ${WORKSPACE_URL}}      # would differ (${PROD_WORKSPACE_URL}) only under
    mode: production                          # the optional dual-workspace pattern
    variables: {catalog: retention_team_customer_churn_prediction_prod}
```

### 5.2 App ↔ Bundle interaction (Bundle Service) — strengthened and grounded

Rev. 3 assumed the Bundle Service parses CLI text output and assumed a `bundle diff` command that isn't actually confirmed to exist. Checked against current Databricks CLI documentation:

- **Structured plan, not parsed text.** `databricks bundle plan -o json > plan.json` produces a real, structured JSON plan showing exactly what would change — this *is* the mechanism for what rev. 3 called `diff()`. There is no need to invent or assume a separate `diff` command. See the [bundle command group](https://docs.databricks.com/aws/en/dev-tools/cli/bundle-commands) reference.
- **Deploy from the reviewed plan, not a re-resolved one.** `databricks bundle deploy --plan plan.json` deploys precisely the plan that was generated and reviewed — closing a real gap where the underlying repo state could otherwise move between "what got approved" and "what gets deployed." The Saga Engine (§15.2) deploys the exact plan file attached to the approval record (§15.1 records the plan file's path/hash alongside the approval so this is enforceable, not just intended).
- **Trust but verify.** After any deploy, the Bundle Service independently reads back deployed resource state via the Databricks SDK and confirms it matches the applied plan before marking a saga step complete — a zero exit code is necessary but not sufficient evidence.
- **Version-pinned CLI, health-checked at startup.** The app's runtime pins an exact CLI version; a startup check confirms the pinned binary is present and reports the expected version, failing loudly rather than silently degrading if the environment drifts.
- **`generate()` / `validate(target)` / `destroy(target)`** round out the service's interface — `generate()` renders `databricks.yml` + `resources/*.yml` from Jinja2 templates (see [Bundle configuration examples](https://docs.databricks.com/aws/en/dev-tools/bundles/examples) and the [jobs tutorial](https://docs.databricks.com/aws/en/dev-tools/bundles/jobs-tutorial)); `validate(target)` runs `bundle validate` before any PR opens; `destroy(target)` is used only in Phase 6 archival, always behind MLOps approval.
- **Known caveat, confirmed by current docs, not resolved by them**: [Migrate to the direct deployment engine](https://docs.databricks.com/aws/en/dev-tools/bundles/direct) notes that "resource fields not handled by the implementation" can still drift between plans even under the current ("direct") deployment engine, and separately documents an older Terraform-based engine as a distinct alternative. This nuance should be re-verified immediately before Phase 1 of the build (§27) — it's exactly the kind of platform detail liable to have moved by the time implementation starts (design tenet 8).

### 5.3 Template versioning
Templates carry their own `template_version`, recorded on every generated project (`mlops.projects.template_version`). Template changes never silently rewrite existing projects — a project only picks up a new template version through an explicit, reviewable "upgrade scaffold" PR, analogous to a dependency bump.

---

## 6. Data Governance & Contracts (Unity Catalog-native)

Contract JSON schema (columns, PII levels, quality rules) is unchanged from the original spec, but enforcement and metadata are native:

- **Tags & comments**: every contracted column gets a UC column tag (`pii_level`, `classification`) via `ALTER TABLE ... ALTER COLUMN ... SET TAGS (...)`, discoverable via Catalog Explorer/UC search — not just inside the app.
- **Row/Column-level security**: `pii_level: high` contracts generate a UC row filter or column mask function, applied automatically. See [Row filters and column masks](https://docs.databricks.com/aws/en/tables/row-and-column-filters).
- **Lineage**: relies on UC's automatic column-level lineage (`system.lineage.*`); app tables record only what UC cannot capture, reconciled nightly. See [system tables — lineage](https://docs.databricks.com/aws/en/admin/system-tables/lineage).
- **Delta Sharing**: contracts can be marked `shareable`, triggering a share for approved external consumers. **Naming note**: current Databricks documentation presents this capability as "OpenSharing" rather than "Delta Sharing" — see [What is OpenSharing?](https://docs.databricks.com/aws/en/opensharing/), which documents the open protocol and its Delta Lake feature support matrix. This document keeps calling it "Delta Sharing" since that's still the more widely recognized name, but this is exactly the kind of rename design tenet 8 says to expect and re-check.
- **UC Volumes**: unstructured artifacts (model card PDFs, SHAP/LIME plots, evaluation reports) are written to a project-scoped UC Volume in addition to being committed to the GitHub repo's `docs/` — discoverable from Catalog Explorer alongside the tables and models they describe. See [What are Unity Catalog volumes?](https://docs.databricks.com/aws/en/volumes/).
- **Metric Views**: standardized business metrics (e.g., "model accuracy," "monthly cost per project") are defined once as UC Metric Views rather than recomputed ad hoc in every dashboard tile, Genie Space query, or Portfolio Analytics rollup (§14). See [Unity Catalog metric views](https://docs.databricks.com/aws/en/metric-views/).
- **`contract_type` stays an open field, never a fixed enum** — a deliberate constraint preserving GenAI extensibility later (§28).
- **Label sources** (§10.1) use this same contract mechanism — a label source is just a contract with a declared arrival-latency SLA.

---

## 7. Model Registry & Lifecycle (Unity Catalog Model Registry)

### 7.1 The core redesign

Current Databricks documentation directly confirms the core premise of this redesign: "setting stages and loading model versions by stage is unsupported in Unity Catalog; instead, use aliases for flexible model deployment." See [Manage model lifecycle in Unity Catalog](https://docs.databricks.com/aws/en/machine-learning/manage-model-lifecycle). Lifecycle is re-expressed accordingly:

| Concept | Old (workspace registry) | New (UC registry) |
|---|---|---|
| Environment | `mlflow_stage` on one model name | Separate catalogs per environment: `{team}.{project}_dev.model`, `_staging.model`, `_prod.model` |
| "Which version is live" | `tags: current/shadow/canary/previous` | **Aliases**: `@champion`, `@challenger`, `@shadow` |
| Promotion | `transition_model_version_stage(...)` | `set_registered_model_alias(alias="champion", version=N)` |
| Rollback | Re-tag previous version | Re-point `@champion` — atomic, auditable |

### 7.2 Promotion workflow

*(`route_optimized` and `ai_gateway.inference_table_config` from §9.1 apply to this endpoint too — omitted here to keep the alias/traffic-split mechanics the focus.)*

```
dev catalog   → staging catalog  → prod catalog
(free versions)  (approval: code       @shadow    → 0% traffic, collecting predictions
                  review + tests)      @challenger → canary %, per traffic_config
                                       @champion   → current production traffic
```

```yaml
resources:
  model_serving_endpoints:
    customer_churn_prediction:
      config:
        served_entities:
          - {name: champion, entity_name: retention_team.customer_churn_prediction_prod.model, entity_version: "@champion"}
          - {name: challenger, entity_name: retention_team.customer_churn_prediction_prod.model, entity_version: "@challenger"}
        traffic_config:
          routes:
            - {served_model_name: champion, traffic_percentage: 90}
            - {served_model_name: challenger, traffic_percentage: 10}
```

### 7.3 `mlops.models` / `mlops.model_versions` (revised)
No longer the source of truth for lifecycle state — a denormalized, queryable index over UC registry state, refreshed by the Reconciliation Service:

```sql
ALTER TABLE mlops.model_versions ADD COLUMNS (
  uc_full_name STRING COMMENT "catalog.schema.model_name",
  uc_version INT,
  current_aliases ARRAY<STRING> COMMENT "aliases pointing at this version, synced from UC",
  last_reconciled_timestamp TIMESTAMP
);
```

### 7.4 Aliases vs. Tags — division of labor

**Aliases** are the single mutable pointer used by anything that needs to *resolve* "the current version for purpose X." Exactly one version holds each alias at a time — this atomicity is what makes promotion and rollback single, auditable operations, and it's what `traffic_config` actually routes on. Tags are non-exclusive, so a pure-tags design (like the original spec's `current`/`shadow`/`canary`/`previous` tags) has no atomic guarantee — nothing stops two versions from both being marked "current" by mistake. See the [MLflow Model Registry workflow guide](https://mlflow.org/docs/latest/ml/model-registry/workflow) for `set_registered_model_alias`/`set_model_version_tag`, and the [Databricks SDK `registered_models` reference](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/registered_models.html) for the underlying UC API.

**Tags** are the descriptive, non-exclusive audit trail, written on every alias move so the history lives *on the artifact itself* in Unity Catalog — not only in the app's tables. Even if `mlops.*` tables were lost entirely, promotion history is reconstructable from UC tags alone:

```python
client.set_registered_model_alias(name=uc_full_name, alias="champion", version=v)
client.set_model_version_tag(name=uc_full_name, version=v, key="promoted_by", value=approver_email)
client.set_model_version_tag(name=uc_full_name, version=v, key="promoted_from_alias", value="challenger")
client.set_model_version_tag(name=uc_full_name, version=v, key="approval_manifest_hash", value=sha256_hash)
client.set_model_version_tag(name=uc_full_name, version=v, key="fairness_test_result", value="pass")
client.set_model_version_tag(name=uc_full_name, version=v, key="previous_champion_version", value=str(prior_version))
```

Anyone browsing Catalog Explorer — not just the app — can see why a version is champion and what it replaced.

---

## 8. Feature Engineering & Serving (Unity Catalog-native)

See [Databricks Feature Store](https://docs.databricks.com/aws/en/machine-learning/feature-store/) for the overview and the [Feature Engineering Python API reference](https://api-docs.databricks.com/python/feature-engineering/latest/index.html) for the client library.

- **Feature tables**: created via `databricks.feature_engineering.FeatureEngineeringClient` ([API reference](https://api-docs.databricks.com/python/feature-engineering/latest/feature_engineering.client.html)), with declared primary keys and (for time-series features) a timestamp key.
- **Point-in-time-correct training sets**: `FeatureLookup` ([API reference](https://api-docs.databricks.com/python/feature-engineering/latest/ml_features.feature_lookup.html)) + `create_training_set()` assemble training data without leakage, automatically — see [Train models with feature tables](https://docs.databricks.com/aws/en/machine-learning/feature-store/train-models-with-feature-store) and [Model Serving with automatic feature lookup](https://docs.databricks.com/aws/en/machine-learning/feature-store/automatic-feature-lookup). **Confirmed implementation detail**: in a Feature Serving or Model Serving context, `FeatureLookup`'s `table_name` is resolved to the corresponding online store automatically — the online table name must *not* be specified separately, which simplifies the Bundle Service's template logic (one table reference, not two).
- **Online lookups**: any feature table needed at low latency is synced for fast serving-time lookup. **Naming/architecture note, confirmed this session**: current documentation is mid-transition here. The capability is documented both as ["Online Feature Stores"](https://docs.databricks.com/aws/en/machine-learning/feature-store/online-tables) under Feature Engineering, and — more specifically — as ["synced tables"](https://docs.databricks.com/aws/en/oltp/instances/sync-data/sync-table) built on **Lakebase** (Databricks' operational Postgres layer), with a dedicated [migration guide from legacy and third-party online tables](https://docs.databricks.com/aws/en/machine-learning/feature-store/migrate-from-online-tables) — meaning "Online Tables" as this document has been calling them is itself the *legacy* term being migrated away from. Sync runs via managed Lakeflow Spark Declarative Pipelines, requires Change Data Feed enabled on the source table and a non-null primary key, and has documented throughput of roughly 150 rows/sec per Capacity Unit (continuous/triggered) or up to 2,000 rows/sec per CU (snapshot) — concrete numbers worth feeding into §17/§19 capacity planning once real feature volumes are known. **This is the single clearest piece of evidence in this whole document for design tenet 8**: the term this design has used throughout ("Online Tables") is documented, in Databricks' own migration guide, as the thing being moved away from.
- **Feature Serving endpoints**: exposes synced-table lookups as a REST endpoint automatically — implements the original spec's Lookup Service use case as pure configuration, no custom PyFunc wrapper needed. See [Feature Serving endpoints](https://docs.databricks.com/aws/en/machine-learning/feature-store/feature-function-serving) and the [tutorial](https://docs.databricks.com/aws/en/machine-learning/feature-store/feature-serving-tutorial).
- Feature tables get the same UC tagging/RLS/CLS treatment as any other governed table (§6).

### 8.5 Feature Discovery

Addresses `black.md`'s "Reuse, Not Reinvention" principle and Reuse Metric (§14.1) directly — a DS needs to *find* existing features before building new ones.

`mlops.features` (already defined in `DATABASE_SCHEMA.md` with `is_shared`/`shared_with_teams`) backs a new **Feature Catalog** page (`pages/08_feature_catalog.py`): searchable/filterable by name, tag, owner, freshness SLA, and a live **"used by N models"** count computed by joining `mlops.feature_lineage.downstream_model_ids`. This count is exactly the Reuse Metric input §14 needs — discovery UI and portfolio metric share one query, not two.

The interview's Data Specs step is updated to search this catalog *before* letting a DS declare a new feature — a structural nudge at the point of decision, not only a browse page nobody remembers to check. Underlying lookups still use Online Tables for the actual serving path; the catalog is a discovery/governance layer on top, not a new serving mechanism.

### 8.6 Feature Contract Versioning (closes a reuse-safety gap)

§8.5 makes it easy to find and consume another team's feature table. Nothing previously protected a consumer from a silent breaking change by the owner. Every shared feature table (`is_shared: true` in `mlops.features`) now carries its own semantic version, following the same pattern as data contracts (§6):
- A breaking change (column removed, type changed, semantics changed) requires a version bump and notifies every project in `mlops.feature_lineage.downstream_model_ids` — surfaced as a blocker on those projects' dashboards, not discovered at the next training run.
- Non-breaking changes (new optional column, freshness improvement) don't require consumer action.
- A consuming project pins the feature version it trained against, so an owner's change doesn't retroactively alter a model's training lineage — only future training runs that opt into the new version are affected.

---

## 9. Model Serving

### 9.1 Real-time serving defaults (governance-by-default, applied to serving config)

Every real-time endpoint ships with two things **on by default, not optional**:

```yaml
resources:
  model_serving_endpoints:
    customer_churn_prediction:
      route_optimized: true                 # top-level field on the endpoint resource, NOT
                                             # nested under config/served_entities — confirmed
                                             # at Week 0 (§29) against the current bundle schema
      config:
        served_entities:
          - name: champion
            entity_name: retention_team.customer_churn_prediction_prod.model
            entity_version: "@champion"
        traffic_config:
          routes: [{served_model_name: champion, traffic_percentage: 100}]
      ai_gateway:
        inference_table_config:             # replaces the deprecated top-level
          enabled: true                     # `auto_capture_config` — same sub-fields,
          catalog_name: retention_team_customer_churn_prediction_prod   # confirmed at Week 0
          schema_name: monitoring
          table_name_prefix: inference_log
```

Turning either off requires an explicit, logged override (`mlops.projects.route_optimization_override_reason` / `inference_capture_override_reason`) — governance enforced structurally (design tenet 3), not left to a checklist item someone can silently skip. See [Create custom model serving endpoints](https://docs.databricks.com/aws/en/machine-learning/model-serving/create-manage-serving-endpoints) and [Declarative Automation Bundles resources](https://docs.databricks.com/aws/en/dev-tools/bundles/resources) for the `model_serving_endpoint` resource schema.

**Confirmed against current docs**: [Route optimization on serving endpoints](https://docs.databricks.com/aws/en/machine-learning/model-serving/route-optimization) states it can only be enabled at endpoint creation — it cannot be added to an existing endpoint later. This means the default-on posture must be set correctly from the very first deploy of a real-time endpoint; an override that later gets reversed (someone decides they do want route optimization after all) requires recreating the endpoint, not a config update, which the Bundle Service's deploy path needs to treat as a "replace," not an "update."

**Week 0 correction (this revision)**: two real errors in earlier revisions of this document, found by actually pulling the current schema rather than continuing to cite it at a summary level:
1. `route_optimized` is a **top-level field of the `model_serving_endpoint` resource** (sibling to `name`, `config`, `permissions`, `tags`) — earlier revisions had it nested inside `served_entities`, which is wrong. Fixed above.
2. `auto_capture_config` is **officially retired** — [its documentation page states so explicitly](https://docs.databricks.com/aws/en/machine-learning/model-serving/enable-model-serving-inference-tables) and recommends **AI Gateway-enabled inference tables** instead, "for its availability on custom model, foundation model, and agent serving endpoints" — explicitly including custom/classical models, not just LLM serving. The replacement path is `ai_gateway.inference_table_config`, confirmed via the bundle resource schema to have the *same* sub-fields (`catalog_name`, `schema_name`, `table_name_prefix`, `enabled`) just re-nested under `ai_gateway` — fixed above. This is exactly the kind of thing the Week 0 spike (§29) existed to catch before it shipped into real code.

### 9.2 Telemetry scaffolding — corrected mechanism

Rev. 3 assumed Inference Tables support an arbitrary `extra_payload` column for custom enrichment. Checked against current documentation ([Inference tables for monitoring and debugging models](https://docs.databricks.com/aws/en/machine-learning/model-serving/inference-tables), [Enable inference tables using the API](https://docs.databricks.com/aws/en/machine-learning/model-serving/enable-model-serving-inference-tables)): this field isn't confirmed to exist. What is confirmed: Inference Tables log the full request and response payload verbatim (each up to a 1 MiB limit), and the caller can set an optional `client_request_id` in the request body specifically to correlate a request across systems.

```python
# generated src/inference.py (excerpt)
from dsml_mlops_toolkit.telemetry import capture_telemetry

@capture_telemetry(
    log_feature_contributions=True,   # ties into Explainability, §12
    log_confidence_bucket=True,
    log_resolved_alias="champion",
)
def predict(model_input):
    return model.predict(model_input)
```

- `capture_telemetry` sets a `client_request_id` (a UUID) on every request.
- Domain-specific enrichment is written to a separate, app-owned Delta table, not a nonexistent Inference Table column:

```sql
CREATE TABLE mlops.telemetry_enrichment (
  client_request_id STRING,
  project_id STRING,
  feature_contributions MAP<STRING, FLOAT>,
  confidence_bucket STRING,
  resolved_alias STRING,
  computed_timestamp TIMESTAMP,
  CONSTRAINT pk_telemetry_enrichment PRIMARY KEY (client_request_id)
) COMMENT "Domain-specific serving telemetry, correlated to Inference Tables via client_request_id";
```

- Consumers (Lakehouse Monitoring, the Feedback Join Service, Portfolio Analytics) join the auto-captured Inference Table against `mlops.telemetry_enrichment` on `client_request_id` — one extra join, grounded in a real, documented mechanism instead of an assumed field.
- Anything meant to reach the caller synchronously (§12.2's sync-delivery explainability items) is included directly in `predict()`'s return value, since that's what gets logged as the response column verbatim — no separate write needed for those.
- This is the extent of "automatic integration" available for telemetry: most of it (request, response, status, latency, timestamp) is free once Inference Tables are on; the decorator only adds what Databricks can't infer on its own.

### 9.3 Batch

Batch models deploy as DAB `jobs.yml` entries (Databricks Workflows / Lakeflow Jobs), schedule taken directly from the interview's cron/frequency answer, **serverless by default** (§17).

### 9.4 Streaming Inference (in scope — third deployment pattern)

Alongside batch and real-time, the interview's inference-type question gains a third option: **streaming**, for continuous, high-frequency scoring of an already-governed stream/table (e.g., a Kafka topic already landing to a Bronze/Silver Delta table, or a DLT pipeline someone else on the team owns). The app deploys the *scoring* job, not the ingestion pipeline:

```yaml
resources:
  jobs:
    customer_churn_streaming_scorer:
      continuous: {pause_status: UNPAUSED}    # top-level field on the job resource — NOT
                                                # nested under a "trigger" key. `continuous`
                                                # and `schedule` are mutually exclusive on a job.
                                                # Confirmed at Week 0 (§29); earlier revisions
                                                # had this wrapped in a nonexistent `trigger:` key.
      tasks:
        - {task_key: score_stream, notebook_task: {notebook_path: ../src/stream_score.py}}
```

`stream_score.py` reads via `spark.readStream` from the declared source table (must already exist and be UC-governed — a data contract still applies to it, §6), resolves `@champion` from the UC registry, scores each micro-batch, and writes to an output Delta table using `writeStream`. Because the output is a normal Delta table, the same telemetry scaffold (§9.2) and Lakehouse Monitoring attachment (§13) apply automatically — streaming inference doesn't need its own separate observability story.

**Explicit boundary, unchanged from the original non-goal**: the app does not author the *upstream* ingestion pipeline (no DLT/Lakeflow pipeline authoring). It assumes a governed source stream/table already exists, owned by whoever built it.

**Confirmed at Week 0**: `continuous` is a direct top-level field of the job resource (sibling to `tasks`, `schedule`, `name`), not nested under a `trigger` key as earlier revisions of this document had it — corrected above.

### 9.5 Lookup services & AutoML
Lookup services are a Feature Serving endpoint (§8), not a separate infrastructure concept — simplifies the original spec's bespoke `LookupServiceConfig` implementation. **AutoML** is offered as an *optional* accelerant at the "model type" interview step ("Want a baseline model trained automatically before you start?") — purely additive, the DS's own training code remains authoritative; AutoML output is just a first commit they can keep or discard. Confirmed against current docs ([What is AutoML?](https://docs.databricks.com/aws/en/machine-learning/automl/)): Databricks AutoML already generates SHAP-based explainability as part of its output notebooks — a direct synergy with §12.1's training-time explainability requirement, meaning an AutoML-accelerated project can satisfy that gate essentially for free rather than needing a separate explainability step bolted on afterward.

---

## 10. Label Quality & Feedback Loops

Addresses `black.md`'s Label Quality item and the "Data Availability Retraining" trigger, neither of which had a mechanism before rev. 3.

### 10.1 Declaring a label source
Any project where ground truth arrives after prediction (churn realized 30 days later, fraud confirmed after investigation) declares a **label source** in its data contract (§6): the table/column where the outcome lands, an expected `label_latency_days`, and its own quality rules (nullability, valid-value-set, duplicate-key checks) — a broken labeling process shouldn't silently poison retraining.

### 10.2 Feedback Join Service
A scheduled service (same family as the Reconciliation Service, §3) joins predictions from the Inference Table (§9.1) against the label source once available, keyed by the `client_request_id` captured at serving time (§9.2):

```sql
CREATE TABLE mlops.label_feedback (
  prediction_id STRING,
  project_id STRING,
  model_version_id STRING,
  predicted_value STRING,
  actual_label STRING,
  label_source_table STRING,
  prediction_timestamp TIMESTAMP,
  label_arrived_timestamp TIMESTAMP,
  latency_days FLOAT,
  correct BOOLEAN,
  CONSTRAINT pk_label_feedback PRIMARY KEY (prediction_id)
) COMMENT "Closes the loop between predictions and eventual ground truth";
```

### 10.3 What this unlocks
- **Real accuracy**: `mlops.model_performance` gains a `live_accuracy` field computed from this table, not only the training-time holdout number.
- **A native synergy**: Databricks' Lakehouse Monitoring `InferenceLog` profile type natively accepts an optional `label_col` (confirmed against current docs, §13). Once `mlops.label_feedback` has joined predictions to ground truth, that joined view can be fed back as the monitored table's label column — so Lakehouse Monitoring computes real accuracy/calibration natively, not only via the custom `live_accuracy` field. The custom field remains for domain-specific metrics Lakehouse Monitoring doesn't know about; the native path is used wherever it can be.
- **Data Availability Retraining** becomes a real, automatic trigger: once `mlops.label_feedback` accumulates N new labeled examples (or X% of training-set size) since the last training run, the Reconciliation Service flags a retrain candidate — replacing what was previously only a manual button.
- **Business Impact Metrics** (§14.2) reuse this exact join mechanism — a business outcome is just another form of delayed ground truth with a dollar value attached.

---

## 11. Human-in-the-Loop Review

Distinct from approval gates on model *promotion* (§15) — this is per-*prediction* review for high-stakes individual decisions.

### 11.1 Configuration
A project-level flag `requires_human_review` (defaulting on for any model whose risk tier's policy pack requires it, §20) plus an optional `hitl_confidence_threshold` (route only low-confidence predictions to review, rather than all of them).

### 11.2 Review mechanism — concurrency-safe

```sql
CREATE TABLE mlops.hitl_reviews (
  prediction_id STRING,
  project_id STRING,
  presented_timestamp TIMESTAMP,
  reviewer_email STRING,
  decision STRING COMMENT "approved, overridden, rejected",
  overridden_value STRING,
  decision_timestamp TIMESTAMP,
  comment STRING,
  CONSTRAINT pk_hitl_reviews PRIMARY KEY (prediction_id)
) COMMENT "Per-prediction human review queue for high-stakes decisions";
```

A new page (`pages/09_hitl_review.py`) surfaces pending predictions alongside the model's explanation (§12) so the reviewer sees *why* the model predicted what it did, not just the raw output.

A review decision write uses a Delta conditional MERGE — `MERGE ... WHEN MATCHED AND decision IS NULL THEN UPDATE` — so two reviewers opening the same pending prediction can't both submit a decision; the second gets a clear "already decided by {reviewer}" rather than a silent overwrite. This reuses Delta's native conflict detection (design tenet 6) rather than a hand-rolled lock.

### 11.3 Synchronous vs. asynchronous
- **Synchronous**: the serving wrapper returns a `pending_review` status; the consuming system waits for a decision. Appropriate for genuinely low-throughput, high-stakes decisions (`black.md`'s own framing — "high-risk or judgment-heavy," not high-QPS).
- **Asynchronous**: the prediction is acted on immediately but flagged for review within an SLA window, with a defined override/reversal path. Used where synchronous review isn't operationally feasible.

Which mode applies is a per-project interview answer, not a global platform decision.

### 11.4 HITL Applicability & Human-Oversight Documentation (resolves the HITL/streaming contradiction)

A risk tier can require human oversight (§20.3) on a project whose deployment pattern (streaming, §9.4) is structurally incompatible with synchronous per-prediction review. Resolved by presenting HITL as one of several documented human-oversight mechanisms, chosen to fit the deployment pattern, rather than a single sync-only flag:

| Mechanism | Fits | What's required |
|---|---|---|
| Synchronous per-prediction review | Real-time, low-QPS | §11.2's queue, blocking response |
| Asynchronous review within an SLA | Real-time, moderate-QPS | §11.2's queue, override/reversal path (§11.3) |
| Statistical sampling / spot-check review | Streaming, high-QPS | A defined sample rate, same review queue, applied to a subsample |
| Automated escalation on threshold breach | Streaming, high-QPS | Only low-confidence/anomalous predictions route to review; the rest proceed automatically |
| Periodic batch audit | Batch, streaming | A scheduled retrospective review of a sample from the prior period's Inference Table |

When a project's risk tier requires human oversight but the selected deployment pattern rules out synchronous review, the interview requires a **Human Oversight Design** documentation step: which mechanism applies, why, and what compensating control covers the gap between "every prediction reviewed" and what's actually happening. This document becomes part of the model card (§12.3) and is itself subject to the same legal/business approval gate that would have covered synchronous HITL (§15.3) — the org still signs off on how oversight works, even when it isn't literally "a human looks at every prediction." The previously-silent contradiction becomes an explicit, governed decision.

---

## 12. Explainability

### 12.1 Training-time (global) explainability
The evaluate.py-style job computes SHAP values (default) or LIME (DS-selectable alternative) on a holdout sample, logged as MLflow artifacts tied to the model version — surfaced on every project's dashboard regardless of HITL status.

### 12.2 Serving-time (per-prediction) explainability — per-item sync/async, not per-project on/off

A single per-project flag computing SHAP inline directly conflicts with §9.1's route-optimization default, since full SHAP (and especially KernelExplainer for non-tree models) can add hundreds of milliseconds to seconds of latency. Instead, explainability delivery is configured per item:

```yaml
# project config excerpt
explainability:
  method: shap  # or lime
  items:
    - name: confidence_bucket
      delivery: sync         # cheap, precomputed calibration lookup — safe inline
    - name: top_3_feature_contributions
      delivery: sync         # only safe for tree models (fast TreeExplainer)
    - name: full_shap_vector
      delivery: async         # expensive regardless of model type
    - name: counterfactual_example
      delivery: async
  sync_latency_budget_ms: 50   # a sync item exceeding this is auto-demoted to async
```

- **Sync items** are computed inline by the telemetry decorator (§9.2) and returned in the same response — reserved for genuinely cheap items.
- **Async items** are computed by a background job (same scheduling family as the Feedback Join Service) and attached via `client_request_id` (§9.2) once ready.
- The `sync_latency_budget_ms` guard automatically demotes a misconfigured "sync" item (e.g., `full_shap_vector` marked sync against a non-tree model) to async — a structural safety net, not just a documentation warning that can be ignored.
- For synchronous HITL (§11.3), only sync-delivered items are guaranteed available at review time; a project needing full-SHAP-at-review-time either accepts a short wait or restricts itself to sync-only items. This is a real, resolvable design choice instead of a silent latency risk.

### 12.3 Model Card Assembly

- `docs/MODEL_CARD.md` is **assembled, not hand-written**, at each promotion: training-time explainability (§12.1) → Factors section; fairness test results (from UC tags, §7.4) → Factors section; `live_accuracy`/drift status (§13) → Metrics section; business impact (§14.2), once available → Metrics section; Human Oversight Design (§11.4), if applicable → a new Governance section; approval chain (§15.1) and risk tier (§20.1) → Governance section.
- Assembly runs as a step in the Approval Saga Engine (§15.2, between steps 6 and 7) — the model card is regenerated and committed alongside the promotion, not maintained by hand.
- "Model card completeness" (§14.1's Governance Coverage metric) becomes a mechanical check (did assembly succeed, are applicable sections populated), not a subjective audit.

Explainability and human review reinforce each other deliberately: a human asked to approve or override a high-stakes prediction without seeing why the model made it isn't actually able to do meaningful review.

### 12.4 Counterfactual Explanations (new)

Not previously designed, though `counterfactual_example` appeared as an item name in §12.2's example config without any actual mechanism behind it. Worth doing properly: a counterfactual explanation answers "what's the smallest change to this input that would have produced a different (favorable) prediction?" — e.g., "if income had been $4,000 higher, this application would have been approved." This is a genuinely different explanation family from SHAP/LIME's feature-contribution framing, and arguably more useful in two specific ways this document already cares about:

- **HITL review (§11)**: a reviewer deciding whether to override a denial benefits more from "what would change the outcome" than from a feature-importance ranking alone — it's directly actionable.
- **Regulatory relevance for credit-decisioning models specifically**: adverse action notice requirements (e.g., ECOA/Regulation B in the US) require giving a rejected applicant *specific reasons* for the decision. A counterfactual-style explanation is a well-established approach for generating compliant adverse-action reasons, and this is exactly the kind of use case §20's SR-11-7-style worked example (credit/capital decisions) is about. This document doesn't implement adverse-action-notice generation as a feature — that's a legal/compliance-owned template, not an ML platform concern — but the counterfactual explanation this section produces is the input such a template would need.

**Mechanism**: computed using an open-source library (e.g., DiCE or Alibi) run inside a scheduled Databricks job — **this is not a Databricks-native capability**, so unlike the rest of this document there's no first-party Databricks documentation link for the method itself; only for where it runs (a standard job, same as any other async computation in §12.2).

**Delivery**: always `async` (§12.2) — counterfactual search is meaningfully more expensive than SHAP/LIME (it's an optimization/search problem, not a single forward computation), so it's never offered as a sync item regardless of model type. It's computed by the same background job family as other async explainability items and joins to `mlops.telemetry_enrichment` (§9.2) via `client_request_id`, and feeds the model card (§12.3) and HITL review UI (§11.2) exactly like other async explainability items.

```yaml
# extends the §12.2 example
explainability:
  items:
    - name: counterfactual_example
      delivery: async         # always async, regardless of model type
      method: dice            # or alibi — org-configurable, not Databricks-native
```

---

## 13. Monitoring & Observability

- **Lakehouse Monitoring** attaches directly to each project's Inference Table (§9.1/9.4) at deploy time, using the contract's declared fairness attributes as slicing columns — replaces hand-rolled KS-statistic drift detection. **Confirmed against current docs**: `w.quality_monitors.create()` with an `InferenceLog` profile (`timestamp_col`, `granularities`, `model_id_col`, `problem_type`, `prediction_col`, optional `label_col`) is the real API shape, requiring `databricks-sdk >= 0.28.0`. See [Create a monitor using the API](https://docs.databricks.com/aws/en/lakehouse-monitoring/create-monitor-api) and the [Lakehouse Monitoring overview](https://docs.databricks.com/aws/en/lakehouse-monitoring/).
- **Note on API churn (evidence for design tenet 8)**: current documentation shows the underlying API surface has already been through at least one naming transition (an older `quality_monitors` path marked deprecated in favor of newer "data profiling" documentation) even within Databricks' own docs. Re-verify the exact API before implementation — don't build against this document's snippets as frozen fact.
- **SQL Alerts** on the monitor's generated metric tables implement the standard alert set (endpoint down, drift breach, quality drop); the app's routing/escalation logic layers on top for destination fan-out and severity.
- Custom/domain-specific metrics (e.g., "true positive rate on fraud") remain app-defined, computed in a scheduled job, logged to `mlops.model_performance` — enriched with `live_accuracy` from §10.3.
- Fairness metrics (demographic parity, equalized odds) computed in the evaluate.py-style job, logged to MLflow, mirrored into `mlops.model_performance`.
- **Genie Spaces**: auto-provisioned per project, scoped to its monitoring/cost/status tables (via Metric Views, §6) — confirmed programmatically creatable via the Genie Spaces [`createspace` REST API](https://docs.databricks.com/api/workspace/genie/createspace) (see also [Use the Genie Spaces API](https://docs.databricks.com/aws/en/genie/conversation-api)) — natural-language queries for the business_stakeholder persona. **Open architectural question, see §29**: Genie Spaces do not appear as a native resource type in current Declarative Automation Bundles documentation, meaning provisioning likely happens via this REST API directly, outside the bundle's declarative plan/deploy/destroy lifecycle.
- **AI/BI Dashboards (Lakeview)**: auto-generated per project as the primary shareable dashboard artifact; Streamlit either embeds or deep-links to it rather than every metric being hand-built in Plotly.

---

## 14. Program & Portfolio Analytics

The single biggest gap identified against `black.md`'s Metrics/Roadmap pillar (`k`) in the original adversarial review. Every metric below is a rollup over data the control plane already has; this section defines the aggregation, not new raw collection (except business impact, §14.2, which needs the declaration described there).

### 14.1 Portfolio dashboard

`pages/10_portfolio_analytics.py` — distinct from the project roster (`pages/01_projects.py`) — aggregates across the whole portfolio:

| Metric family | Computed from | `black.md` ref |
|---|---|---|
| Speed | `mlops.audit_logs` timestamps (approval → deploy) | Speed Metrics |
| Reliability | `mlops.bundle_deployments` failure rate, rollback events | Reliability Metrics |
| Quality coverage | % of production models with an active Lakehouse Monitor attached | Quality Metrics |
| Governance coverage | % of production models with complete model card + lineage (§12.3), penalized by revalidation-due status (§20.5) | Governance Metrics |
| Reuse | Feature Catalog (§8.5) consumption counts, template_version adoption spread | Reuse Metrics |
| Cost | `mlops.cost_tracking` rollup (§17), control-plane overhead shown separately (§17.4) | Cost Metrics |
| Business impact | `mlops.business_impact` (§14.2), shown with a comparability indicator (§14.4) | Business Impact Metrics |
| Interview Speed | `mlops.interview_telemetry` (§26.1) | — (new, app-usability metric, not in `black.md` but justified by its own Success criterion) |
| Workspace Capacity | Job/endpoint/concurrent-run counts vs. known limits (§19.2) | — (new, operational health, not in `black.md`) |

### 14.2 Business impact / outcome attribution

Reuses the Feedback Join Service (§10.2) rather than a separate mechanism — a business outcome is just another form of delayed ground truth with a dollar value attached. A project declares a `business_value_fn` mapping (predicted, actual) → USD (e.g., "customer retained after a targeted offer = +$X LTV saved," "fraud caught = +$Y loss avoided," "false-positive intervention = –$Z wasted cost"):

```sql
CREATE TABLE mlops.business_impact (
  project_id STRING,
  period_start DATE,
  period_end DATE,
  revenue_lift_usd FLOAT,
  loss_avoided_usd FLOAT,
  automation_rate_pct FLOAT COMMENT "% of decisions made without human review",
  risk_reduction_notes STRING,
  computed_timestamp TIMESTAMP
) COMMENT "Business outcome attribution, rolled up into Portfolio Analytics (§14.1)";
```

This directly answers `black.md`'s Success criterion "Higher Trust In Decision" — trust is easier to earn when a model's actual dollar impact is visible, not just its offline accuracy.

### 14.3 Roadmap Phases
`black.md`'s Roadmap Phases (Foundation → Automation → Monitoring → Optimization → Scale) describe the *org's adoption journey*, not a system capability. The portfolio dashboard surfaces this as a simple, org-configured banner (which phase the program currently claims to be in) rather than a computed metric — there's no way to derive "we are in the Optimization phase" from data, and pretending otherwise would misrepresent what's actually being measured.

### 14.4 Metric Comparability & Business-Value-Function Governance

Rolling up "Business Impact" or "Governance Coverage" across projects using different fairness frameworks, risk tiers, and — critically — different, per-project `business_value_fn` definitions of unaudited rigor risks producing a portfolio number that looks authoritative but isn't comparable. Two mitigations:

1. **`business_value_fn` is governed like a policy pack, not arbitrary code.** It's authored as a declarative mapping (predicted, actual) → USD with required fields (assumption source, last-reviewed date, reviewer), reviewed via PR — the same discipline as §20.3's policy packs — rather than editable ad hoc by whoever wants their number to look better.
2. **Portfolio Analytics displays a confidence/comparability indicator alongside every rolled-up business-impact figure**, not a single blended number. A project whose `business_value_fn` hasn't been reviewed in over a year, or was never reviewed at all, is flagged distinctly. Leadership sees "$X, high confidence across N projects" and "$Y, low confidence across M projects" as separate figures, never summed into one misleadingly precise total.

---

## 15. Approval Workflow & Governance

### 15.1 Approval write-path — concurrency-safe

Submitting a decision performs, atomically, via Delta conditional MERGE (design tenet 6) rather than a plain insert-then-update:

```
MERGE INTO mlops.approvals
USING (SELECT ... ) AS new_response
ON mlops.approvals.approval_id = new_response.approval_id
WHEN MATCHED AND approved_count < required_count THEN UPDATE ...
```

A second reviewer's simultaneous submission that would push the count over `required_count` fails the match condition and returns a clear "gate already satisfied" response, rather than both writes succeeding and silently over-counting. If this completes the gate: update `mlops.approvals.status`; if it's the last required gate, trigger the Bundle Service via CI/CD (never directly from the Streamlit process) using the plan file generated for this promotion (§5.2); write `.mlops/approval_record.json` via a PR — recording the plan file's path and hash alongside the approver, timestamp, and manifest hash — so the Saga Engine (§15.2) always deploys exactly what was reviewed.

### 15.2 Approval Saga Engine

```
Saga: PromoteToProduction
  1. Verify all approval gates satisfied           (read-only)
  2. bundle deploy --plan {reviewed plan.json} -t prod   ⤺ on failure: abort, no further steps
  3. Register model version into prod catalog       ⤺ on failure: bundle deployed, no traffic
                                                       change yet — safe, alert MLOps
  4. Set @challenger alias + tags (§7.4), canary     ⤺ on failure: re-deploy previous bundle
     traffic_config
  5. Monitor canary metrics window                   ⤺ on threshold breach: auto re-point
                                                       @champion back, no promotion
  6. Promote @challenger → @champion (+ tags)         ⤺ on failure: manual rollback runbook
  6.5. Assemble model card (§12.3)                    ⤺ on failure: log and alert, does not
                                                       block promotion — a missing model card
                                                       is a Governance Coverage penalty (§14.1),
                                                       not a rollback trigger
  7. Write approval_record.json + audit log entry     (always runs, even on partial failure, to
                                                       record exactly what state was reached)
```

### 15.3 Model risk tiering as a governance input
Every project's interview captures a risk tier (§20) which directly parameterizes which gates in this saga are mandatory vs. skippable-with-override, and whether human-in-the-loop review (§11) defaults on.

### 15.4 Approval Revocation & Remediation

Rev. 1–3 had no path for "this approval was wrong" — only for "this model version is wrong" (§15.2's rollback). Because `mlops.approvals` is append-only (consistent with audit-log immutability), a bad approval is never edited or deleted. Instead:
- A **revocation request** is a new record type that doesn't erase the original approval — it records a countervailing decision ("approval X revoked, reason Y, revoked by Z") and, if the promotion it enabled is still live, automatically triggers the same rollback saga (§15.2) used for a bad model version.
- Revocation itself requires its own approval from a role distinct from whoever made the original approval, reusing the segregation-of-duties principle already in the original spec's SOX section — revocation can't be used to quietly undo governance either.

---

## 16. Secrets & Service Principals

Each project gets a scoped service principal limited to its own dev/staging/prod schemas and its own job/endpoint resources — never a personal token, never a shared admin identity. Databricks secret scopes hold non-Databricks secrets (GitHub token, Slack webhook). Databricks-to-Databricks auth (jobs calling endpoints, CI/CD deploying bundles) uses OAuth M2M with the service principal, not a stored PAT. Rotation policy (365-day default, 7-day grace period) unchanged from the original spec for external secrets.

---

## 17. Compute & Cost Efficiency

### 17.1 Serverless-first
DAB `jobs.yml` defaults every job (training, batch, streaming, retraining) to serverless compute (`environments: - environment_key: default`) rather than specifying `new_cluster` blocks — removes an entire class of cluster-sizing decisions from the interview by default.

### 17.2 Serverless SQL Warehouse
Backs the control plane's own StateService/ReconciliationService/Feedback Join Service queries — fast start, no idle cost.

### 17.3 Compute policies
Generated and attached per project for cases genuinely needing classic clusters (GPU training, specific instance types not yet available serverless) — the interview asks "does your training need specialized compute?" and only then surfaces classic-cluster options, bound by a project-scoped policy (max node count/instance type) that structurally prevents runaway dev-cluster spend rather than only alerting after the fact.

`mlops.cost_tracking` is populated by the Reconciliation Service querying `system.billing.usage`, joined against DAB resource tags (every bundle-created resource is tagged with `project_id`) — not estimated or hand-computed. Budget alerts remain, layered on top of the structural compute-policy prevention above.

### 17.4 Control-Plane Budget (distinct from per-project budgets)

The Reconciliation Service, Feedback Join Service, Portfolio Analytics Service, and Feature Catalog indexing all run cross-project queries whose cost scales with the whole portfolio, not any one project — and this never showed up in §17.1–17.3's per-project cost design.

- Every control-plane-owned job/warehouse is tagged `component: control_plane` (distinct from any `project_id` tag), so `system.billing.usage` reconciliation reports control-plane overhead as its own line item.
- The control plane gets its own budget threshold (warning/critical USD/month), surfaced in Portfolio Analytics (§14.1) as a dedicated tile — "cost of running the control plane" shown separately from "cost of the models it governs."
- Because this cost should scale sub-linearly with project count in an efficient implementation (most reconciliation work should be incremental, not a full-portfolio rescan each run), **cost-per-project trending upward over time is itself an alert condition** — a signal of a query regressing from incremental to full-scan, not just "we have more models now."

---

## 18. Network & Deployment Security

- **Private Link / VPC endpoints** for workspace-to-metastore and workspace-to-control-plane traffic — no public internet exposure path for a production deployment. See [Manage private access settings](https://docs.databricks.com/aws/en/security/network/classic/private-access-settings).
- **IP access lists** on the workspace and, where supported, directly on the Databricks App hosting the control plane itself. See [Manage IP access lists](https://docs.databricks.com/aws/en/security/network/front-end/ip-access-list), [Configure IP access lists for workspaces](https://docs.databricks.com/aws/en/security/network/front-end/ip-access-list-workspace), and — confirmed to exist as its own dedicated page — [Configure networking for Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/networking) specifically. **Two confirmed caveats worth designing around**: (1) this feature requires the **Enterprise pricing tier** — worth confirming the target workspace's tier before assuming it's available; (2) IP access lists only govern traffic over the public internet — "private IP addresses from PrivateLink traffic cannot be blocked by IP access lists" per current docs, so Private Link and IP access lists are complementary, not overlapping, controls. Restricting Private Link traffic itself requires the separate `ENDPOINT` access-level setting on the workspace's private access settings object, not the IP access list feature.
- **Customer-managed VPC / network configuration** as a deployment-pattern option for orgs with existing network security requirements, layered onto the existing single/dual/multi-cloud deployment patterns rather than replacing them.
- **Metastore/catalog isolation**: environment-scoped catalogs (§7) already isolate dev/staging/prod; the strictest compliance postures can extend this to separate metastores per region/compliance boundary.
- **Egress/supply-chain control**: generated projects run `pip-audit` (existing testing pyramid gate) against packages pulled from a private PyPI mirror/allow-list in regulated deployments, rather than an unrestricted public PyPI.

---

## 19. Scaling to Portfolio Scale (100+ Models)

The single-workspace, catalog-per-environment default (§5.1) was chosen for simplicity, but it's the one choice most in tension with the stated ambition of being *the* control plane for a whole org's portfolio.

### 19.1 What's actually documented as a limit

Grounded in current Databricks resource-limits documentation (verify again before relying on these at implementation time — these change): see [Resource limits](https://docs.databricks.com/aws/en/resources/limits), [Model Serving limits and regions](https://docs.databricks.com/aws/en/machine-learning/model-serving/model-serving-limits), and the [job rate limit knowledge-base article](https://kb.databricks.com/jobs/job-rate-limit).
- **Job creation** is rate-limited to 1,000/hour by default (extendable to 2,000 via Databricks support). This is a *creation rate*, not a cap on total existing jobs — it matters for bulk operations (migrating many brownfield projects at once, §21) far more than steady state, since 100 models × roughly 2-3 jobs each (train/retrain/batch-or-stream) is only ~200-300 total jobs, well under any documented cap.
- **Model Serving endpoint limits** exist per workspace/region but aren't published as a fixed public number — Databricks' own guidance is to engage your account team as usage grows. This is the one that actually matters at "100 models": a real-time endpoint per model, per environment, unconsolidated, could plausibly approach a real ceiling well before 100 models.

### 19.2 Concrete strategies

1. **Consolidate endpoints, don't multiply them.** Model Serving already supports multiple `served_entities` per endpoint (§7.2's champion/challenger pattern uses exactly this). The same mechanism extends to hosting multiple *different* models behind fewer endpoints where latency/isolation requirements allow — the Bundle Service should default to this for low-QPS models sharing a team/catalog, rather than treating one endpoint per model as a rigid rule.
2. **A Capacity Service**, run alongside the Reconciliation Service, tracks workspace-level resource utilization (job count, endpoint count, concurrent run count) against known limits and surfaces a **Workspace Capacity** tile in Portfolio Analytics (§14.1) — with an internally-set alert threshold (proposed default: flag at 50 production real-time endpoints, well before any plausible hard ceiling) rather than discovering a limit by hitting it.
3. **A documented "graduation" playbook** for splitting from single-workspace to dual/multi-workspace (§5.1's already-supported alternate pattern) once the Capacity Service flags sustained pressure — written now, not improvised under pressure later.
4. **Naming collision prevention**: the Bundle Service validates global name uniqueness (job names, endpoint names, catalog names) before calling `bundle deploy`, failing fast in the interview/PR stage rather than at the Databricks API call.

### 19.3 The honest bottom line

Nothing above guarantees the single-workspace default scales cleanly to 100+ models without intervention — it guarantees the org sees the pressure coming, via the Capacity Service, with enough runway to act, rather than discovering a limit as a production incident. Whether 100 models comfortably fits one workspace depends on real per-model resource needs and account-specific quotas that aren't knowable in the abstract. §19.2's playbook exists precisely because the honest answer is "it depends — so build the instrumentation to find out early," not a number this document can responsibly promise.

---

## 20. Model Risk Management & Regulatory Tiering

### 20.1 Risk tier as a first-class project attribute
The interview requires: **"What is this model's risk tier?"** against **org-authored tier definitions only**. No named regulatory framework ships built in — the default is a minimal, generic three-tier mechanism (`tier_1`/`tier_2`/`tier_3`).

Two well-known shapes are documented as **worked examples**, not built-in packs:
- *SR 11-7-style materiality tiering*: Tier 1 (high materiality — credit/capital decisions) → independent validation function sign-off + annual revalidation; Tier 2 (moderate) → standard approval gates; Tier 3 (low/internal tooling) → lighter gate set.
- *EU AI Act risk categories*: unacceptable (interview refuses to scaffold it), high-risk (Annex III-style use cases → conformity-assessment-style technical documentation, mandatory human-oversight gate — ties directly to §11, extended logging retention), limited-risk (transparency obligations only), minimal-risk (baseline gates only).

### 20.2 Data model
```sql
ALTER TABLE mlops.projects ADD COLUMNS (
  risk_tier STRING COMMENT "org-defined tier, e.g. tier_1/tier_2/tier_3",
  regulatory_frameworks ARRAY<STRING> COMMENT "policy packs applied"
);

CREATE TABLE mlops.policy_packs (
  policy_pack_id STRING,
  name STRING,
  required_approval_gates ARRAY<STRING>,
  required_contract_fields ARRAY<STRING>,
  min_documentation_fields ARRAY<STRING>,
  audit_log_retention_days INT,
  revalidation_frequency_days INT,
  on_revalidation_due STRING COMMENT "warn, block_new_traffic, or block_all_traffic (§20.5)",
  allows_override BOOLEAN,
  CONSTRAINT pk_policy_packs PRIMARY KEY (policy_pack_id)
) COMMENT "Declarative regulatory/risk policy packs, selected per project";
```

Multiple packs can be active per project; the Saga Engine (§15.2) takes the union of required gates.

### 20.3 Policy pack authoring
Authored as YAML, reviewed via PR into the control plane's own repo (not an in-app editor) — the same "GitHub is source of truth" principle applied to governance rules themselves, not just project code:

```yaml
# policy_packs/generic_tiering.yaml (shipped default — the only pack installed out of the box)
policy_pack_id: generic_tiering_v1
tiers:
  tier_1: {required_approval_gates: [code_review, business_approval], revalidation_frequency_days: null, allows_override: true}
  tier_2: {required_approval_gates: [code_review, legal_review, business_approval], revalidation_frequency_days: 365, allows_override: true}
  tier_3: {required_approval_gates: [code_review, legal_review, business_approval, security_review], revalidation_frequency_days: 180, allows_override: false}
# Orgs copy this file, rename tiers/gates to match SR 11-7, EU AI Act, or any internal
# framework, and PR it in as their own pack — the app ships the mechanism, not the framework.
```

### 20.4 GDPR / data-subject deletion
Because training data lineage is UC-native (§6), a deletion request can walk `system.lineage` to find every downstream table/feature/model version touched by a given source row. Not fully automated, but tractable.

### 20.5 Revalidation Trigger Mechanism

`revalidation_frequency_days` (§20.2/§20.3) was previously a schema field with no described behavior. Fixed: the Reconciliation Service checks every production model version's `promoted_timestamp` (from UC tags, §7.4) against its policy pack's `revalidation_frequency_days`. When due:
- The model is flagged "revalidation due" on its project dashboard and counts *against* Governance Coverage (§14.1) — not just "eventually."
- The policy pack's `on_revalidation_due` field determines severity — surfacing a warning, blocking further canary promotion until revalidation completes, or (strictest tiers) actively paging MLOps.
- Revalidation is a re-run of the applicable approval gates (§15.2, entered at step 1) against the currently live version — it doesn't require retraining, only re-review.

---

## 21. Audit & System-of-Record Integrity

- `mlops.audit_logs` remains authoritative for *app-level* decisions (approvals, config changes, overrides) — no other system of record for these.
- Infra-level events (job runs, table queries, permission changes) are **not** duplicated into `mlops.audit_logs`; they're queried live from `system.access.audit` at read time, joined by `project_id`/`resource_id`. Avoids duplicating Databricks' own immutable audit log. See system tables: [billing/usage](https://docs.databricks.com/aws/en/admin/system-tables/billing), [audit logs](https://docs.databricks.com/aws/en/admin/system-tables/audit-logs), [lineage](https://docs.databricks.com/aws/en/admin/system-tables/lineage).
- **Concurrency**: project config edits use optimistic concurrency (`config_version` check-and-set) so two people editing the same project's interview responses don't silently clobber each other. (Approval and HITL writes use the stronger Delta-MERGE pattern, §15.1/§11.2, since those are higher-stakes concurrent surfaces.)
- **Transactionality**: any multi-resource creation is a saga with defined compensation — not just promotion (§15.2), but initial project scaffolding itself (repo + bundle + UC schemas + service principal), so a failure at step 3 of 4 doesn't leave orphaned resources.
- **Brownfield adoption**: the interview gains an "import an existing model/pipeline" path distinct from "create new" — it inventories an existing UC-registered model and GitHub repo, backfills a best-effort `mlops.projects`/`mlops.model_versions` record, and flags any governance gaps (missing contract, no fairness test history) as a remediation checklist rather than silently pretending the project was born compliant.
- **Schema migrations**: `mlops.*` tables versioned via numbered SQL migration files applied by `db/setup.py` (already the pattern in the current repo) — formalized rather than ad hoc.
- **DR/backup**: UC tables get standard Delta time-travel + a documented restore runbook. The control plane's real DR story is that it can be *rebuilt* from GitHub (bundles) + UC (models/data/feature tables) + system tables — its own `mlops.*` tables are a rebuildable index, not irreplaceable data. This should be tested (a "rebuild the control plane from scratch" drill), not just asserted.
- **The control plane app has its own SDLC**: its own dev/staging/prod, CI/CD, and approval gate for schema/template changes — a control plane with no governance over its own changes is a single point of ungoverned failure for everything it governs.

### 21.1 Reconciliation Self-Monitoring

Nothing previously checked whether the Reconciliation Service, Feedback Join Service, and Portfolio Analytics Service were themselves producing *correct* output — especially important because their entire premise is avoiding duplicated state (design tenet 1), which means there's no independent copy to cross-check against if the reconciliation logic itself breaks. Fixed: each scheduled job emits its own health signal — row-count deltas per run, a checksum of key aggregates, and a "last successful run" timestamp per table it maintains. A SQL Alert (reusing §13's native alerting, design tenet 6) fires if a reconciliation job hasn't materially changed its output in longer than its expected cadence, or if a join that previously matched rows starts returning zero matches — both are strong signals of an upstream Databricks system-table schema change silently breaking things, not just "nothing happened this period."

### 21.2 Retirement/Teardown for New Subsystems

Phase 6 archival previously only thought about models and inference tables. Retirement now explicitly enumerates every subsystem with project-scoped state: label feedback jobs and their output (§10), HITL queue entries (§11), business-impact rollups (§14.2), and feature-catalog listings (§8.5) are archived alongside the model, not left dangling.

---

## 22. CI/CD Pipeline Generation

Generated GitHub Actions workflows call the Bundle Service's CLI wrapper instead of raw `mlflow`/SDK calls:

```yaml
- name: Deploy bundle to staging
  run: databricks bundle deploy -t staging
  env:
    DATABRICKS_CLIENT_ID: ${{ secrets.STAGING_SP_CLIENT_ID }}
    DATABRICKS_CLIENT_SECRET: ${{ secrets.STAGING_SP_CLIENT_SECRET }}

- name: Register model version to staging catalog
  run: python scripts/register_model.py --catalog ${{ vars.STAGING_CATALOG }}
```

The original testing pyramid (lint, security scan, unit/integration tests, fairness tests, 100% coverage gate) is unchanged and still runs before this step; policy-pack-required gates (§20) are additive checks in the same pipeline.

---

## 23. API Layer

The Databricks App exposes a **REST API** (`/api/v1/...`, same app process) so the control plane is queryable/writable by more than a human clicking Streamlit:

- `GET /api/v1/projects/{id}` — full project state (config, current aliases+tags, approval status, cost, risk tier)
- `GET /api/v1/projects/{id}/audit` — merged app + system-table audit view
- `POST /api/v1/projects/{id}/approvals/{gate}` — submit an approval decision (usable by a Slack approval bot, not just the Streamlit form)
- `GET /api/v1/models/{uc_full_name}/aliases` — current alias→version map
- Auth: OAuth passthrough for interactive callers; service-principal OAuth for automation

A store only the Streamlit UI can read or write is not a system of record — it's a UI. This is what earns the label.

**v1 scope note**: this endpoint ships in v1 specifically so it's a stable integration point, but the Slack/Teams bot that would call it is deferred to v1.1 (§0) — the write-path (§15.1) needs to be proven out in the Streamlit UI first.

---

## 24. Application Structure (mapping to current code)

| Area | Current | Change |
|---|---|---|
| `services/generator_service.py` | Calls SDK directly, imports fragile external `databricks_mlops` package | Rewritten as **Bundle Service** (§5.2): renders DAB templates, shells out to `databricks bundle` CLI using structured plan/deploy, not text-parsing |
| `services/state_service.py` | Direct UC SQL CRUD | Gains **Reconciliation Service** sibling (+ self-monitoring, §21.1) |
| `pages/03_approvals.py` | Read-only queue (known gap) | Gains concurrency-safe write-path + Saga Engine + revocation (§15) |
| `pages/06_project_dashboard.py` | Errors on empty state for new projects; no explainability tie-in | Fixed structurally (§13); explainability + model card reintegrated (§12) |
| New: `services/bundle_service.py` | — | §5.2 |
| New: `services/reconciliation_service.py` | — | §3, §21.1 |
| New: `services/feature_engineering_service.py` | — | §8, §8.6 |
| New: `services/policy_pack_service.py` | — | §20 |
| New: `services/feedback_join_service.py` | — | §10.2 |
| New: `services/portfolio_analytics_service.py` | — | §14 |
| New: `services/capacity_service.py` | — | §19.2 |
| New: `services/interview_optimizer_service.py` | — | §26 |
| New: `pages/08_feature_catalog.py` | — | §8.5 |
| New: `pages/09_hitl_review.py` | — | §11.2, §11.4 |
| New: `pages/10_portfolio_analytics.py` | — | §14.1 |
| New: `api/` routes | — | §23 |
| `db/schema.sql` | Custom tables only | Additive columns (§7.3, §20.2) + new tables: `mlops.policy_packs`, `mlops.bundle_deployments`, `mlops.label_feedback`, `mlops.hitl_reviews`, `mlops.business_impact`, `mlops.telemetry_enrichment`, `mlops.interview_telemetry` |

---

## 25. Non-Functional Requirements Summary

(Concurrency, transactionality, DR, schema migrations, and the control plane's own SDLC are detailed in §21 to keep them next to the system-of-record discussion they belong with. This section is a pointer, not a duplicate.)

- Every new Databricks-native integration (§8–§20) must degrade gracefully if the feature isn't enabled/licensed in a given workspace (e.g., Lakehouse Monitoring or Genie not enabled) — the app should detect this at setup and disable the dependent UI affordance with a clear message, not crash.
- Template and policy-pack versions are both recorded per project, so "what rules applied when this was approved" is always answerable even after the rules change.

---

## 26. Continuous Cognitive-Load Optimization

For three revisions, this document only ever added interview questions, config flags, and gates — risk tier, label source, business value function, HITL flag/threshold, explainability method, streaming/batch/real-time choice, feature-search-before-declare. Each was individually justified. Collectively, they risk violating the org's own founding thesis (`black.md`: "MLOps doesn't make AI/ML, it makes AI/ML work," "make the right path easier than the custom path"). A control plane that takes longer to configure than building something de novo has failed at its actual job, regardless of how well-governed the output is.

The fix is making the app responsible for absorbing the complexity it creates, continuously — not trusting design discipline alone to keep the interview short.

### 26.1 The interview's success metric is measured, not assumed

`black.md`'s own Success criterion is "Faster Path to Production." This becomes a literal, tracked KPI:

```sql
CREATE TABLE mlops.interview_telemetry (
  project_id STRING,
  step_name STRING,
  time_to_complete_seconds INT,
  fields_touched_by_user INT,
  fields_resolved_by_default INT COMMENT "answered by smart default, not user input",
  abandoned BOOLEAN,
  interview_version STRING,
  completed_timestamp TIMESTAMP
) COMMENT "Per-step interview telemetry — the app's own usability metric";
```

Rolled up into Portfolio Analytics (§14.1) as **Interview Speed**, alongside Speed/Reliability/Reuse/etc. If median time-to-complete-interview trends up release over release, that's a regression — treated exactly like a latency regression in production code, not an acceptable cost of "more governance."

### 26.2 A Smart Defaults Engine, not a longer form

Every question added to the interview — retroactively for what's in this document, and as a standing rule for everything after — must clear one of three bars before it's allowed to be a blocking, upfront question:

1. **Auto-inferable** — derivable from something already known (uploaded code, schema inference, prior projects by the same team). Preferred.
2. **Defaultable** — has an org- or team-level default right often enough to pre-fill and collapse, reviving the original wireframes' "using defaults unless overridden" pattern and applying it systematically to every new question rev. 1–3 added, not just the original seven steps.
3. **Deferrable** — genuinely can't be known upfront but also doesn't need to block project creation; it's editable into the project config later, with the app nagging (not blocking) until it's filled in before the gate that needs it comes due.

Concretely, the Interview Optimizer Service looks at:
- **Team history**: if 90% of a team's prior projects picked `tier_2` and `hybrid` retraining, pre-select those, collapsed, for the next one.
- **The use case selected**: choosing "streaming" inference auto-suggests the human-oversight mechanism (§11.4) most compatible with streaming, rather than leaving the DS to discover the tension themselves.
- **What's derivable from code/schema**: model type, feature columns, and a first-pass risk-tier suggestion based on data contract PII/classification levels already declared.

### 26.3 A standing design gate, not a one-time fix

Every future addition to this document is required to answer, in the PR that adds it: *"Which of auto-inferable / defaultable / deferrable does this satisfy, and what's the added median seconds for a DS taking the default path?"* A field that can't clear one of the three bars is a design defect to fix before shipping — not a governance cost to accept. This is the same discipline as the control plane's own SDLC (§21), applied specifically and permanently to interview surface area.

### 26.4 The de novo comparison

Interview Speed isn't judged against zero — it's judged against the time to do the equivalent thing by hand (a GitHub repo, UC schemas, a serving endpoint, and monitoring, stood up unassisted). This baseline is measured once per major capability area and re-baselined whenever Databricks tooling changes enough to shift it. The app's onboarding time is only a real win if it beats that number by a deliberately tracked margin — this is "Faster Path to Production" taken literally, not rhetorically.

---

## 27. Migration Roadmap

### 27.1 Weeks 1-4: Minimum Viable Control Plane (realistic near-term scope)

This document describes a multi-quarter target architecture. Built by two people in a few weeks, most of it is not attemptable yet, and pretending otherwise would be the same mistake §26 is trying to fix — adding scope without accounting for the cost of absorbing it. A realistic first build:

- **Week 1**: Bundle Service, grounded in the actual confirmed commands (`bundle plan -o json`, `bundle deploy --plan`, §5.2). Convert one existing example project (e.g., the current `lightgbm_text_project`) into a real DAB. Prove `validate` → `plan` → `deploy` → `destroy` round-trips against a real dev catalog.
- **Week 2**: UC Model Registry cutover for that one project — aliases + tags (§7.4) — plus a real-time serving endpoint with route optimization and Inference Tables on by default (§9.1), confirmed against actual observed behavior, not just documentation.
- **Week 3**: The approval write-path (§15.1) with concurrency-safe MERGE, wired into the *already-existing* Streamlit approvals page — this is the highest-value target because it's a known, previously-scoped gap (`PROJECT_STATUS.md` gap #4), not a new concept to design from scratch.
- **Week 4 (if time allows)**: One end-to-end "vision" feature, proven for the one converted project — most likely the Label Quality & Feedback Loop (§10), since it's the most foundational of the later-revision additions (it unlocks real accuracy and is a prerequisite for business impact) and has the smallest new-surface-area relative to its payoff.

Everything else in this document — HITL, granular explainability, streaming inference, network security, model risk tiering beyond a stub, the control-plane budget, the Capacity Service, interview telemetry — is sequenced below, honestly, as **later phases**, not implied to fit in the first few weeks.

### 27.2 Phase 5 onward (sequenced, not scheduled)

Numbered to continue from the four weeks above, so "phase number" and "build order" stay aligned as this roadmap gets referenced later:

5. **Reconciliation Service** — cost + audit joins first, with self-monitoring (§21.1) built in from day one of this phase, not bolted on after.
6. **Lakehouse Monitoring cutover**, including the `label_col` synergy (§10.3, §13).
7. **Feature Engineering/Online Tables/Feature Serving, Feature Catalog (§8.5), and Contract Versioning (§8.6) together** — discovery without breakage-protection recreates the reuse-safety gap, so these ship as one phase, not two.
8. **Human-in-the-loop review + explainability**, shipped together with the sync/async split from day one (§11, §12) — building the sync-only version first and retrofitting async later would recreate the exact latency contradiction rev. 4 fixed.
9. **Portfolio Analytics**, including the comparability indicator (§14.4) from day one — a portfolio dashboard without it would recreate the metric-comparability risk immediately.
10. **Streaming inference** (§9.4), whenever a first governed source stream/table is actually available to score against.
11. **Policy packs + risk tiering**, including the revalidation trigger (§20.5) — not shipped as a stub field this time.
12. **Network/security hardening**, timed to the first regulated-environment deployment.
13. **Capacity Service and control-plane budget** (§17.4, §19.2) — ideally before project count grows enough to need them, not after.
14. **API layer** — once the above is stable enough to expose externally.
15. **Auth cutover to native Databricks App hosting** — mostly independent of the above, but should land before any external API consumers are onboarded (§23).
16. **Interview Optimizer Service and cognitive-load telemetry** (§26) — ideally threaded through as a discipline from Week 1 onward, even before the dedicated service exists to formalize it.

---

## 28. GenAI Expansion Readiness Audit

Explicit response to: *"flag any decisions that would prevent expansion to GenAI/LLM ops."*

| Decision | GenAI-blocking? | Why |
|---|---|---|
| Databricks Asset Bundles | No | DABs already support Vector Search index resources and LLM-serving endpoints as resource types. |
| Unity Catalog Model Registry (aliases + tags) | No — actually a plus | Same mechanism Databricks recommends for registering GenAI agents/models (MLflow `ChatModel`/`ResponsesAgent` flavors register into UC identically). |
| Native Databricks App hosting (OAuth) | No | GenAI-serving apps use the identical hosting/auth model. |
| Environment-scoped catalogs + aliases | No | Vector Search indexes and a future prompt registry can follow the same per-environment catalog pattern. |
| Reconciliation Service (system tables) | No | Token-based LLM billing already appears in `system.billing.usage` with different `usage_metadata`; the service just needs new field mappings, not a redesign. |
| Feedback Join Service / label feedback (§10) | No — directly reusable | The exact same delayed-ground-truth join pattern applies to RAG relevance feedback or agent outcome scoring. |
| Human-in-the-loop review (§11) | No — directly reusable, and better shaped than a single flag would have been | The sync/async/sampling/escalation menu (§11.4) maps directly onto agent action approval at different autonomy levels. |
| Explainability (§12), including per-item sync/async delivery (§12.2) | No — parallel concept, and the sync/async split generalizes | GenAI's analogous need is citation/traceability (MLflow Tracing); the same latency-vs-completeness tradeoff applies, and the review-UI integration pattern (show the "why" alongside the decision) carries over conceptually. |
| Corrected telemetry via `client_request_id` (§9.2) | No | The correlation-table pattern is provider-agnostic; it would work identically for LLM-serving telemetry. |
| Model card assembly (§12.3) | No — a plus | GenAI's equivalent (system cards / model cards for agents) assembles from the same kinds of inputs. |
| Counterfactual explanations (§12.4) | No — a parallel concept exists | GenAI has an analogous idea (minimal prompt/context perturbation that flips a response), though the tooling is different (not DiCE/Alibi) and would need its own design, not a direct reuse. |
| **Data contract schema** (`contract_type`, quality rules) | **Soft constraint — must actively preserve, not blocking today** | Quality rules (`range_check`, `null_check`, etc.) assume tabular columns; prompts/document corpora don't fit that shape. Not blocking *because* `contract_type` was deliberately kept an open field rather than a fixed enum (§6) — a future `prompt_template` or `document_corpus` contract type can be added without a schema migration. This only stays true if nothing downstream (UI dropdowns, validation code) hardcodes the current contract types as an exhaustive set. |
| **Testing pyramid / fairness frameworks** (aif360/fairlearn) | **Soft constraint, same shape as above** | GenAI evaluation (relevance, faithfulness, hallucination via MLflow Evaluate/judges) is structurally different from tabular fairness testing. Not blocking because gates are already named/pluggable via the policy-pack mechanism (§20) — adding a `genai_eval` gate type is additive. Only stays true if the Approval Saga Engine keeps treating "which gates are required" as data (policy pack config), not a hardcoded list in code. |

**Bottom line**: nothing in the v1 architecture needs to be undone to add GenAI later, and several rev. 3/4 additions (feedback loops, HITL, explainability) turn out to be directly reusable rather than classical-ML-specific — a byproduct of building them Databricks-native and data-driven rather than hardcoding assumptions specific to tabular models. The two soft constraints are implementation discipline to maintain, not open design questions.

---

## 29. Open Questions

Every item below carries an explicit, clearly marked **Suggestion** and **Rationale** — these are recommendations, not decisions; they're marked this way specifically so they're easy to accept, reject, or amend individually rather than having to be inferred from prose elsewhere in the document. Resolved items are separated from genuinely open ones so this section reads as a clean punch list for final review, not a mixed log.

### 29.1 Resolved at Week 0 (this revision)

**Schema corrections** — exact current field names/schema for `route_optimized`, inference table capture, and the Jobs `continuous` trigger (§5.2, §9.1, §9.4) were pulled and checked against this document's YAML directly, rather than left deferred. Three real errors were found and fixed:
1. `route_optimized` was nested inside `served_entities`; it's actually a top-level field of the `model_serving_endpoint` resource. Fixed in §9.1.
2. `auto_capture_config` — used throughout §9.1 as the inference-table enablement mechanism — is **officially retired**. The current, documented replacement is `ai_gateway.inference_table_config` (same sub-fields, re-nested), explicitly confirmed to support "custom model" endpoints, not only foundation/agent models. Fixed in §9.1.
3. The streaming job's `continuous` trigger was wrapped in a nonexistent `trigger:` key; it's a direct top-level field of the job resource. Fixed in §9.4.

One sub-item remains genuinely open even after this check: the exact *declarative* (bundle/API) field structure for `ai_gateway.inference_table_config` couldn't be fully confirmed from documentation alone — the primary docs page describes UI-based setup, and the sub-fields used above come from the bundle resource schema page rather than a worked example.
**Suggestion**: verify this by running `databricks bundle schema` against the actual CLI in the target environment (or a scratch endpoint deploy/inspect cycle) at the very start of Week 1, rather than trusting documentation-only confirmation for this one field.
**Rationale**: this is the one field in the whole document where documentation described a UI flow rather than a declarative schema — a live schema dump or a real test deploy is more reliable here than further doc research, and it's cheap to do first thing in Week 1 before anything is built on top of an assumption about it.

**Terminology** — this document caught two live Databricks product/terminology transitions mid-flight: "Delta Sharing" documented as "OpenSharing" (§6), and "Online Tables" documented as legacy terminology being migrated to Lakebase-based "synced tables" (§8). Per the rule this document set for itself last revision ("re-check at Week 0, adopt whatever the docs say then") — and since Week 0 is now — the call is made: **keep "Delta Sharing" and "Online Tables" as the primary terms in body text, with the current docs' actual names ("OpenSharing," "Lakebase synced tables") noted inline where each concept is introduced, not swapped as the headline term.**
**Rationale**: both renames are real, but neither is confirmed to have fully displaced the older name in general industry/team usage yet, and the §9.1/§9.4 corrections above just demonstrated that the highest-value verification work is on *exact field-level schema* (where being wrong breaks a build), not on *which of two valid names to prefer* (where being "behind" costs nothing but a word choice).

### 29.2 Still open — carried from rev. 4.2

**Open item**: HITL default mechanism per deployment pattern (§11.4) — which row of the table is pre-selected by the Smart Defaults Engine (§26.2) for each inference type, before a team overrides it.
**Suggestion**: Default to "synchronous" for real-time + low-QPS, "automated escalation on threshold breach" for streaming, "asynchronous within an SLA" for real-time + moderate/high-QPS, and "periodic batch audit" for batch — i.e., default to whatever §11.4's own "Fits" column already says, rather than inventing a separate heuristic.
**Rationale**: reuses a decision this document already made and documented instead of introducing new judgment calls; keeps the smart default legible ("we just looked up your inference type in the table you already reviewed") rather than opaque.

**Open item**: Explainability default method (§12.1) — SHAP vs. LIME as the out-of-box default when a project doesn't specify.
**Suggestion**: Default to SHAP with TreeExplainer when the model type is tree-based (XGBoost/LightGBM/RandomForest — likely the majority of classical tabular use cases per the original spec's model-type list), falling back to LIME only when the model type has no fast native SHAP explainer available.
**Rationale**: SHAP has stronger theoretical guarantees (Shapley values uniquely satisfy certain fairness/consistency axioms) and TreeExplainer is fast enough to stay within §12.2's `sync_latency_budget_ms` for the common case — defaulting to "SHAP when fast, LIME when necessary" keeps sync-mode explainability items actually usable rather than silently demoting to async (§12.2) for most projects by default.

**Open item**: Counterfactual explanation library choice (§12.4) — DiCE vs. Alibi vs. another open-source implementation.
**Suggestion**: Default to DiCE (Diverse Counterfactual Explanations) unless a project's model type isn't well-supported by it, in which case Alibi is the documented fallback.
**Rationale**: DiCE has broader existing adoption for tabular classifiers specifically (the dominant model shape in this document's classical-ML scope) and is simpler to run as a batch job against a holdout/inference sample than more general-purpose explainability toolkits; this is a low-stakes default since it's org-configurable per §12.4's YAML.

**Open item**: Model Serving endpoint quota for the actual target account (§19.1) — not publicly published.
**Suggestion**: Start this conversation with the Databricks account team now, in parallel with Weeks 1-4, rather than waiting until the Capacity Service's 50-endpoint alert threshold (§19.2) is actually approached.
**Rationale**: account-team conversations have their own lead time (scheduling, internal review) fully decoupled from the build timeline — better to have the real number in hand before it's urgently needed than to request it under time pressure.

**Open item**: Streaming inference (§9.4) assumes a governed source stream/table already exists.
**Suggestion**: Treat "does a real governed streaming source exist yet" as a go/no-go gate for even starting roadmap phase 10 (§27.2) — do not build a synthetic/dummy source table to unblock it on a schedule.
**Rationale**: the entire value of that phase is validating against a real, upstream-owned source with its own quirks (schema drift, gaps, latency variance); a synthetic table would produce false confidence without testing any of the actual integration risk.

### 29.3 New from the rev. 4.2 adversarial pass

**Finding**: Genie Spaces / AI-BI Dashboards likely sit outside the DAB declarative lifecycle. Current Declarative Automation Bundles resource documentation doesn't list Genie Spaces as a native bundle resource type — provisioning appears to go through the `createspace` REST API directly (§13). That means it won't show up in `bundle plan` drift detection and won't be torn down by `bundle destroy`.
**Suggestion**: Store the Genie Space/dashboard identifiers on `mlops.projects`, and have the Bundle Service's own generate/deploy/destroy wrapper make the direct REST calls as an explicit, tracked step in the same saga pattern used elsewhere (§15.2) — with its own compensating teardown action — rather than assuming bundle deploy/destroy covers it "for free."
**Rationale**: this is the one confirmed non-bundle resource type in the whole design; without an explicit exception, it's the one thing that could get silently orphaned on project retirement (§21.2) despite that section's claim to enumerate everything.

**Finding**: The Smart Defaults Engine (§26.2) risks entrenching under-tiered risk classifications. "90% of this team's prior projects picked tier_2" becoming a one-click default accelerates whatever the team was already doing — including systematic under-tiering, if that's what it was.
**Suggestion**: Exclude governance-consequential fields (risk tier, human-oversight mechanism) from full auto-collapse. Pre-fill them as a suggestion, but keep the section visibly expanded with a required one-line justification field, and have the Interview Optimizer Service track "% of projects accepting the risk-tier default without override" as a health metric — treating a number very close to 0% as suspicious, not just efficient.
**Rationale**: cognitive-load reduction (§26) and governance rigor are in genuine tension for exactly this class of field; the fix is a narrow, named exception for governance-consequential questions, not weakening defaults everywhere else.

**Finding**: Revocation (§15.4) of a *historical*, superseded approval isn't well-defined. If the approval behind v3 is revoked after v5 is already `@champion`, an automatic rollback "to before v3" doesn't cleanly make sense — v4/v5 may have been built on top of it through their own, independently valid approvals.
**Suggestion**: Revocation of the approval behind the *current* `@champion` triggers the existing automatic rollback saga (§15.2) unchanged. Revocation of a *historical, already-superseded* approval instead opens an investigation record and notifies MLOps/legal, with no automatic model action.
**Rationale**: auto-rolling back to an old, likely-stale version in response to a historical revocation would itself be an unreviewed, potentially risky action — precisely the failure mode §15.4 exists to prevent in the first place.

**Finding**: Asynchronous HITL (§11.3) doesn't define what happens if the SLA is missed — no reviewer acting within the window is currently undefined behavior.
**Suggestion**: Default to escalating to a backup reviewer or MLOps on SLA breach — never auto-approve on timeout.
**Rationale**: auto-approving under time pressure would quietly convert a human-oversight requirement into a rubber stamp exactly when load is highest; "fail closed" (already the implicit stance on fairness-test skipping elsewhere in this document) should extend explicitly to this case rather than being left to whoever implements it to guess.

**Finding**: Cross-environment Online Table isolation is unspecified (§8). Per-environment syncing (matching §5.1's catalog-per-environment pattern) triples always-on serving cost per feature; a shared Online Table across environments would be cheaper but lets a dev experiment's feature changes leak into what prod serving reads.
**Suggestion**: Online Tables sync per-environment, consistent with every other isolation guarantee in this document, accepting the extra cost.
**Rationale**: making a cost-driven exception here would be the one place environment isolation is silently weaker than everywhere else this document promises it — not a place to save money quietly.

**Finding**: Feature contract breaking changes (§8.6) can currently be shipped unilaterally by the owning team, only *notifying* consumers after the fact — unlike almost everything else in this document, no cross-team sign-off is required before the change goes out.
**Suggestion**: A breaking change to a feature table with more than one consuming project should require acknowledgment from each consuming project's owner before the version bump is allowed to deploy, reusing the same PR-review discipline already applied to policy packs (§20.3) and business value functions (§14.4).
**Rationale**: "notify after the fact" is fine for low-stakes changes, but a breaking change to a genuinely shared feature is exactly the kind of cross-team-impacting event this document otherwise insists on getting ahead of, not reporting after it lands.

---

## 30. Explicitly Out of Scope (v2 candidates)

If GenAI/LLM workloads are added later (see §28 for why none of this requires undoing v1 work):
- Prompt registry (versioned prompts — likely UC volumes or a `mlops.prompts` table with Git-backed history)
- Vector Search index lifecycle (create/sync/monitor, analogous to §7's model lifecycle)
- AI Gateway integration for rate limiting, spend caps, and guardrails on served LLM/agent endpoints
- RAG/agent evaluation harness (MLflow Evaluate + tracing) as a parallel track to the existing testing pyramid
- Token-based cost tracking reconciled from `system.billing.usage` LLM-serving line items

Also remaining explicitly out of scope regardless of GenAI (§1): upstream problem intake/prioritization, personas beyond the original six, upstream streaming/DLT pipeline authoring, multi-cloud active-active, Terraform-based IaC.
