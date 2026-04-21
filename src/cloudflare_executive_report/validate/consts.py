"""Canonical Cloudflare permission name constants and logical groupings.

These strings match Cloudflare's human-readable permission names exactly.
They are used as keys in the probe map and for display in validation output.

To add a new permission:
  1. Add a constant here.
  2. Add a probe in probes.py.
  3. Add it to ALL_PERMISSIONS (and any relevant group tuple).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Zone-scoped permissions
# ---------------------------------------------------------------------------

ZONE_READ = "Zone > Zone Read"
ZONE_ANALYTICS_READ = "Zone > Analytics Read"
ZONE_DNS_READ = "Zone > DNS Read"
ZONE_SSL_READ = "Zone > SSL and Certificates Read"
ZONE_SETTINGS_READ = "Zone > Zone Settings Read"
ZONE_FIREWALL_READ = "Zone > Firewall Services Read"
ZONE_WAF_READ = "Zone > WAF Read"

# ---------------------------------------------------------------------------
# Account-scoped permissions
# ---------------------------------------------------------------------------

ACCOUNT_AUDIT_READ = "Account > Access: Audit Logs Read"
ACCOUNT_SETTINGS_READ = "Account > Account Settings Read"

# ---------------------------------------------------------------------------
# Logical groupings (used by runner and fetchers)
# ---------------------------------------------------------------------------

# Needed to read zone configuration / security posture (zone_health feature).
ZONE_HEALTH_PERMISSIONS: tuple[str, ...] = (
    ZONE_READ,
    ZONE_SETTINGS_READ,
    ZONE_DNS_READ,
    ZONE_FIREWALL_READ,
    ZONE_WAF_READ,
    ZONE_SSL_READ,
)

# Needed by all GraphQL analytics stream fetchers.
ANALYTICS_PERMISSIONS: tuple[str, ...] = (
    ZONE_READ,
    ZONE_ANALYTICS_READ,
)

# Full set - every permission the tool may ever need.
# Insertion order controls the display order in `cf-report validate`.
ALL_PERMISSIONS: tuple[str, ...] = (
    ZONE_READ,
    ZONE_ANALYTICS_READ,
    ZONE_DNS_READ,
    ZONE_SSL_READ,
    ZONE_SETTINGS_READ,
    ZONE_FIREWALL_READ,
    ZONE_WAF_READ,
    ACCOUNT_AUDIT_READ,
    ACCOUNT_SETTINGS_READ,
)
