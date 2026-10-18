# Changelog

Formato [Keep a Changelog](https://keepachangelog.com/es/1.1.0/), versionado
[SemVer](https://semver.org/lang/es/).

## [2.1.0] - 2026-10-18

Ajustes del asistente de opciones, salidos de usarlo contra providers reales, una
ficha para consultar la configuración de un modelo sin abrir el JSON, el tipo de
servidor (Ollama o vLLM) con autodetección, y `ocm model detect`, que le pregunta al
servidor las opciones de cada modelo en vez de hacer que las escribas a mano. Dos
flujos rematan la idea: registrar un provider y que se rellene solo, y enterarse si un
día cambia el motor de inferencia que hay detrás.

### Añadido

- `ocm cache type [PROVIDER] [TIPO]`: dice, lista o fija si un proveedor es Ollama o
  vLLM. Es un dato **de ocm, no de opencode**: solo cambia qué endpoint se escanea
  (`/api/tags` o `/v1/models`); `opencode.json` sale byte a byte igual con los dos.
  `auto` lo devuelve a la autodetección.
- El escaneo detecta el tipo él solo cuando la caché no lo dice, probando los dos
  endpoints. Y si el tipo guardado no responde, prueba el otro, escanea con él y
  **corrige el tipo avisando**. Si lo fijaste a mano (`--type` o `ocm cache type`) se
  respeta: se escanea con el que funciona, pero solo se avisa.
- Flags `--type ollama|vllm|auto` en `ocm new`, `ocm configure` y `ocm cache update`,
  y un campo más ("Tipo de servidor") en el asistente de `ocm configure`.
- La caché anota de dónde salió cada tipo (`type_source`) y por qué endpoint contestó
  el servidor en el último escaneo (`type_evidence`); `ocm model info` y los listados
  lo enseñan y avisan cuando el tipo no cuadra con la evidencia.
- `ocm model detect [PROVIDER] [MODELO]`: pregunta al servidor qué sabe de cada modelo y
  **propone** las opciones (contexto, modalidades de entrada y salida, razonamiento,
  tool calling). Consulta `GET /props` (llama.cpp), `POST /api/show` (ollama),
  `GET /api/tags` y `GET /v1/models`, el registro de models.dev que opencode ya tiene
  descargado (`~/.cache/opencode/models.json`) y, en último término, el nombre del
  modelo. Cada valor lleva escrita su procedencia, y lo que sólo viene del nombre sale
  marcado como suposición, nunca como dato cierto.
- El asistente cuenta de dónde salió cada cosa: la ficha de `ocm model info` lo pone al
  lado del valor y `ocm model options` lo recuerda antes de preguntar, en amarillo
  cuando fue una pista del nombre y no una prueba del servidor.
- Flags de `ocm model detect`: `--apply` (única forma de escribir, y sólo en la caché;
  rellena huecos), `--force` (cambiar también lo que ya tenías puesto), `--all` (sin
  menú de selección), `--probar` (mandar una imagen 1x1 y leer si la acepta),
  `--no-registro` (fiarse sólo del servidor) y `--json`.
- `ocm new` rellena las opciones **él solo**: terminado el escaneo, consulta al
  servidor y al registro igual que `ocm model detect`, enseña la propuesta completa y
  hace una sola pregunta (*¿Guardar lo detectado en la caché?*). Con un no no se
  escribe nada, y si el servidor no suelta prenda no se gasta ni una pregunta de más.
  `--no-detectar` se salta el paso y deja el asistente campo a campo de siempre.
- `ocm configure` hace lo mismo, pero sólo con los modelos que **aún no tienen
  opciones** (y a los que nunca se les preguntó): no repasa por detrás lo que ya
  dejaste puesto. También se salta con `--no-detectar`.
- Cada escaneo apunta qué motor de inferencia hay detrás del provider (ollama,
  llama.cpp, vLLM, SGLang, LM Studio) y de dónde lo ha sacado; si en el siguiente
  escaneo responde otro, avisa (*«Ojo, el motor parece otro: en la caché constaba
  'ollama' y ahora responde como 'vllm'»*) y `ocm model info` lo recuerda hasta que se
  confirme dos veces. El puerto no distingue —ollama y llama-server comparten el
  11434—, así que se miran `owned_by`, `details.format`, el `model_path` de `/props` y
  la forma de `/api/tags`; si ningún modelo deja pista, no se dice nada. Es un dato de
  la caché: opencode no lo lee.

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
- `ocm new` ya no deja escribir el tipo a mano (era un campo libre y de ahí salían
  valores imposibles): se detecta, y si hay que elegir se elige entre las dos opciones
  válidas. Se aceptan alias al escribirlo (`llama.cpp`, `lmstudio`,
  `openai-compatible` → `vllm`).

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
- Un tipo de proveedor que no fuera literalmente `ollama` o `vllm` (`llama.cpp`,
  `lmstudio`, lo que se escribiera en `ocm new`) hacía que `ocm update` escribiera la URL
  **sin `/v1`**: opencode llamaba entonces a `http://host:11434/chat/completions` en
  vez de a `/v1/chat/completions` y las peticiones fallaban. La regla del `/v1` ya no
  depende del tipo (los dos lo necesitan) y los tipos se normalizan al leerlos.
- Un servidor que contestaba 200 con HTML (un proxy, un puerto equivocado) hacía
  reventar el escaneo con un `ValueError` dentro de `response.json()`; ahora cuenta
  como fallo del escaneo, con su `last_scan_error`, y no borra los modelos de la
  última pasada buena.
- El escaneo respetaba el tipo de la caché a ciegas: si estaba mal dicho, nunca se
  recuperaba. Ahora cae al otro endpoint automáticamente.

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
