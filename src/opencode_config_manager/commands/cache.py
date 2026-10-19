"""
Comandos de gestión de caché (provider_cache.json).
"""

from datetime import datetime

from ..config import Colors, ConfigManager, ConfigUI
from .provider import print_provider_cache_info
from .utils import (
    ETIQUETA_FUENTE,
    ask_tipo_menu,
    estado_tipo,
    parse_tipo_arg,
)


def _linea_tipo(estado: dict) -> str:
    """'vllm  (fijado a mano · /v1/models)' para las listas de providers."""
    notas = []
    if estado["fuente"]:
        notas.append(ETIQUETA_FUENTE[estado["fuente"]])
    if estado["evidencia"]:
        notas.append(estado["evidencia"])
    texto = estado["tipo"] or Colors.YELLOW + "sin definir" + Colors.RESET
    return texto + (f"  ({' · '.join(notas)})" if notas else "")


def cmd_cache_type(manager: ConfigManager, args):
    """`ocm cache type [PROVIDER] [TIPO]`: decir si un provider es Ollama o vLLM.

    Es un dato de ocm, no de opencode: solo cambia que endpoint se escanea
    (/api/tags o /v1/models). Lo que opencode lee —npm, baseURL y modelos— sale
    igual con los dos tipos, porque ambos sirven la API de OpenAI bajo /v1.
    """
    manager.load_cache()

    proveedor = getattr(args, "provider", None)
    pedido = getattr(args, "tipo", None)

    if not proveedor:
        proveedores = manager.cache_data.get("providers", {})
        if not proveedores:
            print("No hay providers en la caché. Ejecuta: ocm new")
            return
        ConfigUI.print_header("Tipo de cada provider (solo afecta al escaneo de ocm)")
        for nombre in proveedores:
            estado = estado_tipo(nombre, proveedores[nombre], manager)
            url = proveedores[nombre].get("baseUrl", "N/A")
            print(f"  {nombre:<20} {url:<38} {_linea_tipo(estado)}")
        print("\nPara cambiarlo: " + Colors.CYAN + "ocm cache type <PROVIDER> <ollama|vllm|auto>"
              + Colors.RESET)
        return

    cache_info = manager.cache_data.get("providers", {}).get(proveedor)
    if cache_info is None:
        ConfigUI.print_error(f"Provider '{proveedor}' no encontrado en la caché.")
        print("Ejecuta: ocm cache list")
        return

    estado = estado_tipo(proveedor, cache_info, manager)

    if not pedido:
        ConfigUI.print_header(f"Tipo de {proveedor}")
        print(f"  URL base : {cache_info.get('baseUrl', 'N/A')}")
        print(f"  Tipo     : {_linea_tipo(estado)}")
        pedido = ask_tipo_menu("Dejarlo en", estado["tipo"])

    nuevo_tipo, valido = parse_tipo_arg(pedido)
    if not valido:
        return
    if nuevo_tipo:
        fuente = "manual"
    else:
        fuente = None
        ConfigUI.print_info("Ocm lo detectara solo en el proximo escaneo.")

    if nuevo_tipo == estado["tipo"] and fuente == estado["fuente"]:
        ConfigUI.print_info(f"'{proveedor}' ya tenia el tipo {nuevo_tipo or 'auto'}.")
        return

    if nuevo_tipo:
        cache_info["provider_type"] = nuevo_tipo
        cache_info["type_source"] = fuente
    else:
        cache_info.pop("provider_type", None)
        cache_info.pop("type_source", None)
    # La evidencia es de un escaneo; al cambiar el tipo a mano deja de valer
    cache_info.pop("type_evidence", None)

    manager.save_cache(touch=False)
    etiqueta = nuevo_tipo or "auto-deteccion"
    if not fuente:
        etiqueta += " (se detectara al escanear)"
    ConfigUI.print_success(f"{proveedor}: tipo {etiqueta}")
    print("Aplicalo al escaneo con: " + Colors.CYAN + f"ocm cache update {proveedor}"
          + Colors.RESET)


def cmd_cache_list(manager: ConfigManager, args):
    """Listar providers en la caché."""
    manager.load_cache()

    cache_timestamp = manager.cache_data.get("cache_timestamp", 0)
    timestamp_str = datetime.fromtimestamp(cache_timestamp) if cache_timestamp else "Nunca"
    ConfigUI.print_header(f"Providers en Caché (actualizada {timestamp_str})")

    providers = manager.cache_data.get("providers", {})
    if not providers:
        print("No hay providers en caché.")
        print("Ejecuta: ocm provider new  o  ocm cache update [PROVIDER]")
        return

    for provider_name, cache_info in providers.items():
        print_provider_cache_info(provider_name, cache_info)


def cmd_cache_clear(manager: ConfigManager, args):
    """Borrar toda la caché."""
    manager.load_cache()

    if ConfigUI.ask_yes_no("¿Borrar toda la caché?"):
        manager.cache_data = {"cache_timestamp": 0, "providers": {}}
        manager.save_cache()
        ConfigUI.print_success("Caché borrada.")


def cmd_cache_remove(manager: ConfigManager, args):
    """Eliminar un provider de la caché (no afecta opencode.json)."""
    manager.load_cache()

    provider_name = args.provider if hasattr(args, 'provider') and args.provider else None

    if not provider_name:
        ConfigUI.print_error("No se especificó un nombre de provider.")
        print("Uso: ocm cache rm <PROVIDER>")
        return

    providers = manager.cache_data.get("providers", {})
    if provider_name not in providers:
        ConfigUI.print_error(f"Provider '{provider_name}' no encontrado en caché.")
        print("Providers en caché:")
        for p in providers.keys():
            print(f"  - {p}")
        return

    if not ConfigUI.ask_yes_no(f"¿Eliminar provider '{provider_name}' de la caché?"):
        print("Operación cancelada.")
        return

    manager.cache_data["providers"].pop(provider_name, None)
    manager.save_cache()
    ConfigUI.print_success(f"Provider '{provider_name}' eliminado de caché.")
    ConfigUI.print_info(f"Nota: opencode.json no se ha modificado. Usa 'ocm provider rm {provider_name}' para eliminar de opencode.json.")
