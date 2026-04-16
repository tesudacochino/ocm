#!/usr/bin/env bash
# Script de compilación para Linux/macOS

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Compilando opencode-config-manager ==="

# Inyectar commit hash en _version.py
GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "")
if [ -n "$GIT_HASH" ]; then
    echo "Commit: $GIT_HASH"
    sed -i.bak "s/__commit__ = \"dev\"/__commit__ = \"$GIT_HASH\"/" src/opencode_config_manager/_version.py
fi

# Limpiar builds anteriores
rm -rf build dist

# Compilar usando el .spec
uv run pyinstaller opencode-config-manager.spec

# Restaurar _version.py
if [ -n "$GIT_HASH" ]; then
    mv src/opencode_config_manager/_version.py.bak src/opencode_config_manager/_version.py
fi

# Verificar que se creó el ejecutable
if [ -f "dist/ocm" ]; then
    echo ""
    echo "Compilación completada!"
    echo "El ejecutable está en: dist/ocm"
    chmod +x dist/ocm
else
    echo ""
    echo "ERROR: No se encontró el ejecutable en dist/ocm"
    exit 1
fi
