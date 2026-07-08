"""Tests for generator_service — GenerationResult, step tracking, and the bundle scaffold."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from config import AppConfig
from services.generator_service import GenerationResult, ProjectInfrastructureGenerator


class TestGenerationResult:
    def test_initial_state(self):
        r = GenerationResult(project_name="test_model")
        assert r.project_name == "test_model"
        assert r.github_repo_url == ""
        assert r.steps == []
        assert r.succeeded is False
        assert r.all_ok is False

    def test_add_ok_step(self):
        r = GenerationResult(project_name="test_model")
        r.add_step("scaffold_code", "ok", "/tmp/test_model")
        assert len(r.steps) == 1
        assert r.steps[0]["name"] == "scaffold_code"
        assert r.steps[0]["status"] == "ok"
        assert r.steps[0]["detail"] == "/tmp/test_model"
        assert r.succeeded is True

    def test_add_failed_step(self):
        r = GenerationResult(project_name="test_model")
        r.add_step("github_repo", "failed", "rate limit exceeded")
        assert r.succeeded is False
        assert r.all_ok is False

    def test_add_skipped_step(self):
        r = GenerationResult(project_name="test_model")
        r.add_step("github_repo", "skipped", "GITHUB_TOKEN not set")
        assert r.steps[0]["status"] == "skipped"
        assert r.succeeded is False

    def test_all_ok_requires_all_steps_ok(self):
        r = GenerationResult(project_name="test_model")
        r.add_step("scaffold_code", "ok")
        r.add_step("uc_schemas", "ok")
        assert r.all_ok is True

        r.add_step("github_repo", "failed", "network error")
        assert r.all_ok is False

    def test_succeeded_true_if_any_ok(self):
        r = GenerationResult(project_name="test_model")
        r.add_step("scaffold_code", "ok")
        r.add_step("github_repo", "failed", "no token")
        assert r.succeeded is True  # at least one succeeded

    def test_step_detail_defaults_empty(self):
        r = GenerationResult(project_name="test_model")
        r.add_step("mlflow_experiment", "ok")
        assert r.steps[0]["detail"] == ""

    def test_multiple_steps_ordering(self):
        r = GenerationResult(project_name="test_model")
        for name in ("scaffold_code", "github_repo", "uc_schemas", "mlflow_experiment", "secret_scope"):
            r.add_step(name, "ok")
        assert [s["name"] for s in r.steps] == [
            "scaffold_code",
            "github_repo",
            "uc_schemas",
            "mlflow_experiment",
            "secret_scope",
        ]

    def test_artifacts_default_empty(self):
        r = GenerationResult(project_name="p")
        assert r.github_repo_url == ""
        assert r.github_repo_name == ""
        assert r.mlflow_experiment_id == ""
        assert r.uc_schema_dev == ""
        assert r.uc_schema_staging == ""
        assert r.uc_schema_prod == ""
        assert r.secret_scope_name == ""

    def test_artifact_assignment(self):
        r = GenerationResult(project_name="p")
        r.github_repo_url = "https://github.com/org/p"
        r.uc_schema_dev = "mlops.p_dev"
        r.mlflow_experiment_id = "exp_123"
        assert r.github_repo_url == "https://github.com/org/p"
        assert r.uc_schema_dev == "mlops.p_dev"
        assert r.mlflow_experiment_id == "exp_123"


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
    )


def _responses(**overrides) -> dict:
    base = {
        "team_name": "retention_team",
        "inference_type": "batch",
        "batch_schedule": "0 2 * * *",
        "retraining_schedule": "0 3 * * 0",
        "legal_contact_email": "legal@example.com",
        "code_review_count": 2,
    }
    base.update(overrides)
    return base


def _scaffold(cfg: AppConfig, **overrides):
    gen = ProjectInfrastructureGenerator(cfg)
    result = GenerationResult(project_name="churn_model")
    path = gen._scaffold_code("churn_model", "owner@example.com", _responses(**overrides), result)
    return path, result


class TestScaffoldCode:
    """Scaffold cutover to Bundle Service (DECISIONS_NEEDED #4, 2026-07-07)."""

    def test_renders_bundle_scaffold(self, cfg):
        path, result = _scaffold(cfg)
        assert path is not None
        assert result.steps[0] == {"name": "scaffold_code", "status": "ok", "detail": str(path)}
        for rel in (
            "databricks.yml",
            "resources/schemas.yml",
            "resources/jobs.yml",
            "src/train.py",
            "src/batch_score.py",
        ):
            assert (path / rel).is_file(), f"missing {rel}"

    def test_realtime_scaffold_includes_serving(self, cfg):
        path, _ = _scaffold(cfg, inference_type="real_time", batch_schedule="")
        assert (path / "resources" / "model_serving.yml").is_file()
        assert not (path / "src" / "batch_score.py").exists()

    def test_streaming_scaffold_renders_continuous_scorer(self, cfg):
        path, result = _scaffold(
            cfg,
            inference_type="streaming",
            batch_schedule="",
            streaming_source_table="mlops.demo_streaming.events",
        )
        assert result.steps[0]["status"] == "ok"
        scorer = path / "src" / "stream_score.py"
        assert scorer.is_file()
        assert not (path / "src" / "batch_score.py").exists()
        assert not (path / "resources" / "model_serving.yml").exists()
        jobs_yml = (path / "resources" / "jobs.yml").read_text()
        assert "continuous:" in jobs_yml
        assert "mlops.demo_streaming.events" in jobs_yml

    def test_writes_mlops_platform_files(self, cfg):
        path, _ = _scaffold(cfg)
        manifest_hash = (path / ".mlops" / "manifest_hash.txt").read_text().strip()
        assert len(manifest_hash) == 64 and all(c in "0123456789abcdef" for c in manifest_hash)
        assert (path / ".mlops" / "approved_state.txt").read_text() == "INITIAL\n"
        record = json.loads((path / ".mlops" / "approval_record.json").read_text())
        assert record["project_name"] == "churn_model"
        assert record["manifest_hash"] == manifest_hash
        script = path / "scripts" / "check_change_scope.py"
        assert script.is_file() and os.access(script, os.X_OK)
        script_text = script.read_text()
        compile(script_text, "check_change_scope.py", "exec")  # generated script is valid Python
        assert "PROJECT_NAME = 'churn_model'" in script_text

    def test_git_repo_on_main_with_initial_commit(self, cfg):
        path, _ = _scaffold(cfg)

        def git(*args: str) -> str:
            proc = subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)
            return proc.stdout.strip()

        assert git("rev-parse", "--abbrev-ref", "HEAD") == "main"
        assert git("status", "--porcelain") == ""  # everything committed
        assert git("log", "--oneline").count("\n") == 0  # exactly one commit
        assert "databricks.yml" in git("ls-files")
        assert ".mlops/manifest_hash.txt" in git("ls-files")

    def test_failure_reports_failed_step(self, cfg):
        class ExplodingBundleService:
            def generate(self, **kwargs):
                raise RuntimeError("template render failed")

        gen = ProjectInfrastructureGenerator(cfg, bundle_service=ExplodingBundleService())
        result = GenerationResult(project_name="churn_model")
        path = gen._scaffold_code("churn_model", "owner@example.com", _responses(), result)
        assert path is None
        assert result.steps[0]["status"] == "failed"
        assert "template render failed" in result.steps[0]["detail"]


class FakeRepo:
    def __init__(self, name):
        self.name = name
        self.clone_url = f"https://github.com/owner/{name}.git"
        self.html_url = f"https://github.com/owner/{name}"

    def get_branch(self, _name):
        from types import SimpleNamespace

        return SimpleNamespace(edit_protection=lambda **kwargs: None)


class FakeOwner:
    def __init__(self):
        self.create_repo_calls: list[dict] = []

    def create_repo(self, **kwargs):
        self.create_repo_calls.append(kwargs)
        return FakeRepo(kwargs["name"])

    def get_repo(self, name):
        return FakeRepo(name)


class FakeGithubClient:
    last_instance: FakeGithubClient | None = None

    def __init__(self, token):
        self.token = token
        self.org_requested: str | None = None
        self.get_user_called = False
        FakeGithubClient.last_instance = self

    def get_organization(self, name):
        self.org_requested = name
        return FakeOwner()

    def get_user(self):
        self.get_user_called = True
        return FakeOwner()


def _cfg_with_github(github_org: str) -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
        github_token="ghp-test",
        github_org=github_org,
    )


class TestGithubRepoOwnerResolution:
    """GITHUB_ORG is optional — a personal GitHub account has no organization
    to resolve, so an unset org must create the repo under the authenticated
    user instead of erroring on get_organization()."""

    def test_uses_organization_when_github_org_set(self, monkeypatch, tmp_path):
        monkeypatch.setattr("github.Github", FakeGithubClient)
        monkeypatch.setattr("services.generator_service.subprocess.run", lambda *a, **k: None)
        gen = ProjectInfrastructureGenerator(_cfg_with_github("my-org"))
        result = GenerationResult(project_name="churn_model")

        gen._create_github_repo("churn_model", "owner@example.com", tmp_path, _responses(), result)

        assert result.steps[0]["status"] == "ok"
        client = FakeGithubClient.last_instance
        assert client.org_requested == "my-org"
        assert client.get_user_called is False

    def test_falls_back_to_authenticated_user_when_org_unset(self, monkeypatch, tmp_path):
        monkeypatch.setattr("github.Github", FakeGithubClient)
        monkeypatch.setattr("services.generator_service.subprocess.run", lambda *a, **k: None)
        gen = ProjectInfrastructureGenerator(_cfg_with_github(""))
        result = GenerationResult(project_name="churn_model")

        gen._create_github_repo("churn_model", "owner@example.com", tmp_path, _responses(), result)

        assert result.steps[0]["status"] == "ok"
        client = FakeGithubClient.last_instance
        assert client.get_user_called is True
        assert client.org_requested is None

    def test_generate_runs_github_step_without_org(self, monkeypatch, tmp_path):
        """generate()'s gate on the GitHub step no longer requires github_org."""
        monkeypatch.setattr("github.Github", FakeGithubClient)
        monkeypatch.setattr("services.generator_service.subprocess.run", lambda *a, **k: None)

        class StubGenerator(ProjectInfrastructureGenerator):
            def _scaffold_code(self, *a, **k):
                return tmp_path

            def _create_uc_schemas(self, *a, **k):
                pass

            def _create_mlflow_experiment(self, *a, **k):
                pass

            def _create_secret_scope(self, *a, **k):
                pass

        gen = StubGenerator(_cfg_with_github(""))
        result = gen.generate("churn_model", "owner@example.com", _responses())

        github_step = next(s for s in result.steps if s["name"] == "github_repo")
        assert github_step["status"] == "ok"
