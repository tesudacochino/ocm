# Changelog

Formato [Keep a Changelog](https://keepachangelog.com/es/1.1.0/), versionado
[SemVer](https://semver.org/lang/es/).

## [2.1.0] - 2026-10-18

Ajustes del asistente de opciones, salidos de usarlo contra providers reales, y una
ficha para consultar la configuración de un modelo sin abrir el JSON.

### Añadido

- `ocm model info [PROVIDER] [MODELO]`: ficha en claro de un modelo —nombre visible,
  dónde está (caché, bloque singular o bloque plural), URL, API key mascada, último
  escaneo, opciones efectivas marcando lo que opencode asume, las claves que ocm no
  toca, y en qué difieren caché y `opencode.json`. Es de solo lectura: a diferencia
  de `ocm model show` no adopta opciones ni escribe en ningún fichero. Con
  `--advanced` saca también las opciones avanzadas vacías, y con `--json` vuelca el
  JSON efectivo del modelo.
- Los modelos que sólo viven en el bloque plural `providers` ya no se muestran en
  "sin definir": la ficha enseña lo que dice ese bloque, ya traducido al formato
  singular, y ofrece `ocm config to-singular <PROVIDER>` para registrarlo.

### Cambiado

- `ocm model options` muestra entre corchetes lo que opencode asume cuando un campo
  no está guardado (`[por defecto: text]`, `[por defecto: no]`) y `sin definir` en
  los tamaños de contexto, para que dar Intro sea una decisión informada. Intro
  sigue sin escribir nada: ocm no rellena claves que opencode aplica de todas formas.
- El prompt de las modalidades ya no dice `(1,3 o text,image)`, que no se entendía:
  ahora lista las opciones (`1=text, 2=audio, 3=image, 4=video, 5=pdf o text,image`)
  y con `?` explica cómo escribir varias de golpe.
- Cuando un modelo no tiene ninguna opción guardada, el asistente lo avisa arriba del
  todo, para que no se confunda "no hay nada" con "el valor es ese".

### Corregido

- El resumen en una línea de `ocm model options` y de los listados ponía
  `out~=text` para las modalidades de salida; ahora es `out=text`, y el límite de
  tokens de salida se distingue como `out_max=` (`ctx=131072, out_max=8192,
  in=text,image, out=text, reasoning, tools`).
- Unas modalidades escritas a mano como texto (`"output": "text"`) se deshacían
  letra a letra al resumir el modelo.
- El bloque plural `providers` escrito en lista (`"models": [{"modelID": ...}]`)
  perdía todos sus modelos al detectarlos y al migrarlos con `ocm config
  to-singular`; ahora se indexan por `modelID`/`id` y se traducen igual, avisando
  del apaño.

## [2.0.0] - 2026-10-18

Serie 2.x = configuración de **opencode v2** (esta versión está comprobada contra
opencode 2.0.32). El número mayor no significa que ocm vaya a ir pegado a la
versión de opencode: significa que hay cambios incompatibles con ocm 1.x. Si un
día opencode saca la v3, ya se verá otra mayor.

### Rupturas respecto a 1.1.1

- **Formato de caché v2** en `provider_cache.json`: los modelos pasan de lista a
  objeto con sus opciones, y cada provider gana `uid`. Se migra sola la primera
  vez que ocm la abre, pero **no hay vuelta atrás**: un `ocm` 1.x ya no entiende
  una caché migrada. Si necesitas volver al 1.x, conserva el `provider_cache.json`
  de antes.
- **`ocm update` ya no reemplaza** el bloque del provider, lo fusiona: conserva las
  claves que ocm no gestiona y no borra providers ni modelos. Quien contaba con
  que sobrescribiera los valores escritos a mano ahora necesita `--force`
  (para cambiar nombres están `ocm rename` y `ocm model name`).
- El paquete **ya no instala un ejecutable llamado `opencode`**: tapaba al CLI real
  de opencode cuando ocm se instalaba en el mismo entorno. Las instalaciones con
  `pip`/`uv`/`uv tool` deben recrear el entorno para limpiar el shim viejo; el
  binario `.exe` de PyInstaller no estaba afectado.
- `ocm model options` pierde el alias `configure`, que se confundía con el
  asistente de provider. El asistente de provider es `ocm configure`.
- Las claves que se escriben son las del esquema oficial de opencode: `tool_call`
  (no `toolcall`), `modalities`, `reasoning`, y `limit` en enteros. `128k` y `1m`
  se aceptan al introducirlas y se guardan como 131072 / 1048576.

### Añadido

- `ocm configure [PROVIDER]`: asistente para reconfigurar un provider ya creado
  (nombre visible, `baseURL`, `apiKey` enmascarada, paquete del SDK, repaso de
  modelos y oferta de podar los que ya no existen en el servidor).
- `ocm model options [PROVIDER] [MODELO]`: asistente campo a campo para las
  opciones de un modelo; acepta `--set clave=valor` para usarlo en scripts.
- `ocm model show [PROVIDER] [MODELO]`: ver el JSON de las opciones de un modelo.
- Opciones por modelo: tamaño de contexto (`limit.context`/`limit.input`/
  `limit.output`), modalidades de entrada y salida, razonamiento y llamadas a
  herramientas. Avanzadas: `temperature`, `attachment`, `experimental`, `status`.
- `ocm model list [PROVIDER]`: modelos con nombre visible, opciones y en qué
  bloque están; `ocm model name` y `ocm rename` cambian los nombres visibles
  escribiendo a la vez caché y `opencode.json`.
- `ocm model rm [PROVIDER] [MODELO]` (`-y` para no preguntar): único sitio, junto
  a la poda de `ocm configure`, donde se borra un modelo; con backup y aviso si
  era el modelo por defecto de la clave `model`.
- `ocm config to-singular [PROVIDER]` (alias `to-single` / `migrate`, con
  `--dry-run`, `--force`, `--drop`, `--keep`, `-y`): migrar providers del bloque
  plural `providers` —el formato "codificado" de v2, que en opencode 2.0.32 no
  llega a registrar el provider— al bloque `provider`, que sí lo registra.
- Detección del bloque plural: `ocm list`, `ocm update` y `ocm config validate`
  avisan de qué providers viven en `providers` y de los ids duplicados en los dos
  bloques; `ocm model list` marca los modelos que solo están ahí.
- `reachable` y `last_scan_error` en la caché: un escaneo que falla no borra la
  api key, los nombres ni las opciones de los modelos.
- Backup rotativo de `opencode.json` antes de cada escritura (últimos 10).
- `ocm config validate` entiende los dos formatos del esquema de opencode,
  comprueba tipos (`capabilities`, modalidades, pareja `context`/`output`) y da
  pistas cuando una clave está colocada en el sitio contrario.
- Caché en formato v2 con migración automática desde v1 (listas de modelos,
  `capabilities`, `toolcall`).
- `scripts/set_version.py`: fijar `__commit__`/`__version__` en bytes, sin pasar
  por PowerShell.
- El paquete registra el ejecutable `ocm` además del nombre largo
  `opencode-config-manager`.

### Cambiado

- `npm` solo se fija al crear el provider: no se pisa un SDK elegido a mano.
- `ocm new` pregunta el estilo de API (paquete del SDK) y permite ajustar las
  opciones de cada modelo dentro del propio asistente.
- `install.bat` / `install.sh` despedían con un comando que ya no existía
  (`opencode-config-manager provider --new`); ahora hablan de `ocm`.

### Corregido

- `build.bat` reescribía `_version.py` con PowerShell `Get-Content | Set-Content`,
  que rompía los acentos del fichero (UTF-8 sin BOM) al inyectar el commit.
- `ocm update` copiaba las opciones de la caché sin convertirlas: un
  `limit.context` con `"128k"` acababa literal en `opencode.json` en lugar de
  131072.
- El `.spec` de PyInstaller no listaba los módulos nuevos (`cache_models`,
  `model_fields`, `commands.model`, `commands.options`, `commands.configure`,
  `commands.encoded`): probado con el binario congelado.
- `uv.lock` desactualizado respecto a `pyproject.toml`.

## [1.1.1] y anteriores

Gestión básica de providers locales: `ocm new`, `ocm list`, `ocm rm`,
`ocm update`, `ocm cache update/list/rm/clear` y `ocm config validate`, con la
caché en formato v1 (`models` como lista) y escritura por reemplazo del bloque
del provider. Instalaba, además, un ejecutable `opencode` que chocaba con el CLI
real de opencode.
