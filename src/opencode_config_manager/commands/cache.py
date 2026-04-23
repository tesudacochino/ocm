"""
Comandos de gestión de caché (provider_cache.json).
"""

from datetime import datetime

from ..config import ConfigManager, ConfigUI
from .provider import print_provider_cache_info


def cmd_cache_list(manager: ConfigManager, args):
    """Listar providers en la caché."""
    manager.load_cache()

    cache_timestamp = manager.cache_data.get("cache_timestamp", 0)
    timestamp_str = datetime.fromtimestamp(cache_timestamp) if cache_timestamp else "Nunca"
    ConfigUI.print_header(f"Providers en Caché (actualizada {timestamp_str})")

    providers = manager.cache_data.get("providers", {})
    if not providers:
        print("No hay providers en caché.")
        print("Ejecuta: ocm provider new  o  ocm cache update [PROVIDER]")
        return

    for provider_name, cache_info in providers.items():
        print_provider_cache_info(provider_name, cache_info)


def cmd_cache_clear(manager: ConfigManager, args):
    """Borrar toda la caché."""
    manager.load_cache()

    if ConfigUI.ask_yes_no("¿Borrar toda la caché?"):
        manager.cache_data = {"cache_timestamp": 0, "providers": {}}
        manager.save_cache()
        ConfigUI.print_success("Caché borrada.")


def cmd_cache_remove(manager: ConfigManager, args):
    """Eliminar un provider de la caché (no afecta opencode.json)."""
    manager.load_cache()

    provider_name = args.provider if hasattr(args, 'provider') and args.provider else None

    if not provider_name:
        ConfigUI.print_error("No se especificó un nombre de provider.")
        print("Uso: ocm cache rm <PROVIDER>")
        return

    providers = manager.cache_data.get("providers", {})
    if provider_name not in providers:
        ConfigUI.print_error(f"Provider '{provider_name}' no encontrado en caché.")
        print("Providers en caché:")
        for p in providers.keys():
            print(f"  - {p}")
        return

    if not ConfigUI.ask_yes_no(f"¿Eliminar provider '{provider_name}' de la caché?"):
        print("Operación cancelada.")
        return

    manager.cache_data["providers"].pop(provider_name, None)
    manager.save_cache()
    ConfigUI.print_success(f"Provider '{provider_name}' eliminado de caché.")
    ConfigUI.print_info(f"Nota: opencode.json no se ha modificado. Usa 'ocm provider rm {provider_name}' para eliminar de opencode.json.")
