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
        assert r.budget_policy_id == ""

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

        cleanup_script = path / "scripts" / "cleanup_qa_resources.py"
        assert cleanup_script.is_file() and os.access(cleanup_script, os.X_OK)
        cleanup_text = cleanup_script.read_text()
        compile(cleanup_text, "cleanup_qa_resources.py", "exec")
        assert "PROJECT_NAME = 'churn_model'" in cleanup_text
        assert 'KEEP_ENDPOINT_NAMES = {f"{PROJECT_NAME}-dev"' in cleanup_text

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


class FakeBudgetPolicyHandle:
    def __init__(self, policy_id: str, already_existed: bool = False):
        self.policy_id = policy_id
        self.already_existed = already_existed


class FakeBudgetPolicy:
    """Test double for BudgetPolicyService — every method is independently
    swappable to raise, so each resolution branch in
    ProjectInfrastructureGenerator._resolve_budget_policy can be exercised."""

    def __init__(
        self,
        ensure_policy_result=None,
        ensure_policy_raises=None,
        ensure_default_result=None,
        ensure_default_raises=None,
    ):
        self._ensure_policy_result = ensure_policy_result
        self._ensure_policy_raises = ensure_policy_raises
        self._ensure_default_result = ensure_default_result
        self._ensure_default_raises = ensure_default_raises
        self.ensure_policy_calls: list[tuple] = []

    def ensure_policy(self, name, custom_tags):
        self.ensure_policy_calls.append((name, custom_tags))
        if self._ensure_policy_raises:
            raise self._ensure_policy_raises
        return self._ensure_policy_result

    def ensure_default_policy(self):
        if self._ensure_default_raises:
            raise self._ensure_default_raises
        return self._ensure_default_result


class TestResolveBudgetPolicy:
    """Owner request 2026-07-12 — per-project cost attribution, never blocks
    project creation regardless of which layer fails."""

    def test_wizard_override_used_directly_no_service_call(self, cfg):
        gen = ProjectInfrastructureGenerator(cfg, budget_policy_service=FakeBudgetPolicy())
        result = GenerationResult(project_name="churn")

        policy_id = gen._resolve_budget_policy("churn", "retention_team", {"budget_policy_id": "preset-999"}, result)

        assert policy_id == "preset-999"
        assert result.budget_policy_id == "preset-999"
        assert result.steps[0]["status"] == "ok"
        assert "wizard override" in result.steps[0]["detail"]

    def test_creates_new_per_project_policy(self, cfg):
        from services.budget_policy_service import BudgetPolicyUnavailable  # noqa: F401 (documents the other branch)

        fake = FakeBudgetPolicy(ensure_policy_result=FakeBudgetPolicyHandle("p-new", already_existed=False))
        gen = ProjectInfrastructureGenerator(cfg, budget_policy_service=fake)
        result = GenerationResult(project_name="churn")

        policy_id = gen._resolve_budget_policy("churn", "retention_team", {}, result)

        assert policy_id == "p-new"
        assert fake.ensure_policy_calls[0][0] == "mlops-churn"
        assert fake.ensure_policy_calls[0][1] == {
            "project_id": "churn",
            "team": "retention_team",
            "managed_by": "mlops_control_plane",
        }
        assert "created" in result.steps[0]["detail"]

    def test_reuses_existing_per_project_policy(self, cfg):
        fake = FakeBudgetPolicy(ensure_policy_result=FakeBudgetPolicyHandle("p-existing", already_existed=True))
        gen = ProjectInfrastructureGenerator(cfg, budget_policy_service=fake)
        result = GenerationResult(project_name="churn")

        policy_id = gen._resolve_budget_policy("churn", "retention_team", {}, result)

        assert policy_id == "p-existing"
        assert "reused" in result.steps[0]["detail"]

    def test_unavailable_credentials_skips_cleanly(self, cfg):
        from services.budget_policy_service import BudgetPolicyUnavailable

        fake = FakeBudgetPolicy(ensure_policy_raises=BudgetPolicyUnavailable("account creds not set"))
        gen = ProjectInfrastructureGenerator(cfg, budget_policy_service=fake)
        result = GenerationResult(project_name="churn")

        policy_id = gen._resolve_budget_policy("churn", "retention_team", {}, result)

        assert policy_id == ""
        assert result.budget_policy_id == ""
        assert result.steps[0]["status"] == "skipped"

    def test_per_project_failure_falls_back_to_default(self, cfg):
        fake = FakeBudgetPolicy(
            ensure_policy_raises=RuntimeError("quota exceeded"),
            ensure_default_result=FakeBudgetPolicyHandle("p-default"),
        )
        gen = ProjectInfrastructureGenerator(cfg, budget_policy_service=fake)
        result = GenerationResult(project_name="churn")

        policy_id = gen._resolve_budget_policy("churn", "retention_team", {}, result)

        assert policy_id == "p-default"
        assert result.steps[0]["status"] == "ok"
        assert "fell back to control-plane default" in result.steps[0]["detail"]

    def test_per_project_and_default_both_fail_skips_cleanly(self, cfg):
        fake = FakeBudgetPolicy(
            ensure_policy_raises=RuntimeError("quota exceeded"),
            ensure_default_raises=RuntimeError("default also broken"),
        )
        gen = ProjectInfrastructureGenerator(cfg, budget_policy_service=fake)
        result = GenerationResult(project_name="churn")

        policy_id = gen._resolve_budget_policy("churn", "retention_team", {}, result)

        assert policy_id == ""
        assert result.steps[0]["status"] == "skipped"
        assert "quota exceeded" in result.steps[0]["detail"]
        assert "default also broken" in result.steps[0]["detail"]


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


class FakeContentEntry:
    def __init__(self, name: str):
        self.name = name


class FakeExistingRepo:
    def __init__(self, full_name: str, contents: list[str] | None):
        """contents=None simulates a truly empty repo (GithubException 404
        on get_contents); contents=[] or a name list simulates real entries."""
        self.name = full_name.split("/")[-1]
        self.clone_url = f"https://github.com/{full_name}.git"
        self.html_url = f"https://github.com/{full_name}"
        self._contents = contents

    def get_contents(self, path: str):
        from github import GithubException

        if self._contents is None:
            raise GithubException(404, {"message": "This repository is empty."}, {})
        return [FakeContentEntry(n) for n in self._contents]

    def get_branch(self, _name):
        from types import SimpleNamespace

        return SimpleNamespace(edit_protection=lambda **kwargs: None)


class FakeGithubClientWithGetRepo(FakeGithubClient):
    """Extends the base fake with gh.get_repo(full_name) for the
    existing-repo-linking path — separate from FakeOwner.get_repo(name),
    which is the new-repo-already-exists fallback."""

    repos_by_full_name: dict[str, FakeExistingRepo] = {}

    def get_repo(self, full_name: str):
        return self.repos_by_full_name[full_name]


def _cfg_with_github_and_ignore_patterns(patterns: list[str] | None = None) -> AppConfig:
    kwargs = dict(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
        github_token="ghp-test",
        github_org="",
    )
    if patterns is not None:
        kwargs["empty_repo_ignore_patterns"] = patterns
    return AppConfig(**kwargs)


class TestExistingRepoLinking:
    """Owner request 2026-07-13: Step 1 may link an existing repo instead of
    creating a new one. The app must verify it's empty (modulo configured
    ignore patterns) before ever pushing into it."""

    def test_rejects_unrecognized_url(self, monkeypatch, tmp_path):
        monkeypatch.setattr("github.Github", FakeGithubClient)
        gen = ProjectInfrastructureGenerator(_cfg_with_github_and_ignore_patterns())
        result = GenerationResult(project_name="churn_model")

        gen._create_github_repo(
            "churn_model",
            "owner@example.com",
            tmp_path,
            _responses(existing_repo_url="git@github.com:org/repo.git"),
            result,
        )

        assert result.steps[0]["status"] == "failed"
        assert "recognized" in result.steps[0]["detail"]

    def test_pushes_into_truly_empty_existing_repo(self, monkeypatch, tmp_path):
        monkeypatch.setattr("github.Github", FakeGithubClientWithGetRepo)
        monkeypatch.setattr("services.generator_service.subprocess.run", lambda *a, **k: None)
        FakeGithubClientWithGetRepo.repos_by_full_name = {
            "my-org/churn-model": FakeExistingRepo("my-org/churn-model", contents=None)
        }
        gen = ProjectInfrastructureGenerator(_cfg_with_github_and_ignore_patterns())
        result = GenerationResult(project_name="churn_model")

        gen._create_github_repo(
            "churn_model",
            "owner@example.com",
            tmp_path,
            _responses(existing_repo_url="https://github.com/my-org/churn-model"),
            result,
        )

        assert result.steps[0]["status"] == "ok"
        assert result.github_repo_url == "https://github.com/my-org/churn-model"

    def test_pushes_when_only_ignored_files_present(self, monkeypatch, tmp_path):
        monkeypatch.setattr("github.Github", FakeGithubClientWithGetRepo)
        monkeypatch.setattr("services.generator_service.subprocess.run", lambda *a, **k: None)
        FakeGithubClientWithGetRepo.repos_by_full_name = {
            "my-org/churn-model": FakeExistingRepo(
                "my-org/churn-model", contents=["README.md", ".gitignore", "LICENSE", ".github"]
            )
        }
        gen = ProjectInfrastructureGenerator(_cfg_with_github_and_ignore_patterns())
        result = GenerationResult(project_name="churn_model")

        gen._create_github_repo(
            "churn_model",
            "owner@example.com",
            tmp_path,
            _responses(existing_repo_url="https://github.com/my-org/churn-model"),
            result,
        )

        assert result.steps[0]["status"] == "ok"

    def test_blocks_push_when_real_content_present(self, monkeypatch, tmp_path):
        monkeypatch.setattr("github.Github", FakeGithubClientWithGetRepo)
        push_calls = []
        monkeypatch.setattr("services.generator_service.subprocess.run", lambda *a, **k: push_calls.append(a) or None)
        FakeGithubClientWithGetRepo.repos_by_full_name = {
            "my-org/churn-model": FakeExistingRepo("my-org/churn-model", contents=["README.md", "src"])
        }
        gen = ProjectInfrastructureGenerator(_cfg_with_github_and_ignore_patterns())
        result = GenerationResult(project_name="churn_model")

        gen._create_github_repo(
            "churn_model",
            "owner@example.com",
            tmp_path,
            _responses(existing_repo_url="https://github.com/my-org/churn-model"),
            result,
        )

        assert result.steps[0]["status"] == "failed"
        assert "not empty" in result.steps[0]["detail"]
        assert "src" in result.steps[0]["detail"]
        assert push_calls == []  # never attempted a push into real content

    def test_ignore_patterns_are_configurable(self, monkeypatch, tmp_path):
        """A company-specific automation-stamped file (e.g. SECURITY.md) can
        be added to the ignore list via app config."""
        monkeypatch.setattr("github.Github", FakeGithubClientWithGetRepo)
        monkeypatch.setattr("services.generator_service.subprocess.run", lambda *a, **k: None)
        FakeGithubClientWithGetRepo.repos_by_full_name = {
            "my-org/churn-model": FakeExistingRepo("my-org/churn-model", contents=["SECURITY.md"])
        }
        cfg = _cfg_with_github_and_ignore_patterns(["SECURITY.md"])
        gen = ProjectInfrastructureGenerator(cfg)
        result = GenerationResult(project_name="churn_model")

        gen._create_github_repo(
            "churn_model",
            "owner@example.com",
            tmp_path,
            _responses(existing_repo_url="https://github.com/my-org/churn-model"),
            result,
        )

        assert result.steps[0]["status"] == "ok"

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


class FakeSchemasAPI:
    def __init__(self):
        self.create_calls: list[dict] = []

    def create(self, catalog_name, name):
        self.create_calls.append({"catalog_name": catalog_name, "name": name})


class FakeVolumesAPI:
    def __init__(self):
        self.create_calls: list[dict] = []

    def create(self, catalog_name, schema_name, name, volume_type):
        self.create_calls.append(
            {"catalog_name": catalog_name, "schema_name": schema_name, "name": name, "volume_type": volume_type}
        )


class FakeWorkspaceClient:
    last_instance: FakeWorkspaceClient | None = None

    def __init__(self, host=None, token=None, **kwargs):
        self.schemas = FakeSchemasAPI()
        self.volumes = FakeVolumesAPI()
        FakeWorkspaceClient.last_instance = self


def _cfg_with_nonprod_catalog() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
        projects_catalog="mlops",
        projects_catalog_dev="mlops_non_prod",
        projects_catalog_staging="mlops_non_prod",
        projects_catalog_prod="mlops",
    )


class TestUcSchemasAndVolumes:
    """Owner request 2026-07-13: dev/staging resolve into the configured
    non-prod catalog via projects_catalog_for(); prod stays in the prod
    catalog. Volumes follow the resolved non-prod schemas."""

    def test_dev_and_staging_use_nonprod_catalog(self, monkeypatch):
        monkeypatch.setattr("databricks.sdk.WorkspaceClient", FakeWorkspaceClient)
        gen = ProjectInfrastructureGenerator(_cfg_with_nonprod_catalog())
        result = GenerationResult(project_name="churn_model")

        gen._create_uc_schemas("churn_model", result)

        assert result.uc_schema_dev == "mlops_non_prod.churn_model_dev"
        assert result.uc_schema_staging == "mlops_non_prod.churn_model_staging"
        assert result.uc_schema_prod == "mlops.churn_model_prod"
        created = {c["catalog_name"] for c in FakeWorkspaceClient.last_instance.schemas.create_calls}
        assert created == {"mlops_non_prod", "mlops"}

    def test_no_nonprod_catalog_configured_falls_back_to_single_catalog(self, monkeypatch):
        """Backward compat: unconfigured orgs keep today's single-catalog
        behavior, disambiguated by the _dev/_staging/_prod suffix."""
        monkeypatch.setattr("databricks.sdk.WorkspaceClient", FakeWorkspaceClient)
        cfg = AppConfig(
            databricks_host="https://test.cloud.databricks.com",
            databricks_token="dapi-test",
            warehouse_id="wh123",
            projects_catalog="mlops",
        )
        gen = ProjectInfrastructureGenerator(cfg)
        result = GenerationResult(project_name="churn_model")

        gen._create_uc_schemas("churn_model", result)

        assert result.uc_schema_dev == "mlops.churn_model_dev"
        assert result.uc_schema_staging == "mlops.churn_model_staging"
        assert result.uc_schema_prod == "mlops.churn_model_prod"

    def test_volumes_created_for_dev_and_staging_only(self, monkeypatch):
        monkeypatch.setattr("databricks.sdk.WorkspaceClient", FakeWorkspaceClient)
        gen = ProjectInfrastructureGenerator(_cfg_with_nonprod_catalog())
        result = GenerationResult(project_name="churn_model")
        gen._create_uc_schemas("churn_model", result)

        gen._create_uc_volumes(result)

        assert result.uc_volume_dev == "mlops_non_prod.churn_model_dev.artifacts"
        assert result.uc_volume_staging == "mlops_non_prod.churn_model_staging.artifacts"
        calls = FakeWorkspaceClient.last_instance.volumes.create_calls
        assert len(calls) == 2
        assert {c["schema_name"] for c in calls} == {"churn_model_dev", "churn_model_staging"}
        assert all(c["name"] == "artifacts" for c in calls)

    def test_volumes_skipped_when_no_schemas_set(self, monkeypatch):
        monkeypatch.setattr("databricks.sdk.WorkspaceClient", FakeWorkspaceClient)
        gen = ProjectInfrastructureGenerator(_cfg_with_nonprod_catalog())
        result = GenerationResult(project_name="churn_model")  # schemas never created

        gen._create_uc_volumes(result)

        volumes_step = next(s for s in result.steps if s["name"] == "uc_volumes")
        assert volumes_step["status"] == "skipped"
