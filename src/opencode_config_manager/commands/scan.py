"""
Comandos de escaneo de providers.
"""

import time
from datetime import datetime

from ..config import ConfigManager, ConfigUI, Colors
from ..api import ProviderScanner
from ..cache_models import merge_scanned_models, normalize_models
from .utils import provider_entry_from_config


def scan_single_provider(provider_name: str, cached_info: dict, manager: ConfigManager,
                         config_data: dict, current_time: int) -> bool:
    """Escanear un provider individual y actualizar su caché.

    Solo toca los campos que dependen del escaneo (models, last_scan, reachable,
    y baseUrl/provider_type/uid si faltaban). La api key, el nombre visible y las
    opciones por modelo se conservan.

    Returns:
        True si el escaneo fue exitoso, False en caso de error.
    """
    base_url = cached_info.get("baseUrl")
    api_key = cached_info.get("apiKey")

    # El tipo puede venir de la caché o, si aún no está, de opencode.json
    provider_type = cached_info.get("provider_type")
    if not provider_type:
        configured = provider_entry_from_config(manager, provider_name)
        provider_type = configured.get("provider_type") or configured.get("type")
    provider_type = provider_type or "ollama"

    if not base_url:
        ConfigUI.print_error(f"El provider '{provider_name}' no tiene URL base en caché.")
        if cached_info:
            cached_info["reachable"] = False
        return False

    print(f"\nEscaneando {provider_name} en {base_url}...")
    print(f"  Tipo: {provider_type}")

    # Escanear usando el endpoint correcto según tipo
    if provider_type == "vllm":
        result = ProviderScanner.scan_vllm(base_url, api_key)
    else:
        result = ProviderScanner.scan_ollama(base_url, api_key)

    old_models = normalize_models(cached_info.get("models"))

    if not result.success:
        ConfigUI.print_error(f"Error al escanear: {result.error}")
        if cached_info:
            # Se conserva la config y los modelos de la última pasada correcta
            cached_info["reachable"] = False
            cached_info["last_scan_error"] = result.error
        return False

    new_models, added, removed = merge_scanned_models(old_models, result.models)

    print(f"  Modelos: {len(new_models)}")
    if added:
        added_str = ', '.join(f'+ {m}' for m in added)
        print(f"  {Colors.BRIGHT_GREEN}Nuevos:{Colors.RESET} {added_str}")
    if removed:
        removed_str = ', '.join(f'- {m}' for m in removed)
        print(f"  {Colors.BRIGHT_RED}Eliminados del provider:{Colors.RESET} {removed_str}")
        if config_data and provider_name in (config_data.get("provider", {}) or {}):
            print(f"  {Colors.YELLOW}Nota:{Colors.RESET} 'ocm update' no borra modelos ya escritos; "
                  f"edítalos a mano en opencode.json si quieres quitarlos.")

    # Actualizar caché preservando uid, nombre visible, api key y opciones por modelo
    cached_info["models"] = new_models
    cached_info["last_scan"] = current_time
    cached_info["provider_type"] = provider_type
    cached_info["reachable"] = True
    cached_info.pop("last_scan_error", None)
    manager.cache_data["providers"][provider_name] = cached_info

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
        cached_info = manager.cache_data["providers"].get(provider)
        if cached_info is None:
            ConfigUI.print_error(f"Provider '{provider}' no encontrado en caché.")
            print("Ejecuta: ocm new para crearlo o 'ocm cache list' para ver los disponibles.")
            return
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
