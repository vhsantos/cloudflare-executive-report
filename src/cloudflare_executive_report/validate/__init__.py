"""Token permission validation for cf-report."""

from cloudflare_executive_report.validate.runner import PermissionResult, validate_token_permissions

__all__ = [
    "PermissionResult",
    "validate_token_permissions",
]
