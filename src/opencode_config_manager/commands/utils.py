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
    normalize_models,
)
from ..model_fields import serialize_model

DEFAULT_NPM = "@ai-sdk/openai-compatible"

# Estilos de API disponibles para un provider local estilo OpenAI. La clave es el
# paquete `npm` que entiende opencode; el valor es lo que se muestra en el menu.
API_STYLES = {
    "@ai-sdk/openai-compatible": "OpenAI chat completions (vLLM, LM Studio, llama.cpp...)",
    "@ai-sdk/openai": "OpenAI responses API",
}

# Claves de provider que ocm escribe (ProviderConfig en el schema de opencode)
PROVIDER_FIELDS = ("api", "name", "env", "id", "npm", "whitelist", "blacklist")

# Claves de provider.options que ocm escribe
OPTION_FIELDS = ("apiKey", "baseURL", "headers", "timeout", "headerTimeout",
                 "chunkTimeout", "setCacheKey")

# Alias de nombre que resuelven a un tipo de provider
TYPE_ALIASES = {
    "ollama": "ollama",
    "ollama-cli": "ollama",
    "vllm": "vllm",
    "v-llm": "vllm",
    "llama.cpp": "vllm",
    "llamacpp": "vllm",
    "llama-server": "vllm",
    "lmstudio": "vllm",
    "lm-studio": "vllm",
    "openai": "vllm",
    "openai-compatible": "vllm",
}

# Los dos unicos tipos que guarda ocm en la caché

# Como se enseña cada tipo al usuario
TIPOS_ETIQUETA = {
    "ollama": "Ollama  (escanea /api/tags)",
    "vllm": "vLLM o compatible con OpenAI  (escanea /v1/models)",
}

# De donde salio el tipo que esta en la caché
ETIQUETA_FUENTE = {"manual": "fijado a mano", "auto": "detectado"}

# El endpoint con el que se reconoce cada tipo
ENDPOINT_TIPO = {"ollama": "/api/tags", "vllm": "/v1/models"}

# Y su contrario, para el reintento automatico del escaneo
OTRO_TIPO = {"ollama": "vllm", "vllm": "ollama"}


def normalizar_tipo(valor) -> str | None:
    """'llama.cpp' -> 'vllm', ' Ollama ' -> 'ollama', lo que no se conoce -> None."""
    if not valor:
        return None
    return TYPE_ALIASES.get(str(valor).strip().lower())


def url_para_config(base_url: str) -> str:
    """La URL que va en options.baseURL de opencode.json.

    ollama y vLLM sirven la API de OpenAI bajo /v1, asi que la regla no depende del
    tipo: se anade /v1 cuando el servidor esta en la raiz de la URL. Si alguien pone
    una URL con su propio camino (http://host/proxy) se respeta tal cual.
    """
    url = (base_url or "").rstrip("/")
    if not url:
        return url
    resto = url.partition("://")[2]
    camino = resto.partition("/")[2] if resto else ""
    return url + "/v1" if camino in ("", "/") else url


def get_provider_type(provider_name: str, manager: ConfigManager = None) -> str:
    """Obtener el tipo de provider desde la caché o por convención de nombre.

    Prioridad:
    1. Campo 'provider_type' en la caché del provider, pasado por alias
    2. Alias conocido por nombre ('ollama', 'vllm', 'llama.cpp', ...)
    3. Fallback: 'vllm' (compatible con OpenAI), que es lo que ocm escribe siempre
    """
    if manager and manager.cache_data:
        cache_info = manager.cache_data.get("providers", {}).get(provider_name, {})
        tipo = normalizar_tipo(cache_info.get("provider_type"))
        if tipo:
            return tipo

    tipo = normalizar_tipo(provider_name)
    if tipo:
        return tipo

    return "vllm"


def tipo_guardado(provider_name: str, cache_info: dict,
                  manager: ConfigManager = None) -> str:
    """El tipo que dice la caché (o, si no, opencode.json), pasado por alias.

    Devuelve 'ollama', 'vllm' o None cuando no se sabe.
    """
    tipo = normalizar_tipo((cache_info or {}).get("provider_type"))
    if not tipo and manager is not None:
        configured = provider_entry_from_config(manager, provider_name)
        tipo = normalizar_tipo(configured.get("provider_type") or configured.get("type"))
    return tipo


def estado_tipo(provider_name: str, cache_info: dict,
                manager: ConfigManager = None) -> dict:
    """Como esta el tipo de un provider: {'tipo', 'fuente', 'evidencia'}.

    'fuente' es 'manual' si alguien lo fijo (configure/cache type/--type), 'auto'
    si lo decidio un escaneo, y None si nunca se pose. 'evidencia' guarda el
    endpoint por el que contesto el servidor en el ultimo escaneo.
    """
    fuente = (cache_info or {}).get("type_source")
    if fuente not in ("manual", "auto"):
        fuente = None
    return {
        "tipo": tipo_guardado(provider_name, cache_info, manager),
        "fuente": fuente,
        "evidencia": (cache_info or {}).get("type_evidence"),
    }


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





def default_model_label(model_id: str, provider_label: str) -> str:
    """Nombre visible por defecto: 'default · chati'.

    El selector de opencode v2 no muestra el provider junto al modelo, asi que dos
    modelos con el mismo id (varios 'default') serian indistinguibles. Solo cambia la
    etiqueta: a la API se le sigue mandando la clave del modelo.
    """
    return f"{model_id} · {provider_label}" if provider_label else model_id


MAX_BACKUPS = 10


def create_backup(config_path: Path) -> str:
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


def build_provider_config(provider_name: str, cache_info: dict) -> dict:
    """Configuración "deseada" de un provider según la caché.

    Es lo que ocm quiere escribir; se combina con lo existente mediante
    `merge_provider_config`, no se asigna directamente.

    No depende del tipo de servidor: lo que ve opencode (npm + baseURL + modelos) es
    igual para Ollama y para vLLM, porque los dos atienden la API de OpenAI bajo /v1.
    El tipo solo decide que endpoint escanea ocm (commands/scan.py).

    Returns:
        {"name": ..., "options": {...}, "models": {...}}
    """
    config = {
        "npm": cache_info.get("npm") or DEFAULT_NPM,
        "name": cache_info.get("name") or provider_name,
    }

    # La URL no depende del tipo: ollama y vLLM atienden la API de OpenAI bajo /v1
    config_url = url_para_config(cache_info.get("baseUrl") or "http://localhost:11434")

    options = {"baseURL": config_url}
    if cache_info.get("apiKey"):
        options["apiKey"] = cache_info["apiKey"]
    config["options"] = options

    models = {}
    for model_id, entry in normalize_models(cache_info.get("models")).items():
        # serialize_model pasa los valores al formato del config: '128k' -> 131072,
        # modalidades validadas, y descarta claves que opencode no conoce
        serialized, avisos = serialize_model(entry)
        for aviso in avisos:
            ConfigUI.print_warning(f"{provider_name}/{model_id}: {aviso}")
        nombre = entry.get("name")
        if not nombre or nombre == model_id:
            nombre = default_model_label(model_id, config["name"])
        models[model_id] = {**serialized, "name": nombre}
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
        # Un nombre que es copia del id es que nadie lo eligio: se mejora sin --force
        if current.get("name") == model_id and wanted.get("name") not in (None, model_id):
            current["name"] = wanted["name"]
            changes.append(f"models.{model_id}.name")
        apply(current, wanted, MANAGED_MODEL_FIELDS, f"models.{model_id}.")

    return merged, changes
