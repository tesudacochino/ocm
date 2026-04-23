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
ocm new                          # Crear nuevo provider
ocm cache update                   # Escanear modelos disponibles
ocm update                       # Actualizar opencode.json
ocm list                         # Ver providers configurados
```

## Comandos

### Principales → `opencode.json`

| Comando | Descripción |
|---------|-------------|
| `ocm new` | Asistente interactivo para añadir un provider |
| `ocm list` | Listar providers en `opencode.json` |
| `ocm rm <nombre>` | Eliminar provider de `opencode.json` |
| `ocm update [nombre]` | Actualizar `opencode.json` con datos de caché |

### Caché → `provider_cache.json`

| Comando | Descripción |
|---------|-------------|
| `ocm cache update` | Escanear **todos** los providers y actualizar caché |
| `ocm cache update <nombre>` | Escanear un provider específico |
| `ocm cache list` | Listar providers en caché |
| `ocm cache rm <nombre>` | Eliminar provider de caché |
| `ocm cache clear` | Borrar toda la caché |

### Configuración avanzada

| Comando | Descripción |
|---------|-------------|
| `ocm config validate` | Validar integridad de `opencode.json` |

### Opciones globales

| Opción | Descripción |
|--------|-------------|
| `--version`, `-V` | Mostrar versión y commit hash |
| `--config <ruta>` | Ruta a opencode.json (default: `~/.config/opencode/opencode.json`) |
| `--home <ruta>` | Directorio base (default: `~/.config/opencode`) |

## Flujo de trabajo

```
ocm new         →  Crea provider       →  provider_cache.json
ocm cache update →  Escanea APIs       →  provider_cache.json
ocm update      →  Lee caché           →  opencode.json
ocm list        →  Muestra config      ←  opencode.json
```

**Ejemplo completo:**

```bash
# 1. Añadir un provider
ocm new

# 2. Escanear modelos disponibles
ocm cache update
# Output: Modelos detectados:
#   - gemma4:e4b
#   - qwen3.5:27b

# 3. Aplicar a opencode.json
ocm update

# 4. Verificar qué quedó configurado
ocm list

# 5. Comparar con la caché (opcional)
ocm cache list
```

> **Nota:** `ocm update` usa datos de caché, no escanea en tiempo real. Ejecuta siempre `ocm cache update` antes.

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
├── opencode.json         # Configuración de opencode.ai (ocm list/rm/update)
└── provider_cache.json   # Caché de modelos escaneados (ocm cache ...)
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
