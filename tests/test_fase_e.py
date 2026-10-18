"""
Regresiones de la Fase E: casos raros y empaquetado del release.

Ejecutar:  uv run python tests/test_fase_e.py
Salida:    lista de checks + codigo de salida 1 si alguno falla.

Cubre lo que las fases anteriores dejaron suelto:
  * escanear un provider que esta caido (no debe perder api key, nombres ni opciones),
  * renombrar cuando el provider/modelo aun no esta en opencode.json,
  * migrar una caché v1 con claves raras (lista de modelos, capabilities, toolcall,
    thinkingLevelMap, limites tipo "128k"),
  * y que el empaquetado no vuelva a registrar un ejecutable `opencode`.
"""

import io
import json
import re
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

CHECKS = []
RAIZ = Path(__file__).resolve().parents[1]


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
        pass  # argparse sale con SystemExit en --version/--help
    return buffer.getvalue()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def feed(*answers):
    sys.stdin = io.StringIO("\n".join(answers) + "\n")


def vecino_config():
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "vecino": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Vecino",
                "options": {"baseURL": "http://192.168.4.173:11434/v1"},
                "models": {"default": {"name": "default"}},
            }
        },
    }


def mole_cache(extra=None):
    entry = {
        "uid": "aabbccdd",
        "name": "Mole",
        "provider_type": "vllm",
        "baseUrl": "http://127.0.0.1:11434",
        "apiKey": "sk-mol-secreta",
        "reachable": True,
        "last_scan": 1700000000,
        "models": {
            "qwen3:14b": {
                "name": "Qwen 3 14B",
                "limit": {"context": 32768, "output": 4096},
                "tool_call": True,
                "modalities": {"input": ["text", "image"], "output": ["text"]},
            },
            "gemma:latest": {"name": "gemma:latest"},
        },
    }
    entry.update(extra or {})
    return {
        "cache_version": 2,
        "cache_timestamp": 1700000000,
        "providers": {"mole": entry,
                      "vecino": {"uid": "11223344", "name": "Vecino",
                                 "provider_type": "ollama",
                                 "baseUrl": "http://192.168.4.173:11434",
                                 "reachable": True, "last_scan": 1700000000,
                                 "models": {"default": {"name": "default"}}}},
    }


def parchear_escaneo(resultado):
    """Sustituir los dos escaneadores por uno que devuelve lo que le digamos.

    Hacen falta los dos: si solo falla uno, el escaneo prueba el otro endpoint y
    ahi dependeriamos de que haya o no un servidor real levantado en la maquina.
    """
    originales = (api.ProviderScanner.scan_vllm, api.ProviderScanner.scan_ollama)
    falso = staticmethod(lambda base_url, api_key=None: resultado)
    api.ProviderScanner.scan_vllm = falso
    api.ProviderScanner.scan_ollama = falso
    return originales


def desparchear_escaneo(originales):
    """Devolverse los escaneadores reales."""
    api.ProviderScanner.scan_vllm, api.ProviderScanner.scan_ollama = originales


# ------------------------------------------------------------------ provider caido --
def scenario_scan_down(home: Path, config: Path):
    """Un escaneo que falla no debe hacer perder nada."""
    print("\n=== E1: escanear un provider caido ===")
    write_json(config, vecino_config())
    write_json(home / "provider_cache.json", mole_cache())

    originales = parchear_escaneo(ScanResult(False, [], "Connection refused"))
    try:
        salida = run_cap(home, config, "cache", "update", "mole")
    finally:
        desparchear_escaneo(originales)

    cache = read(home / "provider_cache.json")
    mole = cache["providers"]["mole"]

    check("caido" in salida.lower() or "error" in salida.lower(),
          "E1: avisa del fallo en pantalla")
    check(mole.get("reachable") is False, "E1: marca el provider no accesible")
    check("refused" in str(mole.get("last_scan_error", "")),
          "E1: guarda el motivo del fallo en la caché")
    check(mole.get("apiKey") == "sk-mol-secreta", "E1: conserva la api key")
    check(mole.get("name") == "Mole", "E1: conserva el nombre visible")
    check(mole.get("last_scan") == 1700000000, "E1: no finge un escaneo reciente")
    modelos = mole.get("models") or {}
    check(modelos.get("qwen3:14b", {}).get("limit", {}).get("context") == 32768,
          "E1: conserva las opciones por modelo")
    check(modelos.get("qwen3:14b", {}).get("modalities", {}).get("input") ==
          ["text", "image"], "E1: conserva las modalidades")
    check("gemma:latest" in modelos, "E1: no borra modelos por un escaneo fallido")

    # Aunque este caido, 'ocm update' escribe y avisa
    salida = run_cap(home, config, "update", "mole")
    check("accesible" in salida, "E1: 'update' avisa de que el provider no esta accesible")
    conf = read(config)
    mole_conf = conf["provider"].get("mole") or {}
    check(mole_conf.get("options", {}).get("apiKey") == "sk-mol-secreta",
          "E1: 'update' escribe la api key aunque este caido")
    check(mole_conf.get("models", {}).get("qwen3:14b", {}).get("tool_call") is True,
          "E1: 'update' escribe las capacidades")
    check(conf["provider"]["vecino"]["name"] == "Vecino", "E1: los demas providers intactos")


# ---------------------------------------------------------------- renombrados raros --
def scenario_rename_without_config(home: Path, config: Path):
    """Renombrar provider/modelo que aun no estan en opencode.json."""
    print("\n=== E2: renombrar sin estar en opencode.json ===")
    write_json(config, vecino_config())
    write_json(home / "provider_cache.json", mole_cache())
    antes = read(config)

    run(home, config, "rename", "mole", "--name", "Mole Nuevo")
    cache = read(home / "provider_cache.json")
    conf = read(config)
    check(cache["providers"]["mole"]["name"] == "Mole Nuevo",
          "E2: el rename del provider llega a la caché")
    check("mole" not in conf["provider"],
          "E2: no crea el provider en opencode.json por renombrar (eso lo hace update)")
    check(conf["provider"]["vecino"] == antes["provider"]["vecino"],
          "E2: y no toca a los demas")

    run(home, config, "model", "name", "mole", "qwen3:14b", "--name", "Qwen Re_nombrado")
    cache = read(home / "provider_cache.json")
    conf = read(config)
    check(cache["providers"]["mole"]["models"]["qwen3:14b"]["name"] == "Qwen Re_nombrado",
          "E2: el rename del modelo llega a la caché")
    check("mole" not in conf["provider"], "E2: el rename del modelo tampoco inventa config")
    check(not backups(home, config), "E2: sin escritura de config, sin backup")

    # Y cuando si existe en el config, se actualizan los dos sitios
    run(home, config, "model", "name", "vecino", "default", "--name", "El Del Vecino")
    conf = read(config)
    check(conf["provider"]["vecino"]["models"]["default"]["name"] == "El Del Vecino",
          "E2: si estaba en opencode.json, ahi queda aplicado tambien")


def backups(home, config):
    return sorted(config.parent.glob(config.name + ".bak.*"))


# ------------------------------------------------------------------ migracion v1 --
def scenario_migrate_v1_rara(home: Path, config: Path):
    """Caché v1 con lista de modelos y claves de models.dev + thinkingLevelMap."""
    print("\n=== E3: migrar una caché v1 con claves raras ===")
    write_json(config, {"$schema": "https://opencode.ai/config.json"})
    v1 = {
        "cache_version": 1,
        "cache_timestamp": 1600000000,
        "providers": {
            "raro": {
                "name": "Raro",
                "provider_type": "vllm",
                "baseUrl": "http://127.0.0.1:11434",
                "apiKey": "sk-raro",
                "models": [
                    {
                        "id": "m1",
                        "name": "Eme Uno",
                        "capabilities": {"tools": True, "input": ["text", "image"],
                                         "output": ["text"], "reasoning": True},
                        "toolcall": True,
                        "thinkingLevelMap": {"low": 0.2},
                        "limit": {"context": "128k"},
                    },
                    "m2",
                ],
            }
        },
    }
    write_json(home / "provider_cache.json", v1)

    run(home, config, "model", "list", "raro")

    cache = read(home / "provider_cache.json")
    check(cache.get("cache_version") == 2, "E3: la caché se migra a v2 y se guarda")
    raro = cache["providers"]["raro"]
    check(bool(raro.get("uid")), "E3: se genera uid en la migracion")
    check(isinstance(raro.get("models"), dict), "E3: los modelos pasan de lista a objeto")

    m1 = raro["models"]["m1"]
    check(m1.get("tool_call") is True, "E3: capabilities.tools/toolcall -> tool_call")
    check("toolcall" not in m1, "E3: desaparece la forma 'toolcall'")
    check("capabilities" not in m1, "E3: desaparece 'capabilities' de la caché")
    check(m1.get("modalities", {}).get("input") == ["text", "image"],
          "E3: capabilities.input -> modalities.input")
    check(m1.get("modalities", {}).get("output") == ["text"],
          "E3: capabilities.output -> modalities.output")
    check(m1.get("reasoning") is True, "E3: capabilities.reasoning -> reasoning")
    check(m1.get("limit", {}).get("context") == "128k",
          "E3: en la caché el limite queda tal cual (se convierte al escribir)")
    check(m1.get("thinkingLevelMap") == {"low": 0.2},
          "E3: lo desconocido se conserva en la caché, no se tira")
    check(m1.get("name") == "Eme Uno", "E3: conserva el nombre escrito a mano")
    check(raro["models"]["m2"].get("name") == "m2", "E3: un id suelto gana su propio nombre")
    check(raro.get("apiKey") == "sk-raro", "E3: la api key sobrevive a la migracion")

    run(home, config, "update", "raro")
    conf = read(config)
    escrito = conf["provider"]["raro"]["models"]["m1"]
    check(escrito.get("limit", {}).get("context") == 131072,
          "E3: '128k' se escribe como 131072 en opencode.json")
    check("thinkingLevelMap" not in escrito,
          "E3: lo que no esta en el esquema de opencode no se escribe")
    check(escrito.get("tool_call") is True, "E3: tool_call si se escribe")
    check(escrito.get("modalities", {}).get("input") == ["text", "image"],
          "E3: las modalidades se escriben")
    check("capabilities" not in escrito, "E3: la forma plural no se cuela en el singular")


# --------------------------------------------------------------------- empaquetado --
def scenario_empaquetado(home: Path, config: Path):
    """Que el paquete no vuelva a registrar un ejecutable que tape a opencode."""
    print("\n=== E4: empaquetado y version ===")
    toml = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    bloque = toml.split("[project.scripts]", 1)[1].split("[", 1)[0]
    claves = re.findall(r'(?m)^([a-zA-Z0-9_-]+)\s*=', bloque)

    check("opencode" not in claves,
          "E4: ya no registra un ejecutable 'opencode' (tapaba el CLI real)")
    check("ocm" in claves, "E4: registra 'ocm' (el nombre con que se le usa)")
    check("opencode-config-manager" in claves, "E4: mantiene el nombre largo del paquete")

    version_toml = re.search(r'(?m)^version = "([^"]+)"', toml).group(1)
    from opencode_config_manager._version import __version__

    check(version_toml == __version__,
          f"E4: pyproject ({version_toml}) y _version.py ({__version__}) coinciden")

    salida = run_cap(home, config, "--version")
    check(f"v{__version__}" in salida or __version__ in salida,
          "E4: ocm --version muestra la version del paquete")

    spec = (RAIZ / "opencode-config-manager.spec").read_text(encoding="utf-8")
    paquete = RAIZ / "src" / "opencode_config_manager"
    esperados = [f"opencode_config_manager.{p.stem}" for p in paquete.glob("*.py")
                 if p.stem not in ("__init__", "__main__")]
    esperados += [f"opencode_config_manager.commands.{p.stem}"
                  for p in (paquete / "commands").glob("*.py") if p.stem != "__init__"]
    ausentes = [mod for mod in esperados if f"'{mod}'" not in spec]
    check(not ausentes, f"E4: el .spec lista todos los modulos ({ausentes or 'ok'})")

    # Y los comandos nuevos siguen registrados en el parser
    from opencode_config_manager.cli import create_parser

    parser = create_parser()
    ayuda = parser.format_help()
    for comando in ("configure", "model", "config", "update", "new"):
        check(comando in ayuda, f"E4: el comando {comando} sigue en el parser")


def main_tests():
    escenarios = [
        ("escaneo con provider caido", scenario_scan_down),
        ("renombrar sin config", scenario_rename_without_config),
        ("migracion de caché v1 rara", scenario_migrate_v1_rara),
        ("empaquetado", scenario_empaquetado),
    ]

    for nombre, fn in escenarios:
        home = Path(tempfile.mkdtemp(prefix="ocm-test-e-"))
        print(f"\n=== escenario: {nombre} ===")
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
