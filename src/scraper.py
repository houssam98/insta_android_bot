"""
src/scraper.py
==============
All Android device interactions for Instagram Reels via uiautomator2.

Resource IDs confirmed from live device inspection:
  - Like button       : com.instagram.android:id/like_button
  - Like count        : com.instagram.android:id/like_count
  - Follow button     : com.instagram.android:id/inline_follow_button
  - Caption parent    : com.instagram.android:id/clips_caption_component
  - Video overlay     : com.instagram.android:id/clips_item_overlay_component
  - Share button      : com.instagram.android:id/direct_share_button
  - Copy link button  : com.instagram.android:id/button

All clicks use bounding-box coordinates with randomized offsets — never
clicking the element directly — to mimic human behaviour.
"""

import logging
import os
import random
import re
import time
import traceback

import easyocr
import uiautomator2 as u2
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEVICE_ID        = ""          # Leave empty to auto-connect, or set serial
SCREENSHOTS_PATH = os.path.join("data", "screenshots")

# ---------------------------------------------------------------------------
# Device + OCR (module-level — shared across imports)
# ---------------------------------------------------------------------------
d = u2.connect(DEVICE_ID) if DEVICE_ID else u2.connect()
reader = easyocr.Reader(["en"], gpu=False, verbose=False)

os.makedirs(SCREENSHOTS_PATH, exist_ok=True)


# ---------------------------------------------------------------------------
# Low-level click helpers
# ---------------------------------------------------------------------------
def _rand_click(bounds: dict, margin: int = 6) -> tuple[int, int]:
    """
    Return a random (x, y) coordinate inside the given bounds,
    avoiding the edge by `margin` pixels.
    Falls back to center if element is too small.
    """
    left, top     = bounds["left"],  bounds["top"]
    right, bottom = bounds["right"], bounds["bottom"]
    w = right - left
    h = bottom - top

    if w <= margin * 2 or h <= margin * 2:
        return (left + w // 2, top + h // 2)

    x = left + random.randint(margin, w - margin)
    y = top  + random.randint(margin, h - margin)
    return (x, y)


def _click_element(element, pre_delay: tuple = (0.4, 1.2), post_delay: tuple = (0.5, 1.4)) -> bool:
    """
    Click a random point inside element's bounding box.
    Never calls element.click() — always uses d.click(x, y).

    Returns True on success.
    """
    try:
        bounds = element.info["bounds"]
        x, y   = _rand_click(bounds)
        time.sleep(random.uniform(*pre_delay))
        d.click(x, y)
        time.sleep(random.uniform(*post_delay))
        return True
    except Exception as e:
        logger.debug(f"_click_element failed: {e}")
        return False


def _click_bounds(bounds: dict, pre_delay: tuple = (0.4, 1.2), post_delay: tuple = (0.5, 1.4)) -> bool:
    """Click a random point inside raw bounds dict."""
    try:
        x, y = _rand_click(bounds)
        time.sleep(random.uniform(*pre_delay))
        d.click(x, y)
        time.sleep(random.uniform(*post_delay))
        return True
    except Exception as e:
        logger.debug(f"_click_bounds failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Like count parser
# ---------------------------------------------------------------------------
def _parse_like_count(raw: str) -> int:
    """
    Parse Instagram like count from accessibility description.
    The description reads: "Like number is177856. View likes"
    Extracts the integer portion.
    Returns 0 if unparseable.
    """
    # Match the number directly after "is" (with or without space)
    match = re.search(r"is\s*([\d,]+)", raw, re.IGNORECASE)
    if match:
        num_str = match.group(1).replace(",", "")
        try:
            return int(num_str)
        except ValueError:
            pass

    # Fallback: find any standalone number in the string
    nums = re.findall(r"\d[\d,]*", raw)
    for n in nums:
        try:
            return int(n.replace(",", ""))
        except ValueError:
            continue
    return 0


# ---------------------------------------------------------------------------
# Caption extraction
# ---------------------------------------------------------------------------
def extract_caption_and_hashtags() -> tuple[str | None, str | None]:
    """
    Extract caption text from the current Instagram Reel.

    Strategy:
      1. Find com.instagram.android:id/clips_caption_component
      2. Navigate: ScrollView[0] → ViewGroup[0] → ViewGroup[0]
      3. Read description attribute
      4. If text contains "...", click the element to expand, then screenshot+OCR
      5. Otherwise use description text directly

    Returns:
        (caption, hashtags) tuple — either may be None.
    """
    try:
        caption_root = d(resourceId="com.instagram.android:id/clips_caption_component")
        if not caption_root.exists:
            logger.debug("Caption component not found.")
            return None, None

        # Navigate the hierarchy: ScrollView[0] → ViewGroup[0] → ViewGroup[0]
        scroll_view = caption_root.child(className="android.widget.ScrollView", index=0)
        if not scroll_view.exists:
            logger.debug("Caption ScrollView not found.")
            return None, None

        vg_outer = scroll_view.child(className="android.view.ViewGroup", index=0)
        if not vg_outer.exists:
            logger.debug("Caption outer ViewGroup not found.")
            return None, None

        vg_inner = vg_outer.child(className="android.view.ViewGroup", index=0)
        target = vg_inner if vg_inner.exists else vg_outer

        info        = target.info
        description = info.get("contentDescription", "") or info.get("text", "") or ""

        if not description:
            logger.debug("Caption description is empty.")
            return None, None

        # If truncated ("..."), click the "..." precisely then OCR.
        # We must NOT use _click_element(target) with a random offset —
        # the full bounding box includes hashtag links which would be
        # opened instead of expanding the caption.
        if "…" in description:
            logger.debug("Caption truncated — clicking '…' to expand.")
            _click_ellipsis(target, description)
            time.sleep(random.uniform(0.8, 1.5))
            text = _ocr_expanded_caption()
            # Dismiss the expanded view by clicking the overlay center
            _dismiss_overlay()
        else:
            text = description

        if not text:
            return None, None

        return _split_caption_hashtags(text)

    except Exception:
        logger.error(f"extract_caption_and_hashtags error:\n{traceback.format_exc()}")
        return None, None


def _click_ellipsis(caption_element, description: str) -> None:
    """
    Click the '...' (more) button precisely without hitting hashtag links.

    Strategy (in priority order):
      1. Find a child TextView/View whose text IS exactly '...' or 'more'
         and click its center — this is the safest target.
      2. If no such child exists, estimate the position of '...' inside
         the caption bounding box: it always appears at the END of the
         last visible line, so we click near the bottom-right of the box
         (avoiding the hashtag zone which is typically to the left).
      3. Never clicks a random point in the full bounds (old behavior that
         caused accidental hashtag taps).
    """
    try:
        # Priority 1 — look for a dedicated child element for the ellipsis/more
        for text_val in ("...", "more", "…"):
            child = caption_element.child(text=text_val)
            if child.exists:
                b  = child.info["bounds"]
                cx = (b["left"] + b["right"])  // 2 + random.randint(-3, 3)
                cy = (b["top"]  + b["bottom"]) // 2 + random.randint(-3, 3)
                time.sleep(random.uniform(0.3, 0.7))
                d.click(cx, cy)
                logger.debug(f"Clicked '...' child element at ({cx}, {cy}).")
                return

        # Priority 2 — '...' is at end of last visible line.
        # Estimate its position: bottom quarter of the element, right-biased
        # (but not the far right edge where hashtags cluster).
        b      = caption_element.info["bounds"]
        width  = b["right"] - b["left"]
        height = b["bottom"] - b["top"]

        # X: aim for 55–75 % of width (center-right, before hashtags at far right)
        x = b["left"] + int(width * random.uniform(0.55, 0.75))
        # Y: aim for the last 20 % of height (last visible line)
        y = b["top"]  + int(height * random.uniform(0.78, 0.92))

        time.sleep(random.uniform(0.3, 0.7))
        d.click(x, y)
        logger.debug(f"Clicked estimated '...' position at ({x}, {y}).")

    except Exception as e:
        logger.debug(f"_click_ellipsis error: {e}")


def _ocr_expanded_caption() -> str:
    """
    Screenshot and OCR the expanded caption panel.
    Uses the sticky_header_list container — same approach as the provided reference code.
    """
    try:
        container = d(resourceId="com.instagram.android:id/sticky_header_list")
        if not container.exists:
            logger.debug("sticky_header_list not found for OCR.")
            return ""

        target = container.child(className="android.view.ViewGroup", index=1)
        if not target.exists:
            logger.debug("OCR target ViewGroup not found.")
            return ""

        b = target.info["bounds"]
        top_padding    = 100
        bottom_padding = 50
        crop_coords = (
            b["left"],
            b["top"]  + top_padding,
            b["right"],
            b["bottom"] - bottom_padding,
        )

        screen_path = os.path.join(SCREENSHOTS_PATH, "_caption_full.png")
        crop_path   = os.path.join(SCREENSHOTS_PATH, "_caption_crop.png")

        d.screenshot(screen_path)
        img = Image.open(screen_path)

        if crop_coords[3] > crop_coords[1] and crop_coords[2] > crop_coords[0]:
            cropped = img.crop(crop_coords)
            cropped.save(crop_path)
        else:
            logger.debug("Invalid crop dimensions — using full screenshot.")
            crop_path = screen_path

        result = reader.readtext(crop_path, detail=0)

        # Cleanup temp screenshots
        for p in [screen_path, crop_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

        return " ".join(result).strip()

    except Exception:
        logger.error(f"_ocr_expanded_caption error:\n{traceback.format_exc()}")
        return ""


def _dismiss_overlay() -> None:
    """
    Click the center of clips_item_overlay_component to dismiss the caption
    bar and comments panel.
    """
    try:
        overlay = d(resourceId="com.instagram.android:id/clips_item_overlay_component")
        if overlay.exists:
            bounds = overlay.info["bounds"]
            cx = (bounds["left"] + bounds["right"])  // 2
            cy = (bounds["top"]  + bounds["bottom"]) // 2
            # Small random offset around center
            x = cx + random.randint(-15, 15)
            y = cy + random.randint(-15, 15)
            time.sleep(random.uniform(0.3, 0.7))
            d.click(x, y)
            time.sleep(random.uniform(0.4, 0.9))
            logger.debug("Dismissed overlay.")
    except Exception as e:
        logger.debug(f"_dismiss_overlay error: {e}")


def _split_caption_hashtags(text: str) -> tuple[str | None, str | None]:
    """Split raw text into (caption, hashtags) at the first '#'."""
    if "#" in text:
        idx = text.index("#")
        caption  = text[:idx].strip() or None
        hashtags = text[idx:].strip() or None
    else:
        caption  = text.strip() or None
        hashtags = None
    return caption, hashtags


# ---------------------------------------------------------------------------
# Like count
# ---------------------------------------------------------------------------
def get_like_count() -> int:
    """
    Read like count from com.instagram.android:id/like_count.
    The content description reads: "Like number is177856. View likes"
    Returns integer count or 0 if not found.
    """
    try:
        el = d(resourceId="com.instagram.android:id/like_count")
        if not el.exists:
            return 0
        info = el.info
        desc = info.get("contentDescription", "") or info.get("text", "") or ""
        count = _parse_like_count(desc)
        logger.debug(f"Like count raw='{desc}' → {count:,}")
        return count
    except Exception as e:
        logger.debug(f"get_like_count error: {e}")
        return 0


# ---------------------------------------------------------------------------
# Like video
# ---------------------------------------------------------------------------
def like_video() -> bool:
    """
    Click the like button using its bounding-box coordinates.
    Checks current state to avoid double-liking.
    Returns True on success.
    """
    try:
        btn = d(resourceId="com.instagram.android:id/like_button")
        if not btn.wait(timeout=3.0):
            logger.debug("Like button not found.")
            return False

        info    = btn.info
        desc    = (info.get("contentDescription") or "").lower()
        checked = info.get("checked", False)

        # Skip if already liked
        if checked or "unlike" in desc or "liked" in desc:
            logger.debug("Already liked — skipping.")
            return False

        success = _click_element(btn, pre_delay=(0.3, 0.9), post_delay=(0.6, 1.4))
        if success:
            logger.info("Liked video.")
        return success

    except Exception as e:
        logger.debug(f"like_video error: {e}")
        return False


# ---------------------------------------------------------------------------
# Follow author
# ---------------------------------------------------------------------------
def follow_author() -> bool:
    """
    Click the inline follow button using bounding-box coordinates.
    Skips if already following.
    Returns True on success.
    """
    try:
        btn = d(resourceId="com.instagram.android:id/inline_follow_button")
        if not btn.wait(timeout=3.0):
            logger.debug("Follow button not found.")
            return False

        info = btn.info
        desc = (info.get("contentDescription") or "").lower()
        text = (info.get("text") or "").lower()

        # Skip if already following
        if "following" in desc or "following" in text or "requested" in text:
            logger.debug("Already following — skipping.")
            return False

        success = _click_element(btn, pre_delay=(0.4, 1.0), post_delay=(0.8, 1.6))
        if success:
            logger.info("Followed author.")
        return success

    except Exception as e:
        logger.debug(f"follow_author error: {e}")
        return False


# ---------------------------------------------------------------------------
# Copy link (share flow)
# ---------------------------------------------------------------------------
def copy_and_get_link() -> str | None:
    """
    Opens the share bar, clicks the copy-link button, dismisses the sheet,
    and returns the URL by reading the clipboard.

    The share sheet is ALWAYS closed in the finally block — even on success —
    so the Reels feed is back in focus before swipe_next_video() is called.

    Returns the URL string or None on failure.
    """
    sheet_open = False
    url        = None
    try:
        # Step 1 — Open share bar
        share_btn = d(resourceId="com.instagram.android:id/direct_share_button")
        if not share_btn.wait(timeout=3.0):
            logger.debug("Share button not found.")
            return None

        _click_element(share_btn, pre_delay=(0.5, 1.2), post_delay=(1.2, 2.2))
        sheet_open = True
        logger.debug("Share bar opened.")

        # Step 2 — Find and click "Copy link" button
        copy_btn = d(resourceId="com.instagram.android:id/button",
                     descriptionContains="Copy link")
        if not copy_btn.exists:
            copy_btn = d(resourceId="com.instagram.android:id/button",
                         textContains="Copy")
        if not copy_btn.exists:
            copy_btn = d(resourceId="com.instagram.android:id/button")

        if not copy_btn.wait(timeout=4.0):
            logger.debug("Copy link button not found.")
            return None   # finally block will still dismiss

        _click_element(copy_btn, pre_delay=(0.4, 0.9), post_delay=(0.6, 1.3))
        logger.debug("Copy link clicked.")

        # Step 3 — Read clipboard
        time.sleep(random.uniform(0.6, 1.2))
        raw = d.clipboard
        if raw and "instagram.com" in str(raw):
            url = str(raw).strip()
            logger.info(f"Link copied: {url}")
        else:
            logger.debug(f"Clipboard value not an Instagram URL: {raw}")

    except Exception:
        logger.error(f"copy_and_get_link error:\n{traceback.format_exc()}")

    finally:
        # ALWAYS close the share sheet so Reels feed is back in focus
        # and the subsequent swipe_next_video() works correctly.
        if sheet_open:
            try:
                time.sleep(random.uniform(0.3, 0.7))
                d.press("back")
                time.sleep(random.uniform(0.6, 1.1))
                logger.debug("Share sheet dismissed.")
            except Exception as e:
                logger.debug(f"Sheet dismiss error: {e}")

    return url


# ---------------------------------------------------------------------------
# Swipe to next Reel
# ---------------------------------------------------------------------------
def swipe_next_video() -> None:
    """
    Swipe up to advance to the next Reel.
    Randomises start/end coordinates and swipe method each time.
    """
    width, height = d.window_size()

    method = random.random()

    if method < 0.40:
        # Standard swipe with randomized coordinates
        start_x = width  // 2 + random.randint(-20, 20)
        start_y = int(height * random.uniform(0.75, 0.85))
        end_x   = width  // 2 + random.randint(-15, 15)
        end_y   = int(height * random.uniform(0.20, 0.30))
        steps   = random.randint(6, 14)
        d.swipe(start_x, start_y, end_x, end_y, steps=steps)

    elif method < 0.70:
        # Quick swipe_ext
        d.swipe_ext("up", scale=random.uniform(0.70, 0.85))

    else:
        # Slower, more deliberate swipe
        start_x = width  // 2 + random.randint(-10, 10)
        start_y = int(height * 0.80)
        end_x   = width  // 2 + random.randint(-10, 10)
        end_y   = int(height * 0.25)
        steps   = random.randint(15, 25)
        d.swipe(start_x, start_y, end_x, end_y, steps=steps)
