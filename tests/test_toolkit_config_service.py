"""Tests for toolkit_config_service — org-authored auto-import config
(owner request 2026-07-13). Mirrors policy_pack_service's YAML-loading
tests: fail closed on malformed config, [] is a normal (not error) state."""

from __future__ import annotations

import pytest

from services.toolkit_config_service import (
    TOOLKITS_DIR,
    ToolkitConfigError,
    load_toolkits,
    toolkit_imports,
    toolkit_pip_specs,
)


class TestLoadToolkits:
    def test_no_directory_returns_empty(self, tmp_path):
        assert load_toolkits(tmp_path / "does_not_exist") == []

    def test_empty_directory_returns_empty(self, tmp_path):
        assert load_toolkits(tmp_path) == []

    def test_shipped_example_is_inert(self):
        # org_toolkits.yaml.example ships but must never be picked up —
        # *.y*ml doesn't match a .example suffix, same convention policy
        # packs used before generic tiering became permanent.
        assert load_toolkits(TOOLKITS_DIR) == []

    def test_loads_valid_entries(self, tmp_path):
        (tmp_path / "org.yaml").write_text(
            "toolkits:\n"
            "  - toolkit_id: mlops_toolkit\n"
            "    name: Acme MLOps Toolkit\n"
            "    pip_spec: acme-mlops-toolkit>=2.0\n"
            "    import_statement: import acme_mlops_toolkit as mlops\n"
            "  - toolkit_id: ds_toolkit\n"
            "    name: Acme DS Toolkit\n"
            "    pip_spec: git+https://github.com/acme-corp/ds-toolkit.git@main\n"
            "    import_statement: from acme_ds_toolkit import eda\n"
        )
        specs = load_toolkits(tmp_path)

        assert [s.toolkit_id for s in specs] == ["mlops_toolkit", "ds_toolkit"]
        assert specs[0].pip_spec == "acme-mlops-toolkit>=2.0"
        assert specs[0].import_statement == "import acme_mlops_toolkit as mlops"
        assert specs[0].source_file == "org.yaml"

    def test_not_a_mapping_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("- just\n- a\n- list\n")
        with pytest.raises(ToolkitConfigError, match="not a mapping"):
            load_toolkits(tmp_path)

    def test_missing_toolkits_key_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("something_else: []\n")
        with pytest.raises(ToolkitConfigError, match="'toolkits' must be a non-empty list"):
            load_toolkits(tmp_path)

    def test_empty_toolkits_list_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("toolkits: []\n")
        with pytest.raises(ToolkitConfigError, match="non-empty list"):
            load_toolkits(tmp_path)

    def test_invalid_toolkit_id_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text(
            'toolkits:\n  - toolkit_id: "bad id; DROP--"\n    name: x\n    pip_spec: x\n    import_statement: x\n'
        )
        with pytest.raises(ToolkitConfigError, match="invalid toolkit_id"):
            load_toolkits(tmp_path)

    def test_duplicate_toolkit_id_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text(
            "toolkits:\n"
            "  - toolkit_id: dup\n"
            "    name: a\n"
            "    pip_spec: a\n"
            "    import_statement: a\n"
            "  - toolkit_id: dup\n"
            "    name: b\n"
            "    pip_spec: b\n"
            "    import_statement: b\n"
        )
        with pytest.raises(ToolkitConfigError, match="duplicate toolkit_id"):
            load_toolkits(tmp_path)

    @pytest.mark.parametrize("missing_field", ["name", "pip_spec", "import_statement"])
    def test_missing_required_field_rejected(self, tmp_path, missing_field):
        fields = {"name": "x", "pip_spec": "x", "import_statement": "x"}
        del fields[missing_field]
        lines = ["toolkits:", "  - toolkit_id: t1"]
        lines += [f"    {k}: {v}" for k, v in fields.items()]
        (tmp_path / "bad.yaml").write_text("\n".join(lines) + "\n")
        with pytest.raises(ToolkitConfigError, match=missing_field):
            load_toolkits(tmp_path)

    def test_blank_field_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text(
            "toolkits:\n  - toolkit_id: t1\n    name: x\n    pip_spec: x\n    import_statement: '   '\n"
        )
        with pytest.raises(ToolkitConfigError, match="import_statement"):
            load_toolkits(tmp_path)


class TestHelpers:
    def test_toolkit_imports_extracts_import_statements(self, tmp_path):
        (tmp_path / "org.yaml").write_text(
            "toolkits:\n  - toolkit_id: t1\n    name: x\n    pip_spec: x\n    import_statement: import x\n"
        )
        specs = load_toolkits(tmp_path)
        assert toolkit_imports(specs) == ["import x"]

    def test_toolkit_pip_specs_extracts_pip_specs(self, tmp_path):
        (tmp_path / "org.yaml").write_text(
            "toolkits:\n  - toolkit_id: t1\n    name: x\n    pip_spec: x==1.0\n    import_statement: import x\n"
        )
        specs = load_toolkits(tmp_path)
        assert toolkit_pip_specs(specs) == ["x==1.0"]
