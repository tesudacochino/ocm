# OpenCode Config Manager (ocm)

Gestor de providers locales para [opencode](https://opencode.ai). Permite gestionar providers de Ollama y vLLM con sistema de caché.

> La serie 2.x gestiona la configuración de **opencode v2** (probado con opencode
> 2.0.32). El número de versión de ocm es suyo: sube de mayor cuando ocm rompe
> compatibilidad, no cada vez que opencode saca una versión.

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

# Los ejecutables quedan dentro del entorno:
uv run ocm --version
uv run ocm new
```

> Hasta la 1.1.1 el paquete registraba también un comando `opencode`, que tapaba
> al CLI real de opencode. Si vienes de una instalación antigua, recrea el venv
> (`Remove-Item -Recurse .venv` / `rm -rf .venv`) al actualizar.

## Uso rápido

```bash
ocm new                            # Crear/configurar un provider (asistente interactivo)
ocm cache update                   # Escanear modelos disponibles
ocm update                         # Actualizar opencode.json desde la caché
ocm list                           # Ver providers configurados
ocm model list                     # Ver modelos y sus nombres visibles
ocm model name mole qwen3:14b      # Cambiar el nombre que muestra opencode
ocm model options mole qwen3:14b   # Contexto, visión, herramientas, thinking
ocm model info mole qwen3:14b      # Ver esa configuración en claro, sin escribir nada
ocm configure mole                 # Repasar el provider entero (URL, key, nombres, modelos)
ocm model rm mole modelo-viejo     # Quitar un modelo que ya no esta en el servidor
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
| `ocm model info [nombre] [modelo]` | Ver la configuración de un modelo en claro (solo lectura) |
| `ocm model show [nombre] [modelo]` | Ver el JSON tal cual de un modelo |
| `ocm model rm [nombre] [modelo]` | Quitar un modelo que ya no existe en el servidor |
| `ocm configure [nombre]` | Reconfigurar un provider entero (nombre, URL, key, modelos) |
| `ocm rename [nombre]` | Cambiar el nombre visible del provider |

> `ocm model name` y `ocm rename` actualizan **a la vez** la caché y `opencode.json`,
> así el nombre nuevo no se pierde en el siguiente `ocm update`.

### Caché → `provider_cache.json`

| Comando | Descripción |
|---------|-------------|
| `ocm cache update` | Escanear **todos** los providers y actualizar caché |
| `ocm cache update <nombre>` | Escanear un provider específico |
| `ocm cache list` | Listar providers en caché |
| `ocm cache type [nombre] [tipo]` | Ver o fijar si es Ollama o vLLM (solo afecta al escaneo) |
| `ocm cache rm <nombre>` | Eliminar provider de caché |
| `ocm cache clear` | Borrar toda la caché |

### Configuración avanzada

| Comando | Descripción |
|---------|-------------|
| `ocm config validate` | Validar integridad de `opencode.json` (los dos formatos) |
| `ocm config to-singular [nombre]` | Migrar providers del bloque plural `providers` al singular |
| `ocm config to-singular --dry-run` | Ver qué migraría, sin escribir |

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
ocm configure    →  Repasa un provider →  caché + opencode.json  (con backup)
ocm model options → Opciones de modelo →  caché + opencode.json
ocm model rm     →  Quita un modelo    ←  caché + opencode.json
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

# 6. Ajustar opciones de un modelo (contexto, visión, herramientas)
ocm model options mole qwen3:14b

# 7. Cambiar la URL del provider o repasar todo (ofrece escaneo y limpieza)
ocm configure mole

# 8. Quitar un modelo que ya no existe en el servidor
ocm model rm mole modelo-viejo
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
| **SGLang, llama.cpp, LM Studio** | el que sea | `GET /v1/models` |

### Ollama o vLLM: qué hace el tipo

ocm guarda en la caché un tipo, `ollama` o `vllm`, que **solo decide qué endpoint se
escanea**. No llega a opencode: lo que opencode lee (`npm`, `options.baseURL` y los
modelos) sale byte a byte igual con los dos tipos, porque ambos sirven la API de
OpenAI bajo `/v1`.

- El puerto no distingue (Ollama y vLLM conviven en el 11434), así que se mira qué
  responde: si existe `GET /api/tags` es Ollama; si no, `GET /v1/models` y vale como
  vLLM o compatible con OpenAI.
- Si el tipo guardado falla al escanear, ocm prueba el otro endpoint, escanea con él
  y **corrige el tipo en la caché avisando**. Si lo fijaste tú a mano, escanea con el
  que funciona pero lo deja como lo dejaste.
- Se aceptan alias al escribirlo: `llama.cpp`, `lmstudio`, `openai-compatible` → `vllm`.

| Quiero | Comando |
|--------|---------|
| Ver el tipo de todos los providers | `ocm cache type` |
| Ver el de uno y cambiarlo en un menú | `ocm cache type <proveedor>` |
| Fijarlo | `ocm cache type <proveedor> ollama` (o `vllm`) |
| Devolverlo a la autodetección | `ocm cache type <proveedor> auto` |
| Forzar el endpoint de un escaneo | `ocm cache update <proveedor> --type vllm` |
| Ponerlo al crear o reconfigurar | `ocm new` / `ocm configure <p> --type ollama` |

`ocm model info <proveedor> <modelo>` enseña además de dónde salió el tipo (detectado
o fijado a mano) y por qué endpoint contestó el servidor en el último escaneo; si el
tipo no cuadra con esa evidencia, lo avisa.

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
corchetes. Si el campo no está guardado, entre corchetes va lo que opencode
asume, etiquetado como `por defecto`; dar Intro ahí deja la clave **sin
escribir**, no se rellena la caché con valores que opencode aplica de todas formas.

```
Opciones de mole/qwen3:14b
  Intro mantiene, '-' quita, '?' ayuda, 's' sale
  Nombre visible en /models [Qwen 3 14B]:
  Tokens de contexto (entrada) [131072] (ej: 4096 o 128k):
  Tokens maximos de salida [8192] (ej: 4096 o 128k):
  Entradas que acepta [text] (1=text, 2=audio, 3=image, 4=video, 5=pdf o text,image): 1,3
  Salidas que produce [por defecto: text] (1=text, 2=audio, ...):
  Es un modelo de razonamiento (thinking) [si] (y/n): -
  Soporta tool calling [por defecto: no] (y/n): y
```

| Tecla | Efecto |
|-------|--------|
| Intro | mantiene lo que hay (si estaba vacío, lo que opencode asume) |
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

Comandos relacionados: `ocm model info mole qwen3:14b` (la ficha en claro),
`ocm model show mole qwen3:14b` (el JSON tal cual), `ocm model list mole` (tabla con
nombre visible y opciones de todos).

### Consultar sin tocar nada: `ocm model info`

```bash
ocm model info mole qwen3:14b          # la ficha
ocm model info mole qwen3:14b -a       # también las opciones avanzadas vacías
ocm model info mole qwen3:14b --json   # el JSON efectivo, para scripts
```

Enseña de una vez lo que antes estaba repartido entre la caché y el JSON:

```
=== mole/qwen3:14b ===

  Nombre visible                            Qwen 3 14B
  Resumen                                   (ctx=131072, out_max=8192, in=text, out=text, tools)
  En opencode.json                          si  provider.mole.models["qwen3:14b"]
  En la cache                               si

Provider
  URL (cache)                               http://192.168.4.99:11434
  URL (opencode)                            http://192.168.4.99:11434/v1
  API key                                   ****abcd  (en la cache)
  Ultimo escaneo                            2026-10-18 15:04  (ok)

Opciones del modelo
  Tokens de contexto (entrada)              131072 tokens (128k)
  Tokens maximos de salida                  8192 tokens (8k)
  Entradas que acepta                       text
  Salidas que produce                       text  (lo asume opencode)
  Es un modelo de razonamiento (thinking)   si
  Soporta tool calling                      si

Otras claves (el asistente no las toca)
  options                                   {"temperature": 0.2}

Comprobaciones
  OK  la cache y opencode.json coinciden
```

Entre paréntesis marca lo que **no está escrito** y opencode aplica de todas formas,
separa las claves que `ocm` no gestiona (ésas se conservan intactas) y, cuando la
caché y `opencode.json` discrepan, lista las claves y dice la orden concreta para
arreglarlo. Si el modelo vive sólo en el bloque plural `providers` —el que opencode
2.0.x no llega a registrar—, lo avisa y ofrece `ocm config to-singular`.

Es de solo lectura: no adopta opciones en la caché ni escribe backups, así que se
puede consultar con la misma calma que un `cat`.

### Reconfigurar un provider: `ocm configure`

```bash
ocm configure                      # pregunta que provider
ocm configure mole                 # directo a ese provider
ocm configure mole --name "Mole Casa" --url http://192.168.4.99:11434
ocm configure mole --model qwen3:14b --advanced   # salta a las opciones avanzadas de ese modelo
```

Muestra el estado actual y va preguntando campo a campo, con las mismas teclas
que el asistente de opciones (`Intro` mantiene, valor nuevo reemplaza, `-` quita,
`?` ayuda):

```
=== Reconfigurar provider: mole ===

  Nombre visible : Mole
  URL base       : http://127.0.0.1:11434
  API key        : sk-1******3456
  SDK (npm)      : @ai-sdk/openai-compatible
  Tipo detectado : vllm

  Nombre visible del provider [Mole] (el que sale en /models):
  URL base [http://127.0.0.1:11434] (ej: http://192.168.1.5:11434 (sin /v1)):
  API key (Intro mantiene la guardada):
Estilo de API del provider
  1) OpenAI chat completions (vLLM, LM Studio, llama.cpp...) *
  2) OpenAI responses API
```

Despues enseña la tabla de modelos, deja repasar uno (o `todos`) y, si hay
modelos en `opencode.json` que ya no aparecen en el ultimo escaneo, **ofrece
quitarlos** (con `n` se quedan como estaban).

La api key nunca se muestra entera en pantalla: se ve `sk-1******3456`.

| Flag | Para que |
|------|----------|
| `--name` / `--url` / `--api-key` | fijar el campo sin preguntar (para scripts) |
| `--model MODELO` | ir directamente a las opciones de ese modelo |
| `--advanced` | incluir las opciones avanzadas al repasar modelos |
| `--no-api-style` | no preguntar el SDK (`npm`) |
| `--no-rescan` | no ofrecer un escaneo al cambiar URL o api key |
| `--no-prune` | no ofrecer la limpieza de modelos |

A diferencia de `ocm update`, esto escribe en `opencode.json` en el momento (es
una accion explicita tuya) y hace backup antes del primer cambio.

### Quitar un modelo: `ocm model rm`

`ocm update` **nunca** borra modelos, para no perder lo que escribiste a mano.
El unico sitio donde se borra uno es aqui:

```bash
ocm model rm mole modelo-viejo     # pregunta confirmacion
ocm model rm mole modelo-viejo -y  # sin preguntar
```

Lo quita de la caché y de `opencode.json`, crea backup y avisa si era el modelo
por defecto (la clave `"model"` de opencode.json).

### El formato nuevo de opencode v2 (`providers`, en plural)

El esquema de opencode marca `provider` (singular) como *deprecated* y añade
`providers` (plural) con otra forma, la "codificada" (`package`, `settings`,
`capabilities`, `modelID`).

**Comprobado sobre opencode 2.0.32: ese bloque plural no llega a registrar el
provider.** Un provider que solo esté en `providers` no aparece en
`opencode models`, le pongas `package`, `settings`, `env` o `canonical`. La
forma que sí registra providers es la singular, así que **`ocm` escribe siempre
`provider` (singular)** y del bloque plural solo hace lo útil:

- lo **detecta**: `ocm list`, `ocm update` y `ocm config validate` te dicen qué
  providers viven en `providers` y si algún id está duplicado en los dos bloques
  (en ese caso opencode hace caso al singular),
- lo **entiende**: `ocm model list <PROVIDER>` lista también los modelos que solo
  están ahí, marcados como `solo 'providers'`,
- lo **migra** a la forma que sí funciona, con `ocm config to-singular`.

```bash
ocm config to-singular                 # detecta y pregunta por todos los que encuentre
ocm config to-singular local-brain     # uno concreto
ocm config to-singular --dry-run       # ver sin escribir
ocm config to-singular --drop          # además quita del plural lo ya migrado
ocm config to-singular --keep          # y además lo deja también en el plural
ocm config to-singular --force         # sobrescribir claves existentes (por defecto no)
```

La migración traduce `package`→`npm`, `settings`→`options`, `headers`→`options.headers`,
y por modelo `capabilities.tools`→`tool_call`, `capabilities.input/output`→`modalities`,
`capabilities.temperature`→`temperature`, `releaseDate`→`release_date`,
`modelID`→`id` y `variants: [{id,settings}]`→`variants: {id:{...}}`. Crea backup,
mete el provider en la caché (para que `ocm update` lo mantenga) y **no pisa nada
que ya existiera** salvo `--force`. `canonical`, `compatibility`, `body` y
`disabled` no tienen sitio en el formato singular: se avisan y se pierden.

Detalle sobre las capacidades: la clave del formato singular es **`tool_call`**
(así aparece en el esquema oficial; `toolcall` es del catálogo de models.dev y
opencode la ignora en silencio). Ojo, que opencode tampoco rechaza las claves
desconocidas en tiempo de ejecución: si escribes `toolcall` te quedas sin la
capacidad y sin aviso. Por eso `ocm` escribe los nombres del esquema y
`ocm config validate` te caza los que están mal colocados.

La forma codificada, para referencia (esto **no** registra el provider en 2.0.32):

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

`ocm` escribe siempre en `provider` (singular, el formato que de verdad registra
providers). El bloque `providers` que ya exista en tu archivo no lo toca nadie: solo
`ocm config to-singular --drop` lo limpia, y te lo pide antes.

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
