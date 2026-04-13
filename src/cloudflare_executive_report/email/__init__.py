"""Email delivery (SMTP) for generated reports."""

from cloudflare_executive_report.email.smtp import (
    apply_email_placeholders,
    send_pdf_report_email,
    validate_email_config_for_send,
)

__all__ = [
    "apply_email_placeholders",
    "send_pdf_report_email",
    "validate_email_config_for_send",
]
