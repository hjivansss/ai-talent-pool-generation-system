# Builds GitHub search query and converts GitHub API data into clean candidate objects.
import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.integrations.github_client import github_client
from app.schemas.candidate_schema import GitHubCandidateProfile, GitHubRepoSummary, LinkedInProfile
from app.models.job_description import JobDescription


# Maps common skill names to GitHub language qualifiers
LANGUAGE_MAP = {
    "python": "python", "javascript": "javascript", "typescript": "typescript",
    "kotlin": "kotlin", "swift": "swift", "go": "go", "golang": "go",
    "java": "java", "rust": "rust", "ruby": "ruby", "php": "php",
    "dart": "dart", "flutter": "dart", "c++": "c++", "c#": "c#",
    "scala": "scala", "r": "r", "elixir": "elixir",
}


class CandidateSearchService:

    def build_github_query(
        self,
        skills: list[str],
        location: Optional[str] = None,
        seniority_level: Optional[str] = None,
        github_language: Optional[str] = None,
        min_followers: Optional[int] = None,
        min_repos: Optional[int] = None,
    ) -> str:
        """
        Builds an optimized GitHub search query using JD fields.
        - Detects primary language from skills → adds language: filter
        - Adjusts follower threshold based on seniority
        - Accepts optional recruiter overrides for language/followers/repos
        """
        skill_query = " OR ".join(skills[:3])

        # Detect language from skills if not explicitly provided
        language = github_language
        if not language:
            for skill in skills:
                detected = LANGUAGE_MAP.get(skill.lower())
                if detected:
                    language = detected
                    break

        # Seniority-based follower threshold
        if min_followers is not None:
            followers = min_followers
        elif seniority_level in ("senior", "lead"):
            followers = 50
        elif seniority_level == "mid":
            followers = 20
        else:
            followers = 10

        repos = min_repos or 5

        query = f"{skill_query} followers:>{followers} repos:>{repos}"
        if language:
            query += f" language:{language}"
        if location:
            query += f" location:{location}"

        return query

    def _parse_repos(self, repos: list[dict]) -> tuple[list[GitHubRepoSummary], list[str], int, int]:
        all_topics, scored = [], []
        total_stars = total_forks = 0

        for repo in repos:
            stars, forks = repo.get("stargazers_count", 0), repo.get("forks_count", 0)
            topics, is_fork = repo.get("topics", []), repo.get("fork", False)
            total_stars += stars
            total_forks += forks
            all_topics.extend(topics)
            summary = GitHubRepoSummary(
                name=repo["name"], description=repo.get("description"),
                url=repo.get("html_url", ""), stars=stars, forks=forks,
                primary_language=repo.get("language"), topics=topics,
                is_fork=is_fork, last_pushed=repo.get("pushed_at"),
            )
            if not is_fork:
                scored.append((stars, summary))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:5]], list(dict.fromkeys(all_topics)), total_stars, total_forks

    def _parse_events(self, events: list[dict]) -> tuple[list[str], int]:
        now = datetime.now(timezone.utc)
        types_seen, active_dates = set(), set()
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
        seniority_level: Optional[str] = None,
        github_language: Optional[str] = None,
        min_followers: Optional[int] = None,
        min_repos: Optional[int] = None,
    ) -> tuple[str, list[GitHubCandidateProfile]]:
        query = self.build_github_query(
            skills=skills, location=location,
            seniority_level=seniority_level,
            github_language=github_language,
            min_followers=min_followers,
            min_repos=min_repos,
        )
        print(f"[GitHubSearch] query: {query!r}")
        users = await github_client.search_users(query=query, limit=limit)
        print(f"[GitHubSearch] search/users returned {len(users)} candidate logins")
        tasks = [self._build_rich_profile(u["login"]) for u in users if u.get("login")]
        results = await asyncio.gather(*tasks)
        profiles = [r for r in results if r is not None]
        print(f"[GitHubSearch] {len(profiles)}/{len(users)} profiles built successfully "
              f"({len(users) - len(profiles)} dropped — org accounts or fetch failures)")
        return query, profiles

candidate_search_service = CandidateSearchService()
