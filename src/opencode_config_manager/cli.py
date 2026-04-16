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
from .commands.cache import cmd_cache, cmd_show_cache
from .commands.debug import cmd_debug_config


def create_parser() -> argparse.ArgumentParser:
    """Crear el parser de argumentos CLI."""
    parser = argparse.ArgumentParser(
        description="Gestor de providers locales para opencode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  ocm new                    # Crear nuevo provider
  ocm list                   # Listar providers
  ocm rm [PROVIDER]          # Eliminar provider
  ocm scan [PROVIDER]        # Escanear provider
  ocm cache show             # Mostrar estado de la caché
  ocm cache clear            # Borrar caché
  ocm update [PROVIDER]      # Actualizar provider con caché
  ocm update                 # Actualizar todos los providers
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

    # Command: new (provider --new)
    subparsers.add_parser("new", help="Crear nuevo provider")

    # Command: list (provider --list)
    subparsers.add_parser("list", aliases=["ls"], help="Listar providers")

    # Command: remove / rm (provider --remove)
    remove_parser = subparsers.add_parser("remove", aliases=["rm"], help="Eliminar provider")
    remove_parser.add_argument("provider", help="Nombre del provider a eliminar")

    # Command: scan
    scan_parser = subparsers.add_parser("scan", help="Escanear providers y actualizar caché")
    scan_parser.add_argument("provider", nargs="?", help="Nombre del provider (opcional)")

    # Command: cache (subparsers)
    cache_parser = subparsers.add_parser("cache", help="Gestionar caché")
    cache_subparsers = cache_parser.add_subparsers(dest="cache_command", help="Comandos de caché")
    cache_show_parser = cache_subparsers.add_parser("show", help="Mostrar estado de la caché")
    cache_show_parser.add_argument("provider", nargs="?", help="Provider específico (opcional)")
    cache_subparsers.add_parser("clear", help="Borrar caché")

    # Command: debug
    debug_parser = subparsers.add_parser("debug", help="Comandos de depuración")
    debug_subparsers = debug_parser.add_subparsers(dest="debug_command", help="Comandos de debug")
    debug_subparsers.add_parser("config", help="Validar integridad de opencode.json")

    # Command: update
    update_parser = subparsers.add_parser("update", help="Actualizar opencode.json con caché")
    update_parser.add_argument("provider", nargs="?", help="Provider a actualizar (global si no se especifica)")

    return parser


def main(args: list = None):
    """Punto de entrada principal."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        return 1

    manager = ConfigManager(config_path=parsed_args.config, home_path=parsed_args.home)

    # Mapeo de comandos a funciones
    if parsed_args.command == "new":
        cmd_provider_new(manager, parsed_args)

    elif parsed_args.command in ("list", "ls"):
        cmd_provider_list(manager, parsed_args)

    elif parsed_args.command in ("remove", "rm"):
        cmd_provider_remove(manager, parsed_args)

    elif parsed_args.command == "scan":
        cmd_scan(manager, parsed_args)

    elif parsed_args.command == "cache":
        if parsed_args.cache_command == "clear":
            cmd_cache(manager, argparse.Namespace(clear=True, show=False))
        elif parsed_args.cache_command == "show":
            cmd_show_cache(manager, parsed_args)
        else:
            cmd_show_cache(manager, parsed_args)

    elif parsed_args.command == "update":
        if parsed_args.provider:
            cmd_update_provider(manager, parsed_args)
        else:
            cmd_update_global(manager, parsed_args)

    elif parsed_args.command == "debug":
        if parsed_args.debug_command == "config":
            cmd_debug_config(manager, parsed_args)
        else:
            parser.print_help()
            return 1

    else:
        parser.print_help()
        return 1

    return 0
