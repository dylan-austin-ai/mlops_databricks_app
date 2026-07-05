"""Tests for generator_service — GenerationResult and step tracking."""

from __future__ import annotations

from services.generator_service import GenerationResult


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
