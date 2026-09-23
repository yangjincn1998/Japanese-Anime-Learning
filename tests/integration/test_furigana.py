from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from japanese_learning.engine import initialize_database  # noqa: E402
from japanese_learning.enums import FrequencyClass, JlptLevel, PartOfSpeech  # noqa: E402
from japanese_learning.furigana import enrich_furigana  # noqa: E402
from japanese_learning.models import (  # noqa: E402
    SourceDeck,
    Word,
    WordForm,
    WordFormRuby,
)


def _seed_database(path: Path) -> None:
    engine = initialize_database(path, replace=True)
    with Session(engine) as session:
        session.execute(text("PRAGMA defer_foreign_keys = ON"))
        session.add_all(
            [
                SourceDeck(
                    id=1,
                    level=JlptLevel.N1,
                    frequency_class=FrequencyClass.LOW,
                ),
                Word(
                    id=1,
                    main_form_id=1,
                    deck_id=1,
                    pos_json=[PartOfSpeech.NOUN],
                    meaning_zh_hans="琐碎",
                    meaning_zh_hant="瑣碎",
                    fields_json={},
                ),
                Word(
                    id=2,
                    main_form_id=2,
                    deck_id=1,
                    pos_json=[PartOfSpeech.TRANSITIVE_V2],
                    meaning_zh_hans="吃",
                    meaning_zh_hant="吃",
                    fields_json={},
                ),
                WordForm(id=1, word_id=1, lemma="些細", reading="ささい"),
                WordForm(id=2, word_id=2, lemma="食べる", reading="たべる"),
            ]
        )
        session.commit()
    engine.dispose()


def test_enrich_furigana(tmp_path: Path) -> None:
    database = tmp_path / "jlpt.sqlite"
    source = tmp_path / "JmdictFurigana.json"
    _seed_database(database)
    source.write_text(
        json.dumps(
            [
                {
                    "text": "些細",
                    "reading": "ささい",
                    "furigana": [
                        {"ruby": "些", "rt": "さ"},
                        {"ruby": "細", "rt": "さい"},
                    ],
                },
                {
                    "text": "食べる",
                    "reading": "たべる",
                    "furigana": [
                        {"ruby": "食", "rt": "た"},
                        {"ruby": "べる"},
                    ],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = enrich_furigana(database, source)
    assert report.matched_forms == 2
    assert report.unmatched_forms == 0
    assert report.segments == 4

    engine = initialize_database(database)
    with Session(engine) as session:
        rows = session.query(WordFormRuby).order_by(
            WordFormRuby.word_form_id,
            WordFormRuby.position,
        )
        values = [(row.text, row.reading) for row in rows]
        assert values == [
            ("些", "さ"),
            ("細", "さい"),
            ("食", "た"),
            ("べる", None),
        ]
    engine.dispose()
