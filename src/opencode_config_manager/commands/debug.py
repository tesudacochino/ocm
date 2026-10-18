"""
Comandos de depuración y validación.
"""

import json

from ..config import ConfigManager, ConfigUI
from ..cache_models import MANAGED_MODEL_FIELDS
from ..model_fields import MODALITIES
from .encoded import format_notes

# Claves de provider aceptadas por opencode según la clave raíz
PROVIDER_KEYS = {"api", "name", "env", "id", "npm", "whitelist", "blacklist",
                 "options", "models"}
PROVIDER_KEYS_V2 = {"canonical", "name", "env", "package", "compatibility",
                    "settings", "headers", "body", "models"}

# Claves de modelo aceptadas ('provider' clásico y 'providers' de v2)
MODEL_KEYS = set(MANAGED_MODEL_FIELDS) | {"disabled"}
MODEL_KEYS_V2 = {"modelID", "family", "name", "releaseDate", "compatibility",
                 "package", "settings", "headers", "body", "capabilities",
                 "variants", "cost", "disabled", "limit"}

# Pistas para los errores más comunes al escribir la config a mano
KEY_HINTS = {
    "baseUrl": "debería ser 'baseURL' dentro de 'options'",
    "baseURL": "debería ir dentro de 'options'",
    "thinkingLevelMap": "no existe en el esquema; usa 'variants' con 'settings'",
    "reasoning_effort": "usa 'variants' o las opciones del proveedor",
}


# Claves de un formato que estan mal colocadas en el otro
FORMAT_HINTS_SINGULAR = {
    "capabilities": "en 'provider' las capacidades son 'tool_call', 'reasoning' y 'modalities'",
    "modelID": "en 'provider' el id es la clave del modelo (o 'id')",
    "releaseDate": "en 'provider' es 'release_date'",
    "compatibility": "no existe en 'provider'; usa 'options'",
    "canonical": "'canonical' es del formato 'providers'",
}

FORMAT_HINTS_ENCODED = {
    "tool_call": "en 'providers' va en 'capabilities.tools'",
    "toolcall": "en 'providers' va en 'capabilities.tools'",
    "modalities": "en 'providers' va en 'capabilities.input' y 'capabilities.output'",
    "temperature": "en 'providers' va en 'capabilities.temperature'",
    "release_date": "en 'providers' es 'releaseDate'",
    "attachment": "no existe en 'providers'; usa 'capabilities.input'",
    "interleaved": "no existe en 'providers'; prueba en 'settings' o 'variants'",
    "provider": "no existe en 'providers'; el paquete se fija con 'package'",
}


def _hint(key: str, encoded: bool):
    """Pista para una clave mal colocada, según el formato ('provider' o 'providers')."""
    container = "settings" if encoded else "options"
    if key in ("baseUrl", "baseURL", "apiKey", "headers"):
        return f"debería ir dentro de '{container}'"
    if key in ("api", "npm", "package"):
        if encoded and key != "package":
            return "en 'providers' el paquete se fija con 'package'"
        if not encoded and key == "api":
            return "para elegir el paquete del SDK usa 'npm' (o 'package' en 'providers')"
        if key == "package":
            return "en 'provider' el paquete se fija con 'npm'"
        return None
    if key == "options" and encoded:
        return "en 'providers' se usa 'settings'"
    if key == "settings" and not encoded:
        return "en 'provider' se usa 'options'"
    extra = (FORMAT_HINTS_ENCODED if encoded else FORMAT_HINTS_SINGULAR).get(key)
    return extra or KEY_HINTS.get(key)


def _check_provider(pname: str, pconfig: dict, path: str, encoded: bool = False) -> list:
    """Avisos sobre claves de provider y de modelos según el esquema oficial."""
    notes = []
    provider_allowed = PROVIDER_KEYS_V2 if encoded else PROVIDER_KEYS
    model_allowed = MODEL_KEYS_V2 if encoded else MODEL_KEYS

    for key in pconfig:
        if key in provider_allowed:
            continue
        hint = _hint(key, encoded)
        notes.append(f"{path}: clave no reconocida '{key}'" + (f" ({hint})" if hint else ""))

    models = pconfig.get("models")
    if models is None:
        return notes

    if not isinstance(models, dict):
        notes.append(f"{path}.models debe ser un objeto keyed por el id de cada modelo "
                     "(tal como lo escribe 'ocm update')")
        return notes

    for mid, entry in models.items():
        if not isinstance(entry, dict):
            notes.append(f"{path}.models.{mid} debe ser un objeto")
            continue
        for key in entry:
            if key in model_allowed:
                continue
            hint = KEY_HINTS.get(key)
            if encoded and key in ("input", "output"):
                hint = f"en v2 va en 'capabilities.{key}'"
            notes.append(f"{path}.models.{mid}: clave no reconocida '{key}'"
                         + (f" ({hint})" if hint else ""))

        if encoded:
            caps = entry.get("capabilities")
            if isinstance(caps, dict):
                for flag in ("tools", "temperature"):
                    if flag in caps and not isinstance(caps[flag], bool):
                        notes.append(f"{path}.models.{mid}: 'capabilities.{flag}' "
                                     "debe ser true/false")
                if "reasoning" in caps and not isinstance(caps["reasoning"], (bool, dict)):
                    notes.append(f"{path}.models.{mid}: 'capabilities.reasoning' debe ser "
                                 "true/false u objeto")
                for side in ("input", "output"):
                    if side not in caps:
                        continue
                    value = caps[side]
                    if not isinstance(value, list):
                        notes.append(f"{path}.models.{mid}: 'capabilities.{side}' debe ser "
                                     "una lista de modalidades")
                        continue
                    for item in value:
                        if item not in MODALITIES:
                            notes.append(f"{path}.models.{mid}: modalidad '{side}' no valida: "
                                         f"'{item}'")
            elif entry.get("capabilities") is not None:
                notes.append(f"{path}.models.{mid}: 'capabilities' debe ser un objeto")

            variants = entry.get("variants")
            if isinstance(variants, dict):
                notes.append(f"{path}.models.{mid}: en 'providers' 'variants' es una lista "
                             "de objetos con 'id' y 'settings'")

        limit = entry.get("limit")
        if isinstance(limit, dict) and not {"context", "output"} <= set(limit):
            notes.append(f"{path}.models.{mid}: 'limit' debería incluir 'context' y 'output'")

        modalities = entry.get("modalities")
        if not encoded and isinstance(entry.get("variants"), list):
            notes.append(f"{path}.models.{mid}: en 'provider' 'variants' es un objeto cuya "
                         "clave es el id de la variante")
        if isinstance(modalities, dict):
            for side in ("input", "output"):
                for value in modalities.get(side) or []:
                    if value not in MODALITIES:
                        notes.append(f"{path}.models.{mid}: modalidad '{side}' no válida: '{value}'")

    return notes


def validate_config(config_data: dict) -> tuple[bool, list[str], list[str]]:
    """Validar integridad de la configuración según formato de opencode.ai.

    Basado en el schema oficial: https://opencode.ai/config.json
    Ningún campo es obligatorio. Se validan tipos cuando están presentes.
    """
    errors = []
    warnings = []

    # Verificar estructura base
    if not isinstance(config_data, dict):
        errors.append("La configuración debe ser un objeto JSON")
        return False, errors, []

    # Verificar model (opcional, pero si existe debe tener formato correcto)
    model = config_data.get("model")
    if model is not None:
        if not isinstance(model, str):
            errors.append("Campo 'model' debe ser un string")
        elif "/" not in model:
            warnings.append("Campo 'model' debería ser en formato 'provider/model' (ej: 'ollama/llama3')")

    # Verificar provider como objeto
    provider = config_data.get("provider")
    if provider is not None and not isinstance(provider, dict):
        errors.append("Campo 'provider' debe ser un objeto JSON")

    # Formato nuevo de opencode v2: 'providers' (plural), con otro esquema
    providers = config_data.get("providers")
    if providers is not None and not isinstance(providers, dict):
        errors.append("Campo 'providers' debe ser un objeto JSON")

    # Verificar que hay al menos providers o model configurado
    if not provider and not providers and not model:
        warnings.append("No hay 'provider', 'providers' ni 'model' configurado. Ejecuta: ocm new")

    # Verificar que cada provider tiene estructura correcta
    if isinstance(provider, dict):
        for pname, pconfig in provider.items():
            if not isinstance(pconfig, dict):
                errors.append(f"Provider '{pname}' debe ser un objeto")
                continue
            if "models" not in pconfig and "npm" in pconfig:
                warnings.append(f"Provider '{pname}' no tiene modelos configurados")
            warnings.extend(_check_provider(pname, pconfig, f"provider.{pname}"))

    # Formato nuevo de opencode v2: 'providers' (plural), con otro esquema
    if isinstance(providers, dict):
        for pname, pconfig in providers.items():
            if not isinstance(pconfig, dict):
                errors.append(f"Provider '{pname}' (en 'providers') debe ser un objeto")
                continue
            warnings.extend(_check_provider(pname, pconfig, f"providers.{pname}", True))

    # Campos válidos según schema de opencode.ai (opencode.ai/config.json)
    valid_top_level_fields = {
        "$schema",
        "shell", "model", "default_agent", "update", "share", "enterprise",
        "username", "permissions", "policies", "agents", "snapshots", "watcher",
        "formatter", "lsp", "media", "tool_output", "mcp", "compaction", "skills",
        "commands", "instructions", "references", "websearch", "plugins",
        "worktree", "warming", "experimental", "logLevel", "server", "command",
        "reference", "snapshot", "plugin", "autoshare", "autoupdate",
        "disabled_providers", "enabled_providers", "small_model", "subagent_depth",
        "mode", "agent", "provider", "providers", "layout", "permission",
        "tools", "attachment",
        "theme", "tui", "keybinds", "ollama",
    }
    # Convivencia de los dos bloques: 'provider' (el que registra providers) y 'providers'
    warnings.extend(format_notes(config_data))

    unknown_fields = [key for key in config_data.keys() if key not in valid_top_level_fields]
    for key in unknown_fields:
        warnings.append(f"Campo no reconocido en schema de opencode: '{key}'")

    return len(errors) == 0, errors, warnings


def cmd_debug_config(manager: ConfigManager, args):
    """Validar integridad de la configuración."""
    manager.load_config()

    ConfigUI.print_header("Validación de Configuración")
    print(f"Archivo: {manager.config_path}")
    print(f"Existente: {manager.config_path.exists()}")

    if not manager.config_path.exists():
        ConfigUI.print_error("Archivo de configuración no encontrado.")
        return

    print("\nContenido:")
    print(json.dumps(manager.config_data, indent=2, ensure_ascii=False))

    print("\n=== Análisis ===")
    is_valid, errors, warnings = validate_config(manager.config_data)

    if warnings:
        print(f"[ADVERTENCIA] {len(warnings)} aviso(s):")
        for w in warnings:
            print(f"  ℹ {w}")

    if is_valid and not errors:
        ConfigUI.print_success("Configuración válida")
    else:
        ConfigUI.print_error(f"{len(errors)} error(es) encontrado(s):")
        for e in errors:
            print(f"  ✗ {e}")

    print("\n=== Fin de validación ===\n")

