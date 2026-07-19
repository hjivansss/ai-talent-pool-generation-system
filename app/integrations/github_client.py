#Usage: handles all direct GitHub API communication.
import httpx
import asyncio
from app.core.config import settings


class GitHubClient:
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.token = settings.GITHUB_TOKEN
        # One shared, connection-pooled client instead of a new httpx.AsyncClient()
        # (new TCP+TLS handshake) per call. Measured impact: for a 20-candidate
        # search this was creating ~260 short-lived clients.
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=15,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=10),
        )
        # Caps concurrent in-flight GitHub requests. Without this, gathering
        # profiles for N candidates concurrently could fire 10+ simultaneous
        # requests each, risking GitHub's secondary (abuse-detection) rate limit,
        # which responds slowly rather than failing fast — invisible latency.
        self._sem = asyncio.Semaphore(8)

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def search_users(self, query: str, limit: int = 10) -> list[dict]:
        async with self._sem:
            response = await self._client.get("/search/users", params={"q": query, "per_page": limit})
            response.raise_for_status()
        return response.json().get("items", [])

    async def get_user_profile(self, username: str) -> dict:
        async with self._sem:
            response = await self._client.get(f"/users/{username}")
            response.raise_for_status()
        return response.json()

    async def get_user_repos(self, username: str, limit: int = 30) -> list[dict]:
        """Fetch owned repos sorted by most recently pushed."""
        params = {"per_page": limit, "sort": "pushed", "direction": "desc", "type": "owner"}
        async with self._sem:
            response = await self._client.get(f"/users/{username}/repos", params=params)
            if response.status_code in (404, 403):
                return []
            response.raise_for_status()
        return response.json()

    async def get_user_events(self, username: str, limit: int = 30) -> list[dict]:
        """Recent public activity — pushes, PRs, issues."""
        async with self._sem:
            response = await self._client.get(f"/users/{username}/events/public", params={"per_page": limit})
            if response.status_code in (404, 403):
                return []
            response.raise_for_status()
        return response.json()

    # NOTE: get_repo_languages / get_aggregated_languages were removed, They cost ~10 extra HTTP calls per candidate (measured 7-10s/candidate) 


github_client = GitHubClient()