"""ProjectInfrastructureGenerator — orchestrates everything created when a project is born.

Steps executed in order:
  1. Scaffold code locally via databricks_mlops.ProjectGenerator (temp dir)
  2. Create GitHub repo and push the scaffold
  3. Create Databricks UC schemas (dev / staging / prod)
  4. Create MLflow experiment
  5. Create Databricks secret scope

Each step is best-effort with its own status reported back to the caller.
A failed GitHub step does not block UC schema creation, etc.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    secret_scope_name: str = ""
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
    def __init__(self, config: AppConfig | None = None) -> None:
        self._cfg = config or get_config()

    def generate(
        self,
        project_name: str,
        owner_email: str,
        interview_responses: dict[str, Any],
    ) -> GenerationResult:
        """Run all generation steps. Returns a result with per-step statuses."""
        result = GenerationResult(project_name=project_name)

        # Step 1 + 2: scaffold code + push to GitHub
        scaffold_dir = self._scaffold_code(project_name, owner_email, interview_responses, result)

        if scaffold_dir and self._cfg.github_token and self._cfg.github_org:
            self._create_github_repo(project_name, owner_email, scaffold_dir, interview_responses, result)
        elif not self._cfg.github_token:
            result.add_step("github_repo", "skipped", "GITHUB_TOKEN not set")

        # Step 3: UC schemas
        self._create_uc_schemas(project_name, result)

        # Step 4: MLflow experiment
        self._create_mlflow_experiment(project_name, result)

        # Step 5: Secret scope
        self._create_secret_scope(project_name, result)

        return result

    # ── Step 1: scaffold ──────────────────────────────────────────────────────

    def _scaffold_code(
        self,
        project_name: str,
        owner_email: str,
        interview_responses: dict[str, Any],
        result: GenerationResult,
    ) -> Path | None:
        try:
            from databricks_mlops.generation.project_generator import ProjectGenerator

            inference_type = interview_responses.get("inference_type", "batch")
            project_type = "realtime-model" if inference_type == "real_time" else "batch-pipeline"

            # Toolkit requires kebab-case names
            kebab_name = project_name.replace("_", "-")

            workspace_config = {
                "host": self._cfg.databricks_host,
                "catalog": self._cfg.catalog,
                "schema": project_name,
                "owner": owner_email,
            }

            features: list[str] = []
            # Fairness is always enabled; include feature if any protected attributes are declared
            fairness_attrs = interview_responses.get("fairness_attributes", [])
            if fairness_attrs:
                features.append("fairness")

            # model_frameworks (new list field) or legacy model_type
            frameworks = interview_responses.get("model_frameworks", [interview_responses.get("model_type", "sklearn")])

            tmp = Path(tempfile.mkdtemp(prefix="mlops_scaffold_"))
            gen = ProjectGenerator()
            scaffold_path = gen.create_project(
                name=kebab_name,
                project_type=project_type,
                workspace_config=workspace_config,
                output_dir=tmp,
                features=features,
                frameworks=frameworks,
            )

            # Write .mlops/ platform files into the scaffold
            self._write_mlops_files(scaffold_path, project_name, owner_email, interview_responses)

            result.add_step("scaffold_code", "ok", str(scaffold_path))
            return scaffold_path

        except Exception as exc:
            result.add_step("scaffold_code", "failed", str(exc))
            return None

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
            "created_timestamp": datetime.now(timezone.utc).isoformat(),
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
        f"**Project:** `{PROJECT_NAME}`",
        f"**Previously approved state:** `{short_sha}`",
        f"**Manifest hash:** `{manifest_hash}`",
        "",
        "The following substantive files changed since the last approved state:",
        "",
    ]
    for f in changed:
        lines.append(f"- `{f}`")

    lines += [
        "",
        "**Required approvals** — each approver must review the diff below and re-confirm:",
        "",
    ]
    for approver in record.get("required_approvers", []):
        role = approver.get("role", "")
        email = approver.get("email", "")
        count = approver.get("count", "")
        count_str = f" (x{count})" if count else ""
        email_str = f" — {email}" if email else ""
        lines.append(f"- **{role}**{count_str}{email_str}")

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
        print(f"✓ Bug-fix change — auto-promote allowed ({len(changed)} file(s) changed)")
        sys.exit(0)

    review_md = build_review_request(substantive or changed, base_sha)
    Path(".mlops/review_request.md").write_text(review_md + "\\n")

    print(review_md)
    print()

    if change_type == "initial":
        print("ℹ Initial deployment — full approval required before first promotion.")
    else:
        print(f"⚠ Substantive change detected ({len(substantive)} file(s)) — re-approval required.")

    sys.exit(1)


if __name__ == "__main__":
    main()
'''

    # ── Step 2: GitHub ────────────────────────────────────────────────────────

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
            org = gh.get_organization(self._cfg.github_org)

            description = interview_responses.get("problem_statement", "")[:250]
            repo_name = project_name.replace("_", "-")

            try:
                repo = org.create_repo(
                    name=repo_name,
                    description=description,
                    private=True,
                    auto_init=False,
                )
            except GithubException as exc:
                if exc.status == 422:  # already exists
                    repo = org.get_repo(repo_name)
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
        try:
            from databricks.sdk import WorkspaceClient

            ws = WorkspaceClient(
                host=self._cfg.databricks_host,
                token=self._cfg.databricks_token,
            )

            schemas = {
                "dev": f"{self._cfg.catalog}.{project_name}_dev",
                "staging": f"{self._cfg.catalog}.{project_name}_staging",
                "prod": f"{self._cfg.catalog}.{project_name}_prod",
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

    # ── Step 4: MLflow experiment ─────────────────────────────────────────────

    def _create_mlflow_experiment(self, project_name: str, result: GenerationResult) -> None:
        try:
            import mlflow

            mlflow.set_tracking_uri("databricks")
            experiment_path = f"/Shared/mlops/{project_name}"

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
            from databricks.sdk.service.workspace import AclPermission

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
