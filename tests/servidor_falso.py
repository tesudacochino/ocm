"""Servidor falso de metadatos para las suites de regresion.

Sustituye el transporte (`_get_json`, `_post_json`, `probar_entrada`) de
`ProviderScanner`, asi que no se toca la red: se finge que el servidor es llama.cpp,
vLLM u ollama y se cuenta lo que se le pidio.
"""

from opencode_config_manager import api


class ServidorFalso:
    """Finge los endpoints de metadatos; cuenta lo que se le pidio."""

    def __init__(self, gets=None, show=None, prueba=None):
        # endpoint -> (datos, error); por defecto todo dice que no existe
        self.gets = {"/api/tags": (None, "404"), "/v1/models": (None, "404"),
                     "/props": (None, "404")}
        self.gets.update(gets or {})
        self.show = show
        self.prueba = prueba              # (estado, mensaje) del POST de chat
        self.llamados = []
        self._originales = None

    def _get_json(self, base_url, endpoint, api_key=None):
        self.llamados.append(endpoint)
        if endpoint not in self.gets:
            return None, f"{endpoint} no existe"
        valor = self.gets[endpoint]
        if isinstance(valor, tuple):          # (datos, error)
            return valor
        return valor, None                    # solo los datos

    def _post_json(self, base_url, endpoint, cuerpo, api_key=None):
        self.llamados.append(f"POST {endpoint}")
        if endpoint != "/api/show" or self.show is None:
            return None, f"{endpoint} no existe"
        return self.show, None

    def _probar(self, base_url, endpoint, cuerpo, api_key=None):
        self.llamados.append(f"POST {endpoint} (prueba)")
        if self.prueba is None:
            return None, "no se probo"
        return self.prueba

    def instalar(self):
        Ps = api.ProviderScanner
        self._originales = (Ps._get_json, Ps._post_json, Ps.probar_entrada)
        Ps._get_json = staticmethod(self._get_json)
        Ps._post_json = staticmethod(self._post_json)
        Ps.probar_entrada = staticmethod(self._probar)

    def restaurar(self):
        Ps = api.ProviderScanner
        Ps._get_json, Ps._post_json, Ps.probar_entrada = self._originales

    def pidio(self, endpoint) -> bool:
        return any(endpoint in llamada for llamada in self.llamados)


def modelos_vllm(modelo="mi-modelo", **extra):
    """La forma de OpenAI: {'data': [...]}, con lo que trae vLLM o SGLang."""
    entrada = {"id": modelo, "object": "model", "owned_by": "vllm"}
    entrada.update(extra)
    return {"data": [entrada]}


def modelos_ollama(modelo="mi-modelo", **extra):
    """La forma de ollama: {'models': [...]} (la que usa tambien llama-server)."""
    entrada = {"name": modelo, "model": modelo}
    entrada.update(extra)
    return {"models": [entrada]}
