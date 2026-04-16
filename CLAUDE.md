# CLAUDE.md

Este repositorio contiene `opencode-config-manager`, una herramienta CLI en Python para gestionar providers locales de modelos para Opencode.

## Propósito del proyecto

Crear un sistema que permite:
- Gestionar providers locales (Ollama, vLLM) de modelos de IA
- Escanear y cachear modelos disponibles de cada provider
- Actualizar el archivo `opencode.json` con modelos detectados

## Arquitectura

### Estructura del repositorio

```
opencodeconfig/
├── pyproject.toml              # Metadatos, dependencias, configuración
├── src/opencode_config_manager/
│   ├── __init__.py            # Exportaciones públicas
│   ├── __main__.py            # Entry point para python -m
│   ├── config.py              # ConfigManager, ConfigUI, Colors
│   ├── api.py                 # ProviderScanner, ScanResult
│   ├── cli.py                 # Parser argparse + dispatch
│   └── commands/
│       ├── __init__.py
│       ├── utils.py           # get_provider_type, create_backup, sanitize_config
│       ├── provider.py        # new, list, remove
│       ├── scan.py            # scan, scan_single_provider
│       ├── update.py          # update provider/global
│       ├── cache.py           # cache show/clear
│       └── debug.py           # debug config, validate_config
├── scripts/
│   ├── ccl                    # Wrapper Linux/macOS
│   └── ccl.bat                # Wrapper Windows
├── opencode-config-manager.spec # PyInstaller config
├── install.sh, install.bat     # Script instalación
├── build.sh, build.bat         # Script compilación
├── README.md                   # Documentación para usuarios
├── DOCUMENTACION_TECNICA.md    # Guía técnica completa
└── CLAUDE.md                   # Esta guía
```

### Módulos principales

**`config.py`** - Clases `ConfigManager`, `ConfigUI`, `Colors`:
- Gestiona `opencode.json` (configuración del usuario)
- Gestiona `provider_cache.json` (caché de modelos escaneados)
- Soporta `--config` y `--home` para paths personalizados
- `migrate_legacy_config()` para migrar formatos antiguos

**`api.py`** - Clase `ProviderScanner` + `ScanResult`:
- `scan_ollama()` → `GET /api/tags` → `ScanResult`
- `scan_vllm()` → `GET /v1/models` → `ScanResult`
- `ScanResult` dataclass con `.success`, `.models`, `.error`

**`cli.py`** - Parser + dispatch (~130 líneas):
- Define argumentos con argparse
- Dispatch a funciones en `commands/`

**`commands/`** - Lógica de cada comando:
- `provider.py`: `new`, `list`, `remove`
- `scan.py`: escaneo de APIs
- `update.py`: actualización de `opencode.json`
- `cache.py`: gestión de caché
- `debug.py`: validación de configuración
- `utils.py`: utilidades compartidas

### Flujo típico

```
user → ocm new   → ConfigManager
                  → ProviderScanner (escanea API, detecta tipo)
                  → Guarda en caché

user → ocm scan  → ProviderScanner (API)
                  → Compara con caché
                  → Muestra: + nuevos, - eliminados
                  → Actualiza caché

user → ocm update → Lee caché
                   → Genera config opencode.ai
                   → Actualiza opencode.json
```

## Comandos principales

```bash
# Gestión de providers
ocm new                          # Asistente interactivo
ocm list                         # Listar providers (alias: ls)
ocm rm NAME                      # Eliminar provider (alias: remove)

# Caché
ocm scan [PROVIDER]              # Escanear y actualizar caché
ocm cache show                   # Ver estado de caché
ocm cache clear                  # Borrar caché

# Actualización de opencode.json
ocm update PROVIDER              # Actualizar provider específico
ocm update                       # Actualizar todos los providers

# Debug
ocm debug config                 # Validar opencode.json

# Via uv
uv run opencode-config-manager --help
```

## Estructura de datos

### opencode.json (configuración opencode.ai)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama",
      "options": {
        "baseURL": "http://localhost:11434/v1"
      },
      "models": {
        "qwen3-coder": {
          "name": "qwen3-coder"
        }
      }
    }
  }
}
```

### provider_cache.json (caché del gestor)
```json
{
  "cache_timestamp": 1711900800,
  "providers": {
    "ollama-local": {
      "models": ["llama2", "mistral"],
      "last_scan": 1711900800,
      "baseUrl": "http://127.0.0.1:11434",
      "provider_type": "ollama"
    }
  }
}
```

## Paths por defecto

- Configuración: `~/.config/opencode/opencode.json`
- Caché: `~/.config/opencode/provider_cache.json`
- Personalizable con `--config` y `--home`

## Providers soportados

1. **Ollama** (default http://127.0.0.1:11434)
   - Endpoint: `GET /api/tags`
   - Respuesta: `{ models: [{ name, ... }] }`

2. **vLLM** (default http://127.0.0.1:8000)
   - Endpoint: `GET /v1/models`
   - Respuesta: `{ data: [{ id, ... }] }`
   - Filtra prefix "data/" automáticamente

## Configuración del entorno

Usamos `uv` para gestión del entorno virtual:

```bash
cd D:/shellrepo/opencodeconfig
uv sync
uv run opencode-config-manager --help
```

## Instalación

```bash
# Via uv
uv sync
uv pip install -e .

# O usar script de instalación
./install.sh       # Linux/macOS
install.bat        # Windows
```

## Compilación

```bash
# Linux/macOS
./build.sh

# Windows
build.bat
```

Esto crea un ejecutable en `dist/ocm.exe`

## Requisitos

- Python 3.10+
- uv (`pip install uv`)
- requests (`uv add requests`)
- Cross-platform: Windows, macOS, Linux
