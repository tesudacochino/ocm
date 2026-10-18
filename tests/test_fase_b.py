"""
Regresiones de la Fase B: opciones de modelo (contexto, modalidades, capacidades).

Ejecutar:  uv run python tests/test_fase_b.py
Salida:    lista de checks + codigo de salida 1 si alguno falla.

No necesita pytest ni red: trabaja contra una caché y un opencode.json temporales.
"""

import io
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from opencode_config_manager.cli import main  # noqa: E402
from opencode_config_manager.model_fields import (  # noqa: E402
    MODALITIES,
    coerce,
    describe_model,
    format_value,
    parse_int,
    serialize_model,
    set_value,
    spec_for,
)

CHECKS = []


def check(cond, label):
    print(("  OK    " if cond else "  FALLO ") + label)
    CHECKS.append((bool(cond), label))


class captura:
    """Guarda lo que ocm imprime mientras corre el bloque, sin codigos ANSI."""

    def __enter__(self):
        self.buffer = io.StringIO()
        self._anterior = sys.stdout
        sys.stdout = self.buffer
        return self

    def __exit__(self, *exc):
        sys.stdout = self._anterior
        self.texto = re.sub(r"\x1b\[[0-9;]*m", "", self.buffer.getvalue())
        return False


def run(home, config, *argv):
    return main(["--home", str(home), "--config", str(config), *argv])


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- unitarias --
def scenario_parser():
    """Normalizacion y validacion de respuestas."""
    print("\n=== parser y validacion ===")
    check(parse_int("128000") == 128000, "un contexto de 128000 no se convierte en 131072")
    check(parse_int("128k") == 131072, "'128k' se entiende como 131072")
    check(parse_int("1m") == 1048576, "'1m' se entiende como 1048576")
    check(coerce(spec_for("tool_call"), "y") is True, "'y' -> True en un bool")
    check(coerce(spec_for("tool_call"), "no") is False, "'no' -> False en un bool")
    check(coerce(spec_for("modalities.input"), "1,3") == ["text", "image"],
          "las modalidades se eligen por numero")
    check(coerce(spec_for("modalities.input"), "vision") == ["image"],
          "'vision' se normaliza a 'image'")

    entry = {"name": "X", "limit": {"context": 4096, "output": 1024}}
    set_value(entry, "limit.output", None)
    set_value(entry, "limit.context", None)
    check("limit" not in entry, "al quitar los dos campos de limit desaparece el contenedor")

    config_part, warnings = serialize_model({"name": "A", "limit": {"context": 8192}})
    check(config_part["limit"] == {"context": 8192}, "serialize emite limit tal cual")
    check(any("output" in warning for warning in warnings),
          "serialize avisa si falta el output en limit")

    _, clean_warnings = serialize_model({"name": "A", "modalities": {"input": ["text"]}})
    check(not clean_warnings, "sin limit no hay avisos")

    from opencode_config_manager.cache_models import normalize_models

    alias = normalize_models({"m": {"name": "M", "toolcall": True,
                                    "input": ["text"], "output": ["text", "image"]}})["m"]
    check(alias.get("tool_call") is True and "toolcall" not in alias,
          "B5: 'toolcall' se guarda como 'tool_call'")
    check(alias.get("modalities") == {"input": ["text"], "output": ["text", "image"]},
          "B5: 'input'/'output' sueltos pasan a 'modalities'")

    cap = normalize_models([{"id": "c", "capabilities": {"tools": True, "vision": True,
                                                         "input": ["text"]}}])["c"]
    check(cap.get("tool_call") is True and cap.get("modalities", {}).get("input"),
          "B5: el formato 'capabilities' de models.dev se entiende")


# ------------------------------------------------------------ no interactivo --
def scenario_set(home: Path, config: Path):
    """`ocm model options --set` escribe caché y opencode.json."""
    print("\n=== ocm model options --set ===")

    write_json(config, {
        "$schema": "https://opencode.ai/config.json",
        "model": "mole/qwen3:14b",
        "provider": {
            "mole": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Mole Local",
                "options": {"baseURL": "http://127.0.0.1:11434/v1"},
                "models": {
                    "qwen3:14b": {"name": "Qwen 3 14B", "options": {"temperature": 0.2},
                                  "variants": [{"id": "high", "settings": {"reasoningEffort": "high"}}]},
                },
            }
        },
    })
    write_json(home / "provider_cache.json", {
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {
            "mole": {
                "uid": "abcd1234",
                "name": "Mole Local",
                "provider_type": "ollama",
                "baseUrl": "http://127.0.0.1:11434",
                "last_scan": 1700000000,
                "models": {"qwen3:14b": {"name": "Qwen 3 14B"}},
            }
        },
    })

    run(home, config, "model", "options", "mole", "qwen3:14b",
        "--set", "limit.context=131072", "--set", "limit.output=8192",
        "--set", "modalities.input=text,image", "--set", "modalities.output=text",
        "--set", "reasoning=y", "--set", "tool_call=y")

    cache_model = read(home / "provider_cache.json")["providers"]["mole"]["models"]["qwen3:14b"]
    config_model = read(config)["provider"]["mole"]["models"]["qwen3:14b"]

    check(cache_model["limit"] == {"context": 131072, "output": 8192},
          "B2: el limit se guarda en la cache")
    check(cache_model["modalities"]["input"] == ["text", "image"],
          "B2: las modalidades se guardan en la cache")
    check(config_model["limit"]["context"] == 131072, "B2: limit llega a opencode.json")
    check(config_model["modalities"]["input"] == ["text", "image"],
          "B2: modalities llegan a opencode.json")
    check(config_model["reasoning"] is True and config_model["tool_call"] is True,
          "B2: capacidades (reasoning/tool_call) escritas")
    check(config_model["options"] == {"temperature": 0.2},
          "B1: las claves ajenas del modelo (options) se conservan")
    check(len(config_model["variants"]) == 1, "B1: los variants escritos a mano se conservan")
    check(config_model["name"] == "Qwen 3 14B", "B2: el nombre visible no se pierde")

    # Respuesta invalida: no rompe y no escribe
    before = read(config)
    run(home, config, "model", "options", "mole", "qwen3:14b", "--set", "limit.context=grande")
    check(read(config) == before, "B1: un valor invalido no cambia opencode.json")

    before_cache = read(home / "provider_cache.json")
    run(home, config, "model", "options", "mole", "no-existe", "--set", "reasoning=y")
    check(read(home / "provider_cache.json") == before_cache,
          "B1: un modelo inexistente no toca la cache")

    # Quitar una opcion gestionada la elimina tambien del config
    run(home, config, "model", "options", "mole", "qwen3:14b", "--set", "reasoning=-")
    model = read(config)["provider"]["mole"]["models"]["qwen3:14b"]
    check("reasoning" not in model, "B2: '-' quita la opcion de opencode.json")
    check(model.get("options") == {"temperature": 0.2},
          "B2: quitar una opcion propia no borra las ajenas")


# --------------------------------------------------------------- interactivo --
def scenario_wizard(home: Path, config: Path):
    """El asistente pregunta una a una mostrando el valor actual."""
    print("\n=== asistente interactivo ===")

    write_json(config, {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "chati": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Chati",
                "options": {"baseURL": "http://chati:11434/v1"},
                "models": {"default": {"name": "default"}},
            }
        },
    })
    write_json(home / "provider_cache.json", {
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {
            "chati": {
                "uid": "ffff0000",
                "name": "Chati",
                "provider_type": "vllm",
                "baseUrl": "http://chati:11434",
                "last_scan": 1700000000,
                "models": {"default": {"name": "default", "limit": {"context": 128000,
                                                                    "output": 8192},
                                       "modalities": {"input": ["text"], "output": ["text"]},
                                       "reasoning": True, "tool_call": True}},
            }
        },
    })

    #  name | limit.context | limit.output | modalities.input | modalities.output | reasoning | tool_call
    sys.stdin = io.StringIO("\n".join([
        "",            # name: Intro -> mantiene 'default'
        "256000",      # context: nuevo valor plano (no se 'snapea' a 262144)
        "",            # output: Intro -> mantiene 8192
        "1,3",         # input: por numero -> text,image
        "",            # output modalidades: mantiene
        "?",           # ayuda del campo reasoning
        "-",           # y luego lo quita
        "quizas",      # respuesta invalida para tool_call...
        "n",           # ...y su correccion
    ]) + "\n")

    run(home, config, "model", "options", "chati", "default")

    cache_model = read(home / "provider_cache.json")["providers"]["chati"]["models"]["default"]
    config_model = read(config)["provider"]["chati"]["models"]["default"]

    check(cache_model["name"] == "default", "B3: Intro mantiene el valor actual")
    check(cache_model["limit"]["context"] == 256000, "B3: un valor nuevo reemplaza el anterior")
    check(cache_model["limit"]["output"] == 8192, "B3: lo que no se toca sigue igual")
    check(cache_model["modalities"]["input"] == ["text", "image"],
          "B3: modalidades por numero ('1,3' = text,image)")
    check("reasoning" not in cache_model, "B3: '-' quita la opcion de la cache")
    check(cache_model["tool_call"] is False, "B3: se re-pregunta tras una respuesta invalida")
    check(config_model["limit"]["context"] == 256000, "B3: el config refleja el cambio")
    check("reasoning" not in config_model, "B3: el config refleja el borrado")

    # 's' sale del asistente dejando lo ya cambiado
    sys.stdin = io.StringIO("\n".join(["Super Chat", "s"]) + "\n")
    run(home, config, "model", "options", "chati", "default")
    cache_model = read(home / "provider_cache.json")["providers"]["chati"]["models"]["default"]
    check(cache_model["name"] == "Super Chat", "B3: los cambios previos a 's' se guardan")
    check(read(config)["provider"]["chati"]["models"]["default"]["name"] == "Super Chat",
          "B3: el rename inmediato llega a opencode.json")

    # Configurar todos los modelos de golpe
    cache = read(home / "provider_cache.json")
    cache["providers"]["chati"]["models"]["otro"] = {"name": "otro"}
    write_json(home / "provider_cache.json", cache)
    # 's' se salta el resto del primer modelo; el segundo se configura entero
    sys.stdin = io.StringIO("\n".join(["s",
                                       "", "4096", "2048", "1", "1", "n", "n",
                                       "n", "n", "n", "active"]) + "\n")
    run(home, config, "model", "options", "chati", "--all", "--advanced")
    other = read(home / "provider_cache.json")["providers"]["chati"]["models"]["otro"]
    check(other["limit"] == {"context": 4096, "output": 2048}, "B3: --all recorre todos los modelos")


# ------------------------------------------------------------------ provider --
def scenario_api_style(home: Path, config: Path):
    """`ocm new` para un provider estilo OpenAI deja elegir el SDK."""
    print("\n=== estilo de API (npm) ===")

    write_json(config, {"$schema": "https://opencode.ai/config.json", "provider": {}})
    write_json(home / "provider_cache.json", {"cache_version": 2, "providers": {}})

    from opencode_config_manager import api

    def fake_scan_vllm(base_url, api_key=None):
        return api.ScanResult(success=True, models=["mi-modelo"])

    def fake_scan_ollama(base_url, api_key=None):
        return api.ScanResult(success=False, models=[], error="no es ollama")

    original_vllm, original_ollama = api.ProviderScanner.scan_vllm, api.ProviderScanner.scan_ollama
    api.ProviderScanner.scan_vllm = staticmethod(fake_scan_vllm)
    api.ProviderScanner.scan_ollama = staticmethod(fake_scan_ollama)
    try:
        #  nombre | visible | url | apiKey | personalizar? | estilo API | opciones? | actualizar?
        sys.stdin = io.StringIO("\n".join([
            "brain", "Cerebro Local", "http://127.0.0.1:8080", "",
            "n",   # no personalizar nombres
            "2",   # OpenAI responses API
            "n",   # no opciones de modelo
            "y",   # actualizar opencode.json
        ]) + "\n")
        run(home, config, "new")
    finally:
        api.ProviderScanner.scan_vllm, api.ProviderScanner.scan_ollama = original_vllm, original_ollama

    entry = read(home / "provider_cache.json")["providers"]["brain"]
    provider = read(config)["provider"]["brain"]
    check(entry.get("npm") == "@ai-sdk/openai", "B4: el estilo de API elegido se guarda en cache")
    check(provider.get("npm") == "@ai-sdk/openai",
          "B4: 'ocm update' escribe el paquete elegido en opencode.json")
    check(provider.get("name") == "Cerebro Local", "B4: el nombre visible del provider se escribe")
    check(provider["models"]["mi-modelo"]["name"] == "mi-modelo",
          "B4: los modelos detectados quedan con su nombre")
    check(entry.get("provider_type") == "vllm", "B4: tipo de provider detectado")


def scenario_adoption(home: Path, config: Path):
    """Lo escrito a mano en opencode.json se adopta y no se pierde."""
    print("\n=== adopcion desde opencode.json ===")

    write_json(config, {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "chati": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Chati",
                "options": {"baseURL": "http://chati:11434/v1"},
                "models": {
                    "default": {
                        "name": "Chati Default",
                        "limit": {"context": 128000, "output": 8192},
                        "modalities": {"input": ["text", "image"], "output": ["text"]},
                        "tool_call": True,
                    }
                },
            }
        },
    })
    # La caché viene del escaneo: solo sabe el id del modelo
    write_json(home / "provider_cache.json", {
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {
            "chati": {
                "uid": "eeee1111",
                "name": "Chati",
                "provider_type": "vllm",
                "baseUrl": "http://chati:11434",
                "last_scan": 1700000000,
                "models": {"default": {"name": "default"}},
            }
        },
    })

    run(home, config, "model", "options", "chati", "default", "--set", "reasoning=y")

    cache = read(home / "provider_cache.json")
    cache_model = cache["providers"]["chati"]["models"]["default"]
    config_model = read(config)["provider"]["chati"]["models"]["default"]

    check(cache_model["modalities"] == {"input": ["text", "image"], "output": ["text"]},
          "B5: las modalities escritas a mano se adoptan a la cache")
    check(cache_model["limit"] == {"context": 128000, "output": 8192},
          "B5: el limit del config llega a la cache sin alterar")
    check(cache_model["name"] == "Chati Default",
          "B5: un nombre puesto a mano en el config se adopta")
    check(config_model["modalities"] == {"input": ["text", "image"], "output": ["text"]},
          "B5: escribir una opcion propia no borra las que no se tocaron")
    check(config_model["limit"] == {"context": 128000, "output": 8192},
          "B5: limit sigue intacto (128000 no se convirtio en 131072)")
    check(config_model.get("reasoning") is True, "B5: solo se escribe la clave cambiada")
    check(cache["cache_timestamp"] == 1700000000,
          "B5: cambiar opciones no mueve la fecha del ultimo escaneo")

    run(home, config, "model", "options", "chati", "default", "--set", "reasoning=-")
    config_model = read(config)["provider"]["chati"]["models"]["default"]
    check("reasoning" not in config_model, "B5: '-' si borra la opcion que el usuario quito")
    check("modalities" in config_model, "B5: y no arrastra nada al hacerlo")


# ------------------------------------------------------------------- prompts --
def scenario_prompts(home: Path, config: Path):
    """Los prompts enseñan lo que opencode asume cuando no hay nada guardado."""
    print("\n=== prompts con valores efectivos ===")

    from opencode_config_manager.commands.options import _field_hint

    # El caso del provider recien escaneado: ni la cache ni el config traen opciones
    write_json(config, {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "chati": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Chati",
                "options": {"baseURL": "http://chati:11434/v1"},
                "models": {"default": {"name": "default"}},
            }
        },
    })
    write_json(home / "provider_cache.json", {
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {
            "chati": {
                "uid": "dddd2222",
                "name": "Chati",
                "provider_type": "vllm",
                "baseUrl": "http://chati:11434",
                "last_scan": 1700000000,
                "models": {"default": {"name": "default"}},
            }
        },
    })

    mapa = _field_hint(spec_for("modalities.input"))
    for indice, valor in enumerate(MODALITIES, start=1):
        check(f"{indice}={valor}" in mapa, f"B6: el prompt dice que {indice} es '{valor}'")
        check(coerce(spec_for("modalities.input"), str(indice)) == [valor],
              f"B6: responder {indice} guarda '{valor}'")

    check(format_value(spec_for("reasoning"), None) == "por defecto: no",
          "B6: un bool sin valor muestra lo que opencode asume")
    check(format_value(spec_for("reasoning"), False) == "no",
          "B6: un 'no' guardado se muestra sin el 'por defecto'")
    check(format_value(spec_for("tool_call"), True) == "si",
          "B6: un bool guardado a true se muestra 'si'")
    check(format_value(spec_for("modalities.input"), None) == "por defecto: text",
          "B6: las modalidades vacias muestran 'text'")
    check(format_value(spec_for("modalities.input"), ["text", "image"]) == "text,image",
          "B6: las modalidades guardadas se muestran tal cual")
    check(format_value(spec_for("limit.context"), None) == "sin definir",
          "B6: un entero sin valor dice 'sin definir', no inventa uno")
    check(format_value(spec_for("status"), None) == "por defecto: active",
          "B6: el estado vacio muestra 'active'")

    resumen = describe_model({"limit": {"context": 131072, "output": 8192},
                               "modalities": {"input": ["text", "image"], "output": ["text"]},
                               "tool_call": True})
    check("out~=" not in resumen, "B6: el resumen de una linea ya no usa 'out~='")
    check("ctx=131072" in resumen and "out_max=8192" in resumen
          and "in=text,image" in resumen and "out=text" in resumen,
          f"B6: ctx / out_max / in / out sin solaparse -> {resumen.strip()}")
    check(describe_model({"modalities": {"output": "text"}}) == "  (out=text)",
          "B6: unas modalidades escritas a mano como texto se resumen bien")

    # Intro en todo: no cambia nada y no escribe nada
    config_antes = config.read_text(encoding="utf-8")
    cache_antes = read(home / "provider_cache.json")
    sys.stdin = io.StringIO("\n" * 10)
    with captura() as cap:
        rc = run(home, config, "model", "options", "chati", "default")
    check(rc == 0, "B6: el asistente termina bien dando Intro en todo")

    texto = cap.texto
    for esperado in (
        "Tokens de contexto (entrada) [sin definir]",
        "Entradas que acepta [por defecto: text]",
        "Salidas que produce [por defecto: text]",
        "Es un modelo de razonamiento (thinking) [por defecto: no]",
        "Soporta tool calling [por defecto: no]",
        "1=text, 2=audio, 3=image, 4=video, 5=pdf",
        "Sin opciones guardadas",
        "sin cambios",
    ):
        check(esperado in texto, f"B6: el asistente muestra '{esperado}'")

    check(config.read_text(encoding="utf-8") == config_antes,
          "B6: Intro en todo no toca opencode.json")
    check(read(home / "provider_cache.json") == cache_antes,
          "B6: Intro en todo no ensucia la cache")

    # Responder: name | context | output | in | out | reasoning | tool_call
    # (limit.output aparece cuando el contexto deja de estar vacio)
    sys.stdin = io.StringIO("\n".join(["", "8192", "", "1,3", "1", "y", "y"]) + "\n")
    with captura() as cap2:
        run(home, config, "model", "options", "chati", "default")

    guardado = read(home / "provider_cache.json")["providers"]["chati"]["models"]["default"]
    check(guardado["limit"]["context"] == 8192, "B6: el contexto respondido queda en la cache")
    check(guardado["modalities"] == {"input": ["text", "image"], "output": ["text"]},
          "B6: las modalidades respondidas quedan en la cache")
    check(guardado.get("reasoning") is True and guardado.get("tool_call") is True,
          "B6: los bools respondidos quedan en la cache")
    check("out~=" not in cap2.texto and "out=text" in cap2.texto,
          "B6: la linea de resumen que ve el usuario dice 'out=text'")
    check("deberia incluir" in cap2.texto,
          "B6: avisa de que limit pedia context y output juntos")
    config_model = read(config)["provider"]["chati"]["models"]["default"]
    check(config_model["limit"] == {"context": 8192}
          and config_model["modalities"]["input"] == ["text", "image"]
          and config_model["tool_call"] is True,
          "B6: lo respondido llega a opencode.json")


# -------------------------------------------------------------------- ficha --
def scenario_info(home, config):
    """'ocm model info': ficha en claro, de solo lectura."""
    print("\n=== ocm model info ===")
    cache_path = home / "provider_cache.json"

    write_json(config, {
        "$schema": "https://opencode.ai/config.json",
        "model": "tok/bueno",
        "provider": {
            "tok": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Tok",
                "options": {"baseURL": "http://127.0.0.1:3000/v1", "apiKey": "sk-secreto-9999"},
                "models": {
                    "bueno": {"name": "Bueno", "limit": {"context": 131072, "output": 8192},
                              "modalities": {"input": ["text", "image"], "output": ["text"]},
                              "reasoning": True, "tool_call": True,
                              "options": {"temperature": 0.2}},
                    "raro": {"name": "raro", "limit": {"context": 4096, "output": 1024},
                             "tool_call": False},
                },
            }
        },
        "providers": {
            "legado": {
                "name": "Legado",
                "package": "@ai-sdk/openai-compatible",
                "models": {
                    "viejo": {"name": "Viejo", "limit": {"context": 8192, "output": 512},
                              "capabilities": {"tools": True, "input": ["text"],
                                               "output": ["text"]}},
                },
            }
        },
    })
    write_json(cache_path, {
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {
            "tok": {
                "uid": "beef1234",
                "name": "Tok",
                "provider_type": "vllm",
                "baseUrl": "http://127.0.0.1:3000",
                "apiKey": "sk-secreto-9999",
                "last_scan": 1760000000,
                "reachable": True,
                "models": {
                    "bueno": {"name": "Bueno", "limit": {"context": 131072, "output": 8192},
                              "modalities": {"input": ["text", "image"], "output": ["text"]},
                              "reasoning": True, "tool_call": True,
                              "options": {"temperature": 0.2}},
                    "raro": {"name": "Raro", "limit": {"context": 1048576}, "tool_call": True,
                             "thinkingLevelMap": {"low": 1, "high": 9}},
                },
            },
        },
    })

    antes = (config.read_bytes(), cache_path.read_bytes())

    with captura() as cap:
        run(home, config, "model", "info", "tok", "bueno")
    check(cap.texto.count("bueno") >= 1 and "=== tok/bueno ===" in cap.texto,
          "B7: la ficha se titula con provider/modelo")
    check("Tokens de contexto (entrada)" in cap.texto
          and "131072 tokens (128k)" in cap.texto,
          "B7: el contexto se ve con el numero y su forma legible")
    check("Tokens maximos de salida" in cap.texto and "8192 tokens (8k)" in cap.texto,
          "B7: la salida maxima sale con su forma legible")
    check("text, image" in cap.texto, "B7: las entradas se ven como lista")
    check("Nombre visible" in cap.texto and "Bueno" in cap.texto,
          "B7: sale el nombre visible del modelo")
    check("Modelo por defecto" in cap.texto,
          "B7: marca el modelo por defecto del config")
    check("URL (cache)" in cap.texto and "URL (opencode)" in cap.texto,
          "B7: se distinguen las dos URLs")
    check("****9999" in cap.texto and "sk-secreto-9999" not in cap.texto,
          "B7: la API key se ensena mascada, nunca entera")
    check("paquete del sdk" in cap.texto.lower() and "@ai-sdk/openai-compatible" in cap.texto,
          "B7: sale el paquete del SDK")
    check("Otras claves" in cap.texto and '"temperature": 0.2' in cap.texto,
          "B7: las claves que ocm no gestiona se muestran aparte")
    check("coinciden" in cap.texto, "B7: si cache y config coinciden, lo dice")
    check("Editar opciones: ocm model options tok bueno" in cap.texto,
          "B7: la ficha dice como editar")
    check(cap.texto.count("(lo asume opencode)") == 0,
          "B7: un modelo completo no necesita avisos de por defecto")

    with captura() as cap:
        run(home, config, "model", "info", "tok", "raro")
    check("no coinciden en: limit, name, tool_call" in cap.texto,
          "B7: detecta en que claves la cache y el config difieren")
    check("cache={\"context\": 1048576}" in cap.texto
          and "config={\"context\": 4096, \"output\": 1024}" in cap.texto,
          "B7: ensena los dos valores de 'limit'")
    check("--force" in cap.texto,
          "B7: explica como hacer que gane la cache")
    check("(lo asume opencode)" in cap.texto,
          "B7: marca lo que opencode asume cuando no esta escrito")
    check("thinkingLevelMap" in cap.texto,
          "B7: una clave desconocida de la cache sale en 'otras claves'")
    check("1048576 tokens (1M)" in cap.texto,
          "B7: manda la cache, no el config (1M frente a 4096)")
    check("deberia incluir" in cap.texto,
          "B7: repite el aviso de limit incompleto")

    with captura() as cap:
        run(home, config, "model", "info", "tok", "raro", "--advanced")
    for etiqueta in ("Acepta parametro temperature", "Acepta adjuntos",
                     "Marcar como experimental", "Estado del modelo"):
        check(etiqueta in cap.texto, f"B7: --advanced anade '{etiqueta}'")

    with captura() as cap:
        run(home, config, "model", "info", "legado", "viejo")
    check("solo en el bloque plural" in cap.texto,
          "B7: avisa si el modelo vive solo en 'providers'")
    check("ocm config to-singular legado" in cap.texto,
          "B7: ofrece la migracion al bloque singular")
    check("8192 tokens (8k)" in cap.texto and "512 tokens" in cap.texto,
          "B7: muestra lo que dice el bloque plural ya traducido")
    check("Legado" in cap.texto and "@ai-sdk/openai-compatible" in cap.texto,
          "B7: nombre y paquete salen aunque no haya entrada en la cache")

    with captura() as cap:
        run(home, config, "model", "info", "tok", "no-existe")
    check("no existe" in cap.texto and "bueno" in cap.texto and "raro" in cap.texto,
          "B7: un modelo desconocido lista los que si existen")

    with captura() as cap:
        run(home, config, "model", "info", "tok", "bueno", "--json")
    volcado = json.loads(cap.texto)
    check(volcado["limit"] == {"context": 131072, "output": 8192}
          and volcado["tool_call"] is True,
          "B7: '--json' vuelca el efectivo (la cache manda en lo propio)")
    check(volcado["options"] == {"temperature": 0.2},
          "B7: '--json' conserva las claves ajenas del config")

    sys.stdin = io.StringIO("2\n")
    with captura() as cap:
        run(home, config, "model", "info", "tok")
    check("Selecciona modelo:" in cap.texto and "1) bueno" in cap.texto
          and "2) raro" in cap.texto,
          "B7: si no se dice el modelo, lo pregunta con menu")
    check("no coinciden en: limit, name, tool_call" in cap.texto,
          "B7: la opcion del menu abre la ficha elegida")

    check((config.read_bytes(), cache_path.read_bytes()) == antes,
          "B7: consultar la ficha no escribe en opencode.json ni en la cache")


def main_tests():
    scenario_parser()

    for name, fn in [("no interactivo", scenario_set),
                     ("asistente", scenario_wizard),
                     ("adopcion", scenario_adoption),
                     ("estilo de API", scenario_api_style),
                     ("prompts", scenario_prompts),
                     ("ficha", scenario_info)]:
        print(f"\n=== escenario: {name} ===")
        home = Path(tempfile.mkdtemp(prefix="ocm-test-b-"))
        try:
            fn(home, home / "opencode.json")
        finally:
            shutil.rmtree(home, ignore_errors=True)

    failed = [label for ok, label in CHECKS if not ok]
    print(f"\n=== {len(CHECKS) - len(failed)}/{len(CHECKS)} checks OK ===")
    for label in failed:
        print(" -", label)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_tests())
