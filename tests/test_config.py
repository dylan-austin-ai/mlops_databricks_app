"""Tests for config.py — AppConfig loading and validation."""

from __future__ import annotations

import os
from unittest.mock import patch

from config import AppConfig


class TestAppConfig:
    def test_is_connected_true_when_all_set(self):
        cfg = AppConfig(
            databricks_host="https://workspace.databricks.com",
            databricks_token="dapi123",
            warehouse_id="abc456",
        )
        assert cfg.is_connected is True

    def test_is_connected_false_missing_host(self):
        # Pass explicit empty string — don't rely on env vars being absent
        cfg = AppConfig(databricks_host="", databricks_token="dapi123", warehouse_id="abc456")
        assert cfg.is_connected is False

    def test_is_connected_false_missing_token(self):
        cfg = AppConfig(
            databricks_host="https://workspace.databricks.com",
            databricks_token="",
            warehouse_id="abc456",
        )
        assert cfg.is_connected is False

    def test_is_connected_false_missing_warehouse(self):
        cfg = AppConfig(
            databricks_host="https://workspace.databricks.com",
            databricks_token="dapi123",
            warehouse_id="",
        )
        assert cfg.is_connected is False

    def test_missing_vars_returns_all_missing(self):
        cfg = AppConfig(databricks_host="", databricks_token="", warehouse_id="")
        missing = cfg.missing_vars()
        assert "DATABRICKS_HOST" in missing
        assert "DATABRICKS_TOKEN" in missing
        assert "DATABRICKS_WAREHOUSE_ID" in missing

    def test_missing_vars_returns_only_absent(self):
        cfg = AppConfig(
            databricks_host="https://workspace.databricks.com",
            databricks_token="dapi123",
            warehouse_id="",
        )
        missing = cfg.missing_vars()
        assert "DATABRICKS_HOST" not in missing
        assert "DATABRICKS_TOKEN" not in missing
        assert "DATABRICKS_WAREHOUSE_ID" in missing

    def test_missing_vars_empty_when_all_set(self):
        cfg = AppConfig(
            databricks_host="https://workspace.databricks.com",
            databricks_token="dapi123",
            warehouse_id="abc456",
        )
        assert cfg.missing_vars() == []

    def test_mlops_schema_prefix(self):
        cfg = AppConfig(catalog="mlops", schema="mlops")
        assert cfg.mlops_schema_prefix == "mlops.mlops"

    def test_mlops_schema_prefix_custom(self):
        cfg = AppConfig(catalog="my_catalog", schema="my_schema")
        assert cfg.mlops_schema_prefix == "my_catalog.my_schema"

    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.catalog == "mlops"
        assert cfg.schema == "mlops"
        assert cfg.llm_endpoint == "databricks-meta-llama-3-1-70b-instruct"

    def test_loads_from_env(self):
        env = {
            "DATABRICKS_HOST": "https://test.databricks.com",
            "DATABRICKS_TOKEN": "dapi_test",
            "DATABRICKS_WAREHOUSE_ID": "wh_test",
            "MLOPS_CATALOG": "test_cat",
            "MLOPS_SCHEMA": "test_schema",
            "GITHUB_TOKEN": "ghp_test",
            "GITHUB_ORG": "test-org",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = AppConfig()
            assert cfg.databricks_host == "https://test.databricks.com"
            assert cfg.databricks_token == "dapi_test"
            assert cfg.warehouse_id == "wh_test"
            assert cfg.catalog == "test_cat"
            assert cfg.schema == "test_schema"
            assert cfg.github_token == "ghp_test"
            assert cfg.github_org == "test-org"
