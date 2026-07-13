"""Toolkit Config Service — org-configured auto-import for generated projects
(owner request 2026-07-13).

This app is going to be open-sourced; there's no universal "the" MLOps or
Data Science toolkit any org would want auto-imported into generated
training/EDA code. So this follows the exact pattern policy_pack_service.py
already established for org-authored, rarely-changing, PR-reviewed
declarative config: YAML files in toolkits/, GitHub is the source of truth,
loaded fresh at bundle-render time.

Unlike policy packs, toolkits have no runtime governance meaning — nothing
ever needs to look one up mid-saga or mid-approval. So there's no DB sync,
no service class, no state dependency: just a pure, stateless loader read at
generation time by BundleService.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TOOLKITS_DIR = Path(__file__).parent.parent / "toolkits"

_SLUG_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class ToolkitConfigError(RuntimeError):
    """Raised when a toolkit config file is malformed. Fail closed — a
    misconfigured toolkit entry must never be silently dropped from a
    generated project (same posture as policy_pack_service.load_packs)."""


@dataclass
class ToolkitSpec:
    toolkit_id: str
    name: str
    pip_spec: str
    import_statement: str
    source_file: str = ""


def load_toolkits(toolkits_dir: Path | None = None) -> list[ToolkitSpec]:
    """Parse and validate every toolkit YAML. Returns [] when no real config
    files exist yet (the default open-source state — only the inert
    .example ships) — that's a normal, not an error, state."""
    import yaml

    toolkits_dir = toolkits_dir or TOOLKITS_DIR
    if not toolkits_dir.exists():
        return []

    specs: list[ToolkitSpec] = []
    seen_ids: set[str] = set()
    for path in sorted(toolkits_dir.glob("*.y*ml")):
        doc = yaml.safe_load(path.read_text())
        if not isinstance(doc, dict):
            raise ToolkitConfigError(f"{path.name}: not a mapping")
        entries = doc.get("toolkits")
        if not isinstance(entries, list) or not entries:
            raise ToolkitConfigError(f"{path.name}: 'toolkits' must be a non-empty list")

        for entry in entries:
            context = f"{path.name}"
            if not isinstance(entry, dict):
                raise ToolkitConfigError(f"{context}: each toolkit entry must be a mapping")

            toolkit_id = entry.get("toolkit_id")
            if not isinstance(toolkit_id, str) or not _SLUG_RE.match(toolkit_id):
                raise ToolkitConfigError(f"{context}: missing or invalid toolkit_id")
            if toolkit_id in seen_ids:
                raise ToolkitConfigError(f"{context}: duplicate toolkit_id {toolkit_id!r}")
            seen_ids.add(toolkit_id)

            for field in ("name", "pip_spec", "import_statement"):
                value = entry.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ToolkitConfigError(f"{context}: {toolkit_id!r} missing or empty {field!r}")

            specs.append(
                ToolkitSpec(
                    toolkit_id=toolkit_id,
                    name=entry["name"].strip(),
                    pip_spec=entry["pip_spec"].strip(),
                    import_statement=entry["import_statement"].strip(),
                    source_file=path.name,
                )
            )
    return specs


def toolkit_imports(toolkits: list[ToolkitSpec]) -> list[str]:
    return [t.import_statement for t in toolkits]


def toolkit_pip_specs(toolkits: list[ToolkitSpec]) -> list[str]:
    return [t.pip_spec for t in toolkits]
