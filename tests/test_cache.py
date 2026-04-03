import json

from cloudflare_executive_report.cache import (
    ZoneIndex,
    merge_index_bounds,
    read_json_file,
    write_json_atomic,
)


def test_merge_index_bounds(tmp_path):
    idx = ZoneIndex(zone_id="z", zone_name="n", dns_earliest="2026-03-01", dns_latest="2026-03-10")
    m = merge_index_bounds(idx, "2026-02-01", "2026-04-01")
    assert m.dns_earliest == "2026-02-01"
    assert m.dns_latest == "2026-04-01"


def test_corrupt_json_deleted(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{not json", encoding="utf-8")
    assert read_json_file(p) is None
    assert not p.exists()


def test_write_json_atomic(tmp_path):
    p = tmp_path / "a" / "b.json"
    write_json_atomic(p, {"k": 1})
    assert json.loads(p.read_text()) == {"k": 1}
