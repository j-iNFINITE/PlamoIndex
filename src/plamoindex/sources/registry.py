"""Source plugin registry.

Manages registration and lookup of built-in source plugins.
External plugins via entry points can be added later.
"""

from __future__ import annotations

from plamoindex.sources.base import SourcePlugin

# Built-in sources are imported lazily to avoid circular imports.
_BUILTIN_SOURCE_CLASSES: dict[str, type[SourcePlugin]] = {}

# Instance cache: source_id -> SourcePlugin
_instances: dict[str, SourcePlugin] = {}


def register_builtin(source_id: str, plugin_class: type[SourcePlugin]) -> None:
    """Register a built-in source plugin class.

    Args:
        source_id: Unique source identifier (e.g., 'bandai').
        plugin_class: SourcePlugin subclass.
    """
    _BUILTIN_SOURCE_CLASSES[source_id] = plugin_class


def get_source(source_id: str) -> SourcePlugin:
    """Get a source plugin instance by source_id.

    Instances are cached after first creation.

    Args:
        source_id: Source identifier.

    Returns:
        A SourcePlugin instance.

    Raises:
        KeyError: If source_id is not registered.
    """
    if source_id in _instances:
        return _instances[source_id]

    if source_id not in _BUILTIN_SOURCE_CLASSES:
        available = ", ".join(sorted(_BUILTIN_SOURCE_CLASSES))
        raise KeyError(f"Unknown source '{source_id}'. Available: {available}")

    plugin = _BUILTIN_SOURCE_CLASSES[source_id]()
    _instances[source_id] = plugin
    return plugin


def list_sources() -> list[str]:
    """Return sorted list of registered source identifiers."""
    return sorted(_BUILTIN_SOURCE_CLASSES.keys())


def list_source_plugins() -> list[SourcePlugin]:
    """Return sorted list of source plugin instances."""
    return [get_source(sid) for sid in list_sources()]


def reset() -> None:
    """Clear all cached instances and registry (for testing)."""
    _instances.clear()
    _BUILTIN_SOURCE_CLASSES.clear()
