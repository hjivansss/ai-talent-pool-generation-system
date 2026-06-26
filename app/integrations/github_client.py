#Usage: handles all direct GitHub API communication.
import httpx

from app.core.config import settings


class GitHubClient:
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.token = settings.GITHUB_TOKEN

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json"
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    async def search_users(
        self,
        query: str,
        limit: int = 10
    ) -> list[dict]:
        url = f"{self.base_url}/search/users"

        params = {
            "q": query,
            "per_page": limit
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url,
                headers=self._headers(),
                params=params
            )
            response.raise_for_status()

        data = response.json()
        return data.get("items", [])

    async def get_user_profile(self, username: str) -> dict:
        url = f"{self.base_url}/users/{username}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                url,
                headers=self._headers()
            )
            response.raise_for_status()

        return response.json()


github_client = GitHubClient()