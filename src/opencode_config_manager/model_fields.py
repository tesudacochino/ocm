"""
Especificación declarativa de las opciones configurables de un modelo.

Es la unica fuente de verdad para:

  * que preguntas hace el asistente (`ocm model options`, `ocm configure`) y en
    que orden,
  * como se valida/normaliza cada respuesta,
  * que claves se escriben en `provider.<id>.models.<id>` de opencode.json.

Las claves admitidas son las de `ModelConfig` en https://opencode.ai/config.json
(los nombres en camelCase, tipo `modelID` o `capabilities`, son del otro formato,
`providers` en plural; ocm escribe el formato documentado en singular).
"""

from dataclasses import dataclass, field as _dataclass_field

# Centinela: el usuario no toco ese campo, hay que dejar el que habia
KEEP = object()

MODALITIES = ("text", "audio", "image", "video", "pdf")

# Atajos que la gente suele escribir y los aceptamos igual
MODALITY_ALIASES = {
    "img": "image",
    "imagen": "image",
    "foto": "image",
    "vision": "image",
    "voice": "audio",
    "voz": "audio",
    "texto": "text",
}

CONTEXT_PRESETS = (4096, 8192, 16384, 32768, 65536, 131072, 200000, 262144, 1048576)
OUTPUT_PRESETS = (1024, 2048, 4096, 8192, 16384, 32768, 65536)

MODEL_STATUSES = ("active", "beta", "alpha", "deprecated")

TRUE_WORDS = {"y", "yes", "si", "sí", "yep", "true", "t", "1", "on", "verdadero"}
FALSE_WORDS = {"n", "no", "false", "f", "0", "off", "falso"}

# Sufijos aceptados al escribir tokens: 128k -> 131072, 1m -> 1048576
_MULTIPLIERS = {"k": 1024, "m": 1048576}


@dataclass(frozen=True)
class FieldSpec:
    """Un campo configurable de un modelo."""

    key: str
    label: str
    kind: str  # "text" | "bool" | "int" | "multi" | "choice"
    help: str = ""
    presets: tuple = _dataclass_field(default_factory=tuple)
    advanced: bool = False
    # Campo del que depende: si no tiene valor, el asistente se salta este
    depends_on: str = ""

    @property
    def parts(self) -> tuple:
        return tuple(self.key.split("."))


# Orden en el que los recorre el asistente
FIELDS: tuple = (
    FieldSpec("name", "Nombre visible en /models", "text",
              help="El nombre que muestra opencode al elegir el modelo"),
    FieldSpec("limit.context", "Tokens de contexto (entrada)", "int",
              help="Cuantos tokens admiten en total; opencode lo usa para el control de contexto",
              presets=CONTEXT_PRESETS),
    FieldSpec("limit.output", "Tokens maximos de salida", "int",
              help="Tokens que puede generar como maximo. El esquema lo pide junto con el contexto",
              presets=OUTPUT_PRESETS, depends_on="limit.context"),
    FieldSpec("modalities.input", "Entradas que acepta", "multi",
              help="text, image (vision), audio, video, pdf", presets=MODALITIES),
    FieldSpec("modalities.output", "Salidas que produce", "multi",
              help="normalmente solo text", presets=MODALITIES),
    FieldSpec("reasoning", "Es un modelo de razonamiento (thinking)", "bool"),
    FieldSpec("tool_call", "Soporta tool calling", "bool",
              help="Recomendado: sin esto opencode no le pasa herramientas"),
    FieldSpec("temperature", "Acepta parametro temperature", "bool", advanced=True),
    FieldSpec("attachment", "Acepta adjuntos", "bool", advanced=True),
    FieldSpec("experimental", "Marcar como experimental", "bool", advanced=True),
    FieldSpec("status", "Estado del modelo", "choice",
              advanced=True, presets=MODEL_STATUSES),
)

FIELDS_BY_KEY = {spec.key: spec for spec in FIELDS}

# Claves que ocm sabe escribir en opencode.json (orden estable al serializar)
SERIALIZE_ORDER = (
    "id", "name", "family", "release_date", "attachment", "reasoning",
    "temperature", "tool_call", "interleaved", "cost", "limit", "modalities",
    "experimental", "status", "provider", "options", "headers", "variants",
)

# Formas alternativas de nombrar una clave (configs escritas a mano, models.dev)
KEY_ALIASES = {
    "toolcall": "tool_call",
    "toolCall": "tool_call",
    "supportsToolCall": "tool_call",
    "capabilities.tools": "tool_call",
    "capabilities.reasoning": "reasoning",
}


def spec_for(key: str) -> FieldSpec:
    """Especificacion de un campo, aceptando sus alias."""
    return FIELDS_BY_KEY[canonical_key(key)]


def is_field(key: str) -> bool:
    return canonical_key(key) in FIELDS_BY_KEY


def canonical_key(key: str) -> str:
    """Normalizar el nombre de una clave de modelo."""
    return KEY_ALIASES.get(key, key)


def visible_fields(advanced: bool = False) -> tuple:
    """Campos que pregunta el asistente."""
    return tuple(spec for spec in FIELDS if advanced or not spec.advanced)


def parse_int(raw):
    """'4096' -> 4096, '128k' -> 131072, '1m' -> 1048576.

    Los numeros se dejan tal cual: un contexto de 128000 tokens es legitimo y no
    hay que convertirlo en 131072.
    """
    text = str(raw).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return None

    multiplier = 1
    if text[-1] in _MULTIPLIERS:
        multiplier = _MULTIPLIERS[text[-1]]
        text = text[:-1]

    return int(text) * multiplier


def parse_bool(raw):
    """Devuelve True/False, o None si no se reconoce."""
    text = str(raw).strip().lower()
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    return None


def parse_modalities(raw):
    """'text,image' | ['text', 'vision'] | '1,3' -> ['text', 'image'].

    Acepta tambien la eleccion por numero de opcion (1=text, 2=audio, ...), que es
    como se muestra en los menus del asistente.
    """
    if isinstance(raw, (list, tuple)):
        items = [str(item) for item in raw]
    else:
        items = str(raw).replace("+", ",").split(",")

    numbered = all(item.strip().isdigit() for item in items if item.strip())

    result = []
    for index, item in enumerate(items):
        text = item.strip().lower()
        if not text:
            continue
        if numbered:
            position = int(text) - 1
            if not 0 <= position < len(MODALITIES):
                raise ValueError(
                    f"opcion no valida: '{item}' (elige entre 1 y {len(MODALITIES)})")
            value = MODALITIES[position]
        else:
            value = MODALITY_ALIASES.get(text, text)
        if value not in MODALITIES:
            raise ValueError(f"modalidad no valida: '{item}' (opciones: {', '.join(MODALITIES)})")
        if value not in result:
            result.append(value)
    return result


def coerce(spec: FieldSpec, raw):
    """Validar y convertir una respuesta del usuario para un campo.

    Raises:
        ValueError: con el mensaje que se le muestra al usuario.
    """
    if spec.kind == "bool":
        value = parse_bool(raw)
        if value is None:
            raise ValueError("responde 'y' o 'n'")
        return value

    if spec.kind == "int":
        try:
            value = parse_int(raw)
        except ValueError:
            raise ValueError(f"numero invalido: '{raw}' (sirve '4096' o '128k')")
        if value is None:
            raise ValueError("falta el numero")
        if value <= 0:
            raise ValueError("debe ser mayor que 0")
        if value > 100_000_000:
            raise ValueError("demasiado grande; seguro que son tokens?")
        return value

    if spec.kind == "multi":
        return parse_modalities(raw)

    if spec.kind == "choice":
        text = str(raw).strip().lower()
        if spec.presets and text not in spec.presets:
            raise ValueError(f"elige una de: {', '.join(spec.presets)}")
        return text

    text = str(raw).strip()
    if not text:
        raise ValueError("vacío")
    return text


def get_value(entry: dict, key: str):
    """Leer un campo por su ruta ('limit.context') en una entrada de modelo."""
    node = entry
    for part in canonical_key(key).split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def set_value(entry: dict, key: str, value) -> dict:
    """Escribir (o borrar con None) un campo por su ruta.

    Al borrar deja limpiado el contenedor si se queda vacio (`limit: {}`).
    """
    parts = canonical_key(key).split(".")

    if value is None:
        node = entry
        parents = []
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                return entry
            parents.append((node, part))
            node = node[part]
        node.pop(parts[-1], None)
        for parent, part in reversed(parents):
            if parent.get(part):
                break
            parent.pop(part, None)
        return entry

    node = entry
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value
    return entry


def serialize_model(entry: dict) -> tuple:
    """Traducir la entrada de cache de un modelo a lo que va en opencode.json.

    Solo emite claves con contenido: no deja diccionarios ni listas vacias.

    Returns:
        (config, avisos)
    """
    out = {}
    warnings = []
    if not isinstance(entry, dict):
        return out, warnings

    for key in SERIALIZE_ORDER:
        if key not in entry:
            continue
        value = entry[key]
        if value is None or value == {} or value == [] or value == "":
            continue

        if key == "limit":
            clean = {}
            for side in ("context", "input", "output"):
                if value.get(side) is None:
                    continue
                try:
                    clean[side] = parse_int(value[side])
                except (ValueError, TypeError):
                    warnings.append(f"'limit.{side}' no es un numero: {value[side]!r}")
            if not clean:
                continue
            if bool(clean.get("context")) != bool(clean.get("output")):
                warnings.append(
                    "'limit' deberia incluir 'context' y 'output' juntos "
                    f"(tienes {', '.join(sorted(clean))})"
                )
            out["limit"] = clean
            continue

        if key == "modalities":
            clean = {}
            for side in ("input", "output"):
                if not (isinstance(value, dict) and value.get(side)):
                    continue
                try:
                    items = parse_modalities(value[side])
                except ValueError as error:
                    warnings.append(f"modalities.{side}: {error}")
                    continue
                if items:
                    clean[side] = items
            if clean:
                out["modalities"] = clean
            continue

        out[key] = value

    return out, warnings


def describe_model(entry: dict) -> str:
    """Resumen en una linea de las opciones de un modelo, para listados."""
    bits = []
    limit = entry.get("limit") or {}
    if limit.get("context"):
        bits.append(f"ctx={limit['context']}")
    if limit.get("output"):
        bits.append(f"out={limit['output']}")
    modalities = entry.get("modalities") or {}
    if modalities.get("input"):
        bits.append(f"in={','.join(modalities['input'])}")
    if modalities.get("output"):
        bits.append(f"out~={','.join(modalities['output'])}")
    if entry.get("reasoning"):
        bits.append("reasoning")
    if entry.get("tool_call"):
        bits.append("tools")
    if entry.get("temperature"):
        bits.append("temperature")
    if entry.get("attachment"):
        bits.append("attachment")
    if entry.get("experimental"):
        bits.append("experimental")
    if entry.get("status") and entry.get("status") != "active":
        bits.append(f"status={entry['status']}")
    if entry.get("options"):
        bits.append(f"options={len(entry['options'])}")
    if entry.get("variants"):
        bits.append(f"variants={len(entry['variants'])}")
    return f"  ({', '.join(bits)})" if bits else ""


def format_value(spec: FieldSpec, value) -> str:
    """Como se muestra un valor actual en el asistente."""
    if value is None or value == "" or value == [] or value == {}:
        return ""
    if spec.kind == "bool":
        return "si" if value else "no"
    if spec.kind == "multi":
        return ",".join(value)
    if isinstance(value, bool):
        return "si" if value else "no"
    return str(value)
