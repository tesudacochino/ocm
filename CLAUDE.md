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
│   ├── cache_models.py        # Modelo de datos de la caché (v2) + migración
│   ├── model_fields.py        # Spec declarativa de las opciones de un modelo
│   ├── cli.py                 # Parser argparse + dispatch
│   └── commands/
│       ├── __init__.py
│       ├── utils.py           # get_provider_type, create_backup, build/merge de config
│       ├── provider.py        # new, list, remove
│       ├── model.py           # model list / name / rm / rename
│       ├── options.py         # model options / show: asistente campo a campo
│       ├── configure.py       # ocm configure: reconfigura el provider completo
│       ├── encoded.py         # bloque plural 'providers': detectar, leer, validar, migrar
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

**`cache_models.py`** - Datos de la caché por modelo:
- `models` en la caché es un dict `{model_id: {name, limit, modalities, ...}}`
- `normalize_models()` acepta el formato antiguo (lista de ids) y el nuevo
- `merge_scanned_models()` conserva nombre/opciones al rescannear
- `migrate_cache()` migra en memoria y `ConfigManager.load_cache()` la persiste
- `MANAGED_MODEL_FIELDS` = claves de modelo que ocm escribe en opencode.json
- `_clean_entry()` canonicaliza formas ajenas: `toolcall`→`tool_call`,
  `capabilities.{tools,reasoning,input,output,vision}`, `input`/`output` sueltos
  → `modalities.*` (usa `model_fields.canonical_key`)
- `adopt_model_options()` rellena en la caché lo que solo existe en opencode.json

**`commands/utils.py`** - Escritura de `opencode.json`:
- `build_provider_config()` → config "deseada" desde la caché
- `merge_provider_config(existing, desired, force)` → **no destructivo**: conserva
  claves ajenas y modelos existentes; sin `--force` tampoco sobrescribe las suyas
- `get_provider_type()` con alias (`llama.cpp`, `lmstudio`, ...), `displayify()`

**`model_fields.py`** - Que se puede configurar en un modelo (unica fuente de verdad):
- `FIELDS`: lista de `FieldSpec(key, label, kind, help, presets, advanced, depends_on)`
  en el orden en que los pregunta el asistente
- `kind` ∈ `text|bool|int|multi|choice`; `coerce()` valida y normaliza
  (`128k`→131072, `vision`→`image`, `1,3`→`text,image`)
- numeros: se guardan tal cual (`128000` no pasa a `131072`)
- `get_value()/set_value()` trabajan por ruta (`limit.context`) y limpian el
  contenedor al vaciarse
- `serialize_model()` → solo emite claves con contenido + avisos (p.ej. `limit`
  sin `output`); `describe_model()` → resumen para listados

**`commands/options.py`** - El asistente campo a campo:
- `ask_field()` implementa la interaccion: Intro = KEEP, `-` = quitar,
  `?` = ayuda, `s` = salir (STOP)
- `configure_model_entry()` recorre `visible_fields(advanced)` respetando
  `depends_on` (no pregunta `limit.output` sin `limit.context`)
- `apply_assignments()` es la via no interactiva (`--set clave=valor`)
- `sync_model_config(..., changed_keys)` escribe en `opencode.json` **solo las
  claves que el usuario toco** (`changed_keys`) dentro de las que "posee" el
  asistente (`WIZARD_OWNED_KEYS`); las borra si se quitaron. `options`, `variants`,
  `cost`, `headers` son ajenas y no se tocan nunca. Si el modelo no estaba en el
  config se crea con todo lo de la caché
- `commands/utils.py::refresh_cache_from_config()` adopta en la caché las opciones
  que solo existen en `opencode.json` (lo escrito a mano) la primera vez que se
  lista/configura/actualiza el provider; la caché manda si ya tiene el campo, y
  `name` solo se adopta cuando en la caché es una copia del id
- Cambiar opciones guarda la caché con `save_cache(touch=False)`: no mueve la fecha
  del ultimo escaneo

**`commands/configure.py`** - `ocm configure`, el asistente de provider:
- `cmd_configure()`: estado actual → campos del provider → estilo de API → escaneo
  opcional → repasar modelos → poda opcional
- `ask_optional()` / `mask_secret()`: Intro = KEEP, `-` = None, la api key se
  pinta enmascarada (`sk-1******3456`)
- `apply_provider_fields(manager, provider, cache_info, fields, backup_done)`:
  vuelca `name|baseUrl|apiKey|npm` en caché y en `opencode.json`; deja backup con
  `create_backup()` antes de la primera escritura
- `_config_url()`: misma convencion que `build_provider_config` (la caché guarda
  el host pelado, el config lleva `/v1`)
- `ask_api_style_fields()` es el menu del SDK (`utils.API_STYLES`); lo reutiliza
  `provider.ask_api_style` en `ocm new`
- `_prune_gone_models()`: unicos lugares, junto a `ocm model rm`, donde se borra
  un modelo de `opencode.json`; siempre con confirmacion previa

**`commands/encoded.py`** - El bloque plural `providers` (formato codificado de v2):
- **Comprobado en opencode 2.0.32**: un provider que solo esta en `providers` no se
  registra (no aparece en `opencode models`), aunque lleve `package`/`settings`/
  `canonical`. Por eso ocm escribe solo la forma singular; aqui nos limitamos a
  leer, validar y migrar el plural
- `format_notes(config_data)` → avisos de convivencia (en los dos bloques / solo en
  el plural); lo usan `debug.validate_config`, `provider.cmd_provider_list` y
  `update.cmd_update_global`
- `model_from_encoded()` / `provider_from_encoded()` → traducen al formato singular:
  `package`→`npm`, `settings`→`options`, `headers`→`options.headers`,
  `capabilities.tools`→`tool_call`, `capabilities.input/output`→`modalities`,
  `capabilities.temperature`→`temperature`, `releaseDate`→`release_date`,
  `modelID`→`id`, `variants:[{id,settings}]`→`variants:{id:{...}}`.
  `canonical`, `compatibility`, `body` y `disabled` no cabe en el singular: se
  devuelven en `notes` y se pierden
- `cache_entry_from_encoded()` → entrada de caché equivalente (el `provider_type` se
  infiere del paquete con `PACKAGE_TYPES` si no viene confirmado)
- `cmd_config_to_singular()` → `ocm config to-singular`: reutiliza
  `merge_provider_config` (no pisa nada sin `--force`), crea backup, mete el
  provider en la caché y ofrece quitar el bloque plural (`--drop`/`--keep`)
- Clave del formato singular: `tool_call` (el esquema solo conoce esa forma;
  `toolcall` es de models.dev y opencode la ignora en silencio, sin error)

**`cli.py`** - Parser + dispatch (~130 líneas):
- Define argumentos con argparse
- Dispatch a funciones en `commands/`

**`commands/`** - Lógica de cada comando:
- `provider.py`: `new`, `list`, `remove`
- `model.py`: `model list|name|rm`, `rename`
- `options.py`: `model options|show` (asistente de opciones)
- `configure.py`: `ocm configure` (asistente de provider + poda)
- `encoded.py`: bloque plural `providers` (deteccion, traduccion, `config to-singular`)
- `scan.py`: escaneo de APIs
- `update.py`: actualización de `opencode.json`
- `cache.py`: gestión de caché
- `debug.py`: validación de configuración
- `utils.py`: utilidades compartidas

### Flujo típico

```
user → ocm new        → ConfigManager
                       → ProviderScanner (escanea API, detecta tipo)
                       → Guarda en caché

user → ocm cache update → ProviderScanner (API)
                       → Compara con caché
                       → Muestra: + nuevos, - eliminados
                       → Actualiza caché

user → ocm update     → Lee caché
                       → build_provider_config() (deseado)
                       → merge_provider_config() con lo que hay en opencode.json
                       → Backup + escribir (solo añade, no borra)

user → ocm configure  → refresh_cache_from_config() (adopta lo escrito a mano)
                       → pregunta campo a campo mostrando el valor actual
                       → apply_provider_fields() / sync_model_config(): escribe
                         solo las claves respondidas, con backup
                       → ofrece escaneo y poda de modelos que ya no existen

user → ocm model rm   → unico camino que borra un modelo (caché + opencode.json),
                       con confirmacion y backup

user → ocm config to-singular
                     → provider_from_encoded(): traduce el bloque 'providers'
                     → merge_provider_config() sobre 'provider' (no pisa sin --force)
                     → cache_entry_from_encoded(): deja el provider en la caché
                     → ofrece quitar lo migrado de 'providers' (--drop/--keep)
```

## Comandos principales

```bash
# Principales → opencode.json
ocm new                          # Asistente interactivo
ocm list                         # Listar providers en opencode.json
ocm rm NAME                      # Eliminar provider de opencode.json
ocm update [PROVIDER]            # Escribir caché → opencode.json (no destructivo)
ocm update [PROVIDER] --force    # Idem, sobrescribiendo las claves de ocm
ocm model list [PROVIDER]        # Modelos + nombre visible + dónde están
ocm model name [P] [M]           # Renombrar modelo (caché + opencode.json)
ocm model options [P] [M]        # Asistente: contexto, modalidades, capacidades
ocm model options P M --set limit.context=131072   # Sin preguntar (script)
ocm model show [P] [M]           # Ver el JSON de las opciones de un modelo
ocm model rm [P] [M] [-y]        # UNICO comando que borra un modelo (caché + config)
ocm configure [PROVIDER]         # Asistente: nombre, URL, api key, estilo API, modelos, poda
ocm rename [PROVIDER]            # Renombrar nombre visible del provider

# Caché → provider_cache.json
ocm cache update [PROVIDER]       # Escanear APIs y actualizar caché
ocm cache list                   # Listar providers en caché
ocm cache rm NAME                # Eliminar provider de caché
ocm cache clear                  # Borrar toda la caché

# Configuración avanzada
ocm config validate              # Validar opencode.json (ambos formatos)
ocm config to-singular [P]       # Migrar del bloque plural 'providers' al singular
                                 #   --dry-run | --force | --drop | --keep | -y

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

### provider_cache.json (caché del gestor, formato v2)
```json
{
  "cache_version": 2,
  "cache_timestamp": 1711900800,
  "providers": {
    "ollama-local": {
      "uid": "4f9bc79b",
      "name": "Ollama Local",
      "models": {
        "llama2": {
          "name": "Llama 2",
          "limit": { "context": 131072, "output": 8192 },
          "modalities": { "input": ["text", "image"], "output": ["text"] }
        }
      },
      "last_scan": 1711900800,
      "baseUrl": "http://127.0.0.1:11434",
      "provider_type": "ollama",
      "apiKey": "sk-...",
      "reachable": true
    }
  }
}
```

- `models` en lista (formato v1) se migra solo al abrir la caché.
- `uid`: identidad estable del provider, no depende del nombre.
- `reachable`: `false` cuando el último escaneo no pudo hablar con la URL.
- Lo que hay en `models.<id>` se copia a `provider.<id>.models.<id>` en opencode.json.

### Reglas de escritura en opencode.json

1. `ocm update` **fusiona**, nunca reemplaza: conserva claves que ocm no gestiona
   y no borra providers ni modelos.
2. Sin `--force` no se sobrescribe una clave ya existente; para cambiar nombres se
   usa `ocm rename` / `ocm model name`, que escriben a la vez caché y opencode.json.
3. `npm` solo se fija al crear el provider (no se pisa un SDK elegido a mano).
4. Se crea backup rotativo antes de escribir (`create_backup`, máx. 10).
5. `ocm update` no escribe el campo `model` ni el bloque `providers` (plural, v2).
   Se decide asi por evidencia: en opencode 2.0.32 un provider que solo esta en
   `providers` **no se registra** (no sale en `opencode models`), mientras que la
   forma singular si funciona; escribir el plural seria dejar al usuario con un
   provider inoperativo. El bloque plural se lee, se valida y se migra con
   `ocm config to-singular` (nico sitio, con `--drop`, donde se toca para borrar).
6. Los comandos que son accion explicita del usuario (`ocm configure`, `ocm rename`,
   `ocm model rm`, `ocm config to-singular`) escriben en `opencode.json` en el
   momento, con backup previo y sin tocar claves que no les pertenecen.

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
