"""
Comandos de gestión de modelos y nombres visibles.

ocm guarda el nombre visible (campo 'name') en la caché y lo propaga a
opencode.json. Estos comandos permiten cambiarlos sin editar el JSON a mano,
y son los que usan el asistente de reconfiguración.
"""

from ..config import ConfigManager, ConfigUI, Colors
from ..cache_models import normalize_models, set_model_option
from ..model_fields import describe_model
from .utils import provider_entry_from_config, refresh_cache_from_config


def _cache_entry(manager: ConfigManager, provider: str) -> dict:
    manager.load_cache()
    return manager.cache_data.get("providers", {}).get(provider)


def _pick_from_list(items: list, label: str):
    """Menú numerado simple. Devuelve el item elegido o None."""
    if not items:
        return None
    if len(items) == 1:
        print(f"{label}: {items[0]}")
        return items[0]

    print(f"Selecciona {label}:")
    for index, item in enumerate(items, start=1):
        print(f"  {index}) {item}")
    while True:
        raw = ConfigUI.ask_input("Opción", "1")
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        ConfigUI.print_warning("Numero fuera de rango.")


def resolve_provider(manager: ConfigManager, provider: str = None) -> str:
    """Resolver el provider por argumento o preguntando entre los conocidos."""
    manager.load_cache()
    manager.load_config()

    names = sorted(set(manager.cache_data.get("providers", {})) |
                   set(k for k, v in (manager.config_data.get("provider", {}) or {}).items()
                       if isinstance(v, dict)))

    if provider:
        if provider in names:
            return provider
        ConfigUI.print_error(f"Provider '{provider}' no encontrado.")
        print("Providers conocidos:")
        for name in names:
            print(f"  - {name}")
        return None

    if not names:
        ConfigUI.print_error("No hay providers. Ejecuta: ocm new")
        return None

    return _pick_from_list(names, "provider")


def _sync_config_name(manager: ConfigManager, provider: str, model_id: str, name: str) -> bool:
    """Escribir el nombre visible en opencode.json si el provider ya está ahí."""
    entry = provider_entry_from_config(manager, provider)
    models = entry.get("models")
    if not isinstance(models, dict) or model_id not in models:
        return False
    model_entry = models[model_id] if isinstance(models[model_id], dict) else {}
    model_entry["name"] = name
    models[model_id] = model_entry
    entry["models"] = models
    manager.config_data.setdefault("provider", {})[provider] = entry
    manager.save_config()
    return True


def cmd_model_list(manager: ConfigManager, args):
    """Listar los modelos de un provider con su nombre visible y opciones."""
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    ConfigUI.print_header(f"Modelos de {provider}")

    cache_info = _cache_entry(manager, provider) or {}
    if refresh_cache_from_config(manager, provider):
        manager.save_cache(touch=False)
        cache_info = _cache_entry(manager, provider) or {}

    models = normalize_models(cache_info.get("models"))
    configured = provider_entry_from_config(manager, provider).get("models", {}) or {}

    if not models and not configured:
        print("No hay modelos en caché para este provider.")
        print(f"Ejecuta: ocm cache update {provider}")
        return

    print(f"{'Modelo':<36} {'Nombre visible':<26} {'Opciones':<34} En config")
    print("-" * 108)
    for model_id in list(models) + [m for m in configured if m not in models]:
        cache_entry = models.get(model_id)
        config_entry = (configured.get(model_id) or {}) if isinstance(configured, dict) else {}
        entry = cache_entry if isinstance(cache_entry, dict) else config_entry
        if not isinstance(entry, dict):
            entry = {}
        name = entry.get("name") or model_id
        where = "si" if model_id in configured else "no"
        print(f"{model_id:<36} {('' if name == model_id else name):<26} "
              f"{describe_model(entry).strip():<34} {where}")

    print()
    print("Renombra con:  " + Colors.CYAN + f"ocm model name {provider} [MODELO]" + Colors.RESET)
    print("Configura con: " + Colors.CYAN + f"ocm model options {provider} [MODELO]" + Colors.RESET)


def cmd_model_rename(manager: ConfigManager, args):
    """Cambiar el nombre visible de un modelo (caché + opencode.json)."""
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    cache_info = _cache_entry(manager, provider)
    if cache_info is None:
        ConfigUI.print_error(f"'{provider}' no está en caché. Ejecuta: ocm new")
        return

    models = normalize_models(cache_info.get("models"))
    configured = provider_entry_from_config(manager, provider).get("models", {}) or {}
    candidates = list(models) + [m for m in configured if m not in models]

    model_id = getattr(args, "model", None) or _pick_from_list(candidates, "modelo")
    if not model_id:
        ConfigUI.print_error("Este provider no tiene modelos.")
        return

    current = (models.get(model_id) or {}).get("name") or model_id
    value = getattr(args, "name", None)
    if not value:
        value = ConfigUI.ask_input(f"Nombre visible de '{model_id}'", current)
    if value in ("-", "", None):
        value = model_id

    set_model_option(cache_info, model_id, "name", value)
    manager.save_cache()
    ConfigUI.print_success(f"Caché actualizada: '{model_id}' -> '{value}'")

    if _sync_config_name(manager, provider, model_id, value):
        ConfigUI.print_success(f"opencode.json actualizado: '{model_id}' -> '{value}'")
    else:
        ConfigUI.print_info("El modelo aún no está en opencode.json. Se aplicará con "
                            f"'ocm update {provider}'.")


def cmd_provider_rename(manager: ConfigManager, args):
    """Cambiar el nombre visible del provider (el que aparece en /models)."""
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    cache_info = _cache_entry(manager, provider)
    entry = provider_entry_from_config(manager, provider)
    current = (cache_info or {}).get("name") or entry.get("name") or provider

    value = getattr(args, "name", None)
    if not value:
        value = ConfigUI.ask_input("Nuevo nombre visible del provider", current)
    if not value:
        ConfigUI.print_error("El nombre no puede estar vacío.")
        return

    changed = False
    if cache_info is not None and cache_info.get("name") != value:
        cache_info["name"] = value
        manager.save_cache()
        changed = True
        ConfigUI.print_success(f"Caché actualizada: provider '{provider}' -> '{value}'")

    if entry and entry.get("name") != value:
        entry["name"] = value
        manager.config_data.setdefault("provider", {})[provider] = entry
        manager.save_config()
        changed = True
        ConfigUI.print_success(f"opencode.json actualizado: '{provider}' -> '{value}'")

    if not changed:
        ConfigUI.print_info(f"El provider ya se llama '{value}'.")
