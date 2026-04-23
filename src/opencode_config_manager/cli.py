"""
CLI - Interfaz de línea de comandos
"""

import sys
import os

# Forzar UTF-8 para Windows (compilado con PyInstaller)
if sys.platform == "win32":
    try:
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")
    except Exception:
        pass

import argparse
from pathlib import Path

from .config import ConfigManager
from ._version import get_version_string
from .commands.provider import cmd_provider_new, cmd_provider_list, cmd_provider_remove
from .commands.scan import cmd_scan
from .commands.update import cmd_update_provider, cmd_update_global
from .commands.cache import cmd_cache_list, cmd_cache_clear, cmd_cache_remove
from .commands.debug import cmd_debug_config


def create_parser() -> argparse.ArgumentParser:
    """Crear el parser de argumentos CLI."""
    version_str = get_version_string()
    parser = argparse.ArgumentParser(
        description=f"{version_str} - Gestor de providers locales para opencode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Ejemplos:
  ocm new                          # Crear nuevo provider
  ocm list                         # Listar providers configurados
  ocm rm <nombre>                  # Eliminar un provider
  ocm update [PROVIDER]            # Actualizar configuración de opencode
  ocm cache update [PROVIDER]      # Escanear APIs y actualizar caché
  ocm cache list                   # Listar providers en caché
  ocm cache rm <nombre>            # Eliminar provider de caché
  ocm cache clear                  # Borrar toda la caché
  ocm config validate              # Validar integridad de la configuración

Flujo típico:
  ocm new  →  ocm cache update  →  ocm update  →  ocm list
        """
    )

    parser.add_argument(
        "--version", "-V",
        action="version",
        version=get_version_string()
    )

    parser.add_argument(
        "--config", "-c",
        type=Path,
        help="Ruta al archivo opencode.json (default: ~/.config/opencode/opencode.json)"
    )
    parser.add_argument(
        "--home",
        type=Path,
        help="Directorio base para configuración y caché (default: ~/.config/opencode)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # ── Comandos principales (opencode.json) ─────────────────────────
    subparsers.add_parser("new", help="Crear nuevo provider")
    subparsers.add_parser("list", aliases=["ls"], help="Listar providers configurados")

    rm_parser = subparsers.add_parser("remove", aliases=["rm"], help="Eliminar un provider")
    rm_parser.add_argument("provider", help="Nombre del provider a eliminar")

    update_parser = subparsers.add_parser("update", help="Actualizar configuración de opencode con la caché")
    update_parser.add_argument("provider", nargs="?", help="Provider a actualizar (todos si no se especifica)")

    # ── Grupo: cache (provider_cache.json) ───────────────────────────
    cache_parser = subparsers.add_parser("cache", help="Gestión de caché de providers")
    cache_sub = cache_parser.add_subparsers(dest="cache_command", help="Comandos de caché")
    cache_update = cache_sub.add_parser("update", help="Escanear APIs y actualizar caché")
    cache_update.add_argument("provider", nargs="?", help="Provider específico (opcional)")
    cache_sub.add_parser("list", aliases=["ls"], help="Listar providers en caché")
    cache_rm = cache_sub.add_parser("remove", aliases=["rm"], help="Eliminar provider de caché")
    cache_rm.add_argument("provider", help="Nombre del provider a eliminar")
    cache_sub.add_parser("clear", help="Borrar toda la caché")

    # ── Grupo: config (opencode.json - operaciones avanzadas) ────────
    config_parser = subparsers.add_parser("config", help="Operaciones avanzadas de configuración")
    config_sub = config_parser.add_subparsers(dest="config_command", help="Comandos de configuración")
    config_sub.add_parser("validate", help="Validar integridad de la configuración")

    # ── Alias oculto: debug config → config validate ─────────────────
    debug_parser = subparsers.add_parser("debug")
    debug_sub = debug_parser.add_subparsers(dest="debug_command")
    debug_sub.add_parser("config")
    subparsers._choices_actions = [a for a in subparsers._choices_actions if a.dest != "debug"]

    # ── Alias oculto: scan → cache update ────────────────────────────
    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("provider", nargs="?", help="Provider específico (opcional)")
    subparsers._choices_actions = [a for a in subparsers._choices_actions if a.dest != "scan"]

    return parser


def main(args: list = None):
    """Punto de entrada principal."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        return 1

    manager = ConfigManager(config_path=parsed_args.config, home_path=parsed_args.home)

    # ── Comandos principales (opencode.json) ─────────────────────────
    if parsed_args.command == "new":
        cmd_provider_new(manager, parsed_args)

    elif parsed_args.command in ("list", "ls"):
        cmd_provider_list(manager, parsed_args)

    elif parsed_args.command in ("remove", "rm"):
        cmd_provider_remove(manager, parsed_args)

    elif parsed_args.command == "update":
        if getattr(parsed_args, "provider", None):
            cmd_update_provider(manager, parsed_args)
        else:
            cmd_update_global(manager, parsed_args)

    # ── Grupo: cache ─────────────────────────────────────────────────
    elif parsed_args.command in ("cache", "scan"):
        # "scan" es alias oculto de "cache update"
        if parsed_args.command == "scan":
            cmd_scan(manager, parsed_args)
        else:
            sub = getattr(parsed_args, "cache_command", None)
            if sub == "update":
                cmd_scan(manager, parsed_args)
            elif sub == "clear":
                cmd_cache_clear(manager, parsed_args)
            elif sub in ("list", "ls"):
                cmd_cache_list(manager, parsed_args)
            elif sub in ("remove", "rm"):
                cmd_cache_remove(manager, parsed_args)
            else:
                # Sin subcomando → mostrar lista de caché
                cmd_cache_list(manager, parsed_args)

    # ── Grupo: config ────────────────────────────────────────────────
    elif parsed_args.command == "config":
        sub = getattr(parsed_args, "config_command", None)
        if sub == "validate":
            cmd_debug_config(manager, parsed_args)
        else:
            print("Uso: ocm config validate")
            return 1

    # ── Alias oculto: debug config ───────────────────────────────────
    elif parsed_args.command == "debug":
        if getattr(parsed_args, "debug_command", None) == "config":
            cmd_debug_config(manager, parsed_args)
        else:
            print("Uso: ocm config validate")
            return 1

    else:
        parser.print_help()
        return 1

    return 0
