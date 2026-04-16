"""
Comandos de depuración y validación.
"""

import json

from ..config import ConfigManager, ConfigUI


def validate_config(config_data: dict) -> tuple[bool, list[str], list[str]]:
    """Validar integridad de la configuración según formato de opencode.ai.

    El formato correcto para opencode.ai es:
    - 'model': string en formato 'provider/model-id' (ej: 'ollama/llama3')
    - 'provider': objeto con configuración del provider
    - Opcional: 'ollama' para backwards compatibility
    """
    errors = []
    warnings = []

    # Verificar estructura base
    if not isinstance(config_data, dict):
        errors.append("La configuración debe ser un objeto JSON")
        return False, errors, []

    # Verificar model (campo obligatorio en formato opencode.ai)
    model = config_data.get("model")
    models = config_data.get("models")  # Soportar formato antiguo

    if model is None and models is None:
        errors.append("Falta campo 'model'. Debe ser en formato 'provider/model' (ej: 'ollama/llama3')")
    elif model is not None:
        if not isinstance(model, str):
            errors.append("Campo 'model' debe ser un string")
        elif "/" not in model:
            errors.append("Campo 'model' debe ser en formato 'provider/model' (ej: 'ollama/llama3')")

    # Verificar provider como objeto
    provider = config_data.get("provider")
    if provider is not None and not isinstance(provider, dict):
        errors.append("Campo 'provider' debe ser un objeto JSON")

    # Verificar configuración opcional de ollama (backwards compatibility)
    ollama_config = config_data.get("ollama")
    if ollama_config is not None:
        if not isinstance(ollama_config, dict):
            errors.append("Campo 'ollama' debe ser un objeto")
        elif "baseUrl" in ollama_config:
            if not isinstance(ollama_config["baseUrl"], str):
                errors.append("Campo 'ollama.baseUrl' debe ser un string")

    # Campos permitidos (según opencode.ai format)
    valid_top_level_fields = {
        "$schema",  # Esquema de validación de opencode.ai
        "model", "small_model", "provider",
        "theme", "autoupdate", "share",
        "permission", "tools", "agent", "command",
        "instructions", "mcp", "formatter", "tui", "keybinds",
        "disabled_providers", "ollama"
    }
    for key in config_data.keys():
        if key not in valid_top_level_fields:
            errors.append(f"Campo no reconocido: '{key}'")

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

    if is_valid:
        ConfigUI.print_success("Configuración válida")
    else:
        ConfigUI.print_error(f"{len(errors)} problema(s) encontrado(s):")
        for e in errors:
            print(f"  ✗ {e}")

        if warnings:
            print("\n[ADVERTENCIA]")
            for w in warnings:
                print(f"  ℹ {w}")

        if ConfigUI.ask_yes_no("¿Intentar reparar automáticamente?"):
            repair_count = 0

            # Reparar 'models' -> 'model'
            if "models" in manager.config_data:
                models_value = manager.config_data["models"]
                if isinstance(models_value, list) and models_value:
                    manager.config_data["model"] = models_value[0]
                    repair_count += 1
                    print("  + Convertiendo 'models' → 'model'...")
                del manager.config_data["models"]

            # Eliminar campo 'providers' antiguo
            if "providers" in manager.config_data:
                del manager.config_data["providers"]
                repair_count += 1
                print("  + Eliminando campo 'providers' obsoleto...")

            # Asegurar provider y model
            if "provider" not in manager.config_data:
                manager.config_data["provider"] = "ollama"
                repair_count += 1
                print("  + Agregando 'provider' por defecto...")

            if "model" not in manager.config_data:
                manager.config_data["model"] = "llama3"
                repair_count += 1
                print("  + Agregando 'model' por defecto...")

            if repair_count > 0:
                print(f"\n[REPARACIÓN] Se aplicaron {repair_count} correcciones")
                print(f"\nContenido reparado:")
                print(json.dumps(manager.config_data, indent=2, ensure_ascii=False))

                if ConfigUI.ask_yes_no("¿Guardar configuración reparada?"):
                    manager.save_config()
                    ConfigUI.print_success("Configuración guardada correctamente")
                else:
                    print("\nOperación cancelada")
            else:
                print("\nNo se pudo realizar reparación automática")
        else:
            print("\nOperación finalizada sin cambios")

    print(f"\n=== Fin de validación ===\n")
