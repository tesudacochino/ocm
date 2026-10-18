"""
CLI - Interfaz de línea de comandos
"""

import sys

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
from .commands.cache import (
    cmd_cache_clear,
    cmd_cache_list,
    cmd_cache_remove,
    cmd_cache_type,
)
from .commands.model import (
    cmd_model_info,
    cmd_model_list,
    cmd_model_remove,
    cmd_model_rename,
    cmd_provider_rename,
)
from .commands.configure import cmd_configure
from .commands.encoded import cmd_config_to_singular
from .commands.options import cmd_model_options, cmd_model_show
from .commands.detect import cmd_model_detect
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
  ocm cache type [PROVIDER] [TIPO] # Si es Ollama o vLLM (afecta solo al escaneo de ocm)
  ocm cache rm <nombre>            # Eliminar provider de caché
  ocm cache clear                  # Borrar toda la caché
  ocm model list [PROVIDER]        # Modelos y nombres visibles
  ocm model name [PROVIDER] [MODELO]  # Renombrar un modelo
  ocm model options [PROVIDER] [MODELO]  # Contexto, modalidades, capacidades
  ocm model options P M --set limit.context=131072 --set modalities.input=text,image
  ocm model info [PROVIDER] [MODELO]      # Ficha en claro de su configuracion
  ocm model show [PROVIDER] [MODELO]      # Su JSON tal cual
  ocm model rm [PROVIDER] [MODELO]      # Quitar un modelo que ya no esta en el servidor
  ocm configure [PROVIDER]       # Reconfigurar un provider (nombre, URL, key, modelos)
  ocm rename [PROVIDER]          # Renombrar el nombre visible de un provider
  ocm config validate              # Validar integridad de la configuración
  ocm config to-singular [PROVIDER]  # Migrar providers del bloque plural 'providers'

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
    new_parser = subparsers.add_parser("new", help="Crear o reconfigurar un provider (asistente)")
    new_parser.add_argument("--type",
                            help="Tipo de servidor: 'ollama', 'vllm' o 'auto' (por defecto auto). "
                                 "Solo cambia que endpoint escanea ocm; opencode lee lo mismo")
    subparsers.add_parser("list", aliases=["ls"], help="Listar providers configurados")

    rm_parser = subparsers.add_parser("remove", aliases=["rm"], help="Eliminar un provider")
    rm_parser.add_argument("provider", help="Nombre del provider a eliminar")

    update_parser = subparsers.add_parser("update", help="Actualizar configuración de opencode con la caché")
    update_parser.add_argument("provider", nargs="?", help="Provider a actualizar (todos si no se especifica)")
    update_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Sobrescribir las claves que gestiona ocm (por defecto solo se añaden)"
    )

    # ── Grupo: model (nombres visibles y opciones de modelo) ─────────
    model_parser = subparsers.add_parser("model", help="Gestión de modelos y nombres visibles")
    model_sub = model_parser.add_subparsers(dest="model_command", help="Comandos de modelos")
    model_list = model_sub.add_parser("list", aliases=["ls"], help="Listar modelos de un provider")
    model_list.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    model_name = model_sub.add_parser("name", aliases=["rename"], help="Cambiar el nombre visible de un modelo")
    model_name.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    model_name.add_argument("model", nargs="?", help="Modelo (se pregunta si se omite)")
    model_name.add_argument("--name", "-n", help="Nuevo nombre visible (si se omite, se pregunta)")

    model_options = model_sub.add_parser(
        "options", aliases=["opts"],
        help="Configurar las opciones de un modelo (contexto, modalidades, capacidades)")
    model_options.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    model_options.add_argument("model", nargs="?", help="Modelo (se pregunta si se omite)")
    model_options.add_argument("--all", "-a", action="store_true",
                               help="Recorrer todos los modelos del provider")
    model_options.add_argument("--advanced", action="store_true",
                               help="Incluir tambien las opciones avanzadas")
    model_options.add_argument("--set", "-s", action="append", metavar="CLAVE=VALOR",
                               help="Fijar una opcion sin preguntar (repetible), "
                                    "ej: --set limit.context=131072 --set modalities.input=text,image")

    model_show = model_sub.add_parser("show",
                                      help="Ver el JSON de las opciones de un modelo")
    model_show.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    model_show.add_argument("model", nargs="?", help="Modelo (se pregunta si se omite)")

    model_info = model_sub.add_parser("info",
                                      help="Ver la configuracion de un modelo en claro")
    model_info.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    model_info.add_argument("model", nargs="?", help="Modelo (se pregunta si se omite)")
    model_info.add_argument("--advanced", "-a", action="store_true",
                            help="Incluir las opciones avanzadas, tambien sin valor")
    model_info.add_argument("--json", action="store_true",
                            help="Volcar solo el JSON efectivo del modelo")

    model_detect = model_sub.add_parser(
        "detect",
        help="Averiguar opciones del modelo (vision, tools, contexto) preguntando al servidor")
    model_detect.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    model_detect.add_argument("model", nargs="?", help="Modelo (se pregunta si se omite)")
    model_detect.add_argument("--all", "-a", action="store_true",
                              help="Repasar todos los modelos del provider")
    model_detect.add_argument("--apply", action="store_true",
                              help="Escribir en la cache lo que se detecte (solo rellena huecos)")
    model_detect.add_argument("--force", action="store_true",
                              help="Con --apply, actualizar tambien lo que ya tenias puesto")
    model_detect.add_argument("--probar", action="store_true",
                              help="Mandar una imagen 1x1 para ver si el modelo la acepta "
                                   "(gasta una peticion minima)")
    model_detect.add_argument("--no-registro", action="store_true",
                              help="No consultar el registro de opencode (models.dev)")
    model_detect.add_argument("--json", action="store_true",
                              help="Volcar la deteccion como JSON")

    model_rm = model_sub.add_parser("rm", aliases=["remove", "del"],
                                    help="Quitar un modelo de la cache y de opencode.json")
    model_rm.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    model_rm.add_argument("model", nargs="?", help="Modelo (se pregunta si se omite)")
    model_rm.add_argument("--yes", "-y", action="store_true", help="No pedir confirmacion")

    rename_parser = subparsers.add_parser("rename", help="Cambiar el nombre visible de un provider")
    rename_parser.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    rename_parser.add_argument("--name", "-n", help="Nuevo nombre visible (si se omite, se pregunta)")

    # ── Grupo: configure (asistente de reconfiguracion) ───────────────
    configure_parser = subparsers.add_parser(
        "configure", aliases=["configurar"],
        help="Reconfigurar un provider: nombre, URL, api key, estilo de API y modelos")
    configure_parser.add_argument("provider", nargs="?", help="Provider (se pregunta si se omite)")
    configure_parser.add_argument("--name", help="Fijar el nombre visible sin preguntar")
    configure_parser.add_argument("--url", help="Fijar la URL base sin preguntar")
    configure_parser.add_argument("--api-key", help="Fijar la api key sin preguntar")
    configure_parser.add_argument("--type",
                                  help="Fijar el tipo de servidor: 'ollama', 'vllm' o 'auto' "
                                       "(afecta solo al escaneo de ocm, no a opencode.json)")
    configure_parser.add_argument("--model", help="Ir directamente a las opciones de este modelo")
    configure_parser.add_argument("--advanced", action="store_true",
                                  help="Incluir las opciones avanzadas al repasar modelos")
    configure_parser.add_argument("--no-api-style", action="store_true",
                                  help="No preguntar el estilo de API (npm)")
    configure_parser.add_argument("--no-rescan", action="store_true",
                                  help="No ofrecer un escaneo tras cambiar URL o api key")
    configure_parser.add_argument("--no-prune", action="store_true",
                                  help="No ofrecer quitar los modelos que ya no existen")

    # ── Grupo: cache (provider_cache.json) ───────────────────────────
    cache_parser = subparsers.add_parser("cache", help="Gestión de caché de providers")
    cache_sub = cache_parser.add_subparsers(dest="cache_command", help="Comandos de caché")
    cache_update = cache_sub.add_parser("update", help="Escanear APIs y actualizar caché")
    cache_update.add_argument("provider", nargs="?", help="Provider específico (opcional)")
    cache_update.add_argument("--type",
                              help="Forzar el endpoint de este escaneo: 'ollama', 'vllm' o "
                                   "'auto' para volver a detectarlo")
    cache_sub.add_parser("list", aliases=["ls"], help="Listar providers en caché")
    cache_type = cache_sub.add_parser(
        "type", aliases=["tipo"],
        help="Ver o fijar si un provider es Ollama o vLLM (solo afecta al escaneo)")
    cache_type.add_argument("provider", nargs="?", help="Provider (lista todos si se omite)")
    cache_type.add_argument("tipo", nargs="?", help="'ollama', 'vllm' o 'auto'")
    cache_rm = cache_sub.add_parser("remove", aliases=["rm"], help="Eliminar provider de caché")
    cache_rm.add_argument("provider", help="Nombre del provider a eliminar")
    cache_sub.add_parser("clear", help="Borrar toda la caché")

    # ── Grupo: config (opencode.json - operaciones avanzadas) ────────
    config_parser = subparsers.add_parser("config", help="Operaciones avanzadas de configuración")
    config_sub = config_parser.add_subparsers(dest="config_command", help="Comandos de configuración")
    config_sub.add_parser("validate", help="Validar integridad de la configuración")

    config_to_single = config_sub.add_parser(
        "to-singular", aliases=["to-single", "migrate"],
        help="Pasar providers del bloque plural 'providers' al bloque 'provider'")
    config_to_single.add_argument("provider", nargs="?", help="Provider concreto (opcional)")
    config_to_single.add_argument("--dry-run", action="store_true",
                                  help="Enseñar qué haría, sin escribir nada")
    config_to_single.add_argument("--force", action="store_true",
                                  help="Sobrescribir las claves que ya existan en 'provider'")
    config_to_single.add_argument("--drop", action="store_true",
                                  help="Quitar de 'providers' lo migrado, sin preguntar")
    config_to_single.add_argument("--keep", action="store_true",
                                  help="Dejar intactas las entradas migradas de 'providers'")
    config_to_single.add_argument("--yes", "-y", action="store_true",
                                  help="No pedir confirmación al migrar varios")

    # ── Alias oculto: debug config → config validate ─────────────────
    debug_parser = subparsers.add_parser("debug")
    debug_sub = debug_parser.add_subparsers(dest="debug_command")
    debug_sub.add_parser("config")
    subparsers._choices_actions = [a for a in subparsers._choices_actions if a.dest != "debug"]

    # ── Alias oculto: scan → cache update ────────────────────────────
    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("provider", nargs="?", help="Provider específico (opcional)")
    scan_parser.add_argument("--type",
                             help="Forzar el endpoint: 'ollama', 'vllm' o 'auto'")
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

    # ── Grupo: model / rename ────────────────────────────────────────
    elif parsed_args.command == "model":
        sub = getattr(parsed_args, "model_command", None)
        if sub in ("name", "rename"):
            cmd_model_rename(manager, parsed_args)
        elif sub in ("options", "opts"):
            cmd_model_options(manager, parsed_args)
        elif sub == "show":
            cmd_model_show(manager, parsed_args)
        elif sub == "info":
            cmd_model_info(manager, parsed_args)
        elif sub in ("detect", "det"):
            cmd_model_detect(manager, parsed_args)
        elif sub in ("rm", "remove", "del"):
            cmd_model_remove(manager, parsed_args)
        elif sub in ("list", "ls"):
            cmd_model_list(manager, parsed_args)
        else:
            cmd_model_list(manager, parsed_args)

    elif parsed_args.command == "rename":
        cmd_provider_rename(manager, parsed_args)

    # ── Grupo: configure (asistente de reconfiguracion) ──────────────
    elif parsed_args.command in ("configure", "configurar"):
        cmd_configure(manager, parsed_args)

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
            elif sub in ("type", "tipo"):
                cmd_cache_type(manager, parsed_args)
            else:
                # Sin subcomando → mostrar lista de caché
                cmd_cache_list(manager, parsed_args)

    # ── Grupo: config ────────────────────────────────────────────────
    elif parsed_args.command == "config":
        sub = getattr(parsed_args, "config_command", None)
        if sub == "validate":
            cmd_debug_config(manager, parsed_args)
        elif sub in ("to-singular", "to-single", "migrate"):
            cmd_config_to_singular(manager, parsed_args)
        else:
            print("Uso: ocm config validate | ocm config to-singular [PROVIDER]")
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
