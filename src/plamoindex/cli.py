"""CLI entry point for plamoindex.

Commands:
- sources list: List all registered source plugins.
- collect: Collect raw records from source plugins.
- curated validate: Validate curated YAML files.
- build: Build dataset from raw and curated data.
- sync: Collect + build in one step.
- validate: Validate an existing dist directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from plamoindex import __version__
from plamoindex.config import load_config
from plamoindex.curated.validator import validate_curated_directory
from plamoindex.dataset import build_dataset
from plamoindex.sources.registry import get_source, list_sources


def _resolve_sources(source: tuple[str, ...]) -> list[str]:
    """Resolve the --source option to a list of source IDs.

    If no sources are specified, returns all registered sources.
    If 'all' is specified, returns all registered sources.
    Otherwise returns the specified source IDs.

    Args:
        source: Tuple of source IDs from the --source option.

    Returns:
        List of resolved source IDs.
    """
    if not source:
        return list_sources()
    source_list = list(source)
    if "all" in source_list:
        return list_sources()
    return source_list


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="plamoindex")
def main() -> None:
    """plamoindex - Metadata index generator for plastic model manual sources."""


@main.group()
def sources() -> None:
    """Manage source plugins."""


@sources.command("list")
def sources_list() -> None:
    """List all registered source plugins."""
    source_ids = list_sources()
    if not source_ids:
        click.echo("No sources registered.")
        return

    click.echo("Registered sources:")
    for sid in source_ids:
        try:
            plugin = get_source(sid)
            click.echo(f"  {sid:<20} {plugin.display_name}")
        except KeyError:
            click.echo(f"  {sid:<20} <error loading>")


@main.command()
@click.option("--source", multiple=True, help="Source plugin(s) to collect from (default: all)")
@click.option(
    "--raw",
    "raw_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Path to store raw collection data (default: data/raw/)",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to plamoindex.yml config file",
)
def collect(source: tuple[str, ...], raw_dir: str | None, config_path: str | None) -> None:
    """Collect raw records from source plugins."""
    cfg_path = Path(config_path) if config_path else None
    config = load_config(cfg_path)

    source_ids = _resolve_sources(source)
    raw_path = Path(raw_dir) if raw_dir else Path(config.raw.path)
    raw_path.mkdir(parents=True, exist_ok=True)

    click.echo(f"Collecting from {len(source_ids)} source(s) into {raw_path}...")

    total_manuals = 0
    total_product_sources = 0
    total_products = 0
    total_relationships = 0
    failures = 0

    for sid in source_ids:
        try:
            plugin = get_source(sid)

            # Configure plugin with raw path
            if hasattr(plugin, "configure"):
                plugin.configure(config, raw_path)

            manuals = plugin.collect_manuals()
            product_sources = plugin.collect_product_sources()
            products = plugin.collect_products()
            relationships = plugin.collect_relationships()

            click.echo(f"  {sid}:")
            click.echo(f"    manuals: {len(manuals)}")
            click.echo(f"    product_sources: {len(product_sources)}")
            click.echo(f"    products: {len(products)}")
            click.echo(f"    relationships: {len(relationships)}")

            total_manuals += len(manuals)
            total_product_sources += len(product_sources)
            total_products += len(products)
            total_relationships += len(relationships)
        except KeyError as exc:
            click.echo(f"  {sid}: ERROR - {exc}", err=True)
            failures += 1
        except Exception as exc:
            click.echo(f"  {sid}: FAILED - {exc}", err=True)
            failures += 1

    click.echo("\nCollection complete.")
    click.echo(f"  Total manuals: {total_manuals}")
    click.echo(f"  Total product_sources: {total_product_sources}")
    click.echo(f"  Total products: {total_products}")
    click.echo(f"  Total relationships: {total_relationships}")
    if failures:
        click.echo(f"  Failures: {failures}", err=True)
        sys.exit(1)


@main.group()
def curated() -> None:
    """Manage curated YAML data."""


@curated.command("validate")
@click.argument("curated_dir", type=click.Path(exists=True, file_okay=False), default="curated")
def curated_validate(curated_dir: str) -> None:
    """Validate curated YAML files in CURATED_DIR."""
    cdir = Path(curated_dir)
    results = validate_curated_directory(cdir)

    if not results:
        click.echo("All curated files valid.")
        return

    for file_path, errors in results.items():
        click.echo(f"Errors in {file_path}:", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)

    sys.exit(1)


@main.command()
@click.option("--source", multiple=True, help="Source plugins to include (default: all)")
@click.option(
    "--curated",
    "curated_dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Path to curated/ directory",
)
@click.option(
    "--raw",
    "raw_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Path to raw/ collection data directory",
)
@click.option(
    "--dist",
    "dist_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Path to dist/ output directory",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to plamoindex.yml config file",
)
def build(
    source: tuple[str, ...],
    curated_dir: str | None,
    raw_dir: str | None,
    dist_dir: str | None,
    config_path: str | None,
) -> None:
    """Build dataset from raw and curated data."""
    cfg_path = Path(config_path) if config_path else None
    config = load_config(cfg_path)

    # If sources specified, resolve them; otherwise None = all sources
    resolved = _resolve_sources(source) if source else None
    source_ids = resolved
    cdir = Path(curated_dir) if curated_dir else None
    rdir = Path(raw_dir) if raw_dir else None
    ddir = Path(dist_dir) if dist_dir else None

    click.echo("Building dataset...")

    result = build_dataset(
        config=config,
        source_ids=source_ids,
        curated_dir=cdir,
        dist_dir=ddir,
        raw_dir=rdir,
    )

    for sid, status in result.source_statuses.items():
        if status.get("status") == "failed":
            click.echo(f"  Source '{sid}': FAILED - {status.get('error', 'unknown error')}", err=True)
        else:
            click.echo(f"  Source '{sid}': {status.get('record_count', 0)} records")

    if result.errors:
        click.echo(f"\nErrors ({len(result.errors)}):", err=True)
        for error in result.errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)

    if result.index_data:
        counts = result.index_data.get("counts", {})
        click.echo("\nBuild complete:")
        click.echo(f"  Total manuals: {counts.get('total', 0)}")
        click.echo(f"  Total products: {counts.get('products', 0)}")
        click.echo(f"  Total relationships: {counts.get('relationships', 0)}")
        click.echo(f"  Total product_sources: {counts.get('product_sources', 0)}")
    else:
        click.echo("\nBuild did not produce output (check errors above).", err=True)


@main.command()
@click.option("--source", multiple=True, help="Source plugins to include (default: all)")
@click.option(
    "--curated",
    "curated_dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Path to curated/ directory",
)
@click.option(
    "--raw",
    "raw_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Path to raw/ collection data directory",
)
@click.option(
    "--dist",
    "dist_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Path to dist/ output directory",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to plamoindex.yml config file",
)
def sync(
    source: tuple[str, ...],
    curated_dir: str | None,
    raw_dir: str | None,
    dist_dir: str | None,
    config_path: str | None,
) -> None:
    """Collect from sources and build dataset in one step."""
    ctx = click.get_current_context()
    # Run collect first
    ctx.invoke(
        collect,
        source=source,
        raw_dir=raw_dir,
        config_path=config_path,
    )
    # Then build
    ctx.invoke(
        build,
        source=source,
        curated_dir=curated_dir,
        raw_dir=raw_dir,
        dist_dir=dist_dir,
        config_path=config_path,
    )


@main.command()
@click.option(
    "--dist",
    "dist_dir",
    type=click.Path(exists=True, file_okay=False),
    default="dist",
    help="Path to dist/ directory to validate",
)
def validate(dist_dir: str) -> None:
    """Validate an existing dist directory."""
    ddir = Path(dist_dir)

    expected_files = [
        "index.json",
        "schema.v1.json",
        "manuals.latest.json",
        "manuals.compact.v1.json",
        "manuals.bandai.v1.json",
        "manuals.kotobukiya.v1.json",
        "manuals.curated.v1.json",
        "sources.json",
        "checksums.json",
        "products.latest.json",
        "products.compact.v1.json",
        "products.bandai.v1.json",
        "products.kotobukiya.v1.json",
        "product-sources.bandai.v1.json",
        "product-sources.kotobukiya.v1.json",
        "relationships.v1.json",
    ]

    missing = [fn for fn in expected_files if not (ddir / fn).is_file()]

    if missing:
        click.echo("Missing files:", err=True)
        for fn in missing:
            click.echo(f"  - {fn}", err=True)
        sys.exit(1)

    click.echo("All required files present.")

    # Validate index.json structure
    try:
        with open(ddir / "index.json", encoding="utf-8") as fh:
            index = json.load(fh)
    except (json.JSONDecodeError, IOError) as exc:
        click.echo(f"Invalid index.json: {exc}", err=True)
        sys.exit(1)

    required_keys = [
        "schema_version", "dataset_version", "generator_version",
        "generated_at", "counts", "files", "sources",
    ]
    missing_keys = [k for k in required_keys if k not in index]
    if missing_keys:
        click.echo(f"index.json missing keys: {missing_keys}", err=True)
        sys.exit(1)

    # Validate counts include product/relationship counts
    counts = index.get("counts", {})
    for count_key in ("total", "products", "product_sources", "relationships"):
        if count_key not in counts:
            click.echo(f"index.json counts missing '{count_key}'", err=True)
            sys.exit(1)

    # Validate checksums
    checksums_path = ddir / "checksums.json"
    try:
        with open(checksums_path, encoding="utf-8") as fh:
            checksums = json.load(fh)
    except (json.JSONDecodeError, IOError) as exc:
        click.echo(f"Invalid checksums.json: {exc}", err=True)
        sys.exit(1)

    # checksums.json cannot contain its own hash, so exclude it from the check
    files_with_checksum = [fn for fn in expected_files if fn != "checksums.json"]
    missing_checksums = [fn for fn in files_with_checksum if fn not in checksums]
    if missing_checksums:
        click.echo(f"Missing checksums for: {missing_checksums}", err=True)
        sys.exit(1)

    # Validate each JSON file is valid
    for fn in expected_files:
        try:
            with open(ddir / fn, encoding="utf-8") as fh:
                json.load(fh)
        except (json.JSONDecodeError, IOError) as exc:
            click.echo(f"Invalid {fn}: {exc}", err=True)
            sys.exit(1)

    click.echo(f"index.json structure valid ({counts.get('total', 0)} manuals, "
               f"{counts.get('products', 0)} products, "
               f"{counts.get('relationships', 0)} relationships).")


if __name__ == "__main__":
    main()
