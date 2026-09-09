import time
import random

from anthropic import Anthropic

FALLBACK_QUOTES = [
    "A budget is a plan for making your money behave.",
    "Small, consistent savings build real financial freedom.",
    "Track today's spending to protect tomorrow's goals.",
    "Every naira, dollar, or pound tracked is a step toward control.",
]

_cache = {"quote": None, "generated_at": 0}


def get_daily_quote(app):
    cache_seconds = app.config["AI_QUOTE_CACHE_MINUTES"] * 60
    now = time.time()

    if _cache["quote"] and (now - _cache["generated_at"]) < cache_seconds:
        return _cache["quote"]

    quote = _generate_quote(app)
    _cache["quote"] = quote
    _cache["generated_at"] = now
    return quote


def _generate_quote(app):
    api_key = app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        return random.choice(FALLBACK_QUOTES)

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=40,
            messages=[{
                "role": "user",
                "content": (
                    "Write one short, original, encouraging quote (under 20 words) about "
                    "personal financial discipline or saving money. Return only the quote "
                    "text, no attribution, no quotation marks."
                ),
            }],
        )
        text = response.content[0].text.strip()
        return text if text else random.choice(FALLBACK_QUOTES)
    except Exception:
        return random.choice(FALLBACK_QUOTES)