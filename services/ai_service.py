"""LLM-powered analysis helpers using Databricks foundation model endpoints.

Uses the configured DATABRICKS_LLM_ENDPOINT (e.g. databricks-meta-llama-3-1-70b-instruct)
via the model serving REST API. Conservative PII detection: flag anything that
could be PII, not just obvious cases.
"""

from __future__ import annotations

import json
from typing import Any

from config import AppConfig, get_config

_PII_SYSTEM_PROMPT = """\
You are a privacy compliance expert. Given a list of column names from a machine \
learning training dataset, identify which columns contain or could contain \
Personally Identifiable Information (PII).

Apply a conservative standard: flag anything that COULD be PII, not just what obviously is.

PII categories:
- Direct identifiers: name, SSN, email, phone, address, DOB, ID numbers, IP address
- Quasi-identifiers: ZIP/postal code, exact age, occupation, marital status
- Sensitive attributes: medical conditions, financial data, political views, religion, biometrics
- Derived PII: any column that could uniquely identify a person when combined with others

Respond ONLY with valid JSON. No explanation text outside the JSON.
Format:
{
  "results": [
    {"column": "column_name", "is_pii": true, "reason": "one sentence", "confidence": "high"},
    ...
  ]
}"""

_SHAP_SYSTEM_PROMPT = """\
You are an ML interpretability expert helping non-technical business stakeholders \
understand model predictions. Given SHAP feature importance values, provide a clear \
and actionable interpretation.

Structure your response as markdown with these sections:
## Top Drivers
Which features most influence predictions and why (2-3 sentences).

## Risk Factors
Features that push predictions toward the high-risk outcome.

## Protective Factors
Features that reduce predicted risk.

## Fairness Note
Whether any declared protected class attributes or their known proxies appear \
in the top 10 features. Be specific.

## Recommended Actions
2-3 concrete things stakeholders should investigate or validate.

Be specific. Reference actual feature names. Keep language non-technical."""

_LIME_SYSTEM_PROMPT = """\
You are an ML interpretability expert. Given LIME local feature importance weights \
for a single prediction, explain in plain language why the model made this specific \
prediction. Reference actual feature values and weights.

Keep it under 150 words. Non-technical audience."""


class AiService:
    """LLM helpers using the configured Databricks foundation model endpoint."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._cfg = config or get_config()

    def _chat(self, system: str, user: str, max_tokens: int = 1000) -> str:
        """POST to the configured Databricks model serving endpoint."""
        import requests

        url = f"{self._cfg.databricks_host.rstrip('/')}/serving-endpoints/{self._cfg.llm_endpoint}/invocations"
        payload: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {self._cfg.databricks_token}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # ── PII detection ─────────────────────────────────────────────────────────

    def check_pii(self, columns: list[str]) -> list[dict[str, Any]]:
        """Check column names for PII risk.

        Args:
            columns: Column names to evaluate.

        Returns:
            List of {column, is_pii, reason, confidence} dicts.
            On parse failure, conservatively flags all columns for manual review.
        """
        if not columns:
            return []

        user_msg = f"Column names to evaluate:\n{json.dumps(columns)}"
        try:
            raw = self._chat(_PII_SYSTEM_PROMPT, user_msg, max_tokens=2000)
            parsed = json.loads(raw)
            return parsed.get("results", [])
        except json.JSONDecodeError:
            # Conservative fallback when LLM returns malformed JSON
            return [
                {
                    "column": col,
                    "is_pii": True,
                    "reason": "PII check failed to parse — manual review required",
                    "confidence": "low",
                }
                for col in columns
            ]

    # ── SHAP interpretation ───────────────────────────────────────────────────

    def interpret_shap(
        self,
        shap_values: dict[str, float],
        model_name: str,
        target_variable: str = "the target",
        protected_classes: list[str] | None = None,
    ) -> str:
        """Generate a business-readable interpretation of SHAP feature importance.

        Args:
            shap_values: {feature_name: mean_abs_shap_value}.
            model_name: Model name for context.
            target_variable: What the model predicts.
            protected_classes: Declared protected attributes to watch for in top features.

        Returns:
            Markdown-formatted interpretation.
        """
        sorted_features = sorted(shap_values.items(), key=lambda x: abs(x[1]), reverse=True)
        feature_list = "\n".join(f"  {name}: {value:.4f}" for name, value in sorted_features[:20])
        protected_note = ""
        if protected_classes:
            protected_note = f"\nDeclared protected classes: {', '.join(protected_classes)}"

        user_msg = (
            f"Model: {model_name}\n"
            f"Predicting: {target_variable}\n"
            f"{protected_note}\n\n"
            f"SHAP mean absolute values (top features, descending):\n{feature_list}"
        )
        return self._chat(_SHAP_SYSTEM_PROMPT, user_msg, max_tokens=800)

    # ── LIME interpretation ───────────────────────────────────────────────────

    def interpret_lime(
        self,
        lime_weights: dict[str, float],
        prediction: float,
        model_name: str,
    ) -> str:
        """Generate a plain-language explanation of a single LIME prediction.

        Args:
            lime_weights: {feature_description: weight} for one sample.
            prediction: The model's predicted value/probability for this sample.
            model_name: Model name for context.

        Returns:
            Plain-text explanation under ~150 words.
        """
        sorted_weights = sorted(lime_weights.items(), key=lambda x: abs(x[1]), reverse=True)
        weights_str = "\n".join(f"  {desc}: {weight:+.4f}" for desc, weight in sorted_weights[:10])
        user_msg = (
            f"Model: {model_name}\n"
            f"Prediction: {prediction:.4f}\n\n"
            f"LIME local feature weights for this prediction:\n{weights_str}"
        )
        return self._chat(_LIME_SYSTEM_PROMPT, user_msg, max_tokens=300)
