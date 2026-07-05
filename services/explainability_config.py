"""Explainability delivery configuration — per-item sync/async (§12.2, §12.4).

Full SHAP inline directly conflicts with §9.1's route-optimization default
(KernelExplainer adds hundreds of ms). Delivery is therefore configured per
item, with a *structural* safety net rather than a documentation warning:

  - items known to be expensive are demoted from sync to async automatically
    (full_shap_vector always; top_3_feature_contributions unless the model has
    a fast TreeExplainer path)
  - counterfactual_example is always async regardless of model type (§12.4 —
    it's a search problem, not a forward pass; DiCE default per accepted §29.2)
  - a measured sync latency above sync_latency_budget_ms demotes at runtime

resolve() returns the effective plan plus the demotions it applied, so the
telemetry decorator computes only genuinely-sync items inline and the review
UI can say why an item is arriving late (§12.2 / HITL §11.3 interplay).

Method default per accepted §29.2 suggestion: SHAP with TreeExplainer for
tree models, LIME only when no fast SHAP path exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TREE_MODEL_TYPES = frozenset({"xgboost", "lightgbm", "random_forest", "randomforest", "decision_tree", "catboost"})

# Items cheap enough to ever be sync, and under what condition.
_ALWAYS_ASYNC = frozenset({"full_shap_vector", "counterfactual_example"})
_TREE_ONLY_SYNC = frozenset({"top_3_feature_contributions"})

DEFAULT_SYNC_BUDGET_MS = 50


class ExplainabilityConfigError(ValueError):
    """Raised for configurations that are structurally invalid (not demotable)."""


@dataclass
class ExplainabilityItem:
    name: str
    delivery: str  # requested: sync | async
    method: str = ""  # per-item override (e.g. dice for counterfactuals)


@dataclass
class ResolvedItem:
    name: str
    delivery: str  # effective: sync | async
    method: str
    demoted: bool = False
    demotion_reason: str = ""


@dataclass
class ExplainabilityPlan:
    method: str
    sync_latency_budget_ms: int
    items: list[ResolvedItem] = field(default_factory=list)

    @property
    def sync_items(self) -> list[ResolvedItem]:
        return [i for i in self.items if i.delivery == "sync"]

    @property
    def async_items(self) -> list[ResolvedItem]:
        return [i for i in self.items if i.delivery == "async"]


def default_method(model_type: str) -> str:
    """§29.2 accepted default: SHAP when a fast explainer exists, else LIME."""
    return "shap" if model_type.lower() in TREE_MODEL_TYPES else "lime"


def resolve(
    *,
    model_type: str,
    items: list[ExplainabilityItem],
    method: str = "",
    sync_latency_budget_ms: int = DEFAULT_SYNC_BUDGET_MS,
    measured_sync_latency_ms: dict[str, float] | None = None,
) -> ExplainabilityPlan:
    """Resolve requested deliveries into an effective plan, demoting unsafe
    sync items instead of letting them blow the serving latency budget."""
    if sync_latency_budget_ms <= 0:
        raise ExplainabilityConfigError("sync_latency_budget_ms must be positive.")

    is_tree = model_type.lower() in TREE_MODEL_TYPES
    effective_method = method or default_method(model_type)
    measured = measured_sync_latency_ms or {}

    resolved: list[ResolvedItem] = []
    seen: set[str] = set()
    for item in items:
        if item.name in seen:
            raise ExplainabilityConfigError(f"Duplicate explainability item {item.name!r}.")
        seen.add(item.name)
        if item.delivery not in ("sync", "async"):
            raise ExplainabilityConfigError(
                f"Item {item.name!r}: delivery must be sync or async, got {item.delivery!r}."
            )

        item_method = item.method or ("dice" if item.name == "counterfactual_example" else effective_method)
        delivery, demoted, reason = item.delivery, False, ""

        if item.delivery == "sync":
            if item.name in _ALWAYS_ASYNC:
                delivery, demoted = "async", True
                reason = (
                    "always async: counterfactual search is an optimization problem (§12.4)"
                    if item.name == "counterfactual_example"
                    else "always async: full SHAP is expensive regardless of model type (§12.2)"
                )
            elif item.name in _TREE_ONLY_SYNC and not is_tree:
                delivery, demoted = "async", True
                reason = f"sync only safe with a fast TreeExplainer; {model_type} has none (§12.2)"
            elif measured.get(item.name, 0) > sync_latency_budget_ms:
                delivery, demoted = "async", True
                reason = (
                    f"measured {measured[item.name]:.0f}ms exceeds "
                    f"sync_latency_budget_ms={sync_latency_budget_ms} (§12.2 auto-demotion)"
                )

        resolved.append(
            ResolvedItem(
                name=item.name,
                delivery=delivery,
                method=item_method,
                demoted=demoted,
                demotion_reason=reason,
            )
        )

    return ExplainabilityPlan(
        method=effective_method,
        sync_latency_budget_ms=sync_latency_budget_ms,
        items=resolved,
    )
