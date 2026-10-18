"""
Regresiones de la Fase H: los dos flujos del asistente con autodeteccion.

Ejecutar:  uv run python tests/test_fase_h.py
Salida:    lista de checks + codigo de salida 1 si alguno falla.

Cubre lo que se pidio:
  1. `ocm new` registra el provider, escanea los modelos, los rellena con lo que
     sepa el servidor (o el registro de opencode) y LUEGO pregunta si lo guarda.
  2. Al volver a escanear, ocm se da cuenta de si el motor de inferencia que hay
     detras del provider ya no es el que constaba (ollama -> vllm, llama.cpp...).

Finge el transporte igual que la Fase G (misma clase prestada), asi que aqui tampoco
se toca la red: los servidores falsos contestan lo que pone en cada prueba.
"""

import io
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import entorno  # noqa: E402
from opencode_config_manager import deteccion  # noqa: E402
from test_fase_g import (CHECKS, ServidorFalso, check,  # noqa: E402
                        modelos_ollama, modelos_vllm, read, run, run_cap, write_json)

URL = "http://127.0.0.1:59999"
SCHEMA = "https://opencode.ai/config.json"


def feed(*answers):
    sys.stdin = io.StringIO("\n".join(answers) + "\n")


def cache_local(modelos, extra=None):
    entrada = {
        "uid": "aabbccdd",
        "name": "Local",
        "provider_type": "ollama",
        "baseUrl": URL,
        "reachable": True,
        "last_scan": 1700000000,
        "models": modelos,
    }
    if extra:
        entrada.update(extra)
    return {"cache_version": 2, "cache_timestamp": 1700000000,
            "providers": {"local": entrada}}


def preparar(home, config, modelos=None, extra=None, con_registro=None):
    """Cache y config de partida, con el registro de opencode que se quiera probar."""
    write_json(home / "provider_cache.json",
               cache_local(modelos if modelos is not None else {"blando:1b": {"name": "blando:1b"}},
                           extra))
    write_json(config, {"$schema": SCHEMA, "provider": {}})
    entorno.sin_registro_models_dev()
    if con_registro is not None:
        ruta = home / "models.json"
        write_json(ruta, con_registro)
        deteccion.RUTA_REGISTRO = str(ruta)
        deteccion._INDICE.clear()
        deteccion._AVISO_REGISTRO = None


def servidor_ollama():
    """Un ollama del monton: /api/tags con detalles y capacidades, /v1/models con contexto."""
    return ServidorFalso(gets={
        "/api/tags": modelos_ollama(
            "blando:1b",
            details={"format": "gguf", "quantization_level": "Q4_K_M",
                     "size_parameter": "1B"},
            capabilities=["completion", "vision", "tools"]),
        "/v1/models": modelos_vllm("blando:1b", owned_by="ollama", max_model_len=131072),
    })


def servidor_vllm():
    """El mismo puerto, pero detras hay vLLM: solo contesta a /v1/models."""
    return ServidorFalso(gets={
        "/v1/models": modelos_vllm("blando:1b", owned_by="vllm", max_model_len=131072),
    })


REGISTRO_BLANDO = {"providers": {"cualquiera": {"models": {"blando:1b": {
    "limit": {"context": 262144, "output": 16384},
    "reasoning": True,
}}}}}


# ------------------------------------------------------------------ ocm new --
def scenario_new_apply(home: Path, config: Path):
    """Registrar el provider: escanea, rellena solo y pregunta una vez."""
    print("\n=== H1: ocm new aplica lo detectado y pide confirmacion ===")
    preparar(home, config, modelos={}, con_registro=REGISTRO_BLANDO)
    servidor = servidor_ollama()
    servidor.instalar()
    try:
        # nombre | visible | URL | api key | personalizar | guardar | repasar | opencode.json
        feed("estereo", "", URL, "", "n", "y", "n", "y")
        salida = run_cap(home, config, "new")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()

    cache = read(home / "provider_cache.json")
    proveedor = cache["providers"].get("estereo") or {}
    modelo = (proveedor.get("models") or {}).get("blando:1b") or {}

    check("Que sabe el servidor" in salida,
          "H1: al crear el provider se pregunta al servidor")
    check("Detectadas" in salida and "¿Guardar lo detectado" in salida,
          "H1: enseña la propuesta y pregunta una sola vez")
    check("Guardadas" in salida, "H1: al decirle que si, la guarda")
    check(modelo.get("limit", {}).get("context") == 131072,
          "H1: el contexto que da el servidor queda en la cache")
    check("image" in (modelo.get("modalities") or {}).get("input", []),
          "H1: la vision que anuncio el servidor queda registrada")
    check(modelo.get("tool_call") is True, "H1: tool calling detectado")
    check(modelo.get("reasoning") is True,
          "H1: lo que solo sabe el registro de opencode tambien entra")
    check(isinstance(modelo.get("opciones_fuente"), dict) and bool(modelo["opciones_fuente"]),
          "H1: y cada valor queda con su procedencia")
    check(proveedor.get("servidor") == "ollama",
          "H1: el provider nace ya con su motor apuntado")
    check("Motor: ollama" in salida, "H1: y lo dice al crearlo")

    conf = read(config)
    entrada = conf["provider"]["estereo"]["models"]["blando:1b"]
    check(entrada.get("limit", {}).get("context") == 131072,
          "H1: tras el si, las opciones llegan a opencode.json")
    check("opciones_fuente" not in entrada and "servidor" not in conf["provider"]["estereo"],
          "H1: lo que es solo de ocm no sale en opencode.json")


def scenario_new_refuse(home: Path, config: Path):
    """Si se dice que no, el provider se crea igual, sin opciones."""
    print("\n=== H2: decir que no no rompe nada ===")
    preparar(home, config, modelos={}, con_registro=REGISTRO_BLANDO)
    servidor = servidor_ollama()
    servidor.instalar()
    try:
        feed("estereo", "", URL, "", "n", "n", "n", "n")
        salida = run_cap(home, config, "new")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()

    cache = read(home / "provider_cache.json")
    proveedor = cache["providers"].get("estereo") or {}
    modelo = (proveedor.get("models") or {}).get("blando:1b") or {}

    check("¿Guardar lo detectado" in salida, "H2: pregunta antes de escribir")
    check("Se deja como estaba" in salida, "H2: y respeta la negativa")
    check("opciones_fuente" not in modelo,
          "H2: sin confirmacion no se guarda ni una opcion")
    check("Guardadas" not in salida, "H2: y no se escribe a escondidas")
    check(modelo.get("name") == "blando:1b",
          "H2: el provider y el modelo se crean igual")
    check("estereo" not in read(config).get("provider", {}),
          "H2: negarse a escribir deja opencode.json intacto")


def scenario_new_silencioso(home: Path, config: Path):
    """Cuando el servidor no suelta prenda, no se gasta ni una pregunta de mas."""
    print("\n=== H3: servidor mudo, cero preguntas de mas ===")
    preparar(home, config, modelos={}, con_registro={"providers": {}})
    servidor = ServidorFalso(gets={"/api/tags": modelos_ollama("blando:1b")})
    servidor.instalar()
    try:
        # nombre | visible | URL | api key | personalizar | opencode.json
        feed("estereo", "", URL, "", "n", "n")
        salida = run_cap(home, config, "new")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()

    check("Que sabe el servidor" in salida, "H3: lo intenta igualmente")
    check("no ha aportado nada" in salida, "H3: dice que no ha podido averiguar nada")
    check("¿Guardar lo detectado" not in salida,
          "H3: y no pregunta si no hay nada que guardar")
    cache = read(home / "provider_cache.json")
    check("estereo" in cache["providers"], "H3: el provider se crea igual")


def scenario_new_sin_detectar(home: Path, config: Path):
    """--no-detectar deja el asistente como estaba antes de la deteccion."""
    print("\n=== H4: --no-detectar ===")
    preparar(home, config, modelos={}, con_registro=REGISTRO_BLANDO)
    servidor = servidor_ollama()
    servidor.instalar()
    try:
        feed("estereo", "", URL, "", "n", "n", "n")
        salida = run_cap(home, config, "new", "--no-detectar")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()

    check("Que sabe el servidor" not in salida,
          "H4: con --no-detectar no se consulta al servidor")
    cache = read(home / "provider_cache.json")
    modelo = cache["providers"]["estereo"]["models"].get("blando:1b") or {}
    check("opciones_fuente" not in modelo,
          "H4: y no se rellena nada por detras")
    check("estereo" in read(home / "provider_cache.json")["providers"],
          "H4: el provider se crea normal")


# ----------------------------------------------------- el motor de inferencia --
def scenario_motor_cambia(home: Path, config: Path):
    """Cambiar el servidor detras del mismo provider se nota y se cuenta."""
    print("\n=== H5: detectar el cambio de motor ===")
    preparar(home, config, modelos={"blando:1b": {"name": "Blando"}},
             extra={"servidor": "ollama",
                    "servidor_evidencia": "details={'quantization_level': 'Q4_K_M'}"})
    servidor = servidor_vllm()
    servidor.instalar()
    try:
        salida = run_cap(home, config, "cache", "update", "local")
    finally:
        servidor.restaurar()

    cache = read(home / "provider_cache.json")["providers"]["local"]
    check("el motor parece otro" in salida,
          "H5: avisa cuando el motor ya no es el que constaba")
    check("ollama" in salida and "vllm" in salida,
          "H5: dice el que constaba y el que responde ahora")
    check(cache.get("servidor") == "vllm", "H5: la cache se queda con el motor nuevo")
    check(cache.get("servidor_anterior") == "ollama",
          "H5: y guardan constancia del anterior, para poder revisarlo")
    check("vllm" in str(cache.get("servidor_evidencia", "")),
          "H5: con la prueba de donde lo ha sacado")

    # Repetir el escaneo: mismo motor, ya no molesta dos veces
    servidor = servidor_vllm()
    servidor.instalar()
    try:
        salida = run_cap(home, config, "cache", "update", "local")
    finally:
        servidor.restaurar()
    check("el motor parece otro" not in salida,
          "H5: si el motor no cambia, no se vuelve a avisar")
    cache = read(home / "provider_cache.json")["providers"]["local"]
    check("servidor_anterior" not in cache,
          "H5: confirmado dos veces, la nota de cambio se retira")


def scenario_motor_ollama(home: Path, config: Path):
    """Un ollama del monton se reconoce solo, por la forma de /api/tags."""
    print("\n=== H6: reconocer ollama y contarlo ===")
    preparar(home, config, modelos={"blando:1b": {"name": "Blando"}})
    servidor = servidor_ollama()
    servidor.instalar()
    try:
        salida = run_cap(home, config, "cache", "update", "local")
    finally:
        servidor.restaurar()

    cache = read(home / "provider_cache.json")["providers"]["local"]
    check(cache.get("servidor") == "ollama",
          "H6: ollama se identifica sin que nadie lo diga")
    check("Motor: ollama" in salida, "H6: y lo dice al escanear")
    check("quantization_level" in str(cache.get("servidor_evidencia", "")),
          "H6: con la pista concreta que lo delata")

    salida = run_cap(home, config, "model", "info", "local", "blando:1b")
    check("Motor" in salida and "ollama" in salida,
          "H6: la ficha cuenta que motor hay detras")


def scenario_motor_ficha(home: Path, config: Path):
    """La ficha avisa del motor que cambio, para poder revisarlo a mano."""
    print("\n=== H7: la ficha cuenta el cambio de motor ===")
    preparar(home, config, modelos={"blando:1b": {"name": "Blando"}},
             extra={"servidor": "llama.cpp",
                    "servidor_evidencia": "GET /props (modalities)",
                    "servidor_anterior": "ollama"})
    salida = run_cap(home, config, "model", "info", "local", "blando:1b")
    check("llama.cpp" in salida, "H7: la ficha dice el motor actual")
    check("GET /props (modalities)" in salida, "H7: y de donde lo saco")
    check("antes constaba 'ollama'" in salida,
          "H7: y avisa de que hay un cambio sin revisar")


# ---------------------------------------------------------------- configure --
def scenario_configure(home: Path, config: Path):
    """`ocm configure` rellena los modelos sin opciones y deja los ya configurados."""
    print("\n=== H8: ocm configure solo pregunta por quien no tiene opciones ===")
    preparar(home, config, con_registro=REGISTRO_BLANDO, modelos={
        "qwen3:14b": {"name": "Qwen 3 14B", "limit": {"context": 4096},
                       "opciones_detectado_en": 1700000000},
        "blando:1b": {"name": "blando:1b"},
    })
    servidor = ServidorFalso(gets={"/v1/models": {"data": [
        {"id": "qwen3:14b", "object": "model", "owned_by": "vllm", "max_model_len": 131072},
        {"id": "blando:1b", "object": "model", "owned_by": "vllm", "max_model_len": 8192},
    ]}})
    servidor.instalar()
    try:
        # nombre | url | apiKey | tipo | guardar detectado | modelo a repasar
        feed("", "", "", "", "y", "")
        salida = run_cap(home, config, "configure", "local",
                         "--no-rescan", "--no-api-style", "--no-prune")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()

    cache = read(home / "provider_cache.json")["providers"]["local"]["models"]
    propuesta = salida.split("Que sabe el servidor")[-1] if "Que sabe el servidor" in salida else ""
    check("local/blando:1b" in propuesta,
          "H8: el modelo sin opciones si que se propone")
    check("local/qwen3:14b" not in propuesta,
          "H8: el que ya esta configurado no pasa por ahi")
    check(cache["blando:1b"].get("limit", {}).get("context") == 8192,
          "H8: el modelo sin opciones se rellena con lo del servidor")
    check("opciones_fuente" in cache["blando:1b"], "H8: y con su procedencia")
    check(cache["qwen3:14b"]["limit"]["context"] == 4096,
          "H8: el modelo ya configurado queda igual")
    check(cache["qwen3:14b"].get("reasoning") is not True,
          "H8: ni siquiera se le anade lo que decia el registro")


def scenario_merece():
    """La regla de a quien merece preguntarle al servidor."""
    print("\n=== H9: merece_deteccion ===")
    from opencode_config_manager.commands.detect import merece_deteccion

    check(merece_deteccion({"name": "solo nombre"}),
          "H9: un modelo sin opciones si que merece la consulta")
    check(not merece_deteccion({"name": "x", "limit": {"context": 1024}}),
          "H9: uno con contexto, no")
    check(not merece_deteccion({"name": "x", "tool_call": True}),
          "H9: uno con tool calling, no")
    check(not merece_deteccion({"name": "x", "opciones_detectado_en": 1700000000}),
          "H9: y uno al que ya se le pregunto, tampoco")
    check(merece_deteccion({}), "H9: una entrada vacia tambien se consulta")
    check(not merece_deteccion(None), "H9: ni una entrada que no existe")


def scenario_motor_no_viaja(home: Path, config: Path):
    """Los campos del motor se quedan en la cache, nunca en opencode.json."""
    print("\n=== H10: el motor no sale en el config ===")
    preparar(home, config, modelos={"blando:1b": {"name": "Blando",
                                                  "limit": {"context": 131072}}},
             extra={"servidor": "vllm", "servidor_evidencia": "owned_by=vllm",
                    "servidor_desde": 1700000000})
    run(home, config, "update", "local")
    proveedor = read(config)["provider"]["local"]
    check(proveedor["models"]["blando:1b"].get("limit") == {"context": 131072},
          "H10: el modelo se escribe normal")
    check("servidor" not in proveedor and "servidor_evidencia" not in proveedor
          and "servidor_desde" not in proveedor,
          "H10: las cosas de ocm se quedan en la cache")


def scenario_rescan_desactualizado(home: Path, config: Path):
    """`ocm configure` vuelve a mirar el servidor cuando hace tiempo que no se escanea.

    Es la unica forma de que un provider ya configurado se entere del cambio de motor,
    de un contexto mas grande o de un modelo nuevo.
    """
    print("\n=== H11: con la cache vieja se ofrece reescanear ===")
    preparar(home, config, modelos={"blando:1b": {"name": "Blando"}},
             extra={"last_scan": 1700000000})
    servidor = servidor_ollama()
    servidor.instalar()
    try:
        # nombre | url | apiKey | tipo | escanear | guardar detectado | modelo a repasar
        feed("", "", "", "", "y", "y", "")
        salida = run_cap(home, config, "configure", "local", "--no-api-style", "--no-prune")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()
    check("¿Escanear local ahora" in salida, "H11: la cache vieja ofrece un escaneo")
    check("hace mas de 7 dias" in salida, "H11: y dice por que lo ofrece")

    print("\n=== H11b: con el escaneo reciente no pregunta ===")
    preparar(home, config, modelos={"blando:1b": {"name": "Blando"}},
             extra={"last_scan": int(time.time())})
    servidor = servidor_ollama()
    servidor.instalar()
    try:
        feed("", "", "", "", "y", "")
        salida = run_cap(home, config, "configure", "local", "--no-api-style", "--no-prune")
    finally:
        sys.stdin = sys.__stdin__
        servidor.restaurar()
    check("¿Escanear local ahora" not in salida,
          "H11b: escaneado hace poco, no se molesta con el escaneo")


def scenario_parameters():
    """`parameters` de /api/show: ollama lo manda en cadena JSON, otros como objeto."""
    print("\n=== H12: 'parameters' vale en las dos formas ===")
    for bruto, esperado in (("{\"num_ctx\": 32768}", 32768), ({"n_ctx": 8192}, 8192),
                            ('{"n_ctx": 4096}', 4096)):
        d = deteccion.Deteccion()
        deteccion._desde_show({"parameters": bruto}, d, [])
        check(d.valores.get("limit.context") == esperado,
              f"H12: parameters {type(bruto).__name__} -> contexto {esperado}")
        check("(parameters)" in str(d.fuentes.get("limit.context", "")),
              "H12: y la fuente queda clara")
    for basura in ("texto suelto", {"num_ctx": "grande"}, {"num_ctx": 0}, None):
        d = deteccion.Deteccion()
        deteccion._desde_show({"parameters": basura}, d, [])
        check("limit.context" not in d.valores,
              f"H12: con 'parameters' raro ({type(basura).__name__}) no se inventa nada")


def _detectar(entrada):
    servidor = ServidorFalso()
    servidor.instalar()
    try:
        return deteccion.detectar_opciones(URL, None, "m", entrada=entrada, usar_registro=False)
    finally:
        servidor.restaurar()


def scenario_salida_supuesta(home: Path, config: Path):
    """H13: con solo contexto, la salida se propone como suposicion y limit sale completo."""
    print("\n=== H13: limit.output supuesto cuando solo hay contexto ===")
    from opencode_config_manager import model_fields
    for ctx, esperado in ((524288, 32768), (65536, 16384)):
        d = _detectar({"id": "m", "max_model_len": ctx})
        check(d.valores.get("limit.output") == esperado, f"H13: ctx={ctx} -> output {esperado}")
        check(d.es_suposicion("limit.output"), "H13: marcado como suposicion")
        _, avisos = model_fields.serialize_model(
            {"limit": {"context": ctx, "output": d.valores["limit.output"]}})
        check(not avisos, "H13: limit completo no avisa")
    d = _detectar({"id": "m"})
    check("limit.output" not in d.valores, "H13: sin contexto no se inventa salida")


def scenario_nombre_con_provider():
    """H14: el nombre visible por defecto es 'modelo · provider'."""
    print("\n=== H14: nombre visible 'modelo · provider' ===")
    from opencode_config_manager.commands.utils import (build_provider_config,
                                                        merge_provider_config)
    cache = {"name": "chati", "baseUrl": URL,
             "models": {"default": {"name": "default"}, "otro": {"name": "Mi nombre"}}}
    deseado = build_provider_config("chati", cache)
    check(deseado["models"]["default"]["name"] == "default · chati",
          "H14: id sin nombre propio -> 'default · chati'")
    check(deseado["models"]["otro"]["name"] == "Mi nombre", "H14: un nombre elegido se respeta")
    previo = {"models": {"default": {"name": "default"}, "otro": {"name": "A mano"}}}
    fusion, cambios = merge_provider_config(previo, deseado)
    check(fusion["models"]["default"]["name"] == "default · chati",
          "H14: update mejora un nombre que era copia del id")
    check(fusion["models"]["otro"]["name"] == "A mano", "H14: y no pisa uno puesto a mano")
    _, cambios2 = merge_provider_config(fusion, deseado)
    check(not cambios2, "H14: es idempotente")


def scenario_regresiones_limpieza(home: Path, config: Path):
    """H15: bugs corregidos en la limpieza (modalities vacio, etiqueta, update con typo)."""
    print("\n=== H15: regresiones de la limpieza ===")
    from opencode_config_manager.cache_models import normalize_models

    modelos = normalize_models({"m": {"modalities": {}, "limit": {"context": 8}}})
    check("modalities" not in modelos["m"], "H15: 'modalities' vacio no revienta la cache")
    modelos = normalize_models({"m": {"modalities": {"input": ["text", "image"]}}})
    check(modelos["m"]["modalities"] == {"input": ["text", "image"]},
          "H15: 'modalities' con datos se conserva")

    d = deteccion.Deteccion()
    deteccion._desde_entrada({"context_length": 4096}, d, "GET /v1/models", [])
    check(d.fuentes.get("limit.context") == "GET /v1/models (context_length)",
          "H15: la etiqueta dice la clave que dio el contexto")

    preparar(home, config)
    antes = config.read_text(encoding="utf-8")
    salida = run_cap(home, config, "update", "no-existe")
    check("no encontrado" in salida, "H15: update con nombre desconocido da error")
    check(config.read_text(encoding="utf-8") == antes,
          "H15: y no escribe otro provider del mismo tipo")


def main_tests():
    escenarios = [
        ("new rellena y confirma", scenario_new_apply),
        ("new dice que no", scenario_new_refuse),
        ("new servidor mudo", scenario_new_silencioso),
        ("new sin detectar", scenario_new_sin_detectar),
        ("cambio de motor", scenario_motor_cambia),
        ("reconocer ollama", scenario_motor_ollama),
        ("ficha del motor", scenario_motor_ficha),
        ("configure", scenario_configure),
        ("reescaneo por viejo", scenario_rescan_desactualizado),
        ("el motor no viaja", scenario_motor_no_viaja),
        ("salida supuesta", scenario_salida_supuesta),
        ("regresiones de la limpieza", scenario_regresiones_limpieza),
    ]
    for nombre, fn in escenarios:
        home = Path(tempfile.mkdtemp(prefix="ocm-test-h-"))
        print(f"\n=== escenario: {nombre} ===")
        try:
            fn(home, home / "opencode.json")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    scenario_merece()
    scenario_parameters()
    scenario_nombre_con_provider()

    fallidos = [etiqueta for ok, etiqueta in CHECKS if not ok]
    print(f"\n=== {len(CHECKS) - len(fallidos)}/{len(CHECKS)} checks OK ===")
    for etiqueta in fallidos:
        print(" -", etiqueta)
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main_tests())
