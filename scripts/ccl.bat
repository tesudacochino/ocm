@echo off
REM Wrapper script para Windows

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

REM Usar uv si está disponible, sino usar python
where uv >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    uv run opencode-config-manager %*
) else (
    python "%PROJECT_ROOT%\src\opencode_config_manager\main.py" %*
)
