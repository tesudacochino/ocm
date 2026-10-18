"""
Regresiones de la Fase A: ocm no destruye opencode.json y los nombres visibles
de provider/modelo viajan de la caché al archivo.

Ejecutar:  uv run python tests/test_fase_a.py
Salida:    lista de checks + codigo de salida 1 si alguno falla.

No necesita pytest ni red: levanta un servidor Ollama simulado en localhost.
"""

import io
import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from opencode_config_manager.cli import main  # noqa: E402
import entorno  # noqa: E402

entorno.sin_registro_models_dev()

PORT = 11499
DEAD_PORT = 11498
STATE = {"auth": [], "models": ["model-a", "model-b"]}
CHECKS = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/api/tags":
            STATE["auth"].append(self.headers.get("Authorization"))
            body = json.dumps({"models": [{"name": m} for m in STATE["models"]]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def check(cond, label):
    print(("  OK    " if cond else "  FALLO ") + label)
    CHECKS.append((bool(cond), label))


def run(home, config, *argv):
    return main(["--home", str(home), "--config", str(config), *argv])


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_no_destructivo(home: Path):
    """A1 + A4: merge no destructivo y migración de la caché."""
    config = home / "opencode.json"
    (home / "provider_cache.json").write_text(json.dumps({
        "cache_timestamp": 1700000000,
        "providers": {
            "mole": {
                # formato v1: modelos en lista
                "models": ["qwen3:14b", "gemma4:latest"],
                "last_scan": 1700000000,
                "baseUrl": "http://127.0.0.1:11434",
                "provider_type": "ollama",
                "apiKey": "sk-local",
            }
        },
    }, indent=2), encoding="utf-8")

    config.write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "model": "mole/qwen3:14b",
        # bloque v2 en plural: ocm no debe tocarlo
        "providers": {"local-brain": {"name": "Local Brain", "models": {"m": {"name": "M"}}}},
        "provider": {
            "other": {"npm": "@ai-sdk/openai-compatible", "name": "Other",
                      "options": {"baseURL": "http://x:1/v1"}, "models": {"x1": {"name": "X1"}}},
            "mole": {"npm": "@ai-sdk/openai-compatible", "name": "mole",
                     "options": {"baseURL": "http://127.0.0.1:11434/v1"},
                     "whitelist": ["qwen3:14b"],
                     "models": {"qwen3:14b": {"name": "qwen3:14b", "options": {"temperature": 0.2}},
                                "legacy-only": {"name": "Legacy Only"}}},
        },
    }, indent=2), encoding="utf-8")

    run(home, config, "update", "mole")
    cfg = read(config)
    check("providers" in cfg, "A1: conserva el bloque 'providers' (v2)")
    check(cfg.get("model") == "mole/qwen3:14b", "A1: no borra el campo 'model'")
    check("other" in cfg["provider"], "A1: deja intactos los demas providers")
    mole = cfg["provider"]["mole"]
    check(mole.get("whitelist") == ["qwen3:14b"], "A1: conserva claves no gestionadas (whitelist)")
    check(mole["models"]["qwen3:14b"].get("options") == {"temperature": 0.2},
          "A1: conserva opciones escritas a mano en un modelo")
    check("legacy-only" in mole["models"], "A1: no borra modelos existentes")
    check(mole["models"]["gemma4:latest"]["name"] == f"gemma4:latest · {mole['name']}",
          "A1: añade el modelo nuevo con nombre 'modelo · provider'")
    check(mole["options"].get("apiKey") == "sk-local", "A3: la apiKey de la cache llega al config")

    before = read(config)
    run(home, config, "update", "mole")
    check(read(config) == before, "A1: repetir 'update' no cambia nada")

    cache = read(home / "provider_cache.json")
    entry = cache["providers"]["mole"]
    check(isinstance(entry["models"], dict), "A4: la cache migra a formato v2")
    check(entry.get("apiKey") == "sk-local", "A4: la migracion no pierde la apiKey")
    check(cache.get("cache_version") == 2, "A4: cache_version = 2")
    check(len(entry.get("uid", "")) == 8, "A4: uid asignado al migrar")

    run(home, config, "model", "name", "mole", "qwen3:14b", "--name", "Qwen 3 14B")
    check(read(config)["provider"]["mole"]["models"]["qwen3:14b"]["name"] == "Qwen 3 14B",
          "A2: renombrar modelo actualiza opencode.json")
    check(read(home / "provider_cache.json")["providers"]["mole"]["models"]["qwen3:14b"]["name"]
          == "Qwen 3 14B", "A2: renombrar modelo actualiza la cache")
    check(read(config)["provider"]["mole"]["models"]["qwen3:14b"].get("options")
          == {"temperature": 0.2}, "A2: renombrar no pisa otras opciones del modelo")

    run(home, config, "rename", "mole", "--name", "Mole Local")
    check(read(config)["provider"]["mole"]["name"] == "Mole Local",
          "A2: renombrar provider actualiza opencode.json")

    data = read(config)
    data["provider"]["mole"]["name"] = "manual"
    config.write_text(json.dumps(data, indent=2), encoding="utf-8")
    run(home, config, "update", "mole")
    check(read(config)["provider"]["mole"]["name"] == "manual",
          "A1: sin --force no sobrescribe una clave existente")
    run(home, config, "update", "mole", "--force")
    check(read(config)["provider"]["mole"]["name"] == "Mole Local",
          "A1: con --force reescribe desde la cache")


def scenario_escaneo(home: Path):
    """A2 + A3: escaneo que conserva apiKey/uid/nombre y asistente interactivo."""
    config = home / "opencode.json"
    (home / "provider_cache.json").write_text(json.dumps({
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {
            "test": {
                "uid": "abcd1234",
                "name": "Test Local",
                "models": {
                    "model-a": {"name": "Modelo A",
                                "limit": {"context": 131072, "output": 16384},
                                "modalities": {"input": ["text", "image"], "output": ["text"]}},
                    "vanished": {"name": "Modelo Que Ya No Esta"},
                },
                "last_scan": 1700000000,
                "baseUrl": f"http://127.0.0.1:{PORT}",
                "provider_type": "ollama",
                "apiKey": "sk-secret",
            },
            "dead": {"models": {}, "last_scan": 1700000000,
                     "baseUrl": f"http://127.0.0.1:{DEAD_PORT}", "provider_type": "ollama"},
        },
    }, indent=2), encoding="utf-8")

    config.write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "provider": {"test": {"npm": "@ai-sdk/openai-compatible", "name": "Test Local",
                              "options": {"baseURL": f"http://127.0.0.1:{PORT}/v1"},
                              "models": {"model-a": {"name": "Modelo A"},
                                         "vanished": {"name": "Modelo Que Ya No Esta",
                                                      "options": {"temperature": 0.5}}}}},
    }, indent=2), encoding="utf-8")

    STATE["auth"] = []
    STATE["models"] = ["model-a", "model-b"]
    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    run(home, config, "cache", "update", "test")
    entry = read(home / "provider_cache.json")["providers"]["test"]
    check(STATE["auth"] == ["Bearer sk-secret"], "A3: el escaneo usa la apiKey guardada")
    check(entry.get("apiKey") == "sk-secret", "A3: la apiKey sobrevive al escaneo")
    check(entry.get("uid") == "abcd1234", "A3: el uid es estable")
    check(entry.get("name") == "Test Local", "A3: el nombre visible sobrevive al escaneo")
    check(entry.get("reachable") is True, "A3: reachable=True tras escaneo ok")
    check(entry["models"]["model-a"]["limit"]["context"] == 131072,
          "A3: conserva las opciones del modelo al rescannear")
    check("model-b" in entry["models"], "A3: detecta el modelo nuevo")
    check("vanished" not in entry["models"], "A3: quita de la cache el modelo que ya no esta")

    run(home, config, "update", "test")
    models = read(config)["provider"]["test"]["models"]
    check(models["model-a"]["modalities"]["input"] == ["text", "image"],
          "A2: modalities de la cache van a opencode.json")
    check(models["model-a"]["limit"]["context"] == 131072,
          "A2: limit de la cache va a opencode.json")
    check("vanished" in models, "A1: el modelo desaparecido no se borra de opencode.json")

    run(home, config, "cache", "update", "dead")
    check(read(home / "provider_cache.json")["providers"]["dead"].get("reachable") is False,
          "A3: provider caido -> reachable False")

    # Asistente interactivo: provider nuevo
    sys.stdin = io.StringIO("\n".join([
        "wizard", "", f"http://127.0.0.1:{PORT}", "sk-wiz",
        "y", "Modelo Uno", "Modelo Dos", "y",
    ]) + "\n")
    run(home, config, "new")
    entry = read(home / "provider_cache.json")["providers"]["wizard"]
    check(entry.get("name") == "Wizard", "A2: pregunta y guarda el nombre visible del provider")
    check(entry["models"]["model-a"]["name"] == "Modelo Uno", "A2: pregunta el nombre por modelo")
    check(len(entry.get("uid", "")) == 8, "A3: genera uid para el provider nuevo")
    cfg = read(config)["provider"]["wizard"]
    check(cfg["name"] == "Wizard", "A2: opencode.json recibe el nombre del provider")
    check(cfg["models"]["model-b"]["name"] == "Modelo Dos", "A2: opencode.json recibe los de modelos")
    check(cfg["options"]["apiKey"] == "sk-wiz", "A3: escribe la apiKey en options")

    # Provider existente: cancelar el overwrite pide otro nombre
    sys.stdin = io.StringIO("\n".join([
        "wizard", "n", "wizard-2", "", f"http://127.0.0.1:{PORT}", "", "n", "n",
    ]) + "\n")
    run(home, config, "new")
    names = set(read(home / "provider_cache.json")["providers"])
    check({"wizard", "wizard-2"} <= names, "A3: no pisa un provider existente sin avisar")

    # Provider existente: reconfigurar conserva apiKey y nombres de modelo
    sys.stdin = io.StringIO("\n".join([
        "wizard", "y", "Wizard Pro", "", "", "n", "n",
    ]) + "\n")
    run(home, config, "new")
    entry = read(home / "provider_cache.json")["providers"]["wizard"]
    check(entry["name"] == "Wizard Pro", "A2: reconfigurar actualiza el nombre del provider")
    check(entry["models"]["model-a"]["name"] == "Modelo Uno",
          "A2: reconfigurar conserva los nombres de los modelos")
    check(entry.get("apiKey") == "sk-wiz", "A3: reconfigurar conserva la apiKey")

    srv.shutdown()
    srv.server_close()


def scenario_mal_formado(home: Path):
    """A1: configs escritas a mano con formas raras no se destruyen."""
    config = home / "opencode.json"
    (home / "provider_cache.json").write_text(json.dumps({
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {"raro": {"models": {"m1": {"name": "M1"}}, "last_scan": 1700000000,
                               "baseUrl": "http://127.0.0.1:9/v1", "provider_type": "vllm"}},
    }, indent=2), encoding="utf-8")

    # 'models' como lista (error habitual) + 'name' en la posicion del provider
    config.write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "provider": {"raro": {"npm": "@ai-sdk/openai-compatible", "name": "Raro",
                              "models": [{"id": "viejo", "name": "Viejo"}]}},
    }, indent=2), encoding="utf-8")

    run(home, config, "update", "raro")
    models = read(config)["provider"]["raro"]["models"]
    check(isinstance(models, dict), "A1: 'models' en lista se convierte a objeto")
    check("viejo" in models and "m1" in models,
          "A1: la conversion conserva el modelo previo y anade el nuevo")

    # Provider con un valor que no es un objeto: no debe reescribirse
    config.write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "provider": {"raro": "compartido"},
    }, indent=2), encoding="utf-8")
    before = read(config)
    run(home, config, "update", "raro")
    check(read(config) == before, "A1: un provider mal formado no se modifica")


def main_tests():
    for name, fn in [("no destructivo", scenario_no_destructivo),
                     ("escaneo y asistente", scenario_escaneo),
                     ("mal formado", scenario_mal_formado)]:
        print(f"\n=== escenario: {name} ===")
        home = Path(tempfile.mkdtemp(prefix="ocm-test-"))
        try:
            fn(home)
        finally:
            shutil.rmtree(home, ignore_errors=True)

    failed = [label for ok, label in CHECKS if not ok]
    print(f"\n=== {len(CHECKS) - len(failed)}/{len(CHECKS)} checks OK ===")
    for label in failed:
        print(" -", label)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_tests())
