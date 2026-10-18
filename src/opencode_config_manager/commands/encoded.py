"""
Bloque plural `providers`: el formato "codificado" de opencode v2.

Comprobado sobre opencode 2.0.32: un provider que solo esta en `providers` **no
se registra**. `opencode models` no lo lista, pongas `package`, `settings`,
`env` o `canonical`. La forma que si registra providers es la singular
(`provider.<id>` con `npm` y `options.baseURL`), que sigue funcionando aunque
el esquema la marque como `deprecated`.

Por eso ocm escribe siempre la singular, y aqui nos limitamos a:

  * detectar las entradas que viven en el plural (para no ignorarlas),
  * entenderlas y validarlas (listados y `ocm config validate`),
  * migrarlas a la forma singular con `ocm config to-singular`.
"""

from ..config import ConfigManager, ConfigUI, Colors
from ..cache_models import adopt_model_options, ensure_uid, normalize_models
from .utils import (
    DEFAULT_NPM,
    create_backup,
    merge_provider_config,
    provider_entry_from_config,
)

# Claves del formato codificado sin equivalencia en el formato singular
DROPPED_PROVIDER_KEYS = ("canonical", "compatibility", "body")
DROPPED_MODEL_KEYS = ("compatibility", "body", "package", "disabled")

# Que paquete SDK declara cada formato codificado -> tipo de provider
PACKAGE_TYPES = {
    "@ai-sdk/openai-compatible": "vllm",
    "@ai-sdk/openai": "vllm",
    "@ai-sdk/anthropic": "vllm",
    "ollama": "ollama",
}


def encoded_providers(manager: ConfigManager) -> dict:
    """Contenido del bloque `providers` (formato codificado de v2)."""
    if not manager or manager.config_data is None:
        return {}
    block = manager.config_data.get("providers")
    return block if isinstance(block, dict) else {}


def encoded_entry(manager: ConfigManager, provider: str) -> dict:
    """Entrada de un provider dentro de `providers`, o {} si no esta."""
    entry = encoded_providers(manager).get(provider)
    return entry if isinstance(entry, dict) else {}



def format_notes(config_data: dict) -> list:
    """Avisos sobre providers declarados en uno u otro bloque.

    Devuelve texto listo para imprimir; no modifica nada.
    """
    notes = []
    if not isinstance(config_data, dict):
        return notes

    single = config_data.get("provider")
    single = single if isinstance(single, dict) else {}
    plural = encoded_providers_from_data(config_data)

    for provider in sorted(set(single) & set(plural)):
        notes.append(
            f"'{provider}' esta en 'provider' y en 'providers' a la vez: opencode hace "
            "caso a 'provider', la entrada de 'providers' se ignora"
        )
    for provider in sorted(set(plural) - set(single)):
        notes.append(
            f"'{provider}' solo esta en 'providers' (formato codificado de v2): en "
            "opencode 2.0.x no llega a registrar el provider. Migralo con: "
            f"ocm config to-singular {provider}"
        )
    return notes


def encoded_providers_from_data(config_data: dict) -> dict:
    """El bloque `providers` desde un dict de config puro (para el validador)."""
    if not isinstance(config_data, dict):
        return {}
    block = config_data.get("providers")
    return block if isinstance(block, dict) else {}


def _cache_url(url: str) -> str:
    """URL para la caché: el config lleva /v1 y la caché no."""
    text = (url or "").rstrip("/")
    if text.endswith("/v1"):
        text = text[: -len("/v1")]
    return text.rstrip("/")


def model_from_encoded(model_id: str, entry: dict) -> tuple:
    """Convertir un modelo del formato codificado al del bloque `provider`.

    Returns:
        (dict_listo_para_el_config, lista_de_avisos)
    """
    notes = []
    if not isinstance(entry, dict):
        return {}, [f"models.{model_id} no es un objeto; se omite"]

    out = {}

    declared = entry.get("modelID")
    if declared and declared != model_id:
        out["id"] = str(declared)
        notes.append(f"models.{model_id}: 'modelID' dice '{declared}' (distinto de la clave); "
                     "se conserva como 'id'")

    for key in ("name", "family"):
        if key in entry:
            out[key] = entry[key]

    if "releaseDate" in entry:
        out["release_date"] = entry["releaseDate"]

    caps = entry.get("capabilities")
    if isinstance(caps, dict):
        if "tools" in caps:
            out["tool_call"] = bool(caps["tools"])
        if "temperature" in caps:
            out["temperature"] = bool(caps["temperature"])
        if caps.get("reasoning") is not None:
            out["reasoning"] = bool(caps["reasoning"])
        modalities = {}
        for side in ("input", "output"):
            value = caps.get(side)
            if isinstance(value, list):
                modalities[side] = [str(item) for item in value]
            elif value is not None:
                notes.append(f"models.{model_id}: 'capabilities.{side}' deberia ser una lista")
        if modalities:
            out["modalities"] = modalities
    elif entry.get("capabilities") is not None:
        notes.append(f"models.{model_id}: 'capabilities' no es un objeto; se omite")

    limit = entry.get("limit")
    if isinstance(limit, dict):
        cleaned = {key: limit[key] for key in ("context", "input", "output") if key in limit}
        if cleaned:
            out["limit"] = cleaned
            if not {"context", "output"} <= set(cleaned):
                notes.append(f"models.{model_id}: 'limit' sin 'context' y 'output' juntos; "
                             "el formato singular los espera a la pareja")
        for extra in set(limit) - set(cleaned):
            notes.append(f"models.{model_id}: 'limit.{extra}' no existe en el formato singular")

    if isinstance(entry.get("cost"), dict) and entry["cost"]:
        out["cost"] = entry["cost"]

    if isinstance(entry.get("headers"), dict) and entry["headers"]:
        out["headers"] = entry["headers"]

    settings = entry.get("settings")
    if isinstance(settings, dict) and settings:
        out["options"] = dict(settings)
    elif entry.get("settings") is not None:
        notes.append(f"models.{model_id}: 'settings' no es un objeto; se omite")

    variants = entry.get("variants")
    if isinstance(variants, list):
        converted = {}
        for variant in variants:
            if not isinstance(variant, dict) or not variant.get("id"):
                notes.append(f"models.{model_id}: variante sin 'id'; se omite")
                continue
            body = {}
            if isinstance(variant.get("settings"), dict):
                body.update(variant["settings"])
            if isinstance(variant.get("headers"), dict) and variant["headers"]:
                body["headers"] = variant["headers"]
            if variant.get("disabled") is not None:
                body["disabled"] = bool(variant["disabled"])
            converted[str(variant["id"])] = body
        if converted:
            out["variants"] = converted
        else:
            notes.append(f"models.{model_id}: ninguna variante aprovechable")

    for key in DROPPED_MODEL_KEYS:
        if key in entry:
            notes.append(f"models.{model_id}: '{key}' no tiene equivalencia en el formato "
                         "singular y se pierde")

    return out, notes


def provider_from_encoded(provider: str, entry: dict) -> tuple:
    """Construir la configuracion "deseada" en formato singular.

    Returns:
        (dict_para_provider.<id>, lista_de_avisos)
    """
    notes = []
    out = {}
    if not isinstance(entry, dict):
        return {}, [f"'{provider}' en 'providers' no es un objeto"]

    if entry.get("name"):
        out["name"] = str(entry["name"])
    if entry.get("package"):
        out["npm"] = str(entry["package"])
    if isinstance(entry.get("env"), list):
        out["env"] = [str(item) for item in entry["env"]]

    options = {}
    settings = entry.get("settings")
    if isinstance(settings, dict):
        options.update(settings)
    elif entry.get("settings") is not None:
        notes.append("'settings' no es un objeto; se omite")
    if isinstance(entry.get("headers"), dict) and entry["headers"]:
        options["headers"] = entry["headers"]
    if options:
        out["options"] = options

    raw_models = entry.get("models")
    if isinstance(raw_models, dict) and raw_models:
        models = {}
        for model_id, model_entry in raw_models.items():
            converted, model_notes = model_from_encoded(model_id, model_entry)
            notes.extend(model_notes)
            models[model_id] = converted or {"name": model_id}
        out["models"] = models
    elif isinstance(raw_models, (list, tuple)) and raw_models:
        # El esquema oficial indexa por id; si alguien lo escribio en lista se
        # resuelve el id con 'modelID'/'id' y cada entrada pasa por el conversor,
        # para no perder 'capabilities' ni 'settings' por el camino.
        models = {}
        for item in raw_models:
            if isinstance(item, str):
                models[item] = {"name": item}
                continue
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("modelID") or item.get("id") or "")
            if not model_id:
                notes.append("un modelo de la lista no tiene 'modelID' ni 'id'; se omite")
                continue
            converted, model_notes = model_from_encoded(model_id, item)
            notes.extend(model_notes)
            models[model_id] = converted or {"name": model_id}
        out["models"] = models
        notes.append("'models' estaba en lista; se indexo por 'modelID'")
    elif raw_models not in (None, {}, []):
        notes.append("'models' no es un objeto keyed por id; se intenta convertir")
        converted_models = normalize_models(raw_models)
        if converted_models:
            out["models"] = {mid: {"name": e.get("name") or mid}
                             for mid, e in converted_models.items()}

    for key in DROPPED_PROVIDER_KEYS:
        if key in entry:
            notes.append(f"'{key}' no tiene equivalencia en el formato singular y se pierde")

    return out, notes


def cache_entry_from_encoded(entry: dict, provider: str, provider_type: str = None) -> dict:
    """Entrada de caché equivalente a una entrada codificada de `providers`.

    Args:
        provider_type: solo si ya esta confirmado (p.ej. en la caché); si no se
            infiere del paquete declarado en la entrada.
    """
    if not isinstance(entry, dict):
        entry = {}

    settings = entry.get("settings") if isinstance(entry.get("settings"), dict) else {}
    package = entry.get("package") or DEFAULT_NPM

    cache_entry = {
        "name": entry.get("name") or provider,
        "provider_type": provider_type or PACKAGE_TYPES.get(package, "vllm"),
        "npm": package,
        "last_scan": 0,
        "models": {},
    }

    base_url = settings.get("baseURL")
    if base_url:
        cache_entry["baseUrl"] = _cache_url(base_url)
    if settings.get("apiKey"):
        cache_entry["apiKey"] = settings["apiKey"]

    models = {}
    raw_models = entry.get("models")
    if isinstance(raw_models, dict):
        for model_id, model_entry in raw_models.items():
            converted, _ = model_from_encoded(model_id, model_entry)
            converted.setdefault("name", (model_entry or {}).get("name")
                                 if isinstance(model_entry, dict) else model_id)
            models[model_id] = converted
    cache_entry["models"] = normalize_models(models)

    return cache_entry


def print_encoded_notice(manager: ConfigManager) -> None:
    """Contar, si las hay, las entradas del bloque `providers`."""
    notes = format_notes(manager.config_data)
    if not notes:
        return

    print(f"\n{Colors.YELLOW}Bloque 'providers' (formato codificado de v2):{Colors.RESET}")
    for note in notes:
        print(f"  ! {note}")
    print(f"  {Colors.CYAN}ocm config to-singular{Colors.RESET} los pasa a la forma que si "
          "entiende opencode")


def cmd_config_to_singular(manager: ConfigManager, args):
    """`ocm config to-singular`: migrar entradas de `providers` a `provider`."""
    manager.load_config()
    manager.load_cache()

    plural = encoded_providers(manager)
    if not plural:
        ConfigUI.print_info("No hay bloque 'providers' en opencode.json: nada que migrar.")
        return

    wanted = getattr(args, "provider", None)
    if wanted:
        if wanted not in plural:
            ConfigUI.print_error(f"'{wanted}' no esta en 'providers'.")
            for name in sorted(plural):
                print(f"  - {name}")
            return
        targets = [wanted]
    else:
        targets = sorted(plural)

    ConfigUI.print_header(f"Migrar 'providers' -> 'provider' ({len(targets)} provider(es))")

    dry_run = bool(getattr(args, "dry_run", False))
    force = bool(getattr(args, "force", False))

    for provider in targets:
        desired, notes = provider_from_encoded(provider, plural[provider])
        model_count = len(desired.get("models") or {})
        print(f"\n{Colors.BOLD}{provider}{Colors.RESET}  "
              f"({desired.get('npm') or 'sin package'}, {model_count} modelo(s))")
        print(f"  ira a: provider.{provider}")
        for note in notes:
            ConfigUI.print_warning(note)

    if dry_run:
        ConfigUI.print_info("--dry-run: no se escribe nada.")
        return

    if len(targets) > 1 and not getattr(args, "yes", False):
        if not ConfigUI.ask_yes_no(f"¿Migrar los {len(targets)} providers detectados?",
                                   default="y"):
            ConfigUI.print_info("Cancelado.")
            return

    backup_done = []
    migrated = []

    for provider in targets:
        desired, _ = provider_from_encoded(provider, plural[provider])
        existing = provider_entry_from_config(manager, provider)
        merged, changes = merge_provider_config(existing, desired, force=force)

        if changes:
            if not backup_done:
                create_backup(manager.config_path)
                backup_done.append(True)
            manager.config_data.setdefault("provider", {})[provider] = merged
            manager.save_config()
            ConfigUI.print_success(f"'{provider}' -> provider.{provider} "
                                   f"({', '.join(changes)})")
        elif existing:
            ConfigUI.print_info(f"'{provider}': provider.{provider} ya tenia esos valores.")
        else:
            # Sin cambios detectados pero sin entrada: se crea igual
            manager.config_data.setdefault("provider", {})[provider] = merged
            manager.save_config()
            ConfigUI.print_success(f"'{provider}' -> provider.{provider}")
        migrated.append(provider)

        # La caché tambien: asi 'ocm update' mantiene el provider de aqui en adelante
        cache_provider = manager.cache_data.setdefault("providers", {}).get(provider)
        fresh = cache_entry_from_encoded(plural[provider], provider,
                                         (cache_provider or {}).get("provider_type"))
        if cache_provider is None:
            ensure_uid(fresh)
            manager.cache_data["providers"][provider] = fresh
            ConfigUI.print_success(f"Caché creada para '{provider}' "
                                   f"({len(fresh.get('models') or {})} modelos).")
        else:
            for key in ("baseUrl", "apiKey", "npm"):
                if not cache_provider.get(key) and fresh.get(key):
                    cache_provider[key] = fresh[key]
            if not cache_provider.get("provider_type") and fresh.get("provider_type"):
                cache_provider["provider_type"] = fresh["provider_type"]
            if adopt_model_options(cache_provider, fresh.get("models") or {}):
                ConfigUI.print_success(f"Caché actualizada con los modelos de '{provider}'.")

    manager.save_cache(touch=False)

    drop = bool(getattr(args, "drop", False))
    keep = bool(getattr(args, "keep", False))
    if not drop and not keep and migrated:
        drop = ConfigUI.ask_yes_no("¿Quitar ahora las entradas migradas de 'providers'? "
                                   "(opencode las ignora)", default="y")

    if drop:
        block = manager.config_data.get("providers") or {}
        for provider in migrated:
            if provider in block:
                block.pop(provider)
        if not block:
            manager.config_data.pop("providers", None)
        if not backup_done:
            create_backup(manager.config_path)
        manager.save_config()
        ConfigUI.print_success(f"Quitadas {len(migrated)} entrada(s) de 'providers'.")

    print("\nSiguiente paso:  " + Colors.CYAN + "ocm config validate" + Colors.RESET +
          "  y  " + Colors.CYAN + "ocm update" + Colors.RESET)
