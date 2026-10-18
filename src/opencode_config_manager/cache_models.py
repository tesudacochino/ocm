"""
Modelos dentro de provider_cache.json.

Formato antiguo (v1): los modelos se guardaban como lista de ids.

    {"models": ["llama2", "mistral"]}

Formato nuevo (v2): cada modelo es un objeto keyed por id, lo que permite
guardar sus opciones (nombre visible, tamano de contexto, modalidades, ...).

    {"models": {"llama2": {"name": "Llama 2", "limit": {"context": 128000}}}}

Las claves que se guardan por modelo son las mismas que acepta opencode en
`provider.<id>.models.<id>`, asi que `ocm update` puede copiarlas tal cual.

Este modulo normaliza ambas formas al leer y migra la caché en memoria al
formato v2 (ver `migrate_cache`).
"""

import time
import uuid

from .model_fields import canonical_key

CACHE_VERSION_KEY = "cache_version"
CACHE_VERSION = 2

# Opciones de modelo que ocm sabe escribir en opencode.json.
# Son las claves validas de ModelConfig en https://opencode.ai/config.json
MANAGED_MODEL_FIELDS = (
    "id",
    "name",
    "family",
    "release_date",
    "attachment",
    "reasoning",
    "temperature",
    "tool_call",
    "interleaved",
    "cost",
    "limit",
    "modalities",
    "experimental",
    "status",
    "provider",
    "options",
    "headers",
    "variants",
)


def _clean_entry(model_id: str, data) -> dict:
    """Construir la entrada de un modelo asegurando al menos un nombre visible.

    Acepta tambien las formas que circulan por ahi (models.dev): `toolcall`,
    `capabilities.tools`, o `input`/`output` sueltos; todo acaba en las claves que
    entiende opencode. Lo que no se reconoce se deja tal cual.
    """
    entry = {}
    modalities = {}

    if isinstance(data, dict):
        for key, value in data.items():
            if key == "id" and value == model_id:
                continue  # el id ya es la clave del mapa
            if value is None or value == {} or value == []:
                continue

            if key == "capabilities" and isinstance(value, dict):
                for side, target in (("input", "input"), ("output", "output")):
                    if value.get(side) and not modalities.get(target):
                        modalities[target] = value[side]
                if value.get("tools"):
                    entry.setdefault("tool_call", True)
                if value.get("reasoning"):
                    entry.setdefault("reasoning", True)
                if value.get("vision"):
                    modalities.setdefault("input", ["text", "image"])
                continue

            if key in ("input", "output") and isinstance(value, (list, tuple)):
                # forma abreviada de las modalidades
                if not modalities.get(key):
                    modalities[key] = list(value)
                continue

            entry[canonical_key(key)] = value

        if isinstance(data.get("modalities"), dict):
            for side in ("input", "output"):
                if data["modalities"].get(side):
                    modalities[side] = data["modalities"][side]
            entry.pop("modalities", None)

    if modalities:
        entry["modalities"] = {side: modalities[side]
                              for side in ("input", "output") if modalities.get(side)}

    if not entry.get("name"):
        entry["name"] = model_id
    return entry


def normalize_models(models) -> dict:
    """Normalizar el campo 'models' de la caché a dict {model_id: entry}.

    Acepta lista de ids (v1), lista de objetos con 'id', dict (v2) o None.
    """
    if not models:
        return {}

    if isinstance(models, dict):
        return {str(mid): _clean_entry(str(mid), data) for mid, data in models.items()}

    if isinstance(models, (list, tuple)):
        result = {}
        for item in models:
            if isinstance(item, str):
                result[item] = _clean_entry(item, None)
            elif isinstance(item, dict) and item.get("id"):
                model_id = str(item["id"])
                result[model_id] = _clean_entry(model_id, item)
        return result

    return {}


def model_ids(models) -> list[str]:
    """Ids de modelos normalizados, en orden de insercion."""
    return list(normalize_models(models).keys())



def set_model_option(cache_entry: dict, model_id: str, key: str, value) -> dict:
    """Fijar (o borrar, con value=None) una opcion de un modelo en la caché."""
    models = normalize_models(cache_entry.get("models"))
    entry = models.setdefault(model_id, _clean_entry(model_id, None))
    if value is None:
        entry.pop(key, None)
        if key == "name":
            entry["name"] = model_id
    else:
        entry[key] = value
    cache_entry["models"] = models
    return cache_entry


def merge_scanned_models(existing_models, scanned_ids: list[str]) -> tuple[dict, list[str], list[str]]:
    """Combinar los modelos escaneados (ids puros) con la configuración guardada.

    Conserva nombre y opciones de los modelos que siguen existiendo, añade los
    nuevos y deja fuera los que ya no responde el provider.

    Returns:
        (models, agregados, eliminados)
    """
    existing = normalize_models(existing_models)
    final = {}
    added = []
    for model_id in scanned_ids:
        if model_id in existing:
            final[model_id] = existing[model_id]
        else:
            final[model_id] = _clean_entry(model_id, None)
            added.append(model_id)
    removed = [mid for mid in existing if mid not in final]
    return final, added, removed


def provider_needs_rescan(cache_entry: dict) -> bool:
    """True si el ultimo escaneo no pudo contactar con el provider.

    `ocm update` escribe desde la caché, asi que un provider caido sigue
    actualizandose con los modelos de la ultima pasada correcta.
    """
    return bool(cache_entry) and cache_entry.get("reachable") is False


DIAS_SCAN = 7


def scan_desactualizado(cache_entry: dict, dias: int = DIAS_SCAN) -> bool:
    """True si hace demasiado que no se escanea el provider.

    Lo usa el asistente de `ocm configure` para volver a mirar el servidor: es la
    unica forma de enterarse de que detras de la misma URL hay ahora otro motor,
    de que han subido el contexto o de que ha aparecido un modelo nuevo.
    """
    if not cache_entry:
        return False
    ultimo = cache_entry.get("last_scan")
    if not isinstance(ultimo, (int, float)) or ultimo <= 0:
        return True
    return (time.time() - ultimo) > dias * 86400


def adopt_model_options(cache_entry: dict, config_models: dict) -> bool:
    """Traer a la caché las opciones de modelo que solo existen en opencode.json.

    Si alguien escribio `limit` o `modalities` a mano en el config, la caché (que
    viene del escaneo) no las conoce. Sin esto, el asistente mostraria valores
    vacios y las listas de opciones se perderian al reescribir.

    La caché manda cuando ya tiene el campo: solo se rellenan huecos.
    `name` se adopta cuando en la caché es una copia del id (o sea, nadie lo
    personalizo) y en el config hay uno bonito.

    Returns:
        True si la entrada de caché cambio.
    """
    if not isinstance(cache_entry, dict) or not isinstance(config_models, dict):
        return False

    models = normalize_models(cache_entry.get("models"))
    if not models:
        return False

    changed = False
    for model_id, cache_model in models.items():
        config_model = config_models.get(model_id)
        if not isinstance(config_model, dict):
            continue

        cached_name = cache_model.get("name") or model_id
        config_name = config_model.get("name")
        if config_name and config_name != model_id and cached_name == model_id:
            cache_model["name"] = config_name
            changed = True

        for key in MANAGED_MODEL_FIELDS:
            if key == "id" or key in cache_model:
                continue
            value = config_model.get(key)
            if value is None or value == {} or value == []:
                continue
            cache_model[key] = value
            changed = True

    if changed:
        cache_entry["models"] = models
    return changed


def ensure_uid(cache_entry: dict) -> str:
    """Garantizar que el provider de caché tenga un uid estable."""
    uid_value = cache_entry.get("uid")
    if not uid_value:
        uid_value = uuid.uuid4().hex[:8]
        cache_entry["uid"] = uid_value
    return uid_value


def migrate_cache(cache_data: dict) -> bool:
    """Migrar la caché en memoria al formato v2.

    Returns True si habia datos en formato antiguo.
    """
    if not isinstance(cache_data, dict):
        return False

    providers = cache_data.get("providers")
    migrated = False
    if isinstance(providers, dict):
        for cache_entry in providers.values():
            if not isinstance(cache_entry, dict):
                continue
            models = cache_entry.get("models")
            if isinstance(models, (list, tuple)):
                cache_entry["models"] = normalize_models(models)
                migrated = True
            if not cache_entry.get("uid"):
                # Identificador estable: permite borrar el provider y volver a
                # crearlo con el mismo nombre sin perder las opciones guardadas
                cache_entry["uid"] = uuid.uuid4().hex[:8]
                migrated = True

    cache_data[CACHE_VERSION_KEY] = CACHE_VERSION
    return migrated
