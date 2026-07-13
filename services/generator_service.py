"""ProjectInfrastructureGenerator — the individual provisioning actions a
project can need, plus generate() which still runs all of them in one call
for callers that want the old all-at-once behavior (tests, backfills).

The main app no longer calls generate() directly (owner request 2026-07-13:
progressive per-step provisioning instead of one waterfall at the end — see
services/project_provisioning_service.py for the step-triggered
orchestration and idempotency tracking). generate() runs, in order:
  0. Resolve a budget policy for cost attribution (owner request 2026-07-12)
     — wizard override, else an idempotent per-project policy, else the
     control-plane default, else skipped entirely (needed before step 1,
     since the resolved id is rendered into the bundle)
  1. Render the Databricks Asset Bundle scaffold via BundleService (temp dir),
     add .mlops/ platform files, git-init with an initial commit
  2. Create GitHub repo and push the scaffold
  3. Create Databricks UC schemas (dev / staging / prod) and, for the
     non-prod ones, an `artifacts` Volume in each
  4. Create MLflow experiment

Databricks secret scope creation (_create_secret_scope) is NOT called from
generate() — traced every reference and found zero consumers (nothing reads
or writes a secret through it), so eager creation was speculative
infrastructure with nothing behind it. The method stays available for
whenever a real consumer needs one.

Each step is best-effort with its own status reported back to the caller.
A failed GitHub step does not block UC schema creation, etc.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import AppConfig, get_config


@dataclass
class GenerationResult:
    project_name: str
    github_repo_url: str = ""
    github_repo_name: str = ""
    mlflow_experiment_id: str = ""
    uc_schema_dev: str = ""
    uc_schema_staging: str = ""
    uc_schema_prod: str = ""
    uc_volume_dev: str = ""
    uc_volume_staging: str = ""
    secret_scope_name: str = ""
    budget_policy_id: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add_step(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append({"name": name, "status": status, "detail": detail})

    @property
    def succeeded(self) -> bool:
        return any(s["status"] == "ok" for s in self.steps)

    @property
    def all_ok(self) -> bool:
        return len(self.steps) > 0 and all(s["status"] == "ok" for s in self.steps)


class ProjectInfrastructureGenerator:
    def __init__(
        self,
        config: AppConfig | None = None,
        bundle_service: Any = None,
        budget_policy_service: Any = None,
    ) -> None:
        self._cfg = config or get_config()
        # Injectable for tests; defaults to a real BundleService on first use
        self._bundle = bundle_service
        # Injectable for tests; defaults to a real BudgetPolicyService on first use
        self._budget_policy = budget_policy_service

    def generate(
        self,
        project_name: str,
        owner_email: str,
        interview_responses: dict[str, Any],
    ) -> GenerationResult:
        """Run all generation steps. Returns a result with per-step statuses."""
        result = GenerationResult(project_name=project_name)

        # Step 0: resolve budget policy (must happen before scaffold render)
        budget_policy_id = self._resolve_budget_policy(
            project_name, interview_responses.get("team_name", ""), interview_responses, result
        )

        # Step 1 + 2: scaffold code + push to GitHub
        scaffold_dir = self._scaffold_code(project_name, owner_email, interview_responses, result, budget_policy_id)

        if scaffold_dir and self._cfg.github_token:
            self._create_github_repo(project_name, owner_email, scaffold_dir, interview_responses, result)
        else:
            result.add_step("github_repo", "skipped", "GITHUB_TOKEN not set")

        # Step 3: UC schemas + volumes
        self._create_uc_schemas(project_name, result)
        self._create_uc_volumes(result)

        # Step 4: MLflow experiment
        self._create_mlflow_experiment(project_name, result)

        # Secret scope is deliberately NOT created here (owner request
        # 2026-07-13): traced every reference to it and found zero consumers
        # — no generated template reads or writes a secret through it. Eager
        # creation was speculative infrastructure with nothing behind it.
        # _create_secret_scope() stays available for whenever a real
        # consumer needs one; nothing calls it yet.

        return result

    # ── Step 0: budget policy resolution ─────────────────────────────────────

    def _resolve_budget_policy(
        self,
        project_name: str,
        team_name: str,
        interview_responses: dict[str, Any],
        result: GenerationResult,
    ) -> str:
        """Owner request 2026-07-12. An explicit wizard override wins outright
        (already resolved, no API call needed). Otherwise an idempotent
        per-project policy is created, falling back to the control-plane
        default on a real failure, falling back to no attribution at all
        when account credentials aren't configured (§25) — this step never
        blocks project creation."""
        override = str(interview_responses.get("budget_policy_id") or "").strip()
        if override:
            result.budget_policy_id = override
            result.add_step("budget_policy", "ok", f"wizard override: {override}")
            return override

        from services.budget_policy_service import BudgetPolicyService, BudgetPolicyUnavailable

        if self._budget_policy is None:
            self._budget_policy = BudgetPolicyService(self._cfg)
        svc = self._budget_policy
        try:
            handle = svc.ensure_policy(
                f"mlops-{project_name}",
                {"project_id": project_name, "team": team_name, "managed_by": "mlops_control_plane"},
            )
            result.budget_policy_id = handle.policy_id
            status = "reused" if handle.already_existed else "created"
            result.add_step("budget_policy", "ok", f"{status}: {handle.policy_id}")
            return handle.policy_id
        except BudgetPolicyUnavailable as exc:
            result.add_step("budget_policy", "skipped", str(exc))
            return ""
        except Exception as exc:
            try:
                handle = svc.ensure_default_policy()
                result.budget_policy_id = handle.policy_id
                result.add_step(
                    "budget_policy", "ok", f"fell back to control-plane default ({exc}): {handle.policy_id}"
                )
                return handle.policy_id
            except Exception as fallback_exc:
                result.add_step(
                    "budget_policy",
                    "skipped",
                    f"per-project policy failed ({exc}); default also unavailable ({fallback_exc})",
                )
                return ""

    # ── Step 1: scaffold ──────────────────────────────────────────────────────

    def _scaffold_code(
        self,
        project_name: str,
        owner_email: str,
        interview_responses: dict[str, Any],
        result: GenerationResult,
        budget_policy_id: str = "",
    ) -> Path | None:
        try:
            from services.bundle_service import BundleService

            if self._bundle is None:
                self._bundle = BundleService(self._cfg)

            tmp = Path(tempfile.mkdtemp(prefix="mlops_scaffold_"))
            scaffold_path = self._bundle.generate(
                project_name=project_name,
                team_name=interview_responses.get("team_name", ""),
                owner_email=owner_email,
                interview_responses=interview_responses,
                output_dir=tmp,
                budget_policy_id=budget_policy_id,
            )

            # Write .mlops/ platform files into the scaffold
            self._write_mlops_files(scaffold_path, project_name, owner_email, interview_responses)

            # The GitHub step pushes `main`, so the scaffold must be a
            # committed git repo before it runs
            self._git_init_commit(scaffold_path)

            result.add_step("scaffold_code", "ok", str(scaffold_path))
            return scaffold_path

        except Exception as exc:
            result.add_step("scaffold_code", "failed", str(exc))
            return None

    @staticmethod
    def _git_init_commit(scaffold_path: Path) -> None:
        for args in (
            ["git", "init", "-b", "main"],
            ["git", "add", "-A"],
            [
                "git",
                "-c",
                "user.name=mlops-control-plane",
                "-c",
                "user.email=mlops-control-plane@noreply.local",
                "commit",
                # Host-machine hooks (e.g. commit-msg policies) must not gate
                # this machine-generated commit in an ephemeral scaffold repo
                "--no-verify",
                "-m",
                "Initial scaffold",
            ],
        ):
            subprocess.run(args, cwd=scaffold_path, check=True, capture_output=True)

    def _write_mlops_files(
        self,
        scaffold_path: Path,
        project_name: str,
        owner_email: str,
        interview_responses: dict[str, Any],
    ) -> None:
        """Write .mlops/ tracking files and CI/CD change-scope script into the scaffold."""
        mlops_dir = scaffold_path / ".mlops"
        mlops_dir.mkdir(exist_ok=True)
        scripts_dir = scaffold_path / "scripts"
        scripts_dir.mkdir(exist_ok=True)

        # Manifest hash — SHA-256 of canonical wizard responses (excludes embedded hash)
        clean = {k: v for k, v in interview_responses.items() if k != "_manifest_hash"}
        canonical = json.dumps(clean, sort_keys=True, ensure_ascii=True)
        manifest_hash = hashlib.sha256(canonical.encode()).hexdigest()

        (mlops_dir / "manifest_hash.txt").write_text(manifest_hash + "\n")

        # Approved state placeholder — updated by CD pipeline on each successful promotion
        (mlops_dir / "approved_state.txt").write_text("INITIAL\n")

        # Approval record — tracks required signatories with the hash they signed off on
        r = interview_responses
        approval_record = {
            "project_name": project_name,
            "manifest_hash": manifest_hash,
            "created_timestamp": datetime.now(UTC).isoformat(),
            "required_approvers": [
                {"role": "Legal / Fairness", "email": r.get("legal_contact_email", "")},
                {"role": "Business Stakeholder", "email": r.get("business_contact_email", "")},
                {"role": "Security Team", "email": r.get("security_contact_email", "")},
                {"role": "Compliance", "email": r.get("compliance_contact_email", "")},
                {"role": "Internal Audit", "email": r.get("internal_audit_contact_email", "")},
                {"role": "Code Reviewer", "email": owner_email, "count": r.get("code_review_count", 2)},
            ],
            "approval_history": [],
        }
        (mlops_dir / "approval_record.json").write_text(json.dumps(approval_record, indent=2) + "\n")

        # CI/CD change-scope detection script
        check_scope_script = self._check_scope_script(project_name)
        script_path = scripts_dir / "check_change_scope.py"
        script_path.write_text(check_scope_script)
        script_path.chmod(0o755)

        # QA/dev reaper, invoked by deploy_prod.yml before deploying (owner
        # request 2026-07-13). Self-contained (databricks-sdk only) — this
        # runs inside the PROJECT's own CI, which doesn't have this app's
        # services/ package. Mirrors services/qa_cleanup_service.py's logic;
        # not shared code, different repos.
        cleanup_script = self._cleanup_qa_script(project_name)
        cleanup_path = scripts_dir / "cleanup_qa_resources.py"
        cleanup_path.write_text(cleanup_script)
        cleanup_path.chmod(0o755)

    @staticmethod
    def _cleanup_qa_script(project_name: str) -> str:
        return f'''#!/usr/bin/env python3
"""Delete non-essential dev/QA-only endpoints and scratch tables before a
prod deploy (owner request 2026-07-13) -- so prod doesn't inherit
exploration clutter (e.g. "{project_name}_v25"). Mirrors
services/qa_cleanup_service.py's logic (not shared code -- this runs inside
this project's own CI, a different repo than the control-plane app).

Deliberately conservative, same as the in-app version:
  - endpoints: only ones prefixed "{project_name}" and NOT the bundle's own
    managed endpoint names are deleted.
  - tables: only ones in this project's non-prod schema(s) prefixed
    zz_/scratch_/tmp_ are deleted. Everything else is left alone.

Best-effort -- failures are printed but never fail the CI job (this script
is invoked with `continue-on-error: true` in deploy_prod.yml).

Env vars required: DATABRICKS_HOST, DATABRICKS_TOKEN.
"""

import os

from databricks.sdk import WorkspaceClient

PROJECT_NAME = {project_name!r}
SCRATCH_TABLE_PREFIXES = ("zz_", "scratch_", "tmp_")
KEEP_ENDPOINT_NAMES = {{f"{{PROJECT_NAME}}-dev", f"{{PROJECT_NAME}}-staging", f"{{PROJECT_NAME}}-prod"}}
# Non-prod schemas to sweep for scratch tables -- ${{var.catalog}}/${{var.schema}}
# resolve per-target in the bundle itself; here we read them from the
# deploying environment's own catalog/schema variables.
NON_PROD_SCHEMAS = [
    s
    for s in (os.environ.get("MLOPS_DEV_SCHEMA", ""), os.environ.get("MLOPS_STAGING_SCHEMA", ""))
    if s
]


def cleanup_endpoints(ws: WorkspaceClient) -> None:
    for ep in ws.serving_endpoints.list():
        if ep.name in KEEP_ENDPOINT_NAMES:
            continue
        if ep.name.startswith(f"{{PROJECT_NAME}}_") or ep.name.startswith(f"{{PROJECT_NAME}}-"):
            try:
                ws.serving_endpoints.delete(name=ep.name)
                print(f"deleted endpoint: {{ep.name}}")
            except Exception as exc:
                print(f"WARNING: could not delete endpoint {{ep.name}}: {{exc}}")


def cleanup_tables(ws: WorkspaceClient) -> None:
    for schema_path in NON_PROD_SCHEMAS:
        catalog, schema = schema_path.split(".", 1)
        try:
            tables = list(ws.tables.list(catalog_name=catalog, schema_name=schema))
        except Exception as exc:
            print(f"WARNING: could not list tables in {{schema_path}}: {{exc}}")
            continue
        for table in tables:
            if any(table.name.startswith(p) for p in SCRATCH_TABLE_PREFIXES):
                full_name = f"{{schema_path}}.{{table.name}}"
                try:
                    ws.tables.delete(full_name=full_name)
                    print(f"deleted table: {{full_name}}")
                except Exception as exc:
                    print(f"WARNING: could not delete table {{full_name}}: {{exc}}")


def main() -> None:
    ws = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    cleanup_endpoints(ws)
    cleanup_tables(ws)


if __name__ == "__main__":
    main()
'''

    @staticmethod
    def _check_scope_script(project_name: str) -> str:
        return f'''#!/usr/bin/env python3
"""Check whether changes in this PR require full re-approval or can auto-promote.

Compares the changed files against the last approved git state stored in
.mlops/approved_state.txt. Substantive changes (model logic, features, config)
require every required approver to re-sign-off and see a diff of what changed.
Bug-fix changes (tests, docs, minor patches) auto-promote without re-approval.

Exit codes:
  0 — bug-fix: auto-promote allowed
  1 — substantive change: re-approval required (writes .mlops/review_request.md)
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_NAME = {project_name!r}

# Changes in these paths trigger full re-approval
SUBSTANTIVE_PREFIXES = [
    "src/train.py",
    "src/features.py",
    "src/evaluate.py",
    "src/preprocess.py",
    "src/explain.py",
    "conf/",
    "databricks.yml",
]

# Changes only in these paths are always safe to auto-promote
SAFE_ONLY_PREFIXES = [
    "tests/",
    "docs/",
    "README",
    ".github/",
]


def get_approved_sha() -> str:
    approved = Path(".mlops/approved_state.txt").read_text().strip()
    if approved == "INITIAL":
        # First deployment — always require full approval
        return ""
    return approved


def get_changed_files(base_sha: str) -> list[str]:
    if not base_sha:
        return ["INITIAL_DEPLOYMENT"]
    result = subprocess.run(
        ["git", "diff", "--name-only", base_sha, "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return [f for f in result.stdout.strip().split("\\n") if f]


def classify(changed: list[str]) -> tuple[str, list[str]]:
    if not changed or changed == ["INITIAL_DEPLOYMENT"]:
        return "initial", []
    substantive = [
        f for f in changed
        if any(f.startswith(p) for p in SUBSTANTIVE_PREFIXES)
    ]
    all_safe = all(
        any(f.startswith(p) for p in SAFE_ONLY_PREFIXES) for f in changed
    )
    if not substantive and all_safe:
        return "bug_fix", []
    return "feature_change", substantive or changed


def build_review_request(changed: list[str], base_sha: str) -> str:
    manifest_hash = Path(".mlops/manifest_hash.txt").read_text().strip()
    record = json.loads(Path(".mlops/approval_record.json").read_text())
    short_sha = base_sha[:8] if base_sha else "n/a"

    lines = [
        "## Re-Approval Required",
        "",
        f"**Project:** `{{PROJECT_NAME}}`",
        f"**Previously approved state:** `{{short_sha}}`",
        f"**Manifest hash:** `{{manifest_hash}}`",
        "",
        "The following substantive files changed since the last approved state:",
        "",
    ]
    for f in changed:
        lines.append(f"- `{{f}}`")

    lines += [
        "",
        "**Required approvals** — each approver must review the diff below and re-confirm:",
        "",
    ]
    for approver in record.get("required_approvers", []):
        role = approver.get("role", "")
        email = approver.get("email", "")
        count = approver.get("count", "")
        count_str = f" (x{{count}})" if count else ""
        email_str = f" — {{email}}" if email else ""
        lines.append(f"- **{{role}}**{{count_str}}{{email_str}}")

    lines += ["", "**Diff from last approved state:**", "```diff"]
    try:
        if base_sha:
            diff = subprocess.run(
                ["git", "diff", base_sha, "HEAD", "--", *changed[:10]],
                capture_output=True, text=True, check=True,
            ).stdout[:4000]
            lines.append(diff or "(no diff available)")
        else:
            lines.append("(initial deployment — no prior state)")
    except Exception as exc:
        lines.append(f"(diff unavailable: {{exc}})")
    lines.append("```")

    return "\\n".join(lines)


def main() -> None:
    base_sha = get_approved_sha()
    changed = get_changed_files(base_sha)
    change_type, substantive = classify(changed)

    if change_type == "bug_fix":
        print(f"✓ Bug-fix change — auto-promote allowed ({{len(changed)}} file(s) changed)")
        sys.exit(0)

    review_md = build_review_request(substantive or changed, base_sha)
    Path(".mlops/review_request.md").write_text(review_md + "\\n")

    print(review_md)
    print()

    if change_type == "initial":
        print("ℹ Initial deployment — full approval required before first promotion.")
    else:
        print(f"⚠ Substantive change detected ({{len(substantive)}} file(s)) — re-approval required.")

    sys.exit(1)


if __name__ == "__main__":
    main()
'''

    # ── Step 2: GitHub ────────────────────────────────────────────────────────

    _GITHUB_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")

    def _is_repo_empty(self, repo: Any) -> tuple[bool, str]:
        """Empty modulo self._cfg.empty_repo_ignore_patterns (owner request
        2026-07-13: "some companies use automation to put in specific
        files/patterns" — a repo stamped with a README/.gitignore/.github by
        org automation at creation time still counts as empty). Returns
        (is_empty, detail) — detail explains what blocked it, if anything."""
        from github import GithubException

        try:
            contents = repo.get_contents("")
        except GithubException as exc:
            if exc.status == 404:
                return True, "no commits"
            raise
        entries = contents if isinstance(contents, list) else [contents]
        blocking = [e.name for e in entries if e.name not in self._cfg.empty_repo_ignore_patterns]
        if blocking:
            return False, f"non-empty: {', '.join(blocking)}"
        return True, f"empty modulo ignored: {', '.join(e.name for e in entries)}" if entries else "no commits"

    def _create_github_repo(
        self,
        project_name: str,
        owner_email: str,
        scaffold_dir: Path,
        interview_responses: dict[str, Any],
        result: GenerationResult,
    ) -> None:
        try:
            from github import Github, GithubException

            gh = Github(self._cfg.github_token)

            existing_repo_url = str(interview_responses.get("existing_repo_url") or "").strip()
            repo_name = project_name.replace("_", "-")

            if existing_repo_url:
                match = self._GITHUB_URL_RE.match(existing_repo_url)
                if not match:
                    result.add_step(
                        "github_repo",
                        "failed",
                        "existing_repo_url isn't a recognized https://github.com/<owner>/<repo> URL: "
                        f"{existing_repo_url}",
                    )
                    return
                owner_name, existing_repo_name = match.group(1), match.group(2)
                repo = gh.get_repo(f"{owner_name}/{existing_repo_name}")
                is_empty, detail = self._is_repo_empty(repo)
                if not is_empty:
                    result.add_step(
                        "github_repo",
                        "failed",
                        f"{existing_repo_url} is not empty ({detail}) — link an empty repo, or leave "
                        "the field blank to create a new one.",
                    )
                    return
                repo_name = existing_repo_name
            else:
                # GITHUB_ORG is optional — GitHub's API has no "organization" for
                # a personal account, so an unset org creates the repo under the
                # authenticated user instead (both expose the same
                # create_repo/get_repo interface).
                owner = gh.get_organization(self._cfg.github_org) if self._cfg.github_org else gh.get_user()
                description = interview_responses.get("problem_statement", "")[:250]

                try:
                    repo = owner.create_repo(
                        name=repo_name,
                        description=description,
                        private=True,
                        auto_init=False,
                    )
                except GithubException as exc:
                    if exc.status == 422:  # already exists
                        repo = owner.get_repo(repo_name)
                    else:
                        raise

            clone_url = repo.clone_url  # https://github.com/org/repo.git
            # Embed token so the push doesn't require interactive auth
            authed_url = clone_url.replace(
                "https://",
                f"https://{self._cfg.github_token}@",
            )

            # Add remote and push
            subprocess.run(
                ["git", "remote", "add", "origin", authed_url],
                cwd=scaffold_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "push", "-u", "origin", "main"],
                cwd=scaffold_dir,
                check=True,
                capture_output=True,
            )

            # Branch protection: require PR reviews
            try:
                branch = repo.get_branch("main")
                branch.edit_protection(
                    required_approving_review_count=2,
                    dismiss_stale_reviews=True,
                    enforce_admins=False,
                )
            except Exception:
                pass  # branch protection is best-effort

            result.github_repo_url = repo.html_url
            result.github_repo_name = repo_name
            result.add_step("github_repo", "ok", repo.html_url)

        except Exception as exc:
            result.add_step("github_repo", "failed", str(exc))

    # ── Step 3: UC schemas ────────────────────────────────────────────────────

    def _create_uc_schemas(self, project_name: str, result: GenerationResult) -> None:
        """dev/staging resolve into the configured non-prod catalog (owner
        request 2026-07-13: "development will be done in a non-prod
        workspace... schema defined in the App config") via
        projects_catalog_for(); prod stays in the prod catalog. The `_dev`/
        `_staging`/`_prod` schema-name suffix is kept even though the
        catalogs now usually differ — dropping it would collide if an org
        hasn't configured a separate non-prod catalog (all three envs then
        share cfg.catalog, and identical schema names across envs would
        clash). Suffixed names stay valid and backward-compatible either way.
        """
        try:
            from databricks.sdk import WorkspaceClient

            ws = WorkspaceClient(
                host=self._cfg.databricks_host,
                token=self._cfg.databricks_token,
            )

            schemas = {
                "dev": f"{self._cfg.projects_catalog_for('dev')}.{project_name}_dev",
                "staging": f"{self._cfg.projects_catalog_for('staging')}.{project_name}_staging",
                "prod": f"{self._cfg.projects_catalog_for('prod')}.{project_name}_prod",
            }

            for env, full_path in schemas.items():
                catalog, schema = full_path.split(".", 1)
                try:
                    ws.schemas.create(catalog_name=catalog, name=schema)
                except Exception as exc:
                    # Schema may already exist — ignore that specific error
                    if "already exists" not in str(exc).lower():
                        raise

            result.uc_schema_dev = schemas["dev"]
            result.uc_schema_staging = schemas["staging"]
            result.uc_schema_prod = schemas["prod"]
            result.add_step("uc_schemas", "ok", ", ".join(schemas.values()))

        except Exception as exc:
            result.add_step("uc_schemas", "failed", str(exc))

    # ── Step 3b: UC Volumes (owner request 2026-07-13) ────────────────────────

    VOLUME_NAME = "artifacts"

    def _create_uc_volumes(self, result: GenerationResult) -> None:
        """One managed Volume per non-prod schema — holds data snapshots,
        profile reports, and EDA notebook checkpoints. dev/staging only:
        prod is the served/deployed environment, not a DS experimentation
        space, so it has no artifacts volume. Requires uc_schema_dev/
        uc_schema_staging already set on `result` (runs after
        _create_uc_schemas)."""
        if not result.uc_schema_dev and not result.uc_schema_staging:
            result.add_step("uc_volumes", "skipped", "no non-prod schema to attach a volume to")
            return
        try:
            from databricks.sdk import WorkspaceClient
            from databricks.sdk.service.catalog import VolumeType

            ws = WorkspaceClient(
                host=self._cfg.databricks_host,
                token=self._cfg.databricks_token,
            )

            created: list[str] = []
            for schema_attr, volume_attr in (
                ("uc_schema_dev", "uc_volume_dev"),
                ("uc_schema_staging", "uc_volume_staging"),
            ):
                schema_path = getattr(result, schema_attr)
                if not schema_path:
                    continue
                catalog, schema = schema_path.split(".", 1)
                try:
                    ws.volumes.create(
                        catalog_name=catalog,
                        schema_name=schema,
                        name=self.VOLUME_NAME,
                        volume_type=VolumeType.MANAGED,
                    )
                except Exception as exc:
                    if "already exists" not in str(exc).lower():
                        raise
                volume_path = f"{schema_path}.{self.VOLUME_NAME}"
                setattr(result, volume_attr, volume_path)
                created.append(volume_path)

            result.add_step("uc_volumes", "ok", ", ".join(created))

        except Exception as exc:
            result.add_step("uc_volumes", "failed", str(exc))

    # ── Step 4: MLflow experiment ─────────────────────────────────────────────

    def _create_mlflow_experiment(self, project_name: str, result: GenerationResult) -> None:
        try:
            import mlflow
            from databricks.sdk import WorkspaceClient

            mlflow.set_tracking_uri("databricks")
            experiment_path = f"/Shared/mlops/{project_name}"

            # MLflow does not create parent workspace directories — found live
            # 2026-07-07: /Shared/mlops missing makes create_experiment 404
            ws = WorkspaceClient(
                host=self._cfg.databricks_host,
                token=self._cfg.databricks_token,
            )
            ws.workspace.mkdirs("/Shared/mlops")

            existing = mlflow.get_experiment_by_name(experiment_path)
            if existing:
                exp_id = existing.experiment_id
            else:
                exp_id = mlflow.create_experiment(experiment_path)

            result.mlflow_experiment_id = exp_id
            result.add_step("mlflow_experiment", "ok", experiment_path)

        except Exception as exc:
            result.add_step("mlflow_experiment", "failed", str(exc))

    # ── Step 5: Secret scope ──────────────────────────────────────────────────

    def _create_secret_scope(self, project_name: str, result: GenerationResult) -> None:
        try:
            from databricks.sdk import WorkspaceClient

            ws = WorkspaceClient(
                host=self._cfg.databricks_host,
                token=self._cfg.databricks_token,
            )

            scope_name = f"mlops-{project_name}"
            try:
                ws.secrets.create_scope(scope=scope_name)
            except Exception as exc:
                if "already exists" not in str(exc).lower():
                    raise

            result.secret_scope_name = scope_name
            result.add_step("secret_scope", "ok", scope_name)

        except Exception as exc:
            result.add_step("secret_scope", "failed", str(exc))
