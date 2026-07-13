"""App-level configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    databricks_host: str = field(default_factory=lambda: os.getenv("DATABRICKS_HOST", ""))
    databricks_token: str = field(default_factory=lambda: os.getenv("DATABRICKS_TOKEN", ""))
    warehouse_id: str = field(default_factory=lambda: os.getenv("DATABRICKS_WAREHOUSE_ID", ""))
    catalog: str = field(default_factory=lambda: os.getenv("MLOPS_CATALOG", "mlops"))
    schema: str = field(default_factory=lambda: os.getenv("MLOPS_SCHEMA", "default"))
    # Project data convention (owner decision 2026-07-07): one schema per
    # project inside a configurable catalog. Per-env overrides keep the
    # 100+-project escape hatch (mlops_dev/_staging/_prod catalogs) a config
    # change, not a code change.
    projects_catalog: str = field(default_factory=lambda: os.getenv("MLOPS_PROJECTS_CATALOG", "mlops"))
    projects_catalog_dev: str = field(default_factory=lambda: os.getenv("MLOPS_PROJECTS_CATALOG_DEV", ""))
    projects_catalog_staging: str = field(default_factory=lambda: os.getenv("MLOPS_PROJECTS_CATALOG_STAGING", ""))
    projects_catalog_prod: str = field(default_factory=lambda: os.getenv("MLOPS_PROJECTS_CATALOG_PROD", ""))
    # Default Storage workspaces require a MANAGED LOCATION to create catalogs
    # via SQL/API (owner decision 2026-07-07, option B). Empty = plain CREATE.
    managed_location: str = field(default_factory=lambda: os.getenv("MLOPS_MANAGED_LOCATION", ""))
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_org: str = field(default_factory=lambda: os.getenv("GITHUB_ORG", ""))
    # Owner request 2026-07-13: when a DS links an existing (rather than
    # app-created) GitHub repo in Step 1, the app pushes the scaffold into it
    # only if it's "empty" — root-level entries matching one of these names
    # are ignored (common org automation: a README/LICENSE/.github stamped in
    # at repo-creation time), anything else blocks the push.
    empty_repo_ignore_patterns: list[str] = field(
        default_factory=lambda: (
            [p.strip() for p in os.environ["MLOPS_EMPTY_REPO_IGNORE_PATTERNS"].split(",") if p.strip()]
            if os.getenv("MLOPS_EMPTY_REPO_IGNORE_PATTERNS")
            else ["README.md", ".gitignore", "LICENSE", ".github"]
        )
    )
    llm_endpoint: str = field(
        default_factory=lambda: os.getenv("DATABRICKS_LLM_ENDPOINT", "databricks-meta-llama-3-1-70b-instruct")
    )
    # §17.4/§19.2, phase 13: control-plane budget + capacity thresholds.
    # Owner decision 2026-07-07: ship config-driven with placeholder defaults
    # ($50/$100 per month) until a real number is set — CapacityService marks
    # these PLACEHOLDER in the UI rather than presenting them as real limits.
    control_plane_budget_warn_usd: float = field(
        default_factory=lambda: float(os.getenv("MLOPS_CONTROL_PLANE_BUDGET_WARN", "50"))
    )
    control_plane_budget_crit_usd: float = field(
        default_factory=lambda: float(os.getenv("MLOPS_CONTROL_PLANE_BUDGET_CRIT", "100"))
    )
    # §19.2: no per-workspace Model Serving endpoint limit is published;
    # this is an internally-set alert threshold, not a hard ceiling.
    capacity_endpoint_warn_threshold: int = field(
        default_factory=lambda: int(os.getenv("MLOPS_CAPACITY_ENDPOINT_WARN_THRESHOLD", "50"))
    )
    # Notification Delivery Service (IMG_1412 gap: alerts/approver-notify/HITL
    # escalation only ever wrote DB rows, never reached anyone). One admin-set
    # credential per channel — the wizard only ever collects a channel_name or
    # recipient list, never a raw webhook URL/SMTP secret, per the app's usual
    # secrets-live-in-config convention (§16). Unset = that channel reports
    # not_configured rather than failing.
    smtp_host: str = field(default_factory=lambda: os.getenv("MLOPS_SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("MLOPS_SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("MLOPS_SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("MLOPS_SMTP_PASSWORD", ""))
    smtp_from_email: str = field(default_factory=lambda: os.getenv("MLOPS_SMTP_FROM_EMAIL", ""))
    slack_webhook_url: str = field(default_factory=lambda: os.getenv("MLOPS_SLACK_WEBHOOK_URL", ""))
    teams_webhook_url: str = field(default_factory=lambda: os.getenv("MLOPS_TEAMS_WEBHOOK_URL", ""))
    # Budget Policy attribution (owner request, 2026-07-12): per-project cost
    # attribution via Databricks' native serverless Budget Policy feature
    # (confirmed live against the pinned CLI's bundle schema — `budget_policy_id`
    # is a top-level [Public Preview] field on jobs and model serving endpoints,
    # both of which this app already generates serverless-only, §17.1). Policy
    # *creation* is an account-level API (AccountClient), a materially
    # different, higher-privilege credential than the workspace token this app
    # otherwise only ever needs — kept as its own credential group, entirely
    # optional (BudgetPolicyService degrades gracefully when unset, same
    # posture as MonitoringService/§25).
    databricks_account_host: str = field(default_factory=lambda: os.getenv("DATABRICKS_ACCOUNT_HOST", ""))
    databricks_account_id: str = field(default_factory=lambda: os.getenv("DATABRICKS_ACCOUNT_ID", ""))
    databricks_account_client_id: str = field(default_factory=lambda: os.getenv("DATABRICKS_ACCOUNT_CLIENT_ID", ""))
    databricks_account_client_secret: str = field(
        default_factory=lambda: os.getenv("DATABRICKS_ACCOUNT_CLIENT_SECRET", "")
    )
    # Owner decision 2026-07-12: pre-set an existing policy id here to use it
    # as-is, or leave it blank and set only the name — BudgetPolicyService
    # creates the named policy once (idempotent, by name) and this ID is
    # effectively "whatever ensure_default_policy() resolves to" from then on.
    default_budget_policy_id: str = field(default_factory=lambda: os.getenv("MLOPS_DEFAULT_BUDGET_POLICY_ID", ""))
    default_budget_policy_name: str = field(
        default_factory=lambda: os.getenv("MLOPS_DEFAULT_BUDGET_POLICY_NAME", "mlops-control-plane-default")
    )

    @property
    def is_connected(self) -> bool:
        return bool(self.databricks_host and self.databricks_token and self.warehouse_id)

    @property
    def has_account_credentials(self) -> bool:
        return bool(
            self.databricks_account_host
            and self.databricks_account_id
            and self.databricks_account_client_id
            and self.databricks_account_client_secret
        )

    @property
    def mlops_schema_prefix(self) -> str:
        """Fully-qualified schema prefix: catalog.schema"""
        return f"{self.catalog}.{self.schema}"

    def projects_catalog_for(self, env: str) -> str:
        """Catalog holding project schemas for a dev/staging/prod target."""
        override = {
            "dev": self.projects_catalog_dev,
            "staging": self.projects_catalog_staging,
            "prod": self.projects_catalog_prod,
        }.get(env, "")
        return override or self.projects_catalog

    def missing_vars(self) -> list[str]:
        required = {
            "DATABRICKS_HOST": self.databricks_host,
            "DATABRICKS_TOKEN": self.databricks_token,
            "DATABRICKS_WAREHOUSE_ID": self.warehouse_id,
        }
        return [k for k, v in required.items() if not v]


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()
