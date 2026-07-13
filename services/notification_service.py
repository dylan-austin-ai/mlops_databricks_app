"""Notification Delivery Service — actually sends the alerts everything else
in this app only ever wrote a database row for.

Before this service existed, three separate call sites were alert-shaped but
notification-free: drift/budget alerts only ever inserted into alert_history
(which was read but never written to), a newly-open approval gate never told
the required approver, and HITL SLA-breach escalation only wrote a DB row.
This is the single place that closes all three — ReconciliationService's
alert paths, ApprovalService's gate-open notification, and
HITLReviewService's SLA escalation all route through send()/send_all()
rather than each hand-rolling delivery.

Channels (design tenet 6 — prefer a standard mechanism over inventing one):
  email  stdlib smtplib against a configured SMTP relay
  slack  Incoming Webhook POST (JSON)
  teams  Incoming Webhook POST (Adaptive-Card-shaped JSON)

The webhook URL / SMTP credentials are admin-set config (§16 — secrets live
in config, never in a wizard free-text field); the wizard only ever collects
a channel_name or recipient list per project, never a raw credential.

Graceful degradation (§25 posture, reused here): a channel with no
configured credentials returns status="not_configured" rather than raising —
callers log it and move on, never crash on a missing secret.
"""

from __future__ import annotations

import json
import smtplib
import urllib.request
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Any

from config import AppConfig, get_config

_TIMEOUT_SECONDS = 10


@dataclass
class NotificationResult:
    destination: str
    status: str  # sent | not_configured | failed
    detail: str = ""


class NotificationService:
    def __init__(
        self,
        config: AppConfig | None = None,
        smtp_cls: Any = None,
        urlopen: Any = None,
    ) -> None:
        self._cfg = config or get_config()
        self._smtp_cls = smtp_cls or smtplib.SMTP
        self._urlopen = urlopen or urllib.request.urlopen

    def send(self, destination_config: dict[str, Any], subject: str, message: str) -> NotificationResult:
        """Send to one destination config, e.g. {"destination": "email",
        "email_addresses": [...]} or {"destination": "slack", "channel_name": "#x"}
        — the same shape the wizard's alert_destination_configs already uses."""
        dest = str(destination_config.get("destination") or "")
        try:
            if dest == "email":
                return self._send_email(destination_config, subject, message)
            if dest == "slack":
                return self._send_webhook(dest, self._cfg.slack_webhook_url, destination_config, subject, message)
            if dest == "teams":
                return self._send_webhook(dest, self._cfg.teams_webhook_url, destination_config, subject, message)
            return NotificationResult(dest or "unknown", "failed", f"unsupported destination type: {dest!r}")
        except Exception as exc:
            return NotificationResult(dest, "failed", str(exc))

    def send_all(
        self, destination_configs: list[dict[str, Any]], subject: str, message: str
    ) -> list[NotificationResult]:
        return [self.send(dc, subject, message) for dc in destination_configs]

    # ── email ─────────────────────────────────────────────────────────────

    def _send_email(self, destination_config: dict[str, Any], subject: str, message: str) -> NotificationResult:
        recipients: list[str] = destination_config.get("email_addresses") or []
        if not recipients:
            return NotificationResult("email", "not_configured", "no recipient addresses on this project")
        if not (self._cfg.smtp_host and self._cfg.smtp_from_email):
            return NotificationResult("email", "not_configured", "MLOPS_SMTP_HOST/MLOPS_SMTP_FROM_EMAIL not set")

        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = self._cfg.smtp_from_email
        msg["To"] = ", ".join(recipients)

        with self._smtp_cls(self._cfg.smtp_host, self._cfg.smtp_port, timeout=_TIMEOUT_SECONDS) as smtp:
            smtp.starttls()
            if self._cfg.smtp_user:
                smtp.login(self._cfg.smtp_user, self._cfg.smtp_password)
            smtp.sendmail(self._cfg.smtp_from_email, recipients, msg.as_string())
        return NotificationResult("email", "sent", f"{len(recipients)} recipient(s)")

    # ── webhooks (slack/teams) ───────────────────────────────────────────

    def _send_webhook(
        self, dest_name: str, webhook_url: str, destination_config: dict[str, Any], subject: str, message: str
    ) -> NotificationResult:
        if not webhook_url:
            return NotificationResult(dest_name, "not_configured", f"MLOPS_{dest_name.upper()}_WEBHOOK_URL not set")

        # Incoming webhooks are typically bound to one channel at creation
        # time; channel_name travels in the payload on a best-effort basis
        # (Slack's classic webhooks honor it, newer app-based ones ignore it).
        payload = (
            {"text": f"*{subject}*\n{message}", "channel": destination_config.get("channel_name")}
            if dest_name == "slack"
            else {"title": subject, "text": message}
        )
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", 200)
            if status >= 300:
                return NotificationResult(dest_name, "failed", f"webhook returned HTTP {status}")
        return NotificationResult(dest_name, "sent", str(destination_config.get("channel_name") or ""))
