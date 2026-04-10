"""World map PNG bytes (Cartopy choropleth with bar fallback)."""

from __future__ import annotations

import io
import logging
from typing import Any

from cloudflare_executive_report.common.colo_locations import COLO_TO_ISO2
from cloudflare_executive_report.pdf.theme import Theme

log = logging.getLogger(__name__)


def dns_queries_by_country(top_colos: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in top_colos:
        colo = str(row.get("colo", "")).upper()
        iso = COLO_TO_ISO2.get(colo)
        if iso is None:
            continue
        c = int(row.get("count", 0))
        out[iso] = out.get(iso, 0) + c
    return out


def map_height_in_for_width(width_in: float) -> float:
    return width_in / 2.0


def world_map_from_colos_bytes(
    top_colos: list[dict[str, Any]],
    *,
    theme: Theme,
    width_in: float | None = None,
) -> bytes:
    w_in = width_in if width_in is not None else theme.content_width_in()
    h_in = map_height_in_for_width(w_in)
    dpi = theme.map_dpi
    country_totals = dns_queries_by_country(top_colos)

    if not top_colos:
        return _placeholder_bytes(
            "No data center breakdown for this period.",
            w_in,
            h_in,
            dpi,
            theme,
        )
    if not country_totals:
        return _placeholder_bytes(
            "No country mapping for these data centers.",
            w_in,
            h_in,
            dpi,
            theme,
        )

    try:
        return _choropleth_cartopy(country_totals, width_in=w_in, dpi=dpi)
    except Exception as e:
        log.warning("Cartopy map failed, using bar fallback: %s", e)
        return _fallback_bars(country_totals, w_in, h_in, dpi, theme)


def world_map_from_country_totals_bytes(
    country_totals: dict[str, int],
    *,
    theme: Theme,
    width_in: float | None = None,
) -> bytes:
    w_in = width_in if width_in is not None else theme.content_width_in()
    h_in = map_height_in_for_width(w_in)
    dpi = theme.map_dpi
    if not country_totals:
        return _placeholder_bytes(
            "No geographic breakdown for this period.",
            w_in,
            h_in,
            dpi,
            theme,
        )
    try:
        return _choropleth_cartopy(country_totals, width_in=w_in, dpi=dpi)
    except Exception as e:
        log.warning("Cartopy map failed, using bar fallback: %s", e)
        return _fallback_bars(country_totals, w_in, h_in, dpi, theme)


def _choropleth_cartopy(
    country_totals: dict[str, int],
    *,
    width_in: float,
    dpi: int,
) -> bytes:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import cartopy.io.shapereader as shpreader
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    max_v = max(country_totals.values()) if country_totals else 1
    # Improve visibility when one country dominates totals.
    norm = mcolors.PowerNorm(gamma=0.45, vmin=0.0, vmax=float(max_v))
    cmap = plt.cm.Blues
    land_no_data = "#f1f5f9"
    nonzero_floor = 0.33
    h_fig = width_in / 2.0
    fig = plt.figure(figsize=(width_in, h_fig), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1), projection=ccrs.PlateCarree())
    ax.set_global()
    ax.set_facecolor("#dbeafe")
    ax.add_feature(cfeature.OCEAN, facecolor="#dbeafe", zorder=0)
    reader = shpreader.Reader(
        shpreader.natural_earth(resolution="50m", category="cultural", name="admin_0_countries")
    )

    def _iso2(attrs: dict[str, Any]) -> str | None:
        a = attrs.get("ISO_A2")
        if isinstance(a, str) and len(a) == 2 and a.isalpha():
            return a.upper()
        return None

    for record in reader.records():
        geom = record.geometry
        if geom is None:
            continue
        iso = _iso2(record.attributes)
        val = country_totals.get(iso, 0) if iso else 0
        if val > 0:
            face = cmap(max(float(norm(float(val))), nonzero_floor))
        else:
            face = land_no_data
        ax.add_geometries(
            [geom],
            ccrs.PlateCarree(),
            facecolor=face,
            edgecolor="#cbd5e1",
            linewidth=0.3,
            zorder=1,
        )
    ax.add_feature(cfeature.COASTLINE, linewidth=0.4, edgecolor="#94a3b8", zorder=2)
    ax.add_feature(cfeature.BORDERS, linewidth=0.2, edgecolor="#cbd5e1", alpha=0.55, zorder=2)
    ax.set_axis_off()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white", bbox_inches=None, pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _fallback_bars(
    country_totals: dict[str, int],
    w_in: float,
    h_in: float,
    dpi: int,
    theme: Theme,
) -> bytes:
    import matplotlib.pyplot as plt

    items = sorted(country_totals.items(), key=lambda x: -x[1])[:28]
    fig, ax = plt.subplots(figsize=(w_in, h_in), facecolor="white")
    if not items:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=11, color=theme.muted)
        ax.axis("off")
    else:
        codes, vals = zip(*items, strict=True)
        y = list(range(len(codes)))
        ax.barh(y, vals, color=theme.primary, alpha=0.82, height=0.65)
        ax.set_yticks(y)
        ax.set_yticklabels(list(codes), fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Volume (approx.)", fontsize=9, color=theme.muted)
        ax.set_title("By country (chart fallback)", fontsize=10, color=theme.slate, pad=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="x", linestyle="--", alpha=0.35)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white", pad_inches=0.12)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _placeholder_bytes(
    message: str,
    w_in: float,
    h_in: float,
    dpi: int,
    theme: Theme,
) -> bytes:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(w_in, h_in))
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=11, color=theme.muted)
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
