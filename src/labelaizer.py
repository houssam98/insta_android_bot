"""
src/labelaizer.py
=================
Classifies Instagram Reels content via Ollama.
Niche is set dynamically per session via set_niche().
"""

import logging
from ollama import Client
import src.storage as storage
from src.niche_prompts import get_prompt_by_niche

logger = logging.getLogger(__name__)

client = Client()

_current_niche: str = "roblox"

to_string = lambda x: x or ""


def set_niche(niche: str) -> None:
    """Set the active niche for all subsequent labelize() calls."""
    global _current_niche
    _current_niche = niche
    logger.debug(f"Niche set to: '{niche}'")


def labelize(caption, hashtags, text_on_screen) -> str | None:
    """
    Send content to Ollama and return the raw JSON response string.

    Returns:
        Raw JSON string like '{"label": 1}', or None on error.
    """
    caption        = storage.clean_text(to_string(caption))
    hashtags       = storage.clean_text(to_string(hashtags))
    text_on_screen = storage.clean_text(to_string(text_on_screen))

    system_prompt = get_prompt_by_niche(_current_niche)

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": (
                f"Classify this Instagram Reel for the '{_current_niche}' niche.\n"
                f"Caption: {caption}\n"
                f"Hashtags: {hashtags}\n"
                f"Text on screen: {text_on_screen}\n\n"
                f"Return ONLY a JSON object: {{\"label\": 1}} for match, "
                f"{{\"label\": 0}} for no match, {{\"label\": 2}} for unsure. "
                f"No explanation. No extra text."
            ),
        },
    ]

    response = ""
    try:
        for part in client.chat("gpt-oss:120b-cloud", messages=messages, stream=True):
            response += part["message"]["content"]
    except Exception as e:
        logger.error(f"Ollama request failed: {e}")
        return None

    return response
