#builds search query and converts GitHub API data into clean candidate objects.
from app.integrations.github_client import github_client
from app.schemas.candidate_schema import GitHubCandidateProfile


class CandidateSearchService:
    def build_github_query(
        self,
        skills: list[str],
        location: str | None = None
    ) -> str:
        skill_query = " ".join(skills[:5])

        query = f"{skill_query} in:bio"

        if location:
            query += f" location:{location}"

        return query

    async def search_github_candidates(
        self,
        skills: list[str],
        location: str | None = None,
        limit: int = 10
    ) -> tuple[str, list[GitHubCandidateProfile]]:
        query = self.build_github_query(
            skills=skills,
            location=location
        )

        users = await github_client.search_users(
            query=query,
            limit=limit
        )

        candidates: list[GitHubCandidateProfile] = []

        for user in users:
            username = user.get("login")

            if not username:
                continue

            profile = await github_client.get_user_profile(username)

            candidates.append(
                GitHubCandidateProfile(
                    username=profile.get("login"),
                    profile_url=profile.get("html_url"),
                    avatar_url=profile.get("avatar_url"),
                    bio=profile.get("bio"),
                    location=profile.get("location"),
                    public_repos=profile.get("public_repos"),
                    followers=profile.get("followers"),
                    source="github"
                )
            )

        return query, candidates


candidate_search_service = CandidateSearchService()