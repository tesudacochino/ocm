"""
opencode_config_manager - Gestor de providers locales para opencode
"""

__version__ = "0.1.0"

from .config import ConfigManager, ConfigUI
from .api import ProviderScanner, ScanResult

__all__ = ["ConfigManager", "ConfigUI", "ProviderScanner", "ScanResult"]
