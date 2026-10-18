"""
Asistente de reconfiguración de un provider: `ocm configure [PROVIDER]`.

Recorre, mostrando el valor actual de cada uno, los campos del provider (nombre
visible, URL base, api key y estilo de API) y luego deja repasar las opciones de
los modelos. Es la via comoda para corregir la URL de un provider que se cambio
de maquina, o para activar la vision de un modelo.

Reglas de escritura (las mismas de los comandos de renombrado):
  * es una accion explicita del usuario, asi que escribe en `opencode.json` en el
    momento, sin esperar a `ocm update`,
  * solo toca las claves que se respondieron,
  * hace backup de opencode.json antes del primer cambio.
"""

import time

from ..config import ConfigManager, ConfigUI, Colors
from ..cache_models import normalize_models, provider_needs_rescan
from .model import resolve_provider
from .options import (
    KEEP,
    UNSET_WORDS,
    configure_model_entry,
    print_model_menu,
    sync_model_config,
)
from .scan import scan_single_provider
from .utils import (
    API_STYLES,
    create_backup,
    get_provider_type,
    provider_entry_from_config,
    refresh_cache_from_config,
)


def mask_secret(secret: str) -> str:
    """Pintar una api key sin mostrarla entera."""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * 6}{secret[-4:]}"


def _config_url(base_url: str, provider_type: str) -> str:
    """URL que va en `options.baseURL` de opencode.json.

    Misma convencion que `build_provider_config`: la caché guarda el host pelado
    y en el config lleva el sufijo /v1.
    """
    url = (base_url or "").rstrip("/")
    if provider_type in ("ollama", "vllm") and not url.endswith("/v1"):
        url = url + "/v1"
    return url


def ask_optional(label: str, current: str = "", hint: str = "", secret: bool = False):
    """Pregunta un campo de texto del provider.

    Returns:
        KEEP (Intro, no lo toco) | None ('-', quitarlo) | el texto nuevo
    """
    display = mask_secret(current) if secret else (current or "")
    raw = ConfigUI.ask_raw(f"  {label}", display, hint)
    if raw is None or raw == "":
        return KEEP
    text = raw.strip()
    if text.lower() in UNSET_WORDS:
        return None
    return text


def apply_provider_fields(manager: ConfigManager, provider: str, cache_info: dict,
                          fields: dict, backup_done: list) -> int:
    """Volcar los campos modificados en la caché y en `opencode.json`.

    Args:
        cache_info: entrada de caché del provider (se modifica in place)
        fields: subconjunto de {'name', 'baseUrl', 'apiKey', 'npm'}; un valor
            None significa quitar la clave

    Returns:
        numero de escrituras realizadas
    """
    writes = 0
    provider_type = cache_info.get("provider_type") or get_provider_type(provider, manager)
    entry = provider_entry_from_config(manager, provider)

    for key, value in fields.items():
        if value is None:
            if key in cache_info:
                cache_info.pop(key, None)
                writes += 1
        elif cache_info.get(key) != value:
            cache_info[key] = value
            writes += 1

    if not entry:
        # Todavia no esta en opencode.json: 'ocm update' lo escribira
        return writes

    changed_here = False

    if "name" in fields:
        wanted = fields["name"]
        if wanted is None:
            if "name" in entry:
                entry.pop("name")
                changed_here = True
        elif entry.get("name") != wanted:
            entry["name"] = wanted
            changed_here = True

    if "npm" in fields and fields["npm"] and entry.get("npm") != fields["npm"]:
        entry["npm"] = fields["npm"]
        changed_here = True

    options = entry.get("options")
    if not isinstance(options, dict):
        options = {}

    if "baseUrl" in fields:
        if fields["baseUrl"] is None:
            if options.pop("baseURL", None) is not None:
                changed_here = True
        else:
            wanted = _config_url(fields["baseUrl"], provider_type)
            if options.get("baseURL") != wanted:
                options["baseURL"] = wanted
                changed_here = True

    if "apiKey" in fields:
        if fields["apiKey"] is None:
            if options.pop("apiKey", None) is not None:
                changed_here = True
        elif options.get("apiKey") != fields["apiKey"]:
            options["apiKey"] = fields["apiKey"]
            changed_here = True

    if changed_here:
        if options:
            entry["options"] = options
        if not backup_done:
            create_backup(manager.config_path)
            backup_done.append(True)
        manager.config_data.setdefault("provider", {})[provider] = entry
        manager.save_config()
        writes += 1

    return writes


def _print_current(provider: str, cache_info: dict, entry: dict) -> None:
    """Mostrar como esta configurado el provider ahora mismo."""
    options = entry.get("options") if isinstance(entry.get("options"), dict) else {}
    key = cache_info.get("apiKey") or options.get("apiKey")
    print(f"\n{Colors.BOLD}{provider}{Colors.RESET}")
    print(f"  Nombre visible : {cache_info.get('name') or entry.get('name') or provider}")
    print(f"  URL base       : {cache_info.get('baseUrl') or options.get('baseURL') or 'N/A'}")
    print(f"  API key        : {mask_secret(key) or 'no'}")
    print(f"  SDK (npm)      : {cache_info.get('npm') or entry.get('npm') or 'N/A'}")
    print(f"  Tipo detectado : {cache_info.get('provider_type') or 'N/A'}")
    if cache_info.get("reachable") is False:
        print(f"  {Colors.YELLOW}No accesible en el ultimo escaneo: "
              f"{cache_info.get('last_scan_error', '')}{Colors.RESET}")


def _ask_fields(provider: str, cache_info: dict, entry: dict, overrides: dict) -> dict:
    """Preguntar los campos del provider, uno a uno, salvo los fijados por flag."""
    options = entry.get("options") if isinstance(entry.get("options"), dict) else {}
    fields = {}

    if "name" in overrides:
        fields["name"] = overrides["name"]
    else:
        value = ask_optional("Nombre visible del provider",
                             cache_info.get("name") or entry.get("name") or provider,
                             "el que sale en /models")
        if value is not KEEP:
            fields["name"] = value

    if "url" in overrides:
        fields["baseUrl"] = overrides["url"]
    else:
        while True:
            value = ask_optional("URL base", cache_info.get("baseUrl") or "",
                                 "ej: http://192.168.1.5:11434 (sin /v1)")
            if value is KEEP or value is None:
                break
            if not value.startswith(("http://", "https://")):
                ConfigUI.print_warning("Escribe la URL completa, con http:// o https://")
                continue
            fields["baseUrl"] = value
            break

    if "api_key" in overrides:
        fields["apiKey"] = overrides["api_key"]
    else:
        value = ask_optional("API key", cache_info.get("apiKey") or options.get("apiKey") or "",
                             "Intro mantiene la guardada", secret=True)
        if value is not KEEP:
            fields["apiKey"] = value

    return fields


def ask_api_style_fields(cache_info: dict, provider_type: str, previous: dict = None) -> dict:
    """Elegir el SDK, solo en providers estilo OpenAI (Ollama siempre chat completions).

    Returns:
        {'npm': paquete} si eligio otro, o {} si no cambio
    """
    if provider_type != "vllm":
        return {}

    keys = list(API_STYLES)
    labels = [API_STYLES[key] for key in keys]
    current = cache_info.get("npm") or (previous or {}).get("npm") or keys[0]
    current_label = labels[keys.index(current)] if current in keys else labels[0]

    choice = ConfigUI.ask_choice("Estilo de API del provider", labels, default=current_label)
    chosen = keys[labels.index(choice)] if choice in labels else current
    return {} if chosen == current else {"npm": chosen}


def _ask_rescan(manager: ConfigManager, provider: str, cache_info: dict,
                url_or_key_changed: bool) -> bool:
    """Ofrecer un escaneo para comprobar la URL o la api key nueva."""
    if url_or_key_changed:
        reason = "has cambiado la URL o la api key"
    elif provider_needs_rescan(cache_info):
        reason = "el provider no esta accesible o hace tiempo que no se escanea"
    else:
        return False

    if not ConfigUI.ask_yes_no(f"¿Escanear {provider} ahora para actualizar los modelos? "
                               f"[{reason}]", default="y"):
        return False

    if scan_single_provider(provider, cache_info, manager, manager.config_data,
                            int(time.time())):
        ConfigUI.print_success("Escaneo completado.")
        return True

    ConfigUI.print_warning("No se pudo contactar con el provider; se conserva lo anterior.")
    return False


def _ask_models(manager: ConfigManager, provider: str, cache_info: dict,
                advanced: bool, only_model: str) -> int:
    """Repasar las opciones de un modelo concreto, de todos, o de ninguno."""
    models = normalize_models(cache_info.get("models"))
    configured = provider_entry_from_config(manager, provider).get("models")
    if not isinstance(configured, dict):
        configured = {}

    if only_model:
        targets = [only_model]
    else:
        print_model_menu(models, configured)
        raw = ConfigUI.ask_raw("Modelo a repasar", hint="Intro ninguno, 'todos' todos")
        if raw is None or raw == "":
            return 0
        text = raw.strip()
        known = list(models) or list(configured)
        if text.lower() in ("t", "todos", "all", "todo"):
            targets = known
        elif text.isdigit() and 1 <= int(text) <= len(known):
            targets = [known[int(text) - 1]]
        else:
            targets = [text]

    touched = 0
    for model_id in targets:
        if model_id not in models and model_id not in configured:
            ConfigUI.print_error(f"'{model_id}' no está en '{provider}'.")
            continue
        entry = models.setdefault(model_id, {"name": model_id})
        changes = configure_model_entry(entry, advanced=advanced,
                                        header=f"Opciones de {provider}/{model_id}")
        if not changes:
            ConfigUI.print_info(f"'{model_id}': sin cambios.")
            continue
        for warning in sync_model_config(manager, provider, model_id, entry,
                                         changed_keys=list(changes)):
            ConfigUI.print_warning(f"{model_id}: {warning}")
        touched += 1

    if models:
        cache_info["models"] = models
    return touched


def _prune_gone_models(manager: ConfigManager, provider: str, cache_info: dict,
                       backup_done: list) -> int:
    """Quitar los modelos que estan en opencode.json pero ya no existen segun la caché.

    `ocm update` nunca borra modelos, para no perder lo escrito a mano; aqui el
    usuario lo pide explicitamente.
    """
    entry = provider_entry_from_config(manager, provider)
    models_in_config = entry.get("models")
    if not isinstance(models_in_config, dict) or not models_in_config:
        return 0

    cached = normalize_models(cache_info.get("models"))
    if not cached:
        ConfigUI.print_info("La caché no tiene modelos: nada que podar. Escanea antes "
                            f"('ocm cache update {provider}') para saber cuales sobran.")
        return 0

    gone = [model_id for model_id in models_in_config if model_id not in cached]
    if not gone:
        return 0

    print(f"\n{Colors.YELLOW}En opencode.json pero no en el ultimo escaneo de "
          f"{provider}:{Colors.RESET}")
    for model_id in gone:
        print(f"  - {model_id}")

    if not cache_info.get("last_scan"):
        ConfigUI.print_warning("Ojo: este provider nunca se escaneo, puede que si existan.")
    elif cache_info.get("reachable") is False:
        ConfigUI.print_warning("Ojo: el provider no esta accesible; los modelos que ves son "
                               "los del ultimo escaneo bueno.")

    if not ConfigUI.ask_yes_no("¿Quitarlos de opencode.json y de la caché?", default="n"):
        ConfigUI.print_info("Se dejan. Luego: ocm model rm "
                            f"{provider} <MODELO>")
        return 0

    for model_id in gone:
        models_in_config.pop(model_id, None)
    entry["models"] = models_in_config
    if not backup_done:
        create_backup(manager.config_path)
        backup_done.append(True)
    manager.config_data.setdefault("provider", {})[provider] = entry
    manager.save_config()

    cache_info["models"] = cached
    ConfigUI.print_success(f"Quitados {len(gone)} modelo(s): {', '.join(gone)}")
    return len(gone)


def cmd_configure(manager: ConfigManager, args):
    """`ocm configure`: reconfigurar un provider campo a campo."""
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    cache_info = manager.cache_data.get("providers", {}).get(provider)
    if cache_info is None:
        ConfigUI.print_error(f"'{provider}' no está en la caché.")
        print("Ejecuta: " + Colors.CYAN + f"ocm new {provider}" + Colors.RESET +
              " (crea o reconfigura su entrada de caché)")
        return

    if refresh_cache_from_config(manager, provider):
        manager.save_cache(touch=False)

    entry = provider_entry_from_config(manager, provider)
    ConfigUI.print_header(f"Reconfigurar provider: {provider}")
    _print_current(provider, cache_info, entry)

    overrides = {}
    for flag, key in (("name", "name"), ("url", "url"), ("api_key", "api_key")):
        value = getattr(args, flag, None)
        if value:
            overrides[key] = value

    provider_type = cache_info.get("provider_type") or get_provider_type(provider, manager)

    fields = _ask_fields(provider, cache_info, entry, overrides)
    if not getattr(args, "no_api_style", False):
        for key, value in ask_api_style_fields(cache_info, provider_type).items():
            fields.setdefault(key, value)

    backup_done: list = []
    changes = 0

    if fields:
        changes += apply_provider_fields(manager, provider, cache_info, fields, backup_done)
        for key, value in fields.items():
            shown = mask_secret(value) if (key == "apiKey" and value) else value
            shown = "(quitado)" if value is None else shown
            print(f"  {Colors.BRIGHT_CYAN}{key}{Colors.RESET} -> {Colors.YELLOW}{shown}{Colors.RESET}")
    else:
        ConfigUI.print_info("Provider sin cambios.")

    if not getattr(args, "no_rescan", False):
        if _ask_rescan(manager, provider, cache_info,
                       "baseUrl" in fields or "apiKey" in fields):
            provider_type = cache_info.get("provider_type") or provider_type

    changes += _ask_models(manager, provider, cache_info,
                           bool(getattr(args, "advanced", False)),
                           getattr(args, "model", None))

    if not getattr(args, "no_prune", False):
        changes += _prune_gone_models(manager, provider, cache_info, backup_done)

    manager.save_cache(touch=False)

    if changes:
        ConfigUI.print_success(f"Provider '{provider}' reconfigurado ({changes} cambios).")
        print("Revisa con:  " + Colors.CYAN + f"ocm model list {provider}" + Colors.RESET)
        print("Aplica con: " + Colors.CYAN + f"ocm update {provider}" + Colors.RESET)
    else:
        ConfigUI.print_info("No ha cambiado nada.")
