"""
src/scroll_session.py
=====================
Core scrolling + engagement loop for Instagram Reels (Android / uiautomator2).

Ported from the TikTok refactored bot — all randomness patterns preserved and
extended for Instagram-specific interactions.

Per-video behaviour:
  ┌──────────────────────────┬──────────────────────────────────────────────────┐
  │ Condition                │ Action                                           │
  ├──────────────────────────┼──────────────────────────────────────────────────┤
  │ niche match              │ extra 5-8 s watch time                           │
  │                          │ 80 % → like                                      │
  │                          │ 10 % → follow                                    │
  │                          │ open share → copy link → save URL                │
  │ no niche match           │  8 % → like anyway                               │
  │ any video                │ random pause 2-6 s (85 %) or 8-15 s (15 %)      │
  └──────────────────────────┴──────────────────────────────────────────────────┘

Human-randomness rules:
  - All clicks use random coordinate offsets inside element bounding boxes
  - Variable pre/post-click delays
  - Mixed swipe styles and speeds
  - Occasional long pauses simulating distraction
  - Niche-matched videos get extra watch time before engagement
"""

import json
import logging
import random
import time
import traceback

import src.labelaizer as labelaizer
import src.scraper    as scraper
import src.storage    as storage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timing configuration  (mirrors TikTok bot)
# ---------------------------------------------------------------------------
MIN_SESSION_MINUTES = 25
MAX_SESSION_MINUTES = 35

SHORT_PAUSE       = (2, 6)     # seconds — frequent
LONG_PAUSE        = (8, 15)    # seconds — occasional
LONG_PAUSE_CHANCE = 0.15       # 15 % of pauses are long

# Extra watch time when the video is a niche match (seconds)
NICHE_WATCH_EXTRA = (5, 8)

# Pre/post-click delays for engagement actions
PRE_CLICK_DELAY  = (0.4, 1.2)
POST_CLICK_DELAY = (0.5, 1.5)

# Engagement probabilities
LIKE_PROB_MATCH    = 0.80   # 80 % like on niche match
FOLLOW_PROB_MATCH  = 0.10   # 10 % follow on niche match
LIKE_PROB_NOMATCH  = 0.08   #  8 % like even on no-match


# ---------------------------------------------------------------------------
# Main session runner
# ---------------------------------------------------------------------------
def run_scroll_session(niche: str, save_links: bool = True) -> None:
    """
    Scroll Instagram Reels and engage for a randomized session duration.

    Args:
        niche:      e.g. "roblox", "brawlstars", "minecraft"
        save_links: if False, skip the copy-link step entirely
    """
    labelaizer.set_niche(niche)

    duration_minutes = random.uniform(MIN_SESSION_MINUTES, MAX_SESSION_MINUTES)
    duration_seconds = duration_minutes * 60
    logger.info(
        f"Session started | niche='{niche}' | save_links={save_links} | "
        f"duration={duration_minutes:.1f} min ({duration_seconds:.0f} s)"
    )

    session_start = time.time()
    index         = 0

    while (time.time() - session_start) < duration_seconds:
        elapsed   = (time.time() - session_start) / 60
        remaining = (duration_seconds - (time.time() - session_start)) / 60
        logger.info(
            f"── Video #{index} │ elapsed {elapsed:.1f} min │ "
            f"remaining {remaining:.1f} min ──────────────"
        )

        try:
            _process_video(index, niche, save_links)
        except Exception:
            logger.error(f"Unhandled error on video #{index}:\n{traceback.format_exc()}")

        scraper.swipe_next_video()
        _random_pause()
        index += 1

    logger.info(f"Session time-limit reached after {index} videos.")


# ---------------------------------------------------------------------------
# Per-video processing pipeline
# ---------------------------------------------------------------------------
def _process_video(index: int, niche: str, save_links: bool) -> None:
    """Run the full pipeline for a single Reel."""

    # ── 1. Caption extraction ─────────────────────────────────────────────
    caption, hashtags = scraper.extract_caption_and_hashtags()

    if caption is None and hashtags is None:
        logger.info("No caption/hashtags — applying no-match engagement only.")
        _maybe_like_nomatch()
        return

    logger.info(f"Caption : {str(caption)[:80]}")
    logger.info(f"Hashtags: {str(hashtags)[:80]}")

    # ── 2. Classify with Ollama (retry on JSON parse failure) ─────────────
    label = _classify_with_retry(caption, hashtags)
    if label is None:
        return

    is_match = int(label.get("label", 2)) == 1
    logger.info(f"Label: {label} | niche_match={is_match}")

    # ── 3. Niche-matched: extra watch time before engagement ──────────────
    if is_match:
        extra = random.uniform(*NICHE_WATCH_EXTRA)
        logger.info(f"Niche match — watching extra {extra:.1f}s before engaging.")
        time.sleep(extra)

    # ── 4. Get like count (only matters for saving URL) ───────────────────
    like_count = 0
    if is_match:
        like_count = scraper.get_like_count()
        logger.info(f"Like count: {like_count:,}")

    # ── 5. Engagement ─────────────────────────────────────────────────────
    if is_match:
        _handle_niche_match_engagement(like_count, niche, caption, hashtags, save_links)
    else:
        _maybe_like_nomatch()


# ---------------------------------------------------------------------------
# Engagement handlers
# ---------------------------------------------------------------------------
def _handle_niche_match_engagement(like_count: int, niche: str,
                                   caption, hashtags, save_links: bool) -> None:
    """
    Full niche-match engagement flow:
      - 80 % like
      - 10 % follow (independent roll)
      - Copy link + save URL only if likes > 5,000 AND save_links is True
    All rolls are independent.
    """
    # Like roll
    if random.random() < LIKE_PROB_MATCH:
        scraper.like_video()
        _human_pause(0.4, 1.0)

    # Follow roll (independent of like)
    if random.random() < FOLLOW_PROB_MATCH:
        scraper.follow_author()
        _human_pause(0.5, 1.2)

    # Copy link and save only if enabled and likes exceed threshold
    if save_links:
        if like_count > 5_000:
            url = scraper.copy_and_get_link()
            if url:
                storage.save_url(url, like_count, niche,
                                 caption=caption or "", hashtags=hashtags or "")
                logger.info(f"Saved URL: {url}  (likes: {like_count:,})")
            else:
                logger.debug("Link copy failed or no URL returned.")
        else:
            logger.info(f"Like count {like_count:,} below 5,000 threshold — skipping link save.")
    else:
        logger.debug("save_links=False — skipping copy-link step.")


def _maybe_like_nomatch() -> None:
    """8 % chance to like even on no-match (organic behaviour)."""
    if random.random() < LIKE_PROB_NOMATCH:
        scraper.like_video()
        logger.info("Liked video (no-match organic roll).")


# ---------------------------------------------------------------------------
# Classification helper
# ---------------------------------------------------------------------------
def _classify_with_retry(caption, hashtags, max_attempts: int = 3) -> dict | None:
    """Call Ollama, retrying up to max_attempts on JSON parse failures."""
    for attempt in range(1, max_attempts + 1):
        try:
            raw   = labelaizer.labelize(caption, hashtags, text_on_screen="")
            label = json.loads(raw)
            return label
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"JSON parse failed (attempt {attempt}/{max_attempts}): {e}")
        except Exception as e:
            logger.error(f"Unexpected labelize error: {e}")
            break
    logger.error("All classification attempts failed — skipping.")
    return None


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------
def _random_pause() -> None:
    """Short pause most of the time; occasional long pause (15 %)."""
    if random.random() < LONG_PAUSE_CHANCE:
        secs = random.uniform(*LONG_PAUSE)
        logger.debug(f"Long pause: {secs:.1f}s")
    else:
        secs = random.uniform(*SHORT_PAUSE)
        logger.debug(f"Short pause: {secs:.1f}s")
    time.sleep(secs)


def _human_pause(lo: float = 0.3, hi: float = 0.9) -> None:
    """Short micro-delay between sequential actions."""
    time.sleep(random.uniform(lo, hi))
