"""Zone configuration snapshot via Cloudflare SDK (not cached)."""

from __future__ import annotations

import logging
from typing import Any

from cloudflare import APIStatusError, PermissionDeniedError

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


def _is_missing_phase_entrypoint_error(exc: Exception) -> bool:
    """True when zone phase has no entrypoint ruleset configured yet."""
    if isinstance(exc, APIStatusError):
        if getattr(exc, "status_code", None) != 404:
            return False
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            for err in body.get("errors", []):
                if str(err.get("code")) == "10003":
                    return True
        msg = str(exc)
        return "10003" in msg
    return False


def _ruleset_rules_active_count(sdk: Any, zone_id: str, warnings: list[str]) -> int:
    """
    Count enabled rules from Ruleset Engine zone entrypoint phases.

    Replaces deprecated Firewall Rules API usage.
    """
    phases = (
        "http_request_firewall_custom",
        "http_ratelimit",
    )
    total = 0
    fetched_any = False
    handled_missing_phase = False
    for phase in phases:
        try:
            entry = sdk.rulesets.phases.get(phase, zone_id=zone_id)
            fetched_any = True
            rules = getattr(entry, "rules", None) or []
            for rule in rules:
                enabled = getattr(rule, "enabled", None)
                if enabled is None:
                    dumped = rule.model_dump() if hasattr(rule, "model_dump") else {}
                    enabled = bool(dumped.get("enabled"))
                if enabled is False:
                    continue
                total += 1
        except PermissionDeniedError:
            _warn(
                warnings,
                "Zone health security_rules_active unavailable (permission denied)",
            )
            return -1
        except Exception as e:
            if _is_missing_phase_entrypoint_error(e):
                handled_missing_phase = True
                continue
            # Missing phase/entrypoint or unavailable product should not fail whole health snapshot.
            _warn(warnings, f"Zone health security_rules_active phase {phase} unavailable: {e}")
            continue
    if not fetched_any and not handled_missing_phase:
        return -1
    return total


def _coerce_bool(v: Any) -> bool | None:
    """Return bool or None when value is absent or unusable."""
    if v is None:
        return None
    return bool(v)


def _coerce_int(v: Any) -> int | None:
    """Return int or None when value is absent or unusable."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _normalize_sts_dict(sts: Any) -> dict[str, Any]:
    """Normalize strict_transport_security payload to a flat snapshot dict."""
    if sts is None:
        return {
            "available": True,
            "enabled": False,
            "max_age": None,
            "include_subdomains": None,
            "preload": None,
        }
    if hasattr(sts, "model_dump"):
        sts = sts.model_dump()
    if not isinstance(sts, dict):
        return {
            "available": False,
            "enabled": None,
            "max_age": None,
            "include_subdomains": None,
            "preload": None,
        }
    return {
        "available": True,
        "enabled": _coerce_bool(sts.get("enabled")),
        "max_age": _coerce_int(sts.get("max_age")),
        "include_subdomains": _coerce_bool(sts.get("include_subdomains")),
        "preload": _coerce_bool(sts.get("preload")),
    }


def _hsts_security_header_snapshot(
    sdk: Any,
    zone_id: str,
    warnings: list[str],
) -> dict[str, Any]:
    """Read HSTS fields from zone setting ``security_header`` (Cloudflare API)."""
    try:
        r = sdk.zones.settings.get(zone_id=zone_id, setting_id="security_header")
    except PermissionDeniedError:
        _warn(
            warnings,
            "Zone health security_header (HSTS) unavailable (permission denied)",
        )
        return {"available": False, "skipped": False}
    except Exception as e:
        _warn(warnings, f"Zone health security_header (HSTS) unavailable: {e}")
        return {"available": False, "skipped": False}
    if r is None:
        _warn(warnings, "Zone health security_header (HSTS) empty response")
        return {"available": False, "skipped": False}
    dumped = r.model_dump()
    val = dumped.get("value")
    if hasattr(val, "model_dump"):
        val = val.model_dump()
    if val is None:
        return {"available": False, "skipped": False}
    if not isinstance(val, dict):
        _warn(warnings, "Zone health security_header (HSTS) value has unexpected shape")
        return {"available": False, "skipped": False}
    sts = val.get("strict_transport_security")
    return _normalize_sts_dict(sts)


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
            "min_tls_version": SKIPPED,
            "hsts": {"available": False, "skipped": True},
            "tls_1_3": SKIPPED,
            "browser_check": SKIPPED,
            "email_obfuscation": SKIPPED,
            "opportunistic_encryption": SKIPPED,
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
    out["min_tls_version"] = _setting_value(
        sdk, zone_id, "min_tls_version", warnings, label="min_tls_version"
    )
    out["tls_1_3"] = _setting_value(sdk, zone_id, "tls_1_3", warnings, label="tls_1_3")
    out["browser_check"] = _setting_value(
        sdk, zone_id, "browser_check", warnings, label="browser_check"
    )
    out["email_obfuscation"] = _setting_value(
        sdk, zone_id, "email_obfuscation", warnings, label="email_obfuscation"
    )
    out["opportunistic_encryption"] = _setting_value(
        sdk,
        zone_id,
        "opportunistic_encryption",
        warnings,
        label="opportunistic_encryption",
    )
    out["security_level"] = _setting_value(
        sdk, zone_id, "security_level", warnings, label="security_level"
    )
    out["dnssec_status"] = _dnssec_status(sdk, zone_id, warnings)
    out["ddos_protection"] = _setting_value(
        sdk, zone_id, "advanced_ddos", warnings, label="ddos_protection"
    )

    cnt = _ruleset_rules_active_count(sdk, zone_id, warnings)
    if cnt < 0:
        out["security_rules_active"] = UNAVAILABLE
    else:
        out["security_rules_active"] = cnt

    out["hsts"] = _hsts_security_header_snapshot(sdk, zone_id, warnings)

    return out, warnings
