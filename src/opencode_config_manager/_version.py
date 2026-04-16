"""
Información de versión.
En desarrollo se lee el hash de git. En compilado se inyecta por el build script.
"""

__version__ = "1.0.0"
__commit__ = "dev"


def get_version_string() -> str:
    """Obtener string de versión con commit hash."""
    commit = __commit__
    if commit == "dev":
        # Intentar leer desde git en desarrollo
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
        except Exception:
            pass
    return f"OpenCode Manager v{__version__} ({commit})"
