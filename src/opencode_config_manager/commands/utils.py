"""
Funciones utilitarias compartidas entre comandos.

Incluye la escritura no destructiva de opencode.json: ocm nunca borra claves
que no gestiona y, salvo `--force`, tampoco sobrescribe las que ya existen.
"""

import copy
import shutil
import time
from pathlib import Path

from ..config import ConfigManager, ConfigUI
from ..cache_models import (
    MANAGED_MODEL_FIELDS,
    adopt_model_options,
    managed_options,
    normalize_models,
)

DEFAULT_NPM = "@ai-sdk/openai-compatible"

# Claves de provider que ocm escribe (ProviderConfig en el schema de opencode)
PROVIDER_FIELDS = ("api", "name", "env", "id", "npm", "whitelist", "blacklist")

# Claves de provider.options que ocm escribe
OPTION_FIELDS = ("apiKey", "baseURL", "headers", "timeout", "headerTimeout",
                 "chunkTimeout", "setCacheKey")

# Alias de nombre que resuelven a un tipo de provider
TYPE_ALIASES = {
    "ollama": "ollama",
    "vllm": "vllm",
    "llama.cpp": "vllm",
    "llamacpp": "vllm",
    "llama-server": "vllm",
    "lmstudio": "vllm",
    "lm-studio": "vllm",
    "openai-compatible": "vllm",
}


def get_provider_type(provider_name: str, manager: ConfigManager = None) -> str:
    """Obtener el tipo de provider desde la caché o por convención de nombre.

    Prioridad:
    1. Campo 'provider_type' en la caché del provider
    2. Alias conocido por nombre ('ollama', 'vllm', 'llama.cpp', ...)
    3. Fallback: 'ollama'
    """
    if manager and manager.cache_data:
        cache_info = manager.cache_data.get("providers", {}).get(provider_name, {})
        cached_type = cache_info.get("provider_type")
        if cached_type:
            return cached_type

    if provider_name in TYPE_ALIASES:
        return TYPE_ALIASES[provider_name]

    return "ollama"


def provider_entry_from_config(manager: ConfigManager, provider_name: str) -> dict:
    """Leer la configuración de un provider desde opencode.json (si existe)."""
    if not manager or manager.config_data is None:
        return {}
    entry = manager.config_data.get("provider", {})
    if not isinstance(entry, dict):
        return {}
    entry = entry.get(provider_name, {})
    return entry if isinstance(entry, dict) else {}


def refresh_cache_from_config(manager: ConfigManager, provider_name: str) -> bool:
    """Rellenar la caché con las opciones que solo existen en opencode.json.

    Sirve para que lo escrito a mano (un `limit`, unas `modalities`) se vea en los
    listados y en el asistente, y para que no se pierda al reescribir.

    Returns:
        True si la entrada de caché cambio (quien llama la guardará).
    """
    cache_entry = manager.cache_data.get("providers", {}).get(provider_name)
    if not isinstance(cache_entry, dict):
        return False

    config_models = provider_entry_from_config(manager, provider_name).get("models")
    if not isinstance(config_models, dict):
        return False

    return adopt_model_options(cache_entry, config_models)


def get_provider_name(manager: ConfigManager, provider_name: str) -> str:
    """Nombre visible (campo 'name') de un provider.

    Prioridad: caché → opencode.json → el propio nombre del provider.
    """
    if manager.cache_data:
        cached = manager.cache_data.get("providers", {}).get(provider_name, {}).get("name")
        if cached:
            return cached

    configured = provider_entry_from_config(manager, provider_name).get("name")
    if configured:
        return configured

    return provider_name


def displayify(name: str) -> str:
    """Nombre legible a partir de un id: 'ollama-local' -> 'Ollama Local'."""
    if not name:
        return name
    parts = [p for p in str(name).replace("_", " ").replace("-", " ").split() if p]
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def model_display_name(models: dict, model_id: str) -> str:
    """Nombre visible guardado para un modelo, o el propio id."""
    entry = models.get(model_id) or {}
    return entry.get("name") or model_id


MAX_BACKUPS = 10


def create_backup(config_path: Path, **_) -> str:
    """Crear backup de la configuración y rotar los antiguos.

    Mantiene un máximo de MAX_BACKUPS archivos .bak.

    Args:
        config_path: Ruta al archivo de configuración

    Returns:
        Ruta al archivo de backup creado
    """
    try:
        timestamp = int(time.time())
        backup_path = Path(f"{config_path}.bak.{timestamp}")
        shutil.copy2(str(config_path), str(backup_path))

        # Rotar: eliminar backups más antiguos si hay más de MAX_BACKUPS
        backups = sorted(config_path.parent.glob(f"{config_path.name}.bak.*"))
        while len(backups) > MAX_BACKUPS:
            oldest = backups.pop(0)
            oldest.unlink()

        return str(backup_path)
    except Exception as e:
        ConfigUI.print_error(f"No se pudo crear backup: {e}")
        return None


def build_provider_config(provider_name: str, cache_info: dict, provider_type: str = None) -> dict:
    """Configuración "deseada" de un provider según la caché.

    Es lo que ocm quiere escribir; se combina con lo existente mediante
    `merge_provider_config`, no se asigna directamente.

    Returns:
        {"name": ..., "options": {...}, "models": {...}}
    """
    provider_type = provider_type or get_provider_type(provider_name, None)

    config = {
        "npm": cache_info.get("npm") or DEFAULT_NPM,
        "name": cache_info.get("name") or provider_name,
    }

    config_url = cache_info.get("baseUrl") or "http://localhost:11434"
    if provider_type in ("ollama", "vllm") and not config_url.endswith("/v1"):
        config_url = config_url.rstrip("/") + "/v1"

    options = {"baseURL": config_url}
    if cache_info.get("apiKey"):
        options["apiKey"] = cache_info["apiKey"]
    config["options"] = options

    models = {}
    for model_id, entry in normalize_models(cache_info.get("models")).items():
        models[model_id] = {"name": entry.get("name") or model_id, **managed_options(entry)}
    if models:
        config["models"] = models

    return config


def merge_provider_config(existing: dict, desired: dict, force: bool = False) -> tuple[dict, list[str]]:
    """Combinar la configuración existente de un provider con la deseada.

    Reglas (no destructivas):
      - Las claves que ocm no gestiona (npm propio, env, whitelist, headers
        extra, opciones de modelo escritas a mano, ...) se conservan siempre.
      - Los modelos que ya estaban en opencode.json y ya no están en la caché
        NO se borran; ocm solo añade.
      - Sin `force`, una clave que ya existe no se sobrescribe: para cambiarla
        se usa `ocm model name` / `ocm rename` o `ocm update --force`.

    Args:
        existing: configuración actual del provider en opencode.json (o {})
        desired: configuración deseada desde la caché
        force: sobrescribir las claves que ocm gestiona

    Returns:
        (config_combinada, lista_de_cambios)
    """
    merged = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    changes: list[str] = []

    raw_options = merged.get("options")
    if not isinstance(raw_options, dict):
        if raw_options:
            changes.append("options (reincorporado como objeto)")
        merged["options"] = {}

    raw_models = merged.get("models")
    if not isinstance(raw_models, dict):
        # Una config escrita a mano con "models": [...] se convierte, no se borra
        converted = normalize_models(raw_models)
        if converted:
            changes.append("models (convertido a objeto)")
        merged["models"] = converted

    # npm: solo al crear el provider, nunca se pisa un proveedor de SDK manual
    if "npm" not in merged and desired.get("npm"):
        merged["npm"] = desired["npm"]
        changes.append("npm")

    def apply(target: dict, source: dict, fields, prefix: str):
        for key in fields:
            if key not in source:
                continue
            value = source[key]
            if target.get(key) != value and (force or key not in target):
                target[key] = value
                changes.append(f"{prefix}{key}")

    apply(merged, desired, PROVIDER_FIELDS, "")
    apply(merged["options"], desired.get("options") or {}, OPTION_FIELDS, "options.")

    models = merged["models"]
    for model_id, wanted in (desired.get("models") or {}).items():
        current = models.get(model_id)
        if not isinstance(current, dict):
            models[model_id] = copy.deepcopy(wanted)
            changes.append(f"models.{model_id} (alta)")
            continue
        apply(current, wanted, MANAGED_MODEL_FIELDS, f"models.{model_id}.")

    return merged, changes
