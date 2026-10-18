"""
Asistente para configurar las opciones de un modelo.

`ocm model options [PROVIDER] [MODELO]` recorre los campos de `model_fields.FIELDS`
uno a uno mostrando el valor actual:

    Tokens de contexto (entrada) [131072] (ej: 4096 o 128k):
    Salidas que produce [por defecto: text] (1=text, 2=audio, 3=image, ...):

  * Intro            mantiene el valor que hay
  * un valor nuevo   lo reemplaza (se valida y se normaliza)
  * `-`              quita la opcion
  * `?`              explica el campo y muestra los valores habituales
  * `s`              termina (lo que ya cambiaste se queda guardado)

Lo que se responde se guarda en la caché (`provider_cache.json`) y, si el provider
ya existe en `opencode.json`, se escribe alli en el mismo momento.
"""

import json

from ..config import ConfigManager, ConfigUI, Colors
from ..cache_models import normalize_models
from ..model_fields import (
    KEEP,
    coerce,
    describe_model,
    format_value,
    get_value,
    serialize_model,
    set_value,
    spec_for,
    visible_fields,
)
from .model import _pick_from_list, resolve_provider
from .utils import provider_entry_from_config, refresh_cache_from_config

# El usuario decidio salir del asistente
STOP = object()

# Opciones que "posee" el asistente: si se quitan, desaparecen tambien del config.
# Las demas (`options`, `variants`, `cost`, `headers`, ...) son siempre ajenas.
WIZARD_OWNED_KEYS = frozenset(field.key.split(".")[0] for field in visible_fields(True))

# Palabras que significan "quitar esta opcion" y "salir del asistente"
UNSET_WORDS = ("-", "ninguna", "ninguno", "ningun", "vacío", "vacio", "null", "none")
SKIP_WORDS = ("s", "salir", "fin", "q", "skip", "terminar")
HELP_WORDS = ("?", "h", "ayuda", "help")


def _field_hint(spec) -> str:
    """Texto corto de ayuda que va junto al prompt."""
    if spec.kind == "bool":
        return "y/n"
    if spec.kind == "int":
        return "ej: 4096 o 128k"
    if spec.kind == "multi":
        # El numero es la posicion en MODALITIES, la misma que usa parse_modalities
        mapa = ", ".join(f"{indice}={valor}"
                         for indice, valor in enumerate(spec.presets, start=1))
        return mapa + " o text,image"
    if spec.kind == "choice":
        return "/".join(spec.presets)
    return ""


def _print_field_help(spec):
    """Detalle de un campo: para que sirve y que valores son habituales."""
    if spec.help:
        ConfigUI.print_info(spec.help)
    if not spec.presets:
        return
    if spec.kind == "multi":
        print("        opciones: " + ", ".join(
            f"{index}={value}" for index, value in enumerate(spec.presets, start=1)))
        print("        varias de golpe: '1,3' o 'text,image'")
    elif spec.kind == "int":
        print("        habituales: " + ", ".join(str(value) for value in spec.presets))
    else:
        print("        valores: " + ", ".join(str(value) for value in spec.presets))


def ask_field(spec, current):
    """Preguntar un campo de un modelo.

    Returns:
        KEEP (no lo toco) | STOP (salir) | None (quitarlo) | valor ya validado
    """
    while True:
        raw = ConfigUI.ask_raw(f"  {spec.label}", format_value(spec, current), _field_hint(spec))

        if raw is None or raw == "":
            return KEEP

        text = raw.strip()
        lowered = text.lower()

        if lowered in HELP_WORDS:
            _print_field_help(spec)
            continue
        if lowered in UNSET_WORDS:
            return None
        if lowered in SKIP_WORDS:
            return STOP

        try:
            return coerce(spec, text)
        except ValueError as error:
            ConfigUI.print_warning(str(error))


def configure_model_entry(entry: dict, advanced: bool = False, only=None,
                          header: str = "") -> dict:
    """Recorrer los campos de un modelo preguntando uno por uno.

    Args:
        entry: entrada de caché del modelo (se modifica in place)
        advanced: incluir tambien las opciones avanzadas
        only: claves concretas a preguntar (todos los visibles si es None)
        header: titulo que se muestra arriba

    Returns:
        dict con los campos modificados (vacio si no cambio nada)
    """
    specs = [spec_for(key) for key in only] if only else list(visible_fields(advanced))

    if header:
        print(f"\n{Colors.BOLD}{header}{Colors.RESET}")
    print(f"{Colors.YELLOW}  Intro mantiene, '-' quita, '?' ayuda, 's' sale{Colors.RESET}")

    # El nombre viene siempre rellenado (con el id), asi que no cuenta para saber si
    # el modelo ya tiene opciones guardadas.
    opciones = [spec for spec in specs if spec.key != "name"]
    if not any(get_value(entry, spec.key) not in (None, "", [], {}) for spec in opciones):
        # Un modelo recien escaneado no trae nada guardado: los corchetes ensenan lo
        # que opencode asume, no algo que ocm vaya a escribir si dan Intro.
        print(f"{Colors.WHITE}  Sin opciones guardadas: lo de entre corchetes es lo que"
              f" opencode asume; Intro lo deja sin escribir{Colors.RESET}")

    changes = {}
    for spec in specs:
        if spec.depends_on and not get_value(entry, spec.depends_on):
            continue

        value = ask_field(spec, get_value(entry, spec.key))
        if value is STOP:
            print(f"{Colors.YELLOW}  Sales del asistente; lo ya cambiado se guarda.{Colors.RESET}")
            break
        if value is KEEP:
            continue

        set_value(entry, spec.key, value)
        changes[spec.key] = value

    return changes


def apply_assignments(entry: dict, assignments) -> dict:
    """Aplicar asignaciones `clave=valor` sin preguntar (modo script).

    Acepta las rutas de `model_fields`: 'limit.context=131072',
    'modalities.input=text,image', 'reasoning=y', 'status=beta'.
    """
    changes = {}
    for item in assignments or []:
        if "=" not in item:
            ConfigUI.print_error(f"Falta '=' en '{item}' (ej: limit.context=131072)")
            continue

        key, _, raw_value = item.partition("=")
        key = key.strip()
        try:
            spec = spec_for(key)
        except KeyError:
            ConfigUI.print_error("Campo desconocido: '{}'. Válidos: {}".format(
                key, ", ".join(field.key for field in visible_fields(True))))
            continue

        if raw_value.strip().lower() in UNSET_WORDS:
            set_value(entry, key, None)
        else:
            try:
                set_value(entry, key, coerce(spec, raw_value))
            except ValueError as error:
                ConfigUI.print_error(f"{key}: {error}")
                continue

        changes[key] = get_value(entry, key)
    return changes


def sync_model_config(manager: ConfigManager, provider: str, model_id: str, entry: dict,
                      changed_keys=None) -> list:
    """Repercutir las opciones de un modelo en `opencode.json`.

    Solo escribe si el provider ya esta en el archivo; si no, sera `ocm update`
    quien lo añada.

    Args:
        entry: entrada de caché del modelo, ya actualizada
        changed_keys: claves que el usuario modifico realmente (p.ej.
            ['limit.context']). Si es None se escriben todas las que gestiona el
            asistente. Las demas claves propias se dejan como estaban, y las
            ajenas (`options`, `variants`, `cost`, ...) no se tocan nunca.

    Returns:
        avisos de validacion
    """
    serialized, warnings = serialize_model(entry)
    serialized.setdefault("name", entry.get("name") or model_id)

    config_entry = provider_entry_from_config(manager, provider)
    if not config_entry:
        ConfigUI.print_info(f"'{provider}' todavía no está en opencode.json; "
                            f"se aplicará con 'ocm update {provider}'.")
        return warnings

    models = config_entry.get("models")
    if not isinstance(models, dict):
        models = {}

    existing = models.get(model_id)
    is_new = not isinstance(existing, dict)
    current = existing if isinstance(existing, dict) else {}
    if is_new:
        ConfigUI.print_info(f"El modelo '{model_id}' no estaba en opencode.json; se añade.")
    models[model_id] = current

    if changed_keys is None or is_new:
        # Recien creado: se escribe todo lo que hay en la caché
        owned = set(WIZARD_OWNED_KEYS)
    else:
        owned = {key.split(".")[0] for key in changed_keys}
        # El nombre visible se escribe siempre: es lo que hace visible el modelo
        if serialized.get("name"):
            owned.add("name")

    for key, value in serialized.items():
        if key in owned:
            current[key] = value
    for key in owned:
        if key not in serialized:
            current.pop(key, None)

    config_entry["models"] = models
    manager.config_data.setdefault("provider", {})[provider] = config_entry
    manager.save_config()
    return warnings


def print_model_menu(models: dict, configured: dict) -> list:
    """Listar los modelos con su nombre visible y opciones; devuelve los ids."""
    ids = list(models) + [mid for mid in configured if mid not in models]
    if not ids:
        return ids

    print(f"\n{'Modelo':<38}{'Nombre visible':<28}Opciones")
    print("-" * 100)
    for model_id in ids:
        entry = models.get(model_id) or configured.get(model_id) or {}
        if not isinstance(entry, dict):
            entry = {}
        name = entry.get("name") or model_id
        print(f"{model_id:<38}{('' if name == model_id else name):<28}"
              f"{describe_model(entry)}")
    print()
    return ids


def _cache_entry_or_error(manager: ConfigManager, provider: str):
    cache_info = manager.cache_data.get("providers", {}).get(provider)
    if cache_info is None:
        ConfigUI.print_error(f"'{provider}' no está en la caché.")
        print(f"Ejecuta: ocm new {provider}  (crea la entrada de caché desde opencode.json)")
    return cache_info


def cmd_model_options(manager: ConfigManager, args):
    """`ocm model options`: configurar uno o varios modelos pregunta a pregunta."""
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    cache_info = _cache_entry_or_error(manager, provider)
    if cache_info is None:
        return

    if refresh_cache_from_config(manager, provider):
        manager.save_cache(touch=False)

    models = normalize_models(cache_info.get("models"))
    cache_info["models"] = models

    configured = provider_entry_from_config(manager, provider).get("models", {})
    if not isinstance(configured, dict):
        configured = {}

    assignments = getattr(args, "set", None)
    advanced = bool(getattr(args, "advanced", False))
    wanted = getattr(args, "model", None)

    if wanted and wanted not in models and wanted not in configured:
        ConfigUI.print_error(f"El modelo '{wanted}' no existe en '{provider}'.")
        print_model_menu(models, configured)
        return

    if wanted:
        targets = [wanted]
    else:
        ids = print_model_menu(models, configured)
        if not ids:
            ConfigUI.print_error("Este provider no tiene modelos en la caché.")
            print(f"Ejecuta: ocm cache update {provider}")
            return
        if getattr(args, "all", False):
            targets = ids
        else:
            picked = _pick_from_list(ids, "modelo")
            if not picked:
                return
            targets = [picked]

    changed_any = False
    for model_id in targets:
        entry = models.setdefault(model_id, {"name": model_id})

        if assignments:
            changes = apply_assignments(entry, assignments)
        else:
            changes = configure_model_entry(
                entry, advanced=advanced, header=f"Opciones de {provider}/{model_id}")

        if not changes:
            ConfigUI.print_info(f"'{model_id}': sin cambios.")
            continue

        changed_any = True
        for warning in sync_model_config(manager, provider, model_id, entry,
                                        changed_keys=list(changes)):
            ConfigUI.print_warning(f"{model_id}: {warning}")
        print(f"{Colors.BRIGHT_GREEN}  ✓ {model_id}{describe_model(entry)}{Colors.RESET}")

    if changed_any:
        # touch=False: cambiar opciones no es un escaneo, no movemos la fecha
        manager.save_cache(touch=False)
        ConfigUI.print_success(f"Opciones guardadas ({len(targets)} modelo(s)).")
        print("Verifica con: " + Colors.CYAN + f"ocm model list {provider}" + Colors.RESET)


def cmd_model_show(manager: ConfigManager, args):
    """`ocm model show`: ver en detalle que hay configurado para un modelo."""
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    if refresh_cache_from_config(manager, provider):
        manager.save_cache(touch=False)

    cache_info = manager.cache_data.get("providers", {}).get(provider) or {}
    models = normalize_models(cache_info.get("models"))
    configured = provider_entry_from_config(manager, provider).get("models", {})
    if not isinstance(configured, dict):
        configured = {}

    ids = list(models) + [mid for mid in configured if mid not in models]
    model_id = getattr(args, "model", None) or _pick_from_list(ids, "modelo")
    if not model_id or (not models.get(model_id) and not configured.get(model_id)):
        ConfigUI.print_error("No hay opciones guardadas para ese modelo.")
        return

    merged = dict(configured.get(model_id) or {})
    merged.update(models.get(model_id) or {})

    ConfigUI.print_header(f"{provider}/{model_id}")
    print(json.dumps(merged, indent=2, ensure_ascii=False))

    for warning in serialize_model(merged)[1]:
        ConfigUI.print_warning(warning)
