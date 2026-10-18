"""
API clientes para providers locales (Ollama, vLLM)
"""

from dataclasses import dataclass, field

import requests

# Los dos endpoints que distinguen un servidor del otro
ENDPOINT_OLLAMA = "/api/tags"
ENDPOINT_VLLM = "/v1/models"


@dataclass
class ScanResult:
    """Resultado de un escaneo de provider."""
    success: bool
    models: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ProbeResult:
    """Resultado de probar que servidor hay detras de una URL.

    `endpoint` es el path que respondio, para poder explicar en la ficha en que
    nos fijamos para decir 'ollama' o 'vllm'.
    """
    tipo: str | None
    models: list[str] = field(default_factory=list)
    endpoint: str | None = None
    errores: dict[str, str] = field(default_factory=dict)


class ProviderScanner:
    """Escáner para providers locales.

    Cada escaneo exige la FORMA esperada del JSON: un 200 que no trae lo suyo es un
    fallo, no un provider con cero modelos. ollama tambien sirve /v1/models, asi que
    lo unico que lo distingue de verdad es que exista /api/tags.
    """

    @staticmethod
    def _get_json(base_url: str, endpoint: str, api_key: str = None):
        """GET + JSON, devolviendo (datos, error) en vez de romper por un 200 con HTML.

        Un proxy o un puerto equivocado suelen contestar 200 con una pagina, y ahi
        response.json() lanza ValueError: no es un RequestException y se escapaba.
        """
        url = f"{(base_url or '').rstrip('/')}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json(), None
        except requests.exceptions.RequestException as error:
            return None, str(error)
        except ValueError:          # cuerpo que no es JSON
            return None, f"{endpoint} contesto algo que no es JSON"
        except Exception as error:           # noqa: BLE001 - consultar no debe romper
            return None, f"error inesperado en {endpoint}: {error}"

    @staticmethod
    def _nombres(lista, claves) -> list[str]:
        """Sacar los ids/nombres de una lista de modelos, en la forma que sea."""
        nombres = []
        for entrada in lista:
            if isinstance(entrada, dict):
                nombre = next((entrada[clave] for clave in claves if entrada.get(clave)), None)
                if nombre:
                    nombres.append(str(nombre))
            elif entrada:
                nombres.append(str(entrada))
        return nombres

    @staticmethod
    def scan_ollama(base_url: str, api_key: str = None) -> ScanResult:
        """Escanear modelos de Ollama (GET /api/tags)."""
        datos, error = ProviderScanner._get_json(base_url, ENDPOINT_OLLAMA, api_key)
        if error:
            return ScanResult(success=False, error=error)
        if not isinstance(datos, dict) or not isinstance(datos.get("models"), list):
            return ScanResult(success=False, error=f"{ENDPOINT_OLLAMA} no devuelve 'models'")
        return ScanResult(success=True,
                          models=ProviderScanner._nombres(datos["models"], ("name", "model")))

    @staticmethod
    def scan_vllm(base_url: str, api_key: str = None) -> ScanResult:
        """Escanear modelos de vLLM y cualquiera compatible con OpenAI (GET /v1/models)."""
        datos, error = ProviderScanner._get_json(base_url, ENDPOINT_VLLM, api_key)
        if error:
            return ScanResult(success=False, error=error)
        if not isinstance(datos, dict) or not isinstance(datos.get("data"), list):
            return ScanResult(success=False, error=f"{ENDPOINT_VLLM} no devuelve 'data'")
        models = []
        for model_id in ProviderScanner._nombres(datos["data"], ("id", "name")):
            if model_id.startswith("data/"):
                model_id = model_id[5:]  # Remove "data/" prefix
            models.append(model_id)
        return ScanResult(success=True, models=models)

    @staticmethod
    def probe(base_url: str, api_key: str = None) -> ProbeResult:
        """Averiguar que servidor hay detras de la URL, sin fiarse del tipo guardado.

        Pasa por los dos escaneos, de manera que quien sustituya scan_ollama o
        scan_vllm (las pruebas, o un caso raro) sigue afectando a la deteccion.
        """
        errores = {}

        resultado = ProviderScanner.scan_ollama(base_url, api_key)
        if resultado.success:
            return ProbeResult(tipo="ollama", models=resultado.models,
                               endpoint=ENDPOINT_OLLAMA)
        errores["ollama"] = resultado.error or f"no contesta a {ENDPOINT_OLLAMA}"

        resultado = ProviderScanner.scan_vllm(base_url, api_key)
        if resultado.success:
            return ProbeResult(tipo="vllm", models=resultado.models,
                               endpoint=ENDPOINT_VLLM)
        errores["vllm"] = resultado.error or f"no contesta a {ENDPOINT_VLLM}"

        return ProbeResult(tipo=None, errores=errores)
