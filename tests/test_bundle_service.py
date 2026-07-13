"""Tests for bundle_service — template rendering, plan/deploy flow, guards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from config import AppConfig
from services.bundle_service import (
    PINNED_CLI_VERSION,
    BundleService,
    BundleServiceError,
    CliResult,
    PlanSummary,
    unix_cron_to_quartz,
)


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
        projects_catalog="mlops",
        projects_catalog_dev="",
        projects_catalog_staging="",
        projects_catalog_prod="",
    )


class FakeRunner:
    """Records CLI invocations and returns canned results."""

    def __init__(self, results: dict[str, CliResult] | None = None):
        self.calls: list[list[str]] = []
        self.results = results or {}

    def __call__(self, args: list[str], cwd: Path | None = None) -> CliResult:
        self.calls.append(list(args))
        key = " ".join(args[:2])
        return self.results.get(key, CliResult(args=args, returncode=0, stdout="{}", stderr=""))


def _interview(**overrides) -> dict:
    base = {
        "inference_type": "batch",
        "batch_schedule": "0 2 * * *",
        "retraining_schedule": "0 3 * * 0",
    }
    base.update(overrides)
    return base


class TestCronConversion:
    def test_daily(self):
        assert unix_cron_to_quartz("0 2 * * *") == "0 0 2 * * ?"

    def test_weekly_dow_renumbered_for_quartz(self):
        # unix Sunday=0 → Quartz Sunday=1 (live API rejects unix numbering)
        assert unix_cron_to_quartz("0 3 * * 0") == "0 0 3 ? * 1"

    def test_dow_seven_is_sunday(self):
        assert unix_cron_to_quartz("0 3 * * 7") == "0 0 3 ? * 1"

    def test_dow_range_renumbered(self):
        # weekdays Mon-Fri: unix 1-5 → Quartz 2-6
        assert unix_cron_to_quartz("0 9 * * 1-5") == "0 0 9 ? * 2-6"

    def test_monthly_dom(self):
        assert unix_cron_to_quartz("30 1 1 * *") == "0 30 1 1 * ?"

    def test_already_quartz_passthrough(self):
        assert unix_cron_to_quartz("0 0 2 * * ?") == "0 0 2 * * ?"

    def test_garbage_raises(self):
        with pytest.raises(BundleServiceError):
            unix_cron_to_quartz("not a cron")


class TestGenerate:
    def test_batch_project_renders_jobs_only(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)

        assert (bundle_dir / "databricks.yml").exists()
        assert (bundle_dir / "resources" / "schemas.yml").exists()
        assert (bundle_dir / "resources" / "jobs.yml").exists()
        assert not (bundle_dir / "resources" / "model_serving.yml").exists()
        assert (bundle_dir / "src" / "train.py").exists()
        assert (bundle_dir / "src" / "batch_score.py").exists()

    def test_databricks_yml_targets_and_catalogs(self, cfg, tmp_path):
        # Schema-per-project inside a configurable catalog (decision 2026-07-07)
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)
        doc = yaml.safe_load((bundle_dir / "databricks.yml").read_text())

        assert doc["bundle"]["name"] == "churn"
        assert doc["targets"]["dev"]["variables"]["catalog"] == "mlops"
        assert doc["targets"]["dev"]["variables"]["schema"] == "churn_dev"
        assert doc["targets"]["prod"]["variables"]["catalog"] == "mlops"
        assert doc["targets"]["prod"]["variables"]["schema"] == "churn_prod"
        assert doc["targets"]["prod"]["mode"] == "production"
        assert doc["targets"]["dev"]["workspace"]["host"] == cfg.databricks_host

    def test_per_env_catalog_override_is_config_only(self, cfg, tmp_path):
        # The 100+-project escape hatch: env-scoped catalogs via config alone
        cfg.projects_catalog_prod = "mlops_prod"
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)
        doc = yaml.safe_load((bundle_dir / "databricks.yml").read_text())

        assert doc["targets"]["dev"]["variables"]["catalog"] == "mlops"
        assert doc["targets"]["prod"]["variables"]["catalog"] == "mlops_prod"

    def test_schema_resource_declared(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)
        doc = yaml.safe_load((bundle_dir / "resources" / "schemas.yml").read_text())

        schema = doc["resources"]["schemas"]["churn_schema"]
        assert schema["catalog_name"] == "${var.catalog}"
        assert schema["name"] == "${var.schema}"

    def test_jobs_yml_shape(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)
        doc = yaml.safe_load((bundle_dir / "resources" / "jobs.yml").read_text())
        jobs = doc["resources"]["jobs"]

        assert set(jobs) == {"churn_training", "churn_retraining", "churn_batch_scoring"}
        # Quartz cron conversion applied
        assert jobs["churn_batch_scoring"]["schedule"]["quartz_cron_expression"] == "0 0 2 * * ?"
        # Serverless default: environments block, no new_cluster anywhere (§17.1)
        assert "environments" in jobs["churn_training"]
        assert "new_cluster" not in json.dumps(doc)
        assert jobs["churn_training"]["tags"]["project_id"] == "churn"

    def test_realtime_renders_serving_with_defaults_on(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(inference_type="real_time", batch_schedule=None, sla_latency_ms=200)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)
        doc = yaml.safe_load((bundle_dir / "resources" / "model_serving.yml").read_text())
        ep = doc["resources"]["model_serving_endpoints"]["churn_endpoint"]

        # §9.1 governance-by-default: both ON, route_optimized top-level
        assert ep["route_optimized"] is True
        assert ep["ai_gateway"]["inference_table_config"]["enabled"] is True
        # Inference log lands in the project schema (schema-per-project, 2026-07-07)
        assert ep["ai_gateway"]["inference_table_config"]["schema_name"] == "${var.schema}"
        assert "route_optimized" not in ep["config"]["served_entities"][0]

    def test_override_reason_turns_default_off(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(
            inference_type="real_time",
            batch_schedule=None,
            route_optimization_override_reason="pinned legacy VPC path",
        )
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)
        doc = yaml.safe_load((bundle_dir / "resources" / "model_serving.yml").read_text())
        ep = doc["resources"]["model_serving_endpoints"]["churn_endpoint"]

        assert ep["route_optimized"] is False
        # Inference capture stays on — overrides are independent
        assert ep["ai_gateway"]["inference_table_config"]["enabled"] is True

    def test_streaming_renders_continuous_job(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(
            inference_type="streaming",
            batch_schedule=None,
            streaming_source_table="bronze.events.clickstream",
        )
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)
        doc = yaml.safe_load((bundle_dir / "resources" / "jobs.yml").read_text())
        scorer = doc["resources"]["jobs"]["churn_streaming_scorer"]

        # §9.4: continuous is a top-level job field, no `trigger:` wrapper
        assert scorer["continuous"] == {"pause_status": "UNPAUSED"}
        assert "schedule" not in scorer
        assert (bundle_dir / "src" / "stream_score.py").exists()

    def test_budget_policy_id_omitted_when_not_resolved(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)
        doc = yaml.safe_load((bundle_dir / "resources" / "jobs.yml").read_text())

        assert "budget_policy_id" not in doc["resources"]["jobs"]["churn_training"]

    def test_budget_policy_id_rendered_on_every_job_when_resolved(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate(
            "churn", "retention", "a@co.com", _interview(), tmp_path, budget_policy_id="policy-abc123"
        )
        doc = yaml.safe_load((bundle_dir / "resources" / "jobs.yml").read_text())
        jobs = doc["resources"]["jobs"]

        assert jobs["churn_training"]["budget_policy_id"] == "policy-abc123"
        assert jobs["churn_retraining"]["budget_policy_id"] == "policy-abc123"
        assert jobs["churn_batch_scoring"]["budget_policy_id"] == "policy-abc123"

    def test_budget_policy_id_rendered_on_serving_endpoint(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(inference_type="real_time", batch_schedule=None)
        bundle_dir = svc.generate(
            "churn", "retention", "a@co.com", responses, tmp_path, budget_policy_id="policy-abc123"
        )
        doc = yaml.safe_load((bundle_dir / "resources" / "model_serving.yml").read_text())
        ep = doc["resources"]["model_serving_endpoints"]["churn_endpoint"]

        assert ep["budget_policy_id"] == "policy-abc123"


def _write_toolkits(tmp_path: Path, *, count: int = 2) -> Path:
    tk_dir = tmp_path / "toolkits"
    tk_dir.mkdir()
    entries = [
        "  - toolkit_id: mlops_toolkit\n"
        "    name: Acme MLOps Toolkit\n"
        "    pip_spec: acme-mlops-toolkit>=2.0\n"
        "    import_statement: import acme_mlops_toolkit as mlops\n",
        "  - toolkit_id: ds_toolkit\n"
        "    name: Acme DS Toolkit\n"
        "    pip_spec: git+https://github.com/acme-corp/ds-toolkit.git@main\n"
        "    import_statement: from acme_ds_toolkit import eda\n",
    ]
    (tk_dir / "org.yaml").write_text("toolkits:\n" + "".join(entries[:count]))
    return tk_dir


class TestAccelerants:
    """Owner request 2026-07-13: AutoML baseline + hyperparameter search,
    purely additive (§9.5) — neither renders unless explicitly opted into."""

    def test_neither_rendered_by_default(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)

        assert not (bundle_dir / "src" / "automl_baseline.py").exists()
        assert not (bundle_dir / "src" / "hyperparameter_search.py").exists()
        assert not (bundle_dir / "requirements.txt").exists()

    def test_automl_baseline_rendered_when_opted_in(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(use_automl_baseline=True, target_variable="churned")
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        automl_py = (bundle_dir / "src" / "automl_baseline.py").read_text()
        assert "from databricks import automl" in automl_py
        assert 'target_col="churned"' in automl_py

    def test_automl_classification_default(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(use_automl_baseline=True, performance_metric_types=["accuracy"])
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        automl_py = (bundle_dir / "src" / "automl_baseline.py").read_text()
        assert "automl.classify(" in automl_py
        assert "automl.regress(" not in automl_py

    def test_automl_regression_metric_routes_to_regress(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(use_automl_baseline=True, performance_metric_types=["rmse"])
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        automl_py = (bundle_dir / "src" / "automl_baseline.py").read_text()
        assert "automl.regress(" in automl_py

    def test_hyperparameter_search_rendered_when_opted_in(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(use_hyperparameter_search=True)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        hp_py = (bundle_dir / "src" / "hyperparameter_search.py").read_text()
        assert "import optuna" in hp_py
        assert "optuna.create_study" in hp_py

    def test_hyperparameter_search_adds_optuna_to_requirements(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(use_hyperparameter_search=True)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        assert "optuna>=3.6.0" in (bundle_dir / "requirements.txt").read_text()

    def test_toolkit_imports_injected_into_both_accelerants(self, cfg, tmp_path):
        tk_dir = _write_toolkits(tmp_path)
        svc = BundleService(config=cfg, runner=FakeRunner(), toolkits_dir=tk_dir)
        responses = _interview(use_automl_baseline=True, use_hyperparameter_search=True)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path / "out")

        automl_py = (bundle_dir / "src" / "automl_baseline.py").read_text()
        hp_py = (bundle_dir / "src" / "hyperparameter_search.py").read_text()
        assert "import acme_mlops_toolkit as mlops" in automl_py
        assert "import acme_mlops_toolkit as mlops" in hp_py

    def test_both_valid_python_syntax(self, cfg, tmp_path):
        import ast

        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = _interview(use_automl_baseline=True, use_hyperparameter_search=True)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        ast.parse((bundle_dir / "src" / "automl_baseline.py").read_text())
        ast.parse((bundle_dir / "src" / "hyperparameter_search.py").read_text())


class TestEvaluatePy:
    """Owner request 2026-07-13: evaluate.py was referenced in 3 places
    (interview_service.py, generator_service.py's change-scope script, Step
    6 help text) but never actually generated. Correctness of the generated
    logic itself (not just rendering) is proven by actually executing it —
    see the manual verification in PROJECT_STATUS.md; these tests cover
    what renders under which config."""

    def _responses(self, **overrides):
        base = _interview(
            target_variable="churned",
            model_frameworks=["xgboost"],
            performance_metric_types=["accuracy", "auc_roc"],
            bias_test_types=["fairlearn"],
            fairness_threshold_pct=10,
        )
        base.update(overrides)
        return base

    def test_always_rendered(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)

        assert (bundle_dir / "src" / "evaluate.py").exists()

    def test_only_selected_metrics_generated(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate(
            "churn", "retention", "a@co.com", self._responses(performance_metric_types=["precision"]), tmp_path
        )

        evaluate_py = (bundle_dir / "src" / "evaluate.py").read_text()
        assert 'results["precision"]' in evaluate_py
        assert 'results["accuracy"]' not in evaluate_py
        assert 'results["recall"]' not in evaluate_py

    def test_fairlearn_selected_generates_real_calls(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate(
            "churn", "retention", "a@co.com", self._responses(bias_test_types=["fairlearn"]), tmp_path
        )

        evaluate_py = (bundle_dir / "src" / "evaluate.py").read_text()
        assert "from fairlearn.metrics import demographic_parity_difference, equalized_odds_difference" in evaluate_py
        assert "from aif360.datasets import BinaryLabelDataset" not in evaluate_py

    def test_aif360_selected_generates_scaffold_not_fake_automation(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate(
            "churn", "retention", "a@co.com", self._responses(bias_test_types=["aif360"]), tmp_path
        )

        evaluate_py = (bundle_dir / "src" / "evaluate.py").read_text()
        # aif360 needs privileged-group values the app can't infer — scaffold
        # only, never pretend to call a real API with guessed group values.
        assert "# from aif360.datasets import BinaryLabelDataset" in evaluate_py
        assert "ClassificationMetric(" not in evaluate_py

    def test_fairness_threshold_and_sensitive_columns_rendered(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        responses = self._responses(
            fairness_threshold_pct=15,
            proxy_variables=[{"column": "zip_code", "protected_classes": ["Race / Ethnicity"], "justification": "x"}],
        )
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        evaluate_py = (bundle_dir / "src" / "evaluate.py").read_text()
        assert "FAIRNESS_THRESHOLD_PCT = 15" in evaluate_py
        assert "'zip_code': ['Race / Ethnicity']" in evaluate_py

    def test_explainability_method_matches_tree_default_for_xgboost(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate(
            "churn", "retention", "a@co.com", self._responses(model_frameworks=["xgboost"]), tmp_path
        )

        evaluate_py = (bundle_dir / "src" / "evaluate.py").read_text()
        assert 'method = "shap"' in evaluate_py

    def test_explainability_method_falls_back_to_lime_for_non_tree_model(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate(
            "churn", "retention", "a@co.com", self._responses(model_frameworks=["pytorch"]), tmp_path
        )

        evaluate_py = (bundle_dir / "src" / "evaluate.py").read_text()
        assert 'method = "lime"' in evaluate_py

    def test_valid_python_syntax(self, cfg, tmp_path):
        import ast

        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", self._responses(), tmp_path)

        ast.parse((bundle_dir / "src" / "evaluate.py").read_text())


class TestFeatureEngineeringIntegration:
    """Owner request 2026-07-13: real FeatureLookup/create_training_set
    codegen for feature columns resolved to a Feature Catalog entry in
    Step 3, grouped by source table (verified live: table_name/feature_names/
    lookup_key and df/feature_lookups/label are the real parameter names)."""

    def _responses_with_resolutions(self, resolutions, **overrides):
        base = _interview(target_variable="churned", feature_columns=list(resolutions.keys()))
        base["feature_catalog_resolutions"] = resolutions
        base.update(overrides)
        return base

    def test_no_resolutions_falls_back_to_plain_read(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)

        train_py = (bundle_dir / "src" / "train.py").read_text()
        assert "FeatureEngineeringClient" not in train_py
        assert "spark.table" in train_py

    def test_shared_feature_generates_lookup(self, cfg, tmp_path):
        responses = self._responses_with_resolutions(
            {
                "policyholder_zip": {
                    "resolved": "shared",
                    "feature_table_name": "mlops.shared.geo_risk_features",
                    "feature_column_name": "policyholder_zip",
                }
            }
        )
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        train_py = (bundle_dir / "src" / "train.py").read_text()
        assert "from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup" in train_py
        assert 'table_name="mlops.shared.geo_risk_features"' in train_py
        assert "'policyholder_zip'" in train_py
        assert 'label="churned"' in train_py
        assert "fe.log_model" in train_py

    def test_columns_from_same_table_grouped_into_one_lookup(self, cfg, tmp_path):
        responses = self._responses_with_resolutions(
            {
                "a": {"resolved": "shared", "feature_table_name": "mlops.shared.t1", "feature_column_name": "a"},
                "b": {"resolved": "shared", "feature_table_name": "mlops.shared.t1", "feature_column_name": "b"},
            }
        )
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        train_py = (bundle_dir / "src" / "train.py").read_text()
        assert train_py.count("FeatureLookup(") == 1
        assert 'table_name="mlops.shared.t1"' in train_py

    def test_adhoc_columns_never_generate_lookups(self, cfg, tmp_path):
        responses = self._responses_with_resolutions(
            {"vendor_score": {"resolved": "adhoc", "justification": "project-specific"}}
        )
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        train_py = (bundle_dir / "src" / "train.py").read_text()
        assert "FeatureEngineeringClient" not in train_py

    def test_mixed_shared_and_adhoc_names_the_adhoc_columns_in_the_todo(self, cfg, tmp_path):
        responses = self._responses_with_resolutions(
            {
                "a": {"resolved": "shared", "feature_table_name": "mlops.shared.t1", "feature_column_name": "a"},
                "vendor_score": {"resolved": "adhoc", "justification": "project-specific"},
            }
        )
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        train_py = (bundle_dir / "src" / "train.py").read_text()
        assert "vendor_score" in train_py  # surfaced in the base_df TODO comment

    def test_base_df_uses_first_training_dataset_when_known(self, cfg, tmp_path):
        responses = self._responses_with_resolutions(
            {"a": {"resolved": "shared", "feature_table_name": "mlops.shared.t1", "feature_column_name": "a"}},
            training_datasets=["acme.risk.property_training"],
        )
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        train_py = (bundle_dir / "src" / "train.py").read_text()
        assert 'spark.table("acme.risk.property_training")' in train_py

    def test_train_py_stays_valid_python_with_lookups(self, cfg, tmp_path):
        import ast

        responses = self._responses_with_resolutions(
            {
                "a": {"resolved": "shared", "feature_table_name": "mlops.shared.t1", "feature_column_name": "a"},
                "b": {"resolved": "adhoc", "justification": "x"},
            }
        )
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path)

        ast.parse((bundle_dir / "src" / "train.py").read_text())


class TestToolkitImports:
    """Owner request 2026-07-13: org-configured auto-import into generated
    training/EDA code, mirroring the policy_packs YAML convention."""

    def test_eda_py_always_rendered(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)

        assert (bundle_dir / "src" / "eda.py").exists()

    def test_no_toolkits_configured_no_requirements_txt_no_imports(self, cfg, tmp_path):
        empty_dir = tmp_path / "empty_toolkits"
        empty_dir.mkdir()
        svc = BundleService(config=cfg, runner=FakeRunner(), toolkits_dir=empty_dir)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path / "out")

        assert not (bundle_dir / "requirements.txt").exists()
        assert "acme" not in (bundle_dir / "src" / "train.py").read_text()
        assert "Org toolkits" not in (bundle_dir / "src" / "eda.py").read_text()

    def test_toolkits_configured_requirements_txt_rendered(self, cfg, tmp_path):
        tk_dir = _write_toolkits(tmp_path)
        svc = BundleService(config=cfg, runner=FakeRunner(), toolkits_dir=tk_dir)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path / "out")

        reqs = (bundle_dir / "requirements.txt").read_text()
        assert "acme-mlops-toolkit>=2.0" in reqs
        assert "git+https://github.com/acme-corp/ds-toolkit.git@main" in reqs

    def test_toolkits_configured_imports_injected_into_train_py(self, cfg, tmp_path):
        tk_dir = _write_toolkits(tmp_path)
        svc = BundleService(config=cfg, runner=FakeRunner(), toolkits_dir=tk_dir)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path / "out")

        train_py = (bundle_dir / "src" / "train.py").read_text()
        assert "import acme_mlops_toolkit as mlops" in train_py
        assert "from acme_ds_toolkit import eda" in train_py

    def test_toolkits_configured_imports_injected_into_eda_py(self, cfg, tmp_path):
        tk_dir = _write_toolkits(tmp_path)
        svc = BundleService(config=cfg, runner=FakeRunner(), toolkits_dir=tk_dir)
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path / "out")

        eda_py = (bundle_dir / "src" / "eda.py").read_text()
        assert "import acme_mlops_toolkit as mlops" in eda_py
        assert "from acme_ds_toolkit import eda" in eda_py

    def test_eda_py_widgets_default_to_dev_catalog_schema(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)

        eda_py = (bundle_dir / "src" / "eda.py").read_text()
        assert 'dbutils.widgets.text("catalog", "mlops")' in eda_py
        assert 'dbutils.widgets.text("schema", "churn_dev")' in eda_py

    def test_eda_py_points_at_same_mlflow_experiment_generator_creates(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)

        eda_py = (bundle_dir / "src" / "eda.py").read_text()
        assert 'mlflow.set_experiment("/Shared/mlops/churn")' in eda_py

    def test_batch_score_and_stream_score_not_touched_by_toolkits(self, cfg, tmp_path):
        # Scoped deliberately to train.py + eda.py (EDA/feature-selection/
        # training) — not the inference-time scripts, which weren't part
        # of the ask.
        tk_dir = _write_toolkits(tmp_path)
        svc = BundleService(config=cfg, runner=FakeRunner(), toolkits_dir=tk_dir)
        responses = _interview(inference_type="batch", batch_schedule="0 2 * * *")
        bundle_dir = svc.generate("churn", "retention", "a@co.com", responses, tmp_path / "out")

        assert "acme" not in (bundle_dir / "src" / "batch_score.py").read_text()


class TestHealthCheck:
    def test_version_match_passes(self, cfg):
        runner = FakeRunner({"--version": CliResult(["--version"], 0, f"Databricks CLI v{PINNED_CLI_VERSION}", "")})
        svc = BundleService(config=cfg, cli_path="/bin/true", runner=runner)
        assert PINNED_CLI_VERSION in svc.health_check()

    def test_version_drift_fails_loudly(self, cfg):
        runner = FakeRunner({"--version": CliResult(["--version"], 0, "Databricks CLI v0.230.0", "")})
        svc = BundleService(config=cfg, cli_path="/bin/true", runner=runner)
        with pytest.raises(BundleServiceError, match="version drift"):
            svc.health_check()

    def test_missing_binary_fails(self, cfg):
        svc = BundleService(config=cfg, cli_path="/nonexistent/databricks", runner=FakeRunner())
        with pytest.raises(BundleServiceError, match="not found"):
            svc.health_check()


class TestPlanDeploy:
    PLAN_JSON = json.dumps(
        {"plan": {"jobs.churn_training": {"action": "create"}, "jobs.churn_batch_scoring": {"action": "create"}}}
    )

    def _svc_with_plan(self, cfg) -> tuple[BundleService, FakeRunner]:
        runner = FakeRunner({"bundle plan": CliResult(["bundle", "plan"], 0, self.PLAN_JSON, "")})
        return BundleService(config=cfg, runner=runner), runner

    def test_plan_persists_file_and_hash(self, cfg, tmp_path):
        svc, _ = self._svc_with_plan(cfg)
        plan = svc.plan(tmp_path, "dev")

        assert plan.plan_path.exists()
        assert plan.plan_hash == hashlib.sha256(self.PLAN_JSON.encode()).hexdigest()
        assert {a["action"] for a in plan.actions} == {"create"}
        assert len(plan.actions) == 2
        assert not plan.is_noop

    def test_deploy_uses_reviewed_plan_file(self, cfg, tmp_path):
        svc, runner = self._svc_with_plan(cfg)
        plan = svc.plan(tmp_path, "dev")
        svc.deploy(tmp_path, plan)

        deploy_call = runner.calls[-1]
        assert deploy_call[:2] == ["bundle", "deploy"]
        assert "--plan" in deploy_call
        assert str(plan.plan_path) in deploy_call

    def test_deploy_refuses_tampered_plan(self, cfg, tmp_path):
        svc, _ = self._svc_with_plan(cfg)
        plan = svc.plan(tmp_path, "dev")
        plan.plan_path.write_text('{"plan": {"jobs.malicious": {"action": "create"}}}')

        with pytest.raises(BundleServiceError, match="changed since it was reviewed"):
            svc.deploy(tmp_path, plan)

    def test_deploy_refuses_missing_plan(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        ghost = PlanSummary(target="dev", plan_path=tmp_path / "nope.json", plan_hash="x")
        with pytest.raises(BundleServiceError, match="missing"):
            svc.deploy(tmp_path, ghost)

    def test_plan_failure_raises(self, cfg, tmp_path):
        runner = FakeRunner({"bundle plan": CliResult(["bundle", "plan"], 1, "", "boom")})
        svc = BundleService(config=cfg, runner=runner)
        with pytest.raises(BundleServiceError, match="bundle plan failed"):
            svc.plan(tmp_path, "dev")

    def test_validate_failure_raises(self, cfg, tmp_path):
        runner = FakeRunner({"bundle validate": CliResult(["bundle", "validate"], 1, "", "bad yaml")})
        svc = BundleService(config=cfg, runner=runner)
        with pytest.raises(BundleServiceError, match="bundle validate failed"):
            svc.validate(tmp_path, "dev")

    def test_destroy_passes_target(self, cfg, tmp_path):
        runner = FakeRunner()
        svc = BundleService(config=cfg, runner=runner)
        svc.destroy(tmp_path, "dev")
        assert runner.calls[-1][:3] == ["bundle", "destroy", "-t"]
        assert "--auto-approve" in runner.calls[-1]
