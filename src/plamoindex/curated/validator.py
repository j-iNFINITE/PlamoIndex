"""Curated data validation.

Validates curated YAML files against the schema and project rules.
"""

from __future__ import annotations

from pathlib import Path

import yaml


class ValidationError(Exception):
    """Raised when curated data validation fails."""


_ALLOWED_MAPPING_STATUSES = {"confirmed", "matched", "candidate", "rejected", "unmapped"}


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
