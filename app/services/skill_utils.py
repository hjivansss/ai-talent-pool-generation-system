import re

_FILLER_PREFIXES = [
    "proficiency in", "strong knowledge of", "basic knowledge of",
    "knowledge of", "experience with", "experience in",
    "familiarity with", "understanding of", "hands-on experience with",
]

_SPLIT_PATTERN = re.compile(r",|\band\b|\bor\b|/")


def flatten_skill_phrases(skills: list[str]) -> list[str]:
    """
    Splits bundled skill entries into atomic tokens. Idempotent — an
    already-atomic list (e.g. ["Python", "Docker", "AWS"]) passes through
    with only whitespace/case-preserving cleanup, so this is safe to apply
    unconditionally to any required_skills/tools_and_platforms list.
    """
    result: list[str] = []
    for raw in skills:
        text = raw.strip()
        low = text.lower()
        for prefix in _FILLER_PREFIXES:
            if low.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        for part in _SPLIT_PATTERN.split(text):
            part = part.strip(" .")
            if part:
                result.append(part)

    seen, deduped = set(), []
    for s in result:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped
