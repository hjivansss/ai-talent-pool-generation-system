#builds search query and converts GitHub API data into clean candidate objects.
import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.integrations.github_client import github_client
from app.schemas.candidate_schema import (
    GitHubCandidateProfile,
    GitHubRepoSummary,
    LinkedInProfile,
)


class CandidateSearchService:

    # ── GitHub ──────────────────────────────────────────────────────────────────

    def build_github_query(self, skills: list[str], location: Optional[str] = None) -> str:
       skill_query = " OR ".join(skills[:3])
       query = f"{skill_query} repos:>5 followers:>10"
       if location:
          query += f" location:{location}"
       return query

    def _parse_repos(
        self, repos: list[dict]
    ) -> tuple[list[GitHubRepoSummary], list[str], int, int]:
        all_topics: list[str] = []
        total_stars = 0
        total_forks = 0
        scored: list[tuple[int, GitHubRepoSummary]] = []

        for repo in repos:
            stars   = repo.get("stargazers_count", 0)
            forks   = repo.get("forks_count", 0)
            topics  = repo.get("topics", [])
            is_fork = repo.get("fork", False)

            total_stars += stars
            total_forks += forks
            all_topics.extend(topics)

            summary = GitHubRepoSummary(
                name=repo["name"],
                description=repo.get("description"),
                url=repo.get("html_url", ""),
                stars=stars,
                forks=forks,
                primary_language=repo.get("language"),
                topics=topics,
                is_fork=is_fork,
                last_pushed=repo.get("pushed_at"),
            )
            if not is_fork:
                scored.append((stars, summary))

        scored.sort(key=lambda x: x[0], reverse=True)
        unique_topics = list(dict.fromkeys(all_topics))
        return [s for _, s in scored[:5]], unique_topics, total_stars, total_forks

    def _parse_events(self, events: list[dict]) -> tuple[list[str], int]:
        now = datetime.now(timezone.utc)
        types_seen: set[str] = set()
        active_dates: set[str] = set()

        for event in events:
            types_seen.add(event.get("type", ""))
            created = event.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if (now - dt).days <= 30:
                        active_dates.add(created[:10])
                except Exception:
                    pass

        return list(types_seen), len(active_dates)

    def _account_age(self, created_at: Optional[str]) -> Optional[float]:
        if not created_at:
            return None
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return round((datetime.now(timezone.utc) - dt).days / 365.25, 1)
        except Exception:
            return None

    async def _build_rich_profile(self, username: str) -> Optional[GitHubCandidateProfile]:
        try:
            profile, repos, events = await asyncio.gather(
                github_client.get_user_profile(username),
                github_client.get_user_repos(username, limit=30),
                github_client.get_user_events(username, limit=30),
            )
        except Exception:
            return None
        
        if profile.get("type") == "Organization":
            return None
        
        top_languages = await github_client.get_aggregated_languages(username, repos)
        top_repos, all_topics, total_stars, total_forks = self._parse_repos(repos)
        activity_types, active_days = self._parse_events(events)

        return GitHubCandidateProfile(
            username=profile.get("login", username),
            name=profile.get("name"),
            profile_url=profile.get("html_url", f"https://github.com/{username}"),
            avatar_url=profile.get("avatar_url"),
            bio=profile.get("bio"),
            location=profile.get("location"),
            email=profile.get("email"),
            company=profile.get("company"),
            blog=profile.get("blog"),
            public_repos=profile.get("public_repos"),
            followers=profile.get("followers"),
            following=profile.get("following"),
            total_stars_earned=total_stars,
            total_forks_earned=total_forks,
            top_languages=top_languages,
            language_list=list(top_languages.keys()),
            top_repos=top_repos,
            all_topics=all_topics,
            recent_activity_types=activity_types,
            active_days_last_month=active_days,
            hireable=profile.get("hireable"),
            account_age_years=self._account_age(profile.get("created_at")),
        )

    async def search_github_candidates(
        self,
        skills: list[str],
        location: Optional[str] = None,
        limit: int = 10,
    ) -> tuple[str, list[GitHubCandidateProfile]]:
        query = self.build_github_query(skills, location)
        users = await github_client.search_users(query=query, limit=limit)
        tasks = [self._build_rich_profile(u["login"]) for u in users if u.get("login")]
        results = await asyncio.gather(*tasks)
        return query, [r for r in results if r is not None]

    # ── LinkedIn ────────────────────────────────────────────────────────────────

    def ingest_linkedin_profiles(self, profiles: list[LinkedInProfile]) -> list[LinkedInProfile]:
        """
        Validates and returns LinkedIn profiles.
        Pydantic already validated them at the endpoint level —
        this is where DB persistence will be added in Phase 5.
        """
        return profiles


candidate_search_service = CandidateSearchService()