"""World map PNG bytes (Cartopy choropleth with bar fallback)."""

from __future__ import annotations

import io
import logging
from typing import Any

from cloudflare_executive_report.common.colo_locations import COLO_TO_ISO2
from cloudflare_executive_report.pdf.theme import Theme

log = logging.getLogger(__name__)

MAP_OCEAN_COLOR = "#dbeafe"
MAP_LAND_NO_DATA_COLOR = "#f1f5f9"
MAP_EDGE_COLOR = "#d0d8e0"
MAP_COASTLINE_COLOR = "#8a9ba8"
MAP_BORDER_COLOR = "#d0d8e0"
MAP_BORDER_ALPHA = 0.55
MAP_POLY_EDGE_WIDTH = 0.28
MAP_COASTLINE_WIDTH = 0.4
MAP_BORDER_WIDTH = 0.2
MAP_NONZERO_FLOOR = 0.30
MAP_POWER_GAMMA = 0.60
MAP_ACCENT_LOW_COLOR = "#fff5ed"


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


def _render_country_totals_map_bytes(
    country_totals: dict[str, int],
    *,
    theme: Theme,
    width_in: float | None = None,
) -> bytes:
    """Render country totals choropleth bytes, or empty bytes when unavailable."""
    if not country_totals:
        return b""
    w_in = width_in if width_in is not None else theme.content_width_in()
    output_format = theme.map_format
    try:
        return _choropleth_cartopy(
            country_totals,
            theme=theme,
            width_in=w_in,
            dpi=theme.map_dpi,
            output_format=output_format,
        )
    except Exception as e:
        log.warning("Cartopy map failed; continuing without map: %s", e)
        return b""


def world_map_from_colos_bytes(
    top_colos: list[dict[str, Any]],
    *,
    theme: Theme,
    width_in: float | None = None,
) -> bytes:
    country_totals = dns_queries_by_country(top_colos)
    return _render_country_totals_map_bytes(country_totals, theme=theme, width_in=width_in)


def world_map_from_country_totals_bytes(
    country_totals: dict[str, int],
    *,
    theme: Theme,
    width_in: float | None = None,
) -> bytes:
    return _render_country_totals_map_bytes(country_totals, theme=theme, width_in=width_in)


def _choropleth_cartopy(
    country_totals: dict[str, int],
    *,
    theme: Theme,
    width_in: float,
    dpi: int,
    output_format: str = "png",
) -> bytes:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import cartopy.io.shapereader as shpreader
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    max_v = max(country_totals.values()) if country_totals else 1
    norm = mcolors.PowerNorm(gamma=MAP_POWER_GAMMA, vmin=0.0, vmax=float(max_v))
    cmap = LinearSegmentedColormap.from_list(
        "report_accent_map",
        [MAP_ACCENT_LOW_COLOR, theme.accent],
    )
    h_fig = width_in / 2.0
    fig = plt.figure(figsize=(width_in, h_fig), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1), projection=ccrs.PlateCarree())
    ax.set_global()  # type: ignore[attr-defined]
    ax.set_facecolor(MAP_OCEAN_COLOR)
    ax.add_feature(cfeature.OCEAN, facecolor=MAP_OCEAN_COLOR, zorder=0)  # type: ignore[attr-defined]
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
            face = cmap(max(float(norm(float(val))), MAP_NONZERO_FLOOR))
        else:
            face = MAP_LAND_NO_DATA_COLOR  # type: ignore[assignment]
        ax.add_geometries(  # type: ignore[attr-defined]
            [geom],
            ccrs.PlateCarree(),
            facecolor=face,
            edgecolor=MAP_EDGE_COLOR,
            linewidth=MAP_POLY_EDGE_WIDTH,
            zorder=1,
        )
    ax.add_feature(  # type: ignore[attr-defined]
        cfeature.COASTLINE,
        linewidth=MAP_COASTLINE_WIDTH,
        edgecolor=MAP_COASTLINE_COLOR,
    )
    ax.add_feature(  # type: ignore[attr-defined]
        cfeature.BORDERS,
        linewidth=MAP_BORDER_WIDTH,
        edgecolor=MAP_BORDER_COLOR,
        alpha=MAP_BORDER_ALPHA,
        zorder=2,
    )
    ax.set_axis_off()
    buf = io.BytesIO()
    save_kwargs: dict[str, Any] = {
        "format": output_format,
        "facecolor": "white",
        "bbox_inches": None,
        "pad_inches": 0,
    }
    if output_format == "png":
        save_kwargs["dpi"] = dpi
    fig.savefig(buf, **save_kwargs)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
