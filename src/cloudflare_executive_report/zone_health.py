"""Zone configuration snapshot via Cloudflare SDK (not cached)."""

from __future__ import annotations

import logging
from typing import Any

from cloudflare import PermissionDeniedError

from cloudflare_executive_report.cf_client import CloudflareClient

log = logging.getLogger(__name__)

SKIPPED = "skipped"
UNAVAILABLE = "unavailable"


def _warn(warnings: list[str], msg: str) -> None:
    warnings.append(msg)
    log.warning("%s", msg)


def _setting_value(
    sdk: Any,
    zone_id: str,
    setting_id: str,
    warnings: list[str],
    *,
    label: str,
) -> str:
    try:
        r = sdk.zones.settings.get(zone_id=zone_id, setting_id=setting_id)
        if r is None:
            _warn(warnings, f"Zone health {label} unavailable (empty response)")
            return UNAVAILABLE
        d = r.model_dump()
        val = d.get("value")
        if val is None and "enabled" in d:
            val = "on" if d.get("enabled") else "off"
        if val is None:
            return UNAVAILABLE
        return str(val)
    except PermissionDeniedError:
        _warn(
            warnings,
            f"Zone health {label} unavailable (permission denied)",
        )
        return UNAVAILABLE
    except Exception as e:
        _warn(warnings, f"Zone health {label} unavailable: {e}")
        return UNAVAILABLE


def _dnssec_status(sdk: Any, zone_id: str, warnings: list[str]) -> str:
    try:
        r = sdk.dns.dnssec.get(zone_id=zone_id)
        if r is None:
            return "disabled"
        st = r.status
        if st is None:
            return UNAVAILABLE
        return str(st)
    except PermissionDeniedError:
        _warn(warnings, "Zone health dnssec_status unavailable (permission denied)")
        return UNAVAILABLE
    except Exception as e:
        _warn(warnings, f"Zone health dnssec_status unavailable: {e}")
        return UNAVAILABLE


def _firewall_rules_active_count(sdk: Any, zone_id: str, warnings: list[str]) -> int:
    try:
        n = 0
        for rule in sdk.firewall.rules.list(zone_id=zone_id):
            if getattr(rule, "paused", None) is True:
                continue
            n += 1
        return n
    except PermissionDeniedError:
        _warn(
            warnings,
            "Zone health security_rules_active unavailable (permission denied)",
        )
        return -1
    except Exception as e:
        _warn(warnings, f"Zone health security_rules_active unavailable: {e}")
        return -1


def fetch_zone_health(
    client: CloudflareClient,
    zone_id: str,
    zone_name: str,
    *,
    skip: bool,
    zone_meta: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if skip:
        warnings.append("Zone health skipped due to --skip-zone-health")
        return {
            "zone_status": SKIPPED,
            "ssl_mode": SKIPPED,
            "always_https": SKIPPED,
            "security_level": SKIPPED,
            "dnssec_status": SKIPPED,
            "ddos_protection": SKIPPED,
            "security_rules_active": SKIPPED,
        }, warnings

    sdk = client.sdk
    out: dict[str, Any] = {}

    if zone_meta is not None:
        st = zone_meta.get("status")
        out["zone_status"] = str(st) if st is not None else UNAVAILABLE
    else:
        try:
            z = sdk.zones.get(zone_id=zone_id)
            if z is None:
                out["zone_status"] = UNAVAILABLE
            else:
                st = getattr(z, "status", None)
                out["zone_status"] = str(st) if st is not None else UNAVAILABLE
        except PermissionDeniedError:
            _warn(warnings, f"Zone health zone_status unavailable for {zone_name}")
            out["zone_status"] = UNAVAILABLE
        except Exception as e:
            _warn(warnings, f"Zone health zone_status unavailable: {e}")
            out["zone_status"] = UNAVAILABLE

    out["ssl_mode"] = _setting_value(sdk, zone_id, "ssl", warnings, label="ssl_mode")
    out["always_https"] = _setting_value(
        sdk, zone_id, "always_use_https", warnings, label="always_https"
    )
    out["security_level"] = _setting_value(
        sdk, zone_id, "security_level", warnings, label="security_level"
    )
    out["dnssec_status"] = _dnssec_status(sdk, zone_id, warnings)
    out["ddos_protection"] = _setting_value(
        sdk, zone_id, "advanced_ddos", warnings, label="ddos_protection"
    )

    cnt = _firewall_rules_active_count(sdk, zone_id, warnings)
    if cnt < 0:
        out["security_rules_active"] = UNAVAILABLE
    else:
        out["security_rules_active"] = cnt

    return out, warnings
