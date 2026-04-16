"""
API clientes para providers locales (Ollama, vLLM)
"""

from dataclasses import dataclass, field

import requests


@dataclass
class ScanResult:
    """Resultado de un escaneo de provider."""
    success: bool
    models: list[str] = field(default_factory=list)
    error: str | None = None


class ProviderScanner:
    """Escáner para providers locales."""

    @staticmethod
    def scan_ollama(base_url: str, api_key: str = None) -> ScanResult:
        """Escanear modelos de Ollama."""
        url = f"{base_url}/api/tags"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            return ScanResult(success=True, models=models)
        except requests.exceptions.RequestException as e:
            return ScanResult(success=False, error=str(e))

    @staticmethod
    def scan_vllm(base_url: str, api_key: str = None) -> ScanResult:
        """Escanear modelos de vLLM."""
        url = f"{base_url}/v1/models"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            # vLLM returns data[].id, filter "data/" prefix
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if model_id.startswith("data/"):
                    model_id = model_id[5:]  # Remove "data/" prefix
                models.append(model_id)
            return ScanResult(success=True, models=models)
        except requests.exceptions.RequestException as e:
            return ScanResult(success=False, error=str(e))
