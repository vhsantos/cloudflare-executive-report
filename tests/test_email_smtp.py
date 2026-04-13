"""Tests for SMTP helpers and email templates."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cloudflare_executive_report.config import DEFAULT_EMAIL_BODY_TEMPLATE, EmailConfig
from cloudflare_executive_report.email.smtp import (
    apply_email_placeholders,
    send_pdf_report_email,
    validate_email_config_for_send,
)


def test_apply_email_placeholders() -> None:
    out = apply_email_placeholders(
        "D={{date}} P={{period}} Z={{zone_count}}",
        date_str="2026-04-13",
        period="2026-04-01 to 2026-04-10",
        zone_count=3,
    )
    assert out == "D=2026-04-13 P=2026-04-01 to 2026-04-10 Z=3"


def test_validate_email_config_rejects_ssl_and_starttls() -> None:
    cfg = EmailConfig(
        smtp_host="smtp.example.com",
        smtp_ssl=True,
        smtp_starttls=True,
        recipients=["a@b.com"],
        smtp_user="u@example.com",
    )
    with pytest.raises(ValueError, match="cannot both be true"):
        validate_email_config_for_send(cfg)


def test_validate_email_config_requires_host() -> None:
    cfg = EmailConfig(
        smtp_host="",
        recipients=["a@b.com"],
        smtp_user="u@example.com",
    )
    with pytest.raises(ValueError, match="smtp_host"):
        validate_email_config_for_send(cfg)


def test_validate_email_config_requires_recipients() -> None:
    cfg = EmailConfig(smtp_host="h", smtp_user="u@example.com", recipients=[])
    with pytest.raises(ValueError, match="recipients"):
        validate_email_config_for_send(cfg)


def test_send_pdf_report_email_disabled_raises() -> None:
    cfg = EmailConfig(enabled=False, smtp_host="h", recipients=["a@b.com"], smtp_user="u@x.com")
    with pytest.raises(ValueError, match="enabled"):
        send_pdf_report_email(
            cfg,
            pdf_path=Path("nope.pdf"),
            period_start="2026-04-01",
            period_end="2026-04-02",
            zone_count=1,
        )


def test_send_pdf_report_email_missing_file_raises(tmp_path: Path) -> None:
    cfg = EmailConfig(
        enabled=True,
        smtp_host="localhost",
        recipients=["a@b.com"],
        smtp_user="u@example.com",
    )
    pdf = tmp_path / "missing.pdf"
    with pytest.raises(ValueError, match="not found"):
        send_pdf_report_email(
            cfg,
            pdf_path=pdf,
            period_start="2026-04-01",
            period_end="2026-04-02",
            zone_count=1,
        )


def test_send_pdf_report_email_uses_attachment_basename_only(tmp_path: Path) -> None:
    nested = tmp_path / "sub"
    nested.mkdir()
    pdf = nested / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")

    cfg = EmailConfig(
        enabled=True,
        smtp_host="localhost",
        smtp_port=25,
        smtp_ssl=False,
        smtp_starttls=False,
        recipients=["dest@example.com"],
        smtp_user="from@example.com",
        subject="R {{date}}",
        body=DEFAULT_EMAIL_BODY_TEMPLATE,
    )

    mock_smtp = MagicMock()

    with patch(
        "cloudflare_executive_report.email.smtp._smtp_session",
        return_value=nullcontext(mock_smtp),
    ):
        send_pdf_report_email(
            cfg,
            pdf_path=pdf,
            period_start="2026-04-01",
            period_end="2026-04-02",
            zone_count=2,
        )

    mock_smtp.send_message.assert_called_once()
    call_arg = mock_smtp.send_message.call_args[0][0]
    attachments = list(call_arg.iter_attachments())
    assert len(attachments) == 1
    part = attachments[0]
    assert part.get_filename() == "report.pdf"
