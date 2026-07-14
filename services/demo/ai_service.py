"""DemoAiService — AiService's public interface without any model-serving
call. Overrides `_chat`, the seam every public method (and two ad-hoc
direct callers in the wizard's Step 3/4) funnels through, with lightweight
heuristics keyed off the prompt shape, plus the public wrapper methods for
the call sites that use those directly.
"""

from __future__ import annotations

import json
import re
from typing import Any

_PII_KEYWORDS = (
    "email",
    "ssn",
    "social_security",
    "phone",
    "address",
    "dob",
    "birth",
    "zip",
    "postal",
    "name",
    "passport",
    "license",
)

_PROXY_KEYWORDS = {
    "zip": "Race / Ethnicity",
    "postal": "Race / Ethnicity",
    "region": "Race / Ethnicity",
    "neighborhood": "Race / Ethnicity",
    "school": "Race / Ethnicity",
    "age": "Age",
    "birth": "Age",
}


def _looks_pii(column: str) -> bool:
    col = column.lower()
    return any(kw in col for kw in _PII_KEYWORDS)


class DemoAiService:
    def __init__(self, config: Any = None) -> None:
        pass

    # ── direct _chat callers (Step 3 sensitivity scan, Step 4 proxy scan) ─────

    def _chat(self, system: str, user: str, max_tokens: int = 1000) -> str:
        if "PII" in system and "JSON" in system:
            return self._fake_pii_json(user)
        if "public / internal / sensitive / restricted" in system:
            return self._fake_classification_json(user)
        if "proxy" in system.lower():
            return self._fake_proxy_json(user)
        if "SHAP" in user or "SHapley" in system:
            return self._fake_shap_text(user)
        if "LIME" in user or "LIME" in system:
            return self._fake_lime_text(user)
        return "(demo) Simulated LLM response — no model endpoint was called."

    def _fake_pii_json(self, user: str) -> str:
        try:
            columns = json.loads(user.split("Column names to evaluate:\n", 1)[1])
        except Exception:
            columns = []
        results = [
            {
                "column": c,
                "is_pii": _looks_pii(c),
                "reason": "(demo) keyword heuristic, not an LLM call",
                "confidence": "medium",
            }
            for c in columns
        ]
        return json.dumps({"results": results})

    def _fake_classification_json(self, user: str) -> str:
        cols_part = user.split("Columns:", 1)[-1]
        columns = [c.strip() for c in cols_part.split(",") if c.strip()]
        return json.dumps({c: ("sensitive" if _looks_pii(c) else "internal") for c in columns})

    def _fake_proxy_json(self, user: str) -> str:
        match = re.search(r"Features:\s*(.+)", user)
        columns = [c.strip() for c in match.group(1).split(",")] if match else []
        flagged = []
        for col in columns:
            for kw, protected in _PROXY_KEYWORDS.items():
                if kw in col.lower():
                    flagged.append(
                        {
                            "column": col,
                            "protected_classes": [protected],
                            "justification": f"(demo) '{col}' commonly correlates with {protected.lower()}",
                        }
                    )
                    break
        return json.dumps(flagged)

    def _fake_shap_text(self, user: str) -> str:
        features = re.findall(r"^\s*([\w.]+):\s*(-?[\d.]+)", user, re.MULTILINE)
        top = features[:3]
        if not top:
            return "(demo) No feature importances were provided to interpret."
        lines = ", ".join(f"**{name}**" for name, _ in top)
        return (
            "_(demo) simulated interpretation — no model endpoint was called._\n\n"
            f"The model's predictions are driven most by {lines}. In a real run this section "
            "explains, in plain language, how these top features push predictions up or down."
        )

    def _fake_lime_text(self, user: str) -> str:
        pred_match = re.search(r"Prediction:\s*(-?[\d.]+)", user)
        prediction = pred_match.group(1) if pred_match else "?"
        weights = re.findall(r"^\s*(.+?):\s*([+-][\d.]+)", user, re.MULTILINE)
        top = weights[:3]
        detail = ", ".join(f"{name} ({weight})" for name, weight in top) or "the top contributing features"
        return (
            "_(demo) simulated interpretation — no model endpoint was called._\n\n"
            f"For this prediction ({prediction}), {detail} had the largest local influence."
        )

    # ── public wrappers (used by pages/06_project_dashboard.py's SHAP tab) ────

    def check_pii(self, columns: list[str]) -> list[dict[str, Any]]:
        if not columns:
            return []
        return [
            {
                "column": c,
                "is_pii": _looks_pii(c),
                "reason": "(demo) keyword heuristic, not an LLM call",
                "confidence": "medium",
            }
            for c in columns
        ]

    def interpret_shap(
        self,
        shap_values: dict[str, float],
        model_name: str,
        target_variable: str = "the target",
        protected_classes: list[str] | None = None,
    ) -> str:
        sorted_features = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        lines = ", ".join(f"**{name}**" for name, _ in sorted_features) or "the top features"
        return (
            "_(demo) simulated interpretation — no model endpoint was called._\n\n"
            f"For `{model_name}` predicting {target_variable}, {lines} contribute most to the outcome."
        )

    def interpret_lime(self, lime_weights: dict[str, float], prediction: float, model_name: str) -> str:
        sorted_weights = sorted(lime_weights.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        lines = ", ".join(name for name, _ in sorted_weights) or "the top features"
        return (
            f"_(demo) simulated interpretation — no model endpoint was called._\n\n"
            f"For `{model_name}` (prediction {prediction}), {lines} had the largest local influence."
        )
