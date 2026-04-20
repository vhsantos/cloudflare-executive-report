import json

import pytest

from cloudflare_executive_report.common.period_resolver import (
    build_data_fingerprint,
    compute_fingerprint_hash,
)
from cloudflare_executive_report.config import AppConfig, ZoneEntry
from cloudflare_executive_report.report.snapshot import find_and_extract_reusable_snapshot


@pytest.fixture
def mock_cfg(tmp_path):
    return AppConfig(
        api_token="x",
        cache_dir=str(tmp_path / "cache"),
        history_dir=str(tmp_path / "out"),
        zones=[ZoneEntry(id="z1", name="n1"), ZoneEntry(id="z2", name="n2")],
    )


def test_find_and_extract_reusable_snapshot_scenarios(mock_cfg):
    hist_dir = mock_cfg.history_path()
    hist_dir.mkdir(parents=True, exist_ok=True)

    fp = build_data_fingerprint(
        start="2026-04-01", end="2026-04-07", top=5, types={"http"}, include_today=False
    )
    fp_hash = compute_fingerprint_hash(fp)

    # 1. Exact match scenario (in current report)
    snapshot = {"data_fingerprint": fp, "zones": [{"zone_id": "z1"}, {"zone_id": "z2"}]}
    current_file = mock_cfg.report_current_path()
    current_file.write_text(json.dumps(snapshot))

    res = find_and_extract_reusable_snapshot(mock_cfg, fp, ["z1", "z2"])
    assert res is not None
    assert len(res["zones"]) == 2
    assert res["zones"][0]["zone_id"] == "z1"
    assert res["zones"][1]["zone_id"] == "z2"

    # 2. Subset request reuses a larger snapshot
    res_subset = find_and_extract_reusable_snapshot(mock_cfg, fp, ["z1"])
    assert res_subset is not None
    assert len(res_subset["zones"]) == 1
    assert res_subset["zones"][0]["zone_id"] == "z1"
    # Ensure original wasn't mutated
    assert len(snapshot["zones"]) == 2

    # 3. Superset request falls back (returns None)
    res_super = find_and_extract_reusable_snapshot(mock_cfg, fp, ["z1", "z2", "z3"])
    assert res_super is None

    # 4. Different period (different hash) must not reuse
    fp_diff = build_data_fingerprint(
        start="2026-04-02", end="2026-04-08", top=5, types={"http"}, include_today=False
    )
    res_diff = find_and_extract_reusable_snapshot(mock_cfg, fp_diff, ["z1"])
    assert res_diff is None

    # 5. History file reuse
    current_file.unlink()  # Remove current to force history check
    hist_file = hist_dir / f"cf_report_{fp_hash}_2026-04-07_120000.json"
    hist_file.write_text(json.dumps(snapshot))

    res_hist = find_and_extract_reusable_snapshot(mock_cfg, fp, ["z2"])
    assert res_hist is not None
    assert len(res_hist["zones"]) == 1
    assert res_hist["zones"][0]["zone_id"] == "z2"


def test_find_and_extract_reusable_snapshot_empty_zones(mock_cfg):
    fp = build_data_fingerprint(
        start="2026-04-01", end="2026-04-07", top=5, types={"http"}, include_today=False
    )
    assert find_and_extract_reusable_snapshot(mock_cfg, fp, []) is None
