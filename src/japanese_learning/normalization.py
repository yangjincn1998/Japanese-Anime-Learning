from __future__ import annotations

import re
import unicodedata

SPACE_RE = re.compile(r"\s+")
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
KATAKANA_RE = re.compile(r"[\u30a1-\u30f6]")
READING_RE = re.compile(r"^[\u3040-\u309fー〜]+$")
FURIGANA_ANNOTATION_RE = re.compile(r"\[[^\]]*\]")
FORM_TOKEN_RE = re.compile(r"^[\u3040-\u30ff\u3400-\u9fff々〆ヵヶー]+$")
SUPPLEMENT_PUNCTUATION = set("。．.！？!?；;：:「」『』（）()【】[]、,，")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value)
    value = ZERO_WIDTH_RE.sub("", value)
    return SPACE_RE.sub(" ", value).strip()


def kata_to_hira(value: str) -> str:
    output: list[str] = []
    for char in value:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            output.append(chr(code - 0x60))
        else:
            output.append(char)
    return "".join(output)


def is_kana_only(value: str) -> bool:
    value = clean_text(value)
    if not value:
        return False
    return bool(KANA_RE.search(value)) and not re.search(
        r"[^\u3040-\u30ffー・〜～\s]",
        value,
    )


def canonicalize_lemma(value: str) -> str:
    value = clean_text(value)
    value = value.replace("～", "〜")
    value = FURIGANA_ANNOTATION_RE.sub("", value)
    return SPACE_RE.sub("", value)


def canonicalize_reading(value: str) -> str:
    return kata_to_hira(canonicalize_lemma(value))


def is_canonical_reading(value: str) -> bool:
    return bool(READING_RE.fullmatch(value))


def derive_primary_reading(headword: str, raw_reading: str) -> str:
    headword = clean_text(headword)
    raw_reading = clean_text(raw_reading)
    if is_kana_only(headword):
        return canonicalize_reading(headword)
    if is_kana_only(raw_reading):
        return canonicalize_reading(raw_reading)
    return canonicalize_reading(headword)


def extract_obvious_variants(
    primary: str,
    supplement: str,
) -> tuple[list[str], bool]:
    """Return obvious alternate spellings and whether parsing was conservative.

    The second value is true when the supplement looked like free text rather
    than a short list of written forms.
    """

    primary = clean_text(primary)
    supplement = clean_text(supplement)
    if not supplement:
        return [], False
    if any(char in SUPPLEMENT_PUNCTUATION for char in supplement):
        return [], True

    parts = [clean_text(part) for part in supplement.split("・")]
    if any(not part for part in parts):
        return [], True
    if len(parts) > 5:
        return [], True

    variants: list[str] = []
    for part in parts:
        if part == primary:
            continue
        if not 1 <= len(part) <= 12:
            return [], True
        if not FORM_TOKEN_RE.fullmatch(part):
            return [], True
        if part not in variants:
            variants.append(part)
    return variants, False
