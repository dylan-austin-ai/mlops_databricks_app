"""Tests for BundleCommitService — progressive per-step file commits and the
changed-assumptions drift guard (owner request 2026-07-13). The critical
property under test: a file the DS has hand-edited since it was last
auto-generated must NEVER be silently overwritten.
"""

from __future__ import annotations

from config import AppConfig
from services.bundle_commit_service import BundleCommitService, _sha256


class FakeStateService:
    def __init__(self):
        self.actions: dict[tuple[str, str], dict] = {}

    def get_last_infrastructure_action(self, project_id, action_name):
        return self.actions.get((project_id, action_name))

    def record_infrastructure_action(
        self, project_id, action_name, status, detail="", resource_id="", content_hash=None
    ):
        self.actions[(project_id, action_name)] = {
            "status": status,
            "detail": detail,
            "resource_id": resource_id,
            "content_hash": content_hash,
        }


class FakeContentFile:
    def __init__(self, content: str, sha: str = "sha-abc"):
        self.decoded_content = content.encode()
        self.sha = sha


class FakeRepo:
    def __init__(self, files: dict[str, str] | None = None):
        self.files = dict(files or {})
        self.create_calls: list[tuple] = []
        self.update_calls: list[tuple] = []

    def get_contents(self, path):
        from github import GithubException

        if path not in self.files:
            raise GithubException(404, {"message": "Not Found"}, {})
        return FakeContentFile(self.files[path])

    def create_file(self, path, message, content, branch):
        self.files[path] = content
        self.create_calls.append((path, content))

    def update_file(self, path, message, content, sha, branch):
        self.files[path] = content
        self.update_calls.append((path, content))


def _cfg() -> AppConfig:
    return AppConfig(
        databricks_host="https://test.cloud.databricks.com",
        databricks_token="dapi-test",
        warehouse_id="wh123",
        github_token="ghp-test",
    )


def _svc_with_repo(repo: FakeRepo, monkeypatch) -> BundleCommitService:
    state = FakeStateService()
    svc = BundleCommitService(_cfg(), state=state)
    monkeypatch.setattr(svc, "_github_repo", lambda repo_full_name: repo)
    return svc


class TestCommitFile:
    def test_creates_new_file_when_absent(self, monkeypatch):
        repo = FakeRepo(files={})
        svc = _svc_with_repo(repo, monkeypatch)

        result = svc.commit_file("proj-1", "org/repo", "src/train.py", "print('v1')", "owner@example.com")

        assert result["status"] == "ok"
        assert repo.files["src/train.py"] == "print('v1')"
        assert repo.create_calls and not repo.update_calls

    def test_updates_existing_untouched_file(self, monkeypatch):
        repo = FakeRepo(files={"src/train.py": "print('v1')"})
        svc = _svc_with_repo(repo, monkeypatch)
        # Simulate: v1 was the last thing WE generated (hash recorded)
        svc._state.record_infrastructure_action(
            "proj-1", "file_commit:src/train.py", "ok", content_hash=_sha256("print('v1')")
        )

        result = svc.commit_file("proj-1", "org/repo", "src/train.py", "print('v2')", "owner@example.com")

        assert result["status"] == "ok"
        assert repo.files["src/train.py"] == "print('v2')"
        assert repo.update_calls

    def test_unchanged_content_is_a_noop(self, monkeypatch):
        repo = FakeRepo(files={"src/train.py": "print('v1')"})
        svc = _svc_with_repo(repo, monkeypatch)

        result = svc.commit_file("proj-1", "org/repo", "src/train.py", "print('v1')", "owner@example.com")

        assert result["status"] == "unchanged"
        assert not repo.create_calls and not repo.update_calls

    def test_drift_guard_blocks_overwrite_of_hand_edited_file(self, monkeypatch):
        """The core safety property: DS edited the file after we generated
        it (repo content hash != what we last recorded) -- must not clobber."""
        repo = FakeRepo(files={"src/train.py": "print('DS_EDITED_THIS')"})
        svc = _svc_with_repo(repo, monkeypatch)
        svc._state.record_infrastructure_action(
            "proj-1",
            "file_commit:src/train.py",
            "ok",
            content_hash=_sha256("print('v1')"),  # what WE generated
        )

        result = svc.commit_file(
            "proj-1", "org/repo", "src/train.py", "print('v2 -- new answers')", "owner@example.com"
        )

        assert result["status"] == "blocked_drift"
        assert repo.files["src/train.py"] == "print('DS_EDITED_THIS')"  # untouched
        assert not repo.create_calls and not repo.update_calls

    def test_force_overrides_drift_guard(self, monkeypatch):
        repo = FakeRepo(files={"src/train.py": "print('DS_EDITED_THIS')"})
        svc = _svc_with_repo(repo, monkeypatch)
        svc._state.record_infrastructure_action(
            "proj-1", "file_commit:src/train.py", "ok", content_hash=_sha256("print('v1')")
        )

        result = svc.commit_file("proj-1", "org/repo", "src/train.py", "print('v2')", "owner@example.com", force=True)

        assert result["status"] == "ok"
        assert repo.files["src/train.py"] == "print('v2')"

    def test_first_ever_commit_has_no_prior_hash_so_no_drift_check(self, monkeypatch):
        """A file that already exists in the repo (e.g. from Step 1's
        initial scaffold) but was never tracked via file_commit: yet --
        first progressive commit should proceed, not treat it as drift."""
        repo = FakeRepo(files={"src/train.py": "raise NotImplementedError()"})
        svc = _svc_with_repo(repo, monkeypatch)
        # no prior file_commit: action recorded

        result = svc.commit_file("proj-1", "org/repo", "src/train.py", "print('real code')", "owner@example.com")

        assert result["status"] == "ok"
        assert repo.files["src/train.py"] == "print('real code')"


class TestCommitStepFiles:
    def test_noop_without_github_token(self):
        state = FakeStateService()
        cfg = AppConfig(
            databricks_host="https://test.cloud.databricks.com",
            databricks_token="dapi-test",
            warehouse_id="wh123",
            github_token="",
        )
        svc = BundleCommitService(cfg, state=state)

        results = svc.commit_step_files("proj-1", "org/repo", 2, "proj", "team", "owner@example.com", {})

        assert results == []

    def test_noop_for_step_with_no_candidate_files(self, monkeypatch):
        state = FakeStateService()
        svc = BundleCommitService(_cfg(), state=state)

        results = svc.commit_step_files("proj-1", "org/repo", 1, "proj", "team", "owner@example.com", {})

        assert results == []  # step 1 handled by ProjectProvisioningService, not this


class TestCheckStaleFiles:
    """Owner rule 2026-07-13, after live-discovering a stale src/batch_score.py
    left behind when inference_type changed from the Step-1 default (batch)
    to real_time: the app must NEVER delete repo files itself -- only flag
    them, persistently, until a human removes them."""

    def test_flags_file_present_in_repo_but_absent_from_render(self, monkeypatch, tmp_path):
        repo = FakeRepo(files={"src/batch_score.py": "raise NotImplementedError()"})
        svc = _svc_with_repo(repo, monkeypatch)
        # bundle_dir has no batch_score.py -- current render is real_time, not batch

        changed = svc.check_stale_files("proj-1", "org/repo", tmp_path)

        assert changed == [
            {
                "path": "src/batch_score.py",
                "status": "pending_deletion",
                "detail": changed[0]["detail"],
            }
        ]
        flag = svc._state.get_last_infrastructure_action("proj-1", "file_stale:src/batch_score.py")
        assert flag["status"] == "pending_deletion"

    def test_never_calls_delete_on_the_repo(self, monkeypatch, tmp_path):
        repo = FakeRepo(files={"src/batch_score.py": "raise NotImplementedError()"})
        repo.delete_file = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must never delete"))
        svc = _svc_with_repo(repo, monkeypatch)

        svc.check_stale_files("proj-1", "org/repo", tmp_path)

        assert repo.files["src/batch_score.py"] == "raise NotImplementedError()"  # untouched, still there

    def test_does_not_reflag_an_already_pending_file(self, monkeypatch, tmp_path):
        """No duplicate/noisy activity-log entries on repeated checks while
        still stale."""
        repo = FakeRepo(files={"src/batch_score.py": "x"})
        svc = _svc_with_repo(repo, monkeypatch)
        svc.check_stale_files("proj-1", "org/repo", tmp_path)  # first flag

        changed = svc.check_stale_files("proj-1", "org/repo", tmp_path)  # second check, still stale

        assert changed == []  # nothing NEW happened

    def test_clears_flag_when_file_becomes_relevant_again(self, monkeypatch, tmp_path):
        repo = FakeRepo(files={"src/batch_score.py": "x"})
        svc = _svc_with_repo(repo, monkeypatch)
        svc.check_stale_files("proj-1", "org/repo", tmp_path)  # flagged stale

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "batch_score.py").write_text("relevant again")
        changed = svc.check_stale_files("proj-1", "org/repo", tmp_path)

        assert changed == [{"path": "src/batch_score.py", "status": "resolved", "detail": "applicable again"}]

    def test_clears_flag_when_human_deletes_the_file(self, monkeypatch, tmp_path):
        repo = FakeRepo(files={"src/batch_score.py": "x"})
        svc = _svc_with_repo(repo, monkeypatch)
        svc.check_stale_files("proj-1", "org/repo", tmp_path)  # flagged stale

        del repo.files["src/batch_score.py"]  # DS deleted it themselves, as instructed
        changed = svc.check_stale_files("proj-1", "org/repo", tmp_path)

        assert changed == [{"path": "src/batch_score.py", "status": "resolved", "detail": "removed by DS"}]

    def test_no_flag_when_file_was_never_in_repo(self, monkeypatch, tmp_path):
        repo = FakeRepo(files={})  # nothing conditional ever got created
        svc = _svc_with_repo(repo, monkeypatch)

        changed = svc.check_stale_files("proj-1", "org/repo", tmp_path)

        assert changed == []
