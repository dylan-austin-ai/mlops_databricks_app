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
        assert (bundle_dir / "resources" / "jobs.yml").exists()
        assert not (bundle_dir / "resources" / "model_serving.yml").exists()
        assert (bundle_dir / "src" / "train.py").exists()
        assert (bundle_dir / "src" / "batch_score.py").exists()

    def test_databricks_yml_targets_and_catalogs(self, cfg, tmp_path):
        svc = BundleService(config=cfg, runner=FakeRunner())
        bundle_dir = svc.generate("churn", "retention", "a@co.com", _interview(), tmp_path)
        doc = yaml.safe_load((bundle_dir / "databricks.yml").read_text())

        assert doc["bundle"]["name"] == "churn"
        assert doc["targets"]["dev"]["variables"]["catalog"] == "retention_churn_dev"
        assert doc["targets"]["prod"]["variables"]["catalog"] == "retention_churn_prod"
        assert doc["targets"]["prod"]["mode"] == "production"
        assert doc["targets"]["dev"]["workspace"]["host"] == cfg.databricks_host

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
        assert ep["ai_gateway"]["inference_table_config"]["schema_name"] == "monitoring"
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
