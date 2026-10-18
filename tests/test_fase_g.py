"""
Regresiones de la Fase G: `ocm model detect` (autodeteccion de opciones).

Ejecutar:  uv run python tests/test_fase_g.py
Salida:    lista de checks + codigo de salida 1 si alguno falla.

Todo va con el transporte (`_get_json`, `_post_json`, `probar_entrada`) sustituido,
asi que no se toca la red: se finge que el servidor es llama.cpp, vLLM u ollama.
"""

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from opencode_config_manager import api, deteccion  # noqa: E402
from opencode_config_manager.cli import main  # noqa: E402

CHECKS = []
SCHEMA = "https://opencode.ai/config.json"


def check(cond, label):
    print(("  OK    " if cond else "  FALLO ") + label)
    CHECKS.append((bool(cond), label))


def run(home, config, *argv):
    return main(["--home", str(home), "--config", str(config), *argv])


def run_cap(home, config, *argv):
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            run(home, config, *argv)
    except SystemExit:
        pass
    return buffer.getvalue()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ------------------------------------------------------------------- servidor --
class ServidorFalso:
    """Finge los endpoints de metadatos; cuenta lo que se le pidio."""

    def __init__(self, gets=None, show=None, prueba=None):
        # endpoint -> (datos, error); por defecto todo dice que no existe
        self.gets = {"/api/tags": (None, "404"), "/v1/models": (None, "404"),
                     "/props": (None, "404")}
        self.gets.update(gets or {})
        self.show = show
        self.prueba = prueba              # (estado, mensaje) del POST de chat
        self.llamados = []
        self._originales = None

    def _get_json(self, base_url, endpoint, api_key=None):
        self.llamados.append(endpoint)
        if endpoint not in self.gets:
            return None, f"{endpoint} no existe"
        valor = self.gets[endpoint]
        if isinstance(valor, tuple):          # (datos, error)
            return valor
        return valor, None                    # solo los datos

    def _post_json(self, base_url, endpoint, cuerpo, api_key=None):
        self.llamados.append(f"POST {endpoint}")
        if endpoint != "/api/show" or self.show is None:
            return None, f"{endpoint} no existe"
        return self.show, None

    def _probar(self, base_url, endpoint, cuerpo, api_key=None):
        self.llamados.append(f"POST {endpoint} (prueba)")
        if self.prueba is None:
            return None, "no se probo"
        return self.prueba

    def instalar(self):
        Ps = api.ProviderScanner
        self._originales = (Ps._get_json, Ps._post_json, Ps.probar_entrada)
        Ps._get_json = staticmethod(self._get_json)
        Ps._post_json = staticmethod(self._post_json)
        Ps.probar_entrada = staticmethod(self._probar)

    def restaurar(self):
        Ps = api.ProviderScanner
        Ps._get_json, Ps._post_json, Ps.probar_entrada = self._originales

    def pidio(self, endpoint) -> bool:
        return any(endpoint in llamada for llamada in self.llamados)


def modelos_vllm(modelo="mi-modelo", **extra):
    """La forma de OpenAI: {'data': [...]}, con lo que trae vLLM o SGLang."""
    entrada = {"id": modelo, "object": "model", "owned_by": "vllm"}
    entrada.update(extra)
    return {"data": [entrada]}


def modelos_ollama(modelo="mi-modelo", **extra):
    """La forma de ollama: {'models': [...]} (la que usa tambien llama-server)."""
    entrada = {"name": modelo, "model": modelo}
    entrada.update(extra)
    return {"models": [entrada]}


# ---------------------------------------------------------------------- caché --
def cache_de(modelos, tipo="vllm"):
    entrada = {
        "uid": "aabbccdd",
        "name": "Local",
        "baseUrl": "http://127.0.0.1:59999",
        "reachable": True,
        "last_scan": 1700000000,
        "models": modelos,
    }
    if tipo:
        entrada["provider_type"] = tipo
    return {"cache_version": 2, "cache_timestamp": 1700000000,
            "providers": {"local": entrada}}


def preparar(home, config, modelos=None, con_config=False):
    write_json(home / "provider_cache.json",
               cache_de(modelos or {"mi-modelo": {"name": "mi-modelo"}}))
    if con_config:
        write_json(config, {"$schema": SCHEMA, "provider": {
            "local": {"npm": "@ai-sdk/openai-compatible", "name": "Local",
                      "options": {"baseURL": "http://127.0.0.1:59999/v1"},
                      "models": {}}}})
    else:
        write_json(config, {"$schema": SCHEMA, "provider": {}})


def registro_falso(home: Path, contenido):
    """Montar el models.json de opencode que usan las pruebas."""
    ruta = home / "models.json"
    write_json(ruta, contenido)
    deteccion.RUTA_REGISTRO = str(ruta)
    deteccion._INDICE.clear()


# ------------------------------------------------------------- G1 llama.cpp --
def scenario_props(home: Path, config: Path):
    """llama-server dice las modalidades en /props: eso es una prueba, no una pista."""
    print("\n=== G1: llama.cpp por /props ===")
    preparar(home, config)
    servidor = ServidorFalso(
        gets={"/v1/models": modelos_ollama("mi-modelo",
                                           capabilities=["completion", "multimodal"],
                                           details={"format": "gguf"}),
              "/props": {"modalities": {"vision": True, "video": True, "audio": False},
                         "chat_template_caps": {"supports_tools": True,
                                                "supports_reasoning_effort": True},
                         "model_path": "/models/Qwen3-VL-Q8_0.gguf",
                         "default_generation_settings": {"params": {"n_ctx": 131072}}}},
    )
    servidor.instalar()
    try:
        salida = run_cap(home, config, "model", "detect", "local", "--all", "--no-registro")
    finally:
        servidor.restaurar()

    check("[llama.cpp]" in salida, "G1: se da cuenta de que es llama.cpp")
    check("GET /props (modalities)" in salida, "G1: las modalidades salen de /props")
    check("text,image,video" in salida,
          "G1: video entra por /props aunque 'capabilities' solo dijera multimodal")
    check("131072" in salida and "n_ctx" in salida, "G1: el contexto sale de /props")
    check("GET /props (supports_tools)" in salida, "G1: tool calling de /props")
    check("reasoning" not in salida,
          "G1: 'supports_reasoning_effort' no hace decir que el modelo razona")
    check("opciones_fuente" not in
          read(home / "provider_cache.json")["providers"]["local"]["models"]["mi-modelo"],
          "G1: sin --apply la cache no se toca")


# ------------------------------------------------------------------ G2 vLLM --
def scenario_vllm(home: Path, config: Path):
    """vLLM no dice modalidades: queda max_model_len y la pista del nombre."""
    print("\n=== G2: vLLM, a base de indicios ===")
    preparar(home, config, modelos={"nemotron-3.5-super-vl": {"name": "nemotron-3.5-super-vl"}})
    servidor = ServidorFalso(
        gets={"/v1/models": modelos_vllm("nemotron-3.5-super-vl",
                                         root="/hf/hub/models--nvidia--NVIDIA-Nemotron-Super-VL-120B"
                                              "/snapshots/2e5cc3953bb1ea66b2fb7c831fee3aa317427e69",
                                         max_model_len=1048576)},
    )
    servidor.instalar()
    try:
        salida = run_cap(home, config, "model", "detect", "local", "--all", "--no-registro")
    finally:
        servidor.restaurar()

    check("[vllm]" in salida, "G2: reconoce vLLM por owned_by")
    check("1048576" in salida and "max_model_len" in salida,
          "G2: el contexto sale de max_model_len")
    check("suposicion por el nombre" in salida,
          "G2: la vision sale de los apellidos del modelo (-VL)")
    check("(pista del nombre, no una prueba)" in salida,
          "G2: y lo dice claro, no lo vende como cierto")
    check(not servidor.pidio("/api/show"),
          "G2: a vLLM no se le pregunta /api/show (solo lo tiene ollama)")


# ----------------------------------------------------------------- G3 ollama --
def scenario_ollama(home: Path, config: Path):
    """ollama lo dice casi todo por POST /api/show."""
    print("\n=== G3: ollama por /api/show ===")
    preparar(home, config)
    servidor = ServidorFalso(
        gets={"/api/tags": modelos_ollama("mi-modelo",
                                          details={"format": "gguf", "family": "qwen2"}),
              "/props": (None, "404")},
        show={"capability": ["completion", "vision", "tools"],
              "model_info": {"qwen2vl.context_length": 262144,
                             "qwen2vl.att_num_frames": 16}},
    )
    servidor.instalar()
    try:
        salida = run_cap(home, config, "model", "detect", "local", "--all", "--no-registro")
    finally:
        servidor.restaurar()

    check("POST /api/show (capability)" in salida, "G3: las capacidades salen de /api/show")
    check("image" in salida, "G3: 'vision' se traduce a image en las entradas")
    check("GET /props" not in salida, "G3: no se inventa un /props que no existe")
    check("262144" in salida and "model_info" in salida, "G3: el contexto sale de model_info")
    check("video" in salida, "G3: att_num_frames del model_info cuenta como video")


# ---------------------------------------------------------------- G4 registro --
def scenario_registro(home: Path, config: Path):
    """El registro de opencode rellena lo que el servidor no dice, sin taparlo."""
    print("\n=== G4: el registro de opencode ===")
    registro_falso(home, {"providers": {
        "vultr": {"models": {"mi-modelo": {
            "name": "Mi Modelo",
            "limit": {"context": 8192, "output": 4096},
            "modalities": {"input": ["text", "image"], "output": ["text"]},
            "reasoning": True, "tool_call": True, "temperature": True,
            "attachment": True, "status": "ga",
        }}}},
    })
    preparar(home, config)
    servidor = ServidorFalso(gets={"/v1/models": modelos_vllm("mi-modelo", max_model_len=131072)})
    servidor.instalar()
    try:
        salida = run_cap(home, config, "model", "detect", "local", "--all")
        check("registro opencode (vultr/mi-modelo)" in salida,
              "G4: encuentra el modelo en el registro")
        check("reasoning" in salida and "tool_call" in salida,
              "G4: razonamiento y tools salen del registro")
        check("131072" in salida and "max_model_len" in salida,
              "G4: el contexto del servidor gana al del registro")
        check("status" not in salida,
              "G4: el estado ('ga' del registro) no es cosa que detecte ocm")
        check("Mi Modelo" not in salida,
              "G4: el nombre visible no se toca: lo pone alguien")

        salida2 = run_cap(home, config, "model", "detect", "local", "--all", "--no-registro")
        check("registro opencode" not in salida2,
              "G4: --no-registro deja solo lo que dice el servidor")
    finally:
        servidor.restaurar()

    # aviso si no hay registro
    deteccion.RUTA_REGISTRO = str(home / "no-existe.json")
    deteccion._INDICE.clear()
    servidor = ServidorFalso(gets={"/v1/models": modelos_vllm("mi-modelo")})
    servidor.instalar()
    try:
        salida = run_cap(home, config, "model", "detect", "local", "--all")
    finally:
        servidor.restaurar()
    check("no se encontro el registro" in salida,
          "G4: avisa si falta el registro de opencode")


# ------------------------------------------------------------------- G5 apply --
def scenario_apply(home: Path, config: Path):
    """Con --apply rellena huecos y respeta lo que ya estaba puesto."""
    print("\n=== G5: --apply ===")
    registro_falso(home, {"providers": {}})
    preparar(home, config, modelos={
        "mi-modelo": {"name": "Mi Modelo", "modalities": {"input": ["text"]}},
    })
    servidor = ServidorFalso(
        gets={"/v1/models": modelos_vllm("mi-modelo", max_model_len=131072,
                                         capabilities=["completion", "tools"])})
    servidor.instalar()
    try:
        antes_config = config.read_bytes()
        salida = run_cap(home, config, "model", "detect", "local", "--all", "--apply")
    finally:
        servidor.restaurar()

    entrada = read(home / "provider_cache.json")["providers"]["local"]["models"]["mi-modelo"]
    check("opcion" in salida, "G5: dice cuantas cosas escribio")
    check(entrada.get("limit", {}).get("context") == 131072,
          "G5: el contexto que no estaba se anade")
    check(entrada.get("modalities", {}).get("input") == ["text"],
          "G5: lo que tu pusiste a mano no se pisa")
    check(entrada.get("tool_call") is True, "G5: tool calling detectado se anade")
    check(entrada.get("opciones_fuente", {}).get("limit.context") ==
          "GET /v1/models (max_model_len)", "G5: queda constancia de donde salio")
    check("modalities.input" not in entrada.get("opciones_fuente", {}),
          "G5: no se firma como propio un valor que no se cambio")
    check(isinstance(entrada.get("opciones_detectado_en"), int),
          "G5: y queda la fecha de la deteccion")
    check(config.read_bytes() == antes_config,
          "G5: detectar escribe la cache, nunca opencode.json")

    # con --force si que se actualiza
    servidor = ServidorFalso(
        gets={"/v1/models": modelos_vllm("mi-modelo", max_model_len=131072,
                                         capabilities=["completion", "vision"])})
    servidor.instalar()
    try:
        run_cap(home, config, "model", "detect", "local", "--all", "--apply", "--force")
    finally:
        servidor.restaurar()

    entrada = read(home / "provider_cache.json")["providers"]["local"]["models"]["mi-modelo"]
    check(entrada.get("modalities", {}).get("input") == ["text", "image"],
          "G5: con --force si que entra la vision")


# ----------------------------------------------------- G6 no se filtran claves --
def scenario_no_filtran(home: Path, config: Path):
    """Las claves de ocm (opciones_fuente, ...) no salen en opencode.json."""
    print("\n=== G6: lo que guarda ocm no se cuela en opencode.json ===")
    registro_falso(home, {"providers": {}})
    preparar(home, config, con_config=True, modelos={
        "mi-modelo": {"name": "Mi Modelo", "limit": {"context": 131072},
                      "tool_call": True,
                      "opciones_fuente": {"limit.context": "GET /v1/models (max_model_len)",
                                          "tool_call": "GET /props (supports_tools)"},
                      "opciones_detectado_en": 1700000000},
    })
    run(home, config, "update", "local")

    modelo = read(config)["provider"]["local"]["models"]["mi-modelo"]
    check(modelo.get("limit") == {"context": 131072}, "G6: el limite si llega al config")
    check(modelo.get("tool_call") is True, "G6: tool_call llega al config")
    check("opciones_fuente" not in modelo, "G6: 'opciones_fuente' no va a opencode.json")
    check("opciones_detectado_en" not in modelo, "G6: la marca de tiempo tampoco")
    check("opciones_fuente" in
          read(home / "provider_cache.json")["providers"]["local"]["models"]["mi-modelo"],
          "G6: y en la cache se conserva para la ficha")


# ------------------------------------------------------------------ G7 ficha --
def scenario_ficha(home: Path, config: Path):
    """`ocm model info` cuenta quien puso cada valor."""
    print("\n=== G7: la ficha cuenta la procedencia ===")
    registro_falso(home, {"providers": {}})
    preparar(home, config, modelos={
        "mi-modelo": {"name": "Mi Modelo", "tool_call": True,
                      "modalities": {"input": ["text", "image"]},
                      "opciones_fuente": {
                          "tool_call": "GET /props (supports_tools)",
                          "modalities.input": "suposicion por el nombre"},
                      "opciones_detectado_en": 1700000000},
    })
    salida = run_cap(home, config, "model", "info", "local", "mi-modelo")
    check("GET /props (supports_tools)" in salida,
          "G7: la ficha dice que tool_call viene del servidor")
    check("revisalo" in salida or "una pista, no una prueba" in salida,
          "G7: y avisa cuando fue una suposicion")
    check("opciones_fuente" not in salida,
          "G7: las claves de ocm no salen como 'otras claves'")


# --------------------------------------------------------------- G8 --probar --
def scenario_probar(home: Path, config: Path):
    """--probar manda una imagen 1x1 y lee lo que contesta el servidor."""
    print("\n=== G8: --probar ===")
    registro_falso(home, {"providers": {}})

    def correr(prueba):
        preparar(home, config)
        servidor = ServidorFalso(gets={"/v1/models": modelos_vllm("mi-modelo")},
                                 prueba=prueba)
        servidor.instalar()
        try:
            salida = run_cap(home, config, "model", "detect", "local", "--all",
                             "--no-registro", "--probar")
        finally:
            servidor.restaurar()
        return salida, servidor

    salida, _ = correr((400, "The model does not support image inputs"))
    check("prueba: rechazo la imagen" in salida,
          "G8: si se queja de las imagenes, se apunta que no ve")

    salida, _ = correr((200, '{"choices":[]}'))
    check("prueba: acepto una imagen" in salida, "G8: si la acepta, se apunta image")

    salida, servidor = correr((500, "boom interno"))
    check("no conclusive" in salida, "G8: un error raro no cuenta como evidencia")
    check(not servidor.pidio("/api/show"),
          "G8: a un vLLM no se le pregunta /api/show ni por error")

    # si el servidor ya lo dijo, no se gasta la peticion
    preparar(home, config)
    servidor = ServidorFalso(
        gets={"/v1/models": modelos_vllm("mi-modelo"),
              "/props": {"modalities": {"vision": True, "video": False, "audio": False}}},
        prueba=(200, "{}"))
    servidor.instalar()
    try:
        run_cap(home, config, "model", "detect", "local", "--all", "--no-registro", "--probar")
    finally:
        servidor.restaurar()
    check(not servidor.pidio("chat/completions"),
          "G8: si /props ya lo dijo, no se gasta una peticion en probarlo")


# ----------------------------------------------------------------- G9 cacheo --
def scenario_cacheo(home: Path, config: Path):
    """Los endpoints de metadatos se piden una vez por provider, no por modelo."""
    print("\n=== G9: no repetir consultas ===")
    registro_falso(home, {"providers": {}})
    preparar(home, config, modelos={"a": {"name": "a"}, "b": {"name": "b"}})
    servidor = ServidorFalso(
        gets={"/v1/models": {"data": [{"id": "a", "owned_by": "llama.cpp"},
                                      {"id": "b", "owned_by": "llama.cpp"}]},
              "/props": {"modalities": {"vision": True}}})
    servidor.instalar()
    try:
        run_cap(home, config, "model", "detect", "local", "--all", "--no-registro")
    finally:
        servidor.restaurar()

    veces_props = sum(1 for llamada in servidor.llamados if "/props" in llamada)
    check(veces_props == 1, f"G9: /props se pide una vez para dos modelos ({veces_props})")
    veces_v1 = sum(1 for llamada in servidor.llamados if "/v1/models" in llamada)
    check(veces_v1 == 1, f"G9: /v1/models se pide una vez ({veces_v1})")


# ----------------------------------------------------------- G10 el asistente --
def scenario_asistente(home: Path, config: Path):
    """El asistente de opciones dice de donde salio cada valor."""
    print("\n=== G10: el asistente cuenta la procedencia ===")
    from opencode_config_manager.commands.options import configure_model_entry

    entrada = {"name": "Mi Modelo", "tool_call": True, "reasoning": True,
               "opciones_fuente": {"tool_call": "GET /props (supports_tools)",
                                   "reasoning": "suposicion por el nombre"},
               "opciones_detectado_en": 1700000000}
    buffer = io.StringIO()
    sys.stdin = io.StringIO("\n" * 24)
    try:
        with redirect_stdout(buffer):
            configure_model_entry(entrada, advanced=False, header="Mi Modelo")
    finally:
        sys.stdin = sys.__stdin__
    salida = buffer.getvalue()

    check("Opciones que puso 'ocm model detect'" in salida,
          "G10: el asistente dice que eso lo puso la deteccion")
    check("GET /props (supports_tools)" in salida,
          "G10: y de donde salio cada una")
    check("una pista, no una prueba" in salida,
          "G10: marca las que fueron suposicion")
    check("lo puso una pista del nombre" in salida,
          "G10: y lo recuerda justo antes de preguntar ese campo")


# ------------------------------------------------------------------ G11 units --
def scenario_unidades():
    """Cositas sueltas que se rompen solas."""
    print("\n=== G11: utilidades ===")
    casos = {
        "/hf/hub/models--nvidia--NVIDIA-Nemotron-3.5-Super-VL-120B/snapshots/"
        "2e5cc3953bb1ea66b2fb7c831fee3aa317427e69": "NVIDIA-Nemotron-3.5-Super-VL-120B",
        "/models/Qwen3-VL-Q8_0.gguf": "Qwen3-VL-Q8_0.gguf",
        "": "",
    }
    for entrada, salida in casos.items():
        obtenido = deteccion._nombre_del_repo(entrada)
        check(obtenido == salida,
              f"G11: _nombre_del_repo({entrada[-30:]!r}) -> {salida!r}")

    formas = deteccion._formas("Qwen/Qwen3-VL:latest")
    check("qwen3-vl" in formas and "qwen/qwen3-vl:latest" in formas,
          f"G11: _formas saca varias variantes ({formas})")

    d = deteccion.Deteccion()
    d.ofrecer("modalities.input", ["text", "image"], "capabilities")
    d.ofrecer("modalities.input", ["text", "video"], "/props")
    check(d.valores["modalities.input"] == ["text", "image", "video"],
          "G11: dos fuentes del servidor suman modalidades")
    check("+" in d.fuentes["modalities.input"], "G11: y la fuente queda compuesta")

    d2 = deteccion.Deteccion()
    d2.ofrecer("modalities.input", ["text"], "GET /props (modalities)")
    d2.ofrecer("modalities.input", ["text", "image"], "suposicion por el nombre",
               suposicion=True)
    check(d2.valores["modalities.input"] == ["text"],
          "G11: una pista del nombre no anade lo que el servidor nego")

    d3 = deteccion.Deteccion()
    d3.ofrecer("tool_call", True, "suposicion por el nombre", suposicion=True)
    d3.ofrecer("reasoning", True, "suposicion por el nombre", suposicion=True)
    check(d3.es_suposicion("tool_call") and d3.es_suposicion("reasoning"),
          "G11: lo que sale del nombre queda marcado")


# ------------------------------------------------- G12 el escaneo no rompe nada --
def scenario_preserva(home: Path, config: Path):
    """Volver a escanear despues de detectar no borra las opciones ni su procedencia."""
    print("\n=== G12: el escaneo conserva lo detectado ===")
    registro_falso(home, {"providers": {}})
    preparar(home, config, modelos={
        "mi-modelo": {"name": "Mi Modelo", "limit": {"context": 131072},
                      "tool_call": True,
                      "opciones_fuente": {"limit.context": "GET /v1/models (max_model_len)"},
                      "opciones_detectado_en": 1700000000},
    })
    servidor = ServidorFalso(gets={"/v1/models": modelos_vllm("mi-modelo")})
    servidor.instalar()
    sys.stdin = io.StringIO("\n")
    try:
        run_cap(home, config, "cache", "update", "local")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()

    entrada = read(home / "provider_cache.json")["providers"]["local"]["models"]["mi-modelo"]
    check(entrada.get("limit", {}).get("context") == 131072,
          "G12: el escaneo conserva el contexto detectado")
    check(entrada.get("opciones_fuente", {}).get("limit.context") ==
          "GET /v1/models (max_model_len)",
          "G12: y conserva de donde salio")
    check(entrada.get("name") == "Mi Modelo", "G12: y el nombre visible")


# ------------------------------------------------------------------ G13 --json --
def scenario_json(home: Path, config: Path):
    """`--json` saca datos parseables, sin lineas sueltas estorbando."""
    print("\n=== G13: --json ===")
    registro_falso(home, {"providers": {}})
    preparar(home, config)
    servidor = ServidorFalso(gets={"/v1/models": modelos_vllm("mi-modelo",
                                                               max_model_len=131072)})
    servidor.instalar()
    try:
        salida = run_cap(home, config, "model", "detect", "local", "--all",
                         "--no-registro", "--json")
    finally:
        servidor.restaurar()

    try:
        datos = json.loads(salida)
    except ValueError as error:
        check(False, f"G13: la salida de --json es JSON ({error})")
        return

    check(isinstance(datos, list) and len(datos) == 1,
          "G13: --json da una lista con cada modelo")
    parte = datos[0]
    check(parte.get("provider") == "local" and parte.get("model") == "mi-modelo",
          "G13: y dice que modelo es")
    check(parte.get("servidor") == "vllm", "G13: informa del servidor")
    check(parte.get("valores", {}).get("limit.context") == 131072,
          "G13: los valores salen por su ruta")
    check(parte.get("fuentes", {}).get("limit.context") ==
          "GET /v1/models (max_model_len)", "G13: y su procedencia")
    check("opciones_fuente" not in
          read(home / "provider_cache.json")["providers"]["local"]["models"]["mi-modelo"],
          "G13: --json sigue sin escribir nada")

    # con un unico modelo no hay que preguntar cuales
    servidor = ServidorFalso(gets={"/v1/models": modelos_vllm("mi-modelo",
                                                               max_model_len=131072)})
    servidor.instalar()
    sys.stdin = io.StringIO("")
    try:
        salida = run_cap(home, config, "model", "detect", "local", "--no-registro")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()
    check("limit.context" in salida,
          "G13: habiendo un solo modelo no pregunta cuales repasar")


def main_tests():
    escenarios = [
        ("llama.cpp /props", scenario_props),
        ("vLLM indicios", scenario_vllm),
        ("ollama /api/show", scenario_ollama),
        ("registro", scenario_registro),
        ("apply", scenario_apply),
        ("no filtran claves", scenario_no_filtran),
        ("ficha", scenario_ficha),
        ("probar", scenario_probar),
        ("cacheo", scenario_cacheo),
        ("asistente", scenario_asistente),
        ("escaneo conserva", scenario_preserva),
        ("json", scenario_json),
    ]
    for nombre, fn in escenarios:
        home = Path(tempfile.mkdtemp(prefix="ocm-test-g-"))
        print(f"\n=== escenario: {nombre} ===")
        try:
            fn(home, home / "opencode.json")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    scenario_unidades()

    fallidos = [etiqueta for ok, etiqueta in CHECKS if not ok]
    print(f"\n=== {len(CHECKS) - len(fallidos)}/{len(CHECKS)} checks OK ===")
    for etiqueta in fallidos:
        print(" -", etiqueta)
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main_tests())
