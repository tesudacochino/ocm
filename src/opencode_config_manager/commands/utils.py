"""
Funciones utilitarias compartidas entre comandos.
"""

import shutil
import time
from pathlib import Path

from ..config import ConfigManager, ConfigUI


def get_provider_type(provider_name: str, manager: ConfigManager = None) -> str:
    """Obtener el tipo de provider desde la caché o por convención de nombre.

    Prioridad:
    1. Campo 'provider_type' en la caché del provider
    2. Nombre conocido ('ollama', 'vllm')
    3. Fallback: 'ollama'
    """
    # Si tenemos manager con caché, buscar el tipo guardado
    if manager and manager.cache_data:
        cache_info = manager.cache_data.get("providers", {}).get(provider_name, {})
        cached_type = cache_info.get("provider_type")
        if cached_type:
            return cached_type

    # Nombres que coinciden directamente con un tipo
    if provider_name in ("ollama", "vllm"):
        return provider_name

    return "ollama"


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


def sanitize_config_for_opencode(provider_type: str, provider_name: str = None,
                                  model_name: str = None, base_url: str = None,
                                  models_list: list = None, api_key: str = None) -> dict:
    """Sanitizar configuración para opencode.ai.

    Devuelve solo la configuración del provider específico, sin campos nivel superior.

    Formato de retorno:
    {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama",
      "options": {
        "baseURL": "http://localhost:11434/v1"
      },
      "models": {
        "model-id": {
          "name": "model-id"
        }
      }
    }
    """
    provider_config = {}

    provider_config["npm"] = "@ai-sdk/openai-compatible"
    provider_config["name"] = provider_name or provider_type.capitalize()

    # Asegurar que la URL tenga /v1 para providers ollama/vllm
    config_url = base_url or "http://localhost:11434"
    if provider_type in ("ollama", "vllm") and not config_url.endswith("/v1"):
        config_url = config_url.rstrip("/") + "/v1"

    provider_config["options"] = {"baseURL": config_url}
    if api_key:
        provider_config["options"]["apiKey"] = api_key

    # Añadir modelos (solo con nombre según formato oficial)
    if models_list:
        provider_config["models"] = {}
        for m in models_list:
            provider_config["models"][m] = {
                "name": m
            }
    elif model_name:
        provider_config["models"] = {
            model_name: {
                "name": model_name
            }
        }

    return provider_config
