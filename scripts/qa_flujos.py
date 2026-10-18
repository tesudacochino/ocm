"""QA de los dos flujos del asistente, end-to-end, contra el codigo real.

Flujo 1: dar de alta un provider (cmd_provider_new) -> escanea, auto-detecta lo que
         sepa el servidor, pregunta una sola vez si lo guarda, y deja repasar a mano.
Flujo 2: reconfigurar (cmd_configure) un provider ya configurado -> el escaneo
         comprueba que no ha cambiado el motor de inferencia.

Se conduce todo por ConfigUI._read_line, el unico punto por el que entra cualquier
respuesta, asi que lo impreso es literalmente el cuestionario que veria el usuario:
vale para ver de un golpe cuantas preguntas hace cada flujo y que contesta Intro.

Ejecutar:  uv run python scripts/qa_flujos.py     (rc 0 si pasan todas)
"""
import json
import pathlib
import shutil
import sys
import tempfile

_RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RAIZ / "src"))
sys.path.insert(0, str(_RAIZ / "tests"))

import entorno  # noqa: E402
from opencode_config_manager.config import Colors, ConfigManager, ConfigUI
from opencode_config_manager.commands.configure import cmd_configure
from opencode_config_manager.commands.provider import cmd_provider_new
from opencode_config_manager.commands.scan import scan_single_provider
from test_fase_g import ServidorFalso, modelos_vllm

CHECKS = []
TRANSCRIPT = []


def check(nombre, cond, detalle=""):
    CHECKS.append((nombre, bool(cond)))
    print(f"  [{'OK' if cond else 'FALLO'}] {nombre}" + ("" if cond else f"  << {detalle}"))


def ollama_local(modelo, ctx=262144):
    """ollama: la lista viene en forma de ollama con sus detalles de modelo."""
    return ServidorFalso(
        gets={"/api/tags": {"models": [{
            "name": modelo, "model": modelo, "size": 1,
            "details": {"quantization_level": "Q4_K_M", "size_parameter": "12B",
                        "parent_model": "ggml-org/" + modelo, "model_file": "x.ggmm"}}]}},
        show={"model_info": {"GGUF.general.name": [modelo], "llama.context_length": ctx},
              "parameters": json.dumps({"type": "llamafile", "num_ctx": ctx, "top_p": 0.9}),
              "metrics": {"prompt_ms": 1, "predicted_ms": 1, "predicted_tokens": 1},
              "license": "",
              "capabilities": {"completion": True, "vision": True, "audio": False,
                               "temperature": 1.0, "top_p": True, "tools": True,
                               "prompt_prefix": False, "insert": False}},
    )


GUION = []


def guion(pares):
    GUION.clear()
    GUION.extend(pares)

    def _read_line(prompt):
        limpio = (prompt.replace(Colors.BOLD, "").replace(Colors.CYAN, "")
                  .replace(Colors.RESET, "").replace(Colors.YELLOW, ""))
        respuesta = ""
        for indice, (clave, valor) in enumerate(GUION):
            if clave in limpio:
                respuesta = valor
                del GUION[indice]
                break
        TRANSCRIPT.append((limpio.strip(), respuesta))
        print(f"  ? {limpio.strip()}" + (f"  >> {respuesta}" if respuesta else "  >> <Intro>"))
        return respuesta

    ConfigUI._read_line = staticmethod(_read_line)


def args_fake(**kw):
    a = type("A", (), {})()
    base = dict(type=None, no_detectar=False, advanced=False, model=None, provider=None,
                no_prune=False, no_rescan=False, no_api_style=False, name=None, url=None,
                api_key=None, uid=None, all=False, apply=False, force=False, probar=False,
                json=False)
    for clave, valor in base.items():
        setattr(a, clave, kw.get(clave, valor))
    return a


URL = "http://127.0.0.1:11434"


def main():
    entorno.sin_registro_models_dev()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ocm_flujos_"))
    (tmp / "providers").mkdir(parents=True, exist_ok=True)
    (tmp / "cache").mkdir(parents=True, exist_ok=True)
    try:
        # ------------------------------------------------------------ FLUJO 1: ocm new
        print("\n=============== FLUJO 1: dar de alta (ocm new) ===============")
        servidor = ollama_local("gemma-4-31b")
        servidor.instalar()
        manager = ConfigManager(config_path=tmp / "providers" / "opencode.json",
                                home_path=tmp / "cache")
        guion([
            ("Nombre del provider", "jilgaro"),
            ("URL base del provider", URL),
            ("¿Guardar lo detectado en la cache", "y"),   # la unica pregunta de deteccion
            ("¿Repasar alguna a mano", "y"),               # y pasamos por el asistente
            ("¿Incluir las opciones avanzadas", "y"),
            ("Es un modelo de razonamiento", "y"),         # thinking: el usuario dice que si
            # "Soporta tool calling" sin respuesta: Intro debe dejar el [si] detectado
            ("Acepta adjuntos", "n"),
            ("Marcar como experimental", "n"),
            ("¿Actualizar opencode.json ahora", "y"),
        ])
        cmd_provider_new(manager, args_fake())
        servidor.restaurar()

        cfg = json.loads((tmp / "providers" / "opencode.json").read_text(encoding="utf-8"))
        cache = json.loads((tmp / "cache" / "provider_cache.json").read_text(encoding="utf-8"))
        entry = cache["providers"]["jilgaro"]
        modelo = entry["models"]["gemma-4-31b"]
        modelos_escritos = cfg["provider"]["jilgaro"]["models"]
        check("alta: un unico modelo escrito, con su id como clave",
              list(modelos_escritos) == ["gemma-4-31b"], str(list(modelos_escritos)))
        escrito = modelos_escritos["gemma-4-31b"]

        print("\n--- entrada de cache del modelo ---")
        print(json.dumps(modelo, ensure_ascii=False, indent=2))
        print("--- lo que se ha escrito en opencode.json ---")
        print(json.dumps(cfg["provider"]["jilgaro"], ensure_ascii=False, indent=2))

        check("alta: tipo auto-detectado como ollama", entry["provider_type"] == "ollama"
              and entry.get("type_source") == "auto", str(entry))
        check("alta: motor ollama apuntado desde el alta", entry.get("servidor") == "ollama",
              str(entry.get("servidor")))
        check("alta: contexto auto-detectado del servidor",
              modelo["limit"]["context"] == 262144, str(modelo["limit"]))
        check("alta: vision auto-detectada",
              modelo["modalities"]["input"] == ["text", "image"], str(modelo["modalities"]))
        check("alta: Intro en tool calling conserva el 'si' detectado",
              escrito["tool_call"] is True, str(escrito))
        check("alta: thinking a 'si' por respuesta del usuario",
              escrito.get("reasoning") is True, str(escrito))
        check("alta: adjuntos y experimental a 'no'",
              escrito.get("attachment") is False
              and escrito.get("experimental") is False, str(escrito))
        check("alta: temperature no se inventa, el asistente dejo el default",
              "temperature" not in escrito, str(escrito))
        check("alta: ninguna clave intermedia 'options' en el modelo",
              "options" not in escrito, str(sorted(escrito)))
        check("alta: cada valor auto-detectado lleva su procedencia",
              "api/show" in modelo.get("opciones_fuente", {}).get("tool_call", ""),
              str(modelo.get("opciones_fuente")))
        check("alta: opencode.json con npm, baseURL y nombres visibles",
              cfg["provider"]["jilgaro"]["npm"] == "@ai-sdk/openai-compatible"
              and cfg["provider"]["jilgaro"]["options"]["baseURL"] == URL + "/v1"
              and cfg["provider"]["jilgaro"]["name"] == "Jilgaro"
              and escrito["name"] == "gemma-4-31b", str(cfg["provider"]["jilgaro"]))
        check("alta: a opencode no le llega ninguna clave nuestra",
              set(escrito) <= {"name", "limit", "modalities", "options", "temperature",
                               "interleaved", "tool_call", "attachment", "reasoning",
                               "experimental", "status"}, str(sorted(escrito)))
        check("alta: una sola pregunta para confirmar la deteccion",
              sum(1 for p, _ in TRANSCRIPT if "detectado en la cache" in p) == 1,
              str([p for p, _ in TRANSCRIPT]))

        # ------------------------------------------------------ segunda alta: no pregunta
        print("\n--- segunda pasada sobre el provider ya configurado ---")
        TRANSCRIPT.clear()
        servidor = ollama_local("gemma-4-31b")
        servidor.instalar()
        guion([
            ("Nombre del provider", "jilgaro"),
            ("¿Continuar y reconfigurar", "y"),
            ("URL base del provider", URL),
            ("¿Actualizar opencode.json ahora", "n"),
        ])
        cmd_provider_new(manager, args_fake())
        servidor.restaurar()
        check("alta repetida: no vuelve a preguntar si guarda lo detectado",
              not [p for p, _ in TRANSCRIPT if "detectado en la cache" in p],
              str([p for p, _ in TRANSCRIPT]))
        check("alta repetida: el repaso a mano se ofrece pero Intro lo cierra",
              any("Repasar alguna a mano" in p for p, _ in TRANSCRIPT)
              and not any("Tokens de contexto" in p for p, _ in TRANSCRIPT),
              str([p for p, _ in TRANSCRIPT]))

        # ------------------------------------------------------------ FLUJO 2: configure
        print("\n============ FLUJO 2: reconfigurar (ocm configure) ============")
        # Detras de la misma URL aparece otro motor (vLLM) y hay un modelo de la cache
        # que nunca se ha configurado.
        servidor = ServidorFalso(
            gets={"/v1/models": modelos_vllm("gemma-4-31b", max_model_len=1048576)},
            show=None)
        servidor.llamados.clear()
        # el modelo nuevo, anadido a mano en la cache como si viniera de un escaneo viejo
        cache["providers"]["jilgaro"]["models"]["qwen-32b"] = {"name": "qwen-32b"}
        cache["providers"]["jilgaro"]["last_scan"] = 0        # para que ofrezca reescanear
        (tmp / "cache" / "provider_cache.json").write_text(
            json.dumps(cache, ensure_ascii=False), encoding="utf-8")

        # el escaneo tiene que ver los dos modelos
        servidor.gets["/v1/models"]["data"].append(
            {"id": "qwen-32b", "object": "model", "owned_by": "vllm",
             "max_model_len": 1048576, "root": "/modelos/qwen-32b"})
        servidor.instalar()
        guion([
            ("¿Escanear jilgaro ahora", "y"),
            ("¿Guardar lo detectado en la cache", "y"),
            ("Modelo a repasar", ""),
            ("¿Quitarlos de opencode.json", "n"),
        ])
        manager2 = ConfigManager(config_path=tmp / "providers" / "opencode.json",
                                 home_path=tmp / "cache")
        TRANSCRIPT.clear()
        cmd_configure(manager2, args_fake(provider="jilgaro"))
        servidor.restaurar()

        cache = json.loads((tmp / "cache" / "provider_cache.json").read_text(encoding="utf-8"))
        entry = cache["providers"]["jilgaro"]
        nuevo = entry["models"]["qwen-32b"]
        vieja = entry["models"]["gemma-4-31b"]
        print("\n--- provider en caché tras reconfigurar ---")
        print(json.dumps({k: v for k, v in entry.items() if k != "models"},
                         ensure_ascii=False, indent=2))
        print("qwen-32b:", json.dumps(nuevo, ensure_ascii=False))
        print("gemma-4-31b opciones:", json.dumps(
            {k: v for k, v in vieja.items() if not k.startswith("opciones_")},
            ensure_ascii=False))

        check("configure: el escaneo ve que el motor es ahora vllm",
              entry.get("servidor") == "vllm", str(entry.get("servidor")))
        check("configure: queda constancia del motor anterior",
              entry.get("servidor_anterior") == "ollama", str(entry.get("servidor_anterior")))
        check("configure: sin tipo fijado a mano, el tipo sigue al servidor (vllm)",
              entry.get("provider_type") == "vllm" and entry.get("type_source") == "auto",
              str((entry.get("provider_type"), entry.get("type_source"))))
        check("configure: rellena el modelo sin configurar con lo del servidor",
              nuevo.get("limit", {}).get("context") == 1048576, str(nuevo))
        check("configure: a vLLM no se le inventan modalidades (solo registro)",
              "modalities" not in nuevo, str(nuevo))
        check("configure: no pisa lo ya decidido de gemma",
              vieja["tool_call"] is True and vieja["reasoning"] is True
              and vieja["limit"]["context"] == 262144, str(vieja))
        check("configure: la deteccion se confirma con una sola pregunta",
              sum(1 for p, _ in TRANSCRIPT if "detectado en la cache" in p) == 1,
              str([p for p, _ in TRANSCRIPT]))

        # estabilizar: otro escaneo viendo el mismo motor quita el aviso
        servidor = ServidorFalso(
            gets={"/v1/models": {"data": [
                {"id": "gemma-4-31b", "object": "model", "owned_by": "vllm",
                 "max_model_len": 1048576},
                {"id": "qwen-32b", "object": "model", "owned_by": "vllm",
                 "max_model_len": 1048576}]}})
        servidor.instalar()
        manager2.load_cache()
        scan_single_provider("jilgaro", manager2.cache_data["providers"]["jilgaro"],
                             manager2, manager2.config_data, 0)
        manager2.save_cache(touch=False)
        servidor.restaurar()
        cache = json.loads((tmp / "cache" / "provider_cache.json").read_text(encoding="utf-8"))
        entry = cache["providers"]["jilgaro"]
        check("configure: repetir el escaneo estable retira el aviso de cambio",
              entry.get("servidor") == "vllm" and "servidor_anterior" not in entry,
              str(entry.get("servidor_anterior")))

        # tolerancia del detector con `parameters` de /api/show: ollama lo manda como
        # cadena JSON y algunos servidores compatible como objeto ya hecho.
        from opencode_config_manager import deteccion

        def ctx_desde_show(parameters):
            det = deteccion.Deteccion()
            deteccion._desde_show({"parameters": parameters}, det, [])
            return det.valores.get("limit.context"), det.fuentes.get("limit.context")

        check("detector: 'parameters' en cadena JSON aporta el contexto",
              ctx_desde_show('{"num_ctx": 32768}') [0] == 32768, str(ctx_desde_show("{}")))
        check("detector: 'parameters' como objeto aporta el contexto igual",
              ctx_desde_show({"n_ctx": 8192})[0] == 8192, str(ctx_desde_show({})))
        check("detector: 'parameters' basura no inventa nada",
              ctx_desde_show("no es json")[0] is None
              and ctx_desde_show({"num_ctx": "grande"})[0] is None, str(ctx_desde_show([])))

        # la ficha que ve el usuario
        from opencode_config_manager.commands.model import cmd_model_info

        print("\n--- ficha que ve el usuario (ocm model info) ---")
        manager2.load_cache()
        cmd_model_info(manager2, args_fake(provider="jilgaro", model="qwen-32b"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    fallidos = [n for n, ok in CHECKS if not ok]
    print(f"\n===== {len(CHECKS) - len(fallidos)}/{len(CHECKS)} comprobaciones =====")
    for nombre in fallidos:
        print("  FALLO:", nombre)
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
