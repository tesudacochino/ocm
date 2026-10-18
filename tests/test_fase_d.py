"""
Regresiones de la Fase D: bloque plural `providers` (formato codificado de v2).

Ejecutar:  uv run python tests/test_fase_d.py
Salida:    lista de checks + codigo de salida 1 si alguno falla.

Se comprueba empiricamente (opencode 2.0.32) que `providers` no registra
providers, asi que ocm lo que hace es detectarlo, entenderlo y migrarlo a la
forma singular, que es la que funciona.
"""

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from opencode_config_manager.cli import main  # noqa: E402
from opencode_config_manager.commands.encoded import (  # noqa: E402
    format_notes,
    model_from_encoded,
    provider_from_encoded,
)

CHECKS = []


def check(cond, label):
    print(("  OK    " if cond else "  FALLO ") + label)
    CHECKS.append((bool(cond), label))


def run(home, config, *argv):
    return main(["--home", str(home), "--config", str(config), *argv])


def run_cap(home, config, *argv):
    """Ejecutar capturando lo que se imprime (para comprobar avisos)."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        run(home, config, *argv)
    return buffer.getvalue()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def feed(*answers):
    sys.stdin = io.StringIO("\n".join(answers) + "\n")


def backups(home, config):
    return sorted(config.parent.glob(config.name + ".bak.*"))


LEGADO_MODEL = {
    "modelID": "llama-3.1-8b",
    "name": "Legado Llama",
    "releaseDate": "2024-07-01",
    "capabilities": {"tools": True, "input": ["text", "image"], "output": ["text"],
                     "temperature": True, "reasoning": False},
    "limit": {"context": 131072, "input": 128000, "output": 16384},
    "settings": {"temperature": 0.2},
    "variants": [{"id": "think", "settings": {"thinking": {"type": "enabled"}}}, {"id": "fast"}],
    "disabled": False,
}


def base_config():
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": "vecino/default",
        "provider": {
            "vecino": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Vecino",
                "options": {"baseURL": "http://192.168.4.173:11434/v1"},
                "models": {"default": {"name": "default"}},
            },
            "duplicado": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Duplicado",
                "options": {"baseURL": "http://127.0.0.1:9999/v1"},
                "models": {"m1": {"name": "M1"}},
            },
        },
        "providers": {
            "legado": {
                "canonical": "openai-compatible",
                "name": "Legado",
                "env": ["LEGADO_API_KEY"],
                "package": "@ai-sdk/openai-compatible",
                "compatibility": {"reasoningField": "reasoning"},
                "settings": {"baseURL": "http://192.168.4.200:8000/v1",
                             "apiKey": "sk-legado", "timeout": 60000},
                "headers": {"X-Client": "ocm"},
                "body": {"user": "x"},
                "models": {
                    "llama-3.1-8b": LEGADO_MODEL,
                    "incompleto": {"limit": {"context": 4096}},
                },
            },
            "duplicado": {
                "package": "@ai-sdk/openai-compatible",
                "settings": {"baseURL": "http://127.0.0.1:1234/v1"},
                "models": {"m1": {}},
            },
        },
    }


def base_cache():
    return {
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {
            "vecino": {
                "uid": "11223344",
                "name": "Vecino",
                "provider_type": "ollama",
                "baseUrl": "http://192.168.4.173:11434",
                "reachable": True,
                "last_scan": 1700000000,
                "models": {"default": {"name": "default"}},
            },
            "duplicado": {
                "uid": "55667788",
                "name": "Duplicado",
                "provider_type": "vllm",
                "baseUrl": "http://127.0.0.1:9999",
                "reachable": True,
                "last_scan": 1700000000,
                "models": {"m1": {"name": "M1"}},
            },
        },
    }


def setup(home):
    config = home / "opencode.json"
    write_json(config, base_config())
    write_json(home / "provider_cache.json", base_cache())
    return config


# ------------------------------------------------------------------ conversion --
def scenario_conversion(home: Path, config: Path):
    """La traduccion del formato codificado al singular."""
    print("\n=== D1: conversion de modelos ===")

    out, notes = model_from_encoded("llama-3.1-8b", LEGADO_MODEL)

    check(out.get("tool_call") is True, "D1: capabilities.tools -> tool_call")
    check(out.get("temperature") is True, "D1: capabilities.temperature -> temperature")
    check(out.get("reasoning") is False, "D1: capabilities.reasoning -> reasoning")
    check(out.get("modalities") == {"input": ["text", "image"], "output": ["text"]},
          "D1: capabilities.input/output -> modalities")
    check(out.get("release_date") == "2024-07-01", "D1: releaseDate -> release_date")
    check("releaseDate" not in out, "D1: la forma camelCase no se queda")
    check(out.get("limit") == {"context": 131072, "input": 128000, "output": 16384},
          "D1: 'limit' pasa tal cual")
    check(out.get("options") == {"temperature": 0.2}, "D1: 'settings' del modelo -> 'options'")
    check("id" not in out, "D1: 'modelID' igual a la clave no genera 'id'")
    check(out.get("variants") == {"think": {"thinking": {"type": "enabled"}}, "fast": {}},
          "D1: 'variants' de lista a objeto")
    check("disabled" not in out and any("disabled" in n for n in notes),
          "D1: 'disabled' se avisa de que se pierde")
    check(any("compatibilidad" in n or "singular" in n for n in notes),
          "D1: deja aviso de lo que no cabe en el formato singular")

    otro, notas2 = model_from_encoded("x", {"modelID": "y", "limit": {"context": 100}})
    check(otro.get("id") == "y", "D1: 'modelID' distinto de la clave se guarda como 'id'")
    check(any("limit" in n for n in notas2), "D1: 'limit' sin 'output' avisa")

    roto, notas3 = model_from_encoded("z", "no-es-objeto")
    check(roto == {} and notas3, "D1: un modelo que no es objeto se omite con aviso")


def scenario_provider_conversion(home: Path, config: Path):
    """La traduccion a nivel de provider."""
    print("\n=== D2: conversion del provider ===")

    enc = base_config()["providers"]["legado"]
    out, notes = provider_from_encoded("legado", enc)

    check(out.get("npm") == "@ai-sdk/openai-compatible", "D2: package -> npm")
    check(out.get("name") == "Legado", "D2: el nombre visible pasa")
    check(out.get("env") == ["LEGADO_API_KEY"], "D2: 'env' pasa")
    check(out["options"]["baseURL"] == "http://192.168.4.200:8000/v1",
          "D2: settings.baseURL -> options.baseURL")
    check(out["options"]["apiKey"] == "sk-legado", "D2: settings.apiKey -> options.apiKey")
    check(out["options"]["timeout"] == 60000, "D2: otros settings pasan a options")
    check(out["options"]["headers"] == {"X-Client": "ocm"},
          "D2: 'headers' del provider se recoloca en options")
    check(set(out["models"]) == {"llama-3.1-8b", "incompleto"}, "D2: los modelos se traducen")
    check("canonical" not in out and "compatibility" not in out and "body" not in out,
          "D2: canonical/compatibility/body no se escriben")
    check(any("canonical" in n for n in notes) and any("compatibility" in n for n in notes),
          "D2: se avisa de lo que se pierde")


def scenario_notes(home: Path, config: Path):
    """Detectar quien vive en cada bloque."""
    print("\n=== D3: deteccion de bloques ===")

    notas = format_notes(base_config())

    check(any("duplicado" in n and "se ignora" in n for n in notas),
          "D3: avisa del provider que esta en los dos bloques")
    check(any(n.startswith("'legado'") and "to-singular" in n for n in notas),
          "D3: avisa del que solo esta en 'providers' y manda al migrador")
    check(format_notes({"provider": {"a": {}}}) == [], "D3: sin bloque plural, sin avisos")


# -------------------------------------------------------------------- migracion --
def scenario_migrate(home: Path, config: Path):
    """`ocm config to-singular` escribe el bloque singular y la caché."""
    print("\n=== D4: migrar con to-singular ===")
    setup(home)

    feed("n")  # dejar las entradas en 'providers'
    run(home, config, "config", "to-singular", "legado", "--keep")

    conf = read(config)
    legado = conf["provider"].get("legado") or {}

    check(bool(legado), "D4: se creo provider.legado")
    check(legado.get("npm") == "@ai-sdk/openai-compatible", "D4: npm desde 'package'")
    check(legado["options"]["baseURL"] == "http://192.168.4.200:8000/v1",
          "D4: la URL con /v1 en options")
    check(legado["models"]["llama-3.1-8b"].get("tool_call") is True,
          "D4: las capacidades llegan al singular")
    check(legado["models"]["llama-3.1-8b"]["modalities"]["input"] == ["text", "image"],
          "D4: las modalidades llegan al singular")
    check(conf["provider"]["vecino"] == base_config()["provider"]["vecino"],
          "D4: los demas providers no se tocan")
    check(conf.get("model") == "vecino/default", "D4: la clave 'model' intacta")
    check("legado" in conf.get("providers", {}), "D4: --keep deja el bloque plural")
    check(bool(backups(home, config)), "D4: se creo backup de opencode.json")

    cache = read(home / "provider_cache.json")
    cache_entry = cache["providers"].get("legado") or {}
    check(cache_entry.get("baseUrl") == "http://192.168.4.200:8000",
          "D4: la caché guarda la URL sin /v1")
    check(cache_entry.get("apiKey") == "sk-legado", "D4: la api key pasa a la caché")
    check(cache_entry.get("npm") == "@ai-sdk/openai-compatible", "D4: el npm pasa a la caché")
    check(cache_entry.get("provider_type") == "vllm", "D4: tipo detectado por el paquete")
    check(bool(cache_entry.get("uid")), "D4: la entrada nueva de caché lleva uid")
    check("llama-3.1-8b" in (cache_entry.get("models") or {}),
          "D4: los modelos migrados quedan en la caché")
    check(cache["cache_timestamp"] == 1700000000, "D4: no mueve la fecha del escaneo")


def scenario_non_destructive(home: Path, config: Path):
    """Migrar sobre un provider que ya existe no pisa lo que ya estaba."""
    print("\n=== D5: migrar sin pisar ===")
    setup(home)

    run(home, config, "config", "to-singular", "duplicado", "--keep")
    duplicado = read(config)["provider"]["duplicado"]
    check(duplicado["options"]["baseURL"] == "http://127.0.0.1:9999/v1",
          "D5: sin --force la URL que ya estaba en el singular se respeta")
    check(duplicado["models"]["m1"].get("name") == "M1",
          "D5: las opciones del modelo que ya existian se respetan")

    run(home, config, "config", "to-singular", "duplicado", "--keep", "--force")
    duplicado = read(config)["provider"]["duplicado"]
    check(duplicado["options"]["baseURL"] == "http://127.0.0.1:1234/v1",
          "D5: con --force si que se aplica el valor del bloque plural")


def scenario_dry_run(home: Path, config: Path):
    """--dry-run no escribe nada."""
    print("\n=== D6: dry run ===")
    setup(home)
    antes = config.read_bytes()
    cache_antes = (home / "provider_cache.json").read_bytes()

    salida = run_cap(home, config, "config", "to-singular", "--dry-run")

    check(config.read_bytes() == antes, "D6: --dry-run no toca opencode.json")
    check((home / "provider_cache.json").read_bytes() == cache_antes,
          "D6: --dry-run no toca la caché")
    check(not backups(home, config), "D6: --dry-run no deja backup")
    check("provider.legado" in salida, "D6: --dry-run enseña donde ira cada provider")


def scenario_drop(home: Path, config: Path):
    """--drop quita del bloque plural lo migrado (y solo eso)."""
    print("\n=== D7: drop ===")
    setup(home)

    run(home, config, "config", "to-singular", "legado", "--drop")
    conf = read(config)
    check("legado" not in conf.get("providers", {}), "D7: --drop quita la entrada migrada")
    check("duplicado" in conf.get("providers", {}),
          "D7: --drop solo quita las migradas, no las demas")
    check(bool(conf["provider"].get("legado")), "D7: y deja la Version singular")

    # La ultima entrada plural se quita del todo (no queda un objeto vacio)
    run(home, config, "config", "to-singular", "duplicado", "--drop")
    conf = read(config)
    check("providers" not in conf, "D7: si no queda nada, el bloque 'providers' desaparece")
    check(bool(conf["provider"]), "D7: el bloque singular sigue completo")


def scenario_list_and_validate(home: Path, config: Path):
    """Que se vean y que el validador los entienda."""
    print("\n=== D8: list y validate ===")
    setup(home)

    salida = run_cap(home, config, "model", "list", "legado")
    check("solo 'providers'" in salida, "D8: model list marca los que solo estan en el plural")
    check("Legado Llama" in salida, "D8: model list ensena el nombre visible migrable")
    check("to-singular" in salida, "D8: model list sugiere como arreglarlo")

    salida = run_cap(home, config, "config", "validate")
    check("duplicado" in salida and "se ignora" in salida,
          "D8: validate avisa del provider en los dos bloques")
    check("legado" in salida, "D8: validate avisa del que solo esta en 'providers'")

    conf = read(config)
    conf["providers"]["roto"] = {
        "package": "@ai-sdk/openai-compatible",
        "models": {"x": {"capabilities": {"tools": "si", "input": "text",
                                           "otracosa": 1},
                         "tool_call": True, "variants": {"a": {}}}},
    }
    write_json(config, conf)
    salida = run_cap(home, config, "config", "validate")
    check("capabilities.tools" in salida, "D8: validate pilla 'tools' que no es booleano")
    check("capabilities.input" in salida or "capabilities.otracosa" in salida,
          "D8: validate revisa el resto de capabilities")
    check("providers.roto.models.x: clave no reconocida 'tool_call'" in salida,
          "D8: validate dice que tool_call no va en el plural")
    check("'variants'" in salida and "lista" in salida,
          "D8: validate avisa de 'variants' en formato equivocado")


def scenario_update_coexistencia(home: Path, config: Path):
    """`ocm update` no toca el bloque plural pero avisa de la convivencia."""
    print("\n=== D9: update y el bloque plural ===")
    setup(home)
    plural_antes = base_config()["providers"]

    salida = run_cap(home, config, "update", "duplicado")

    conf = read(config)
    check(conf["providers"] == plural_antes, "D9: 'update' no escribe ni borra en 'providers'")
    check("providers" in salida and "hace caso" in salida,
          "D9: 'update' avisa de la entrada duplicada en 'providers'")
    check("model" in conf and conf["model"] == "vecino/default",
          "D9: 'update' sigue sin tocar otras claves del archivo")


def scenario_safety(home: Path, config: Path):
    """Cosas que no deben romperse."""
    print("\n=== D10: seguridad ===")
    setup(home)
    antes = config.read_bytes()

    run(home, config, "config", "to-singular", "no-existe")
    check(config.read_bytes() == antes, "D10: un provider inexistente no escribe nada")

    # Sin bloque plural: mensaje claro y nada escrito
    solo_singular = base_config()
    solo_singular.pop("providers")
    write_json(config, solo_singular)
    antes = config.read_bytes()
    salida = run_cap(home, config, "config", "to-singular")
    check(config.read_bytes() == antes, "D10: sin bloque plural no se toca el archivo")
    check("nada que migrar" in salida, "D10: y lo dice")

    # 'providers' mal formado no revienta el migrador
    conf = base_config()
    conf["providers"] = {"roto": "no-es-objeto"}
    write_json(config, conf)
    antes_untouched = read(config)["provider"]["vecino"]
    salida = run_cap(home, config, "config", "to-singular", "roto", "--keep")
    conf = read(config)
    check(conf["provider"]["vecino"] == antes_untouched,
          "D10: un provider mal formado en el plural no estroaga los demas")
    check(isinstance(conf["provider"].get("roto"), dict),
          "D10: del formato roto sale al menos una entrada singular usable")


def main_tests():
    escenarios = [
        ("conversion de modelos", scenario_conversion),
        ("conversion del provider", scenario_provider_conversion),
        ("deteccion de bloques", scenario_notes),
        ("migracion", scenario_migrate),
        ("no destructivo", scenario_non_destructive),
        ("dry run", scenario_dry_run),
        ("drop", scenario_drop),
        ("list y validate", scenario_list_and_validate),
        ("update y convivencia", scenario_update_coexistencia),
        ("seguridad", scenario_safety),
    ]

    for name, fn in escenarios:
        home = Path(tempfile.mkdtemp(prefix="ocm-test-d-"))
        print(f"\n=== escenario: {name} ===")
        try:
            fn(home, home / "opencode.json")
        finally:
            sys.stdin = sys.__stdin__
            shutil.rmtree(home, ignore_errors=True)

    failed = [label for ok, label in CHECKS if not ok]
    print(f"\n=== {len(CHECKS) - len(failed)}/{len(CHECKS)} checks OK ===")
    for label in failed:
        print(" -", label)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_tests())
