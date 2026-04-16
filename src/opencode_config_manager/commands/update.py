"""
Comandos de actualización de opencode.json.
"""

import shutil
from datetime import datetime

from ..config import ConfigManager, ConfigUI
from .utils import get_provider_type, create_backup, sanitize_config_for_opencode


def cmd_update_provider(manager: ConfigManager, args, provider: str = None):
    """Actualizar un provider específico usando la caché (NO escanea en tiempo real).

    Args:
        manager: Instancia de ConfigManager
        args: Argumentos del parser
        provider: Nombre del provider a actualizar (si se proporciona, ignora args.provider)
    """
    manager.load_config()
    manager.load_cache()

    # Usar provider si se proporciona, de lo contrario verificar args
    if provider:
        pass  # Ya tenemos el provider
    elif hasattr(args, 'provider') and args.provider:
        provider = args.provider
    else:
        provider = None

    model = manager.config_data.get("model")

    # Verificar si tenemos provider para actualizar
    if not provider:
        ConfigUI.print_error("No hay provider configurado ni especificado.")
        print("Uso: ocm update [PROVIDER]")
        print("Proveedores disponibles en caché:")
        for p in manager.cache_data.get("providers", {}).keys():
            print(f"  - {p}")
        return

    # Verificar si el provider existe en caché
    if provider not in manager.cache_data.get("providers", {}):
        ConfigUI.print_error(f"Provider '{provider}' no encontrado en caché.")
        print("Ejecuta primero: ocm scan {provider}")
        print("Proveedores disponibles en caché:")
        for p in manager.cache_data.get("providers", {}).keys():
            print(f"  - {p}")
        return

    # Obtener datos de caché (NO escanear en tiempo real)
    cache_info = manager.cache_data["providers"][provider]
    cache_models = cache_info.get("models", [])
    cached_model = cache_models[0] if cache_models else None
    base_url = cache_info.get("baseUrl", "http://127.0.0.1:11434")
    last_scan = cache_info.get("last_scan", 0)

    # Mostrar estado actual desde caché
    print(f"\n=== Provider: {provider} ===")
    print(f"Modelos en caché: {len(cache_models)}")
    print(f"Último escaneo: {datetime.fromtimestamp(last_scan) if last_scan else 'N/A'}")

    # Verificar si hay modelos en caché
    if not cache_models:
        ConfigUI.print_error("No hay modelos en caché para este provider.")
        print("Ejecuta primero: ocm scan {provider}")
        return

    # Crear backup ANTES de modificar
    backup_path = create_backup(manager.config_path, provider_name=provider)
    if backup_path:
        print(f"\n[BACKUP] Creado en: {backup_path}")

    # Generar configuración compatible con opencode.ai usando datos de caché
    # El campo 'provider' debe ser el TIPO (ollama, anthropic, etc.), no el nombre
    provider_type = get_provider_type(provider, manager)
    model_name = cache_models[0] if cache_models else (model or cached_model or "unknown")
    model_id = f"{provider_type}/{model_name}"

    # Limpiar campos no compatibles
    for key in ["temperature", "maxTokens", "models", "providers"]:
        manager.config_data.pop(key, None)

    # Actualizar provider específico manteniendo los demás
    provider_config = sanitize_config_for_opencode(
        provider_type=provider_type,
        provider_name=provider,
        model_name=model_name,
        base_url=base_url,
        models_list=cache_models,
        api_key=cache_info.get("apiKey")
    )

    # Conservar providers existentes
    existing_providers = manager.config_data.get("provider", {})
    if isinstance(existing_providers, dict):
        # Unir providers existentes con el nuevo
        merged_providers = {**existing_providers, provider: provider_config}
        manager.config_data["provider"] = merged_providers
    else:
        manager.config_data["provider"] = {provider: provider_config}

    # Eliminar campo model (no es necesario, los modelos están en provider.X.models)
    manager.config_data.pop("model", None)

    # Asegurar que el schema exista
    manager.config_data["$schema"] = "https://opencode.ai/config.json"

    try:
        manager.save_config()
        ConfigUI.print_success(f"Provider {provider} actualizado en {manager.config_path}")
        print(f"Modelos disponibles:")
        for m in cache_models:
            print(f"  - {m}")
    except Exception as e:
        ConfigUI.print_error(f"No se pudo guardar la configuración: {e}")
        if backup_path:
            print(f"\n[RECOVER] Restaurando backup: {backup_path}")
            shutil.copy2(backup_path, manager.config_path)
            ConfigUI.print_success("Configuración restaurada correctamente.")
        return


def cmd_update_global(manager: ConfigManager, args):
    """Actualizar todos los providers en caché a opencode.json.
    Si se especifica un provider, solo actualiza ese.
    """
    manager.load_config()
    manager.load_cache()

    # Si no se especificó un provider, actualizar TODOS los providers en caché
    if not hasattr(args, 'provider') or not args.provider:
        if manager.cache_data.get("providers"):
            ConfigUI.print_info("No se especificó provider. Actualizando todos los providers en caché...")
            providers_to_update = list(manager.cache_data["providers"].keys())
            updated_count = 0

            for cache_provider in providers_to_update:
                try:
                    cmd_update_provider(manager, args, provider=cache_provider)
                    updated_count += 1
                except Exception as e:
                    ConfigUI.print_error(f"Error al actualizar {cache_provider}: {e}")
                    continue

            ConfigUI.print_success(f"Actualizados {updated_count}/{len(providers_to_update)} providers")
            return
        else:
            ConfigUI.print_error("No hay providers en caché para actualizar.")
            return

    # Si se especificó un provider, usarlo
    provider = args.provider

    # Si el provider por nombre no existe en caché, buscar por tipo
    if provider not in manager.cache_data.get("providers", {}):
        # Obtener el tipo del provider
        provider_type = get_provider_type(provider, manager)

        # Buscar en caché por tipo
        found_provider = None
        for cache_name, cache_info in manager.cache_data.get("providers", {}).items():
            # Verificar si este provider en caché tiene el mismo tipo
            if get_provider_type(cache_name, manager) == provider_type:
                found_provider = cache_name
                break

        if found_provider:
            provider = found_provider
            ConfigUI.print_info(f"Usando provider encontrado en caché: {provider} (tipo: {provider_type})")
        else:
            ConfigUI.print_error(f"Provider '{provider}' no encontrado en caché.")
            print("Ejecuta primero: ocm scan {provider}")
            print("Proveedores disponibles en caché:")
            for p in manager.cache_data.get("providers", {}).keys():
                print(f"  - {p} (tipo: {get_provider_type(p, manager)})")
            return

    # Ahora ejecutar cmd_update_provider con el provider correcto
    cmd_update_provider(manager, args, provider=provider)
