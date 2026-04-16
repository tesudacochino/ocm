"""
Comandos de gestión de providers: new, list, remove.
"""

import time
from datetime import datetime

from ..config import ConfigManager, ConfigUI
from ..api import ProviderScanner


def detect_provider_type(base_url: str) -> tuple[str, list[str]]:
    """Detectar automáticamente si es Ollama o vLLM escaneando la API.

    Retorna (tipo, lista de modelos)
    """
    # Probar Ollama primero (endpoint más común)
    result_ollama = ProviderScanner.scan_ollama(base_url, None)
    if result_ollama.success and result_ollama.models:
        return "ollama", result_ollama.models

    # Si falla, probar vLLM
    result_vllm = ProviderScanner.scan_vllm(base_url, None)
    if result_vllm.success and result_vllm.models:
        return "vllm", result_vllm.models

    # Ninguno funciona
    return None, []


def print_provider_info(provider_name: str, cache_info: dict):
    """Mostrar información de un provider desde la caché."""
    models = cache_info.get("models", [])
    last_scan = cache_info.get("last_scan", 0)
    base_url = cache_info.get("baseUrl", "N/A")

    print(f"{provider_name}:")
    print(f"  Última escaneada: {datetime.fromtimestamp(last_scan) if last_scan else 'N/A'}")
    print(f"  URL base: {base_url}")
    if models:
        print(f"  Modelos ({len(models)}):")
        for model in models:
            print(f"    - {model}")
    else:
        print(f"  Modelos: Ninguno escaneado")
    print()


def cmd_provider_new(manager: ConfigManager, args):
    """Crear un nuevo provider local compatible con opencode.ai.
    El tipo de provider (ollama/vllm) se detecta automáticamente.
    El modelo activo no se define en este paso.
    """
    manager.load_config()

    ConfigUI.print_header("Nuevo Provider Local")

    # Nombre del provider (ej: local, ollama-home, ollama-server)
    provider_name = ConfigUI.ask_input("Nombre del provider", "local")

    # URL base del provider
    default_url = "http://127.0.0.1:11434"
    base_url = ConfigUI.ask_input("URL base del provider", default_url)

    # Eliminar /v1 del final si el usuario lo incluyó, para que el escaneo funcione
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    elif base_url.endswith("/v1/"):
        base_url = base_url[:-4]

    # Detectar automáticamente si es Ollama o vLLM
    print("\nDetectando tipo de provider...")
    provider_type, models = detect_provider_type(base_url)

    if not provider_type:
        ConfigUI.print_error(f"No se pudo detectar el provider en {base_url}")
        ConfigUI.print_error("Verifica que el servicio esté corriendo.")
        return

    ConfigUI.print_success(f"Provider detectado: {provider_type}")
    ConfigUI.print_success(f"URL: {base_url}")

    if models:
        ConfigUI.print_success(f"Modelos encontrados: {len(models)}")
        print("Modelos detectados:")
        for m in models:
            print(f"  - {m}")
        print()
    else:
        ConfigUI.print_info("No se encontraron modelos, puedes continuar de todos modos.")
        print()

    # API Key opcional
    api_key = ConfigUI.ask_input("API Key (dejar vacío si no requiere)", "")

    # Guardar SOLO en caché (NO modificar opencode.json)
    manager.load_cache()
    cache_entry = {
        "models": models,
        "last_scan": int(time.time()),
        "baseUrl": base_url,
        "provider_type": provider_type
    }
    if api_key:
        cache_entry["apiKey"] = api_key
    manager.cache_data["providers"][provider_name] = cache_entry
    manager.save_cache()

    ConfigUI.print_success(f"Provider '{provider_name}' guardado en caché.")
    ConfigUI.print_info(f"Para actualizar opencode.json ejecuta: ocm update {provider_name}")


def cmd_provider_list(manager: ConfigManager, args):
    """Listar providers desde caché."""
    manager.load_cache()

    ConfigUI.print_header("Providers en Caché")

    if not manager.cache_data.get("providers"):
        print("No hay providers escaneados aún.")
        print("Ejecuta: ocm scan [PROVIDER]")
        return

    for provider_name, cache_info in manager.cache_data.get("providers", {}).items():
        print_provider_info(provider_name, cache_info)


def cmd_provider_remove(manager: ConfigManager, args):
    """Eliminar un provider específico de la configuración."""
    manager.load_config()
    manager.load_cache()

    # Obtener el nombre del provider desde los argumentos
    provider_name = args.provider if hasattr(args, 'provider') and args.provider else None

    if not provider_name:
        ConfigUI.print_error("No se especificó un nombre de provider.")
        print("Uso: ocm remove [PROVIDER_NAME]")
        return

    # Verificar si el provider existe en la configuración
    providers = manager.config_data.get("provider", {})
    if provider_name not in providers:
        ConfigUI.print_error(f"Provider '{provider_name}' no encontrado en la configuración.")
        print("Providers disponibles:")
        for p in providers.keys():
            print(f"  - {p}")
        return

    if not ConfigUI.ask_yes_no(f"¿Eliminar provider '{provider_name}'?"):
        print("Operación cancelada.")
        return

    # Eliminar solo el provider específico del objeto provider
    manager.config_data["provider"].pop(provider_name, None)

    # Si no quedan providers, limpiar el objeto provider
    if not manager.config_data.get("provider"):
        manager.config_data.pop("provider", None)

    # También eliminar de la caché
    manager.cache_data["providers"].pop(provider_name, None)
    manager.save_cache()

    manager.save_config()
    ConfigUI.print_success(f"Provider '{provider_name}' eliminado correctamente.")
