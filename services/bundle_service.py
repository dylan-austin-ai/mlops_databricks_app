"""Bundle Service — declarative infrastructure via Databricks Asset Bundles (§5.2).

Wraps the pinned Databricks CLI with a structured (JSON) plan/deploy flow:

  generate()   render databricks.yml + resources/*.yml + src/ from Jinja2 templates
  validate()   `bundle validate -o json` before any PR opens
  plan()       `bundle plan -o json` — the reviewable, hashable deployment plan
  deploy()     `bundle deploy --plan <file>` — deploys exactly the reviewed plan,
               refusing to run if the plan file's hash no longer matches
  verify()     post-deploy read-back via `bundle summary` + the Databricks SDK —
               a zero exit code is necessary but not sufficient evidence
  destroy()    `bundle destroy --auto-approve` — Phase 6 archival only, behind approval

The CLI version is pinned; health_check() fails loudly on drift rather than
silently degrading (design tenet 5).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from config import AppConfig, get_config

PINNED_CLI_VERSION = "1.6.0"

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "bundle"

_SUBPROCESS_TIMEOUT_S = 300


class BundleServiceError(RuntimeError):
    """Raised when a bundle operation fails or preconditions aren't met."""


@dataclass
class CliResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class PlanSummary:
    """A generated, reviewable deployment plan (§5.2, §15.1)."""

    target: str
    plan_path: Path
    plan_hash: str  # sha256 of the plan file — recorded on approval records
    actions: list[dict[str, str]] = field(default_factory=list)  # [{action, resource}]

    @property
    def is_noop(self) -> bool:
        return not self.actions


@dataclass
class VerificationResult:
    """Post-deploy read-back evidence (§5.2 'trust but verify')."""

    resource_key: str
    resource_type: str
    exists: bool
    detail: str = ""


def unix_cron_to_quartz(cron: str) -> str:
    """Convert a 5-field unix cron to the 6-field Quartz form Databricks expects.

    Quartz requires '?' in exactly one of day-of-month / day-of-week, and its
    day-of-week is 1-7 with Sunday=1 (unix: 0-6 with Sunday=0; 7 also Sunday).
    Verified against the live Jobs API — it rejects unix-numbered weekdays.
    """
    fields = cron.split()
    if len(fields) == 6 or len(fields) == 7:
        return cron  # already Quartz-shaped
    if len(fields) != 5:
        raise BundleServiceError(f"Unrecognized cron expression: {cron!r}")
    minute, hour, dom, month, dow = fields
    if dow == "*":
        dow = "?"
    else:
        dow = _shift_unix_dow(dow)
        if dom == "*":
            dom = "?"
    return f"0 {minute} {hour} {dom} {month} {dow}"


def _shift_unix_dow(dow: str) -> str:
    """Renumber a unix day-of-week field (0-7, SUN=0 or 7) to Quartz (1-7, SUN=1)."""

    def shift(match: re.Match[str]) -> str:
        n = int(match.group())
        return str(1 if n == 7 else n + 1)

    return re.sub(r"\d+", shift, dow)


class BundleService:
    def __init__(
        self,
        config: AppConfig | None = None,
        cli_path: str | None = None,
        runner: Any = None,
    ) -> None:
        self._cfg = config or get_config()
        self._cli = cli_path or shutil.which("databricks") or str(Path.home() / ".local/bin/databricks")
        # Injectable for tests: callable(list[str], cwd) -> CliResult
        self._runner = runner or self._run_subprocess

    # ── CLI plumbing ──────────────────────────────────────────────────────────

    def _run_subprocess(self, args: list[str], cwd: Path | None = None) -> CliResult:
        env = {
            **os.environ,
            "DATABRICKS_HOST": self._cfg.databricks_host,
            "DATABRICKS_TOKEN": self._cfg.databricks_token,
        }
        proc = subprocess.run(
            [self._cli, *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
        return CliResult(args=list(args), returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)

    def health_check(self) -> str:
        """Confirm the pinned CLI binary is present and the expected version.

        Raises BundleServiceError on any drift — fail loudly, not degraded.
        """
        if not Path(self._cli).exists() and shutil.which(self._cli) is None:
            raise BundleServiceError(
                f"Databricks CLI not found at {self._cli!r}. "
                f"Install v{PINNED_CLI_VERSION} before using the Bundle Service."
            )
        result = self._runner(["--version"], None)
        if not result.ok:
            raise BundleServiceError(f"Databricks CLI --version failed: {result.stderr}")
        if PINNED_CLI_VERSION not in result.stdout:
            raise BundleServiceError(
                f"Databricks CLI version drift: expected v{PINNED_CLI_VERSION}, "
                f"got {result.stdout.strip()!r}. Update PINNED_CLI_VERSION deliberately "
                f"(re-verifying the bundle schema) rather than running mixed versions."
            )
        return result.stdout.strip()

    # ── generate ──────────────────────────────────────────────────────────────

    def generate(
        self,
        project_name: str,
        team_name: str,
        owner_email: str,
        interview_responses: dict[str, Any],
        output_dir: Path,
    ) -> Path:
        """Render the full bundle scaffold into output_dir and return its path."""
        inference_type = interview_responses.get("inference_type", "batch")
        route_override = interview_responses.get("route_optimization_override_reason", "")
        capture_override = interview_responses.get("inference_capture_override_reason", "")

        retraining_cron = ""
        if interview_responses.get("retraining_schedule"):
            retraining_cron = unix_cron_to_quartz(interview_responses["retraining_schedule"])
        batch_cron = ""
        if inference_type in ("batch", "both") and interview_responses.get("batch_schedule"):
            batch_cron = unix_cron_to_quartz(interview_responses["batch_schedule"])

        context = {
            "project_name": project_name,
            "team_name": team_name,
            "owner_email": owner_email,
            "workspace_host": self._cfg.databricks_host,
            # Schema-per-project inside a configurable catalog (owner decision
            # 2026-07-07); per-env catalog overrides are config, not code.
            "catalog_dev": self._cfg.projects_catalog_for("dev"),
            "catalog_staging": self._cfg.projects_catalog_for("staging"),
            "catalog_prod": self._cfg.projects_catalog_for("prod"),
            "cli_version": PINNED_CLI_VERSION,
            "retraining_cron": retraining_cron,
            "batch_cron": batch_cron,
            "streaming": inference_type == "streaming",
            "streaming_source_table": interview_responses.get("streaming_source_table", ""),
            "target_default_unpaused": True,
            # Serving defaults are ON unless an explicit, logged override reason
            # was captured (§9.1) — governance enforced structurally.
            "route_optimized": not route_override,
            "inference_capture": not capture_override,
            # First deploy serves version 1. Live-verified 2026-07-07
            # (DECISIONS_NEEDED #3): entity_version rejects UC aliases
            # ("Entity version must be a number"), so this stays numeric and
            # promotion updates the endpoint config (saga step 6).
            "champion_version": interview_responses.get("champion_version", "1"),
        }

        env = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

        bundle_dir = output_dir / project_name
        rendered: list[tuple[str, Path]] = [
            ("databricks.yml.j2", bundle_dir / "databricks.yml"),
            ("resources/schemas.yml.j2", bundle_dir / "resources" / "schemas.yml"),
            ("resources/jobs.yml.j2", bundle_dir / "resources" / "jobs.yml"),
            ("src/train.py.j2", bundle_dir / "src" / "train.py"),
        ]
        if inference_type in ("real_time", "both"):
            rendered.append(("resources/model_serving.yml.j2", bundle_dir / "resources" / "model_serving.yml"))
        if inference_type in ("batch", "both"):
            rendered.append(("src/batch_score.py.j2", bundle_dir / "src" / "batch_score.py"))
        if inference_type == "streaming":
            rendered.append(("src/stream_score.py.j2", bundle_dir / "src" / "stream_score.py"))

        for template_name, dest in rendered:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(env.get_template(template_name).render(context))

        return bundle_dir

    # ── validate / plan / deploy / verify / destroy ──────────────────────────

    def validate(self, bundle_dir: Path, target: str) -> dict[str, Any]:
        result = self._runner(["bundle", "validate", "-t", target, "-o", "json"], bundle_dir)
        if not result.ok:
            raise BundleServiceError(f"bundle validate failed for target {target}:\n{result.stderr}")
        return json.loads(result.stdout)

    def plan(self, bundle_dir: Path, target: str) -> PlanSummary:
        """Produce a structured JSON plan and persist it for review + deploy."""
        result = self._runner(["bundle", "plan", "-t", target, "-o", "json"], bundle_dir)
        if not result.ok:
            raise BundleServiceError(f"bundle plan failed for target {target}:\n{result.stderr}")

        plan_path = bundle_dir / f"plan_{target}.json"
        plan_path.write_text(result.stdout)
        plan_hash = hashlib.sha256(result.stdout.encode()).hexdigest()

        actions = self._parse_plan_actions(result.stdout)
        return PlanSummary(target=target, plan_path=plan_path, plan_hash=plan_hash, actions=actions)

    @staticmethod
    def _parse_plan_actions(plan_json: str) -> list[dict[str, str]]:
        plan = json.loads(plan_json)
        actions: list[dict[str, str]] = []
        # v1.6.0 plan shape: {"plan": {"<group>.<key>": {"action": "create"|...}, ...}}
        entries = plan.get("plan", plan)
        if isinstance(entries, dict):
            for resource, detail in entries.items():
                if isinstance(detail, dict) and "action" in detail:
                    actions.append({"resource": resource, "action": str(detail["action"])})
        return actions

    def deploy(self, bundle_dir: Path, plan: PlanSummary) -> None:
        """Deploy exactly the reviewed plan — never a re-resolved one (§5.2, §15.1)."""
        if not plan.plan_path.exists():
            raise BundleServiceError(f"Plan file missing: {plan.plan_path}")
        current_hash = hashlib.sha256(plan.plan_path.read_bytes()).hexdigest()
        if current_hash != plan.plan_hash:
            raise BundleServiceError(
                f"Plan file {plan.plan_path} changed since it was reviewed "
                f"(hash {current_hash[:12]} != approved {plan.plan_hash[:12]}). "
                "Re-plan and re-review; refusing to deploy an unreviewed plan."
            )
        result = self._runner(
            ["bundle", "deploy", "-t", plan.target, "--plan", str(plan.plan_path)],
            bundle_dir,
        )
        if not result.ok:
            raise BundleServiceError(f"bundle deploy failed for target {plan.target}:\n{result.stderr}")

    def verify(self, bundle_dir: Path, target: str) -> list[VerificationResult]:
        """Independently read back deployed resource state (§5.2 'trust but verify').

        Uses `bundle summary` for deployed IDs, then confirms each resource
        actually exists via a direct SDK call — not just the CLI's word for it.
        """
        result = self._runner(["bundle", "summary", "-t", target, "-o", "json"], bundle_dir)
        if not result.ok:
            raise BundleServiceError(f"bundle summary failed for target {target}:\n{result.stderr}")
        summary = json.loads(result.stdout)

        from databricks.sdk import WorkspaceClient

        ws = WorkspaceClient(host=self._cfg.databricks_host, token=self._cfg.databricks_token)

        checks: list[VerificationResult] = []
        resources = summary.get("resources", {})

        for key, job in resources.get("jobs", {}).items():
            job_id = job.get("id")
            if not job_id:
                checks.append(VerificationResult(key, "job", False, "no id in summary"))
                continue
            try:
                fetched = ws.jobs.get(job_id=int(job_id))
                name = fetched.settings.name if fetched.settings else ""
                checks.append(VerificationResult(key, "job", True, f"id={job_id} name={name!r}"))
            except Exception as exc:
                checks.append(VerificationResult(key, "job", False, str(exc)))

        for key, ep in resources.get("model_serving_endpoints", {}).items():
            ep_name = ep.get("name") or ep.get("id")
            if not ep_name:
                checks.append(VerificationResult(key, "model_serving_endpoint", False, "no name in summary"))
                continue
            try:
                fetched = ws.serving_endpoints.get(name=ep_name)
                checks.append(
                    VerificationResult(
                        key,
                        "model_serving_endpoint",
                        True,
                        f"name={ep_name} route_optimized={getattr(fetched, 'route_optimized', None)}",
                    )
                )
            except Exception as exc:
                checks.append(VerificationResult(key, "model_serving_endpoint", False, str(exc)))

        for key, sch in resources.get("schemas", {}).items():
            full_name = sch.get("id") or (
                f"{sch.get('catalog_name')}.{sch.get('name')}" if sch.get("catalog_name") and sch.get("name") else ""
            )
            if not full_name:
                checks.append(VerificationResult(key, "schema", False, "no id in summary"))
                continue
            try:
                fetched = ws.schemas.get(full_name=full_name)
                checks.append(VerificationResult(key, "schema", True, f"full_name={fetched.full_name}"))
            except Exception as exc:
                checks.append(VerificationResult(key, "schema", False, str(exc)))

        return checks

    def destroy(self, bundle_dir: Path, target: str) -> None:
        """Tear down all bundle resources. Phase 6 archival only — always behind approval."""
        result = self._runner(["bundle", "destroy", "-t", target, "--auto-approve"], bundle_dir)
        if not result.ok:
            raise BundleServiceError(f"bundle destroy failed for target {target}:\n{result.stderr}")
