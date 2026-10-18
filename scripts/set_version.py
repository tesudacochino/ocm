"""Fijar __commit__ (y opcionalmente __version__) en _version.py de forma segura.

Lo usan build.bat / build.sh. La version antigua de build.bat lo hacia con
PowerShell `Get-Content | Set-Content`, que reescribe el archivo con la
codificacion de la consola y rompe los acentos del fichero (UTF-8 sin BOM).
Aqui se trabaja en bytes, asi que lo unico que cambia es la linea buscada.

Uso:
    python scripts/set_version.py <commit>            # fijar __commit__
    python scripts/set_version.py <commit> <version>  # y tambien __version__
"""

import re
import sys
from pathlib import Path

TARGET = (Path(__file__).resolve().parents[1] /
          "src" / "opencode_config_manager" / "_version.py")


def set_field(field: str, value: str) -> None:
    raw = TARGET.read_bytes()
    pattern = f'__{field}__ = "[^"]*"'.encode("utf-8")
    replacement = f'__{field}__ = "{value}"'.encode("utf-8")
    nuevo, veces = re.subn(pattern, replacement, raw, count=1)
    if veces == 0:
        print(f"[set_version] no se encontro __{field}__ en {TARGET}", file=sys.stderr)
        raise SystemExit(1)
    if nuevo != raw:
        TARGET.write_bytes(nuevo)
    print(f'[set_version] __{field}__ = "{value}"')


def main(argv: list) -> int:
    if len(argv) not in (2, 3):
        print("Uso: python scripts/set_version.py <commit> [version]", file=sys.stderr)
        return 2

    if argv[1] == "--show":
        raw = TARGET.read_text(encoding="utf-8")
        for campo in ("version", "commit"):
            encontrado = re.search(rf'__{campo}__ = "([^"]*)"', raw)
            print(f"__{campo}__ = {encontrado.group(1) if encontrado else '?'}")
        return 0

    set_field("commit", argv[1])
    if len(argv) == 3:
        set_field("version", argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
