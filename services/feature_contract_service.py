"""Feature Contract Service — discovery + versioned, breakage-protected reuse (§8.5, §8.6).

Discovery (§8.5): the catalog search backs pages/08_feature_catalog.py with a
live "used by N models" count computed from feature_lineage — the same query
that feeds §14's Reuse Metric, deliberately not a second implementation.

Versioning (§8.6, with the accepted §29.3 hardening):
  - non-breaking change → releases immediately, consumers notified via audit
  - breaking change with consumers → held in pending_acks until every consuming
    project's owner acknowledges; release() fails closed while acks are missing
  - a consuming project pins the feature version it trained against at
    training time (training-pipeline integration, phase 7 follow-up), so an
    owner's change never retroactively alters training lineage
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from services.state_service import StateService


class FeatureContractError(RuntimeError):
    """Raised when a feature-contract operation fails or preconditions aren't met."""


@dataclass
class ChangeProposal:
    change_id: str
    feature_id: str
    to_version: str
    status: str  # pending_acks | released
    consumers: list[str]  # project_ids that must ack (breaking only)


class FeatureContractService:
    def __init__(self, state: StateService | None = None) -> None:
        self._state = state or StateService()

    def _tbl(self, name: str) -> str:
        return self._state._tbl(name)

    # ── §8.5 discovery ───────────────────────────────────────────────────────

    def catalog_search(self, query: str = "", shared_only: bool = False) -> list[dict[str, Any]]:
        """Searchable feature list with live used-by-N-models counts."""
        where = "WHERE f.is_active = true"
        params: dict[str, Any] = {}
        if query:
            where += (
                " AND (f.feature_name LIKE :pattern"
                " OR f.feature_description LIKE :pattern"
                " OR f.owner_team LIKE :pattern)"
            )
            params["pattern"] = f"%{query}%"
        if shared_only:
            where += " AND f.is_shared = true"

        return self._state._exec(
            f"""SELECT f.feature_id, f.feature_name, f.feature_description,
                       f.feature_table_name, f.owner_email, f.owner_team,
                       f.freshness_hours, f.feature_version, f.is_shared,
                       coalesce(u.used_by_models, 0) AS used_by_models
                FROM {self._tbl("features")} f
                LEFT JOIN (
                  SELECT feature_id,
                         count(DISTINCT model_id) AS used_by_models
                  FROM {self._tbl("feature_lineage")}
                  LATERAL VIEW explode(downstream_model_ids) AS model_id
                  GROUP BY feature_id
                ) u ON u.feature_id = f.feature_id
                {where}
                ORDER BY used_by_models DESC, f.feature_name""",
            params or None,
        )

    def consumers_of(self, feature_id: str) -> list[str]:
        """Distinct consuming project_ids, resolved via downstream model ids."""
        rows = self._state._exec(
            f"""SELECT DISTINCT m.project_id
                FROM {self._tbl("feature_lineage")} fl
                LATERAL VIEW explode(fl.downstream_model_ids) AS model_id
                JOIN {self._tbl("models")} m ON m.model_id = model_id
                WHERE fl.feature_id = :feature_id""",
            {"feature_id": feature_id},
        )
        return [str(r["project_id"]) for r in rows if r.get("project_id")]

    # ── §8.6 version changes ─────────────────────────────────────────────────

    def propose_change(
        self,
        *,
        feature_id: str,
        to_version: str,
        is_breaking: bool,
        description: str,
        proposed_by: str,
    ) -> ChangeProposal:
        feature_rows = self._state._exec(
            f"SELECT feature_version FROM {self._tbl('features')} WHERE feature_id = :feature_id",
            {"feature_id": feature_id},
        )
        if not feature_rows:
            raise FeatureContractError(f"Feature {feature_id} not found.")
        from_version = str(feature_rows[0].get("feature_version") or "")

        consumers = self.consumers_of(feature_id) if is_breaking else []
        status = "pending_acks" if consumers else "released"

        change_id = str(uuid.uuid4())
        self._state._exec(
            f"""INSERT INTO {self._tbl("feature_contract_changes")}
                (change_id, feature_id, from_version, to_version, is_breaking,
                 description, status, proposed_by, created_timestamp, released_timestamp)
                VALUES (:change_id, :feature_id, :from_version, :to_version, :is_breaking,
                        :description, :status, :proposed_by, current_timestamp(),
                        CASE WHEN :status = 'released' THEN current_timestamp() END)""",
            {
                "change_id": change_id,
                "feature_id": feature_id,
                "from_version": from_version,
                "to_version": to_version,
                "is_breaking": is_breaking,
                "description": description,
                "status": status,
                "proposed_by": proposed_by,
            },
        )
        if status == "released":
            self._bump_version(feature_id, to_version)

        # Consumers hear about every change — blocking ack only for breaking (§8.6)
        self._state.log_audit(
            action_type="feature_change_proposed" if consumers else "feature_change_released",
            actor_email=proposed_by,
            actor_role="feature_owner",
            resource_type="feature",
            resource_id=feature_id,
            change_details={
                "change_id": change_id,
                "to_version": to_version,
                "is_breaking": is_breaking,
                "consumers_requiring_ack": consumers,
                "description": description,
            },
        )
        return ChangeProposal(change_id, feature_id, to_version, status, consumers)

    def acknowledge(self, *, change_id: str, project_id: str, acked_by: str) -> None:
        """Idempotent consumer acknowledgment — MERGE keyed on the PK."""
        self._state._exec(
            f"""MERGE INTO {self._tbl("feature_change_acks")} t
                USING (SELECT :change_id AS change_id, :project_id AS project_id) s
                ON t.change_id = s.change_id AND t.project_id = s.project_id
                WHEN NOT MATCHED THEN INSERT
                  (change_id, project_id, acked_by, acked_timestamp)
                VALUES (:change_id, :project_id, :acked_by, current_timestamp())""",
            {"change_id": change_id, "project_id": project_id, "acked_by": acked_by},
        )

    def pending_acks(self, change_id: str) -> list[str]:
        """Consumers who haven't acknowledged yet — the release blocker list."""
        change = self._get_change(change_id)
        consumers = set(self.consumers_of(str(change["feature_id"])))
        acked_rows = self._state._exec(
            f"SELECT project_id FROM {self._tbl('feature_change_acks')} WHERE change_id = :change_id",
            {"change_id": change_id},
        )
        acked = {str(r["project_id"]) for r in acked_rows}
        return sorted(consumers - acked)

    def release(self, change_id: str, actor_email: str) -> None:
        """Release a breaking change. Fails closed while any consumer ack is missing."""
        change = self._get_change(change_id)
        if str(change["status"]) == "released":
            return  # idempotent
        missing = self.pending_acks(change_id)
        if missing:
            raise FeatureContractError(
                f"Cannot release change {change_id}: awaiting acknowledgment from "
                f"consuming project(s) {', '.join(missing)} (§8.6/§29.3 — "
                "breaking shared-feature changes never ship on notify-only)."
            )
        self._state._exec(
            f"""UPDATE {self._tbl("feature_contract_changes")}
                SET status = 'released', released_timestamp = current_timestamp()
                WHERE change_id = :change_id""",
            {"change_id": change_id},
        )
        self._bump_version(str(change["feature_id"]), str(change["to_version"]))
        self._state.log_audit(
            action_type="feature_change_released",
            actor_email=actor_email,
            actor_role="feature_owner",
            resource_type="feature",
            resource_id=str(change["feature_id"]),
            change_details={"change_id": change_id, "to_version": change["to_version"]},
        )

    # ── internals ────────────────────────────────────────────────────────────

    def _get_change(self, change_id: str) -> dict[str, Any]:
        rows = self._state._exec(
            f"SELECT * FROM {self._tbl('feature_contract_changes')} WHERE change_id = :change_id",
            {"change_id": change_id},
        )
        if not rows:
            raise FeatureContractError(f"Change {change_id} not found.")
        return rows[0]

    def _bump_version(self, feature_id: str, to_version: str) -> None:
        self._state._exec(
            f"""UPDATE {self._tbl("features")}
                SET feature_version = :to_version, last_updated = current_timestamp()
                WHERE feature_id = :feature_id""",
            {"to_version": to_version, "feature_id": feature_id},
        )
