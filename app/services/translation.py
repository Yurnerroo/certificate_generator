"""UA -> EN translation for the training title and location fields.

Uses `deep-translator`'s free backends (no API key needed): GoogleTranslator
first, falling back to MyMemoryTranslator if Google is unavailable or
rate-limiting requests (a common occurrence on shared/corporate networks).
Since this depends on network access, failures are handled gracefully: the
caller gets back an empty string plus a human-readable warning instead of a
raised exception, so certificate generation can still proceed (with the
English field left blank for the user to fill in manually and regenerate).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Some free translation backends (particularly the MyMemory fallback) return
# proper nouns lowercase, e.g. "alicante, spain" instead of "Alicante, Spain".
# This capitalizes the first letter of every word (after start-of-string,
# whitespace, hyphen, or an opening bracket/quote) without touching letters
# that are already uppercase, so a correctly-cased Google Translate result
# passes through unchanged.
_WORD_START_RE = re.compile(r"(^|[\s\-(\"'/])([a-z])")


def _fix_capitalization(text: str) -> str:
    return _WORD_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)


class TranslationResult:
    def __init__(self, text: str, warning: str | None = None):
        self.text = text
        self.warning = warning


def _translate_with_google(text: str) -> str:
    from deep_translator import GoogleTranslator

    translated = GoogleTranslator(source="uk", target="en").translate(text)
    if not translated:
        raise ValueError("empty translation result")
    return translated.strip()


def _translate_with_mymemory(text: str) -> str:
    from deep_translator import MyMemoryTranslator

    translated = MyMemoryTranslator(source="uk-UA", target="en-GB").translate(text)
    if not translated:
        raise ValueError("empty translation result")
    return translated.strip()


def translate_uk_to_en(text: str, field_label: str) -> TranslationResult:
    """Translate `text` from Ukrainian to English.

    `field_label` is a human-readable field name (e.g. "Назва тренінгу") used
    to build a clear warning message if translation fails.
    """
    text = (text or "").strip()
    if not text:
        return TranslationResult("", None)

    # Imported/called lazily so the whole app doesn't fail to start if the
    # optional dependency / its own imports have trouble in some
    # environment -- we degrade to "translation unavailable" instead.
    last_exc: Exception | None = None
    for translate_fn in (_translate_with_google, _translate_with_mymemory):
        try:
            return TranslationResult(_fix_capitalization(translate_fn(text)), None)
        except Exception as exc:  # noqa: BLE001 - try the next backend / degrade gracefully
            last_exc = exc
            logger.warning(
                "Auto-translation via %s failed for %s: %s",
                translate_fn.__name__,
                field_label,
                exc,
            )

    exc_name = type(last_exc).__name__ if last_exc else ""
    if "TooManyRequests" in exc_name or "429" in str(last_exc):
        reason = "сервіс перекладу тимчасово обмежив кількість запитів — спробуйте ще раз за кілька хвилин"
    else:
        reason = "немає інтернету або сервіс перекладу недоступний"
    warning = (
        f"Не вдалося автоматично перекласти поле «{field_label}» ({reason}). "
        f"Поле англійською залишено порожнім — заповніть його вручну "
        f"та згенеруйте сертифікати повторно."
    )
    return TranslationResult("", warning)
