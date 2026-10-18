"""
Gestor de configuración y caché para opencode
"""

import json
import sys
import time
from pathlib import Path

from .cache_models import migrate_cache


# Rutas por defecto según estándar XDG Base Directory
# Cross-platform: Windows, Linux, macOS usan ~/.config/opencode
DEFAULT_HOME = Path.home() / ".config" / "opencode"
DEFAULT_CONFIG = DEFAULT_HOME / "opencode.json"
DEFAULT_CACHE = DEFAULT_HOME / "provider_cache.json"


class ConfigManager:
    """Gestor de configuración y caché para providers de opencode."""

    def __init__(self, config_path: Path = None, home_path: Path = None):
        """Inicializar el gestor."""
        self.home = home_path or DEFAULT_HOME
        self.config_path = config_path or DEFAULT_CONFIG
        self.cache_path = self.home / "provider_cache.json"
        self.config_data = None
        self.cache_data = None

        # Crear directorio home si no existe
        self.home.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> dict:
        """Cargar configuración desde el archivo JSON.

        Si el archivo no existe o está vacío/corrupto, inicializa con un dict vacío.
        No realiza migraciones — usar migrate_legacy_config() para eso.
        """
        if not self.config_path.exists():
            self.config_data = {}
            self.save_config()
        else:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        self.config_data = {}
                        self.save_config()
                        return self.config_data
                    self.config_data = json.loads(content)
            except json.JSONDecodeError:
                ConfigUI.print_error(f"Archivo {self.config_path} corrupto. Creando nuevo.")
                self.config_data = {}
                self.save_config()
                return self.config_data

        return self.config_data

    def migrate_legacy_config(self):
        """Migrar formato antiguo con 'providers' al nuevo formato 'provider'.

        Debe llamarse explícitamente después de load_config() cuando se sospecha
        que el archivo puede tener formato antiguo.
        """
        if self.config_data is None:
            return

        if "provider" not in self.config_data:
            old_providers = self.config_data.get("providers", {})
            if old_providers:
                for provider_name, config in old_providers.items():
                    if config.get("type") == "ollama":
                        self.config_data["provider"] = "ollama"
                        self.config_data["models"] = config.get("models", [])
                        if config.get("options", {}).get("base_url"):
                            self.config_data["ollama"] = {
                                "baseUrl": config["options"]["base_url"]
                            }
                        break
                self.save_config()

    def save_config(self):
        """Guardar configuración en el archivo JSON."""
        # Reordenar para que $schema sea el primer campo
        ordered_data = {}
        if "$schema" in self.config_data:
            ordered_data["$schema"] = self.config_data["$schema"]
        for key, value in self.config_data.items():
            if key != "$schema":
                ordered_data[key] = value

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(ordered_data, f, indent=2, ensure_ascii=False)

    def load_cache(self) -> dict:
        """Cargar caché desde el archivo JSON.

        Los modelos en formato antiguo (lista de ids) se migran en memoria al
        formato nuevo (dict con opciones por modelo). La migración se persiste
        la próxima vez que se guarda la caché.
        """
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        self.cache_data = {"cache_timestamp": 0, "providers": {}}
                        return self.cache_data
                    self.cache_data = json.loads(content)
            except json.JSONDecodeError:
                ConfigUI.print_warning(f"Archivo de caché {self.cache_path} corrupto. Creando nuevo.")
                self.cache_data = {"cache_timestamp": 0, "providers": {}}
                self.save_cache()
        else:
            self.cache_data = {"cache_timestamp": 0, "providers": {}}

        if not isinstance(self.cache_data.get("providers"), dict):
            self.cache_data["providers"] = {}

        if migrate_cache(self.cache_data):
            ConfigUI.print_info("Caché migrada al formato v2 (modelos con opciones).")
            self._persist_cache_migration()

        return self.cache_data

    def _persist_cache_migration(self):
        """Guardar la caché migrada sin tocar la fecha del último escaneo global."""
        timestamp = self.cache_data.get("cache_timestamp", 0)
        self.save_cache(touch=False)
        self.cache_data["cache_timestamp"] = timestamp

    def save_cache(self, touch: bool = True):
        """Guardar caché en el archivo JSON."""
        if self.cache_data is None:
            self.cache_data = {"cache_timestamp": 0, "providers": {}}
        self.cache_data.setdefault("providers", {})
        migrate_cache(self.cache_data)
        if touch:
            self.cache_data["cache_timestamp"] = int(time.time())
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.cache_data, f, indent=2, ensure_ascii=False)


# Colores ANSI
class Colors:
    """Códigos de colores ANSI para terminal."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    # Colores normales
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    # Colores brillantes
    BRIGHT_RED = "\033[91;1m"
    BRIGHT_GREEN = "\033[92;1m"
    BRIGHT_YELLOW = "\033[93;1m"
    BRIGHT_BLUE = "\033[94;1m"
    BRIGHT_CYAN = "\033[96;1m"


class ConfigUI:
    """Interfaz de usuario para interacciones."""

    # Caché de soporte ANSI (se detecta una sola vez)
    _ansi_supported: bool | None = None

    @classmethod
    def _supports_ansi(cls) -> bool:
        """Detectar soporte ANSI una sola vez y cachear el resultado."""
        if cls._ansi_supported is not None:
            return cls._ansi_supported

        if sys.platform != "win32":
            cls._ansi_supported = True
            return True

        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            stderr_handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(stderr_handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                cls._ansi_supported = bool(mode.value & 0x0004)
            else:
                cls._ansi_supported = False
        except Exception:
            cls._ansi_supported = False

        return cls._ansi_supported

    @staticmethod
    def _color(text: str, color: str) -> str:
        """Aplicar color al texto si la terminal lo soporta."""
        if ConfigUI._supports_ansi():
            return f"{color}{text}{Colors.RESET}"
        return text

    @staticmethod
    def ask_yes_no(prompt: str, default: str = "y") -> bool:
        """Pregunta con respuesta Y/n o Y/N."""
        default_upper = default.upper()
        while True:
            colored_prompt = ConfigUI._color(prompt, Colors.BOLD)
            colored_default = ConfigUI._color(f"[{default_upper}]", Colors.CYAN)
            response = ConfigUI._read_line(f"{colored_prompt} {colored_default}: ")
            if response is None:
                return default_upper == "Y"
            response = response.lower()
            if response == "":
                return default_upper == "Y"
            if response in ["y", "n"]:
                return response == "y"
            print(ConfigUI._color("Por favor, responde con 'y' o 'n'.", Colors.YELLOW))

    @staticmethod
    def ask_input(prompt: str, default: str = "") -> str:
        """Pregunta con valor por defecto."""
        colored_prompt = ConfigUI._color(prompt, Colors.BOLD)
        if default:
            colored_default = ConfigUI._color(f"[{default}]", Colors.CYAN)
            response = ConfigUI._read_line(f"{colored_prompt} {colored_default}: ")
            return response or default
        return ConfigUI._read_line(f"{colored_prompt}: ") or ""

    @staticmethod
    def _read_line(prompt: str):
        """Leer una linea de stdin.

        Devuelve None cuando la entrada se ha acabado (EOF), para que los bucles
        de pregunta no queden colgados si ocm se ejecuta sin terminal.
        """
        try:
            return input(prompt).strip()
        except EOFError:
            return None

    @staticmethod
    def ask_raw(prompt: str, default: str = "", hint: str = ""):
        """Pregunta devolviendo lo escrito tal cual.

        A diferencia de `ask_input`, Intro sin texto devuelve `""` (no el
        default), asi el llamador puede distinguir 'mantener' de 'cambiar'.
        """
        parts = [ConfigUI._color(prompt, Colors.BOLD)]
        if default:
            parts.append(ConfigUI._color(f"[{default}]", Colors.CYAN))
        if hint:
            parts.append(ConfigUI._color(f"({hint})", Colors.YELLOW))
        return ConfigUI._read_line(" ".join(parts) + ": ")

    @staticmethod
    def ask_choice(prompt: str, choices, default=None):
        """Menu numerado simple; devuelve la opcion elegida o `default`.

        Intro a secas mantiene `default`. Escribe el numero de una opcion.
        """
        items = list(choices)
        if not items:
            return default

        labels = []
        for index, item in enumerate(items, start=1):
            label = str(item)
            marker = ""
            if default is not None and str(default) == label:
                marker = Colors.CYAN + " *" + Colors.RESET
            labels.append(f"  {index}) {label}{marker}")
            items[index - 1] = (label, item)

        print(f"\n{prompt}")
        print("\n".join(labels))
        hint = "Intro mantiene la opcion actual" if default is not None else None
        while True:
            raw = ConfigUI.ask_raw("Opcion", hint=hint)
            if raw is None or raw == "":
                return default if default is not None else items[0][1]
            if raw.isdigit() and 1 <= int(raw) <= len(items):
                return items[int(raw) - 1][1]
            for label, value in items:
                if raw.lower() == label.lower():
                    return value
            ConfigUI.print_warning(f"Valor no valido. Escribe un numero entre 1 y {len(items)}.")

    @staticmethod
    def print_success(message: str):
        """Imprimir mensaje de éxito."""
        print(f"{Colors.BRIGHT_GREEN}[OK]{Colors.RESET} {message}")

    @staticmethod
    def print_error(message: str):
        """Imprimir mensaje de error."""
        print(f"{Colors.BRIGHT_RED}[ERROR]{Colors.RESET} {message}")

    @staticmethod
    def print_info(message: str):
        """Imprimir mensaje informativo."""
        print(f"{Colors.BLUE}[INFO]{Colors.RESET} {message}")

    @staticmethod
    def print_warning(message: str):
        """Imprimir mensaje de advertencia."""
        print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} {message}")

    @staticmethod
    def print_header(text: str):
        """Imprimir encabezado."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}=== {text} ==={Colors.RESET}\n")

    @staticmethod
    def print_provider(provider_name: str, provider_config: dict, models: list = None):
        """Imprimir información de un provider."""
        print(f"\n{Colors.BOLD}Provider:{Colors.RESET} {provider_name}")
        print(f"  {Colors.CYAN}Type:{Colors.RESET} {provider_config.get('type', 'unknown')}")
        print(f"  {Colors.CYAN}Options:{Colors.RESET}")
        for key, value in provider_config.get("options", {}).items():
            print(f"    {key}: {value}")
        if models:
            print(f"  {Colors.CYAN}Models ({len(models)}):{Colors.RESET}")
            for model in models:
                print(f"    - {model}")
