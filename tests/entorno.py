"""Puesta a punto del entorno para las suites de regresion de ocm.

Los tests son scripts sueltos (sin pytest): cada uno hace `import entorno` despues
de meter `src` en el path y llama a lo que necesite.
"""

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from opencode_config_manager import deteccion
from opencode_config_manager.cli import main


def sin_registro_models_dev():
    """Dejar el registro de models.dev como si opencode nunca lo hubiera descargado.

    `ocm model detect` y los asistentes rellenan opciones con ese fichero, que vive
    en el home del usuario y no depende de ocm. Si se deja el que haya en cada
    maquina, la deteccion encuentra valores distintos segun donde se lancen los
    tests: cambia lo que se escribe y hasta cuantas respuestas se gasta el
    asistente. Las pruebas que si quieren registro (Fase G) lo montan ellas mismas
    con `deteccion.RUTA_REGISTRO`.
    """
    deteccion.RUTA_REGISTRO = str(
        Path(tempfile.gettempdir()) / "ocm-sin-registro-models.json")
    deteccion._INDICE.clear()
    deteccion._AVISO_REGISTRO = None


# ------------------------------------------------------------- helpers comunes --
CHECKS = []


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


def backups(home, config):
    return sorted(config.parent.glob(config.name + ".bak.*"))
