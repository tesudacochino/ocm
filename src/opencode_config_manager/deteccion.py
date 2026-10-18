"""
Autodeteccion de las opciones de un modelo (vision, tool calling, contexto...).

ocm no inventa nada aqui: cada valor sale de algo que dice explicitamente el
servidor o el registro que opencode ya tiene en disco. Aun asi el resultado es una
PROPUESTA: se guarda aparte, con su procedencia, y el usuario decide si aplicarla.

Fuentes, de mas a menos confianza:

  1. el servidor mismo
     * GET /props ......... llama.cpp (llama-server): `modalities.vision/video/audio`
                            y `chat_template_caps.supports_tools`
     * GET /v1/models ..... `max_model_len` (contexto), `root` (el repo de HuggingFace),
                            `owned_by` (quien es el servidor) y a veces `capabilities`
     * GET /api/tags ...... ollama: `capabilities` y `details`
     * POST /api/show ..... ollama: `capability` y `model_info`
  2. ~/.cache/opencode/models.json, el registro de models.dev que usa opencode
  3. los apellidos del nombre (`-vl`, `llava`, `thinking`, ...) -> esto es una
     **suposicion** y se marca como tal para que la ficha y el asistente lo recuerden

Las claves que produce son las mismas del asistente (`limit.context`,
`modalities.input`, `tool_call`, ...), asi que se aplican con `set_value` sin
traducir nada.

El video no se supone nunca: casi ningun modelo local lo acepta de verdad, y
escribirlo sin evidencia hace que opencode mande frames a un modelo que no los ve.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field

from .api import ProviderScanner
from .model_fields import MODALITIES, get_value

# Donde vive el registro de models.dev que opencode mantiene descargado
RUTA_REGISTRO = os.path.expanduser("~/.cache/opencode/models.json")

# Claves de la entrada de provider que ocm usa para sí: son de la cache, no van a opencode.json
CLAVE_FUENTES = "opciones_fuente"
CLAVE_DETECTADO = "opciones_detectado_en"

# Que motor de inferencia parece ser el servidor, y cuando se entero ocm
CLAVE_MOTOR = "servidor"
CLAVE_MOTOR_EVIDENCIA = "servidor_evidencia"
CLAVE_MOTOR_DESDE = "servidor_desde"
CLAVE_MOTOR_ANTERIOR = "servidor_anterior"

# Ningun servidor dice la salida maxima; si solo hay contexto se propone esta como tope
SALIDA_MAXIMA_SUPUESTA = 32768

# Lo que se trae del registro, y solo eso: el nombre visible, el estado y lo
# experimental son decisiones del usuario, no datos del servidor
DE_REGISTRO = (
    "limit.context",
    "limit.output",
    "modalities.input",
    "modalities.output",
    "reasoning",
    "tool_call",
    "temperature",
    "attachment",
)

# Las unicas claves que se pueden sumar entre fuentes del servidor
MODALITY_KEYS = ("modalities.input", "modalities.output")

MARCAS_VISION = ("vision", "visual", "multimodal", "image", "mmproj")
MARCAS_AUDIO = ("audio", "voice", "speech", "omni", "asr")
MARCAS_VIDEO = ("video",)
MARCAS_TOOLS = ("tools", "tool", "tool_call", "function_calling", "functions")
MARCAS_REASONING = ("reasoning", "thinking", "think")

# Ultimo recurso: el nombre del modelo. Son pistas, no pruebas
MARCAS_VISION_NOMBRE = (
    "-vl", "vl-", "_vl", "vision", "llava", "pixtral", "minicpm", "internvl",
    "nvila", "molmo", "gemma3", "gemma-3", "paligemma", "fuyu", "janus",
    "-4v", "multimodal", "visual", "ocr",
)
MARCAS_AUDIO_NOMBRE = ("-audio", "audio-", "omni", "sensevoice", "voice", "tts-")
MARCAS_TOOLS_NOMBRE = ("-tool", "tool-", "toolformer", "hermes", "function-calling")
MARCAS_REASONING_NOMBRE = ("thinking", "reason", "-r1", "r1-", "qwq", "deepseek-r",
                           "sidetable", "riotrs")

# Lo que tiene que decir un servidor que soporta imagenes, en sus palabras
_PALABRAS_NO_VISION = ("does not support", "not support image", "unsupported",
                       "does not support image", "no image", "not multimodal",
                       "not support multimodal")

# 1x1 blanco en PNG: lo minimo que se le puede ense
# ar a un modelo, para la prueba de vision
PIXEL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAh"
    "KmMIQAAAABJRU5ErkJggg=="
)


@dataclass
class Deteccion:
    """Lo que se averiguo de un modelo, y de donde salio cada cosa."""

    valores: dict = field(default_factory=dict)
    fuentes: dict = field(default_factory=dict)
    suposiciones: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    servidor: str = None

    def ofrecer(self, clave, valor, fuente, suposicion=False):
        """Anotar un valor si nadie lo puso antes (gana la fuente mas fiable).

        Las modalidades hacen excepcion: si dos endpoints del servidor dicen cosas
        distintas ('multimodal' por un lado, vision+video por otro) se suman, porque
        cada uno conoce una parte.
        """
        if valor is None or valor == [] or valor == {} or valor == "":
            return
        if clave in self.valores:
            if clave in MODALITY_KEYS and not suposicion and not self.es_suposicion(clave):
                actual = self.valores[clave]
                if isinstance(actual, list) and isinstance(valor, list):
                    unidas = [m for m in MODALITIES if m in set(actual) | set(valor)]
                    if unidas and unidas != actual:
                        self.valores[clave] = unidas
                        self.fuentes[clave] = f"{self.fuentes[clave]} + {fuente}"
            return
        self.valores[clave] = valor
        self.fuentes[clave] = fuente
        if suposicion and clave not in self.suposiciones:
            self.suposiciones.append(clave)

    def es_suposicion(self, clave) -> bool:
        return clave in self.suposiciones


class Explorador:
    """Consulta los endpoints de metadatos del servidor, una sola vez cada uno."""

    def __init__(self, base_url, api_key=None):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self._get = {}
        self._show = {}
        self.fallos = []

    def json(self, endpoint):
        """GET de un endpoint de metadatos; None si no responde o no es JSON."""
        if endpoint not in self._get:
            datos, error = ProviderScanner._get_json(self.base_url, endpoint, self.api_key)
            if error:
                self.fallos.append(f"{endpoint}: {error}")
                datos = None
            self._get[endpoint] = datos if isinstance(datos, dict) else None
        return self._get[endpoint]

    def show(self, model_id):
        """POST /api/show de ollama, probando las dos formas del cuerpo."""
        if model_id in self._show:
            return self._show[model_id]
        datos = None
        for cuerpo in ({"name": model_id}, {"model": model_id}):
            datos, error = ProviderScanner._post_json(self.base_url, "/api/show", cuerpo,
                                                      self.api_key)
            if datos and isinstance(datos, dict):
                break
        if not isinstance(datos, dict):
            self.fallos.append("/api/show: no responde")
            datos = None
        self._show[model_id] = datos
        return datos


# --------------------------------------------------------------------- servidor --
# Los motores que sabemos distinguir, por orden de especificidad, y las palabras con
# las que cada uno se delata en los JSON que sirve
MARCAS_MOTOR = (
    ("sglang", ("sglang",)),
    ("vllm", ("vllm",)),
    ("lmstudio", ("lmstudio", "lm studio")),
    ("llama.cpp", ("llama.cpp", "llama-server", "llamacpp")),
    # 'quantization_level' y compania son la forma de /api/tags: solo ollama la usa
    ("ollama", ("quantization_level", "size_parameter", "model_file")),
)


def _campos_motor(entrada, props) -> tuple:
    """Los sitios donde un servidor suele escribir en que se ejecuta."""
    return (("owned_by", (entrada or {}).get("owned_by")),
            ("details", (entrada or {}).get("details")),
            ("root", (entrada or {}).get("root")),
            ("parent", (entrada or {}).get("parent")),
            ("model_path", (props or {}).get("model_path")))


def _marca_motor(entrada, props) -> tuple:
    """(motor, pista que lo delata), o (None, None) si el servidor no suelta prenda."""
    campos = _campos_motor(entrada, props)
    for motor, marcas in MARCAS_MOTOR:
        for marca in marcas:
            for nombre, valor in campos:
                if valor and marca in str(valor).lower():
                    return motor, f"{nombre} contiene '{marca}'"
    if props is not None and "modalities" in props:
        # 'modalities' en /props solo lo tiene llama-server
        return "llama.cpp", "GET /props (modalities)"
    return None, None


def motor_de(entradas, props=None) -> tuple:
    """De que motor va el provider, con lo que los endpoints ya contestaron.

    Se mira cada modelo y se hace mayoría: un servidor que lista doce modelos 'vllm'
    y uno raro es vllm. Devuelve (motor, evidencia), o (None, None) si ningun modelo
    deja pista (no se inventa: mejor no decir nada que decir 'ollama' sin saberlo).
    """
    votos = {}
    for model_id, entrada in (entradas or {}).items():
        motor, evidencia = _marca_motor(entrada, props)
        if motor:
            votos.setdefault(motor, []).append((model_id, evidencia))
    if not votos:
        return None, None
    motor = max(sorted(votos), key=lambda m: len(votos[m]))
    return motor, votos[motor][0][1]


def _lista_capability(valor) -> list:
    """Las capacidades, vengan como lista o como dict ({'vision': true})."""
    if isinstance(valor, dict):
        return [clave for clave, activo in valor.items() if activo]
    if isinstance(valor, (list, tuple)):
        return [str(item) for item in valor]
    return []


def _desde_capabilities(capacidades, fuente, d, textos):
    """Traducir una lista de capacidades ('completion','tools','vision'...) a campos."""
    texto = " ".join(c.lower() for c in capacidades)
    if not texto:
        return
    if any(marca in texto for marca in MARCAS_VISION):
        d.ofrecer("modalities.input", _con("image"), fuente)
        d.ofrecer("modalities.output", ["text"], fuente)
    if any(marca in texto for marca in MARCAS_VIDEO):
        d.ofrecer("modalities.input", _con("image", "video"), fuente)
    if any(marca in texto for marca in MARCAS_AUDIO):
        d.ofrecer("modalities.input", _con("audio"), fuente)
    if any(marca in texto for marca in MARCAS_TOOLS):
        d.ofrecer("tool_call", True, fuente)
    if any(marca in texto for marca in MARCAS_REASONING):
        d.ofrecer("reasoning", True, fuente)
    textos.append(texto)


def _con(*extras, base=None):
    """['text'] + extras, sin repetir y en el orden de las modalidades."""
    actuales = list(base or ["text"]) + [item for item in extras if item not in ("text",)]
    return [m for m in MODALITIES if m in actuales] or ["text"]


# ------------------------------------------------------------------- por fuente --
def _desde_entrada(entrada, d, fuente, textos):
    """Lo que el servidor ya dijo en la lista de modelos (/v1/models o /api/tags)."""
    if not isinstance(entrada, dict):
        return

    for clave in ("max_model_len", "context_length", "n_ctx", "max_context"):
        valor = entrada.get(clave)
        if isinstance(valor, int) and valor > 0:
            d.ofrecer("limit.context", valor, f"{fuente} ({clave})")
            break

    _desde_capabilities(
        _lista_capability(entrada.get("capabilities") or entrada.get("capability")),
        f"{fuente} (capabilities)", d, textos)

    details = entrada.get("details")
    if isinstance(details, dict):
        _desde_capabilities(_lista_capability(details.get("capability")), f"{fuente} (details)",
                            d, textos)
        for clave in ("format", "family"):
            if details.get(clave):
                textos.append(str(details[clave]))
        familias = details.get("families")
        if isinstance(familias, (list, tuple)):
            textos.extend(str(item) for item in familias)

    for clave in ("root", "parent", "model_path"):
        if entrada.get(clave):
            textos.append(_nombre_del_repo(str(entrada[clave])))


def _desde_props(props, d, textos):
    """llama.cpp (llama-server): `/props` dice las modalidades del modelo."""
    if not isinstance(props, dict):
        return

    mod = props.get("modalities")
    if isinstance(mod, dict):
        entradas = ["text"]
        for clave, modalidad in (("vision", "image"), ("audio", "audio"), ("video", "video")):
            if props.get("modalities", {}).get(clave):
                entradas.append(modalidad)
        if len(entradas) > 1:
            entradas = [m for m in MODALITIES if m in entradas]
            d.ofrecer("modalities.input", entradas, "GET /props (modalities)")
            d.ofrecer("modalities.output", ["text"], "GET /props (modalities)")
        if mod.get("vision") and not mod.get("video"):
            d.avisos.append("el servidor dice que no acepta video (modalities.video=false)")

    caps = props.get("chat_template_caps")
    if isinstance(caps, dict):
        if caps.get("supports_tools"):
            d.ofrecer("tool_call", True, "GET /props (supports_tools)")
        # 'supports_reasoning_effort' es del servidor, no del modelo: no lo uso

    ajustes = props.get("default_generation_settings")
    if isinstance(ajustes, dict):
        params = ajustes.get("params") or {}
        for clave in ("n_ctx", "ctx_size"):
            if isinstance(params.get(clave), int) and params[clave] > 0:
                d.ofrecer("limit.context", params[clave], f"GET /props ({clave})")
                break

    if props.get("model_path"):
        textos.append(_nombre_del_repo(str(props["model_path"])))


def _desde_show(show, d, textos):
    """ollama `/api/show`: `capability` y `model_info` por modelo."""
    if not isinstance(show, dict):
        return

    _desde_capabilities(_lista_capability(show.get("capability") or show.get("capabilities")),
                        "POST /api/show (capability)", d, textos)

    info = show.get("model_info")
    if isinstance(info, dict):
        for clave, valor in info.items():
            if not isinstance(valor, int) or valor <= 0:
                continue
            if clave.endswith(".context_length") or clave.endswith(".num_ctx"):
                d.ofrecer("limit.context", valor, "POST /api/show (model_info)")
            if clave.endswith(".att_num_frames") or clave.endswith(".video"):
                d.ofrecer("modalities.input", _con("image", "video"),
                          "POST /api/show (model_info)")

    # ollama manda `parameters` como cadena JSON; otros servidores compatibles
    # (lmstudio y algunos forks) la devuelven ya como objeto.
    parametros = show.get("parameters")
    if isinstance(parametros, str) and parametros.strip():
        try:
            parametros = json.loads(parametros)
        except ValueError:
            parametros = None
    if isinstance(parametros, dict):
        for clave in ("num_ctx", "n_ctx", "context"):
            if isinstance(parametros.get(clave), int) and parametros[clave] > 0:
                d.ofrecer("limit.context", parametros[clave], "POST /api/show (parameters)")
                break
        if parametros.get("mmproj") or parametros.get("clip_model_path"):
            d.ofrecer("modalities.input", _con("image"), "POST /api/show (mmproj)")

    detalles = show.get("details")
    if isinstance(detalles, dict):
        for clave in ("family", "format"):
            if detalles.get(clave):
                textos.append(str(detalles[clave]))
    if show.get("model"):
        textos.append(str(show["model"]))


# --------------------------------------------------------------------- registro --
_INDICE = {}
_AVISO_REGISTRO = None      # sobre que ruta se aviso ya de que no existe


def _nombre_del_repo(ruta: str) -> str:
    """De '/hf/hub/models--nvidia--NVIDIA-Nemotron-3.5-Super-VL.../snapshots/xxx' saca el repo."""
    tramos = [t for t in re.split(r"[/\\]", ruta) if t]
    for tramo in reversed(tramos):
        if tramo.startswith("models--"):
            partes = tramo.split("--")
            return partes[-1] if len(partes) > 1 else tramo
        if tramo not in ("snapshots", "blobs", "refs") and not re.fullmatch(r"[0-9a-f]{20,}", tramo):
            return tramo
    return ""


def _formas(texto: str) -> list:
    """Las maneras en que un id puede aparecer en el registro, de mas a menos literal."""
    if not texto:
        return []
    salida = []
    bruto = str(texto).strip().lower()
    for valor in (bruto, bruto.replace(":", "/").rsplit("/tag", 1)[0]):
        if valor and valor not in salida:
            salida.append(valor)
    cola = bruto.split("/")[-1]
    if cola and cola not in salida:
        salida.append(cola)
    if ":" in cola:
        sin_tag = cola.split(":")[0]
        if sin_tag not in salida:
            salida.append(sin_tag)
    return salida


def _indice_registro(ruta: str = None):
    """{forma: (provider, model_id, entrada)} sobre el models.json de opencode.

    Se cachea por ruta y mtime: leer el registro cuesta un par de megas y no
    cambia entre dos modelos del mismo provider.
    """
    ruta = ruta or RUTA_REGISTRO
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        return None
    guardado = _INDICE.get(ruta)
    if guardado and guardado[0] == mtime:
        return guardado[1]

    try:
        with open(ruta, encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, ValueError):
        return None

    indice = {}
    proveedores = datos.get("providers") if isinstance(datos, dict) else None
    if not isinstance(proveedores, dict):
        proveedores = datos if isinstance(datos, dict) else {}
    for pid, proveedor in proveedores.items():
        modelos = proveedor.get("models") if isinstance(proveedor, dict) else None
        if not isinstance(modelos, dict):
            continue
        for mid, entrada in modelos.items():
            if not isinstance(entrada, dict):
                continue
            for forma in _formas(mid) + _formas(entrada.get("id")) + _formas(entrada.get("family")):
                indice.setdefault(forma, (str(pid), str(mid), entrada))
    _INDICE[ruta] = (mtime, indice)
    return indice


def _desde_registro(candidatos, d, textos):
    """Buscar el modelo en el registro de opencode (models.dev)."""
    global _AVISO_REGISTRO
    indice = _indice_registro()
    if indice is None:
        # Se avisa una vez por ruta y comando, no por modelo: es lo mismo para todos
        if _AVISO_REGISTRO != RUTA_REGISTRO:
            d.avisos.append("no se encontro el registro de opencode en "
                            + str(RUTA_REGISTRO))
            _AVISO_REGISTRO = RUTA_REGISTRO
        return
    if not indice:
        return

    for texto in candidatos:
        for forma in _formas(texto):
            encontrado = indice.get(forma)
            if not encontrado:
                continue
            pid, mid, entrada = encontrado
            etiqueta = f"registro opencode ({pid}/{mid})"
            for clave in DE_REGISTRO:
                valor = get_value(entrada, clave)
                if valor is None:
                    continue
                d.ofrecer(clave, valor, etiqueta)
            textos.append(f"{pid} {mid}")
            if entrada.get("family"):
                textos.append(str(entrada["family"]))
            return


# ----------------------------------------------------------------- heuristico --
def _desde_nombre(candidatos, d):
    """Lo ultimo que queda: los apellidos del modelo. Marcado como suposicion."""
    texto = " ".join(str(c) for c in candidatos if c).lower()
    if not texto:
        return
    fuente = "suposicion por el nombre"

    if any(marca in texto for marca in MARCAS_VISION_NOMBRE):
        d.ofrecer("modalities.input", _con("image"), fuente, suposicion=True)
        d.ofrecer("modalities.output", ["text"], fuente, suposicion=True)
    if any(marca in texto for marca in MARCAS_AUDIO_NOMBRE):
        d.ofrecer("modalities.input", _con("audio"), fuente, suposicion=True)
    if any(marca in texto for marca in MARCAS_TOOLS_NOMBRE):
        d.ofrecer("tool_call", True, fuente, suposicion=True)
    if any(marca in texto for marca in MARCAS_REASONING_NOMBRE):
        d.ofrecer("reasoning", True, fuente, suposicion=True)


# ------------------------------------------------------------- probar a ver --
def probar_vision(base_url, api_key, model_id):
    """Mandarle una imagen diminuta y ver si la acepta (o se queja de ello).

    Devuelve (True|False|None, mensaje). None es 'no se ha podido averiguar': el
    servidor no contesto, o el error no tiene nada que ver con imagenes.
    """
    cuerpo = {
        "model": model_id,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "hi"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PIXEL_PNG}"}},
        ]}],
    }
    estado, mensaje = ProviderScanner.probar_entrada(base_url, "/v1/chat/completions", cuerpo,
                                                     api_key)
    if estado is None:
        return None, mensaje
    texto = (mensaje or "").lower()
    if estado < 400:
        return True, "acepto una imagen 1x1"
    if any(palabra in texto for palabra in _PALABRAS_NO_VISION):
        return False, texto[:160]
    return None, f"{estado}: {texto[:140]}"


# ---------------------------------------------------------------------- entrada --
def detectar_opciones(base_url, api_key, model_id, entrada=None, nombre=None,
                      explorador=None, usar_registro=True, probar=False):
    """Que se puede saber de un modelo, y de donde.

    `entrada` es el objeto crudo que el servidor devolvio para este modelo (si se
    tiene, evita repetir el GET). `explorador` se pasa para reutilizar las consultas
    entre los modelos de un mismo provider.
    """
    d = Deteccion()
    textos = []
    explorador = explorador or Explorador(base_url, api_key)

    _desde_entrada(entrada or {}, d, "GET /v1/models", textos)

    props = explorador.json("/props")
    if props:
        _desde_props(props, d, textos)

    d.servidor = _marca_motor(entrada, props)[0]

    # /api/show solo lo trae ollama; si ya sabemos quien es el servidor no se le molesta
    show = None
    if d.servidor not in ("vllm", "sglang", "llama.cpp"):
        show = explorador.show(model_id)
        if show:
            _desde_show(show, d, textos)
            d.servidor = d.servidor or "ollama"

    candidatos = [model_id, nombre] + textos
    if usar_registro:
        _desde_registro([c for c in candidatos if c], d, textos)

    _desde_nombre([model_id, nombre, _nombre_del_repo(str((entrada or {}).get("root") or ""))]
                  + textos, d)

    # opencode exige context y output juntos: con solo el contexto, se supone la salida
    contexto = d.valores.get("limit.context")
    if isinstance(contexto, int) and contexto > 0 and "limit.output" not in d.valores:
        d.ofrecer("limit.output", min(contexto // 4, SALIDA_MAXIMA_SUPUESTA),
                  "suposicion: salida prudente a partir del contexto", suposicion=True)

    if probar and "modalities.input" not in d.valores:
        acepta, mensaje = probar_vision(base_url, api_key, model_id)
        if acepta is None:
            d.avisos.append(f"la prueba de vision no conclusive: {mensaje}")
        elif acepta:
            d.ofrecer("modalities.input", _con("image"), "prueba: acepto una imagen")
            d.ofrecer("modalities.output", ["text"], "prueba: acepto una imagen")
        else:
            d.ofrecer("modalities.input", ["text"], "prueba: rechazo la imagen")
            d.ofrecer("modalities.output", ["text"], "prueba: rechazo la imagen")

    return d


def marca_detectada() -> int:
    """Marca de tiempo que se guarda junto a lo detectado."""
    return int(time.time())
