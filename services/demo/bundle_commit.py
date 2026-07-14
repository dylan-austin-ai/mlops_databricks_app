"""DemoBundleCommitService — same commit_step_files(...) signature as
BundleCommitService, but never touches GitHub: fabricates a per-file "ok"
result and queues one popup summarizing what would have been pushed.
"""

from __future__ import annotations

from typing import Any

from services.bundle_commit_service import STEP_CANDIDATE_FILES


class DemoBundleCommitService:
    def __init__(self, config: Any = None, state: Any = None) -> None:
        pass

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
        from components.demo import queue_action

        candidates = STEP_CANDIDATE_FILES.get(step_num, [])
        if not candidates:
            return []
        queue_action(
            "Bundle Files",
            f"Would push {len(candidates)} file(s) to `{repo_full_name}`: " + ", ".join(candidates),
        )
        return [{"path": p, "status": "ok", "detail": "(demo) would commit"} for p in candidates]
