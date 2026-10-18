@echo off
REM Script de compilación para Windows

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo === Compilando opencode-config-manager ===

REM Inyectar commit hash en _version.py (en bytes: PowerShell romperia los acentos)
for /f "delims=" %%i in ('git rev-parse --short HEAD') do set GIT_HASH=%%i
if defined GIT_HASH (
    echo Commit: %GIT_HASH%
    uv run python scripts\set_version.py %GIT_HASH%
)

REM Limpiar builds anteriores
if exist build (
    rmdir /s /q build
)
if exist dist (
    rmdir /s /q dist
)

REM Compilar usando uv run
uv run pyinstaller opencode-config-manager.spec

REM Restaurar _version.py
if defined GIT_HASH (
    uv run python scripts\set_version.py dev
)

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
