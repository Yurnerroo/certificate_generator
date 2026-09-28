"""UA -> EN translation for the training title and location fields.

Uses `deep-translator`'s free GoogleTranslator backend (no API key needed).
Since this depends on network access, failures are handled gracefully: the
caller gets back an empty string plus a human-readable warning instead of a
raised exception, so certificate generation can still proceed (with the
English field left blank for the user to fill in manually and regenerate).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TranslationResult:
    def __init__(self, text: str, warning: str | None = None):
        self.text = text
        self.warning = warning


def translate_uk_to_en(text: str, field_label: str) -> TranslationResult:
    """Translate `text` from Ukrainian to English.

    `field_label` is a human-readable field name (e.g. "Назва тренінгу") used
    to build a clear warning message if translation fails.
    """
    text = (text or "").strip()
    if not text:
        return TranslationResult("", None)

    try:
        # Imported lazily so the whole app doesn't fail to start if the
        # optional dependency / its own imports have trouble in some
        # environment -- we degrade to "translation unavailable" instead.
        from deep_translator import GoogleTranslator

        translated = GoogleTranslator(source="uk", target="en").translate(text)
        if not translated:
            raise ValueError("empty translation result")
        return TranslationResult(translated.strip(), None)
    except Exception as exc:  # noqa: BLE001 - any failure should degrade gracefully
        logger.warning("Auto-translation failed for %s: %s", field_label, exc)
        warning = (
            f"Не вдалося автоматично перекласти поле «{field_label}» "
            f"(немає інтернету або сервіс перекладу недоступний). "
            f"Поле англійською залишено порожнім — заповніть його вручну "
            f"та згенеруйте сертифікати повторно."
        )
        return TranslationResult("", warning)
