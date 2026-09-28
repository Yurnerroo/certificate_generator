"""Deterministic Ukrainian -> Latin transliteration.

Implements the official transliteration table approved by Resolution of the
Cabinet of Ministers of Ukraine No. 55 (27 January 2010, as amended), which is
the table used on Ukrainian passports and by tools such as grafiati.com. There
is no public API for that resolution, so the character-mapping rules are
reproduced here directly -- fully offline and deterministic.

Reference mapping (lowercase source -> lowercase target unless noted):
    а=a   б=b   в=v   г=h   ґ=g   д=d   е=e   є=ie (ye at word start)
    ж=zh  з=z   и=y   і=i   ї=i (yi at word start)
    й=i (y at word start)
    к=k   л=l   м=m   н=n   о=o   п=p   р=r   с=s   т=t   у=u   ф=f
    х=kh  ц=ts  ч=ch  ш=sh  щ=shch
    ю=iu (yu at word start)   я=ia (ya at word start)
    ь and the apostrophe (' or ') are dropped (not reproduced).
"""
from __future__ import annotations

import re

# Simple one-to-one letters (word position does not matter).
_SIMPLE = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e",
    "ж": "zh", "з": "z", "и": "y", "і": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
}

# Letters whose Latin form depends on whether they start a word.
_WORD_INITIAL = {
    "є": ("ye", "ie"),
    "ї": ("yi", "i"),
    "й": ("y", "i"),
    "ю": ("yu", "iu"),
    "я": ("ya", "ia"),
}

# Dropped entirely (soft sign, apostrophe variants).
_DROPPED = {"ь", "'", "\u2019", "\u02bc", "`"}

# A "word" token is a maximal run of letters, allowing a single embedded
# apostrophe/soft-apostrophe between letter runs (so "Мар'яна" is one token
# and the apostrophe correctly does NOT reset word-initial tracking for the
# following letter). Hyphens, spaces, digits and other punctuation are
# separators copied through unchanged and DO reset word-initial tracking.
_WORD_TOKEN_RE = re.compile(
    r"[^\W\d_]+(?:['\u2019\u02bc`][^\W\d_]+)*", re.UNICODE
)


def _transliterate_word(word: str) -> str:
    """Transliterate a single word (no separators inside), lowercase result."""
    parts: list[str] = []
    at_word_start = True
    for ch in word:
        ch_lower = ch.lower()
        if ch_lower in _DROPPED:
            # Soft sign / apostrophe: dropped, but does not itself count as
            # "start of word" for a following letter.
            continue
        if ch_lower in _WORD_INITIAL:
            initial_form, mid_form = _WORD_INITIAL[ch_lower]
            parts.append(initial_form if at_word_start else mid_form)
        else:
            parts.append(_SIMPLE.get(ch_lower, ch_lower))
        at_word_start = False
    return "".join(parts)


def _apply_casing(original_word: str, latin_lower: str) -> str:
    """Re-apply the original word's casing style to its transliteration."""
    letters = [c for c in original_word if c.isalpha()]
    if not letters:
        return latin_lower
    if all(c.isupper() for c in letters):
        return latin_lower.upper()
    if letters[0].isupper():
        return latin_lower[:1].upper() + latin_lower[1:]
    return latin_lower


def transliterate(text: str) -> str:
    """Transliterate a Ukrainian string to Latin script per Resolution No. 55.

    Preserves the original casing style per word (all lowercase, Title case,
    or ALL CAPS). Non-Cyrillic characters (digits, punctuation, already-Latin
    text) and separators (spaces, hyphens, etc.) pass through unchanged, and
    each word is transliterated independently so hyphenated/compound names
    get correct word-initial handling (e.g. "Ana-Maria" style names).
    """
    if not text:
        return ""

    def _replace(match: re.Match) -> str:
        word = match.group(0)
        latin_lower = _transliterate_word(word)
        return _apply_casing(word, latin_lower)

    return _WORD_TOKEN_RE.sub(_replace, text)


def transliterate_name(full_name: str) -> str:
    """Transliterate a full name, trimming incidental whitespace."""
    return transliterate(full_name.strip())
