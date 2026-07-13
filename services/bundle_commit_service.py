"""BundleCommitService — progressive per-step file commits + changed-
assumptions drift guard (owner request 2026-07-13).

Each wizard step, once answered, re-renders the whole bundle to a local temp
dir (cheap — BundleService.generate() is pure Jinja rendering) and pushes
only the files that step's own answers can affect. This lets a DS's
train.py/evaluate.py edits show up in GitHub incrementally instead of one
big commit at the very end.

Drift guard: before overwriting a file that was previously auto-generated,
compare the file's CURRENT content in the repo against the hash recorded
when it was last auto-generated (project_infrastructure_actions,
action_name=f"file_commit:{path}"). If they match, the DS hasn't touched it
— safe to regenerate. If they differ, the DS has hand-edited it — refuse to
silently clobber; the caller gets a "blocked_drift" status per file and can
surface it (a full diff-preview UI is a documented fast-follow, not built
here — see PROJECT_STATUS.md).
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from config import AppConfig, get_config
from services.state_service import StateService

# Which rendered files each wizard step's answers can affect. Only files
# that actually exist in a given render (accelerants/streaming/etc. are
# conditionally rendered by BundleService) are pushed — this list is a
# candidate set, not a guarantee.
STEP_CANDIDATE_FILES: dict[int, list[str]] = {
    2: [
        "resources/model_serving.yml",
        "resources/jobs.yml",
        "requirements.txt",
        "src/automl_baseline.py",
        "src/hyperparameter_search.py",
        "src/train.py",
    ],
    3: ["src/train.py"],
    4: ["src/train.py", "src/evaluate.py"],
    5: ["resources/jobs.yml"],
    6: ["src/evaluate.py"],
}

# Files bundle_service.py renders conditionally (inference_type,
# accelerants). Owner request 2026-07-13, discovered live: if a DS answers
# Step 2 with inference_type=batch (or leaves it at the default before
# reaching Step 2), then later changes it to real_time, a stale
# src/batch_score.py is left behind — nothing ever removed it. Owner's
# explicit rule after that finding: "The app should never delete any files
# within a repo once they're written" — so this never deletes; it persists
# a visible pending_deletion flag until a human removes the file themselves,
# same posture as the GitHub-repo-deletion reminder.
CONDITIONAL_FILES = [
    "resources/model_serving.yml",
    "src/batch_score.py",
    "src/stream_score.py",
    "src/automl_baseline.py",
    "src/hyperparameter_search.py",
]


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class BundleCommitService:
    def __init__(self, config: AppConfig | None = None, state: StateService | None = None) -> None:
        self._cfg = config or get_config()
        self._state = state or StateService(self._cfg)

    def _github_repo(self, repo_full_name: str) -> Any:
        from github import Github

        return Github(self._cfg.github_token).get_repo(repo_full_name)

    def _current_repo_file(self, repo: Any, path: str) -> tuple[str | None, Any]:
        """Returns (content_hash, ContentFile-or-None). None hash = file
        doesn't exist in the repo yet."""
        from github import GithubException

        try:
            content_file = repo.get_contents(path)
        except GithubException as exc:
            if exc.status == 404:
                return None, None
            raise
        return _sha256(content_file.decoded_content.decode()), content_file

    def commit_file(
        self,
        project_id: str,
        repo_full_name: str,
        path: str,
        new_content: str,
        actor_email: str,
        force: bool = False,
    ) -> dict[str, str]:
        """Push one file if it's safe to. Returns {"path", "status", "detail"}
        with status one of: ok | unchanged | blocked_drift | failed."""
        action_name = f"file_commit:{path}"
        try:
            repo = self._github_repo(repo_full_name)
            current_hash, content_file = self._current_repo_file(repo, path)
            new_hash = _sha256(new_content)
            last = self._state.get_last_infrastructure_action(project_id, action_name)
            last_hash = last["content_hash"] if last else None

            if current_hash is not None and last_hash is not None and current_hash != last_hash and not force:
                self._state.record_infrastructure_action(
                    project_id,
                    action_name,
                    "blocked_drift",
                    detail=f"repo content (hash {current_hash[:8]}) differs from last auto-generated "
                    f"version (hash {last_hash[:8]}) — DS has likely edited this file",
                    content_hash=current_hash,
                )
                return {"path": path, "status": "blocked_drift", "detail": "file has been hand-edited since"}

            if current_hash == new_hash:
                return {"path": path, "status": "unchanged", "detail": ""}

            if content_file is None:
                repo.create_file(path, f"chore: generate {path}", new_content, branch="main")
            else:
                repo.update_file(path, f"chore: update {path}", new_content, content_file.sha, branch="main")

            self._state.record_infrastructure_action(
                project_id, action_name, "ok", detail="committed", content_hash=new_hash
            )
            return {"path": path, "status": "ok", "detail": "committed"}

        except Exception as exc:
            self._state.record_infrastructure_action(project_id, action_name, "failed", detail=str(exc))
            return {"path": path, "status": "failed", "detail": str(exc)}

    def commit_step_files(
        self,
        project_id: str,
        repo_full_name: str,
        step_num: int,
        project_name: str,
        team_name: str,
        owner_email: str,
        interview_responses: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Re-renders the whole bundle (cheap, local) and pushes only the
        files STEP_CANDIDATE_FILES[step_num] that actually exist in this
        render. No-ops (returns []) if GITHUB_TOKEN isn't set, this step has
        no candidate files, or the repo isn't known yet."""
        candidates = STEP_CANDIDATE_FILES.get(step_num, [])
        if not candidates or not self._cfg.github_token or not repo_full_name:
            return []

        from services.bundle_service import BundleService

        budget_action = self._state.get_last_infrastructure_action(project_id, "budget_policy")
        budget_policy_id = budget_action["resource_id"] if budget_action and budget_action["status"] == "ok" else ""

        tmp = Path(tempfile.mkdtemp(prefix="mlops_step_commit_"))
        bundle_dir = BundleService(self._cfg).generate(
            project_name=project_name,
            team_name=team_name,
            owner_email=owner_email,
            interview_responses=interview_responses,
            output_dir=tmp,
            budget_policy_id=budget_policy_id,
        )

        results: list[dict[str, str]] = []
        for rel_path in candidates:
            local_path = bundle_dir / rel_path
            if not local_path.exists():
                continue  # conditionally-rendered file, not applicable this run
            results.append(self.commit_file(project_id, repo_full_name, rel_path, local_path.read_text(), owner_email))

        results.extend(self.check_stale_files(project_id, repo_full_name, bundle_dir))
        return results

    def check_stale_files(self, project_id: str, repo_full_name: str, bundle_dir: Path) -> list[dict[str, str]]:
        """Flags (never deletes — owner rule 2026-07-13) any CONDITIONAL_FILES
        entry that exists in the repo but is no longer produced by the
        current render (e.g. src/batch_score.py left over after
        inference_type changed away from batch). Also clears a prior flag if
        the file became relevant again, or if a human has since deleted it
        themselves. Returns only the entries whose status changed this call."""
        try:
            repo = self._github_repo(repo_full_name)
        except Exception:
            return []

        changed: list[dict[str, str]] = []
        for rel_path in CONDITIONAL_FILES:
            action_name = f"file_stale:{rel_path}"
            exists_in_render = (bundle_dir / rel_path).exists()
            exists_in_repo, _ = self._current_repo_file(repo, rel_path)
            exists_in_repo = exists_in_repo is not None
            last = self._state.get_last_infrastructure_action(project_id, action_name)
            currently_flagged = bool(last and last["status"] == "pending_deletion")

            if exists_in_repo and not exists_in_render and not currently_flagged:
                detail = (
                    f"{rel_path} no longer applies given your current answers, but is still in the repo. "
                    "Delete or archive it yourself — the app never removes files from a repo it didn't just "
                    "add moments ago."
                )
                self._state.record_infrastructure_action(project_id, action_name, "pending_deletion", detail=detail)
                changed.append({"path": rel_path, "status": "pending_deletion", "detail": detail})
            elif exists_in_render and currently_flagged:
                self._state.record_infrastructure_action(
                    project_id, action_name, "resolved", detail=f"{rel_path} is applicable again"
                )
                changed.append({"path": rel_path, "status": "resolved", "detail": "applicable again"})
            elif not exists_in_repo and currently_flagged:
                self._state.record_infrastructure_action(
                    project_id, action_name, "resolved", detail=f"{rel_path} was removed — thank you"
                )
                changed.append({"path": rel_path, "status": "resolved", "detail": "removed by DS"})

        return changed
