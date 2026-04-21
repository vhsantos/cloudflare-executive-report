"""Token permission validation runner.

Executes one lightweight API probe per permission and returns structured
PermissionResult objects. Callers (CLI, tests) consume these directly.

Stream-awareness: each result carries a `used_by` tuple listing which registered
fetcher stream IDs (and the "zone_health" feature) depend on that permission.
This lets the CLI show a "Used By" column without any coupling to display logic here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cloudflare import APIStatusError, AuthenticationError, PermissionDeniedError

from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
    CloudflareRateLimitError,
)

try:
    from cloudflare_executive_report.fetchers.registry import FETCHER_REGISTRY
except ImportError:
    # Fallback for testing environments where registry might be isolated
    FETCHER_REGISTRY = {}


from cloudflare_executive_report.validate.consts import (
    ACCOUNT_AUDIT_READ,
    ACCOUNT_SETTINGS_READ,
    ALL_PERMISSIONS,
    ZONE_ANALYTICS_READ,
    ZONE_DNS_READ,
    ZONE_FIREWALL_READ,
    ZONE_HEALTH_PERMISSIONS,
    ZONE_READ,
    ZONE_SETTINGS_READ,
    ZONE_SSL_READ,
    ZONE_WAF_READ,
)
from cloudflare_executive_report.validate.probes import (
    probe_account_audit_read,
    probe_account_settings_read,
    probe_zone_analytics_read,
    probe_zone_dns_read,
    probe_zone_dns_write,
    probe_zone_firewall_read,
    probe_zone_read,
    probe_zone_settings_read,
    probe_zone_ssl_read,
    probe_zone_waf_read,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_OK = "OK"
STATUS_MISSING = "MISSING"
STATUS_RATE_LIMITED = "RATE_LIMITED"
STATUS_SKIPPED = "SKIPPED"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_ERROR = "ERROR"
STATUS_UNWANTED_WRITE = "UNWANTED_WRITE"


@dataclass(frozen=True)
class ValidationReport:
    """Full report of the validation run.

    Acts like a list of PermissionResult for backward compatibility.
    """

    permissions: list[PermissionResult]
    write_access_detected: bool = False

    def __iter__(self):
        return iter(self.permissions)

    def __len__(self) -> int:
        return len(self.permissions)

    def __getitem__(self, index: int | slice) -> Any:
        return self.permissions[index]


# ---------------------------------------------------------------------------
# Probe registry
# ---------------------------------------------------------------------------

# Maps permission name -> probe callable.
# Probe signature: (client, target_id: str) -> Any
# where target_id is zone_id for zone permissions, account_id for account permissions.
_PROBE_MAP: dict[str, Callable[[CloudflareClient, str], Any]] = {
    ZONE_READ: probe_zone_read,
    ZONE_ANALYTICS_READ: probe_zone_analytics_read,
    ZONE_DNS_READ: probe_zone_dns_read,
    ZONE_SSL_READ: probe_zone_ssl_read,
    ZONE_SETTINGS_READ: probe_zone_settings_read,
    ZONE_FIREWALL_READ: probe_zone_firewall_read,
    ZONE_WAF_READ: probe_zone_waf_read,
    ACCOUNT_AUDIT_READ: probe_account_audit_read,
    ACCOUNT_SETTINGS_READ: probe_account_settings_read,
}


def _validate_probe_coverage() -> None:
    """Ensure every permission in ALL_PERMISSIONS has a probe implementation."""
    missing = [p for p in ALL_PERMISSIONS if p not in _PROBE_MAP]
    if missing:
        # This is a developer error, not a runtime failure.
        log.warning("Permissions missing probe implementations: %s", missing)


# Run coverage check at module load time
_validate_probe_coverage()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PermissionResult:
    """Outcome of probing a single Cloudflare permission."""

    permission: str
    status: str
    message: str = ""
    is_account_scoped: bool = False
    used_by: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """Return True when the permission is confirmed available."""
        return self.status == STATUS_OK

    @property
    def skipped(self) -> bool:
        """Return True when the probe was not run (missing target)."""
        return self.status == STATUS_SKIPPED


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_account_permission(permission: str) -> bool:
    """Return True for account-scoped permissions."""
    return permission.startswith("Account")


def _resolve_account_id(client: CloudflareClient) -> str | None:
    """Return the first accessible account ID for this token, or None.

    Uses get_first_account_id() which breaks SDK iteration after the first
    result, making exactly one HTTP request regardless of how many accounts
    the token has access to.
    """
    try:
        return client.get_first_account_id()
    except (CloudflareAuthError, CloudflareAPIError) as exc:
        log.debug("Could not resolve account ID: %s", exc)
    return None


def _build_used_by_map(permissions: tuple[str, ...] | list[str]) -> dict[str, list[str]]:
    """Build a permission -> [consumer_name, ...] map from the fetcher registry.

    Reads each registered fetcher's optional `required_permissions` ClassVar.
    Also includes "zone_health" as a consumer for ZONE_HEALTH_PERMISSIONS.
    Falls back to an empty list when a fetcher has no declared permissions.
    """
    result: dict[str, list[str]] = {p: [] for p in permissions}

    for stream_id, fetcher in FETCHER_REGISTRY.items():
        fetcher_perms: tuple[str, ...] = getattr(fetcher, "required_permissions", ())
        for perm in fetcher_perms:
            if perm in result:
                result[perm].append(stream_id)

    for perm in ZONE_HEALTH_PERMISSIONS:
        if perm in result and "zone_health" not in result[perm]:
            result[perm].append("zone_health")

    return result


def _run_probe(
    client: CloudflareClient,
    permission: str,
    target_id: str,
    used_by: tuple[str, ...],
) -> PermissionResult:
    """Execute the probe for a single permission and return a result."""
    probe = _PROBE_MAP.get(permission)
    if probe is None:
        return PermissionResult(
            permission=permission,
            status=STATUS_ERROR,
            message=f"No probe implemented for '{permission}'",
            is_account_scoped=_is_account_permission(permission),
            used_by=used_by,
        )

    is_account = _is_account_permission(permission)
    try:
        probe(client, target_id)
        return PermissionResult(
            permission=permission,
            status=STATUS_OK,
            is_account_scoped=is_account,
            used_by=used_by,
        )
    except CloudflareRateLimitError:
        return PermissionResult(
            permission=permission,
            status=STATUS_RATE_LIMITED,
            message="Rate limited - retry later",
            is_account_scoped=is_account,
            used_by=used_by,
        )
    except (CloudflareAuthError, AuthenticationError, PermissionDeniedError):
        return PermissionResult(
            permission=permission,
            status=STATUS_MISSING,
            message="Permission denied (403)",
            is_account_scoped=is_account,
            used_by=used_by,
        )
    except CloudflareAPIError as exc:
        msg = str(exc)
        if "403" in msg or "permission" in msg.lower():
            return PermissionResult(
                permission=permission,
                status=STATUS_MISSING,
                message="Permission denied (403)",
                is_account_scoped=is_account,
                used_by=used_by,
            )
        if "404" in msg:
            return PermissionResult(
                permission=permission,
                status=STATUS_NOT_FOUND,
                message="Resource not found (404)",
                is_account_scoped=is_account,
                used_by=used_by,
            )
        return PermissionResult(
            permission=permission,
            status=STATUS_ERROR,
            message=msg[:120],
            is_account_scoped=is_account,
            used_by=used_by,
        )
    except Exception as exc:  # noqa: BLE001
        # Broad catch is intentional: we must never let an unexpected probe
        # failure crash the entire validation run. We log and surface as ERROR.
        log.debug("Unexpected error probing '%s': %s", permission, exc)
        return PermissionResult(
            permission=permission,
            status=STATUS_ERROR,
            message=str(exc)[:120],
            is_account_scoped=is_account,
            used_by=used_by,
        )


def _check_write_permissions(client: CloudflareClient, zone_id: str) -> bool:
    """Return True if write access is detected on the zone.

    Attempts a DNS create call with an invalid IP.
    403 Forbidden -> False (Correctly read-only)
    400/422/Validation error -> True (Unwanted write access detected)
    """
    try:
        probe_zone_dns_write(client, zone_id)
        # If it somehow succeeds, it's definitely write access
        return True
    except (CloudflareAuthError, AuthenticationError, PermissionDeniedError):
        return False
    except (APIStatusError, CloudflareAPIError) as exc:
        # SDK error or our mapped wrapper: check status code
        status = None
        if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
            status = exc.response.status_code
        elif hasattr(exc, "status_code"):
            status = exc.status_code

        if status in (400, 422):
            return True
        if status == 403:
            return False

        # Fallback to string matching
        msg = str(exc).lower()
        if "400" in msg or "422" in msg or "validation" in msg or "invalid" in msg:
            return True
        if "403" in msg:
            return False

        return False
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_token_permissions(
    client: CloudflareClient,
    zone_id: str | None,
    *,
    permissions: tuple[str, ...] | list[str] = ALL_PERMISSIONS,
    enabled_streams: list[str] | None = None,
    probe_delay_seconds: float = 0.3,
) -> ValidationReport:
    """Validate each permission in *permissions* by running its probe.

    Args:
        client: Authenticated Cloudflare client.
        zone_id: Zone ID to use for zone-scoped probes. When None, all
            zone-scoped permissions are returned with SKIPPED status.
        permissions: Ordered sequence of permission names to validate.
            Defaults to ALL_PERMISSIONS from consts.
        enabled_streams: Optional list of active stream IDs.
            - None or []: Validate ALL registered permissions.
            - ['dns']: Validate permissions for dns + zone_health (if zone_id set).
        probe_delay_seconds: Seconds to sleep between probes to avoid
            triggering rate limits.

    Returns:
        ValidationReport containing the list of results and write access status.
    """
    used_by_map = _build_used_by_map(permissions)

    results: list[PermissionResult] = []
    probes_executed = 0

    # Lazy account resolution - only if we encounter a required account permission
    account_id: str | None = None
    account_id_fetched = False

    for permission in permissions:
        # Determine if this permission is actually needed for the current run
        used_by_raw = used_by_map.get(permission, [])

        if enabled_streams:
            # We have a specific subset of enabled streams.
            active_streams = set(enabled_streams)
            # Always include zone_health if we have a zone to probe
            if zone_id:
                active_streams.add("zone_health")

            used_by_filtered = [u for u in used_by_raw if u in active_streams]
        else:
            # If enabled_streams is None or [], we treat all registered streams as active.
            used_by_filtered = used_by_raw

        # If the permission isn't needed by any enabled module, skip it entirely.
        if not used_by_filtered:
            results.append(
                PermissionResult(
                    permission=permission,
                    status=STATUS_SKIPPED,
                    message="Not required by any enabled module",
                    is_account_scoped=_is_account_permission(permission),
                    used_by=(),
                )
            )
            continue

        used_by = tuple(used_by_filtered)

        # Rate limit delay: only if we actually performed a probe previously
        if probes_executed > 0:
            time.sleep(probe_delay_seconds)

        is_account = _is_account_permission(permission)

        if is_account:
            if not account_id_fetched:
                account_id = _resolve_account_id(client)
                account_id_fetched = True

            if not account_id:
                results.append(
                    PermissionResult(
                        permission=permission,
                        status=STATUS_SKIPPED,
                        message="No accessible account found for this token",
                        is_account_scoped=True,
                        used_by=used_by,
                    )
                )
                continue

            results.append(_run_probe(client, permission, account_id, used_by))
            probes_executed += 1

        else:
            if not zone_id:
                results.append(
                    PermissionResult(
                        permission=permission,
                        status=STATUS_SKIPPED,
                        message="No zone configured - pass --zone or add zones to config",
                        is_account_scoped=False,
                        used_by=used_by,
                    )
                )
                continue

            results.append(_run_probe(client, permission, zone_id, used_by))
            probes_executed += 1

    # Optional: Check for unwanted write permissions if Zone Read was successful
    write_access_detected = False
    if zone_id:
        zone_read_ok = any(r.permission == ZONE_READ and r.ok for r in results)
        if zone_read_ok:
            write_access_detected = _check_write_permissions(client, zone_id)

    return ValidationReport(
        permissions=results,
        write_access_detected=write_access_detected,
    )
