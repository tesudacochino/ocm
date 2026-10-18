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
ocm new                            # Crear/configurar un provider (asistente interactivo)
ocm cache update                   # Escanear modelos disponibles
ocm update                         # Actualizar opencode.json desde la caché
ocm list                           # Ver providers configurados
ocm model list                     # Ver modelos y sus nombres visibles
ocm model name mole qwen3:14b      # Cambiar el nombre que muestra opencode
ocm model options mole qwen3:14b   # Contexto, visión, herramientas, thinking
ocm rename mole                    # Cambiar el nombre visible del provider
```

## Comandos

### Principales → `opencode.json`

| Comando | Descripción |
|---------|-------------|
| `ocm new` | Asistente interactivo para añadir o reconfigurar un provider |
| `ocm list` | Listar providers en `opencode.json` |
| `ocm rm <nombre>` | Eliminar provider de `opencode.json` |
| `ocm update [nombre] [--force]` | Actualizar `opencode.json` con datos de caché |
| `ocm model list [nombre]` | Listar modelos de un provider con su nombre visible |
| `ocm model name [nombre] [modelo]` | Cambiar el nombre visible de un modelo |
| `ocm model options [nombre] [modelo]` | Configurar contexto, modalidades y capacidades de un modelo |
| `ocm model show [nombre] [modelo]` | Ver en detalle las opciones de un modelo |
| `ocm rename [nombre]` | Cambiar el nombre visible del provider |

> `ocm model name` y `ocm rename` actualizan **a la vez** la caché y `opencode.json`,
> así el nombre nuevo no se pierde en el siguiente `ocm update`.

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
ocm new          →  Asistente         →  provider_cache.json  (+ opencode.json si acceptas)
ocm cache update →  Escanea APIs      →  provider_cache.json
ocm update       →  Lee caché         →  opencode.json  (solo añade, no pisa)
ocm list         →  Muestra config    ←  opencode.json
```

**Ejemplo completo:**

```bash
# 1. Añadir un provider (pregunta nombre visible del provider y de los modelos)
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

### `ocm update` no destruye tu configuración

- Combina la configuración de la caché con la que ya hay en `opencode.json`: **añade** providers y modelos nuevos y **respeta** las claves que ocm no gestiona (`npm` propio, `env`, `whitelist`, `blacklist`, `options.headers`, opciones escritas a mano en un modelo, etc).
- **Nunca borra** providers ni modelos, ni toca otras claves del archivo (`model`, `agent`, `mcp`, ...) ni el bloque `providers` (el formato nuevo de opencode v2).
- Si quieres que ocm reescriba las claves que sí gestiona: `ocm update <provider> --force`.
- Para renombrar sin pelearse con el merge está `ocm rename` y `ocm model name`, que escriben a la vez en caché y en `opencode.json`.
- Antes de cada escritura se crea un backup rotativo (`opencode.json.bak.<timestamp>`, últimos 10).

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

### Opciones de un modelo

Dentro de `provider.<id>.models.<id>` opencode acepta, entre otras, estas claves
([esquema oficial](https://opencode.ai/config.json)):

```json
{
  "qwen3.5:27b": {
    "name": "Qwen 3.5 27B",
    "limit": { "context": 131072, "output": 16384 },
    "modalities": { "input": ["text", "image"], "output": ["text"] },
    "reasoning": true,
    "tool_call": true,
    "temperature": true,
    "options": { "temperature": 0.2 },
    "variants": [{ "id": "high", "settings": { "reasoningEffort": "high" } }]
  }
}
```

| Clave | Para qué sirve |
|-------|----------------|
| `name` | **El nombre que se ve en el selector `/models`** de opencode |
| `limit.context` / `limit.output` | Tokens de contexto (entrada) y de salida. Conviene ponerlos en locales (Ollama/vLLM), opencode no los puede adivinar |
| `modalities.input` / `.output` | Qué acepta/produce el modelo: `text`, `audio`, `image`, `video`, `pdf` (vision = `image` en `input`) |
| `reasoning` / `tool_call` / `temperature` / `attachment` | Capacidades del modelo |
| `options` | Parámetros que se pasan al proveedor (`reasoningEffort`, `thinking`, ...) |
| `variants` | Configuraciones alternativas del mismo modelo (los "niveles de thinking") |
| `cost` | Precios, para las métricas de uso |

`ocm` escribe `name` a partir del nombre visible que guardas en la caché
(`ocm model name`). Las demás opciones que pongas a mano en `opencode.json` se
conservan: `ocm update` no las pisa ni las borra.

### Configurar las opciones de un modelo

```bash
ocm model options                      # pregunta provider y modelo
ocm model options mole qwen3:14b       # directo al modelo
ocm model options mole --all           # recorre todos los modelos
ocm model options mole --all --advanced   # incluyendo las avanzadas
ocm model options mole qwen3:14b --set limit.context=131072 \
    --set modalities.input=text,image --set tool_call=y    # sin preguntar (script)
```

El asistente va preguntando campo a campo y muestra el valor actual entre
corchetes:

```
Opciones de mole/qwen3:14b
  Intro mantiene, '-' quita, '?' ayuda, 's' sale
  Nombre visible en /models [Qwen 3 14B]:
  Tokens de contexto (entrada) [131072] (ej: 4096 o 128k):
  Tokens maximos de salida [8192] (ej: 4096 o 128k):
  Entradas que acepta [text] (1,3 o text,image): 1,3
  Es un modelo de razonamiento (thinking) [si] (y/n): -
  Soporta tool calling [si] (y/n):
```

| Tecla | Efecto |
|-------|--------|
| Intro | mantiene lo que hay |
| un valor nuevo | lo reemplaza (se valida: `128k` → 131072, `vision` → `image`, `1,3` → `text,image`) |
| `-` | quita la opción |
| `?` | explica para qué sirve el campo y qué valores son habituales |
| `s` | sale del asistente (lo ya cambiado se guarda) |

Los cambios se escriben a la vez en la caché y en `opencode.json`, así no se
pierden al siguiente `ocm update`. Un `4096` se guarda tal cual (no se redondea a
potencias de 2): `128000` y `131072` son contextos distintos y válidos.

Si ya tenías opciones escritas a mano en `opencode.json`, `ocm` las adopta a la
caché la primera vez que listes o configures ese provider: verás su valor real en
el asistente y no se pierden. Al guardar solo reescribe las claves que has tocado
(en las que el asistente manda); las ajenas como `options`, `variants` o `cost`
nunca se tocan.

Comandos relacionados: `ocm model show mole qwen3:14b` (ver el JSON de un modelo),
`ocm model list mole` (tabla con nombre visible y opciones de todos).

### El formato nuevo de opencode v2 (`providers`, en plural)

El esquema de opencode marca `provider` (singular) como *deprecated* aunque sigue
funcionando, y añade `providers` (plural) con otra forma:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "providers": {
    "local-brain": {
      "name": "Local Brain",
      "package": "@ai-sdk/openai-compatible",
      "settings": { "baseURL": "http://127.0.0.1:8080/v1", "apiKey": "clave" },
      "models": {
        "m": {
          "name": "Mi modelo",
          "limit": { "context": 131072, "output": 16384 },
          "capabilities": { "input": ["text", "image"], "output": ["text"], "reasoning": { "supported": true } }
        }
      }
    }
  }
}
```

Errores frecuentes al escribirlo a mano (los detecta `ocm config validate`):

| Escribiste | Correcto |
|------------|----------|
| `"baseUrl"` / `"apiKey"` a nivel de provider | dentro de `options` (singular) o `settings` (plural) |
| `"api": "openai-completions"` | `"npm": "@ai-sdk/openai-compatible"` (o `"package"` en plural) |
| `"models": [{ "id": "m", ... }]` | `"models": { "m": { ... } }`, un objeto por modelo |
| `"input": ["text", "image"]` en el modelo | `"modalities": { "input": [...] }` (o `"capabilities"` en plural) |
| `"thinkingLevelMap": {...}` | no existe; usa `"variants"` con `"settings"` |

`ocm` escribe siempre en `provider` (singular, el formato documentado) y **no toca**
un bloque `providers` que ya exista en tu archivo.

## Estructura de archivos

```
~/.config/opencode/
├── opencode.json         # Configuración de opencode.ai (ocm list/rm/update)
├── opencode.json.bak.*   # Backups rotativos (últimos 10)
└── provider_cache.json   # Caché de ocm: url, tipo, apiKey, nombre y opciones por modelo
```

Formato de `provider_cache.json` (v2; las cachés antiguas con `models` en lista se
migran solas la primera vez que ocm las abre):

```json
{
  "cache_version": 2,
  "cache_timestamp": 1711900800,
  "providers": {
    "ollama-local": {
      "uid": "4f9bc79b",
      "name": "Ollama Local",
      "provider_type": "ollama",
      "baseUrl": "http://127.0.0.1:11434",
      "apiKey": "sk-...",
      "reachable": true,
      "last_scan": 1711900800,
      "models": {
        "qwen3.5:27b": {
          "name": "Qwen 3.5 27B",
          "limit": { "context": 131072, "output": 16384 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
        }
      }
    }
  }
}
```

| Campo | Para qué sirve |
|-------|----------------|
| `uid` | Identificador estable del provider (sobrevive a renombres y borrados) |
| `name` | Nombre visible que ocm escribe en `provider.<id>.name` |
| `reachable` | `false` si el último escaneo no pudo contactar con la URL |
| `models.<id>` | Opciones del modelo; se copian tal cual a `opencode.json` |

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
