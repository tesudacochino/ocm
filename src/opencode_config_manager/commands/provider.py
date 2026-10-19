"""
Comandos de gestión de providers: new, list, remove.
"""

import time
from datetime import datetime

from ..config import ConfigManager, ConfigUI, Colors
from ..api import ProviderScanner
from ..cache_models import ensure_uid, normalize_models
from ..model_fields import describe_model
from ..deteccion import (CLAVE_MOTOR, CLAVE_MOTOR_ANTERIOR,
                         CLAVE_MOTOR_EVIDENCIA)
from .configure import ask_api_style_fields
from .encoded import print_encoded_notice
from .update import cmd_update_provider
from .options import configure_model_entry
from .detect import proponer_en_asistente
from .scan import anotar_motor
from .utils import (
    ENDPOINT_TIPO,
    ETIQUETA_FUENTE,
    ask_tipo_menu,
    parse_tipo_arg,
    provider_entry_from_config,
    url_para_cache,
)



def print_provider_config_info(provider_name: str, provider_config: dict):
    """Mostrar información de un provider desde opencode.json."""
    name = provider_config.get("name", provider_name)
    options = provider_config.get("options", {}) or {}
    base_url = options.get("baseURL", "N/A")
    models = provider_config.get("models", {}) or {}

    print(f"{provider_name}:")
    print(f"  Nombre: {name}")
    print(f"  URL base: {base_url}")
    if options.get("apiKey"):
        print("  API Key: configurada")
    extra = sorted(set(provider_config.keys()) - {"name", "options", "models", "npm"})
    if extra:
        print(f"  Otras claves: {', '.join(extra)}")
    if models:
        print(f"  Modelos ({len(models)}):")
        for model_id, entry in models.items():
            entry = entry if isinstance(entry, dict) else {}
            display = entry.get("name") or model_id
            marker = "" if display == model_id else f" -> {display}"
            print(f"    - {model_id}{marker}{describe_model(entry)}")
    else:
        print("  Modelos: Ninguno configurado")
    print()


def print_provider_cache_info(provider_name: str, cache_info: dict):
    """Mostrar información de un provider desde la caché."""
    models = normalize_models(cache_info.get("models"))
    last_scan = cache_info.get("last_scan", 0)
    base_url = cache_info.get("baseUrl", "N/A")

    print(f"{provider_name}:")
    if cache_info.get("uid"):
        print(f"  UID: {cache_info['uid']}")
    print(f"  Nombre: {cache_info.get('name') or provider_name}")
    print(f"  URL base: {base_url}")
    tipo = cache_info.get("provider_type") or Colors.YELLOW + "sin definir" + Colors.RESET
    notas = []
    if cache_info.get("type_source") in ETIQUETA_FUENTE:
        notas.append(ETIQUETA_FUENTE[cache_info["type_source"]])
    if cache_info.get("type_evidence"):
        notas.append("último escaneo por " + cache_info["type_evidence"])
    print(f"  Tipo: {tipo}" + (f"  ({' · '.join(notas)})" if notas else ""))
    motor = cache_info.get(CLAVE_MOTOR)
    if motor:
        notas = []
        if cache_info.get(CLAVE_MOTOR_EVIDENCIA):
            notas.append(cache_info[CLAVE_MOTOR_EVIDENCIA])
        anterior = cache_info.get(CLAVE_MOTOR_ANTERIOR)
        if anterior and anterior != motor:
            notas.append(Colors.BRIGHT_YELLOW + f"ojo, antes constaba '{anterior}'"
                         + Colors.RESET)
        print(f"  Motor: {motor}" + (f"  ({' · '.join(notas)})" if notas else ""))
    if cache_info.get("apiKey"):
        print("  API Key: guardada")
    if cache_info.get("reachable") is False:
        print(f"  {Colors.BRIGHT_YELLOW}Provider no accesible en el último escaneo{Colors.RESET}")
    print(f"  Última escaneada: {datetime.fromtimestamp(last_scan) if last_scan else 'N/A'}")
    if models:
        print(f"  Modelos ({len(models)}):")
        for model_id, entry in models.items():
            display = entry.get("name") or model_id
            marker = "" if display == model_id else f" -> {display}"
            print(f"    - {model_id}{marker}{describe_model(entry)}")
    else:
        print("  Modelos: Ninguno escaneado")
    print()


def personalize_model_names(cache_entry: dict, model_ids: list, personalize=None) -> dict:
    """Asignar nombres visibles a los modelos, uno por uno.

    Enter deja el nombre actual (o el id). Es la misma interacción que usa el
    asistente de reconfiguración.
    """
    models = normalize_models(cache_entry.get("models"))

    if personalize is None:
        personalize = ConfigUI.ask_yes_no(
            "¿Personalizar el nombre que verás en /models para cada modelo?", default="n"
        )

    if personalize:
        print(f"\n{Colors.BOLD}Nombres de modelos{Colors.RESET} (Enter deja el actual, '-' usa el id):")
        for model_id in model_ids:
            current = models.get(model_id, {}).get("name") or model_id
            value = ConfigUI.ask_input(f"  Nombre de '{model_id}'", current)
            if value in ("-", model_id):
                models[model_id] = {"name": model_id}
            else:
                models[model_id] = {**(models.get(model_id) or {}), "name": value}
    else:
        # Sin personalizar, el nombre visible es el id (evita nombres huecos)
        for model_id in model_ids:
            entry = models.get(model_id) or {}
            entry.setdefault("name", model_id)
            models[model_id] = entry

    cache_entry["models"] = models
    return cache_entry


def configure_model_options_step(cache_entry: dict, model_ids: list,
                                base_url: str = None, api_key: str = None,
                                provider: str = "", detectar: bool = True) -> dict:
    """Rellenar las opciones de cada modelo: primero lo que sepa el servidor, luego a mano.

    Se consulta al servidor como hace `ocm model detect`, se enseña la propuesta y se
    pide una sola confirmacion. Lo que quede sin decidir, o lo que el usuario quiera
    revisar, pasa luego por el asistente campo a campo. Con `detectar=False` se salta
    la consulta y queda solo el asistente.
    """
    if not model_ids:
        return cache_entry

    models = normalize_models(cache_entry.get("models"))
    if base_url is None:
        base_url = cache_entry.get("baseUrl")
    if api_key is None:
        api_key = cache_entry.get("apiKey")

    escritos = 0
    if detectar:
        escritos = proponer_en_asistente(base_url, api_key, models, model_ids,
                                       provider=provider)

    if not ConfigUI.ask_yes_no(
            "¿Repasar alguna a mano (contexto, vision, herramientas)?",
            default="n"):
        if not escritos:
            ConfigUI.print_info("Puedes hacerlo luego con: ocm model options")
        cache_entry["models"] = models
        return cache_entry

    advanced = ConfigUI.ask_yes_no("¿Incluir las opciones avanzadas (temperature, adjuntos, "
                                   "experimental, estado)?", default="n")

    for model_id in model_ids:
        entry = models.setdefault(model_id, {"name": model_id})
        configure_model_entry(entry, advanced=advanced,
                              header=f"Opciones de '{model_id}'")
        print(f"{Colors.BRIGHT_GREEN}  {model_id}{describe_model(entry)}{Colors.RESET}")

    cache_entry["models"] = models
    return cache_entry


def ask_api_style(manager: ConfigManager, provider_name: str, cache_entry: dict,
                  provider_type: str, previous: dict) -> dict:
    """Elegir el paquete del SDK (chat completions o responses).

    Solo aplica a endpoints estilo OpenAI: Ollama siempre usa chat completions.
    Se guarda en la caché como `npm`, que es lo que acaba en `provider.<id>.npm`.
    """
    chosen = ask_api_style_fields({**(previous or {}), **cache_entry}, provider_type)
    if not chosen:
        return cache_entry

    cache_entry.update(chosen)

    # Si el provider ya estaba escrito, se actualiza aqui mismo: es una decision
    # explicita del usuario y 'ocm update' no pisa claves existentes.
    entry = provider_entry_from_config(manager, provider_name)
    if entry and entry.get("npm") != chosen["npm"]:
        entry["npm"] = chosen["npm"]
        manager.config_data.setdefault("provider", {})[provider_name] = entry
        manager.save_config()
        ConfigUI.print_success(f"SDK del provider: {chosen['npm']}")

    return cache_entry


def _ask_provider_name(existing_names, suggested: str = "local") -> str:
    """Pedir un nombre de provider que no esté en uso."""
    while True:
        name = ConfigUI.ask_input("Nombre del provider", suggested)
        if not name:
            ConfigUI.print_warning("El nombre no puede estar vacío.")
            continue
        if name not in existing_names:
            return name
        ConfigUI.print_warning(f"Ya existe un provider llamado '{name}'.")


def _ask_overwrite(manager: ConfigManager, provider_name: str) -> bool:
    """El provider ya existe: mostrar qué hay y preguntar si se reconfigura."""
    cached = manager.cache_data.get("providers", {}).get(provider_name)
    print(f"\n{Colors.BOLD}El provider '{provider_name}' ya existe.{Colors.RESET}")
    if cached:
        print_provider_cache_info(provider_name, cached)
        print("Se actualizará la caché y se podrán reconfigurar los nombres.")
    else:
        print_provider_config_info(provider_name, provider_entry_from_config(manager, provider_name))
        print("Existe en opencode.json pero no en caché. Se añadirá a la caché.")
    return ConfigUI.ask_yes_no(f"¿Continuar y reconfigurar '{provider_name}'?", default="y")


def cmd_provider_new(manager: ConfigManager, args):
    """Crear un nuevo provider local compatible con opencode.ai.
    El tipo de provider (ollama/vllm) se detecta automáticamente.
    Los nombres visibles del provider y de los modelos se preguntan aquí.
    """
    manager.load_config()
    manager.load_cache()

    ConfigUI.print_header("Nuevo Provider Local")

    existing_names = set(manager.cache_data.get("providers", {})) | set(
        (manager.config_data.get("provider", {}) or {})
    )

    # Nombre del provider (ej: local, ollama-home, ollama-server)
    provider_name = ConfigUI.ask_input("Nombre del provider", "local")
    if not provider_name:
        ConfigUI.print_error("El nombre del provider es obligatorio.")
        return

    if provider_name in existing_names:
        if not _ask_overwrite(manager, provider_name):
            provider_name = _ask_provider_name(existing_names, suggested=f"{provider_name}-2")

    # Nombre visible del provider: es el que aparece en el selector de /models
    # Se sugiere tal cual lo escribio el usuario: 'chispa' -> 'chispa', no 'Chispa'
    default_display = provider_name
    provider_display = ConfigUI.ask_input("Nombre visible del provider (el que muestra opencode)",
                                          default_display)

    # URL base del provider
    previous = manager.cache_data.get("providers", {}).get(provider_name, {})
    default_url = previous.get("baseUrl") or "http://127.0.0.1:11434"
    base_url = ConfigUI.ask_input("URL base del provider", default_url)

    # Quitar el /v1 del final si el usuario lo puso, para que el escaneo funcione
    base_url = url_para_cache(base_url)

    # API Key opcional (se reutiliza la guardada si aplica)
    default_key = previous.get("apiKey", "")
    api_key = ConfigUI.ask_input("API Key (dejar vacío si no requiere)", default_key)

    # Tipo de servidor: lo fija el flag --type; si no, se detecta probando endpoints
    pedido = None
    tipo_flag = getattr(args, "type", None)
    if tipo_flag:
        pedido, valido = parse_tipo_arg(tipo_flag)
        if not valido:
            return

    provider_type = None
    models = []
    evidencia = None
    fuente = None
    entradas = {}          # los JSON crudos del servidor, para detectar opciones

    if pedido:
        print(f"\nEscaneando {base_url} como {pedido}...")
        if pedido == "vllm":
            resultado = ProviderScanner.scan_vllm(base_url, api_key or None)
        else:
            resultado = ProviderScanner.scan_ollama(base_url, api_key or None)
        provider_type, fuente = pedido, "manual"
        if resultado.success:
            models, evidencia = resultado.models, ENDPOINT_TIPO[pedido]
            entradas = resultado.entradas or {}
        else:
            ConfigUI.print_error(f"No responde por {ENDPOINT_TIPO[pedido]}: {resultado.error}")
            prueba = ProviderScanner.probe(base_url, api_key or None)
            if prueba.tipo:
                ConfigUI.print_warning(
                    f"Si responde a {prueba.endpoint} ({prueba.tipo}); lo dejo en '{pedido}' "
                    f"porque lo fijaste. Para seguir al servidor: "
                    f"ocm cache type {provider_name} auto")
                models, evidencia = prueba.models, prueba.endpoint
                entradas = prueba.entradas or {}
    else:
        print("\nDetectando tipo de provider...")
        prueba = ProviderScanner.probe(base_url, api_key or None)
        provider_type, models, evidencia = prueba.tipo, prueba.models, prueba.endpoint
        entradas = prueba.entradas or {}
        fuente = "auto" if provider_type else None

    if not provider_type:
        ConfigUI.print_error(f"No se pudo detectar el provider en {base_url}")
        ConfigUI.print_error("Verifica que el servicio esté corriendo.")
        if not ConfigUI.ask_yes_no("¿Crear el provider de todos modos (sin modelos)?", default="n"):
            print("Operación cancelada.")
            return
        # Ya no se escribe a mano: se elige uno de los dos tipos validos
        provider_type = ask_tipo_menu("Tipo de servidor", con_auto=False)
        evidencia, fuente = ENDPOINT_TIPO[provider_type], "manual"
        models = list(normalize_models(previous.get("models")))
        if models:
            ConfigUI.print_info(f"Se conservan {len(models)} modelos de la caché.")

    ConfigUI.print_success(f"Provider detectado: {provider_type}")
    ConfigUI.print_success(f"URL: {base_url}")

    if models:
        ConfigUI.print_success(f"Modelos encontrados: {len(models)}")
        print("Modelos detectados:")
        for m in models:
            print(f"  - {m}")
        print()
    else:
        ConfigUI.print_info("No hay modelos en este provider por ahora.")
        print()

    # Guardar SOLO en caché (NO modificar opencode.json)
    cache_entry = dict(previous)
    cache_entry.update({
        "name": provider_display or provider_name,
        "baseUrl": base_url,
        "provider_type": provider_type,
        "type_source": fuente,
        "type_evidence": evidencia,
        "reachable": bool(models),
        "last_scan": int(time.time()) if models else previous.get("last_scan", 0),
    })
    for clave in ("type_source", "type_evidence"):
        if cache_entry.get(clave) is None:
            cache_entry.pop(clave, None)
    if api_key:
        cache_entry["apiKey"] = api_key
    else:
        cache_entry.pop("apiKey", None)
    cache_entry.pop("last_scan_error", None)
    # Se apunta ya el motor que se ha visto, para que el primer 'cache update' tenga
    # con que comparar y poder avisar si un dia cambia lo que hay detras del provider.
    anotar_motor(cache_entry, entradas, base_url, api_key or None)
    personalize_model_names(cache_entry, models)
    ask_api_style(manager, provider_name, cache_entry, provider_type, previous)
    configure_model_options_step(cache_entry, models, base_url, api_key or None,
                                 provider_name,
                                 detectar=not getattr(args, "no_detectar", False))
    ensure_uid(cache_entry)

    manager.cache_data["providers"][provider_name] = cache_entry
    manager.save_cache()

    ConfigUI.print_success(f"Provider '{provider_name}' guardado en caché (uid: {cache_entry['uid']}).")

    # Escribir en opencode.json desde aquí mismo, si el usuario quiere
    if ConfigUI.ask_yes_no("¿Actualizar opencode.json ahora?", default="y"):
        print()
        cmd_update_provider(manager, args, provider=provider_name)
    else:
        ConfigUI.print_info(f"Para actualizar opencode.json ejecuta: ocm update {provider_name}")


def cmd_provider_list(manager: ConfigManager, args):
    """Listar providers desde opencode.json."""
    manager.load_config()

    ConfigUI.print_header("Providers en opencode.json")
    print(f"Archivo: {manager.config_path}\n")

    providers = manager.config_data.get("provider", {})
    if not providers or not isinstance(providers, dict):
        print("No hay providers configurados en opencode.json.")
        print("Ejecuta: ocm update [PROVIDER]")
        print_encoded_notice(manager)
        return

    for provider_name, provider_config in providers.items():
        print_provider_config_info(provider_name, provider_config)

    print_encoded_notice(manager)


def cmd_provider_remove(manager: ConfigManager, args):
    """Eliminar un provider de opencode.json (no afecta la caché)."""
    manager.load_config()

    # Obtener el nombre del provider desde los argumentos
    provider_name = args.provider if hasattr(args, 'provider') and args.provider else None

    if not provider_name:
        ConfigUI.print_error("No se especificó un nombre de provider.")
        print("Uso: ocm rm <PROVIDER>")
        return

    # Verificar si el provider existe en opencode.json
    providers = manager.config_data.get("provider", {})
    if not isinstance(providers, dict) or provider_name not in providers:
        ConfigUI.print_error(f"Provider '{provider_name}' no encontrado en opencode.json.")
        if isinstance(providers, dict):
            print("Providers disponibles:")
            for p in providers.keys():
                print(f"  - {p}")
        return

    if not ConfigUI.ask_yes_no(f"¿Eliminar provider '{provider_name}' de opencode.json?"):
        print("Operación cancelada.")
        return

    # Eliminar solo de opencode.json
    manager.config_data["provider"].pop(provider_name, None)

    # Si no quedan providers, limpiar el objeto provider
    if not manager.config_data.get("provider"):
        manager.config_data.pop("provider", None)

    manager.save_config()
    ConfigUI.print_success(f"Provider '{provider_name}' eliminado de opencode.json.")
    ConfigUI.print_info("La caché no se ha modificado. "
                        f"Usa 'ocm cache rm {provider_name}' para eliminarla de caché.")
