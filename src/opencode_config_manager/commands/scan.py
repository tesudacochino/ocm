"""
Comandos de escaneo de providers.
"""

import time
from datetime import datetime

from ..config import ConfigManager, ConfigUI, Colors
from ..api import ProviderScanner


def scan_single_provider(provider_name: str, cached_info: dict, manager: ConfigManager,
                         config_data: dict, current_time: int) -> bool:
    """Escanear un provider individual y actualizar su caché.

    Returns:
        True si el escaneo fue exitoso, False en caso de error.
    """
    base_url = cached_info.get("baseUrl", "http://127.0.0.1:11434")
    old_models = cached_info.get("models", [])

    # Obtener tipo de provider desde caché o detectar
    provider_type = cached_info.get("provider_type", "ollama")

    print(f"\nEscaneando {provider_name} en {base_url}...")
    print(f"  Tipo: {provider_type}")

    # Escanear usando el endpoint correcto según tipo
    if provider_type == "vllm":
        result = ProviderScanner.scan_vllm(base_url, None)
    else:
        result = ProviderScanner.scan_ollama(base_url, None)

    if not result.success:
        ConfigUI.print_error(f"Error al escanear: {result.error}")
        return False

    new_models = result.models

    # Comparar con caché anterior
    added = set(new_models) - set(old_models)
    removed = set(old_models) - set(new_models)

    # Mostrar resumen de cambios
    print(f"  Modelos: {len(new_models)}")
    if added:
        new_str = ', '.join(f'+ {m}' for m in added)
        print(f"  {Colors.BRIGHT_GREEN}Nuevos:{Colors.RESET} {new_str}")
    if removed:
        removed_str = ', '.join(f'- {m}' for m in removed)
        print(f"  {Colors.BRIGHT_RED}Eliminados:{Colors.RESET} {removed_str}")

    # Actualizar caché
    manager.cache_data["providers"][provider_name] = {
        "models": new_models,
        "last_scan": current_time,
        "baseUrl": base_url,
        "provider_type": provider_type
    }

    return True


def cmd_scan(manager: ConfigManager, args):
    """Escanear providers y actualizar caché."""
    manager.load_cache()
    manager.load_config()

    # Si se especificó un provider específico
    provider = getattr(args, 'provider', None)
    current_time = int(time.time())

    if provider:
        # Escanear provider específico
        ConfigUI.print_header(f"Escaneando: {provider}")
        cached_info = manager.cache_data["providers"].get(provider, {})
        scan_single_provider(provider, cached_info, manager, manager.config_data, current_time)
    else:
        # Escanear todos los providers guardados en caché
        if not manager.cache_data.get("providers"):
            ConfigUI.print_error("No hay providers para escanear.")
            print("Ejecuta: ocm new para crear un provider primero.")
            return

        ConfigUI.print_header("Escaneando todos los providers")
        for provider_name, cached_info in manager.cache_data["providers"].items():
            scan_single_provider(provider_name, cached_info, manager, manager.config_data, current_time)

    # Guardar caché
    manager.cache_data["cache_timestamp"] = current_time
    manager.save_cache()
    ConfigUI.print_success(f"Caché actualizada a {datetime.fromtimestamp(current_time)}")
