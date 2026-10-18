"""
Comandos de actualización de opencode.json.

`ocm update` escribe desde la caché (NO escanea en tiempo real) de forma no
destructiva: combina la configuración deseada con la que ya hay en el archivo,
de modo que sobreviven las claves que ocm no gestiona (npm manual, env,
whitelist/blacklist, headers, opciones de modelo escritas a mano, ...) y tampoco
se borran providers ni modelos existentes.
"""

import shutil
from datetime import datetime

from ..config import ConfigManager, ConfigUI, Colors
from ..cache_models import normalize_models, provider_needs_rescan
from .utils import (
    build_provider_config,
    create_backup,
    get_provider_type,
    merge_provider_config,
    provider_entry_from_config,
    refresh_cache_from_config,
)


def _resolve_provider(name: str, manager: ConfigManager):
    """Resolver un provider por nombre o por uid de la caché."""
    providers = manager.cache_data.get("providers", {})
    if name in providers:
        return name
    for cache_name, cache_info in providers.items():
        if cache_info.get("uid") == name:
            return cache_name
    return None


def _print_cache_providers(manager: ConfigManager, requested: str = None):
    configured = manager.config_data.get("provider", {}) if manager.config_data else {}
    if requested and isinstance(configured, dict) and requested in configured:
        ConfigUI.print_info(
            f"'{requested}' existe en opencode.json pero no en la caché. "
            f"Ejecuta: ocm new {requested}"
        )
    providers = manager.cache_data.get("providers", {})
    if providers:
        print("Proveedores disponibles en caché:")
        for name, info in providers.items():
            uid = info.get("uid", "-")
            count = len(normalize_models(info.get("models")))
            print(f"  - {name} (uid: {uid}, {count} modelos)")
    else:
        print("La caché está vacía. Ejecuta: ocm new")


def cmd_update_provider(manager: ConfigManager, args, provider: str = None, force: bool = None):
    """Actualizar un provider específico usando la caché (NO escanea en tiempo real).

    Args:
        manager: Instancia de ConfigManager
        args: Argumentos del parser
        provider: Nombre del provider a actualizar (si se proporciona, ignora args.provider)
        force: Sobrescribir las claves que ocm gestiona aunque ya existan
    """
    manager.load_config()
    manager.load_cache()

    if force is None:
        force = bool(getattr(args, "force", False))

    requested = provider or getattr(args, "provider", None)

    if not requested:
        ConfigUI.print_error("No hay provider configurado ni especificado.")
        print("Uso: ocm update [PROVIDER]")
        _print_cache_providers(manager)
        return

    provider = _resolve_provider(requested, manager)
    if not provider:
        ConfigUI.print_error(f"Provider '{requested}' no encontrado en caché.")
        print("Ejecuta primero: ocm cache update <PROVIDER>")
        _print_cache_providers(manager, requested)
        return

    cache_info = manager.cache_data["providers"][provider]
    # Si alguien puso opciones a mano en opencode.json, se adoptan a la caché para
    # que 'ocm update' no las trate como inexistentes
    if refresh_cache_from_config(manager, provider):
        manager.save_cache(touch=False)
    models = normalize_models(cache_info.get("models"))

    print(f"\n=== Provider: {provider} ===")
    if cache_info.get("uid"):
        print(f"UID: {cache_info['uid']}")
    print(f"URL base: {cache_info.get('baseUrl', 'N/A')}")
    print(f"Modelos en caché: {len(models)}")
    last_scan = cache_info.get("last_scan", 0)
    print(f"Último escaneo: {datetime.fromtimestamp(last_scan) if last_scan else 'N/A'}")

    if not models:
        ConfigUI.print_error("No hay modelos en caché para este provider.")
        print(f"Ejecuta primero: ocm cache update {provider}")
        return

    if provider_needs_rescan(cache_info):
        ConfigUI.print_warning(
            "Este provider ya no está accesible en la URL guardada; "
            f"usa 'ocm new {provider}' para corregir la URL antes de actualizar."
        )

    provider_type = get_provider_type(provider, manager)
    desired = build_provider_config(provider, cache_info, provider_type)

    configured = manager.config_data.get("provider")
    raw = configured.get(provider) if isinstance(configured, dict) else None
    if raw is not None and not isinstance(raw, dict):
        ConfigUI.print_error(f"'provider.{provider}' no es un objeto JSON; "
                             "arreglalo antes de actualizar (ocm config validate).")
        return

    existing = provider_entry_from_config(manager, provider)
    merged, changes = merge_provider_config(existing, desired, force=force)

    if not changes:
        ConfigUI.print_success(f"Provider '{provider}' ya está al día. No hay cambios.")
        return

    # Crear backup ANTES de modificar
    backup_path = create_backup(manager.config_path, provider_name=provider)
    if backup_path:
        print(f"[BACKUP] Creado en: {backup_path}")

    providers = manager.config_data.get("provider")
    if not isinstance(providers, dict):
        providers = {}
    providers[provider] = merged
    manager.config_data["provider"] = providers
    manager.config_data["$schema"] = "https://opencode.ai/config.json"

    try:
        manager.save_config()
    except Exception as e:
        ConfigUI.print_error(f"No se pudo guardar la configuración: {e}")
        if backup_path:
            print(f"[RECOVER] Restaurando backup: {backup_path}")
            shutil.copy2(backup_path, manager.config_path)
            ConfigUI.print_success("Configuración restaurada correctamente.")
        return

    ConfigUI.print_success(f"Provider '{provider}' actualizado en {manager.config_path}")
    print(f"Cambios aplicados ({len(changes)}):")
    for change in changes:
        print(f"  {Colors.BRIGHT_GREEN}+{Colors.RESET} {change}")
    if not force:
        print(f"\n{Colors.CYAN}ocm solo añade: las claves existentes se respetan. "
              f"Usa 'ocm update {provider} --force' para sobrescribir las que gestiona ocm."
              f"{Colors.RESET}")

    print("Modelos disponibles:")
    for model_id, entry in models.items():
        name = entry.get("name") or model_id
        limit = entry.get("limit") or {}
        extra = ""
        if limit.get("context"):
            extra += f"  ctx={limit['context']}"
        modalities = (entry.get("modalities") or {}).get("input")
        if modalities:
            extra += f"  in={','.join(modalities)}"
        marker = "" if name == model_id else f" -> {name}"
        print(f"  - {model_id}{marker}{extra}")


def cmd_update_global(manager: ConfigManager, args):
    """Actualizar todos los providers en caché a opencode.json.
    Si se especifica un provider, solo actualiza ese.
    """
    manager.load_config()
    manager.load_cache()

    provider = getattr(args, "provider", None)

    if not provider:
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

    # Resolver por nombre o uid; si no existe, buscar por tipo
    resolved = _resolve_provider(provider, manager)
    if not resolved:
        provider_type = get_provider_type(provider, manager)
        for cache_name, cache_info in manager.cache_data.get("providers", {}).items():
            if get_provider_type(cache_name, manager) == provider_type:
                resolved = cache_name
                ConfigUI.print_info(f"Usando provider encontrado en caché: {resolved} (tipo: {provider_type})")
                break

    if not resolved:
        ConfigUI.print_error(f"Provider '{provider}' no encontrado en caché.")
        print("Ejecuta primero: ocm cache update <PROVIDER>")
        _print_cache_providers(manager)
        return

    cmd_update_provider(manager, args, provider=resolved)
