from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

SPELLER_URL = "https://speller.yandex.net/services/spellservice.json/checkText"


async def suggest_correction(text: str, timeout: float = 5.0) -> str | None:
    """Call Yandex Speller API to suggest a corrected version of the text.

    Returns the corrected string if spelling errors were found, None otherwise.
    Returns None on any network/parsing error (graceful degradation).
    """
    if not text or not text.strip():
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(SPELLER_URL, params={"lang": "ru", "text": text})
            resp.raise_for_status()
            errors = resp.json()
    except Exception:
        logger.debug("Speller API call failed for text=%r", text, exc_info=True)
        return None

    if not errors:
        return None

    # Reconstruct corrected string by applying fixes in reverse position order
    corrected = text
    for error in sorted(errors, key=lambda e: e.get("pos", 0), reverse=True):
        suggestions = error.get("s", [])
        if not suggestions:
            continue
        pos = error.get("pos", 0)
        length = error.get("len", 0)
        corrected = corrected[:pos] + suggestions[0] + corrected[pos + length:]

    if corrected == text:
        return None

    return corrected
