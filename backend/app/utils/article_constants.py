"""Shared a/an pronunciation helpers for review and spell-check."""
import re

ABBR_VOWEL_SOUND = set("AEFHILMNORSX")
WORDLIKE_ALL_CAPS = {
    "home",
    "end",
    "start",
    "next",
    "back",
    "stop",
    "pause",
    "run",
    "save",
    "open",
    "close",
    "fastq",
    "bam",
    "cram",
    "sam",
    "tab",
}
WORDLIKE_CAPS = WORDLIKE_ALL_CAPS

_SILENT_H_RE = re.compile(r"^(honest|hour|honor|heir)", re.IGNORECASE)
_JU_SOUND_RE = re.compile(
    r"^(university|universal|unified|union|unilateral|user|unit|unique|european|eucalyptus|one|one-step)",
    re.IGNORECASE,
)


def is_wordlike_all_caps(word: str) -> bool:
    token = (word or "").strip(".,;:()[]{}\"'").strip()
    return bool(token) and token.isupper() and token.isalpha() and token.lower() in WORDLIKE_ALL_CAPS


def abbrev_article(word: str):
    token = (word or "").strip(".,;:()[]{}\"'").strip()
    if len(token) < 2 or not token.isupper() or not token.isalpha():
        return None
    if token.lower() in WORDLIKE_ALL_CAPS:
        return None
    return "an" if token[0] in ABBR_VOWEL_SOUND else "a"


def expected_article(word: str):
    """Return 'a'/'an' for a token, or None when both articles are accepted."""
    token = (word or "").strip(".,;:()[]{}\"'").strip()
    if not token:
        return None
    if is_wordlike_all_caps(token):
        return None
    head = token.split("-", 1)[0]
    if is_wordlike_all_caps(head):
        return None
    return "an" if is_vowel_sound(token) else "a"


def is_vowel_sound(word: str) -> bool:
    token = (word or "").strip(".,;:()[]{}\"'").strip()
    if not token:
        return False

    lower = token.lower()
    if _SILENT_H_RE.match(lower):
        return True
    if _JU_SOUND_RE.match(lower):
        return False
    if token.isupper() and token.isalpha():
        if lower in WORDLIKE_ALL_CAPS:
            return lower[0] in "aeiou"
        return token[0] in ABBR_VOWEL_SOUND
    head = token.split("-", 1)[0]
    if head and head.isupper() and head.isalpha():
        if head.lower() in WORDLIKE_ALL_CAPS:
            return head.lower()[0] in "aeiou"
        return head[0] in ABBR_VOWEL_SOUND
    return lower[0] in "aeiou"
