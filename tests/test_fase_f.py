"""
Regresiones de la Fase F: el tipo de servidor (Ollama o vLLM).

Ejecutar:  uv run python tests/test_fase_f.py
Salida:    lista de checks + codigo de salida 1 si alguno falla.

Aqui se comprueba sobre todo que el tipo NO cambia opencode.json: es un dato de
ocm que solo decide que endpoint se escanea. Los escaneos van parcheados, asi que
no se toca la red.
"""

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from opencode_config_manager import api  # noqa: E402
from opencode_config_manager.api import ScanResult  # noqa: E402
from opencode_config_manager.cli import main  # noqa: E402
import entorno  # noqa: E402

entorno.sin_registro_models_dev()
from opencode_config_manager.commands.utils import url_para_config  # noqa: E402

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


def feed(*answers):
    sys.stdin = io.StringIO("\n".join(answers) + "\n")


# ------------------------------------------------------------------ fixtures --
MODELO = {"name": "Qwen 3 14B", "limit": {"context": 32768},
          "modalities": {"input": ["text", "image"]}}


def cache(tiempo=1700000000, tipo="vllm", fuente=None, evidencia=None):
    entrada = {
        "uid": "11223344",
        "name": "Prueba",
        "baseUrl": "http://127.0.0.1:59999",
        "reachable": True,
        "last_scan": tiempo,
        "models": {"qwen3:14b": dict(MODELO)},
    }
    if tipo:
        entrada["provider_type"] = tipo
    if fuente:
        entrada["type_source"] = fuente
    if evidencia:
        entrada["type_evidence"] = evidencia
    return {"cache_version": 2, "cache_timestamp": tiempo,
            "providers": {"prueba": entrada}}


def config_vacia():
    return {"$schema": SCHEMA, "provider": {}}


def config_escrita():
    return {
        "$schema": SCHEMA,
        "provider": {
            "prueba": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Prueba",
                "options": {"baseURL": "http://127.0.0.1:59999/v1"},
                "models": {"qwen3:14b": {"name": "Qwen 3 14B",
                                         "limit": {"context": 32768},
                                         "modalities": {"input": ["text", "image"]}}},
            }
        },
    }


class Falsos:
    """Sustituye los dos escaneadores y recuerda a cuales se llamo."""

    def __init__(self, ollama=None, vllm=None):
        self.ollama = ollama or ScanResult(False, [], "conexion rechazada")
        self.vllm = vllm or ScanResult(False, [], "conexion rechazada")
        self.llamados = []

    def instalar(self):
        self.originales = (api.ProviderScanner.scan_ollama, api.ProviderScanner.scan_vllm)

        def marcar(cual, resultado):
            def falso(base_url, api_key=None):
                self.llamados.append(cual)
                return resultado
            return staticmethod(falso)

        api.ProviderScanner.scan_ollama = marcar("ollama", self.ollama)
        api.ProviderScanner.scan_vllm = marcar("vllm", self.vllm)

    def restaurar(self):
        api.ProviderScanner.scan_ollama, api.ProviderScanner.scan_vllm = self.originales


def preparar(home, config, datos_cache=None, datos_config=None):
    write_json(config, datos_config or config_escrita())
    write_json(home / "provider_cache.json", datos_cache or cache())
    return config


# ------------------------------------------------------------------ F1 detecta --
def scenario_detecta(home: Path, config: Path):
    """Sin tipo en la caché, el escaneo lo averigua probando los dos endpoints."""
    print("\n=== F1: detectar el tipo solo ===")
    preparar(home, config, cache(tipo=None))

    falsos = Falsos(vllm=ScanResult(True, ["qwen3:14b", "nuevo:1"]))
    falsos.instalar()
    try:
        salida = run_cap(home, config, "cache", "update", "prueba")
    finally:
        falsos.restaurar()

    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check(entrada["provider_type"] == "vllm", "F1: detecta vllm cuando solo contesta /v1/models")
    check(entrada.get("type_source") == "auto", "F1: queda constancia de que lo detecto ocm")
    check(entrada.get("type_evidence") == "/v1/models",
          "F1: se guarda el endpoint que respondio")
    check("pruebo los dos endpoints" in salida, "F1: avisa de que esta detectando")
    check(falsos.llamados == ["ollama", "vllm"], "F1: prueba los dos endpoints, no uno al azar")
    check(set(entrada["models"]) == {"qwen3:14b", "nuevo:1"}, "F1: los modelos se actualizan")
    check(entrada["models"]["qwen3:14b"]["modalities"] == MODELO["modalities"],
          "F1: detectar el tipo no pisa las opciones del modelo")


# ---------------------------------------------------------- F2 autocorregirse --
def scenario_autocorreccion(home: Path, config: Path):
    """La caché decia ollama y el servidor es vllm: se corrige solo y avisa."""
    print("\n=== F2: corregir el tipo equivocado ===")
    preparar(home, config, cache(tipo="ollama"))

    falsos = Falsos(ollama=ScanResult(False, [], "404 no es ollama"),
                    vllm=ScanResult(True, ["qwen3:14b"]))
    falsos.instalar()
    try:
        salida = run_cap(home, config, "cache", "update", "prueba")
    finally:
        falsos.restaurar()

    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check(entrada["provider_type"] == "vllm", "F2: cambia el tipo al que de verdad responde")
    check(entrada.get("type_source") == "auto", "F2: queda marcado como detectado")
    check(entrada.get("type_evidence") == "/v1/models", "F2: la evidencia es el endpoint usado")
    check("lo cambio a 'vllm'" in salida, "F2: avisa del cambio en pantalla")
    check(entrada.get("reachable") is True, "F2: el escaneo cuenta como exito")
    check("last_scan_error" not in entrada, "F2: sin error pendiente")


# ------------------------------------------------------------------ F3 pin --
def scenario_pin_manual(home: Path, config: Path):
    """Si alguien lo fijo a mano, ocm escanea igual pero no lo cambia."""
    print("\n=== F3: el tipo fijado a mano se respeta ===")
    preparar(home, config, cache(tipo="ollama", fuente="manual"))

    falsos = Falsos(ollama=ScanResult(False, [], "404 no es ollama"),
                    vllm=ScanResult(True, ["qwen3:14b"]))
    falsos.instalar()
    try:
        salida = run_cap(home, config, "cache", "update", "prueba")
    finally:
        falsos.restaurar()

    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check(entrada["provider_type"] == "ollama", "F3: no cambia un tipo fijado a mano")
    check(entrada.get("type_source") == "manual", "F3: sigue marcado como manual")
    check(entrada.get("type_evidence") == "/v1/models",
          "F3: guarda por donde contesto el servidor aunque el tipo sea otro")
    check("ocm cache type prueba auto" in salida, "F3: dice como dejarlo seguir al servidor")
    check(entrada.get("reachable") is True, "F3: el escaneo no se considera fallido")


# ------------------------------------------------------------------ F4 caido --
def scenario_caido(home: Path, config: Path):
    """Ni /api/tags ni /v1/models: no se pierde nada."""
    print("\n=== F4: servidor apagado ===")
    preparar(home, config, cache(tipo="vllm"))
    antes = config.read_bytes()

    falsos = Falsos()
    falsos.instalar()
    try:
        salida = run_cap(home, config, "cache", "update", "prueba")
    finally:
        falsos.restaurar()

    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check(entrada.get("reachable") is False, "F4: marca el provider no accesible")
    check("conexion rechazada" in entrada.get("last_scan_error", ""),
          "F4: guarda el motivo del fallo")
    check(entrada.get("last_scan") == 1700000000, "F4: no finge un escaneo reciente")
    check(set(entrada["models"]) == {"qwen3:14b"}, "F4: conserva los modelos")
    check(entrada["models"]["qwen3:14b"].get("limit") == {"context": 32768},
          "F4: conserva las opciones por modelo")
    check(entrada["provider_type"] == "vllm", "F4: un escaneo fallido no cambia el tipo")
    check("accesible" in salida or "Error" in salida, "F4: el fallo se ve en pantalla")
    check(config.read_bytes() == antes if config.exists() else True,
          "F4: escanear no escribe en opencode.json")


# ------------------------------------------------------------------ F5 --type --
def scenario_flag_type(home: Path, config: Path):
    """`--type` fija el endpoint de esta pasada y lo deja marcado como manual."""
    print("\n=== F5: --type en cache update ===")
    preparar(home, config, cache(tipo="ollama"))

    falsos = Falsos(ollama=ScanResult(True, ["qwen3:14b"]),
                    vllm=ScanResult(True, ["qwen3:14b", "otro:2"]))
    falsos.instalar()
    try:
        run_cap(home, config, "cache", "update", "prueba", "--type", "vllm")
        entrada = read(home / "provider_cache.json")["providers"]["prueba"]
        check(entrada["provider_type"] == "vllm", "F5: --type fuerza el endpoint")
        check(entrada.get("type_source") == "manual", "F5: --type queda fijado a mano")
        check(entrada.get("type_evidence") == "/v1/models", "F5: la evidencia es la del tipo usado")
        check(falsos.llamados == ["vllm"],
              "F5: con el tipo forzudo no pierde tiempo probando el otro")

        # un valor que no es ollama/vllm/auto no escribe nada
        antes = json.dumps(entrada, sort_keys=True)
        salida = run_cap(home, config, "cache", "update", "prueba", "--type", "sglang")
        check("desconocido" in salida, "F5: un tipo desconocido se queja")
        despues = read(home / "provider_cache.json")["providers"]["prueba"]
        check(json.dumps(despues, sort_keys=True) == antes,
              "F5: un tipo desconocido no escribe en la caché")

        # volver a la deteccion automatica
        falsos.ollama = ScanResult(True, ["qwen3:14b"])
        run_cap(home, config, "cache", "update", "prueba", "--type", "auto")
        entrada = read(home / "provider_cache.json")["providers"]["prueba"]
        check(entrada.get("type_source") == "auto", "F5: --type auto suelta el fijado a mano")
        check(entrada["provider_type"] == "ollama",
              "F5: --type auto vuelve a detectar (ollama responde a /api/tags)")
    finally:
        falsos.restaurar()

    # --type sin provider: se queja en vez de aplicar el mismo tipo a todos
    preparar(home, config, cache(tipo="vllm"))
    salida = run_cap(home, config, "cache", "update", "--type", "vllm")
    check("--type necesita un provider" in salida, "F5: --type exige decir que provider")


# ------------------------------------------------------------ F6 alias y URLs --
def scenario_alias(home: Path, config: Path):
    """Los alias rarales escanean y escriben la URL correcta."""
    print("\n=== F6: alias y la URL con /v1 ===")
    preparar(home, config, cache(tipo="llama.cpp"))

    falsos = Falsos(vllm=ScanResult(True, ["qwen3:14b"]))
    falsos.instalar()
    try:
        run_cap(home, config, "cache", "update", "prueba")
    finally:
        falsos.restaurar()

    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check("vllm" in falsos.llamados and "ollama" not in falsos.llamados,
          "F6: 'llama.cpp' escanea por /v1/models, no por /api/tags")
    check(entrada["provider_type"] == "vllm", "F6: el alias queda normalizado en la caché")

    # la URL del config lleva /v1 sea cual sea el tipo
    hashes = {}
    for tipo in ("ollama", "vllm", "llama.cpp", "lmstudio", None):
        home_x = Path(tempfile.mkdtemp(prefix="ocm-tipo-"))
        try:
            config_x = home_x / "opencode.json"
            write_json(config_x, config_vacia())
            write_json(home_x / "provider_cache.json", cache(tipo=tipo))
            run(home_x, config_x, "update", "prueba")
            texto = read(config_x)["provider"]["prueba"]["options"]["baseURL"]
            hashes[str(tipo)] = (texto, config_x.read_bytes())
        finally:
            shutil.rmtree(home_x, ignore_errors=True)

    urls = {valor[0] for valor in hashes.values()}
    bytes_ = {valor[1] for valor in hashes.values()}
    check(urls == {"http://127.0.0.1:59999/v1"},
          f"F6: la URL escrita es siempre .../v1 (salo {urls})")
    check(len(bytes_) == 1, "F6: opencode.json sale identico con cualquier tipo")


def scenario_url_para_config():
    """La regla del /v1 depende del camino, no del tipo."""
    print("\n=== F6b: url_para_config ===")
    casos = {
        "http://127.0.0.1:11434": "http://127.0.0.1:11434/v1",
        "http://127.0.0.1:11434/": "http://127.0.0.1:11434/v1",
        "http://127.0.0.1:11434/v1": "http://127.0.0.1:11434/v1",
        "http://servidor:8080/proxy": "http://servidor:8080/proxy",
        "http://servidor:8080/proxy/": "http://servidor:8080/proxy",
        "": "",
    }
    for entrada, salida in casos.items():
        check(url_para_config(entrada) == salida,
              f"F6b: {entrada!r} -> {salida!r}")


# --------------------------------------------------------------- F7 forma JSON --
def scenario_forma(home: Path, config: Path):
    """Un 200 que no trae la forma esperada es un fallo, no un provider vacio."""
    print("\n=== F7: forma de la respuesta ===")
    original = api.ProviderScanner._get_json
    try:
        api.ProviderScanner._get_json = staticmethod(
            lambda base_url, endpoint, api_key=None: ({"models": [{"name": "a"}, "b"]}, None))
        check(api.ProviderScanner.scan_ollama("http://x").models == ["a", "b"],
              "F7: /api/tags con 'models' se acepta (mezclando formas)")

        api.ProviderScanner._get_json = staticmethod(
            lambda base_url, endpoint, api_key=None: ({"html": True}, None))
        check(not api.ProviderScanner.scan_ollama("http://x").success,
              "F7: un 200 sin 'models' no cuenta como ollama")
        check(not api.ProviderScanner.scan_vllm("http://x").success,
              "F7: un 200 sin 'data' no cuenta como vllm")

        api.ProviderScanner._get_json = staticmethod(
            lambda base_url, endpoint, api_key=None: (None, "contesto algo que no es JSON"))
        check(not api.ProviderScanner.scan_vllm("http://x").success,
              "F7: HTML en vez de JSON no rompe nada")

        api.ProviderScanner._get_json = staticmethod(
            lambda base_url, endpoint, api_key=None: ({"data": [{"id": "data/mi-modelo"}]}, None))
        check(api.ProviderScanner.scan_vllm("http://x").models == ["mi-modelo"],
              "F7: sigue quitando el prefijo data/")

        # si los dos responden, gana ollama (es lo que distingue a uno de otro)
        def ambos(base_url, endpoint, api_key=None):
            if endpoint.endswith("/api/tags"):
                return {"models": [{"name": "m"}]}, None
            return {"data": [{"id": "m"}]}, None

        api.ProviderScanner._get_json = staticmethod(ambos)
        prueba = api.ProviderScanner.probe("http://x")
        check(prueba.tipo == "ollama" and prueba.endpoint == "/api/tags",
              "F7: cuando contesta a los dos se queda con ollama")
    finally:
        api.ProviderScanner._get_json = original


# ------------------------------------------------------------- F8 cache type --
def scenario_cache_type(home: Path, config: Path):
    """`ocm cache type` mira y cambia el tipo sin tocar opencode.json."""
    print("\n=== F8: ocm cache type ===")
    preparar(home, config, cache(tipo="vllm", evidencia="/v1/models"))
    antes = config.read_bytes()

    run(home, config, "cache", "type", "prueba", "ollama")
    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check(entrada["provider_type"] == "ollama", "F8: poner el tipo directo funciona")
    check(entrada.get("type_source") == "manual", "F8: queda marcado como fijado a mano")
    check("type_evidence" not in entrada,
          "F8: al fijarlo a mano la evidencia del escaneo anterior deja de valer")
    check(config.read_bytes() == antes, "F8: cambiar el tipo no toca opencode.json")

    run(home, config, "cache", "type", "prueba", "auto")
    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check("provider_type" not in entrada, "F8: 'auto' quita el tipo (lo dira el escaneo)")
    check("type_source" not in entrada, "F8: 'auto' quita tambien la procedencia")
    check(config.read_bytes() == antes, "F8: ponerlo en auto tampoco toca el config")

    salida = run_cap(home, config, "cache", "type", "prueba", "patraña")
    check("desconocido" in salida, "F8: un valor imposible se queja")
    check(read(home / "provider_cache.json")["providers"]["prueba"].get("provider_type") is None,
          "F8: y no escribe nada")

    salida = run_cap(home, config, "cache", "type", "no-existe", "vllm")
    check("no encontrado" in salida, "F8: un provider inexistente se dice claro")

    # la lista sin argumentos
    write_json(home / "provider_cache.json",
               cache(tipo="ollama", fuente="manual", evidencia="/api/tags"))
    salida = run_cap(home, config, "cache", "type")
    check("prueba" in salida and "fijado a mano" in salida and "/api/tags" in salida,
          "F8: la lista cuenta tipo, procedencia y evidencia")

    # sin tipo por flag: pregunta, y Intro deja el actual
    salida = run_cap(home, config, "cache", "type", "prueba")
    check("Tipo de servidor" in salida or "Dejarlo en" in salida,
          "F8: sin argumento ofrece el menu")


# ------------------------------------------------------------------ F9 ficha --
def scenario_ficha(home: Path, config: Path):
    """`ocm model info` cuenta de donde salio el tipo y avisa si miente."""
    print("\n=== F9: la ficha del modelo ===")
    preparar(home, config, cache(tipo="vllm", fuente="manual", evidencia="/v1/models"))
    salida = run_cap(home, config, "model", "info", "prueba", "qwen3:14b")
    check("Tipo" in salida and "vllm" in salida, "F9: la ficha dice el tipo")
    check("fijado a mano" in salida, "F9: y de donde salio")

    preparar(home, config, cache(tipo="ollama", fuente="manual", evidencia="/v1/models"))
    salida = run_cap(home, config, "model", "info", "prueba", "qwen3:14b")
    check("no contesta a /api/tags" in salida,
          "F9: avisa cuando el tipo no cuadra con lo que responde el servidor")
    check("ocm cache type prueba auto" in salida,
          "F9: y propone la salida")


# ------------------------------------------------------------------ F10 wizard --
def scenario_configure_tipo(home: Path, config: Path):
    """El asistente de provider pregunta el tipo y eso no cambia el config."""
    print("\n=== F10: el tipo en ocm configure ===")
    preparar(home, config, cache(tipo="vllm"))
    antes = config.read_bytes()

    #  nombre | url | apiKey | tipo (2 = Ollama) | estilo SDK | modelo | poda
    feed("", "", "", "2", "1", "", "")
    run(home, config, "configure", "prueba", "--no-rescan", "--no-prune")

    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check(entrada["provider_type"] == "ollama", "F10: elegir el tipo en el asistente lo guarda")
    check(entrada.get("type_source") == "manual", "F10: queda como fijado a mano")
    check(config.read_bytes() == antes, "F10: cambiar el tipo no escribe en opencode.json")

    # por flag, sin preguntar
    preparar(home, config, cache(tipo="ollama"))
    feed("", "", "", "", "")
    run(home, config, "configure", "prueba", "--type", "vllm",
        "--no-rescan", "--no-api-style", "--no-prune")
    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check(entrada["provider_type"] == "vllm", "F10: --type en configure fija el tipo")
    check(entrada.get("type_source") == "manual", "F10: --type en configure marca manual")

    # 'auto' lo deja en manos del proximo escaneo
    preparar(home, config, cache(tipo="ollama", fuente="manual"))
    feed("", "", "", "")
    run(home, config, "configure", "prueba", "--type", "auto",
        "--no-rescan", "--no-api-style", "--no-prune")
    entrada = read(home / "provider_cache.json")["providers"]["prueba"]
    check("provider_type" not in entrada and "type_source" not in entrada,
          "F10: --type auto limpia para que detecte el escaneo")


def main_tests():
    escenarios = [
        ("detectar tipo", scenario_detecta),
        ("autocorreccion", scenario_autocorreccion),
        ("pin manual", scenario_pin_manual),
        ("servidor caido", scenario_caido),
        ("flag --type", scenario_flag_type),
        ("alias", scenario_alias),
        ("forma", scenario_forma),
        ("cache type", scenario_cache_type),
        ("ficha", scenario_ficha),
        ("configure tipo", scenario_configure_tipo),
    ]
    for nombre, fn in escenarios:
        home = Path(tempfile.mkdtemp(prefix="ocm-test-f-"))
        print(f"\n=== escenario: {nombre} ===")
        try:
            fn(home, home / "opencode.json")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    print("\n=== escenario: url para el config ===")
    scenario_url_para_config()

    fallidos = [etiqueta for ok, etiqueta in CHECKS if not ok]
    print(f"\n=== {len(CHECKS) - len(fallidos)}/{len(CHECKS)} checks OK ===")
    for etiqueta in fallidos:
        print(" -", etiqueta)
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main_tests())
