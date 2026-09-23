from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from japanese_learning.engine import current_revision, initialize_database  # noqa: E402
from japanese_learning.enums import (  # noqa: E402
    ExampleRelation,
    FrequencyClass,
    JlptLevel,
    PartOfSpeech,
)
from japanese_learning.models import (  # noqa: E402
    Base,
    DictionaryExample,
    SourceDeck,
    Word,
    WordForm,
)
from japanese_learning.repositories import database_stats, lookup_forms  # noqa: E402


def _records() -> tuple[SourceDeck, Word, WordForm, WordForm, DictionaryExample]:
    deck = SourceDeck(
        id=1,
        level=JlptLevel.N5,
        frequency_class=FrequencyClass.HIGH,
    )
    word = Word(
        id=1,
        main_form_id=1,
        deck_id=1,
        pos_json=[PartOfSpeech.INTRANSITIVE_V2],
        meaning_zh_hans="可以，会",
        meaning_zh_hant="可以，會",
        fields_json={},
    )
    primary = WordForm(
        id=1,
        word_id=1,
        lemma="できる",
        reading="できる",
    )
    variant = WordForm(
        id=2,
        word_id=1,
        lemma="出来る",
        reading="できる",
    )
    example = DictionaryExample(
        id=1,
        word_id=1,
        relation_type=ExampleRelation.EXAMPLE,
        sentence_ja="彼女はイタリア語ができます",
        sentence_zh_hans="她会说意大利文",
    )
    return deck, word, primary, variant, example


def _add_records(
    session: Session,
    records: tuple[SourceDeck, Word, WordForm, WordForm, DictionaryExample],
) -> None:
    session.execute(text("PRAGMA defer_foreign_keys = ON"))
    deck, word, primary, variant, example = records
    session.add_all([deck, word, primary, variant, example])
    session.commit()


def test_all_models_and_columns_have_chinese_comments() -> None:
    for table in Base.metadata.tables.values():
        assert table.comment
        for column in table.columns:
            assert column.comment, f"{table.name}.{column.name} lacks a comment"


def test_sqlalchemy_schema_roundtrip(tmp_path: Path) -> None:
    database = tmp_path / "jlpt.sqlite"
    engine = initialize_database(database, replace=True)
    assert current_revision(engine)
    with Session(engine) as session:
        _add_records(session, _records())
        matches = lookup_forms(session, "出来る")
        assert len(matches) == 1
        assert matches[0]["canonical_lemma"] == "できる"
        assert matches[0]["matched_lemma"] == "出来る"
        assert matches[0]["examples"][0]["sentence_zh_hans"] == "她会说意大利文"
        assert matches[0]["jlpt_profile"] == {
            "level": JlptLevel.N5,
            "frequency_class": FrequencyClass.HIGH,
        }
        assert database_stats(session)["word_count"] == 1

        session.expire_all()
        stored_word = session.get(Word, 1)
        assert stored_word is not None
        assert stored_word.main_form.lemma == "できる"
        assert stored_word.main_form.reading == "できる"
        assert stored_word.pos_json == [PartOfSpeech.INTRANSITIVE_V2]
    engine.dispose()


def test_duplicate_form_within_word_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "jlpt.sqlite"
    engine = initialize_database(database, replace=True)
    with Session(engine) as session:
        deck, word, primary, _, example = _records()
        duplicate = WordForm(
            id=3,
            word_id=1,
            lemma="できる",
            reading="できる",
        )
        session.execute(text("PRAGMA defer_foreign_keys = ON"))
        session.add_all([deck, word, primary, duplicate, example])
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    engine.dispose()
