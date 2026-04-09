"""cf-report CLI."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

import typer

from cloudflare_executive_report import exits
from cloudflare_executive_report.cf_client import (
    CloudflareAPIError,
    CloudflareAuthError,
    CloudflareClient,
)
from cloudflare_executive_report.cli_common import (
    CliConfigError,
    CliValidationError,
    cache_has_any_zone_data,
    load_app_config,
    resolve_zone_filter,
    validate_and_build_sync_options,
    zone_ids_for_report,
    zones_matching_filter,
)
from cloudflare_executive_report.common.logging_config import (
    effective_debug_enabled,
    setup_logging,
)
from cloudflare_executive_report.config import (
    AppConfig,
    ZoneEntry,
    default_config_path,
    load_config,
    save_config,
    template_config,
)
from cloudflare_executive_report.fetchers.registry import (
    default_types_csv,
    registered_stream_ids,
)
from cloudflare_executive_report.report.command_flow import run_report_pdf_command
from cloudflare_executive_report.sync import run_clean, run_sync
from cloudflare_executive_report.zones_api import (
    find_zone_by_name,
    get_zone,
    list_all_zones,
)


def _valid_sync_types() -> frozenset[str]:
    return frozenset(registered_stream_ids())


def _parse_sync_types(raw: str) -> frozenset[str]:
    valid = _valid_sync_types()
    allowed = ", ".join(registered_stream_ids())
    found: set[str] = set()
    for part in raw.split(","):
        p = part.strip().lower()
        if not p:
            continue
        if p in valid:
            found.add(p)
        else:
            typer.echo(
                f"Ignoring unknown type {p!r} (allowed: {allowed})",
                err=True,
            )
    if not found:
        typer.echo(
            f"Error: at least one valid type is required ({allowed}).",
            err=True,
        )
        raise typer.Exit(exits.INVALID_PARAMS)
    return frozenset(found)


def _config_log_level(cfg: AppConfig) -> str:
    s = (cfg.log_level or "").strip()
    return s if s else "info"


def _pdf_streams_from_types(type_set: frozenset[str]) -> tuple[str, ...]:
    """Order follows registry; only streams with PDF sections."""
    out: list[str] = []
    for sid in registered_stream_ids():
        if sid in type_set and sid in ("dns", "http", "security", "cache"):
            out.append(sid)
    return tuple(out)


app = typer.Typer(
    help="Cloudflare Executive Report - multi-zone reporting and cache. All dates are UTC.",
    context_settings={"help_option_names": ["-h", "--help"]},
)

_cli_verbose = False
_cli_quiet = False


def _check_last_argv() -> None:
    if "--last" not in sys.argv:
        return
    if "sync" not in sys.argv and "report" not in sys.argv:
        return
    i = sys.argv.index("--last")
    if i + 1 >= len(sys.argv):
        typer.echo("Error: --last requires a number. Example: --last 7", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)
    nxt = sys.argv[i + 1]
    if nxt.startswith("-") or not nxt.isdigit():
        typer.echo("Error: --last requires a positive integer. Example: --last 7", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)


@app.callback()
def main_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Same as log_level debug for this run (overrides config); includes HTTP traces.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress progress output (errors still shown)."
    ),
) -> None:
    """Incremental by default; use --last N or --start/--end for fixed windows."""
    global _cli_verbose, _cli_quiet
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    _cli_verbose = verbose
    _cli_quiet = quiet


@app.command("init")
def cmd_init(
    ctx: typer.Context,
    config: Path | None = typer.Option(None, "--config", help="Override config file path."),
) -> None:
    """Create ~/.cf-report/config.yaml template and prompt for API token."""
    path = config or default_config_path()
    if path.exists():
        typer.echo(f"Config already exists: {path}", err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    token = getpass.getpass("Cloudflare API token: ").strip()
    cfg = template_config()
    cfg.api_token = token or cfg.api_token
    save_config(cfg, path)
    typer.echo(f"Wrote {path}")


zones_app = typer.Typer(help="List and manage zones in config.")
app.add_typer(zones_app, name="zones")


@app.command("report")
def cmd_report(
    ctx: typer.Context,
    last: int | None = typer.Option(None, "--last", help="Last N complete UTC days (requires N)."),
    start: str | None = typer.Option(
        None, "--start", help="Start date YYYY-MM-DD (requires --end)."
    ),
    end: str | None = typer.Option(None, "--end", help="End date YYYY-MM-DD (requires --start)."),
    last_month: bool = typer.Option(False, "--last-month", help="Use previous full UTC month."),
    last_week: bool = typer.Option(False, "--last-week", help="Use previous full UTC week."),
    last_year: bool = typer.Option(False, "--last-year", help="Use previous full UTC year."),
    this_month: bool = typer.Option(False, "--this-month", help="Use current UTC month to date."),
    this_week: bool = typer.Option(False, "--this-week", help="Use current UTC week to date."),
    this_year: bool = typer.Option(False, "--this-year", help="Use current UTC year to date."),
    yesterday: bool = typer.Option(False, "--yesterday", help="Use previous UTC day."),
    refresh: bool = typer.Option(
        False, "--refresh", help="Ignore cache and re-fetch active range (during sync step)."
    ),
    include_today: bool = typer.Option(
        False, "--include-today", help="Include today in the report end date (see sync behavior)."
    ),
    cache_only: bool = typer.Option(
        False,
        "--cache-only",
        help=(
            "Skip sync; build PDF from cache only. Date span matches sync JSON "
            "(indices for --types, or --last / --start/--end when set)."
        ),
    ),
    refresh_health: bool = typer.Option(
        False,
        "--refresh-health",
        help=(
            "Refresh live zone health for this report window and rebuild output JSON "
            "(takes precedence over --cache-only reuse)."
        ),
    ),
    output: Path | None = typer.Option(
        None,
        "-o",
        "--output",
        help="Output PDF path.",
    ),
    zone: str | None = typer.Option(
        None,
        "--zone",
        help=(
            "Zone id or name in config; if omitted, uses default_zone when set, "
            "else all configured zones."
        ),
    ),
    types: str = typer.Option(
        default_types_csv(),
        "--types",
        help=(
            f"Comma-separated stream ids (default: {default_types_csv()}). "
            "PDF includes dns, http, security, and cache."
        ),
    ),
    top: int = typer.Option(
        10,
        "--top",
        help="How many items in each ranked list (e.g. top query names, countries).",
    ),
    skip_zone_health: bool = typer.Option(
        False,
        "--skip-zone-health",
        help="Omit zone health (REST); same as sync.",
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Override JSON/history output root directory for this run."
    ),
    config: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    """Sync cache (unless --cache-only) then build a PDF.

    Same date modes as ``cf-report sync``: default is incremental (span from cache
    indices for selected --types); or use --last N or --start/--end. Omit ``--zone``
    to include all configured zones.
    """
    verbose = ctx.obj.get("verbose", False)
    quiet = ctx.obj.get("quiet", False)

    if output is None:
        typer.echo("Error: --output / -o is required.", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)

    type_set = _parse_sync_types(types)
    pdf_streams = _pdf_streams_from_types(type_set)
    if not pdf_streams:
        typer.echo(
            "Error: --types must include at least one of dns, http "
            "security, cache (PDF has no section for other streams yet).",
            err=True,
        )
        raise typer.Exit(exits.INVALID_PARAMS)

    try:
        sync_opts = validate_and_build_sync_options(
            last=last,
            start=start,
            end=end,
            last_month=last_month,
            last_week=last_week,
            last_year=last_year,
            this_month=this_month,
            this_week=this_week,
            this_year=this_year,
            yesterday=yesterday,
            refresh=refresh,
            include_today=include_today,
            quiet=quiet,
            type_set=type_set,
            top=top,
            skip_zone_health=skip_zone_health,
        )
    except CliValidationError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.INVALID_PARAMS) from None

    try:
        cfg = load_app_config(config)
    except CliConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None

    if output_dir is not None:
        cfg.output_dir = str(output_dir)

    setup_logging(verbose=verbose, quiet=quiet, log_level=_config_log_level(cfg))

    zone_effective = resolve_zone_filter(cfg, zone)
    zone_keys = zone_ids_for_report(cfg, zone_effective)
    if not zone_keys:
        typer.echo(
            "Error: no zones in config. Use `cf-report zones add` or set `zones` / `default_zone`.",
            err=True,
        )
        raise typer.Exit(exits.INVALID_PARAMS)

    scoped_zones = zones_matching_filter(cfg, zone_effective)
    if cache_only:
        if zone_effective and not scoped_zones:
            typer.echo(f"Error: Zone not found in config: {zone_effective!r}.", err=True)
            raise typer.Exit(exits.INVALID_PARAMS)
        if not cache_has_any_zone_data(cfg.cache_path(), scoped_zones):
            typer.echo(
                "Error: --cache-only requires non-empty cache for the selected zone(s). "
                "Run `cf-report sync` first (omit --cache-only).",
                err=True,
            )
            raise typer.Exit(exits.INVALID_PARAMS)

    outcome = run_report_pdf_command(
        cfg=cfg,
        sync_opts=sync_opts,
        output=output,
        zone_effective=zone_effective,
        zone_keys=zone_keys,
        scoped_zone_ids=[z.id for z in scoped_zones],
        pdf_streams=pdf_streams,
        top=top,
        type_set=type_set,
        include_today=include_today,
        cache_only=cache_only,
        refresh_health=refresh_health,
    )
    if outcome.stderr:
        typer.echo(outcome.stderr, err=True)
    if outcome.pdf_written_line:
        typer.echo(outcome.pdf_written_line)
    raise typer.Exit(outcome.exit_code)


@zones_app.command("list")
def zones_list(ctx: typer.Context) -> None:
    """List all zones visible to the token (id + name)."""
    verbose = _cli_verbose
    quiet = _cli_quiet
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    setup_logging(verbose=verbose, quiet=quiet, log_level=_config_log_level(cfg))
    try:
        with CloudflareClient(cfg.api_token, verbose=effective_debug_enabled()) as c:
            zs = list_all_zones(c)
    except CloudflareAuthError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.AUTH_FAILED) from None
    except CloudflareAPIError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    for z in zs:
        typer.echo(f"{z.get('id')}\t{z.get('name')}")


@zones_app.command("add")
def zones_add(
    ctx: typer.Context,
    zone_id: str | None = typer.Option(None, "--id", help="Zone ID"),
    name: str | None = typer.Option(None, "--name", help="Zone name (hostname)"),
) -> None:
    """Add a zone to config (fetch missing id/name via API)."""
    verbose = _cli_verbose
    quiet = _cli_quiet
    if (zone_id is None) == (name is None):
        typer.echo("Specify exactly one of --id or --name", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    setup_logging(verbose=verbose, quiet=quiet, log_level=_config_log_level(cfg))
    try:
        with CloudflareClient(cfg.api_token, verbose=effective_debug_enabled()) as c:
            if zone_id:
                z = get_zone(c, zone_id)
            else:
                assert name
                z = find_zone_by_name(c, name)
                if not z:
                    typer.echo(f"Zone not found: {name}", err=True)
                    raise typer.Exit(exits.GENERAL_ERROR) from None
        entry = ZoneEntry(id=str(z["id"]), name=str(z["name"]))
        for existing in cfg.zones:
            if existing.id == entry.id or existing.name == entry.name:
                typer.echo("Zone already in config", err=True)
                raise typer.Exit(exits.GENERAL_ERROR) from None
        cfg.zones.append(entry)
        save_config(cfg)
        typer.echo(f"Added {entry.name} ({entry.id})")
    except CloudflareAuthError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.AUTH_FAILED) from None
    except CloudflareAPIError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None


@zones_app.command("remove")
def zones_remove(
    ctx: typer.Context,
    zone_id: str | None = typer.Option(None, "--id"),
    name: str | None = typer.Option(None, "--name"),
) -> None:
    """Remove a zone from config."""
    verbose = _cli_verbose
    quiet = _cli_quiet
    if (zone_id is None) == (name is None):
        typer.echo("Specify exactly one of --id or --name", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    setup_logging(verbose=verbose, quiet=quiet, log_level=_config_log_level(cfg))
    key = zone_id or name
    assert key
    new_z = [z for z in cfg.zones if z.id != key and z.name != key]
    if len(new_z) == len(cfg.zones):
        typer.echo("Zone not in config", err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    cfg.zones = new_z
    save_config(cfg)
    typer.echo("Removed")


@app.command("sync")
def cmd_sync(
    ctx: typer.Context,
    last: int | None = typer.Option(None, "--last", help="Last N complete UTC days (requires N)."),
    start: str | None = typer.Option(
        None, "--start", help="Start date YYYY-MM-DD (requires --end)."
    ),
    end: str | None = typer.Option(None, "--end", help="End date YYYY-MM-DD (requires --start)."),
    last_month: bool = typer.Option(False, "--last-month", help="Use previous full UTC month."),
    last_week: bool = typer.Option(False, "--last-week", help="Use previous full UTC week."),
    last_year: bool = typer.Option(False, "--last-year", help="Use previous full UTC year."),
    this_month: bool = typer.Option(False, "--this-month", help="Use current UTC month to date."),
    this_week: bool = typer.Option(False, "--this-week", help="Use current UTC week to date."),
    this_year: bool = typer.Option(False, "--this-year", help="Use current UTC year to date."),
    yesterday: bool = typer.Option(False, "--yesterday", help="Use previous UTC day."),
    refresh: bool = typer.Option(
        False, "--refresh", help="Ignore cache and re-fetch active range."
    ),
    include_today: bool = typer.Option(
        False, "--include-today", help="Include today (not cached; incomplete data)."
    ),
    zone: str | None = typer.Option(
        None,
        "--zone",
        help="Zone id or name in config; if omitted, uses default_zone from config when set.",
    ),
    types: str = typer.Option(
        default_types_csv(),
        "--types",
        help=f"Comma-separated stream ids (default: {default_types_csv()}).",
    ),
    top: int = typer.Option(
        10,
        "--top",
        help="How many items in each ranked list (e.g. top query names, countries).",
    ),
    skip_zone_health: bool = typer.Option(
        False,
        "--skip-zone-health",
        help="Omit zone health (REST); cache data only.",
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Override JSON/history output root directory for this run."
    ),
    config: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    """Incremental sync by default; use --last N or --start/--end for explicit windows."""
    verbose = ctx.obj.get("verbose", False)
    quiet = ctx.obj.get("quiet", False)

    type_set = _parse_sync_types(types)
    try:
        opts = validate_and_build_sync_options(
            last=last,
            start=start,
            end=end,
            last_month=last_month,
            last_week=last_week,
            last_year=last_year,
            this_month=this_month,
            this_week=this_week,
            this_year=this_year,
            yesterday=yesterday,
            refresh=refresh,
            include_today=include_today,
            quiet=quiet,
            type_set=type_set,
            top=top,
            skip_zone_health=skip_zone_health,
        )
    except CliValidationError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.INVALID_PARAMS) from None

    try:
        cfg = load_app_config(config)
    except CliConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None

    if output_dir is not None:
        cfg.output_dir = str(output_dir)

    setup_logging(verbose=verbose, quiet=quiet, log_level=_config_log_level(cfg))

    zone_effective = resolve_zone_filter(cfg, zone)

    code = run_sync(
        cfg,
        opts,
        zone_filter=zone_effective,
        output_path=None,
        write_stdout=False,
        write_report_json=False,
    )
    raise typer.Exit(code)


@app.command("clean")
def cmd_clean(
    ctx: typer.Context,
    older_than: int | None = typer.Option(
        None, "--older-than", help="Delete selected scope entries older than N days."
    ),
    scope_cache: bool = typer.Option(False, "--cache", help="Clean cache scope."),
    scope_history: bool = typer.Option(False, "--history", help="Clean report history scope."),
    delete_all: bool = typer.Option(False, "--all", help="Clean both cache and history."),
    force: bool = typer.Option(False, "--force", help="Confirm destructive cleanup for --all."),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Override JSON/history output root directory for this run."
    ),
) -> None:
    """Prune or wipe the DNS cache directory."""
    verbose = ctx.obj.get("verbose", False)
    quiet = ctx.obj.get("quiet", False)
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    if output_dir is not None:
        cfg.output_dir = str(output_dir)
    setup_logging(verbose=verbose, quiet=quiet, log_level=_config_log_level(cfg))
    if delete_all and not force:
        typer.echo("Error: --all requires --force.", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)
    selected_cache = scope_cache or delete_all
    selected_history = scope_history or delete_all
    if not selected_cache and not selected_history:
        typer.echo("Error: specify --cache, --history, or --all.", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)
    code = run_clean(
        cfg,
        older_than=older_than,
        scope_cache=selected_cache,
        scope_history=selected_history,
        quiet=quiet,
    )
    raise typer.Exit(code)


def main() -> None:
    try:
        _check_last_argv()
        app()
    except KeyboardInterrupt:
        raise typer.Exit(exits.GENERAL_ERROR) from None


if __name__ == "__main__":
    main()
