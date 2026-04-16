# OpenCode Config Manager (ocm)

Gestor de providers locales para [opencode](https://opencode.ai). Permite gestionar providers de Ollama y vLLM con sistema de caché.

## Instalación

### Descargar ejecutable (recomendado)

Descarga el binario desde [Releases](https://github.com/tesudacochino/ocm/releases) y colócalo en tu PATH:

- **Windows:** `ocm.exe`
- **Linux:** `ocm-linux`
- **macOS:** `ocm-mac`

### Desde código fuente

Requiere Python 3.10+ y [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/tesudacochino/ocm.git
cd ocm
uv sync
```

## Uso rápido

```bash
# Ver ayuda y versión
ocm --help
ocm --version

# Crear un nuevo provider (asistente interactivo)
ocm new

# Listar providers configurados
ocm list

# Escanear modelos disponibles
ocm scan

# Actualizar opencode.json con los modelos detectados
ocm update
```

## Comandos

### Gestión de providers

| Comando | Descripción |
|---------|-------------|
| `ocm new` | Asistente interactivo para añadir un provider |
| `ocm list` | Listar providers configurados |
| `ocm remove <nombre>` | Eliminar un provider |

### Escaneo y caché

| Comando | Descripción |
|---------|-------------|
| `ocm scan` | Escanear **todos** los providers |
| `ocm scan <nombre>` | Escanear un provider específico |
| `ocm cache show` | Ver estado de la caché |
| `ocm cache clear` | Borrar la caché |

### Actualizar opencode.json

| Comando | Descripción |
|---------|-------------|
| `ocm update` | Actualizar con **todos** los providers en caché |
| `ocm update <nombre>` | Actualizar solo un provider |

### Debug

| Comando | Descripción |
|---------|-------------|
| `ocm debug config` | Validar integridad de `opencode.json` |

### Opciones globales

| Opción | Descripción |
|--------|-------------|
| `--version`, `-V` | Mostrar versión y commit hash |
| `--config <ruta>` | Ruta a opencode.json (default: `~/.config/opencode/opencode.json`) |
| `--home <ruta>` | Directorio base (default: `~/.config/opencode`) |

## Flujo de trabajo

```
ocm scan  →  Obtiene modelos de la API  →  provider_cache.json
ocm update  →  Lee la caché  →  Escribe opencode.json
```

**Ejemplo completo:**

```bash
# 1. Añadir un provider
ocm new

# 2. Escanear modelos disponibles
ocm scan
# Output: Modelos detectados:
#   - gemma4:e4b
#   - qwen3.5:27b

# 3. Aplicar a opencode.json
ocm update

# 4. Verificar configuración
ocm debug config
```

> **Nota:** `ocm update` usa datos de caché, no escanea en tiempo real. Ejecuta siempre `ocm scan` antes.

## Providers soportados

| Provider | URL por defecto | Endpoint |
|----------|----------------|----------|
| **Ollama** | `http://127.0.0.1:11434` | `GET /api/tags` |
| **vLLM** | `http://127.0.0.1:8000` | `GET /v1/models` |

## Formato de opencode.json

El archivo generado sigue el formato de [opencode.ai](https://opencode.ai):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama",
      "options": {
        "baseURL": "http://127.0.0.1:11434/v1"
      },
      "models": {
        "gemma4:e4b": { "name": "gemma4:e4b" },
        "qwen3.5:27b": { "name": "qwen3.5:27b" }
      }
    }
  }
}
```

<details>
<summary>Ejemplo con múltiples providers</summary>

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama-remote": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama Remote",
      "options": {
        "baseURL": "http://10.0.0.50:11434/v1",
        "apiKey": "ollama"
      },
      "models": {
        "mistral:latest": { "name": "mistral:latest" }
      }
    },
    "ollama-local": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama Local",
      "options": {
        "baseURL": "http://127.0.0.1:11434/v1"
      },
      "models": {
        "qwen3.5:27b": { "name": "qwen3.5:27b" }
      }
    }
  }
}
```

</details>

## Estructura de archivos

```
~/.config/opencode/
├── opencode.json         # Configuración de opencode.ai
└── provider_cache.json   # Caché de modelos escaneados
```

## Compilación

```bash
# Windows
build.bat

# Linux / macOS
./build.sh
```

El ejecutable se genera en `dist/ocm` (o `dist/ocm.exe` en Windows).

## Licencia

MIT
