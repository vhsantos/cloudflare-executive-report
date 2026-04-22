"""Send report PDFs over SMTP using ``EmailConfig`` (no globals, raise on failure)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

from cloudflare_executive_report.common.constants import SMTP_TIMEOUT_SECONDS
from cloudflare_executive_report.config import EmailConfig

log = logging.getLogger(__name__)


def apply_email_placeholders(
    template: str,
    *,
    date_str: str,
    period: str,
    zone_count: int,
) -> str:
    """Replace ``{{date}}``, ``{{period}}``, and ``{{zone_count}}`` in a template string."""
    text = template.replace("{{date}}", date_str)
    text = text.replace("{{period}}", period)
    return text.replace("{{zone_count}}", str(zone_count))


def _resolved_from_header(cfg: EmailConfig) -> str:
    raw_from = (cfg.smtp_from or "").strip()
    if raw_from:
        return raw_from
    raw_user = (cfg.smtp_user or "").strip()
    if raw_user:
        return raw_user
    msg = "email.smtp_from or email.smtp_user is required to send mail"
    raise ValueError(msg)


def _normalized_recipient_list(addresses: list[str]) -> list[str]:
    out = [a.strip() for a in addresses if str(a).strip()]
    if not out:
        msg = "email.recipients must list at least one non-empty address"
        raise ValueError(msg)
    return out


def validate_email_config_for_send(cfg: EmailConfig) -> None:
    """Ensure ``EmailConfig`` has the minimum fields needed to send mail.

    Raises:
        ValueError: When configuration is incomplete or contradictory.
    """
    if cfg.smtp_ssl and cfg.smtp_starttls:
        msg = "email.smtp_ssl and email.smtp_starttls cannot both be true"
        raise ValueError(msg)
    host = (cfg.smtp_host or "").strip()
    if not host:
        msg = "email.smtp_host is required to send mail"
        raise ValueError(msg)
    _normalized_recipient_list(list(cfg.recipients))
    _resolved_from_header(cfg)


@contextmanager
def _smtp_session(cfg: EmailConfig) -> Iterator[smtplib.SMTP | smtplib.SMTP_SSL]:
    """Open an SMTP or SMTP_SSL session, STARTTLS when configured, then login if user set."""
    host = (cfg.smtp_host or "").strip()
    if cfg.smtp_ssl:
        client: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(
            host, cfg.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
        )
    else:
        client = smtplib.SMTP(host, cfg.smtp_port, timeout=SMTP_TIMEOUT_SECONDS)
    try:
        client.ehlo()
        if not cfg.smtp_ssl and cfg.smtp_starttls:
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        user = (cfg.smtp_user or "").strip()
        if user:
            client.login(user, cfg.smtp_password or "")
        yield client
    finally:
        try:
            client.quit()
        except Exception as exc:
            log.debug("SMTP quit failed (ignored): %s", exc)


def send_pdf_report_email(
    cfg: EmailConfig,
    *,
    pdf_path: Path,
    period_start: str,
    period_end: str,
    zone_count: int,
    recipients: list[str] | None = None,
) -> None:
    """Connect to SMTP, build message from templates, attach PDF, send to recipients.

    Does not send when ``cfg.enabled`` is false (raises). Caller should gate on ``enabled``.

    Args:
        cfg: Email section of application config.
        pdf_path: Path to the PDF file (attachment uses ``pdf_path.name`` only).
        period_start: Report start date (UTC YYYY-MM-DD).
        period_end: Report end date (UTC YYYY-MM-DD).
        zone_count: Number of zones in the report (for ``{{zone_count}}``).
        recipients: Optional override; defaults to ``cfg.recipients``.

    Raises:
        ValueError: Invalid configuration or missing file.
        OSError: File read errors.
        smtplib.SMTPException: SMTP-level failures.
    """
    if not cfg.enabled:
        error_msg = "email.enabled is false; enable it in config to send mail"
        raise ValueError(error_msg)
    validate_email_config_for_send(cfg)
    path = pdf_path.resolve()
    if not path.is_file():
        error_msg = f"PDF not found: {path}"
        raise ValueError(error_msg)

    raw_to = list(recipients) if recipients is not None else list(cfg.recipients)
    to_list = _normalized_recipient_list(raw_to)
    period = f"{period_start} to {period_end}"
    from_header = _resolved_from_header(cfg)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    subject = apply_email_placeholders(
        cfg.subject, date_str=date_str, period=period, zone_count=zone_count
    )
    body = apply_email_placeholders(
        cfg.body, date_str=date_str, period=period, zone_count=zone_count
    )
    msg = EmailMessage()
    msg["From"] = from_header
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = subject
    msg.set_content(body)

    payload = path.read_bytes()
    msg.add_attachment(
        payload,
        maintype="application",
        subtype="pdf",
        filename=path.name,
    )

    log.info(
        "Sending report PDF by SMTP to %d recipient(s) via %s:%s",
        len(to_list),
        (cfg.smtp_host or "").strip(),
        cfg.smtp_port,
    )
    with _smtp_session(cfg) as server:
        server.send_message(msg)
    log.info("SMTP send finished for %s", path.name)
