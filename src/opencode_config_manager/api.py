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
    """Resultado de un escaneo de provider.

    `entradas` guarda, por id de modelo, el objeto tal cual que devolvio el
    servidor: ahi estan `capabilities`, `max_model_len`, `root`... que usan la
    autodeteccion de opciones (`ocm model detect`).
    """
    success: bool
    models: list[str] = field(default_factory=list)
    error: str | None = None
    entradas: dict[str, dict] = field(default_factory=dict)


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
    entradas: dict[str, dict] = field(default_factory=dict)


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
    def _post_json(base_url: str, endpoint: str, cuerpo: dict, api_key: str = None):
        """POST + JSON, para /api/show de ollama (que es de consultar, pero por POST)."""
        url = f"{(base_url or '').rstrip('/')}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = requests.post(url, json=cuerpo, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json(), None
        except requests.exceptions.RequestException as error:
            return None, str(error)
        except ValueError:
            return None, f"{endpoint} contesto algo que no es JSON"
        except Exception as error:           # noqa: BLE001
            return None, f"error inesperado en {endpoint}: {error}"

    @staticmethod
    def probar_entrada(base_url: str, endpoint: str, cuerpo: dict, api_key: str = None):
        """POST sin interpretar el codigo: devuelve (estado, mensaje).

        Es para la prueba de vision: un 400 que dice 'this model does not support
        image inputs' es informacion util, no un fallo de conexion. Por eso aqui no
        se usa raise_for_status y el cuerpo del error se devuelve como mensaje.
        """
        url = f"{(base_url or '').rstrip('/')}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = requests.post(url, json=cuerpo, headers=headers, timeout=60)
        except requests.exceptions.RequestException as error:
            return None, str(error)
        except Exception as error:           # noqa: BLE001
            return None, f"error inesperado en {endpoint}: {error}"

        mensaje = response.text[:400] if response.text else ""
        try:
            detalle = response.json()
        except ValueError:
            return response.status_code, mensaje
        if isinstance(detalle, dict):
            error = detalle.get("error")
            if isinstance(error, dict) and error.get("message"):
                mensaje = str(error["message"])
            elif isinstance(error, str):
                mensaje = error
            elif detalle.get("message"):
                mensaje = str(detalle["message"])
            elif detalle.get("detail"):
                mensaje = str(detalle["detail"])
        return response.status_code, mensaje

    @staticmethod
    def _lista_modelos(datos, claves):
        """La lista de modelos, en la forma que use el servidor (o None).

        vLLM y los compatibles con OpenAI usan {'data': [...]}; ollama usa
        {'models': [...]}, y hay servidores (llama-server) que responden a
        /v1/models con la forma de ollama. Una lista pelada tambien vale.
        """
        if isinstance(datos, list):
            return datos
        if isinstance(datos, dict):
            for clave in claves:
                if isinstance(datos.get(clave), list):
                    return datos[clave]
        return None

    @staticmethod
    def _pares(lista, claves):
        """[(id, entrada_cruda)]: el id se saca de la primera clave que funcione.

        La entrada cruda se conserva porque `capabilities`, `max_model_len` o `root`
        son justo lo que necesita la autodeteccion de opciones.
        """
        pares = []
        for entrada in lista:
            if isinstance(entrada, dict):
                nombre = next((entrada[clave] for clave in claves if entrada.get(clave)), None)
                if nombre:
                    pares.append((str(nombre), entrada))
            elif entrada:
                pares.append((str(entrada), {}))
        return pares

    @staticmethod
    def _listar(base_url, endpoint, api_key, claves_lista, claves_nombre):
        """Pedir la lista de modelos a un endpoint y devolver un ScanResult."""
        datos, error = ProviderScanner._get_json(base_url, endpoint, api_key)
        if error:
            return ScanResult(success=False, error=error)
        lista = ProviderScanner._lista_modelos(datos, claves_lista)
        if lista is None:
            return ScanResult(success=False, error=f"{endpoint} no trae la lista de modelos")
        modelos = []
        entradas = {}
        for nombre, entrada in ProviderScanner._pares(lista, claves_nombre):
            if nombre.startswith("data/"):
                nombre = nombre[5:]  # Remove "data/" prefix
            modelos.append(nombre)
            entradas[nombre] = entrada
        return ScanResult(success=True, models=modelos, entradas=entradas)

    @staticmethod
    def scan_ollama(base_url: str, api_key: str = None) -> ScanResult:
        """Escanear modelos de Ollama (GET /api/tags).

        Exige la clave 'models': es lo que distingue a ollama, porque ollama tambien
        sirve /v1/models con forma de OpenAI.
        """
        return ProviderScanner._listar(base_url, ENDPOINT_OLLAMA, api_key,
                                       claves_lista=("models",),
                                       claves_nombre=("name", "model", "id"))

    @staticmethod
    def scan_vllm(base_url: str, api_key: str = None) -> ScanResult:
        """Escanear modelos de vLLM y cualquiera compatible con OpenAI (GET /v1/models).

        Tolera las dos formas: la de OpenAI ('data') y la de ollama ('models'), que
        es la que usan llama-server y algun otro por estas rutas.
        """
        return ProviderScanner._listar(base_url, ENDPOINT_VLLM, api_key,
                                       claves_lista=("data", "models"),
                                       claves_nombre=("id", "name", "model"))

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
                               endpoint=ENDPOINT_OLLAMA, entradas=resultado.entradas)
        errores["ollama"] = resultado.error or f"no contesta a {ENDPOINT_OLLAMA}"

        resultado = ProviderScanner.scan_vllm(base_url, api_key)
        if resultado.success:
            return ProbeResult(tipo="vllm", models=resultado.models,
                               endpoint=ENDPOINT_VLLM, entradas=resultado.entradas)
        errores["vllm"] = resultado.error or f"no contesta a {ENDPOINT_VLLM}"

        return ProbeResult(tipo=None, errores=errores)
