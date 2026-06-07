"""Curated data validation.

Validates curated YAML files against the schema and project rules.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


class ValidationError(Exception):
    """Raised when curated data validation fails."""


_ALLOWED_MAPPING_STATUSES = {"confirmed", "matched", "candidate", "rejected", "unmapped"}
_ALLOWED_RELEASE_PRECISIONS = {"day", "month", "year", "unknown"}
_MANUAL_SOURCE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]*:[a-zA-Z0-9_.-]+$")
_PRODUCT_SOURCE_KEY_RE = re.compile(
    r"^[a-z][a-z0-9_-]*:[a-z]{2,}(-[A-Z][a-z]+)?:[a-zA-Z0-9_.-]+$"
)


def validate_vendor_yaml(path: Path) -> list[str]:
    """Validate a curated vendor YAML file.

    Args:
        path: Path to the vendor YAML file.

    Returns:
        List of validation error messages. Empty if valid.
    """
    errors: list[str] = []

    if not path.is_file():
        errors.append(f"File not found: {path}")
        return errors

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error in {path}: {e}")
        return errors

    if not isinstance(data, dict):
        errors.append(f"Expected a YAML mapping (dict), got {type(data).__name__}: {path}")
        return errors

    # Check required fields
    required_fields = ["source_id", "display_name"]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field '{field}' in {path}")

    # Check records
    records = data.get("records", [])
    if not isinstance(records, list):
        errors.append(f"'records' must be a list in {path}")
        return errors

    seen_keys: set[str] = set()
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"Record {i} is not a mapping in {path}")
            continue

        key = record.get("manual_source_key")
        if not key:
            errors.append(f"Record {i} missing 'manual_source_key' in {path}")

        if key and key in seen_keys:
            errors.append(f"Duplicate manual_source_key '{key}' in {path}")
        if key:
            seen_keys.add(key)

        # Check required fields on each record
        for field in ["manual_source_id", "title", "brand"]:
            if field not in record:
                errors.append(f"Record '{key}' missing required field '{field}' in {path}")

        # Validate manual_source_key format
        if key and ":" not in str(key):
            errors.append(f"Record '{key}' has invalid manual_source_key format (expected 'source:id') in {path}")

    return errors


def validate_products_yaml(path: Path) -> list[str]:
    """Validate a curated products YAML file."""
    errors: list[str] = []

    if not path.is_file():
        errors.append(f"File not found: {path}")
        return errors

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error in {path}: {e}")
        return errors

    if not isinstance(data, dict):
        errors.append(f"Expected a YAML mapping (dict), got {type(data).__name__}: {path}")
        return errors

    for field in ["source_id", "display_name", "manufacturer"]:
        if field not in data:
            errors.append(f"Missing required field '{field}' in {path}")

    products = data.get("products", [])
    if not isinstance(products, list):
        errors.append(f"'products' must be a list in {path}")
        return errors

    seen_keys: dict[str, int] = {}
    file_source_id = str(data.get("source_id", ""))
    file_locale = str(data.get("locale", "ja"))
    for i, product in enumerate(products):
        product_path = f"products[{i}]"
        if not isinstance(product, dict):
            errors.append(f"{product_path} must be a mapping in {path}")
            continue

        product_id = product.get("product_id")
        if not product_id:
            errors.append(f"{product_path}.product_id is required in {path}")
        if "title" not in product:
            errors.append(f"{product_path}.title is required for product_id {product_id!r} in {path}")

        locale = str(product.get("locale", file_locale))
        product_source_id = str(product.get("product_source_id", product_id or ""))
        product_source_key = str(
            product.get("product_source_key")
            or f"{file_source_id}-product:{locale}:{product_source_id}"
        )
        if product_source_key in seen_keys:
            errors.append(
                f"{product_path}.product_source_key duplicates products[{seen_keys[product_source_key]}] "
                f"with value {product_source_key!r} in {path}"
            )
        else:
            seen_keys[product_source_key] = i
        if product_source_key and not _PRODUCT_SOURCE_KEY_RE.fullmatch(product_source_key):
            errors.append(
                f"{product_path}.product_source_key has invalid value {product_source_key!r} "
                f"(expected source-family:locale:id, e.g. hasegawa-product:ja:bk-001) in {path}"
            )

        release_date = product.get("release_date")
        if release_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(release_date)):
            errors.append(
                f"{product_path}.release_date has invalid value {release_date!r} "
                f"(expected YYYY-MM-DD, e.g. 2026-06-30) in {path}"
            )
        release_month = product.get("release_month")
        if release_month and not re.fullmatch(r"\d{4}-\d{2}", str(release_month)):
            errors.append(
                f"{product_path}.release_month has invalid value {release_month!r} "
                f"(expected YYYY-MM, e.g. 2026-06) in {path}"
            )
        precision = product.get("release_date_precision")
        if precision is not None and str(precision) not in _ALLOWED_RELEASE_PRECISIONS:
            errors.append(
                f"{product_path}.release_date_precision has invalid value {precision!r} "
                f"(expected one of: day, month, year, unknown) in {path}"
            )
        effective_precision = str(precision) if precision is not None else None
        if effective_precision is None and release_date:
            effective_precision = "day"
        elif effective_precision is None and release_month:
            effective_precision = "month"
        if effective_precision == "day" and not release_date:
            errors.append(f"{product_path}.release_date is required when release_date_precision is 'day' in {path}")
        if effective_precision in {"day", "month"} and not release_month:
            errors.append(
                f"{product_path}.release_month is required when release_date_precision is "
                f"{effective_precision!r} in {path}"
            )

        if "price_amount" in product:
            _validate_numeric(errors, product["price_amount"], f"{product_path}.price_amount", path)

        prices = product.get("prices", [])
        if prices is None:
            prices = []
        if not isinstance(prices, list):
            errors.append(f"{product_path}.prices must be a list in {path}")
        else:
            for price_index, price in enumerate(prices):
                price_path = f"{product_path}.prices[{price_index}]"
                if not isinstance(price, dict):
                    errors.append(f"{price_path} must be a mapping in {path}")
                    continue
                if "amount" not in price:
                    errors.append(f"{price_path}.amount is required in {path}")
                else:
                    _validate_numeric(
                        errors,
                        price["amount"],
                        f"{price_path}.amount",
                        path,
                    )

        manual_source_keys = product.get("manual_source_keys", [])
        if manual_source_keys is None:
            manual_source_keys = []
        if not isinstance(manual_source_keys, list):
            errors.append(f"{product_path}.manual_source_keys must be a list in {path}")
        else:
            for manual_index, manual_key in enumerate(manual_source_keys):
                manual_path = f"{product_path}.manual_source_keys[{manual_index}]"
                if not isinstance(manual_key, str) or not _MANUAL_SOURCE_KEY_RE.fullmatch(manual_key):
                    errors.append(
                        f"{manual_path} has invalid value {manual_key!r} "
                        f"(expected source:id, e.g. hasegawa:bk-001-manual) in {path}"
                    )

    return errors


def validate_overrides_yaml(path: Path, known_keys: set[str] | None = None) -> list[str]:
    """Validate curated overrides YAML file.

    Args:
        path: Path to the overrides YAML file.
        known_keys: Set of known manual_source_keys to validate override targets.

    Returns:
        List of validation error messages. Empty if valid.
    """
    errors: list[str] = []

    if not path.is_file():
        errors.append(f"File not found: {path}")
        return errors

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error in {path}: {e}")
        return errors

    if data is None:
        return []

    overrides = data.get("overrides", [])
    if not isinstance(overrides, list):
        errors.append(f"'overrides' must be a list in {path}")
        return errors

    for i, override in enumerate(overrides):
        if not isinstance(override, dict):
            errors.append(f"Override {i} is not a mapping in {path}")
            continue

        key = override.get("manual_source_key")
        if not key:
            errors.append(f"Override {i} missing 'manual_source_key' in {path}")
            continue

        if known_keys is not None and key not in known_keys:
            errors.append(f"Override target '{key}' not found in known records in {path}")

        if "set" not in override or not isinstance(override["set"], dict):
            errors.append(f"Override '{key}' missing or invalid 'set' field in {path}")

        if "reason" not in override:
            errors.append(f"Override '{key}' missing 'reason' field in {path}")

    return errors


def _validate_numeric(
    errors: list[str],
    value: str | int | float,
    label: str,
    path: Path,
) -> None:
    try:
        float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric (got {value!r}) in {path}")


def validate_mappings_yaml(path: Path) -> list[str]:
    """Validate curated product/manual mapping YAML file."""
    errors: list[str] = []

    if not path.is_file():
        errors.append(f"File not found: {path}")
        return errors

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error in {path}: {e}")
        return errors

    if data is None:
        return []
    if not isinstance(data, dict):
        errors.append(f"Expected a YAML mapping (dict), got {type(data).__name__}: {path}")
        return errors

    mappings = data.get("mappings", [])
    if not isinstance(mappings, list):
        errors.append(f"'mappings' must be a list in {path}")
        return errors

    seen: set[tuple[str, str | None, str | None]] = set()
    for i, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            errors.append(f"Mapping {i} is not a mapping in {path}")
            continue

        product_key = mapping.get("product_key")
        if not product_key:
            errors.append(f"Mapping {i} missing 'product_key' in {path}")

        link_keys = [
            mapping.get("zh_schedule_key"),
            mapping.get("ja_schedule_key"),
            mapping.get("en_schedule_key"),
            mapping.get("manual_source_key"),
        ]
        if not any(link_keys):
            errors.append(
                f"Mapping {i} must include at least one source/manual key in {path}"
            )

        status = mapping.get("status", "confirmed")
        if status not in _ALLOWED_MAPPING_STATUSES:
            errors.append(f"Mapping {i} has invalid status '{status}' in {path}")

        if status == "confirmed" and not mapping.get("reason") and not mapping.get("method"):
            errors.append(
                f"Confirmed mapping {i} requires 'reason' or 'method' in {path}"
            )

        confidence = mapping.get("confidence")
        if confidence is not None:
            try:
                confidence_float = float(confidence)
            except (TypeError, ValueError):
                errors.append(f"Mapping {i} confidence must be numeric in {path}")
            else:
                if not 0.0 <= confidence_float <= 1.0:
                    errors.append(f"Mapping {i} confidence must be 0.0-1.0 in {path}")

        identity = (
            str(product_key) if product_key else "",
            mapping.get("zh_schedule_key"),
            mapping.get("manual_source_key"),
        )
        if identity in seen:
            errors.append(f"Duplicate mapping {i} for {identity} in {path}")
        seen.add(identity)

    return errors


def validate_curated_directory(curated_dir: Path) -> dict[str, list[str]]:
    """Validate all curated YAML files in a directory.

    Args:
        curated_dir: Path to the curated/ directory.

    Returns:
        Dict mapping file paths to lists of validation error messages.
    """
    results: dict[str, list[str]] = {}

    vendors_dir = curated_dir / "vendors"
    all_keys: set[str] = set()

    # Validate vendor files
    if vendors_dir.is_dir():
        for yaml_file in sorted(vendors_dir.glob("*.yaml")):
            errors = validate_vendor_yaml(yaml_file)
            if errors:
                results[str(yaml_file)] = errors
            # Collect keys for override validation
            try:
                from plamoindex.curated.loader import load_curated_vendor

                vendor = load_curated_vendor(yaml_file)
                for record in vendor.records:
                    all_keys.add(record.manual_source_key)
            except Exception:
                pass

    products_dir = curated_dir / "products"
    if products_dir.is_dir():
        for yaml_file in sorted(products_dir.glob("*.yaml")):
            errors = validate_products_yaml(yaml_file)
            if errors:
                results[str(yaml_file)] = errors

    # Validate overrides
    overrides_path = curated_dir / "overrides.yaml"
    if overrides_path.is_file():
        errors = validate_overrides_yaml(overrides_path, all_keys)
        if errors:
            results[str(overrides_path)] = errors

    # Validate aliases
    aliases_path = curated_dir / "aliases.yaml"
    if aliases_path.is_file():
        try:
            with open(aliases_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data is not None and not isinstance(data, dict):
                results[str(aliases_path)] = ["Expected a YAML mapping at top level"]
            elif data is not None:
                aliases = data.get("aliases", {})
                if not isinstance(aliases, dict):
                    results[str(aliases_path)] = ["'aliases' must be a mapping"]
        except yaml.YAMLError as e:
            results[str(aliases_path)] = [f"YAML parse error: {e}"]

    # Validate mappings
    mappings_path = curated_dir / "mappings.yaml"
    if mappings_path.is_file():
        errors = validate_mappings_yaml(mappings_path)
        if errors:
            results[str(mappings_path)] = errors

    return results
