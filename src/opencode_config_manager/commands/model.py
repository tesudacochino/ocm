"""
Comandos de gestión de modelos y nombres visibles.

ocm guarda el nombre visible (campo 'name') en la caché y lo propaga a
opencode.json. Estos comandos permiten cambiarlos sin editar el JSON a mano,
y son los que usan el asistente de reconfiguración.
"""

import json
from datetime import datetime

from ..config import ConfigManager, ConfigUI, Colors
from ..cache_models import normalize_models, set_model_option
from ..model_fields import (
    EFFECTIVE_DEFAULTS,
    describe_model,
    format_value,
    get_value,
    serialize_model,
    visible_fields,
)
from .encoded import encoded_entry, encoded_providers, provider_from_encoded
from .utils import (
    ENDPOINT_TIPO,
    ETIQUETA_FUENTE,
    create_backup,
    estado_tipo,
    provider_entry_from_config,
    refresh_cache_from_config,
)


def _cache_entry(manager: ConfigManager, provider: str) -> dict:
    manager.load_cache()
    return manager.cache_data.get("providers", {}).get(provider)


def _pick_from_list(items: list, label: str):
    """Menú numerado simple. Devuelve el item elegido o None."""
    if not items:
        return None
    if len(items) == 1:
        print(f"{label}: {items[0]}")
        return items[0]

    print(f"Selecciona {label}:")
    for index, item in enumerate(items, start=1):
        print(f"  {index}) {item}")
    while True:
        raw = ConfigUI.ask_input("Opción", "1")
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        ConfigUI.print_warning("Numero fuera de rango.")


def resolve_provider(manager: ConfigManager, provider: str = None,
                     extra_names=None) -> str:
    """Resolver el provider por argumento o preguntando entre los conocidos.

    Args:
        extra_names: nombres adicionales a ofrecer, para los providers que solo
            existen en el bloque 'providers' y aun asi se quieren listar.
    """
    manager.load_cache()
    manager.load_config()

    names = sorted(set(manager.cache_data.get("providers", {})) |
                   set(k for k, v in (manager.config_data.get("provider", {}) or {}).items()
                       if isinstance(v, dict)) |
                   set(extra_names or []))

    if provider:
        if provider in names:
            return provider
        ConfigUI.print_error(f"Provider '{provider}' no encontrado.")
        print("Providers conocidos:")
        for name in names:
            print(f"  - {name}")
        return None

    if not names:
        ConfigUI.print_error("No hay providers. Ejecuta: ocm new")
        return None

    return _pick_from_list(names, "provider")


def _sync_config_name(manager: ConfigManager, provider: str, model_id: str, name: str) -> bool:
    """Escribir el nombre visible en opencode.json si el provider ya está ahí."""
    entry = provider_entry_from_config(manager, provider)
    models = entry.get("models")
    if not isinstance(models, dict) or model_id not in models:
        return False
    model_entry = models[model_id] if isinstance(models[model_id], dict) else {}
    model_entry["name"] = name
    models[model_id] = model_entry
    entry["models"] = models
    manager.config_data.setdefault("provider", {})[provider] = entry
    manager.save_config()
    return True


def cmd_model_list(manager: ConfigManager, args):
    """Listar los modelos de un provider con su nombre visible y opciones."""
    manager.load_config()
    provider = resolve_provider(manager, getattr(args, "provider", None),
                                extra_names=list(encoded_providers(manager)))
    if not provider:
        return

    ConfigUI.print_header(f"Modelos de {provider}")

    cache_info = _cache_entry(manager, provider) or {}
    if refresh_cache_from_config(manager, provider):
        manager.save_cache(touch=False)
        cache_info = _cache_entry(manager, provider) or {}

    models = normalize_models(cache_info.get("models"))
    configured = provider_entry_from_config(manager, provider).get("models", {}) or {}

    # Si no tiene nada en el formato singular, igual vive en 'providers' (v2 codificado)
    solo_plural = False
    if not models and not configured:
        enc = encoded_entry(manager, provider)
        if enc:
            desired, notes = provider_from_encoded(provider, enc)
            configured = desired.get("models") or {}
            solo_plural = bool(configured)
            ConfigUI.print_warning(
                f"'{provider}' esta definido en 'providers', el formato codificado de v2. "
                "Opencode 2.0.x no llega a registrar estos modelos; pasalos a la forma "
                f"singular con: ocm config to-singular {provider}"
            )
            for note in notes[:4]:
                ConfigUI.print_warning(note)

    if not models and not configured:
        print("No hay modelos en caché para este provider.")
        print(f"Ejecuta: ocm cache update {provider}")
        return

    print(f"{'Modelo':<36} {'Nombre visible':<26} {'Opciones':<34} En config")
    print("-" * 108)
    for model_id in list(models) + [m for m in configured if m not in models]:
        cache_entry = models.get(model_id)
        config_entry = (configured.get(model_id) or {}) if isinstance(configured, dict) else {}
        entry = cache_entry if isinstance(cache_entry, dict) else config_entry
        if not isinstance(entry, dict):
            entry = {}
        name = entry.get("name") or model_id
        if solo_plural:
            where = "solo 'providers'"
        else:
            where = "si" if model_id in configured else "no"
        print(f"{model_id:<36} {('' if name == model_id else name):<26} "
              f"{describe_model(entry).strip():<34} {where}")

    print()
    print("Renombra con:  " + Colors.CYAN + f"ocm model name {provider} [MODELO]" + Colors.RESET)
    print("Configura con: " + Colors.CYAN + f"ocm model options {provider} [MODELO]" + Colors.RESET)


# ───────────────────────────────────────────────────────────── ficha de modelo --

# Claves que gestiona el asistente. Es la misma formula que WIZARD_OWNED_KEYS de
# commands/options.py, repetida a proposito: options importa este modulo y
# importar al reves cerraria un circulo.
_PROPIAS = frozenset(spec.key.split(".")[0] for spec in visible_fields(True)) | {"name"}

# Los campos que salen siempre en la ficha, tengan valor o no
_NUCLEALES = frozenset(spec.key for spec in visible_fields(False)) - {"name"}

# La columna de etiquetas mide la etiqueta mas larga: ficha y asistente comparten
# los textos de model_fields, asi que cambiar uno mueve el otro
_ANCHO_FICHA = max(len(spec.label) for spec in visible_fields(True)) + 2
_POR_DEFECTO_NOTA = Colors.YELLOW + "  (lo asume opencode)" + Colors.RESET


def _fila(etiqueta: str, valor: str):
    """Una linea de la ficha: etiqueta alineada + valor ya coloreado."""
    print(f"  {Colors.BOLD}{etiqueta:<{_ANCHO_FICHA}}{Colors.RESET} {valor}")


def _seccion(titulo: str):
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}{titulo}{Colors.RESET}")


def _mascarar(secreto) -> str:
    texto = str(secreto)
    return "****" + texto[-4:] if len(texto) > 4 else "*" * len(texto)


def _tokens_humanos(valor) -> str:
    """131072 -> '131072 tokens (128k)', conservando el numero literal."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return str(valor)
    if numero >= 1048576 and numero % 1048576 == 0:
        return f"{numero} tokens ({numero // 1048576}M)"
    if numero >= 1024 and numero % 1024 == 0:
        return f"{numero} tokens ({numero // 1024}k)"
    return f"{numero} tokens"


def _resumen_valor(valor) -> str:
    """JSON compacto y cortado, para enseñar las claves que ocm no gestiona."""
    try:
        texto = json.dumps(valor, ensure_ascii=False)
    except (TypeError, ValueError):
        texto = str(valor)
    return texto if len(texto) <= 72 else texto[:69] + "..."


def _filas_opciones(entrada: dict, avanzado: bool):
    """Una linea por campo, con el valor que opencode va a aplicar de verdad."""
    for spec in visible_fields(avanzado):
        if spec.key == "name":
            continue  # sale arriba, en la identidad del modelo

        valor = get_value(entrada, spec.key)
        vacio = valor is None or valor == "" or valor == [] or valor == {}
        if vacio and spec.key not in _NUCLEALES and not avanzado:
            continue  # sin --advanced, las avanzadas vacias no ocupan sitio

        nota = ""
        if vacio:
            valor = EFFECTIVE_DEFAULTS.get(spec.key)
            if valor is not None:
                nota = _POR_DEFECTO_NOTA

        if valor is None:
            texto = Colors.WHITE + "sin definir" + Colors.RESET
        elif spec.kind == "bool":
            texto = Colors.BRIGHT_GREEN + "si" + Colors.RESET if valor else "no"
        elif spec.kind == "int":
            texto = _tokens_humanos(valor)
        elif spec.kind == "multi":
            items = valor if isinstance(valor, (list, tuple)) else [valor]
            texto = ", ".join(str(item) for item in items)
        else:
            texto = format_value(spec, valor)

        _fila(spec.label, texto + nota)


def cmd_model_info(manager: ConfigManager, args):
    """`ocm model info`: ficha en claro de como esta configurado un modelo.

    A diferencia de `ocm model show`, que adopta en la cache lo escrito a mano y la
    guarda, este comando es de solo lectura: se compara sobre la marcha y no escribe
    en ningun fichero.
    """
    manager.load_config()
    provider = resolve_provider(manager, getattr(args, "provider", None),
                                extra_names=list(encoded_providers(manager)))
    if not provider:
        return

    cache_info = manager.cache_data.get("providers", {}).get(provider) or {}
    models_cache = normalize_models(cache_info.get("models"))
    entrada_provider = provider_entry_from_config(manager, provider)
    models_config = entrada_provider.get("models")
    if not isinstance(models_config, dict):
        models_config = {}

    entrada_codificada = encoded_entry(manager, provider)
    modelos_plural = {}
    if entrada_codificada:
        modelos_plural = provider_from_encoded(
            provider, entrada_codificada)[0].get("models") or {}

    ids = list(dict.fromkeys(list(models_cache) + list(models_config) + list(modelos_plural)))
    if not ids:
        ConfigUI.print_error(f"'{provider}' no tiene modelos.")
        print(f"Ejecuta: ocm cache update {provider}")
        return

    model_buscado = getattr(args, "model", None) or _pick_from_list(ids, "modelo")
    if not model_buscado:
        return
    if model_buscado not in ids:
        ConfigUI.print_error(f"El modelo '{model_buscado}' no existe en '{provider}'.")
        for conocido in ids:
            print(f"  - {conocido}")
        return
    model_id = model_buscado

    def _entrada(coleccion):
        entrada = coleccion.get(model_id)
        return entrada if isinstance(entrada, dict) else None

    en_cache = _entrada(models_cache)
    en_config = _entrada(models_config)
    en_plural = _entrada(modelos_plural)

    # Lo que va a ver opencode: en las claves propias manda la cache, porque es de
    # donde escribe 'ocm update'; las ajenas se quedan como estan en el config.
    # El bloque plural ya viene traducido por provider_from_encoded: es lo que
    # 'ocm config to-singular' escribira, asi que merece verse como valor de fondo
    serializada, avisos = serialize_model(en_cache) if en_cache else ({}, [])
    efectiva = dict(en_plural or {})
    efectiva.update(en_config or {})
    for clave, valor in serializada.items():
        if clave in _PROPIAS:
            efectiva[clave] = valor
    efectiva.setdefault("name", (en_cache or en_config or en_plural or {}).get("name") or model_id)

    if getattr(args, "json", False):
        print(json.dumps(efectiva, indent=2, ensure_ascii=False))
        return

    ConfigUI.print_header(f"{provider}/{model_id}")
    _fila("Nombre visible", efectiva.get("name") or model_id)
    _fila("Resumen", describe_model(efectiva).strip() or "-")

    if en_config:
        _fila("En opencode.json", Colors.BRIGHT_GREEN + "si" + Colors.RESET +
              f"  provider.{provider}.models[\"{model_id}\"]")
    elif en_plural:
        _fila("En opencode.json", Colors.YELLOW + "solo en el bloque plural" + Colors.RESET +
              f"  providers.{provider}.models[\"{model_id}\"]")
    else:
        _fila("En opencode.json", Colors.WHITE + "no esta" + Colors.RESET +
              f"  'ocm update {provider}' lo anadira")
    if en_cache:
        _fila("En la cache", Colors.BRIGHT_GREEN + "si" + Colors.RESET)
    else:
        _fila("En la cache", Colors.YELLOW + "no esta" + Colors.RESET)

    if (manager.config_data or {}).get("model") == f"{provider}/{model_id}":
        _fila("Modelo por defecto", Colors.BRIGHT_GREEN + "si" + Colors.RESET)

    _seccion("Provider")
    opciones_provider = entrada_provider.get("options")
    opciones_provider = opciones_provider if isinstance(opciones_provider, dict) else {}

    _fila("Nombre", cache_info.get("name") or entrada_provider.get("name")
          or entrada_codificada.get("name") or provider)
    estado = estado_tipo(provider, cache_info, manager)
    if estado["tipo"] or estado["fuente"] or estado["evidencia"]:
        notas = []
        if estado["fuente"]:
            notas.append(ETIQUETA_FUENTE[estado["fuente"]])
        if estado["evidencia"]:
            notas.append("ultimo escaneo por " + estado["evidencia"])
        esperado = ENDPOINT_TIPO.get(estado["tipo"])
        if estado["evidencia"] and esperado and estado["evidencia"] != esperado:
            notas.append(Colors.YELLOW + f"el servidor no contesta a {esperado}; "
                                         f"'ocm cache type {provider} auto' lo arregla"
                         + Colors.RESET)
        detalle = f"  ({' · '.join(notas)})" if notas else ""
        valor = estado["tipo"] or (Colors.YELLOW + "sin definir" + Colors.RESET)
        _fila("Tipo", valor + detalle)
    npm = (entrada_provider.get("npm") or cache_info.get("npm")
           or entrada_codificada.get("package"))
    if npm:
        _fila("Paquete del SDK", npm)
    if cache_info.get("baseUrl"):
        _fila("URL (cache)", cache_info["baseUrl"])
    if opciones_provider.get("baseURL"):
        _fila("URL (opencode)", opciones_provider["baseURL"])

    if cache_info.get("apiKey"):
        _fila("API key", _mascarar(cache_info["apiKey"]) + "  (en la cache)")
    elif opciones_provider.get("apiKey"):
        _fila("API key", _mascarar(opciones_provider["apiKey"]) + "  (en opencode.json)")
    elif entrada_provider.get("env"):
        envs = entrada_provider["env"]
        _fila("API key", "por variable de entorno: " +
              (", ".join(envs) if isinstance(envs, (list, tuple)) else str(envs)))
    else:
        _fila("API key", Colors.YELLOW + "sin definir" + Colors.RESET)

    ultimo = cache_info.get("last_scan")
    if ultimo:
        try:
            fecha = datetime.fromtimestamp(ultimo).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError, OverflowError):
            fecha = str(ultimo)
        if cache_info.get("reachable") is False:
            _fila("Ultimo escaneo",
                  Colors.RED + "fallo: " + str(cache_info.get("last_scan_error") or "sin detalle") +
                  Colors.RESET + f"  ({fecha})")
        else:
            _fila("Ultimo escaneo", f"{fecha}  (ok)")
    else:
        _fila("Ultimo escaneo", Colors.WHITE + "nunca" + Colors.RESET +
              f"  'ocm cache update {provider}'")

    _seccion("Opciones del modelo")
    _filas_opciones(efectiva, bool(getattr(args, "advanced", False)))

    ajenas = sorted((set(en_cache or {}) | set(en_config or {})) - _PROPIAS)
    ajenas = [c for c in ajenas if not (c == "id" and (en_cache or en_config or {}).get(c) == model_id)]
    if ajenas:
        _seccion("Otras claves (el asistente no las toca)")
        for clave in ajenas:
            _fila(clave, _resumen_valor((en_config or {}).get(clave, (en_cache or {}).get(clave))))

    _seccion("Comprobaciones")
    vistos = set()
    for aviso in list(avisos) + [nota for nota in _notas_plural(provider, modelos_plural)]:
        if aviso in vistos:
            continue
        vistos.add(aviso)
        ConfigUI.print_warning(aviso)

    if en_plural and not en_config:
        print("        Opencode 2.0.x no registra los modelos que solo estan en 'providers'.")
        print("        Pásalos al bloque singular con: " + Colors.CYAN +
              f"ocm config to-singular {provider}" + Colors.RESET)

    if en_cache and en_config:
        diferencias = []
        for clave in sorted(_PROPIAS):
            esperado = serializada.get(clave)
            actual = en_config.get(clave)
            if esperado is None and actual is None:
                continue
            if (esperado or model_id) == (actual or model_id):
                continue
            diferencias.append((clave, esperado, actual))
        if diferencias:
            ConfigUI.print_warning("La cache y opencode.json no coinciden en: " +
                                   ", ".join(clave for clave, _, _ in diferencias))
            for clave, esperado, actual in diferencias:
                print(f"          {clave}: cache={_resumen_valor(esperado)} "
                      f"config={_resumen_valor(actual)}")
            print("        'ocm update' no pisa lo que hay en opencode.json; para que gane la "
                  f"cache: {Colors.CYAN}ocm update {provider} --force{Colors.RESET}")
        else:
            print(f"  {Colors.BRIGHT_GREEN}OK  la cache y opencode.json coinciden{Colors.RESET}")

    print()
    print("Editar opciones: " + Colors.CYAN + f"ocm model options {provider} {model_id}" + Colors.RESET)
    print("Renombrar:       " + Colors.CYAN + f"ocm model name {provider} {model_id}" + Colors.RESET)
    print("JSON tal cual:   " + Colors.CYAN + f"ocm model show {provider} {model_id}" + Colors.RESET)


def _notas_plural(provider: str, modelos_plural: dict) -> list:
    """Avisos del formato codificado, solo si el provider vive en el bloque plural."""
    if not modelos_plural:
        return []
    return [f"'{provider}' tiene modelos definidos en 'providers' (el formato codificado "
            f"de v2): {', '.join(sorted(modelos_plural))}"]


def cmd_model_rename(manager: ConfigManager, args):
    """Cambiar el nombre visible de un modelo (caché + opencode.json)."""
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    cache_info = _cache_entry(manager, provider)
    if cache_info is None:
        ConfigUI.print_error(f"'{provider}' no está en caché. Ejecuta: ocm new")
        return

    models = normalize_models(cache_info.get("models"))
    configured = provider_entry_from_config(manager, provider).get("models", {}) or {}
    candidates = list(models) + [m for m in configured if m not in models]

    model_id = getattr(args, "model", None) or _pick_from_list(candidates, "modelo")
    if not model_id:
        ConfigUI.print_error("Este provider no tiene modelos.")
        return

    current = (models.get(model_id) or {}).get("name") or model_id
    value = getattr(args, "name", None)
    if not value:
        value = ConfigUI.ask_input(f"Nombre visible de '{model_id}'", current)
    if value in ("-", "", None):
        value = model_id

    set_model_option(cache_info, model_id, "name", value)
    manager.save_cache()
    ConfigUI.print_success(f"Caché actualizada: '{model_id}' -> '{value}'")

    if _sync_config_name(manager, provider, model_id, value):
        ConfigUI.print_success(f"opencode.json actualizado: '{model_id}' -> '{value}'")
    else:
        ConfigUI.print_info("El modelo aún no está en opencode.json. Se aplicará con "
                            f"'ocm update {provider}'.")


def cmd_provider_rename(manager: ConfigManager, args):
    """Cambiar el nombre visible del provider (el que aparece en /models)."""
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    cache_info = _cache_entry(manager, provider)
    entry = provider_entry_from_config(manager, provider)
    current = (cache_info or {}).get("name") or entry.get("name") or provider

    value = getattr(args, "name", None)
    if not value:
        value = ConfigUI.ask_input("Nuevo nombre visible del provider", current)
    if not value:
        ConfigUI.print_error("El nombre no puede estar vacío.")
        return

    changed = False
    if cache_info is not None and cache_info.get("name") != value:
        cache_info["name"] = value
        manager.save_cache()
        changed = True
        ConfigUI.print_success(f"Caché actualizada: provider '{provider}' -> '{value}'")

    if entry and entry.get("name") != value:
        entry["name"] = value
        manager.config_data.setdefault("provider", {})[provider] = entry
        manager.save_config()
        changed = True
        ConfigUI.print_success(f"opencode.json actualizado: '{provider}' -> '{value}'")

    if not changed:
        ConfigUI.print_info(f"El provider ya se llama '{value}'.")


def cmd_model_remove(manager: ConfigManager, args):
    """`ocm model rm`: quitar un modelo de la caché y de opencode.json.

    Es el unico comando de ocm que borra un modelo. `ocm update` nunca lo hace,
    para no perder configuraciones escritas a mano.
    """
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    cache_info = _cache_entry(manager, provider) or {}
    models = normalize_models(cache_info.get("models"))
    entry = provider_entry_from_config(manager, provider)
    configured = entry.get("models")
    if not isinstance(configured, dict):
        configured = {}

    model_id = getattr(args, "model", None)
    if not model_id:
        ids = list(dict.fromkeys(list(models) + list(configured)))
        if not ids:
            ConfigUI.print_error(f"'{provider}' no tiene modelos que quitar.")
            return
        model_id = _pick_from_list(ids, "modelo a quitar")
    if not model_id:
        return

    if model_id not in models and model_id not in configured:
        ConfigUI.print_error(f"El modelo '{model_id}' no existe en '{provider}'.")
        for known in list(models) + list(configured):
            print(f"  - {known}")
        return

    usar_default = (manager.config_data or {}).get("model")
    if usar_default == f"{provider}/{model_id}":
        ConfigUI.print_warning(
            f"'{model_id}' es el modelo por defecto (clave \"model\": "
            f"\"{usar_default}\"). Tendras que elegir otro en opencode.json o con "
            "'ocm update --default'."
        )

    if not getattr(args, "yes", False):
        print(f"\nSe quitara {Colors.BOLD}{provider}/{model_id}{Colors.RESET} de:")
        print("  - provider_cache.json" + ("" if model_id in models else "  (no estaba)"))
        print("  - opencode.json" + ("" if model_id in configured else "  (no estaba)"))
        if not ConfigUI.ask_yes_no("Confirmar?", default="n"):
            ConfigUI.print_info("Cancelado.")
            return

    removed_any = False
    if model_id in models:
        models.pop(model_id)
        cache_info["models"] = models
        manager.cache_data.setdefault("providers", {})[provider] = cache_info
        manager.save_cache(touch=False)
        removed_any = True

    if model_id in configured:
        configured.pop(model_id)
        entry["models"] = configured
        create_backup(manager.config_path)
        manager.config_data.setdefault("provider", {})[provider] = entry
        manager.save_config()
        removed_any = True

    if removed_any:
        ConfigUI.print_success(f"Quitado {provider}/{model_id}.")
        print("Revisa con: " + Colors.CYAN + f"ocm model list {provider}" + Colors.RESET)
    else:
        ConfigUI.print_info("No habia nada que quitar.")
