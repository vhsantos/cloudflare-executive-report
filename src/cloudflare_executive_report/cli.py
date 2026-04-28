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
    validate_api_token,
    zone_ids_for_report,
    zones_matching_filter,
)
from cloudflare_executive_report.common.constants import PDF_RENDERABLE_STREAMS, PROJECT_NAME
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
    save_config_template,
    template_config,
)
from cloudflare_executive_report.fetchers.registry import (
    default_types_csv,
    registered_stream_ids,
)
from cloudflare_executive_report.report.command_flow import run_report_pdf_command
from cloudflare_executive_report.sync.orchestrator import run_clean, run_sync
from cloudflare_executive_report.validate.consts import ALL_PERMISSIONS
from cloudflare_executive_report.validate.runner import (
    STATUS_MISSING,
    STATUS_OK,
    STATUS_SKIPPED,
    validate_token_permissions,
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
            typer.echo(f"Warning: unknown type {p!r} will be ignored.", err=True)
    if not found:
        typer.echo(
            f"Error: no valid types specified. Allowed: {allowed}",
            err=True,
        )
        raise typer.Exit(exits.INVALID_PARAMS)
    return frozenset(found)


def _resolve_types(cli_types: str | None, config_types: list[str]) -> frozenset[str]:
    """Determine active streams. CLI overrides Config. Empty or None means ALL."""
    if cli_types:
        found = set(_parse_sync_types(cli_types))
    elif config_types:
        found = set(config_types)
    else:
        found = set(_parse_sync_types(default_types_csv()))

    if "dns" in found:
        found.add("dns_records")
    if "http" in found:
        found.add("http_adaptive")

    return frozenset(found)


def _config_log_level(cfg: AppConfig) -> str:
    s = (cfg.log_level or "").strip()
    return s if s else "info"


def _pdf_streams_from_types(type_set: frozenset[str]) -> tuple[str, ...]:
    """Order follows master list; return only streams requested in type_set."""
    out: list[str] = []
    for sid in PDF_RENDERABLE_STREAMS:
        if sid in type_set:
            out.append(sid)
    return tuple(out)


app = typer.Typer(
    help=f"{PROJECT_NAME} - multi-zone reporting and cache. All dates are UTC.",
    context_settings={"help_option_names": ["-h", "--help"]},
)

_cli_verbose = 0
_cli_quiet = False
_cli_log_file: Path | None = None


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
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity (-v: INFO, -vv: DEBUG, -vvv: TRACE).",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Only show errors."),
    log_file: Path | None = typer.Option(None, "--log-file", help="Write all logs to file."),
) -> None:
    """Incremental by default; use --last N or --start/--end for fixed windows."""
    global _cli_verbose, _cli_quiet, _cli_log_file
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["log_file"] = log_file
    _cli_verbose = verbose
    _cli_quiet = quiet
    _cli_log_file = log_file


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
    save_config_template(cfg, path)
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
    email: bool = typer.Option(
        False,
        "--email",
        help=("After a successful PDF, send it via SMTP when email.enabled is true in config."),
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
    types: str | None = typer.Option(
        None,
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
    history_dir: Path | None = typer.Option(
        None, "--history-dir", help="Override JSON/history output root directory for this run."
    ),
    config: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    """Sync cache (unless --cache-only) then build a PDF.

    Same date modes as ``cf-report sync``: default is incremental (span from cache
    indices for selected --types); or use --last N or --start/--end. Omit ``--zone``
    to include all configured zones.
    """
    verbose = ctx.obj.get("verbose", 0)
    quiet = ctx.obj.get("quiet", False)
    log_file = ctx.obj.get("log_file")

    if output is None:
        typer.echo("Error: --output / -o is required.", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)

    try:
        cfg = load_app_config(config)
        validate_api_token(cfg)
    except CliConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None

    type_set = _resolve_types(types, cfg.types)
    pdf_streams = _pdf_streams_from_types(type_set)

    if not pdf_streams:
        typer.echo(
            "Error: --types must include at least one of dns, http "
            "security, cache (PDF has no section for other streams yet).",
            err=True,
        )
        raise typer.Exit(exits.INVALID_PARAMS)

    if history_dir is not None:
        cfg.history_dir = str(history_dir)

    try:
        sync_opts = validate_and_build_sync_options(
            default_period=cfg.default_period,
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

    if history_dir is not None:
        cfg.history_dir = str(history_dir)

    setup_logging(
        verbose_count=verbose, quiet=quiet, log_level=_config_log_level(cfg), log_file=log_file
    )

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
        send_email=email,
    )
    if outcome.stderr:
        typer.echo(outcome.stderr, err=True)
    if outcome.email_sent_line:
        typer.echo(outcome.email_sent_line)
    raise typer.Exit(outcome.exit_code)


@zones_app.command("list")
def zones_list(ctx: typer.Context) -> None:
    """List all zones visible to the token (id + name)."""
    verbose = _cli_verbose
    quiet = _cli_quiet
    try:
        cfg = load_config()
        validate_api_token(cfg)
    except (CliConfigError, FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    setup_logging(
        verbose_count=verbose, quiet=quiet, log_level=_config_log_level(cfg), log_file=None
    )
    try:
        with CloudflareClient(cfg.api_token, verbose=effective_debug_enabled()) as c:
            zs = c.list_zones()
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
    add_all: bool = typer.Option(False, "--all", help="Add all accessible zones."),
) -> None:
    """Add a zone to config (fetch missing id/name via API)."""
    verbose = _cli_verbose
    quiet = _cli_quiet
    log_file = _cli_log_file

    # Exactly one of --id, --name, or --all
    provided = sum([zone_id is not None, name is not None, add_all])
    if provided != 1:
        typer.echo("Specify exactly one of --id, --name, or --all", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)

    try:
        cfg = load_config()
        validate_api_token(cfg)
    except (CliConfigError, FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    setup_logging(
        verbose_count=verbose, quiet=quiet, log_level=_config_log_level(cfg), log_file=log_file
    )
    try:
        with CloudflareClient(cfg.api_token, verbose=effective_debug_enabled()) as c:
            if add_all:
                all_z = c.list_zones()
                added_count = 0
                existing_ids = {z.id for z in cfg.zones}
                for z in all_z:
                    if z["id"] not in existing_ids:
                        cfg.zones.append(ZoneEntry(id=str(z["id"]), name=str(z["name"])))
                        added_count += 1
                save_config(cfg)
                typer.echo(f"Added {added_count} new zones.")
                return

            if zone_id:
                z = c.get_zone(zone_id)
            else:
                assert name is not None
                z_found = c.find_zone_by_name(name)
                if not z_found:
                    typer.echo(f"Zone not found: {name}", err=True)
                    raise typer.Exit(exits.GENERAL_ERROR) from None
                z = z_found

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
    log_file = _cli_log_file
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    setup_logging(
        verbose_count=verbose, quiet=quiet, log_level=_config_log_level(cfg), log_file=log_file
    )
    if (zone_id is None) == (name is None):
        typer.echo("Specify exactly one of --id or --name", err=True)
        raise typer.Exit(exits.INVALID_PARAMS)
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
    types: str | None = typer.Option(
        None,
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
    history_dir: Path | None = typer.Option(
        None, "--history-dir", help="Override JSON/history output root directory for this run."
    ),
    config: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    """Incremental sync by default; use --last N or --start/--end for explicit windows."""
    verbose = ctx.obj.get("verbose", 0)
    quiet = ctx.obj.get("quiet", False)
    log_file = ctx.obj.get("log_file")

    try:
        cfg = load_app_config(config)
        validate_api_token(cfg)
    except CliConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None

    type_set = _resolve_types(types, cfg.types)

    try:
        opts = validate_and_build_sync_options(
            default_period=cfg.default_period,
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

    if history_dir is not None:
        cfg.history_dir = str(history_dir)

    setup_logging(
        verbose_count=verbose, quiet=quiet, log_level=_config_log_level(cfg), log_file=log_file
    )

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
    history_dir: Path | None = typer.Option(
        None, "--history-dir", help="Override JSON/history output root directory for this run."
    ),
) -> None:
    """Prune or wipe the DNS cache directory."""
    verbose = ctx.obj.get("verbose", 0)
    quiet = ctx.obj.get("quiet", False)
    log_file = ctx.obj.get("log_file")
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None
    if history_dir is not None:
        cfg.history_dir = str(history_dir)
    setup_logging(
        verbose_count=verbose, quiet=quiet, log_level=_config_log_level(cfg), log_file=log_file
    )
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


@app.command("validate")
def cmd_validate(
    ctx: typer.Context,
    zone: str | None = typer.Option(
        None,
        "--zone",
        help=(
            "Zone id or name to use for zone-scoped probes. "
            "Defaults to default_zone from config, then first configured zone."
        ),
    ),
    config: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    """Check that the configured API token has all required Cloudflare permissions.

    Runs one lightweight API call per permission and prints a status table.
    Exits with a non-zero code when any permission is MISSING.
    """
    verbose = ctx.obj.get("verbose", 0)
    quiet = ctx.obj.get("quiet", False)
    log_file = ctx.obj.get("log_file")

    try:
        cfg = load_app_config(config)
        validate_api_token(cfg)
    except CliConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None

    setup_logging(
        verbose_count=verbose,
        quiet=quiet,
        log_level=_config_log_level(cfg),
        log_file=log_file,
    )

    # Resolve the zone for zone-scoped probes.
    zone_effective = resolve_zone_filter(cfg, zone)
    test_zone_id: str | None = None
    if zone_effective:
        matched = zones_matching_filter(cfg, zone_effective)
        if not matched:
            typer.echo(f"Error: Zone not found in config: {zone_effective!r}.", err=True)
            raise typer.Exit(exits.INVALID_PARAMS)
        test_zone_id = matched[0].id
    elif cfg.zones:
        test_zone_id = cfg.zones[0].id

    if not test_zone_id:
        typer.echo(
            "Warning: no zones configured - zone-scoped permissions will be skipped.",
            err=True,
        )

    typer.echo(f"Validating token permissions ({len(ALL_PERMISSIONS)} checks)...")
    if test_zone_id:
        typer.echo(f"Zone used for zone-scoped probes: {test_zone_id}")
    typer.echo("")

    try:
        with CloudflareClient(cfg.api_token, verbose=effective_debug_enabled()) as client:
            results = validate_token_permissions(
                client,
                test_zone_id,
                enabled_streams=cfg.types,
            )
    except CloudflareAuthError as e:
        typer.echo(f"Authentication failed: {e}", err=True)
        raise typer.Exit(exits.AUTH_FAILED) from None
    except CloudflareAPIError as e:
        typer.echo(f"API error during validation: {e}", err=True)
        raise typer.Exit(exits.GENERAL_ERROR) from None

    # -----------------------------------------------------------------------
    # Print results table
    # -----------------------------------------------------------------------
    col_perm = 46
    col_status = 14
    col_used = 28

    header = f"{'Permission':<{col_perm}}  {'Status':<{col_status}}  {'Used By':<{col_used}}  Notes"
    separator = "-" * (len(header) + 4)
    typer.echo(header)
    typer.echo(separator)

    missing: list[str] = []
    for result in results:
        used_display = ", ".join(result.used_by) if result.used_by else "-"
        notes = result.message or ""
        typer.echo(
            f"{result.permission:<{col_perm}}  {result.status:<{col_status}}  "
            f"{used_display:<{col_used}}  {notes}".rstrip()
        )
        if result.status == STATUS_MISSING:
            missing.append(result.permission)

    typer.echo("")

    # -----------------------------------------------------------------------
    # Summary and exit
    # -----------------------------------------------------------------------
    ok_count = sum(1 for r in results if r.status == STATUS_OK)
    skipped_count = sum(1 for r in results if r.status == STATUS_SKIPPED)
    missing_count = len(missing)
    typer.echo(f"Result: {ok_count} OK  |  {missing_count} MISSING  |  {skipped_count} SKIPPED")

    if missing:
        typer.echo("", err=True)
        typer.echo("Missing permissions:", err=True)
        for perm in missing:
            typer.echo(f"  - {perm}", err=True)
        typer.echo(
            "\nGrant the above permissions in your Cloudflare token settings and re-run.",
            err=True,
        )
        raise typer.Exit(exits.AUTH_FAILED)

    typer.echo("All required permissions are available.")

    if results.write_access_detected:
        msg_width = 80
        msg_warning = "SECURITY WARNING: UNWANTED WRITE PERMISSIONS DETECTED."
        msg_line1 = "Your API token appears to have WRITE access to your Cloudflare zone."
        msg_line2 = "This tool only requires READ permissions. For better security, it is"
        msg_line3 = "strongly recommended to restrict this token to 'Read' access only."
        typer.echo("")
        typer.echo("!" * msg_width, err=True)
        typer.echo(msg_warning.center(msg_width), err=True)
        typer.echo("", err=True)
        typer.echo(msg_line1.center(msg_width), err=True)
        typer.echo(msg_line2.center(msg_width), err=True)
        typer.echo(msg_line3.center(msg_width), err=True)
        typer.echo("!" * msg_width, err=True)

    raise typer.Exit(exits.SUCCESS)


def main() -> None:
    try:
        _check_last_argv()
        app()
    except KeyboardInterrupt:
        raise typer.Exit(exits.GENERAL_ERROR) from None


if __name__ == "__main__":
    main()
