"""Tests for VolumeArtifactService — saves profile reports and EDA
snapshots into a project's UC Volume (owner request 2026-07-13)."""

from __future__ import annotations

import pytest

from config import AppConfig
from services.volume_artifact_service import VolumeArtifactError, VolumeArtifactService


class FakeFilesAPI:
    def __init__(self):
        self.uploads: list[tuple] = []

    def upload(self, file_path, contents, overwrite=None):
        self.uploads.append((file_path, contents.read(), overwrite))


class FakeWorkspaceClient:
    def __init__(self, host=None, token=None, **kwargs):
        self.files = FakeFilesAPI()


def _svc(monkeypatch) -> tuple[VolumeArtifactService, FakeWorkspaceClient]:
    cfg = AppConfig(
        databricks_host="https://test.cloud.databricks.com", databricks_token="dapi-test", warehouse_id="wh123"
    )
    svc = VolumeArtifactService(cfg)
    fake_ws = FakeWorkspaceClient()
    svc._ws_client = fake_ws
    return svc, fake_ws


class TestSaveArtifact:
    def test_rejects_malformed_volume_path(self, monkeypatch):
        svc, _ = _svc(monkeypatch)
        with pytest.raises(VolumeArtifactError):
            svc.save_artifact("not.a.valid.path.at.all", "x.txt", b"data")

    def test_rejects_unsafe_volume_path(self, monkeypatch):
        svc, _ = _svc(monkeypatch)
        with pytest.raises(VolumeArtifactError):
            svc.save_artifact("cat.schema; DROP TABLE x.volume", "x.txt", b"data")

    def test_writes_to_correct_volume_path(self, monkeypatch):
        svc, fake_ws = _svc(monkeypatch)

        result = svc.save_artifact("cat.proj_dev.artifacts", "reports/foo.html", b"<html></html>")

        assert result == "/Volumes/cat/proj_dev/artifacts/reports/foo.html"
        assert fake_ws.files.uploads[0][0] == "/Volumes/cat/proj_dev/artifacts/reports/foo.html"
        assert fake_ws.files.uploads[0][1] == b"<html></html>"
        assert fake_ws.files.uploads[0][2] is True  # overwrite

    def test_strips_leading_slash_from_sub_path(self, monkeypatch):
        svc, fake_ws = _svc(monkeypatch)
        svc.save_artifact("cat.proj_dev.artifacts", "/reports/foo.html", b"data")
        assert fake_ws.files.uploads[0][0] == "/Volumes/cat/proj_dev/artifacts/reports/foo.html"


class TestSaveProfileReport:
    def test_names_file_from_table_and_timestamp(self, monkeypatch):
        svc, fake_ws = _svc(monkeypatch)

        result = svc.save_profile_report("cat.proj_dev.artifacts", "src.schema.my_training_table", "<html>x</html>")

        assert result.startswith("/Volumes/cat/proj_dev/artifacts/profile_reports/my_training_table_")
        assert result.endswith(".html")
        assert fake_ws.files.uploads[0][1] == b"<html>x</html>"


class TestSaveEdaSnapshot:
    def test_writes_timestamped_py_file(self, monkeypatch):
        svc, fake_ws = _svc(monkeypatch)

        result = svc.save_eda_snapshot("cat.proj_dev.artifacts", "# Databricks notebook source\nprint(1)")

        assert result.startswith("/Volumes/cat/proj_dev/artifacts/eda_snapshots/eda_")
        assert result.endswith(".py")
        assert fake_ws.files.uploads[0][1] == b"# Databricks notebook source\nprint(1)"
