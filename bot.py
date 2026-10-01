"""
bot.py — Instagram Android Reels Bot
=====================================
Scrolls Instagram Reels on an Android device via uiautomator2, classifies
each video with Ollama, and engages based on niche match.

Usage:
    python bot.py roblox
    python bot.py brawlstars --no-save

Engagement rules:
    niche match  →  extra 5-8 s watch time
                    80 % like
                    10 % follow (independent)
                    share → copy link → save URL  (skipped with --no-save)
    no match     →   8 % like (organic randomness)
    any video    →  random pause 2-6 s (85 %) or 8-15 s (15 %)

All clicks use randomized coordinates within element bounding boxes.
"""

import logging
import sys
import time
import traceback

from src.scroll_session import run_scroll_session

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_session.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Supported niches (extend as needed)
SUPPORTED_NICHES = {"roblox", "brawlstars", "minecraft", "fortnite"}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    # ── Parse niche argument ──────────────────────────────────────────────
    if not args:
        logger.error(
            "No niche provided.\n"
            f"Usage: python bot.py <niche> [--no-save]\n"
            f"Supported niches: {', '.join(sorted(SUPPORTED_NICHES))}"
        )
        sys.exit(1)

    niche   = args[0].strip().lower()
    no_save = "--no-save" in flags

    if niche not in SUPPORTED_NICHES:
        logger.warning(
            f"Unknown niche '{niche}' — proceeding anyway with generic prompt.\n"
            f"Known niches: {', '.join(sorted(SUPPORTED_NICHES))}"
        )

    logger.info("========== INSTAGRAM ANDROID BOT STARTED ==========")
    logger.info(f"Niche: {niche} | save_links: {not no_save}")

    start = time.time()
    try:
        run_scroll_session(niche=niche, save_links=not no_save)
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl-C).")
    except Exception:
        logger.error(f"Fatal error:\n{traceback.format_exc()}")
    finally:
        elapsed = (time.time() - start) / 60
        logger.info(
            f"========== BOT STOPPED | total runtime: {elapsed:.1f} min =========="
        )


if __name__ == "__main__":
    main()
