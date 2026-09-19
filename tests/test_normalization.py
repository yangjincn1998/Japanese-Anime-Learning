from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from jlpt_db.normalization import (  # noqa: E402
    canonicalize_lemma,
    canonicalize_reading,
    derive_primary_reading,
    extract_obvious_variants,
)
from jlpt_db.enums import ExampleRelation, PartOfSpeech  # noqa: E402
from jlpt_db.importer import _parse_examples, _parse_pos_values  # noqa: E402


def test_kana_headword_does_not_use_etymology_as_reading() -> None:
    assert derive_primary_reading("タバコ", "(ポ) tabaco") == "たばこ"
    assert derive_primary_reading("タイプ", "type") == "たいぷ"


def test_kanji_headword_uses_kana_reading() -> None:
    assert derive_primary_reading("高校", "こうこう") == "こうこう"


def test_obvious_variants() -> None:
    assert extract_obvious_variants("きれい", "奇麗・綺麗") == (
        ["奇麗", "綺麗"],
        False,
    )
    assert extract_obvious_variants("できる", "出来る") == (
        ["出来る"],
        False,
    )


def test_free_text_supplement_is_not_parsed() -> None:
    variants, unparsed = extract_obvious_variants(
        "高校",
        "「高等学校」の略",
    )
    assert variants == []
    assert unparsed is True


def test_canonicalization_keeps_lemma_and_normalizes_reading() -> None:
    assert canonicalize_lemma("  タバコ  ") == "タバコ"
    assert canonicalize_reading("タバコ") == "たばこ"


def test_canonicalization_strips_furigana_annotations() -> None:
    assert canonicalize_lemma("絆[きずな]") == "絆"
    assert canonicalize_lemma("冴[さ]える") == "冴える"
    assert canonicalize_lemma("石 鹸[けん]") == "石鹸"


def test_pos_values_strip_pitch_marks_before_unicode_normalization() -> None:
    assert _parse_pos_values("副①・自動3①") == [
        PartOfSpeech.ADVERB,
        PartOfSpeech.INTRANSITIVE_V3,
    ]


def test_example_relation_is_stored_as_enum() -> None:
    examples = _parse_examples(
        {
            "SentKanji1": "関連語",
            "SentType1": "関",
            "SentKanji2": "対義語",
            "SentType2": "対",
        }
    )
    assert [example.relation_type for example in examples] == [
        ExampleRelation.RELATED,
        ExampleRelation.ANTONYM,
    ]
