# Instagram Android Reels Bot

Scrolls Instagram Reels on an Android device, classifies content with Ollama,
and engages based on niche match. Built on top of the TikTok refactored bot's
human-randomness architecture.

## Setup

```bash
pip install -r requirements.txt
# Also install uiautomator2 on the device:
python -m uiautomator2 init
```

## Usage

```bash
python bot.py roblox
python bot.py brawlstars
python bot.py minecraft
```

## Engagement Logic

| Condition       | Action                                                  |
|-----------------|---------------------------------------------------------|
| Niche match     | +5–8s watch time, 80% like, 10% follow, always copy URL |
| No match        | 8% like (organic)                                       |
| Any video       | Random pause 2–6s (85%) or 8–15s (15%)                 |

## Files

```
bot.py                      ← Entry point (pass niche as CLI arg)
src/
  scraper.py                ← All device interactions (u2 + OCR)
  scroll_session.py         ← Main loop + engagement logic
  labelaizer.py             ← Ollama niche classifier
  niche_prompts.py          ← Per-niche system prompts
  storage.py                ← Text cleaning + URL saving
data/
  saved_urls.txt            ← Qualifying URLs written here
  screenshots/              ← Temporary OCR screenshots (auto-cleaned)
```

## Configuration

- **Device ID**: Set `DEVICE_ID` in `src/scraper.py` (leave empty to auto-connect)
- **Session length**: `MIN/MAX_SESSION_MINUTES` in `src/scroll_session.py`
- **Probabilities**: `LIKE_PROB_MATCH`, `FOLLOW_PROB_MATCH`, `LIKE_PROB_NOMATCH`
- **Add niches**: Extend `NICHE_PROMPTS` in `src/niche_prompts.py`
