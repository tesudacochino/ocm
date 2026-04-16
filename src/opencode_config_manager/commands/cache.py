"""
Comandos de gestión de caché.
"""

from datetime import datetime

from ..config import ConfigManager, ConfigUI
from .provider import print_provider_info


def cmd_show_cache(manager: ConfigManager, args):
    """Mostrar estado de la caché en formato opencode.ai."""
    manager.load_cache()
    manager.load_config()

    provider = manager.config_data.get("provider")

    cache_timestamp = manager.cache_data.get("cache_timestamp", 0)
    timestamp_str = datetime.fromtimestamp(cache_timestamp) if cache_timestamp else "Nunca"
    ConfigUI.print_header(f"Estado de Caché (actualizada {timestamp_str})")

    if provider:
        print(f"Provider: {provider}")
    print()

    # Mostrar caché de todos los providers
    for provider_name, cache_info in manager.cache_data.get("providers", {}).items():
        print_provider_info(provider_name, cache_info)


def cmd_cache(manager: ConfigManager, args):
    """Gestionar caché."""
    manager.load_cache()

    if args.clear:
        if ConfigUI.ask_yes_no("¿Borrar toda la caché?"):
            manager.cache_data = {"cache_timestamp": 0, "providers": {}}
            manager.save_cache()
            ConfigUI.print_success("Caché borrada.")
    elif args.show:
        cmd_show_cache(manager, args)
    else:
        print("Uso: cache --show [PROVIDER]  |  cache --clear")
