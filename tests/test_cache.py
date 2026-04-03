import json

from cloudflare_executive_report.cache import (
    IndexStream,
    ZoneIndex,
    merge_stream_bounds,
    read_json_file,
    write_json_atomic,
)


def test_merge_stream_bounds_dns():
    idx = ZoneIndex(
        zone_id="z",
        zone_name="n",
        streams={"dns": IndexStream(earliest="2026-03-01", latest="2026-03-10")},
    )
    m = merge_stream_bounds(idx, "2026-02-01", "2026-04-01", "dns")
    assert m.streams["dns"].earliest == "2026-02-01"
    assert m.streams["dns"].latest == "2026-04-01"


def test_merge_stream_bounds_http():
    idx = ZoneIndex(
        zone_id="z",
        zone_name="n",
        streams={"http": IndexStream(earliest="2026-03-01", latest="2026-03-05")},
    )
    m = merge_stream_bounds(idx, "2026-02-01", "2026-04-01", "http")
    assert m.streams["http"].earliest == "2026-02-01"
    assert m.streams["http"].latest == "2026-04-01"


def test_corrupt_json_deleted(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{not json", encoding="utf-8")
    assert read_json_file(p) is None
    assert not p.exists()


def test_write_json_atomic(tmp_path):
    p = tmp_path / "a" / "b.json"
    write_json_atomic(p, {"k": 1})
    assert json.loads(p.read_text()) == {"k": 1}
