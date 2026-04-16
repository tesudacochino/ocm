@echo off
REM Script de instalación para Windows

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo === Instalando opencode-config-manager ===

REM Verificar uv
where uv >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    uv sync
    uv pip install -e .
) else (
    echo uv no está instalado.
    echo Para instalar uv, visita: https://github.com/astral-sh/uv
    echo Instalando con pip...
    pip install -e .
)

echo.
echo Instalacion completada!
echo Puedes usar: opencode-config-manager --help
echo O: opencode-config-manager provider --new
