"""
src/storage.py
==============
Text cleaning and URL persistence utilities.
Ported from the TikTok refactored bot — blacklisted words/sentences preserved.
"""

import csv
import os
import re

SAVED_URLS_PATH = os.path.join("data", "saved_urls.txt")

to_string = lambda x: x or ""

black_listed_words = set([
    "a", "an", "the", "and", "or", "but", "if", "while",
    "is", "am", "are", "was", "were", "till",
    "be", "been", "being", "end",
    "to", "of", "in", "on", "at",
    "for", "with", "as", "by",
    "this", "that", "these", "those",
    "it", "its",
    "he", "she", "they", "them",
    "my", "your", "his", "her",
    "we", "us", "like",
    "likes", "comment", "comments", "share",
    "save", "live", "sound", "shop", "reply",
    "replies"
])

black_listed_sentences = set([
    "like and share", "comment below", "tag someone", "tag your friend",
    "double tap", "don't forget to", "link in bio", "check bio",
    "full screen", "subscribe", "follow me", "new post",
    "#fyp", "#foryou", "#foryoupage", "#viral", "#trending",
    "#trend", "#xyzbca", "#tiktok", "#tiktokviral",
    "#reels", "#shorts", "#video", "#explorepage",
    "#instagood", "#like4like", "#follow4follow",
    "watch till the end", "wait for it",
])


def clean_text(text: str) -> str:
    """Normalize and strip noise from caption/hashtag text."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z#\-_\s]", " ", text)
    text = text.replace("\u2019", "'")
    for sentence in black_listed_sentences:
        text = re.sub(re.escape(sentence.lower()), "", text)
    cleaned = [w for w in text.split() if w.lower() not in black_listed_words]
    text = " ".join(cleaned)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def save_url(url: str, like_count: int, niche: str) -> None:
    """Append a qualifying URL to the saved URLs file."""
    os.makedirs(os.path.dirname(SAVED_URLS_PATH) or ".", exist_ok=True)
    with open(SAVED_URLS_PATH, "a", encoding="utf-8") as f:
        f.write(f"{url}\t(likes: {like_count:,})\t[niche: {niche}]\n")
