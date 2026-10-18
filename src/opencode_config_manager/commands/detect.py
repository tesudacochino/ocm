"""
`ocm model detect`: proponer las opciones de un modelo mirando lo que dice el
servidor (modalidades, tool calling, tamano de contexto...).

Es una PROPUESTA: sin `--apply` no escribe nada. Con `--apply` solo rellena huecos
en la cache (lo que tu pusiste a mano se queda como estaba) y guarda, al lado de
cada valor, de donde salio, para que `ocm model info` lo pueda contar.
"""

import json

from ..api import ProviderScanner
from ..cache_models import normalize_models
from ..config import Colors, ConfigManager, ConfigUI
from ..deteccion import (CLAVE_DETECTADO, CLAVE_FUENTES, Explorador,
                         detectar_opciones, marca_detectada)
from ..model_fields import format_value, get_value, set_value, visible_fields
from .model import _pick_from_list, resolve_provider

# Lo que se puede detectar: todo menos el nombre visible, que lo pone alguien
CAMPOS = tuple(spec for spec in visible_fields(True) if spec.key != "name")
_ANCHO_CAMPO = max(len(spec.key) for spec in CAMPOS) + 2
_ANCHO_VALOR = 18


def _vacio(valor) -> bool:
    return valor is None or valor == [] or valor == {} or valor == ""


def _texto_valor(spec, valor) -> str:
    """Como se pinta el valor de un campo en la tabla (sin color, para que alinee)."""
    if _vacio(valor):
        return "-"
    return format_value(spec, valor)


def _pintar_cabecera():
    print(f"  {Colors.BOLD}{'campo':<{_ANCHO_CAMPO}}{'ahora':<{_ANCHO_VALOR}}"
          f"{'detectado':<{_ANCHO_VALOR}}de donde{Colors.RESET}")
    print("  " + "-" * (_ANCHO_CAMPO + 2 * _ANCHO_VALOR + 26))


def filas_de_un_modelo(entrada_cache: dict, det) -> list:
    """Que se escribiria en un modelo, como filas listas para pintar.

    Cada fila lleva `accion`: 'anade' (no estaba), 'igual' (coincide), 'cambia'
    (el usuario puso otra cosa) o 'respeta', que pone el comando cuando no se
    paso --force y por tanto no se toca.
    """
    filas = []
    for spec in CAMPOS:
        if spec.key not in det.valores:
            continue
        actual = get_value(entrada_cache or {}, spec.key)
        nuevo = det.valores[spec.key]
        if _vacio(actual):
            accion = "anade"
        elif actual == nuevo:
            accion = "igual"
        else:
            accion = "cambia"
        filas.append({
            "spec": spec,
            "clave": spec.key,
            "actual": actual,
            "valor": nuevo,
            "fuente": det.fuentes.get(spec.key, ""),
            "accion": accion,
            "suposicion": det.es_suposicion(spec.key),
        })
    return filas


def aplicar_filas(entrada_cache: dict, filas: list, forzar: bool) -> int:
    """Escribir en la entrada de cache lo que corresponde; devuelve cuantos valores."""
    fuentes = dict(entrada_cache.get(CLAVE_FUENTES) or {})
    escritos = 0
    for fila in filas:
        if fila["accion"] == "anade":
            set_value(entrada_cache, fila["clave"], fila["valor"])
            escritos += 1
        elif fila["accion"] == "cambia" and forzar:
            set_value(entrada_cache, fila["clave"], fila["valor"])
            escritos += 1
        if fila["accion"] in ("anade", "igual") or (fila["accion"] == "cambia" and forzar):
            fuentes[fila["clave"]] = fila["fuente"]

    if fuentes:
        entrada_cache[CLAVE_FUENTES] = fuentes
    if escritos:
        entrada_cache[CLAVE_DETECTADO] = marca_detectada()
    return escritos


def _seleccionar(args, modelos: dict, provider: str) -> list:
    """Que modelos revisar: el del argumento, todos con --all, o se pregunta."""
    ids = list(modelos)
    pedido = getattr(args, "model", None)
    if pedido:
        if pedido not in modelos:
            ConfigUI.print_error(f"El modelo '{pedido}' no existe en '{provider}'.")
            for conocido in ids:
                print(f"  - {conocido}")
            return None
        return [pedido]
    if getattr(args, "all", False) or len(ids) == 1:
        return ids
    elegido = _pick_from_list(ids, "modelo")
    return [elegido] if elegido else []


def _entradas_crudas(base_url: str, api_key: str) -> tuple:
    """Los objetos que el servidor devuelve por modelo, mezclados de los dos endpoints.

    Se piden los dos aunque solo uno sirva para escanear: en /v1/models esta
    `max_model_len` y en /api/tags estan `capabilities` y `details`, y hay servidores
    que responden a los dos con partes distintas (SGLang, llama-server).
    """
    ollama = ProviderScanner.scan_ollama(base_url, api_key)
    vllm = ProviderScanner.scan_vllm(base_url, api_key)

    entradas = {}
    for resultado in (vllm, ollama):
        if not resultado.success:
            continue
        for model_id, entrada in (resultado.entradas or {}).items():
            if model_id not in entradas:
                entradas[model_id] = dict(entrada)
                continue
            for campo, valor in entrada.items():
                if entradas[model_id].get(campo) in (None, "", [], {}):
                    entradas[model_id][campo] = valor

    fallos = [r.error for r in (ollama, vllm) if not r.success and r.error]
    return entradas, fallos


def consultar_modelos(base_url: str, api_key: str, modelos: dict, seleccion: list,
                      provider: str = "", entradas: dict = None, usar_registro: bool = True,
                      probar: bool = False, forzar: bool = False, pintar: bool = True) -> tuple:
    """Preguntar al servidor por cada modelo; devuelve (trabajos, totales).

    Cada trabajo es `{'model_id', 'entrada', 'det', 'filas'}`, y `filas` trae ya la
    accion que se tomara: 'respeta' cuando el valor lo puso el usuario y no se paso
    --force. Aqui solo se mira y se pinta; escribir lo decide quien llama, con
    `aplicar_filas`. Es la pieza que comparten `ocm model detect`, `ocm new` y
    `ocm configure`.
    """
    fallos = []
    if entradas is None:
        entradas, fallos = _entradas_crudas(base_url, api_key)
    explorador = Explorador(base_url, api_key)

    if pintar and not entradas:
        detalle = (" (" + "; ".join(fallos)[:130] + ")") if fallos else ""
        ConfigUI.print_warning("El servidor no contesto a la lista de modelos" + detalle +
                               "; se usara lo poco que se pueda saber del resto.")

    totales = {"anade": 0, "cambia": 0, "igual": 0, "respeta": 0}
    trabajos = []
    for model_id in seleccion:
        entrada_cache = modelos.get(model_id) or {}
        nombre = entrada_cache.get("name")
        det = detectar_opciones(
            base_url, api_key, model_id,
            entrada=entradas.get(model_id),
            nombre=nombre if nombre and nombre != model_id else None,
            explorador=explorador,
            usar_registro=usar_registro,
            probar=probar,
        )
        filas = filas_de_un_modelo(entrada_cache, det)
        trabajos.append({"model_id": model_id, "entrada": entrada_cache,
                         "det": det, "filas": filas})
        if not pintar:
            continue

        titulo = f"{provider}/{model_id}" if provider else model_id
        if det.servidor:
            titulo += f"   [{det.servidor}]"
        print(f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}{titulo}{Colors.RESET}")

        if not filas:
            print("  No se ha podido averiguar nada nuevo.")
        else:
            _pintar_cabecera()
            for fila in filas:
                nota = ""
                if fila["accion"] == "cambia" and not forzar:
                    fila["accion"] = "respeta"
                    nota = Colors.YELLOW + "   (ya lo tenias puesto: no se toca)" + Colors.RESET
                if fila["suposicion"]:
                    nota += Colors.YELLOW + "   (pista del nombre, no una prueba)" + Colors.RESET
                _linea(fila, nota)
                totales[fila["accion"]] = totales.get(fila["accion"], 0) + 1

        for aviso in det.avisos:
            print(Colors.YELLOW + "  ! " + aviso + Colors.RESET)

    return trabajos, totales


def aplicar_propuesta(trabajos: list, forzar: bool = False) -> int:
    """Guardar en la cache (en memoria) lo que propone `consultar_modelos`."""
    escritos = 0
    for trabajo in trabajos:
        escritos += aplicar_filas(trabajo["entrada"], trabajo["filas"], forzar)
    return escritos


def merece_deteccion(entrada: dict) -> bool:
    """Si a este modelo le conviene que se le pregunte al servidor.

    No se repite la consulta a quien ya la tiene hecha (`ocm model detect` deja la
    marca en la cache) ni a los que alguien ya configuro: para eso esta el comando,
    que se puede lanzar cuando haga falta, con --force si hace falta insistir.
    """
    if not isinstance(entrada, dict) or entrada.get(CLAVE_DETECTADO):
        return False
    for clave in ("limit", "modalities", "reasoning", "tool_call", "temperature",
                  "attachment", "experimental", "status", "options"):
        if entrada.get(clave):
            return False
    return True


def proponer_en_asistente(base_url: str, api_key: str, modelos: dict, seleccion: list,
                          provider: str = "") -> int:
    """Lo que hacen `ocm new` y `ocm configure` despues de escanear.

    Consulta al servidor (los dos endpoints, como `ocm model detect`, para ver lo
    mismo que veria el comando), enseña lo que sabe, y pregunta una sola vez si lo
    guarda. Si no se ha averiguado nada, no gasta ni una pregunta: se queda en cero
    y el asistente campo a campo seguira ofreciendose igual que antes.
    """
    seleccion = [m for m in seleccion if m in modelos]
    if not base_url or not seleccion:
        return 0

    print(f"\n{Colors.BOLD}Que sabe el servidor sobre estas opciones?{Colors.RESET}")
    trabajos, totales = consultar_modelos(base_url, api_key, modelos, seleccion,
                                          provider=provider)
    posibles = totales["anade"]
    if not posibles:
        ConfigUI.print_info("El servidor no ha aportado nada nuevo; se preguntara campo a campo.")
        return 0

    dudoso = sum(1 for t in trabajos for f in t["filas"] if f["suposicion"])
    resumen = f"{posibles} opciones para {len(seleccion)} modelo(s)"
    if dudoso:
        resumen += (f", {dudoso} de ellas solo por pistas del nombre"
                    f" {Colors.YELLOW}(a comprobar){Colors.RESET}")
    print(f"\n{Colors.BRIGHT_GREEN}Detectadas{Colors.RESET} {resumen}.")
    if not ConfigUI.ask_yes_no("¿Guardar lo detectado en la cache?", default="y"):
        ConfigUI.print_info("Se deja como estaba; puedes hacerlo luego con "
                            "'ocm model detect'.")
        return 0

    escritos = aplicar_propuesta(trabajos, forzar=False)
    print(f"{Colors.BRIGHT_GREEN}Guardadas {escritos} opcion(es) en la cache.{Colors.RESET} "
          "Falta 'ocm update' para llevarlas a opencode.json.")
    return escritos


def cmd_model_detect(manager: ConfigManager, args):
    """`ocm model detect [PROVIDER] [MODELO] [--apply] [--force] [--all] [--probar]`."""
    manager.load_config()
    provider = resolve_provider(manager, getattr(args, "provider", None))
    if not provider:
        return

    cache_info = (manager.cache_data or {}).get("providers", {}).get(provider)
    if not cache_info:
        ConfigUI.print_error(f"'{provider}' no esta en la cache.")
        print("Ejecuta:  " + Colors.CYAN + f"ocm new {provider}" + Colors.RESET +
              " (crea o reconfigura su entrada de cache)")
        return

    modelos = normalize_models(cache_info.get("models"))
    if not modelos:
        ConfigUI.print_error(f"'{provider}' no tiene modelos en la cache.")
        print("Ejecuta:  " + Colors.CYAN + f"ocm cache update {provider}" + Colors.RESET)
        return

    seleccion = _seleccionar(args, modelos, provider)
    if seleccion is None:
        return
    if not seleccion:
        return

    base_url = cache_info.get("baseUrl") or ""
    api_key = cache_info.get("apiKey")
    forzar = bool(getattr(args, "force", False))
    aplicar = bool(getattr(args, "apply", False))
    usar_registro = not getattr(args, "no_registro", False)
    probar = bool(getattr(args, "probar", False))

    quiero_json = bool(getattr(args, "json", False))

    if not quiero_json:
        ConfigUI.print_info(f"Consultando {base_url}...")

    trabajos, totales = consultar_modelos(
        base_url, api_key, modelos, seleccion,
        provider=provider,
        usar_registro=usar_registro,
        probar=probar,
        forzar=forzar,
        pintar=not quiero_json,
    )

    if quiero_json:
        volcado = [{
            "provider": provider,
            "model": trabajo["model_id"],
            "servidor": trabajo["det"].servidor,
            "valores": trabajo["det"].valores,
            "fuentes": trabajo["det"].fuentes,
            "suposiciones": trabajo["det"].suposiciones,
            "avisos": trabajo["det"].avisos,
            "aplicables": [f["clave"] for f in trabajo["filas"]
                           if f["accion"] in ("anade", "cambia")],
        } for trabajo in trabajos]
        print(json.dumps(volcado, indent=2, ensure_ascii=False))
        return

    if len(seleccion) > 1:
        print(f"\nResumen: {totales['anade']} nuevas, {totales['igual']} confirmadas, "
              f"{totales['respeta']} respetadas, {totales['cambia']} cambiadas.")

    if aplicar:
        escritos_total = aplicar_propuesta(trabajos, forzar)
        if escritos_total:
            cache_info["models"] = modelos
            manager.save_cache(touch=False)
        print()
        print(f"{Colors.BRIGHT_GREEN}{escritos_total} opcion(es) en la cache.{Colors.RESET} "
              "Aplica con: " + Colors.CYAN + f"ocm update {provider}" + Colors.RESET)
        if not forzar and totales["respeta"]:
            print("Algunos valores ya los tenias puestos: "
                  f"{Colors.CYAN}--force{Colors.RESET} los actualizaria.")
    else:
        print()
        print("Para guardarlo: " + Colors.CYAN + f"ocm model detect {provider} --apply" +
              Colors.RESET)


def _linea(fila: dict, nota: str = ""):
    """Una fila de la tabla."""
    spec = fila["spec"]
    print(f"  {spec.key:<{_ANCHO_CAMPO}}{_texto_valor(spec, fila['actual']):<{_ANCHO_VALOR}}"
          f"{_texto_valor(spec, fila['valor']):<{_ANCHO_VALOR}}{fila['fuente']}{nota}")
