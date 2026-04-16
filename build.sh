#!/usr/bin/env bash
# Script de compilación para Linux/macOS

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Compilando opencode-config-manager ==="

# Limpiar builds anteriores
rm -rf build dist

# Compilar usando el .spec (mismo que Windows)
uv run pyinstaller opencode-config-manager.spec

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
