"""Tests for notification_service — the delivery layer alerts/approvals/HITL
escalation route through (previously: DB row only, nobody ever notified)."""

from __future__ import annotations

import json

import pytest

from config import AppConfig
from services.notification_service import NotificationService

CONFIGURED = AppConfig(
    databricks_host="https://test.cloud.databricks.com",
    databricks_token="dapi-test",
    warehouse_id="wh123",
    smtp_host="smtp.company.com",
    smtp_port=587,
    smtp_user="alerts@company.com",
    smtp_password="secret",
    smtp_from_email="alerts@company.com",
    slack_webhook_url="https://hooks.slack.example/T000/B000/xyz",
    teams_webhook_url="https://outlook.office.example/webhook/abc",
)

UNCONFIGURED = AppConfig(
    databricks_host="https://test.cloud.databricks.com",
    databricks_token="dapi-test",
    warehouse_id="wh123",
)


class FakeSMTP:
    instances: list[FakeSMTP] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_calls: list[tuple] = []
        self.sent: list[tuple] = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_calls.append((user, password))

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent.append((from_addr, to_addrs, msg))


class FailingSMTP(FakeSMTP):
    def sendmail(self, from_addr, to_addrs, msg):
        raise RuntimeError("relay refused connection")


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(status=200, calls=None):
    def urlopen(req, timeout=None):
        if calls is not None:
            calls.append((req.full_url, json.loads(req.data.decode()), timeout))
        return FakeResponse(status)

    return urlopen


def _failing_urlopen():
    def urlopen(req, timeout=None):
        raise RuntimeError("connection refused")

    return urlopen


@pytest.fixture(autouse=True)
def _reset_fake_smtp():
    FakeSMTP.instances = []
    yield


class TestEmail:
    def test_sends_via_smtp(self):
        svc = NotificationService(config=CONFIGURED, smtp_cls=FakeSMTP)

        result = svc.send(
            {"destination": "email", "email_addresses": ["oncall@co.com", "mlops@co.com"]},
            "Budget alert",
            "Project x-team exceeded 80% of its monthly budget.",
        )

        assert result.status == "sent"
        assert "2 recipient" in result.detail
        smtp = FakeSMTP.instances[0]
        assert smtp.started_tls is True
        assert smtp.login_calls == [("alerts@company.com", "secret")]
        from_addr, to_addrs, msg = smtp.sent[0]
        assert from_addr == "alerts@company.com"
        assert to_addrs == ["oncall@co.com", "mlops@co.com"]
        assert "Budget alert" in msg

    def test_not_configured_without_recipients(self):
        svc = NotificationService(config=CONFIGURED, smtp_cls=FakeSMTP)

        result = svc.send({"destination": "email", "email_addresses": []}, "s", "m")

        assert result.status == "not_configured"
        assert not FakeSMTP.instances

    def test_not_configured_without_smtp_host(self):
        svc = NotificationService(config=UNCONFIGURED, smtp_cls=FakeSMTP)

        result = svc.send({"destination": "email", "email_addresses": ["a@co.com"]}, "s", "m")

        assert result.status == "not_configured"
        assert "MLOPS_SMTP_HOST" in result.detail

    def test_smtp_failure_reported_not_raised(self):
        svc = NotificationService(config=CONFIGURED, smtp_cls=FailingSMTP)

        result = svc.send({"destination": "email", "email_addresses": ["a@co.com"]}, "s", "m")

        assert result.status == "failed"
        assert "relay refused" in result.detail


class TestSlack:
    def test_sends_via_webhook(self):
        calls: list = []
        svc = NotificationService(config=CONFIGURED, urlopen=_fake_urlopen(calls=calls))

        result = svc.send({"destination": "slack", "channel_name": "#mlops-alerts"}, "Drift detected", "PSI 0.31")

        assert result.status == "sent"
        assert result.detail == "#mlops-alerts"
        url, payload, timeout = calls[0]
        assert url == CONFIGURED.slack_webhook_url
        assert "Drift detected" in payload["text"]
        assert "PSI 0.31" in payload["text"]
        assert payload["channel"] == "#mlops-alerts"

    def test_not_configured_without_webhook(self):
        svc = NotificationService(config=UNCONFIGURED, urlopen=_fake_urlopen())

        result = svc.send({"destination": "slack", "channel_name": "#x"}, "s", "m")

        assert result.status == "not_configured"
        assert "MLOPS_SLACK_WEBHOOK_URL" in result.detail

    def test_webhook_http_error_reported(self):
        svc = NotificationService(config=CONFIGURED, urlopen=_fake_urlopen(status=500))

        result = svc.send({"destination": "slack", "channel_name": "#x"}, "s", "m")

        assert result.status == "failed"
        assert "500" in result.detail

    def test_webhook_exception_reported_not_raised(self):
        svc = NotificationService(config=CONFIGURED, urlopen=_failing_urlopen())

        result = svc.send({"destination": "slack", "channel_name": "#x"}, "s", "m")

        assert result.status == "failed"
        assert "connection refused" in result.detail


class TestTeams:
    def test_sends_via_webhook(self):
        calls: list = []
        svc = NotificationService(config=CONFIGURED, urlopen=_fake_urlopen(calls=calls))

        result = svc.send({"destination": "teams", "channel_name": "MLOps > General"}, "Revalidation due", "tier_1")

        assert result.status == "sent"
        url, payload, _ = calls[0]
        assert url == CONFIGURED.teams_webhook_url
        assert payload["title"] == "Revalidation due"
        assert payload["text"] == "tier_1"


class TestUnsupportedAndSendAll:
    def test_unsupported_destination(self):
        svc = NotificationService(config=CONFIGURED)

        result = svc.send({"destination": "pager"}, "s", "m")

        assert result.status == "failed"
        assert "unsupported" in result.detail

    def test_send_all_fans_out_to_every_destination(self):
        calls: list = []
        svc = NotificationService(config=CONFIGURED, smtp_cls=FakeSMTP, urlopen=_fake_urlopen(calls=calls))

        results = svc.send_all(
            [
                {"destination": "email", "email_addresses": ["a@co.com"]},
                {"destination": "slack", "channel_name": "#x"},
            ],
            "Alert",
            "body",
        )

        assert [r.status for r in results] == ["sent", "sent"]
        assert FakeSMTP.instances and calls
