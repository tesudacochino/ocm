"""
Comandos de escaneo de providers.

El tipo ('ollama' | 'vllm') solo decide que endpoint se escanea; no afecta a lo
que opencode lee de opencode.json (los dos sirven la API de OpenAI bajo /v1).
"""

import time
from datetime import datetime

from ..config import ConfigManager, ConfigUI, Colors
from ..api import ProviderScanner
from ..cache_models import merge_scanned_models, normalize_models
from ..deteccion import (
    CLAVE_MOTOR,
    CLAVE_MOTOR_ANTERIOR,
    CLAVE_MOTOR_DESDE,
    CLAVE_MOTOR_EVIDENCIA,
    Explorador,
    motor_de,
)
from .utils import (
    ENDPOINT_TIPO,
    ETIQUETA_FUENTE,
    OTRO_TIPO,
    estado_tipo,
    normalizar_tipo,
)


def anotar_motor(cached_info: dict, entradas: dict, base_url: str,
                 api_key: str = None) -> tuple:
    """Apuntar en la caché qué motor hay detras del provider, y avisar si cambio.

    Es informativo: opencode no lee nada de aqui. Pero saber si detras del provider
    hay ollama, llama.cpp, vLLM o SGLang cambia lo que se le puede pedir (vision,
    tools, contexto), asi que la primera vez se cuenta y cuando se tuerce se avisa.

    `servidor_anterior` es una nota pendiente de revisar: si el escaneo siguiente
    vuelve a ver el mismo motor, se da por confirmado y se quita.
    """
    motor, evidencia = (None, None)
    if entradas:
        motor, evidencia = motor_de(entradas)
        if motor is None:
            # La lista no dice nada: /props delata a llama-server, una peticion y listo
            motor, evidencia = motor_de(
                entradas, Explorador(base_url, api_key).json("/props"))

    anterior = cached_info.get(CLAVE_MOTOR)
    if motor and anterior and anterior != motor:
        ConfigUI.print_warning(
            f"  Ojo, el motor parece otro: en la cache constaba '{anterior}' y ahora "
            f"responde como '{motor}' ({evidencia}).")
    elif motor and not anterior:
        print(f"  Motor: {motor}  ({evidencia})")

    if motor:
        cached_info[CLAVE_MOTOR] = motor
        cached_info[CLAVE_MOTOR_EVIDENCIA] = evidencia
        if anterior and anterior != motor:
            cached_info[CLAVE_MOTOR_ANTERIOR] = anterior
            cached_info[CLAVE_MOTOR_DESDE] = int(time.time())
        elif not anterior:
            cached_info[CLAVE_MOTOR_DESDE] = int(time.time())
        elif CLAVE_MOTOR_ANTERIOR in cached_info:
            cached_info.pop(CLAVE_MOTOR_ANTERIOR)
            cached_info.pop(CLAVE_MOTOR_DESDE, None)
    return motor, evidencia


def _escanear_como(base_url: str, api_key: str, tipo: str) -> tuple:
    """Escanear con un tipo concreto -> (modelos, endpoint_usado, error, entradas)."""
    if tipo == "vllm":
        resultado = ProviderScanner.scan_vllm(base_url, api_key)
    else:
        resultado = ProviderScanner.scan_ollama(base_url, api_key)
    if resultado.success:
        return resultado.models, ENDPOINT_TIPO.get(tipo), None, (resultado.entradas or {})
    return [], None, resultado.error or "no responde", {}


def scan_single_provider(provider_name: str, cached_info: dict, manager: ConfigManager,
                         config_data: dict, current_time: int, tipo: str = None) -> bool:
    """Escanear un provider individual y actualizar su caché.

    Solo toca los campos que dependen del escaneo (models, last_scan, reachable,
    y baseUrl/provider_type/uid si faltaban). La api key, el nombre visible y las
    opciones por modelo se conservan.

    Args:
        tipo: 'ollama', 'vllm' para fijar el endpoint de esta pasada, 'auto' para
            volver a detectarlo, o None para usar lo que dice la caché.

    Returns:
        True si el escaneo fue exitoso, False en caso de error.
    """
    base_url = cached_info.get("baseUrl")
    api_key = cached_info.get("apiKey")

    if not base_url:
        ConfigUI.print_error(f"El provider '{provider_name}' no tiene URL base en caché.")
        if cached_info:
            cached_info["reachable"] = False
        return False

    pedido = None
    if tipo:
        texto = str(tipo).strip().lower()
        if texto != "auto":
            pedido = normalizar_tipo(texto)
            if not pedido:
                ConfigUI.print_error(f"Tipo '{tipo}' desconocido; vale 'ollama', 'vllm' o 'auto'.")
                return False

    estado = estado_tipo(provider_name, cached_info, manager)
    guardado = estado["tipo"]
    fuente = estado["fuente"]
    # '--type auto' revoca un fijado anterior: esta pasada manda lo que diga el servidor
    forzar = bool(tipo) and str(tipo).strip().lower() == "auto"
    fijado = fuente == "manual" and not forzar
    se_detecto = False

    print(f"\nEscaneando {provider_name} en {base_url}...")

    modelos = []
    entradas = {}
    endpoint = None
    tipo_usado = pedido or (None if forzar else guardado)

    if tipo_usado:
        modelos, endpoint, error, entradas = _escanear_como(base_url, api_key, tipo_usado)
        if error:
            alternativo = OTRO_TIPO[tipo_usado]
            print(f"  {Colors.YELLOW}no responde a {ENDPOINT_TIPO[tipo_usado]} ({error}); "
                  f"pruebo {ENDPOINT_TIPO[alternativo]}...{Colors.RESET}")
            modelos_alt, endpoint_alt, error_alt, entradas_alt = _escanear_como(
                base_url, api_key, alternativo)
            if error_alt:
                ConfigUI.print_error(f"Error al escanear: {error} "
                                     f"(tampoco responde a {ENDPOINT_TIPO[alternativo]}: {error_alt})")
                cached_info["reachable"] = False
                cached_info["last_scan_error"] = error
                return False
            if pedido or fijado:
                # Alguien lo fijo a mano: se escanea con lo que hay, pero no se cambia
                ConfigUI.print_warning(
                    f"El servidor responde a {endpoint_alt}, pero tienes el tipo fijado en "
                    f"'{tipo_usado}': escaneo con {endpoint_alt} y lo dejo igual. Para seguir "
                    f"al servidor: ocm cache type {provider_name} auto")
                modelos, endpoint, entradas = modelos_alt, endpoint_alt, entradas_alt
            else:
                ConfigUI.print_warning(
                    f"La caché decia '{tipo_usado}' pero el servidor responde a {endpoint_alt}: "
                    f"lo cambio a '{alternativo}'.")
                tipo_usado, modelos, endpoint, entradas = (alternativo, modelos_alt,
                                                          endpoint_alt, entradas_alt)
                fuente, se_detecto = "auto", True
    else:
        if forzar:
            print("  Me lo pediste: pruebo los dos endpoints...")
        else:
            print("  No se que tipo es; pruebo los dos endpoints...")
        prueba = ProviderScanner.probe(base_url, api_key)
        if not prueba.tipo:
            detalle = "; ".join(f"{clave}: {valor}" for clave, valor in prueba.errores.items())
            ConfigUI.print_error(f"Error al escanear: {detalle or 'ningun endpoint responde'}")
            cached_info["reachable"] = False
            cached_info["last_scan_error"] = detalle or "ningun endpoint responde"
            return False
        tipo_usado, modelos, endpoint = prueba.tipo, prueba.models, prueba.endpoint
        entradas = prueba.entradas or {}
        se_detecto = True
        if fijado:
            ConfigUI.print_warning(
                f"Lo tienes fijado en '{guardado}' pero el servidor responde a {endpoint}: "
                f"escaneo con {endpoint} sin cambirlo. Para seguir al servidor: "
                f"ocm cache type {provider_name} auto")
            tipo_usado = guardado

    etiqueta = ETIQUETA_FUENTE.get(fuente, "sin fijar")
    if pedido or fijado:
        etiqueta = ETIQUETA_FUENTE["manual"]
    elif se_detecto:
        etiqueta = ETIQUETA_FUENTE["auto"]
    print(f"  Tipo: {tipo_usado}  ({etiqueta}, {endpoint})")

    old_models = normalize_models(cached_info.get("models"))

    new_models, added, removed = merge_scanned_models(old_models, modelos)

    print(f"  Modelos: {len(new_models)}")
    if added:
        added_str = ', '.join(f'+ {m}' for m in added)
        print(f"  {Colors.BRIGHT_GREEN}Nuevos:{Colors.RESET} {added_str}")
    if removed:
        removed_str = ', '.join(f'- {m}' for m in removed)
        print(f"  {Colors.BRIGHT_RED}Eliminados del provider:{Colors.RESET} {removed_str}")
        if config_data and provider_name in (config_data.get("provider", {}) or {}):
            print(f"  {Colors.YELLOW}Nota:{Colors.RESET} 'ocm update' no borra modelos ya escritos; "
                  f"quítalos con 'ocm model rm {provider_name} <MODELO>' o con "
                  f"'ocm configure {provider_name}', que ofrece la limpieza.")

    # Que motor hay detras (ollama, llama.cpp, vLLM, SGLang...): es solo informativo,
    # pero si ha cambiado conviene decirlo, porque cambia lo que se puede preguntar.
    anotar_motor(cached_info, entradas, base_url, api_key)

    # Actualizar caché preservando uid, nombre visible, api key y opciones por modelo
    cached_info["models"] = new_models
    cached_info["last_scan"] = current_time
    cached_info["provider_type"] = tipo_usado
    cached_info["type_evidence"] = endpoint
    if pedido or fijado:
        cached_info["type_source"] = "manual"
    elif se_detecto:
        cached_info["type_source"] = "auto"
    cached_info["reachable"] = True
    cached_info.pop("last_scan_error", None)
    manager.cache_data["providers"][provider_name] = cached_info

    return True


def cmd_scan(manager: ConfigManager, args):
    """Escanear providers y actualizar caché."""
    manager.load_cache()
    manager.load_config()

    # Si se especificó un provider específico
    provider = getattr(args, 'provider', None)
    tipo = getattr(args, 'type', None)
    current_time = int(time.time())

    if provider:
        # Escanear provider específico
        ConfigUI.print_header(f"Escaneando: {provider}")
        cached_info = manager.cache_data["providers"].get(provider)
        if cached_info is None:
            ConfigUI.print_error(f"Provider '{provider}' no encontrado en caché.")
            print("Ejecuta: ocm new para crearlo o 'ocm cache list' para ver los disponibles.")
            return
        scan_single_provider(provider, cached_info, manager, manager.config_data,
                             current_time, tipo=tipo)
    else:
        if tipo:
            ConfigUI.print_error("--type necesita un provider concreto: ocm cache update <PROVIDER> --type <TIPO>")
            return
        # Escanear todos los providers guardados en caché
        if not manager.cache_data.get("providers"):
            ConfigUI.print_error("No hay providers para escanear.")
            print("Ejecuta: ocm new para crear un provider primero.")
            return

        ConfigUI.print_header("Escaneando todos los providers")
        for provider_name, cached_info in manager.cache_data["providers"].items():
            scan_single_provider(provider_name, cached_info, manager, manager.config_data,
                                 current_time)

    # Guardar caché
    manager.cache_data["cache_timestamp"] = current_time
    manager.save_cache()
    ConfigUI.print_success(f"Caché actualizada a {datetime.fromtimestamp(current_time)}")
