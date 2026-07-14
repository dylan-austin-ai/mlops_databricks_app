"""Registry Service — UC Model Registry lifecycle via aliases + tags (§7).

UC does not support legacy stages; the single mutable pointer for "which
version is live for purpose X" is an alias (@champion / @challenger / @shadow),
which is what promotion, rollback, and traffic_config all resolve against.

Every alias move also writes descriptive tags on the model version itself
(§7.4), so the promotion history lives on the artifact in Unity Catalog — the
mlops.* tables are a rebuildable index, and even without them anyone browsing
Catalog Explorer can see why a version is champion and what it replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from config import AppConfig, get_config

CHAMPION = "champion"
CHALLENGER = "challenger"
SHADOW = "shadow"


class RegistryServiceError(RuntimeError):
    """Raised when a registry operation fails or preconditions aren't met."""


@dataclass
class AliasMove:
    """Record of one alias move — returned so callers can audit-log it."""

    uc_full_name: str
    alias: str
    version: int
    previous_version: int | None
    tags_written: dict[str, str] = field(default_factory=dict)


class RegistryService:
    def __init__(self, config: AppConfig | None = None, client: Any = None, ws_client: Any = None) -> None:
        self._cfg = config or get_config()
        self._client_override = client  # injectable for tests
        self._ws_override = ws_client  # injectable for tests

    def _client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        import mlflow
        from mlflow import MlflowClient

        mlflow.set_registry_uri("databricks-uc")
        return MlflowClient()

    def _ws(self) -> Any:
        if self._ws_override is not None:
            return self._ws_override
        from databricks.sdk import WorkspaceClient

        return WorkspaceClient(host=self._cfg.databricks_host, token=self._cfg.databricks_token, auth_type="pat")

    # ── reads ─────────────────────────────────────────────────────────────────

    def alias_map(self, uc_full_name: str) -> dict[str, int]:
        """Current alias → version map, straight from UC."""
        model = self._client().get_registered_model(uc_full_name)
        aliases = getattr(model, "aliases", None) or {}
        return {alias: int(version) for alias, version in aliases.items()}

    def alias_version(self, uc_full_name: str, alias: str) -> int | None:
        return self.alias_map(uc_full_name).get(alias)

    def version_tags(self, uc_full_name: str, version: int) -> dict[str, str]:
        """§7.4 audit tags on a model version, straight from UC."""
        mv = self._client().get_model_version(name=uc_full_name, version=str(version))
        return dict(getattr(mv, "tags", None) or {})

    # ── promotion (§7.2 / §7.4) ───────────────────────────────────────────────

    def promote(
        self,
        uc_full_name: str,
        version: int,
        alias: str,
        *,
        actor_email: str,
        approval_manifest_hash: str = "",
        fairness_test_result: str = "",
        promoted_from_alias: str = "",
        extra_tags: dict[str, str] | None = None,
    ) -> AliasMove:
        """Point `alias` at `version`, writing the §7.4 audit tags on the version.

        The alias move is the atomic promotion; tags are the non-exclusive audit
        trail written alongside it. Exactly one version holds an alias at a time.
        """
        client = self._client()
        previous = self.alias_version(uc_full_name, alias)

        client.set_registered_model_alias(name=uc_full_name, alias=alias, version=version)

        tags = {
            "promoted_by": actor_email,
            "promoted_alias": alias,
            "promoted_timestamp": datetime.now(UTC).isoformat(),
        }
        if promoted_from_alias:
            tags["promoted_from_alias"] = promoted_from_alias
        if approval_manifest_hash:
            tags["approval_manifest_hash"] = approval_manifest_hash
        if fairness_test_result:
            tags["fairness_test_result"] = fairness_test_result
        if alias == CHAMPION and previous is not None:
            tags["previous_champion_version"] = str(previous)
        if extra_tags:
            tags.update(extra_tags)

        for key, value in tags.items():
            client.set_model_version_tag(name=uc_full_name, version=str(version), key=key, value=value)

        return AliasMove(
            uc_full_name=uc_full_name,
            alias=alias,
            version=version,
            previous_version=previous,
            tags_written=tags,
        )

    # ── rollback (§7.1: re-point @champion — atomic, auditable) ─────────────

    def rollback_champion(self, uc_full_name: str, *, actor_email: str, reason: str) -> AliasMove:
        """Re-point @champion to the version it replaced, per the tags on the
        current champion. Fails loudly if no rollback target is recorded."""
        client = self._client()
        current = self.alias_version(uc_full_name, CHAMPION)
        if current is None:
            raise RegistryServiceError(f"{uc_full_name} has no @{CHAMPION} alias to roll back.")

        current_mv = client.get_model_version(name=uc_full_name, version=str(current))
        prev_tag = (getattr(current_mv, "tags", None) or {}).get("previous_champion_version")
        if not prev_tag:
            raise RegistryServiceError(
                f"{uc_full_name} v{current} has no previous_champion_version tag — "
                "cannot determine a rollback target automatically. Roll back manually "
                "via promote() with an explicit version."
            )
        target = int(prev_tag)

        client.set_registered_model_alias(name=uc_full_name, alias=CHAMPION, version=target)

        tags = {
            "promoted_by": actor_email,
            "promoted_alias": CHAMPION,
            "promoted_timestamp": datetime.now(UTC).isoformat(),
            "promoted_from_alias": "rollback",
            "rollback_of_version": str(current),
            "rollback_reason": reason,
        }
        for key, value in tags.items():
            client.set_model_version_tag(name=uc_full_name, version=str(target), key=key, value=value)

        return AliasMove(
            uc_full_name=uc_full_name,
            alias=CHAMPION,
            version=target,
            previous_version=current,
            tags_written=tags,
        )

    # ── serving endpoint version (§15.2 step 6) ──────────────────────────────

    def update_champion_serving_version(self, endpoint_name: str, version: int) -> bool | None:
        """Point the endpoint's champion served entity at a numeric version.

        Live-verified 2026-07-07 (DECISIONS_NEEDED #3): entity_version rejects
        UC aliases ("Entity version must be a number"), so re-pointing
        @champion alone never moves traffic — promotion must update the
        endpoint config too.

        Returns True on update, None when the endpoint doesn't exist (batch/
        streaming projects have no serving endpoint — callers record skipped).
        """
        ws = self._ws()
        try:
            ep = ws.serving_endpoints.get(name=endpoint_name)
        except Exception as exc:
            msg = str(exc).lower()
            if "does not exist" in msg or "not found" in msg or "resource_does_not_exist" in msg:
                return None
            raise

        from databricks.sdk.service.serving import ServedEntityInput

        current = ep.config or ep.pending_config
        entities: list[Any] = []
        champion_found = False
        for se in (current.served_entities or []) if current else []:
            entity_version = se.entity_version
            if se.name == "champion":
                entity_version = str(version)
                champion_found = True
            entities.append(
                ServedEntityInput(
                    name=se.name,
                    entity_name=se.entity_name,
                    entity_version=entity_version,
                    workload_size=se.workload_size,
                    scale_to_zero_enabled=se.scale_to_zero_enabled,
                )
            )
        if not champion_found:
            raise RegistryServiceError(
                f"endpoint {endpoint_name!r} has no served entity named 'champion' — "
                "refusing to guess which entity to update."
            )
        ws.serving_endpoints.update_config(
            name=endpoint_name,
            served_entities=entities,
            traffic_config=current.traffic_config if current else None,
        )
        return True

    # ── cross-catalog registration (§7.2 promotion between env catalogs) ────

    def copy_version_to_catalog(self, src_model_uri: str, dest_uc_full_name: str) -> int:
        """Copy a model version into another environment's catalog
        (e.g. staging → prod) and return the new version number."""
        result = self._client().copy_model_version(src_model_uri=src_model_uri, dst_name=dest_uc_full_name)
        return int(result.version)
