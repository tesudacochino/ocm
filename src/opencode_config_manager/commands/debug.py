"""
Comandos de depuración y validación.
"""

import json

from ..config import ConfigManager, ConfigUI


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

    # Verificar que hay al menos providers o model configurado
    if not provider and not model:
        warnings.append("No hay 'provider' ni 'model' configurado. Ejecuta: ocm new")

    # Verificar que cada provider tiene estructura correcta
    if isinstance(provider, dict):
        for pname, pconfig in provider.items():
            if not isinstance(pconfig, dict):
                errors.append(f"Provider '{pname}' debe ser un objeto")
                continue
            if "models" not in pconfig and "npm" in pconfig:
                warnings.append(f"Provider '{pname}' no tiene modelos configurados")

    # Campos válidos según schema de opencode.ai
    valid_top_level_fields = {
        "$schema",
        "logLevel", "server", "command", "skills", "watcher", "snapshot",
        "plugin", "share", "autoshare", "autoupdate",
        "disabled_providers", "enabled_providers",
        "model", "small_model", "default_agent", "username",
        "mode", "agent", "provider",
        "mcp", "theme", "tui", "keybinds", "formatter",
        "instructions", "permission", "tools", "ollama",
    }
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

    print(f"\nContenido:")
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

    print(f"\n=== Fin de validación ===\n")

