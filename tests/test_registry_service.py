"""Tests for registry_service — alias moves, audit tags, rollback."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import AppConfig
from services.registry_service import (
    CHAMPION,
    RegistryService,
    RegistryServiceError,
)


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
    )


class FakeMlflowClient:
    """In-memory stand-in for MlflowClient's registry surface."""

    def __init__(self):
        self.aliases: dict[str, dict[str, int]] = {}  # model -> alias -> version
        self.tags: dict[tuple[str, str], dict[str, str]] = {}  # (model, version) -> tags
        self.copies: list[tuple[str, str]] = []

    def get_registered_model(self, name):
        return SimpleNamespace(name=name, aliases=dict(self.aliases.get(name, {})))

    def set_registered_model_alias(self, name, alias, version):
        self.aliases.setdefault(name, {})[alias] = int(version)

    def delete_registered_model_alias(self, name, alias):
        self.aliases.get(name, {}).pop(alias, None)

    def set_model_version_tag(self, name, version, key, value):
        self.tags.setdefault((name, str(version)), {})[key] = value

    def get_model_version(self, name, version):
        return SimpleNamespace(name=name, version=str(version), tags=dict(self.tags.get((name, str(version)), {})))

    def copy_model_version(self, src_model_uri, dst_name):
        self.copies.append((src_model_uri, dst_name))
        return SimpleNamespace(version="1")


class FakeServingEndpoints:
    """In-memory stand-in for WorkspaceClient.serving_endpoints."""

    def __init__(self, endpoints: dict | None = None, fail_update: bool = False):
        self.endpoints = endpoints or {}
        self.fail_update = fail_update
        self.updates: list[tuple] = []

    def get(self, name):
        if name not in self.endpoints:
            raise RuntimeError(f"Endpoint with name '{name}' does not exist")
        return self.endpoints[name]

    def update_config(self, name, served_entities=None, traffic_config=None):
        if self.fail_update:
            raise RuntimeError("serving config update failed")
        self.updates.append((name, served_entities, traffic_config))


class FakeWorkspaceClient:
    def __init__(self, endpoints: dict | None = None, fail_update: bool = False):
        self.serving_endpoints = FakeServingEndpoints(endpoints, fail_update)


MODEL = "retention_churn_prod.ml.churn"


def _endpoint(entity_name: str = MODEL, version: str = "1") -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            served_entities=[
                SimpleNamespace(
                    name="champion",
                    entity_name=entity_name,
                    entity_version=version,
                    workload_size="Small",
                    scale_to_zero_enabled=True,
                )
            ],
            traffic_config=None,
        ),
        pending_config=None,
    )


@pytest.fixture
def client() -> FakeMlflowClient:
    return FakeMlflowClient()


@pytest.fixture
def svc(cfg, client) -> RegistryService:
    return RegistryService(config=cfg, client=client)


class TestPromote:
    def test_first_champion_promotion(self, svc, client):
        move = svc.promote(MODEL, 1, CHAMPION, actor_email="a@co.com", approval_manifest_hash="abc123")

        assert client.aliases[MODEL][CHAMPION] == 1
        assert move.previous_version is None
        tags = client.tags[(MODEL, "1")]
        assert tags["promoted_by"] == "a@co.com"
        assert tags["approval_manifest_hash"] == "abc123"
        # No previous champion → no previous_champion_version tag
        assert "previous_champion_version" not in tags

    def test_promotion_records_previous_champion(self, svc, client):
        svc.promote(MODEL, 1, CHAMPION, actor_email="a@co.com")
        move = svc.promote(MODEL, 2, CHAMPION, actor_email="b@co.com", promoted_from_alias="challenger")

        assert client.aliases[MODEL][CHAMPION] == 2
        assert move.previous_version == 1
        tags = client.tags[(MODEL, "2")]
        assert tags["previous_champion_version"] == "1"
        assert tags["promoted_from_alias"] == "challenger"

    def test_alias_is_exclusive_single_pointer(self, svc, client):
        svc.promote(MODEL, 1, CHAMPION, actor_email="a@co.com")
        svc.promote(MODEL, 2, CHAMPION, actor_email="a@co.com")
        # One alias, one version — never two champions (§7.4)
        assert client.aliases[MODEL] == {CHAMPION: 2}

    def test_fairness_tag_written_when_given(self, svc, client):
        svc.promote(MODEL, 1, CHAMPION, actor_email="a@co.com", fairness_test_result="pass")
        assert client.tags[(MODEL, "1")]["fairness_test_result"] == "pass"

    def test_non_champion_alias_skips_previous_champion_tag(self, svc, client):
        svc.promote(MODEL, 1, CHAMPION, actor_email="a@co.com")
        svc.promote(MODEL, 2, "challenger", actor_email="a@co.com")
        assert "previous_champion_version" not in client.tags[(MODEL, "2")]


class TestRollback:
    def test_rollback_repoints_champion(self, svc, client):
        svc.promote(MODEL, 1, CHAMPION, actor_email="a@co.com")
        svc.promote(MODEL, 2, CHAMPION, actor_email="a@co.com")

        move = svc.rollback_champion(MODEL, actor_email="oncall@co.com", reason="canary breach")

        assert client.aliases[MODEL][CHAMPION] == 1
        assert move.version == 1
        assert move.previous_version == 2
        tags = client.tags[(MODEL, "1")]
        assert tags["rollback_of_version"] == "2"
        assert tags["rollback_reason"] == "canary breach"
        assert tags["promoted_from_alias"] == "rollback"

    def test_rollback_without_champion_fails(self, svc):
        with pytest.raises(RegistryServiceError, match="no @champion"):
            svc.rollback_champion(MODEL, actor_email="a@co.com", reason="x")

    def test_rollback_without_history_fails_loudly(self, svc, client):
        # champion set directly with no previous_champion_version tag
        client.set_registered_model_alias(MODEL, CHAMPION, 5)
        with pytest.raises(RegistryServiceError, match="previous_champion_version"):
            svc.rollback_champion(MODEL, actor_email="a@co.com", reason="x")


class TestReadsAndCopy:
    def test_alias_map_empty_for_unknown(self, svc):
        assert svc.alias_map("nope.ml.model") == {}

    def test_alias_version_none_when_absent(self, svc):
        assert svc.alias_version(MODEL, CHAMPION) is None

    def test_copy_version_to_catalog(self, svc, client):
        version = svc.copy_version_to_catalog("models:/retention_churn_staging.ml.churn/3", MODEL)
        assert version == 1
        assert client.copies == [("models:/retention_churn_staging.ml.churn/3", MODEL)]


class TestUpdateChampionServingVersion:
    """Live-verified 2026-07-07: entity_version rejects aliases (numeric-only)."""

    def test_updates_champion_entity_to_numeric_version(self, cfg, client):
        ws = FakeWorkspaceClient({"churn-prod": _endpoint()})
        svc = RegistryService(config=cfg, client=client, ws_client=ws)

        assert svc.update_champion_serving_version("churn-prod", 7) is True

        name, entities, _ = ws.serving_endpoints.updates[0]
        assert name == "churn-prod"
        champion = next(e for e in entities if e.name == "champion")
        assert champion.entity_version == "7"
        assert champion.entity_name == MODEL

    def test_returns_none_when_endpoint_missing(self, cfg, client):
        svc = RegistryService(config=cfg, client=client, ws_client=FakeWorkspaceClient())
        assert svc.update_champion_serving_version("churn-prod", 7) is None

    def test_raises_when_no_champion_entity(self, cfg, client):
        ep = _endpoint()
        ep.config.served_entities[0].name = "challenger"
        ws = FakeWorkspaceClient({"churn-prod": ep})
        svc = RegistryService(config=cfg, client=client, ws_client=ws)

        with pytest.raises(RegistryServiceError, match="champion"):
            svc.update_champion_serving_version("churn-prod", 7)

    def test_propagates_non_notfound_errors(self, cfg, client):
        class Boom:
            def get(self, name):
                raise RuntimeError("500 internal error")

        ws = SimpleNamespace(serving_endpoints=Boom())
        svc = RegistryService(config=cfg, client=client, ws_client=ws)

        with pytest.raises(RuntimeError, match="500"):
            svc.update_champion_serving_version("churn-prod", 7)
