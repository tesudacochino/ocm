@echo off
REM Script de compilación para Windows

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo === Compilando opencode-config-manager ===

REM Inyectar commit hash en _version.py
for /f "delims=" %%i in ('git rev-parse --short HEAD') do set GIT_HASH=%%i
if defined GIT_HASH (
    echo Commit: %GIT_HASH%
    powershell -Command "(Get-Content 'src\opencode_config_manager\_version.py') -replace '__commit__ = \"dev\"', '__commit__ = \"%GIT_HASH%\"' | Set-Content 'src\opencode_config_manager\_version.py'"
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
    powershell -Command "(Get-Content 'src\opencode_config_manager\_version.py') -replace '__commit__ = \"%GIT_HASH%\"', '__commit__ = \"dev\"' | Set-Content 'src\opencode_config_manager\_version.py'"
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
