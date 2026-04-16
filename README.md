# opencode-config-manager

Gestor de providers locales para opencode. Permite gestionar providers de Ollama y vLLM con sistema de caché.

## Instalación

Requiere Python 3.10+ y `uv` para gestión del entorno:

```bash
# Ir al repositorio
cd D:/shellrepo/opencodeconfig

# Instalar dependencias y crear entorno virtual
uv sync
```

O usar el script de instalación:
```bash
./install.sh       # Linux/macOS
install.bat        # Windows
```

## Uso rápido

### Ver ayuda
```bash
uv run opencode-config-manager --help
```

### Crear un nuevo provider
```bash
uv run opencode-config-manager new
```

Interactúa con el asistente para configurar un nuevo provider local.

### Listar providers
```bash
uv run opencode-config-manager list
```

### Escanear modelos (actualiza CACHÉ)
```bash
# Escanear un provider específico
uv run opencode-config-manager scan ollama-local

# Escanear todos los providers
uv run opencode-config-manager scan
```

El escaneo compara con la caché anterior y muestra cambios:
- Modelos nuevos: `+ llama3, + mistral`
- Modelos eliminados: `- llama2`

**Nota:** `scan` actualiza `provider_cache.json`, NO `opencode.json`.

### Ver estado de caché
```bash
# Ver todo
uv run opencode-config-manager cache show

# Ver un provider específico
uv run opencode-config-manager cache show ollama-local
```

### Actualizar opencode.json (CONFIGURACIÓN)

**IMPORTANTE:** Los comandos `update` usan la caché existente, NO escanean en tiempo real.

**Flujo recomendado:**
1. Primero escanea para obtener datos frescos: `ocm scan ollama-local`
2. Luego actualiza opencode.json con **todos** los providers: `ocm update`
   - O actualiza un provider específico: `ocm update ollama-local`

```bash
# Actualizar todos los providers en caché
uv run opencode-config-manager update

# Actualizar opencode.json con caché de un provider específico
uv run opencode-config-manager update ollama-local
```

**Diferencia entre `scan` y `update`:**

| Comando | Actualiza | Uso |
|---------|-----------|-----|
| `scan ollama-local` | `provider_cache.json` | Obtener datos frescos de la API |
| `update` | `opencode.json` | Actualiza **todos** los providers en caché |
| `update [NAME]` | `opencode.json` | Actualiza solo el provider específico |

### Gestionar caché
```bash
# Borrar caché
uv run opencode-config-manager cache clear
```

## Comandos completos

### Gestión de providers
| Comando | Descripción |
|---------|------------|
| `ocm new` | Asistente interactivo para crear nuevo provider |
| `ocm list` (alias `ls`) | Listar todos los providers en caché |
| `ocm remove NAME` (alias `rm`) | Eliminar un provider existente |

### Escaneo y caché
| Comando | Descripción |
|---------|------------|
| `ocm scan [NAME]` | **Escanear** API y actualizar caché de modelos |
| `ocm cache show` | Mostrar estado de la caché |
| `ocm cache clear` | Borrar toda la caché |

### Actualización de opencode.json
| Comando | Descripción |
|---------|------------|
| `ocm update [NAME]` | Actualizar `opencode.json` con caché de provider |
| `ocm update` | Actualizar con todos los providers de caché |

### Debug
| Comando | Descripción |
|---------|------------|
| `ocm debug config` | Validar integridad de `opencode.json` |

**Nota:** `update` usa datos de caché, no escanea en tiempo real.

## Argumentos globales

| Argumento | Descripción |
|-----------|-------------|
| `--config PATH` | Ruta a opencode.json (default: ~/.config/opencode/opencode.json) |
| `--home PATH` | Directorio base para configs (default: ~/.config/opencode) |

### Ejemplos
```bash
# Usar opencode.json en carpeta actual
uv run opencode-config-manager update --config ./opencode.json

# Usar directorio personalizado
uv run opencode-config-manager --home /custom/path new
```

## Estructura de archivos

Por defecto:
```
~/.config/opencode/
├── opencode.json       # Configuración principal
└── provider_cache.json # Caché de modelos escaneados
```

## Formato del JSON de configuración (opencode.ai)

El archivo `opencode.json` generado sigue el formato de opencode.ai:

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

**Formato con múltiples providers:**
```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama-remote": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama Remote",
      "options": {
        "baseURL": "http://remote-server.example.com:11434/v1",
        "apiKey": "ollama"
      },
      "models": {
        "mistral:latest": {
          "name": "mistral:latest"
        }
      }
    },
    "ollama-local": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama Local",
      "options": {
        "baseURL": "http://192.168.4.120:11434/v1"
      },
      "models": {
        "qwen3.5:27b": {
          "name": "qwen3.5:27b"
        }
      }
    }
  }
}
```

**Campos principales:**
- `$schema`: URL del esquema de validación `https://opencode.ai/config.json`
- `provider.<name>`: Nombre del provider (ej: `ollama`, `ollama-remote`)
  - `npm`: Paquete NPM para conexión (ej: `@ai-sdk/openai-compatible`)
  - `name`: Nombre descriptivo del provider
  - `options.baseURL`: URL del endpoint API
  - `options.apiKey`: API key opcional (se configura al crear el provider)
  - `models.<model-id>`: Modelo disponible
    - `name`: ID del modelo

## Providers soportados

1. **Ollama** (default http://127.0.0.1:11434)
   - Endpoint: `GET /api/tags`
   - Ejemplo de respuesta: `{ models: [{ name: "llama2", ... }] }`

2. **vLLM** (default http://127.0.0.1:8000)
   - Endpoint: `GET /v1/models`
   - Ejemplo de respuesta: `{ data: [{ id: "llama2", ... }] }`
   - Filtra automáticamente prefix "data/"

## Ejemplo completo

```bash
# 1. Crear un nuevo provider (asistente interactivo)
uv run opencode-config-manager new

# 2. Listar providers en caché
uv run opencode-config-manager list

# 3. Escanear modelos y ver cambios
uv run opencode-config-manager scan ollama-local
# Output: + llama3, + mistral \n - llama2

# 4. Ver resumen de caché
uv run opencode-config-manager cache show

# 5. Actualizar opencode.json con datos de caché
uv run opencode-config-manager update ollama-local

# 6. Verificar opencode.json
uv run opencode-config-manager debug config
```

## Flujo recomendado

1. **Escanear** (`scan`) → Obtiene datos frescos de la API
2. **Actualizar** (`update`) → Aplica datos de caché a opencode.json

```bash
# Paso 1: Escanear para obtener datos frescos
ocm scan ollama-local

# Paso 2: Verificar cambios
ocm list

# Paso 3: Actualizar opencode.json
ocm update ollama-local
```

## Compilación

Crear ejecutable standalone:

```bash
# Linux/macOS
./build.sh

# Windows
build.bat
```

El ejecutable resultante estará en `dist/ocm.exe`

## Requisitos

- Python 3.10+
- uv (`pip install uv`)
- requests (`uv add requests`)
- Cross-platform: Windows, macOS, Linux

## Comandos `scan` vs `update`

**Esta es la diferencia más importante:**

| Comando | ¿Qué hace? | ¿Actualiza qué archivo? |
|---------|------------|----------------------|
| `ocm scan [NAME]` | Llama a la API Ollama/vLLM | `provider_cache.json` |
| `ocm update [NAME]` | Aplica datos de caché | `opencode.json` |

**Flujo correcto:**
1. `ocm scan ollama-local` → Escanea API, actualiza caché
2. `ocm update ollama-local` → Usa caché para actualizar opencode.json

**Advertencia:** `update` NO escanea en tiempo real, usa datos de caché.

