"""Budget Policy Service — per-project cost attribution via Databricks'
native serverless Budget Policy feature (owner request, 2026-07-12).

Confirmed live against the pinned CLI's bundle schema (`databricks bundle
schema`, v1.6.0): `budget_policy_id` is a top-level [Public Preview] field
on both the job and model_serving_endpoint bundle resources — both of which
this app already generates serverless-only (§17.1), which is the only
compute shape Databricks' serverless usage policies attribute at all
(https://docs.databricks.com/aws/en/admin/usage/budget-policies — "do not
apply tags to classic compute resources"). Policy tags propagate into
system.billing.usage.custom_tags automatically once a workload references
the policy — no reconciliation-side change needed for that part.

Policy *creation* is an account-level API (AccountClient), a materially
different, higher-privilege credential than the workspace token every other
service in this app uses — kept as its own optional credential group.
Graceful degradation (§25 posture, reused here): no account credentials
configured -> BudgetPolicyUnavailable, callers skip attribution entirely
rather than crash project creation.

Idempotent by name: asking for a policy named "mlops-{project_name}" a
second time returns the existing one. No create-time duplicate-detection
API is documented, so this lists and matches client-side — a small, bounded
cost, run at most once per project at creation time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import AppConfig, get_config

# Reserved by Databricks itself — auto-populated onto usage records; a
# custom tag using one of these keys would silently be rejected/overwritten.
_RESERVED_TAG_KEYS = {"budget-policy-name", "budget-policy-id", "budget-policy-resolution-result"}


class BudgetPolicyUnavailable(RuntimeError):
    """Account-level credentials aren't configured (§25) — skip, don't crash."""


class BudgetPolicyServiceError(RuntimeError):
    """A budget-policy operation failed for a reason other than availability."""


@dataclass
class BudgetPolicyHandle:
    policy_id: str
    policy_name: str
    already_existed: bool = False


class BudgetPolicyService:
    def __init__(self, config: AppConfig | None = None, account_client: Any = None) -> None:
        self._cfg = config or get_config()
        self._client_override = account_client  # injectable for tests

    def _client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        if not self._cfg.has_account_credentials:
            raise BudgetPolicyUnavailable(
                "Account-level credentials not configured (DATABRICKS_ACCOUNT_HOST/_ID/"
                "_CLIENT_ID/_CLIENT_SECRET) — budget policy attribution skipped."
            )
        from databricks.sdk import AccountClient

        return AccountClient(
            host=self._cfg.databricks_account_host,
            account_id=self._cfg.databricks_account_id,
            client_id=self._cfg.databricks_account_client_id,
            client_secret=self._cfg.databricks_account_client_secret,
        )

    # ── lookup / idempotent create ───────────────────────────────────────────

    def find_by_name(self, policy_name: str) -> BudgetPolicyHandle | None:
        try:
            for p in self._client().budget_policy.list():
                if str(getattr(p, "policy_name", "")) == policy_name:
                    return BudgetPolicyHandle(str(p.policy_id), policy_name, already_existed=True)
        except BudgetPolicyUnavailable:
            raise
        except Exception as exc:
            raise BudgetPolicyServiceError(f"Failed to list budget policies: {exc}") from exc
        return None

    def ensure_policy(self, policy_name: str, custom_tags: dict[str, str] | None = None) -> BudgetPolicyHandle:
        """Returns the existing policy if one with this name already exists;
        otherwise creates it. Never creates a duplicate for the same name."""
        existing = self.find_by_name(policy_name)
        if existing is not None:
            return existing

        from databricks.sdk.service import compute
        from databricks.sdk.service.billing import BudgetPolicy

        tags = [
            compute.CustomPolicyTag(key=k, value=v)
            for k, v in (custom_tags or {}).items()
            if k not in _RESERVED_TAG_KEYS
        ]
        try:
            created = self._client().budget_policy.create(
                policy=BudgetPolicy(policy_name=policy_name, custom_tags=tags)
            )
        except BudgetPolicyUnavailable:
            raise
        except Exception as exc:
            raise BudgetPolicyServiceError(f"Failed to create budget policy {policy_name!r}: {exc}") from exc
        return BudgetPolicyHandle(str(created.policy_id), policy_name, already_existed=False)

    def delete_policy(self, policy_id: str) -> None:
        """Owner request 2026-07-13: project deletion disables cost
        attribution for the deleted project. Best-effort — a policy that's
        already gone (or account credentials unavailable) isn't an error
        worth blocking project deletion over."""
        try:
            self._client().budget_policy.delete(policy_id)
        except BudgetPolicyUnavailable:
            pass
        except Exception as exc:
            if "not found" not in str(exc).lower() and "does not exist" not in str(exc).lower():
                raise BudgetPolicyServiceError(f"Failed to delete budget policy {policy_id!r}: {exc}") from exc

    def ensure_default_policy(self) -> BudgetPolicyHandle:
        """Owner decision 2026-07-12: a pre-set MLOPS_DEFAULT_BUDGET_POLICY_ID
        is used as-is (no lookup, trusted); otherwise the named default
        (MLOPS_DEFAULT_BUDGET_POLICY_NAME) is ensured — created once, reused
        on every subsequent call."""
        if self._cfg.default_budget_policy_id:
            return BudgetPolicyHandle(
                self._cfg.default_budget_policy_id, self._cfg.default_budget_policy_name, already_existed=True
            )
        return self.ensure_policy(self._cfg.default_budget_policy_name, {"managed_by": "mlops_control_plane"})
