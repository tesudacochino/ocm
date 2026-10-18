"""
opencode_config_manager - Gestor de providers locales para opencode
"""

from ._version import __version__
from .config import ConfigManager, ConfigUI
from .api import ProviderScanner, ScanResult

__all__ = ["__version__", "ConfigManager", "ConfigUI", "ProviderScanner", "ScanResult"]
