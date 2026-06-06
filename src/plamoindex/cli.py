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

import sys
from pathlib import Path

import click

from plamoindex import __version__
from plamoindex.config import load_config
from plamoindex.curated.validator import validate_curated_directory
from plamoindex.dataset import build_dataset
from plamoindex.sources.registry import get_source, list_sources


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
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to plamoindex.yml config file",
)
def collect(source: tuple[str, ...], config_path: str | None) -> None:
    """Collect raw records from source plugins."""
    source_ids = list(source) if source else list_sources()

    click.echo(f"Collecting from {len(source_ids)} source(s)...")
    for sid in source_ids:
        try:
            plugin = get_source(sid)
            manuals = plugin.collect_manuals()
            product_sources = plugin.collect_product_sources()
            products = plugin.collect_products()
            relationships = plugin.collect_relationships()

            click.echo(f"  {sid}:")
            click.echo(f"    manuals: {len(manuals)}")
            click.echo(f"    product_sources: {len(product_sources)}")
            click.echo(f"    products: {len(products)}")
            click.echo(f"    relationships: {len(relationships)}")
        except KeyError as exc:
            click.echo(f"  {sid}: ERROR - {exc}", err=True)
        except Exception as exc:
            click.echo(f"  {sid}: FAILED - {exc}", err=True)

    click.echo("Collection complete.")


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
    dist_dir: str | None,
    config_path: str | None,
) -> None:
    """Build dataset from raw and curated data."""
    cfg_path = Path(config_path) if config_path else None
    config = load_config(cfg_path)

    source_ids = list(source) if source else None
    cdir = Path(curated_dir) if curated_dir else None
    ddir = Path(dist_dir) if dist_dir else None

    click.echo("Building dataset...")

    result = build_dataset(
        config=config,
        source_ids=source_ids,
        curated_dir=cdir,
        dist_dir=ddir,
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
        click.echo(f"  Total products: {len(result.products)}")
        click.echo(f"  Total relationships: {len(result.relationships)}")
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
    dist_dir: str | None,
    config_path: str | None,
) -> None:
    """Collect from sources and build dataset in one step."""
    ctx = click.get_current_context()
    ctx.invoke(build, source=source, curated_dir=curated_dir, dist_dir=dist_dir, config_path=config_path)


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
    ]

    missing = [fn for fn in expected_files if not (ddir / fn).is_file()]

    if missing:
        click.echo("Missing files:", err=True)
        for fn in missing:
            click.echo(f"  - {fn}", err=True)
        sys.exit(1)

    click.echo("All required files present.")

    # Validate index.json structure
    import json

    try:
        with open(ddir / "index.json", encoding="utf-8") as fh:
            index = json.load(fh)
    except (json.JSONDecodeError, IOError) as exc:
        click.echo(f"Invalid index.json: {exc}", err=True)
        sys.exit(1)

    required_keys = ["schema_version", "dataset_version", "generator_version", "generated_at", "counts"]
    missing_keys = [k for k in required_keys if k not in index]
    if missing_keys:
        click.echo(f"index.json missing keys: {missing_keys}", err=True)
        sys.exit(1)

    click.echo("index.json structure valid.")


if __name__ == "__main__":
    main()
