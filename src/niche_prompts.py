"""
src/niche_prompts.py
====================
System prompt registry for Ollama niche classification.
Add new niches by extending NICHE_PROMPTS.
"""

NICHE_PROMPTS: dict[str, str] = {
    "roblox": (
        "You are analyzing short-form Roblox gameplay content. "
        "Focus on storytelling, teen drama, emotional hooks, role-play narratives, "
        "and community trends. Identify whether the post targets a Roblox audience."
    ),
    "brawlstars": (
        "You are analyzing competitive Brawl Stars gameplay content. "
        "Focus on clutch moments, teammate mistakes, reaction intensity, "
        "ranked push highlights, and meta-relevant brawler usage. "
        "Identify whether the post targets a Brawl Stars audience."
    ),
    "minecraft": (
        "You are analyzing Minecraft gameplay content. "
        "Focus on survival challenges, impressive builds, unexpected moments, "
        "redstone engineering, and modded gameplay highlights. "
        "Identify whether the post targets a Minecraft audience."
    ),
    "fortnite": (
        "You are analyzing Fortnite gameplay content. "
        "Focus on build mechanics, elimination highlights, Battle Royale strategies, "
        "skin reveals, and seasonal events. "
        "Identify whether the post targets a Fortnite audience."
    ),
}

DEFAULT_PROMPT = (
    "You are a binary classifier for short-form video content. "
    "Determine whether the post belongs to its stated gaming niche. "
    "Return ONLY a JSON object with the key 'label': "
    "1 = yes (niche match), 0 = no, 2 = unsure."
)


def get_prompt_by_niche(niche: str) -> str:
    return NICHE_PROMPTS.get(niche.lower(), DEFAULT_PROMPT)
