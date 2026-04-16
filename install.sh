#!/usr/bin/env bash
# Script de instalación para Linux/macOS

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Instalando opencode-config-manager ==="

# Verificar uv
if ! command -v uv &> /dev/null; then
    echo "uv no está instalado. Instalando..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Sincronizar entorno
echo "Sincronizando entorno..."
uv sync

# Instalar como paquete editable
echo "Instalando paquete..."
uv pip install -e .

echo ""
echo "Instalación completada!"
echo "Puedes usar: opencode-config-manager --help"
echo "O: opencode-config-manager provider --new"
