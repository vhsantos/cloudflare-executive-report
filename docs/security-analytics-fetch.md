
# Security stream: GraphQL and cache shape

Daily **`security.json`** uses **`httpRequestsAdaptiveGroups`** only (eyeball matrix + mitigating filtered groups). No **`firewallEventsAdaptive`** pagination.

## Cached fields (per UTC day)

| Area              | Fields                                                                                                                                                                                                                                                                |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Eyeball split     | `http_requests_sampled`, `mitigated_count`, `served_cf_count`, `served_origin_count` (matrix fold: mitigated = block/challenge/js_challenge/managed_challenge; pass → origin if `cacheStatus` ∈ dynamic/miss/bypass else Cloudflare-served; total = sum of the three) |
| Mitigating groups | `by_action`, `by_source`, `attack_source_buckets` (`ip`, `country`, `count`), `by_attack_path`, `by_attack_country`                                                                                                                                                   |
| Pass traffic      | `http_by_cache_status`, `by_http_method`                                                                                                                                                                                                                              |

`http_requests_sampled` is not a second GraphQL total query; it matches the sum of the matrix fold.

## Queries (split documents)

1. Eyeball matrix - `securityAction` × `cacheStatus`, `limit` 10000.
2. Eyeball methods - `clientRequestHTTPMethodName`.
3. Mitigating slices - `securityAction_in` + dimensions for action×source, IP, path, country.

Any GraphQL failure fails the whole day fetch (same idea as strict DNS dimension fetches).

## Rollup

Range metrics are merged in **`aggregate.build_security_section`** from daily lists of `{value, count}` rows and `attack_source_buckets`.
