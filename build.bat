@echo off
REM Script de compilación para Windows

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo === Compilando opencode-config-manager ===

REM Limpiar builds anteriores
if exist build (
    rmdir /s /q build
)
if exist dist (
    rmdir /s /q dist
)

REM Compilar usando uv run
uv run pyinstaller opencode-config-manager.spec

REM Verificar que se creó el ejecutable
if exist dist\ocm.exe (
    echo.
    echo Compilacion completada!
    echo El ejecutable esta en: dist\ocm.exe
) else (
    echo.
    echo ERROR: No se encontro el ejecutable en dist\ocm.exe
    exit /b 1
)
