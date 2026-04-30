from cloudflare_executive_report.cf_client import CloudflareAPIError
from cloudflare_executive_report.fetchers import http_adaptive as ha


def test_status_rows_rollup_buckets_4xx_5xx():
    rows = [
        {"count": 100, "dimensions": {"edgeResponseStatus": "200"}},
        {"count": 20, "dimensions": {"edgeResponseStatus": "404"}},
        {"count": 3, "dimensions": {"edgeResponseStatus": "502"}},
        {"count": 2, "dimensions": {"edgeResponseStatus": "504"}},
    ]
    total, n4, n5, status_rows = ha._status_rows_rollup(rows)
    assert total == 125
    assert n4 == 20
    assert n5 == 5
    assert status_rows[0]["value"] == "200"
    assert status_rows[0]["count"] == 100


def test_timing_avg_parser_handles_absent_fields():
    data = {"viewer": {"zones": [{"tm": [{"avg": {}}]}]}}
    p50, p95 = ha._timing_p50_p95_from_data_avg(data)
    assert p50 is None
    assert p95 is None


def test_timing_quantiles_parser_reads_values():
    data = {
        "viewer": {
            "zones": [
                {
                    "tm": [
                        {
                            "quantiles": {
                                "edgeTimeToFirstByteMsP50": 120.45,
                                "edgeTimeToFirstByteMsP95": 480.9,
                            }
                        }
                    ]
                }
            ]
        }
    }
    p50, p95 = ha._timing_p50_p95_from_data_quantiles(data)
    assert p50 == 120.45
    assert p95 == 480.9


def test_optional_timing_short_circuits_on_unknown_field():
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def graphql(self, _q: str, _v: dict[str, str]) -> dict:
            self.calls += 1
            raise CloudflareAPIError('unknown field "edgeTimeToFirstByteMsP95"')

    c = FakeClient()
    p50, p95 = ha._fetch_optional_timing_ms(
        c, {"zoneTag": "z", "datetime_geq": "a", "datetime_lt": "b"}
    )
    assert p50 is None and p95 is None
    assert c.calls == 1


def test_optional_origin_response_ms_parser():
    class FakeClient:
        def graphql(self, _q: str, _v: dict[str, str]) -> dict:
            return {
                "viewer": {
                    "zones": [{"tm": [{"count": 1, "sum": {"originResponseDurationMs": 264.18}}]}]
                }
            }

    v = ha._fetch_optional_origin_response_ms(
        FakeClient(),
        {"zoneTag": "z", "datetime_geq": "a", "datetime_lt": "b"},
    )
    assert v == 264.18
