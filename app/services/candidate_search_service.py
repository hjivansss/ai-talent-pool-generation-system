# Builds GitHub search query and converts GitHub API data into clean candidate objects.
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from app.integrations.github_client import github_client
from app.schemas.candidate_schema import GitHubCandidateProfile, GitHubRepoSummary, LinkedInProfile
from app.models.job_description import JobDescription
from app.services.skill_utils import flatten_skill_phrases


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
        # Flatten any bundled skill phrases (e.g. "Proficiency in HTML5, CSS3,
        # JavaScript" as one entry) before building the query — GitHub's search
        # ANDs all words in a non-OR-separated phrase together, so a bundled
        # entry becomes an unmatchable literal-phrase search. See skill_utils.py.
        atomic_skills = flatten_skill_phrases(skills)
        skill_query = " OR ".join(atomic_skills[:3])

        # Detect language from skills if not explicitly provided
        language = github_language
        if not language:
            for skill in atomic_skills:
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
        # all_topics was unbounded — a candidate with many tagged repos could
        # produce a very long list that gets stored/returned for no benefit.
        deduped_topics = list(dict.fromkeys(all_topics))[:15]
        return [s for _, s in scored[:5]], deduped_topics, total_stars, total_forks

    def _top_languages_from_repos(self, repos: list[dict]) -> dict[str, int]:
        """
        Approximates language weighting from each repo's primary `language`
        field, which GitHub already returns as part of the repo list — no
        extra HTTP call needed. Replaces the old per-repo /languages endpoint
        aggregation (github_client.get_aggregated_languages), which cost
        ~7-10 extra API calls per candidate for marginally more precise
        (byte-weighted vs repo-count-weighted) data. See github_client.py note.
        """
        counts: dict[str, int] = {}
        for repo in repos:
            lang = repo.get("language")
            if lang and not repo.get("fork"):
                counts[lang] = counts.get(lang, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

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
        candidate_start = time.perf_counter()
        try:
            profile, repos, events = await asyncio.gather(
                github_client.get_user_profile(username),
                github_client.get_user_repos(username, limit=30),
                github_client.get_user_events(username, limit=30),
            )
        except Exception as e:
            print(f"[TIMING]   GitHub fetch — {username!r}: FAILED after "
                  f"{time.perf_counter() - candidate_start:.2f}s ({e})")
            return None
        core_fetch_elapsed = time.perf_counter() - candidate_start

        if profile.get("type") == "Organization":
            return None

        top_languages = self._top_languages_from_repos(repos)
        top_repos, all_topics, total_stars, total_forks = self._parse_repos(repos)
        activity_types, active_days = self._parse_events(events)

        total_elapsed = time.perf_counter() - candidate_start
        print(f"[TIMING]   GitHub fetch — {username!r}: {total_elapsed:.2f}s "
              f"(profile+repos+events, languages derived in-memory — no extra calls)")

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
        search_start = time.perf_counter()
        users = await github_client.search_users(query=query, limit=limit)
        print(f"[TIMING] GitHub search/users: {time.perf_counter() - search_start:.2f}s "
              f"({len(users)} candidate logins)")

        enrich_start = time.perf_counter()
        tasks = [self._build_rich_profile(u["login"]) for u in users if u.get("login")]
        results = await asyncio.gather(*tasks)
        print(f"[TIMING] GitHub per-candidate enrichment (all {len(tasks)} concurrently): "
              f"{time.perf_counter() - enrich_start:.2f}s wall-clock")

        profiles = [r for r in results if r is not None]
        print(f"[GitHubSearch] {len(profiles)}/{len(users)} profiles built successfully "
              f"({len(users) - len(profiles)} dropped — org accounts or fetch failures)")
        return query, profiles

candidate_search_service = CandidateSearchService()
