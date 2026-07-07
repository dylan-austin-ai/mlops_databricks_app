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
    llm_endpoint: str = field(
        default_factory=lambda: os.getenv("DATABRICKS_LLM_ENDPOINT", "databricks-meta-llama-3-1-70b-instruct")
    )

    @property
    def is_connected(self) -> bool:
        return bool(self.databricks_host and self.databricks_token and self.warehouse_id)

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
