#Usage: handles all direct GitHub API communication.
import httpx
import asyncio
from app.core.config import settings


class GitHubClient:
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.token = settings.GITHUB_TOKEN

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def search_users(self, query: str, limit: int = 10) -> list[dict]:
        url = f"{self.base_url}/search/users"
        params = {"q": query, "per_page": limit}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
        return response.json().get("items", [])

    async def get_user_profile(self, username: str) -> dict:
        url = f"{self.base_url}/users/{username}"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
        return response.json()

    async def get_user_repos(self, username: str, limit: int = 30) -> list[dict]:
        """Fetch owned repos sorted by most recently pushed."""
        url = f"{self.base_url}/users/{username}/repos"
        params = {"per_page": limit, "sort": "pushed", "direction": "desc", "type": "owner"}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            if response.status_code in (404, 403):
                return []
            response.raise_for_status()
        return response.json()

    async def get_repo_languages(self, username: str, repo_name: str) -> dict:
        """Language byte breakdown for one repo."""
        url = f"{self.base_url}/repos/{username}/{repo_name}/languages"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=self._headers())
            if response.status_code in (404, 403):
                return {}
            response.raise_for_status()
        return response.json()

    async def get_user_events(self, username: str, limit: int = 30) -> list[dict]:
        """Recent public activity — pushes, PRs, issues."""
        url = f"{self.base_url}/users/{username}/events/public"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=self._headers(), params={"per_page": limit})
            if response.status_code in (404, 403):
                return []
            response.raise_for_status()
        return response.json()

    async def get_aggregated_languages(self, username: str, repos: list[dict]) -> dict:
        """
        Aggregate language bytes across top 10 non-fork repos concurrently.
        Returns {language: total_bytes} sorted descending.
        """
        top_repos = [r for r in repos if not r.get("fork")][:10]
        tasks = [self.get_repo_languages(username, r["name"]) for r in top_repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        totals: dict[str, int] = {}
        for lang_map in results:
            if isinstance(lang_map, dict):
                for lang, count in lang_map.items():
                    totals[lang] = totals.get(lang, 0) + count

        return dict(sorted(totals.items(), key=lambda x: x[1], reverse=True))


github_client = GitHubClient()
