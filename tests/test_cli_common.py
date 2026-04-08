"""Shared sync/report CLI validation."""

from __future__ import annotations

import pytest

from cloudflare_executive_report.cli_common import (
    CLI_TOP_MAX,
    CliValidationError,
    cache_has_any_zone_data,
    validate_and_build_sync_options,
)
from cloudflare_executive_report.config import ZoneEntry
from cloudflare_executive_report.sync.options import SyncMode


def _types(*ids: str) -> frozenset[str]:
    return frozenset(ids)


def test_validate_start_without_end():
    with pytest.raises(CliValidationError, match="together"):
        validate_and_build_sync_options(
            last=None,
            start="2026-01-01",
            end=None,
            yesterday=False,
            this_week=False,
            last_week=False,
            this_month=False,
            last_month=False,
            this_year=False,
            last_year=False,
            refresh=False,
            include_today=False,
            quiet=True,
            type_set=_types("dns"),
            top=10,
            skip_zone_health=False,
        )


def test_validate_last_with_range():
    with pytest.raises(CliValidationError, match="not both"):
        validate_and_build_sync_options(
            last=3,
            start="2026-01-01",
            end="2026-01-02",
            yesterday=False,
            this_week=False,
            last_week=False,
            this_month=False,
            last_month=False,
            this_year=False,
            last_year=False,
            refresh=False,
            include_today=False,
            quiet=True,
            type_set=_types("dns"),
            top=10,
            skip_zone_health=False,
        )


def test_validate_bad_date():
    with pytest.raises(CliValidationError, match="Invalid"):
        validate_and_build_sync_options(
            last=None,
            start="not-a-date",
            end="2026-01-02",
            yesterday=False,
            this_week=False,
            last_week=False,
            this_month=False,
            last_month=False,
            this_year=False,
            last_year=False,
            refresh=False,
            include_today=False,
            quiet=True,
            type_set=_types("dns"),
            top=10,
            skip_zone_health=False,
        )


def test_build_incremental():
    o = validate_and_build_sync_options(
        last=None,
        start=None,
        end=None,
        yesterday=False,
        this_week=False,
        last_week=False,
        this_month=False,
        last_month=False,
        this_year=False,
        last_year=False,
        refresh=False,
        include_today=False,
        quiet=True,
        type_set=_types("dns", "http"),
        top=5,
        skip_zone_health=True,
    )
    assert o.mode == SyncMode.incremental
    assert o.top == 5
    assert o.skip_zone_health is True
    assert o.types == _types("dns", "http")


def test_build_last_n():
    o = validate_and_build_sync_options(
        last=7,
        start=None,
        end=None,
        yesterday=False,
        this_week=False,
        last_week=False,
        this_month=False,
        last_month=False,
        this_year=False,
        last_year=False,
        refresh=True,
        include_today=True,
        quiet=False,
        type_set=_types("dns"),
        top=10,
        skip_zone_health=False,
    )
    assert o.mode == SyncMode.last_n
    assert o.last_n == 7
    assert o.refresh is True


def test_top_must_be_positive():
    with pytest.raises(CliValidationError, match="--top"):
        validate_and_build_sync_options(
            last=None,
            start=None,
            end=None,
            yesterday=False,
            this_week=False,
            last_week=False,
            this_month=False,
            last_month=False,
            this_year=False,
            last_year=False,
            refresh=False,
            include_today=False,
            quiet=True,
            type_set=_types("dns"),
            top=0,
            skip_zone_health=False,
        )


def test_top_cannot_exceed_max():
    with pytest.raises(CliValidationError, match="cannot exceed"):
        validate_and_build_sync_options(
            last=None,
            start=None,
            end=None,
            yesterday=False,
            this_week=False,
            last_week=False,
            this_month=False,
            last_month=False,
            this_year=False,
            last_year=False,
            refresh=False,
            include_today=False,
            quiet=True,
            type_set=_types("dns"),
            top=CLI_TOP_MAX + 1,
            skip_zone_health=False,
        )


def test_build_semantic_this_week():
    o = validate_and_build_sync_options(
        last=None,
        start=None,
        end=None,
        yesterday=False,
        this_week=True,
        last_week=False,
        this_month=False,
        last_month=False,
        this_year=False,
        last_year=False,
        refresh=False,
        include_today=False,
        quiet=True,
        type_set=_types("dns"),
        top=10,
        skip_zone_health=False,
    )
    assert o.mode == SyncMode.this_week


def test_reject_semantic_combination():
    with pytest.raises(CliValidationError, match="only one semantic"):
        validate_and_build_sync_options(
            last=None,
            start=None,
            end=None,
            yesterday=True,
            this_week=True,
            last_week=False,
            this_month=False,
            last_month=False,
            this_year=False,
            last_year=False,
            refresh=False,
            include_today=False,
            quiet=True,
            type_set=_types("dns"),
            top=10,
            skip_zone_health=False,
        )


def test_cache_has_any_zone_data(tmp_path):
    zid = "zone-a1"
    zdir = tmp_path / zid
    zdir.mkdir(parents=True)
    (zdir / "_index.json").write_text("{}")
    zones = [ZoneEntry(id=zid, name="example.com")]
    assert cache_has_any_zone_data(tmp_path, zones) is True


def test_cache_has_any_zone_data_empty_dir(tmp_path):
    zid = "zone-b2"
    (tmp_path / zid).mkdir(parents=True)
    zones = [ZoneEntry(id=zid, name="x.example")]
    assert cache_has_any_zone_data(tmp_path, zones) is False
