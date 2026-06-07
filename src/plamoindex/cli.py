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
from typing import Any

import click
import yaml

from plamoindex import __version__
from plamoindex.config import load_config
from plamoindex.curated.loader import (
    curated_product_entry_to_mappings,
    curated_product_entry_to_product_source_record,
    load_curated_products,
)
from plamoindex.curated.validator import validate_curated_directory, validate_products_yaml
from plamoindex.dataset import build_dataset, collect_sources
from plamoindex.merge import merge_product_sources
from plamoindex.output.checksums import sha256_hex
from plamoindex.output.writer import CHECKSUMMED_DATASET_FILES, PUBLISHED_DATASET_FILES
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


def _optional_prompt(label: str, default: str | None = None) -> str | None:
    """Prompt for an optional string value."""
    value = click.prompt(
        label,
        default=default or "",
        show_default=bool(default),
    )
    text = str(value).strip()
    return text or None


def _select_or_enter(
    label: str,
    choices: list[str],
    default: str | None = None,
) -> str | None:
    """Prompt with known choices while allowing custom input."""
    unique_choices = sorted({choice for choice in choices if choice})
    if unique_choices:
        click.echo(f"已有{label}：")
        for index, choice in enumerate(unique_choices, start=1):
            click.echo(f"  {index}. {choice}")
        value = click.prompt(
            f"{label}（输入编号选择已有项，或输入新值）",
            default=default or "",
            show_default=bool(default),
        )
        text = str(value).strip()
        if text.isdigit():
            choice_index = int(text)
            if 1 <= choice_index <= len(unique_choices):
                return unique_choices[choice_index - 1]
        return text or None
    return _optional_prompt(label, default)


def _split_keys(value: str | None) -> list[str] | None:
    """Split a comma-separated key list into normalized strings."""
    if not value:
        return None
    keys = [key.strip() for key in value.split(",") if key.strip()]
    return keys or None


def _string_value(value: Any) -> str | None:
    """Return a non-empty string from YAML data."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _taxonomy_label(value: Any) -> str | None:
    """Extract a human label from string or mapping taxonomy YAML."""
    if isinstance(value, str):
        return _string_value(value)
    if isinstance(value, dict):
        for key in ("label", "line_name", "slug", "id"):
            label = _string_value(value.get(key))
            if label:
                return label
    return None


def _read_curated_choice_data(curated_dir: Path) -> dict[str, Any]:
    """Read existing curated data to offer product-entry choices."""
    profiles: dict[str, dict[str, str]] = {}
    manufacturers: set[str] = set()
    series: set[str] = set()
    scales: set[str] = set()

    products_dir = curated_dir / "products"
    if products_dir.is_dir():
        for yaml_file in sorted(products_dir.glob("*.yaml")):
            data = _load_yaml_mapping(yaml_file)
            source_id = _string_value(data.get("source_id"))
            display_name = _string_value(data.get("display_name"))
            manufacturer = _string_value(data.get("manufacturer"))
            locale = _string_value(data.get("locale"))
            market = _string_value(data.get("market"))
            if source_id:
                profile: dict[str, str] = {"source_id": source_id}
                for key, value in (
                    ("display_name", display_name),
                    ("manufacturer", manufacturer),
                    ("locale", locale),
                    ("market", market),
                ):
                    if value:
                        profile[key] = value
                profiles[source_id] = profile
            if manufacturer:
                manufacturers.add(manufacturer)
            _collect_product_choices(data.get("products"), series, scales)

    vendors_dir = curated_dir / "vendors"
    if vendors_dir.is_dir():
        for yaml_file in sorted(vendors_dir.glob("*.yaml")):
            data = _load_yaml_mapping(yaml_file)
            source_id = _string_value(data.get("source_id"))
            display_name = _string_value(data.get("display_name"))
            records = data.get("records")
            first_brand = _first_record_string(records, "brand")
            if first_brand:
                manufacturers.add(first_brand)
            if source_id and source_id not in profiles:
                profile = {"source_id": source_id}
                if display_name:
                    profile["display_name"] = display_name
                if first_brand:
                    profile["manufacturer"] = first_brand
                profiles[source_id] = profile
            _collect_vendor_record_choices(records, series, scales)

    return {
        "profiles": profiles,
        "manufacturers": sorted(manufacturers),
        "series": sorted(series),
        "scales": sorted(scales),
    }


def _collect_product_choices(products: Any, series: set[str], scales: set[str]) -> None:
    if not isinstance(products, list):
        return
    for product in products:
        if not isinstance(product, dict):
            continue
        series_label = _taxonomy_label(product.get("series"))
        if series_label:
            series.add(series_label)
        specs = product.get("specs")
        if isinstance(specs, dict):
            scale = _string_value(specs.get("scale"))
            if scale:
                scales.add(scale)


def _collect_vendor_record_choices(records: Any, series: set[str], scales: set[str]) -> None:
    if not isinstance(records, list):
        return
    for record in records:
        if not isinstance(record, dict):
            continue
        series_value = _string_value(record.get("series"))
        if series_value:
            series.add(series_value)
        scale = _string_value(record.get("scale"))
        if scale:
            scales.add(scale)


def _first_record_string(records: Any, key: str) -> str | None:
    if not isinstance(records, list):
        return None
    for record in records:
        if isinstance(record, dict):
            value = _string_value(record.get(key))
            if value:
                return value
    return None


def _select_source_profile(choice_data: dict[str, Any]) -> dict[str, str] | None:
    """Select an existing curated source profile, or return None for a new one."""
    raw_profiles = choice_data.get("profiles", {})
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        return None

    profiles = [
        profile
        for profile in raw_profiles.values()
        if isinstance(profile, dict) and isinstance(profile.get("source_id"), str)
    ]
    profiles.sort(key=lambda profile: str(profile["source_id"]))
    click.echo("已有数据源：")
    for index, profile in enumerate(profiles, start=1):
        manufacturer = profile.get("manufacturer") or profile.get("display_name") or ""
        suffix = f" ({manufacturer})" if manufacturer else ""
        click.echo(f"  {index}. {profile['source_id']}{suffix}")
    value = click.prompt("数据源 ID（输入编号选择已有项，或输入新值）", default="", show_default=False)
    text = str(value).strip()
    if text.isdigit():
        choice_index = int(text)
        if 1 <= choice_index <= len(profiles):
            return {str(key): str(value) for key, value in profiles[choice_index - 1].items()}
    return {"source_id": text} if text else None


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load a YAML mapping or return an empty mapping for missing files."""
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise click.ClickException(f"{path} 应为 YAML mapping。")
    return data


def _write_yaml_mapping(path: Path, data: dict[str, Any]) -> None:
    """Write a YAML mapping using repository-friendly formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


def _show_curated_product_summary(path: Path, product_id: str) -> None:
    """Show the generated keys and mappings for a newly-added curated product."""
    product_file = load_curated_products(path)
    matching_entries = [
        entry for entry in product_file.products if entry.product_id == product_id
    ]
    if not matching_entries:
        return

    entry = matching_entries[-1]
    product_source = curated_product_entry_to_product_source_record(entry, product_file)
    products, _ = merge_product_sources([product_source])
    product_key = products[0].product_key if products else "<unknown>"
    mappings = curated_product_entry_to_mappings(entry, product_file)

    click.echo("写入摘要：")
    click.echo(f"  文件: {path}")
    click.echo(f"  product_source_key: {product_source.product_source_key}")
    click.echo(f"  product_key: {product_key}")
    if mappings:
        click.echo(f"  manual mappings: {len(mappings)}")
        for mapping in mappings:
            click.echo(f"    {mapping.manual_source_key} -> {mapping.product_key}")
    else:
        click.echo("  manual mappings: 0")


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

    result = collect_sources(config, source_ids=source_ids, raw_dir=raw_path)

    for sid, status in result.source_statuses.items():
        click.echo(f"  {sid}:")
        if status.get("status") == "failed":
            click.echo(f"    FAILED: {status.get('error', 'unknown error')}", err=True)
        else:
            click.echo(f"    manuals: {status.get('record_count', 0)}")
            click.echo(f"    product_sources: {status.get('product_source_count', 0)}")
            click.echo(f"    relationships: {status.get('relationship_count', 0)}")

    click.echo("\nCollection complete.")
    click.echo(f"  Total manuals: {len(result.manuals)}")
    click.echo(f"  Total product_sources: {len(result.product_sources)}")
    click.echo(f"  Total relationships: {len(result.relationships)}")
    if result.errors:
        click.echo(f"  Failures: {len(result.errors)}", err=True)
        if not result.manuals and not result.product_sources and not result.relationships:
            sys.exit(1)


@main.group()
def curated() -> None:
    """Manage curated YAML data."""


@curated.group("product")
def curated_product() -> None:
    """Manage curated product metadata."""


@curated_product.command("add")
@click.option(
    "--curated",
    "curated_dir",
    type=click.Path(file_okay=False),
    default="curated",
    help="Path to curated/ directory.",
)
@click.option("--source-id", default=None, help="Curated source id, e.g. hasegawa.")
@click.option("--display-name", default=None, help="Human-readable source name.")
@click.option("--manufacturer", default=None, help="Manufacturer name used in output.")
@click.option("--locale", default="ja", show_default=True, help="Default locale for this product.")
@click.option("--market", default="jp", show_default=True, help="Default market for this product.")
@click.option("--product-id", default=None, help="Stable source-local product id.")
@click.option("--title", default=None, help="Product title.")
def curated_product_add(
    curated_dir: str,
    source_id: str | None,
    display_name: str | None,
    manufacturer: str | None,
    locale: str,
    market: str,
    product_id: str | None,
    title: str | None,
) -> None:
    """Interactively add one product to curated/products/<source-id>.yaml."""
    cdir = Path(curated_dir)
    choice_data = _read_curated_choice_data(cdir)
    source_profile = None if source_id else _select_source_profile(choice_data)
    source_id = source_id or (source_profile or {}).get("source_id") or click.prompt("数据源 ID", type=str)
    display_name = (
        display_name
        or (source_profile or {}).get("display_name")
        or click.prompt("显示名称", default=source_id)
    )
    manufacturer = (
        manufacturer
        or (source_profile or {}).get("manufacturer")
        or _select_or_enter(
            "厂商",
            choice_data.get("manufacturers", []),
            display_name.upper(),
        )
    )
    if manufacturer is None:
        raise click.ClickException("厂商不能为空。")
    locale = (source_profile or {}).get("locale") or locale
    market = (source_profile or {}).get("market") or market
    locale = click.prompt("语言/地区代码", default=locale)
    market = click.prompt("市场", default=market)
    product_id = product_id or click.prompt("产品 ID", type=str)
    title = title or click.prompt("产品名称", type=str)

    manufacturer_item_code = _optional_prompt("厂商货号")
    product_url = _optional_prompt("产品页面 URL")
    image_url = _optional_prompt("图片 URL")
    category = _optional_prompt("类别")
    brand_line = _optional_prompt("产品线")
    series = _select_or_enter("系列", choice_data.get("series", []))
    product_series = _optional_prompt("产品系列")
    release_month = _optional_prompt("发售月份（YYYY-MM）")
    price_amount_raw = _optional_prompt("价格")
    price_currency = None
    price_tax_included = True
    if price_amount_raw:
        price_currency = _optional_prompt("货币", "JPY")
        price_tax_included = click.confirm("价格是否含税？", default=True)
    scale = _select_or_enter("比例", choice_data.get("scales", []))
    manual_keys = _split_keys(
        _optional_prompt("关联说明书 key（多个用英文逗号分隔）")
    )

    product: dict[str, Any] = {
        "product_id": product_id,
        "title": title,
    }
    for key, value in (
        ("manufacturer_item_code", manufacturer_item_code),
        ("product_url", product_url),
        ("image_url", image_url),
        ("category", category),
        ("brand_line", brand_line),
        ("series", series),
        ("product_series", product_series),
        ("release_month", release_month),
        ("price_currency", price_currency),
        ("manual_source_keys", manual_keys),
    ):
        if value:
            product[key] = value

    if price_amount_raw:
        try:
            product["price_amount"] = float(price_amount_raw)
        except ValueError as exc:
            raise click.ClickException("价格必须是数字。") from exc
        product["price_tax_included"] = price_tax_included

    if scale:
        product["specs"] = {"scale": scale}

    path = cdir / "products" / f"{source_id}.yaml"
    data = _load_yaml_mapping(path)
    if not data:
        data = {
            "source_id": source_id,
            "display_name": display_name,
            "manufacturer": manufacturer,
            "locale": locale,
            "market": market,
            "products": [],
        }
    else:
        data.setdefault("source_id", source_id)
        data.setdefault("display_name", display_name)
        data.setdefault("manufacturer", manufacturer)
        data.setdefault("locale", locale)
        data.setdefault("market", market)
        data.setdefault("products", [])

    products = data.get("products")
    if not isinstance(products, list):
        raise click.ClickException(f"{path} 中的 'products' 必须是列表。")
    if any(isinstance(existing, dict) and existing.get("product_id") == product_id for existing in products):
        raise click.ClickException(f"产品 ID '{product_id}' 已存在于 {path}。")

    products.append(product)
    _write_yaml_mapping(path, data)

    errors = validate_products_yaml(path)
    if errors:
        for error in errors:
            click.echo(f"  - {error}", err=True)
        raise click.ClickException(f"产品文件校验失败：{path}")

    click.echo(f"已添加产品 '{product_id}' 到 {path}")
    _show_curated_product_summary(path, str(product_id))


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
    raw_path = raw_dir
    ctx.invoke(
        collect,
        source=source,
        raw_dir=raw_path,
        config_path=config_path,
    )
    ctx.invoke(
        build,
        source=source,
        curated_dir=curated_dir,
        raw_dir=raw_path,
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

    missing = [fn for fn in PUBLISHED_DATASET_FILES if not (ddir / fn).is_file()]

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

    missing_checksums = [fn for fn in CHECKSUMMED_DATASET_FILES if fn not in checksums]
    if missing_checksums:
        click.echo(f"Missing checksums for: {missing_checksums}", err=True)
        sys.exit(1)

    mismatched_checksums = []
    for fn in CHECKSUMMED_DATASET_FILES:
        actual = sha256_hex(ddir / fn)
        expected = checksums.get(fn)
        if expected != actual:
            mismatched_checksums.append(fn)

    if mismatched_checksums:
        click.echo(f"Checksum mismatch for: {mismatched_checksums}", err=True)
        sys.exit(1)

    # Validate each JSON file is valid
    for fn in PUBLISHED_DATASET_FILES:
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
