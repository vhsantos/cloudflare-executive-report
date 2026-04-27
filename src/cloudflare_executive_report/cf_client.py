"""Cloudflare: official SDK for REST, httpx only for Analytics GraphQL."""

from __future__ import annotations

import logging
import time
from typing import Any, cast

import httpx
from cloudflare import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    Cloudflare,
    CloudflareError,
    PermissionDeniedError,
)
from cloudflare import RateLimitError as SDKRateLimitError

log = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"

BACKOFF_429 = (1, 2, 4, 8, 16, 32)
MAX_429_RETRIES = 3
NETWORK_RETRIES = 3
NETWORK_BACKOFF = (1.0, 2.0, 4.0)

AUTH_MESSAGE = "Invalid or missing permissions. Required: Zone:Read, Analytics:Read"


class CloudflareAuthError(Exception):
    pass


class CloudflareRateLimitError(Exception):
    def __init__(self, message: str, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class CloudflareAPIError(Exception):
    pass


def _truncate(s: str, max_len: int = 500) -> str:
    s = s.replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


def _map_sdk_exception(exc: Exception) -> None:
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        raise CloudflareAuthError(AUTH_MESSAGE) from exc
    if isinstance(exc, SDKRateLimitError):
        ra = None
        if getattr(exc, "response", None) is not None:
            ra = exc.response.headers.get("retry-after")
        raise CloudflareRateLimitError(str(exc), retry_after=ra) from exc
    if isinstance(exc, (APIConnectionError, APITimeoutError, APIStatusError, CloudflareError)):
        raise CloudflareAPIError(str(exc)) from exc
    raise exc


class CloudflareClient:
    """
    REST via official Cloudflare Python SDK (pagination, retries, rate limits).
    GraphQL Analytics via direct httpx POST (SDK has no GraphQL support).
    """

    def __init__(
        self,
        api_token: str,
        *,
        timeout: float = 60.0,
        verbose: bool = False,
    ) -> None:
        self._token = api_token
        self._timeout = timeout
        self._verbose = verbose
        self._sdk = Cloudflare(api_token=api_token, timeout=timeout)
        self._http = httpx.Client(
            timeout=httpx.Timeout(timeout),
            headers={"Authorization": f"Bearer {api_token}"},
        )

    def close(self) -> None:
        self._sdk.close()
        self._http.close()

    def __enter__(self) -> CloudflareClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def sdk(self) -> Cloudflare:
        """Official SDK client (REST). GraphQL remains on `graphql` / `graphql_query`."""
        return self._sdk

    def _log_graphql_response(self, resp: httpx.Response, label: str, elapsed: float) -> None:
        if not self._verbose:
            return
        ray = resp.headers.get("cf-ray") or resp.headers.get("CF-Ray")
        rid = resp.headers.get("cf-request-id") or resp.headers.get("CF-Request-ID")
        parts = [f"{label} {resp.status_code} in {elapsed * 1000:.0f}ms"]
        if ray:
            parts.append(f"cf-ray={ray}")
        if rid:
            parts.append(f"cf-request-id={rid}")
        log.debug(" ".join(parts))
        if resp.status_code >= 400:
            log.debug("body: %s", _truncate(resp.text))

    def list_zones(self) -> list[dict[str, Any]]:
        """All zones visible to the token (SDK auto-pagination)."""
        if self._verbose:
            log.debug("SDK zones.list()")
        try:
            return [z.model_dump() for z in self._sdk.zones.list()]
        except Exception as e:
            _map_sdk_exception(e)
            raise

    def list_accounts(self) -> list[dict[str, Any]]:
        """All accounts accessible to the token (SDK auto-pagination)."""
        if self._verbose:
            log.debug("SDK accounts.list()")
        try:
            return [a.model_dump() for a in self._sdk.accounts.list()]
        except Exception as e:
            _map_sdk_exception(e)
            raise

    def get_first_account_id(self) -> str | None:
        """Return the first accessible account ID using a single API request.

        Breaks out of the SDK iterator after the first item so that auto-pagination
        never fetches page 2. Use this instead of list_accounts() when only an
        account ID is needed as a probe target.
        """
        if self._verbose:
            log.debug("SDK accounts.list() - first item only")
        try:
            for account in self._sdk.accounts.list():
                account_id = str(account.id or "").strip()
                return account_id or None
        except Exception as e:
            _map_sdk_exception(e)
            raise
        return None

    def get_zone(self, zone_id: str) -> dict[str, Any]:
        if self._verbose:
            log.debug("SDK zones.get zone_id=%s", zone_id)
        try:
            z = self._sdk.zones.get(zone_id=zone_id)
        except Exception as e:
            _map_sdk_exception(e)
            raise
        if z is None:
            raise CloudflareAPIError(f"Zone not found: {zone_id}")
        return z.model_dump()

    def find_zone_by_name(self, name: str) -> dict[str, Any] | None:
        if self._verbose:
            log.debug("SDK zones.list name=%s", name.strip())
        try:
            for z in self._sdk.zones.list(name=name.strip()):
                return z.model_dump()
        except Exception as e:
            _map_sdk_exception(e)
            raise
        return None

    def list_account_audit_logs(
        self, account_id: str, *, since: str, before: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List account audit logs via SDK."""
        if self._verbose:
            log.debug(
                "SDK audit_logs.list account_id=%s since=%s before=%s limit=%s",
                account_id,
                since,
                before,
                limit,
            )
        try:
            page = self._sdk.audit_logs.list(
                account_id=account_id,
                since=since,
                before=before,
                per_page=limit,
            )
            return [item.model_dump() for item in page]
        except Exception as e:
            _map_sdk_exception(e)
            raise

    def list_dns_records(
        self, zone_id: str, *, per_page: int = 100, record_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List all DNS records for a zone via SDK pagination."""
        if self._verbose:
            log.debug(
                "SDK dns.records.list zone_id=%s per_page=%s type=%s",
                zone_id,
                per_page,
                record_type,
            )
        try:
            kwargs: dict[str, Any] = {"zone_id": zone_id, "per_page": per_page}
            if record_type:
                kwargs["type"] = record_type
            page = self._sdk.dns.records.list(**kwargs)
            return [item.model_dump() for item in page]
        except Exception as e:
            _map_sdk_exception(e)
            raise

    def list_zone_certificate_packs(self, zone_id: str) -> list[dict[str, Any]]:
        """List zone certificate packs via SDK."""
        if self._verbose:
            log.debug("SDK ssl.certificate_packs.list zone_id=%s", zone_id)
        try:
            page = self._sdk.ssl.certificate_packs.list(zone_id=zone_id, status="all")
            return cast(list[dict[str, Any]], page.result)  # Already a list
        except Exception as e:
            _map_sdk_exception(e)
            raise

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """POST Analytics GraphQL only (manual HTTP; not available on SDK)."""
        return self.graphql_query(query, variables)

    def graphql_query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a GraphQL query against the Cloudflare Analytics API.

        Handles retries for network errors and 429 rate limits.
        """
        payload = {"query": query, "variables": variables}
        last_network: Exception | None = None
        for net_attempt in range(NETWORK_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                resp = self._http.post(GRAPHQL_URL, json=payload)
                self._log_graphql_response(resp, "GraphQL", time.perf_counter() - t0)
                if resp.status_code in (401, 403):
                    raise CloudflareAuthError(AUTH_MESSAGE)
                if resp.status_code == 429:
                    return self._graphql_after_429(payload, resp)
                resp.raise_for_status()
                body = resp.json()
            except CloudflareAuthError:
                raise
            except CloudflareRateLimitError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_network = e
                if net_attempt < NETWORK_RETRIES:
                    time.sleep(NETWORK_BACKOFF[min(net_attempt, len(NETWORK_BACKOFF) - 1)])
                    continue
                raise CloudflareAPIError(f"Network error after retries: {e}") from e
            except httpx.HTTPStatusError as e:
                # Retry 5xx server errors like 503 "too many queries"
                if e.response.status_code in (500, 502, 503, 504) and net_attempt < NETWORK_RETRIES:
                    time.sleep(NETWORK_BACKOFF[min(net_attempt, len(NETWORK_BACKOFF) - 1)])
                    continue

                # Include CF-Ray in all HTTP errors
                ray_id = e.response.headers.get("cf-ray", "unknown")
                msg = f"HTTP {e.response.status_code}: "
                msg += f"{_truncate(e.response.text)} (cf-ray: {ray_id})"

                raise CloudflareAPIError(msg) from e

            errs = body.get("errors")
            if errs:
                msg = errs[0].get("message", str(errs))
                low = msg.lower()

                # Parsing / Validation
                if "iso8601" in low or "datetime" in low:
                    raise CloudflareAPIError(
                        f"Date format error (use YYYY-MM-DD for filters): {msg}"
                    ) from None

                if (
                    "not authorized" in low
                    or "unauthorized" in low
                    or "permission" in low
                    or "does not have access" in low
                ):
                    raise CloudflareAuthError(f"Permission denied: {msg}") from None
                raise CloudflareAPIError(msg)
            return cast(dict[str, Any], body["data"])
        raise CloudflareAPIError(str(last_network))

    def _graphql_after_429(self, payload: dict[str, Any], first: httpx.Response) -> dict[str, Any]:
        ra = first.headers.get("retry-after")
        for i in range(MAX_429_RETRIES):
            sleep_s = BACKOFF_429[min(i, len(BACKOFF_429) - 1)]
            log.debug(
                "429 GraphQL; sleeping %ss (retry %s/%s)",
                sleep_s,
                i + 1,
                MAX_429_RETRIES,
            )
            time.sleep(sleep_s)
            t0 = time.perf_counter()
            resp = self._http.post(GRAPHQL_URL, json=payload)
            self._log_graphql_response(resp, "GraphQL retry", time.perf_counter() - t0)
            if resp.status_code in (401, 403):
                raise CloudflareAuthError(AUTH_MESSAGE)
            if resp.status_code == 429:
                continue
            resp.raise_for_status()
            body = resp.json()
            errs = body.get("errors")
            if errs:
                msg = errs[0].get("message", str(errs))
                low = msg.lower()
                if "iso8601" in low:
                    raise CloudflareAPIError(
                        f"Date format error (use YYYY-MM-DDT00:00:00Z): {msg}"
                    ) from None
                raise CloudflareAPIError(msg)
            return cast(dict[str, Any], body["data"])
        raise CloudflareRateLimitError(
            "Rate limit exceeded after retries",
            retry_after=ra,
        )
