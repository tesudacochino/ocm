"""
Regresiones de la Fase C: `ocm configure` y `ocm model rm`.

Ejecutar:  uv run python tests/test_fase_c.py
Salida:    lista de checks + codigo de salida 1 si alguno falla.

No necesita pytest ni red: trabaja contra una caché y un opencode.json temporales.
"""

import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from opencode_config_manager.cli import main  # noqa: E402
import entorno  # noqa: E402

entorno.sin_registro_models_dev()

CHECKS = []


def check(cond, label):
    print(("  OK    " if cond else "  FALLO ") + label)
    CHECKS.append((bool(cond), label))


def run(home, config, *argv):
    return main(["--home", str(home), "--config", str(config), *argv])


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def feed(*answers):
    sys.stdin = io.StringIO("\n".join(answers) + "\n")


def base_config():
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": "mole/qwen3:14b",
        "provider": {
            "mole": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Mole",
                "options": {"baseURL": "http://127.0.0.1:11434/v1", "apiKey": "sk-vieja"},
                "models": {
                    "qwen3:14b": {"name": "Qwen 3 14B", "limit": {"context": 32768, "output": 4096},
                                  "options": {"temperature": 0.3}},
                    "gemma:latest": {"name": "gemma:latest"},
                    # modelo fantasma: ya no lo sirve el servidor
                    "viejo:1": {"name": "Viejo Uno"},
                },
            },
            "vecino": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Vecino",
                "options": {"baseURL": "http://192.168.4.173:11434/v1"},
                "models": {"default": {"name": "default"}},
            },
            # solo en opencode.json, nunca escaneado
            "soloconfig": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Solo Config",
                "options": {"baseURL": "http://localhost:1234/v1"},
                "models": {},
            },
        },
    }


def base_cache():
    return {
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {
            "mole": {
                "uid": "aabbccdd",
                "name": "Mole",
                "provider_type": "vllm",
                "baseUrl": "http://127.0.0.1:11434",
                "apiKey": "sk-vieja",
                "reachable": True,
                "last_scan": 1700000000,
                "models": {
                    "qwen3:14b": {"name": "Qwen 3 14B"},
                    "gemma:latest": {"name": "gemma:latest"},
                },
            },
            "vecino": {
                "uid": "11223344",
                "name": "Vecino",
                "provider_type": "ollama",
                "baseUrl": "http://192.168.4.173:11434",
                "reachable": True,
                "last_scan": 1700000000,
                "models": {"default": {"name": "default"}},
            },
        },
    }


def setup(home):
    config = home / "opencode.json"
    write_json(config, base_config())
    write_json(home / "provider_cache.json", base_cache())
    return config


def backups(home, config):
    return sorted(config.parent.glob(config.name + ".bak.*"))


# --------------------------------------------------------------------- C1 -- --
def scenario_provider_fields(home: Path, config: Path):
    """Cambiar nombre, api key y estilo de API desde el asistente."""
    print("\n=== C1: campos del provider ===")
    setup(home)

    #  nombre | url | apiKey | tipo | estilo API | modelo a repasar
    feed("Mole Casa", "", "", "", "2", "")
    run(home, config, "configure", "mole", "--no-rescan", "--no-prune")

    cache = read(home / "provider_cache.json")
    conf = read(config)
    mole_cache = cache["providers"]["mole"]
    mole = conf["provider"]["mole"]

    check(mole_cache["name"] == "Mole Casa", "C1: el nombre visible va a la cache")
    check(mole["name"] == "Mole Casa", "C1: el nombre visible va a opencode.json")
    check(mole_cache["npm"] == "@ai-sdk/openai", "C1: el estilo de API elegido se guarda")
    check(mole["npm"] == "@ai-sdk/openai", "C1: el npm elegido llega al config")
    check(mole["options"]["baseURL"] == "http://127.0.0.1:11434/v1",
          "C1: la URL que no se toco queda igual")
    check(mole["options"].get("apiKey") == "sk-vieja", "C1: la api key guardada se conserva")
    check(conf["provider"]["vecino"] == base_config()["provider"]["vecino"],
          "C1: los demas providers no se tocan")
    check(conf.get("model") == "mole/qwen3:14b", "C1: la clave 'model' sigue intacta")
    check(cache["cache_timestamp"] == 1700000000,
          "C1: reconfigurar no mueve la fecha del ultimo escaneo")
    check(bool(backups(home, config)), "C1: se creo backup de opencode.json")


def scenario_no_changes(home: Path, config: Path):
    """Dar Intro a todo no escribe nada."""
    print("\n=== C2: Intro a todo no escribe nada ===")
    setup(home)
    antes_bytes = config.read_bytes()

    #  nombre | url | apiKey | tipo | modelo a repasar
    feed("", "", "", "", "")
    run(home, config, "configure", "mole", "--no-rescan", "--no-api-style", "--no-prune")

    check(config.read_bytes() == antes_bytes, "C2: opencode.json queda byte a byte igual")
    cache = read(home / "provider_cache.json")
    check(cache["cache_timestamp"] == 1700000000, "C2: la fecha del ultimo escaneo no se mueve")
    check(cache["providers"]["mole"]["name"] == "Mole", "C2: el nombre del provider no cambia")
    check(cache["providers"]["mole"]["models"]["qwen3:14b"].get("limit") ==
          {"context": 32768, "output": 4096},
          "C2: lo unico que gana la cache es lo que ya estaba en el config (adopcion)")
    check(not backups(home, config), "C2: sin cambios no se genera backup")

    # El modelo fantasma sigue ahi porque se respondio 'n' a la poda
    check("viejo:1" in read(config)["provider"]["mole"]["models"],
          "C2: negarse a podar deja los modelos como estaban")


def scenario_url(home: Path, config: Path):
    """Cambiar la URL: la caché guarda el host y el config lleva /v1."""
    print("\n=== C3: cambiar la URL ===")
    setup(home)

    #  nombre | apiKey | tipo | modelo a repasar  (la URL va por flag)
    feed("", "", "", "")
    run(home, config, "configure", "mole", "--url", "http://192.168.4.99:11434/",
        "--no-rescan", "--no-api-style", "--no-prune")

    mole_cache = read(home / "provider_cache.json")["providers"]["mole"]
    mole = read(config)["provider"]["mole"]
    check(mole_cache["baseUrl"] == "http://192.168.4.99:11434/",
          "C3: la cache guarda la URL tal cual")
    check(mole["options"]["baseURL"] == "http://192.168.4.99:11434/v1",
          "C3: opencode.json recibe la URL con /v1")


def scenario_api_key(home: Path, config: Path):
    """Poner y quitar la api key (en pantalla se muestra enmascarada)."""
    print("\n=== C4: api key ===")
    setup(home)

    from opencode_config_manager.commands.configure import mask_secret

    check(mask_secret("sk-proj-ABCDEF123456") == "sk-p******3456",
          "C4: la api key se muestra enmascarada")
    check(mask_secret("") == "", "C4: sin key no se muestra nada")

    #  nombre | url | tipo | modelo a repasar  (la key va por flag)
    feed("", "", "", "")
    run(home, config, "configure", "mole", "--api-key", "sk-nueva-1234",
        "--no-rescan", "--no-api-style", "--no-prune")
    mole = read(config)["provider"]["mole"]
    check(mole["options"]["apiKey"] == "sk-nueva-1234", "C4: --api-key escribe en el config")
    check(read(home / "provider_cache.json")["providers"]["mole"]["apiKey"] == "sk-nueva-1234",
          "C4: --api-key escribe en la cache")

    #  nombre | url | apiKey ('-' para quitarla) | tipo | modelo a repasar
    feed("", "", "-", "", "")
    run(home, config, "configure", "mole", "--no-rescan", "--no-api-style", "--no-prune")
    mole = read(config)["provider"]["mole"]
    check("apiKey" not in mole["options"], "C4: '-' quita la api key del config")
    check("apiKey" not in read(home / "provider_cache.json")["providers"]["mole"],
          "C4: '-' quita la api key de la cache")


def scenario_models_step(home: Path, config: Path):
    """Repasar un modelo dentro de `ocm configure`."""
    print("\n=== C5: repasar modelos desde configure ===")
    setup(home)

    #  nombre | url | apiKey | tipo | modelo | 7 campos del modelo
    feed("", "", "", "", "qwen3:14b",
         "", "131072", "", "1,3", "", "y", "y")
    run(home, config, "configure", "mole", "--no-rescan", "--no-api-style", "--no-prune")

    mole = read(config)["provider"]["mole"]
    entry = mole["models"]["qwen3:14b"]
    check(entry["limit"] == {"context": 131072, "output": 4096},
          "C5: el contexto nuevo se escribe y el output del config se conserva")
    check(entry["modalities"]["input"] == ["text", "image"],
          "C5: las modalidades se escriben desde configure")
    check(entry.get("reasoning") is True and entry.get("tool_call") is True,
          "C5: las capacidades se escriben desde configure")
    check(entry.get("options") == {"temperature": 0.3},
          "C5: las claves ajenas del modelo siguen intactas")

    cache_entry = read(home / "provider_cache.json")["providers"]["mole"]["models"]["qwen3:14b"]
    check(cache_entry["limit"]["context"] == 131072, "C5: la cache refleja el cambio")


def scenario_prune(home: Path, config: Path):
    """Aceptar la poda deja solo los modelos que si existen."""
    print("\n=== C6: podar modelos que ya no estan ===")
    setup(home)

    #  nombre | url | apiKey | tipo | modelo a repasar | ¿quitar los que ya no estan?
    feed("", "", "", "", "", "y")
    run(home, config, "configure", "mole", "--no-rescan", "--no-api-style")

    mole = read(config)["provider"]["mole"]
    check("viejo:1" not in mole["models"], "C6: el modelo fantasma sale de opencode.json")
    check(set(mole["models"]) == {"qwen3:14b", "gemma:latest"},
          "C6: los modelos validos no se tocan")
    cache_models = read(home / "provider_cache.json")["providers"]["mole"]["models"]
    check("viejo:1" not in cache_models, "C6: el modelo fantasma sale de la cache")
    check(mole["models"]["qwen3:14b"].get("options") == {"temperature": 0.3},
          "C6: podar no toca las opciones de los que se quedan")


def scenario_model_rm(home: Path, config: Path):
    """`ocm model rm` quita un modelo concreto de los dos archivos."""
    print("\n=== C7: ocm model rm ===")
    setup(home)

    run(home, config, "model", "rm", "mole", "gemma:latest", "--yes")
    mole = read(config)["provider"]["mole"]
    check("gemma:latest" not in mole["models"], "C7: sale de opencode.json")
    cache_models = read(home / "provider_cache.json")["providers"]["mole"]["models"]
    check("gemma:latest" not in cache_models, "C7: sale de la cache")
    check("qwen3:14b" in mole["models"], "C7: los demas modelos siguen")
    check(bool(backups(home, config)), "C7: se crea backup antes de borrar")

    # Quitar el modelo por defecto avisa pero no rompe
    run(home, config, "model", "rm", "mole", "qwen3:14b", "--yes")
    check("qwen3:14b" not in read(config)["provider"]["mole"]["models"],
          "C7: se puede quitar el modelo por defecto (con aviso)")

    # Modelo inexistente: no toca nada
    setup(home)
    antes = config.read_bytes()
    run(home, config, "model", "rm", "mole", "no-existe", "--yes")
    check(config.read_bytes() == antes, "C7: un modelo inexistente no cambia el config")

    # Sin confirmacion no borra
    feed("n")
    run(home, config, "model", "rm", "mole", "gemma:latest")
    check("gemma:latest" in read(config)["provider"]["mole"]["models"],
          "C7: responder 'n' deja el modelo")


def scenario_safety(home: Path, config: Path):
    """Cosas que no deben romperse ni escribir de mas."""
    print("\n=== C8: seguridad ===")
    setup(home)

    antes = config.read_bytes()
    feed("", "", "")
    run(home, config, "configure", "no-existe")
    check(config.read_bytes() == antes, "C8: un provider inexistente no escribe nada")

    # Provider que solo esta en opencode.json (sin entrada de caché)
    antes_bytes = config.read_bytes()
    run(home, config, "configure", "soloconfig", "--no-rescan")
    check(config.read_bytes() == antes_bytes,
          "C8: un provider sin caché no se modifica (manda a 'ocm new')")

    # 'ocm update' sigue sin borrar el modelo fantasma (no destructivo)
    before = read(config)
    feed("n")
    run(home, config, "update", "mole")
    after = read(config)
    check("viejo:1" in after["provider"]["mole"]["models"],
          "C8: update no poda por su cuenta")
    check(after["provider"]["vecino"] == before["provider"]["vecino"],
          "C8: update no toca otros providers")


def main_tests():
    for name, fn in [("campos del provider", scenario_provider_fields),
                     ("sin cambios", scenario_no_changes),
                     ("cambiar URL", scenario_url),
                     ("api key", scenario_api_key),
                     ("repasar modelos", scenario_models_step),
                     ("poda", scenario_prune),
                     ("model rm", scenario_model_rm),
                     ("seguridad", scenario_safety)]:
        home = Path(tempfile.mkdtemp(prefix="ocm-test-c-"))
        print(f"\n=== escenario: {name} ===")
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
