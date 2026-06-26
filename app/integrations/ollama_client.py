#httpx is used for making API calls to the Ollama server and handling responses
import httpx

from app.core.config import settings


class OllamaClient:
    def __init__(self):
        self.base_url = settings.OLLAMA_URL
        self.model = settings.OLLAMA_MODEL

    async def generate(self, prompt: str , temperature: float = 0.1) -> str:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature}, # Low temperature = more deterministic output = more consistent JSON.
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        
        return response.json().get("response", "")


ollama_client = OllamaClient()