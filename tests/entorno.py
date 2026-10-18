"""Puesta a punto del entorno para las suites de regresion de ocm.

Los tests son scripts sueltos (sin pytest): cada uno hace `import entorno` despues
de meter `src` en el path y llama a lo que necesite.
"""

import tempfile
from pathlib import Path

from opencode_config_manager import deteccion


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
