"""Source plugins for plamoindex.

Every source is a plugin. Built-in sources are registered on import.
"""

from plamoindex.sources.bandai import BandaiSource
from plamoindex.sources.kotobukiya import KotobukiyaSource
from plamoindex.sources.registry import register_builtin

register_builtin("bandai", BandaiSource)
register_builtin("kotobukiya", KotobukiyaSource)

__all__ = [
    "BandaiSource",
    "KotobukiyaSource",
]
