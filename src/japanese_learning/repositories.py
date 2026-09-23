from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import DictionaryExample, SourceDeck, Word, WordForm, WordFormRuby
from .normalization import canonicalize_lemma, canonicalize_reading


def database_stats(session: Session) -> dict[str, Any]:
    """Return current row counts grouped by table and JLPT level."""

    def count(model: type[object]) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    level_counts = session.execute(
        select(
            SourceDeck.level,
            func.count(func.distinct(Word.id)),
        )
        .join(Word, Word.deck_id == SourceDeck.id)
        .group_by(SourceDeck.level)
        .order_by(SourceDeck.level.desc())
    ).all()
    return {
        "deck_count": count(SourceDeck),
        "word_count": count(Word),
        "form_count": count(WordForm),
        "ruby_segment_count": count(WordFormRuby),
        "ruby_form_count": int(
            session.scalar(select(func.count(func.distinct(WordFormRuby.word_form_id))))
            or 0
        ),
        "example_count": count(DictionaryExample),
        "level_counts": [
            {"level": level, "count": count} for level, count in level_counts
        ],
    }


def lookup_forms(
    session: Session,
    lemma: str,
    reading: str | None = None,
) -> list[dict[str, Any]]:
    """Look up dictionary entries by canonical lemma and optional reading."""

    canonical_lemma = canonicalize_lemma(lemma)
    canonical_reading = canonicalize_reading(reading) if reading else None
    statement = (
        select(WordForm)
        .options(
            selectinload(WordForm.word).selectinload(Word.forms),
            selectinload(WordForm.word).selectinload(Word.deck),
            selectinload(WordForm.word).selectinload(Word.dictionary_examples),
            selectinload(WordForm.ruby_segments),
        )
        .where(WordForm.lemma == canonical_lemma)
        .order_by(WordForm.id)
        .limit(20)
    )
    if canonical_reading:
        statement = statement.where(WordForm.reading == canonical_reading)
    forms = list(session.execute(statement).scalars())
    if not forms and canonical_reading is None:
        fallback = (
            select(WordForm)
            .options(
                selectinload(WordForm.word).selectinload(Word.forms),
                selectinload(WordForm.word).selectinload(Word.deck),
                selectinload(WordForm.word).selectinload(Word.dictionary_examples),
                selectinload(WordForm.ruby_segments),
            )
            .where(WordForm.reading == canonical_lemma)
            .order_by(WordForm.id)
            .limit(20)
        )
        forms = list(session.execute(fallback).scalars())

    matches = []
    seen_word_ids: set[int] = set()
    for form in forms:
        if form.word_id in seen_word_ids:
            continue
        seen_word_ids.add(form.word_id)
        word = form.word
        matches.append(
            {
                "word_id": word.id,
                "canonical_lemma": word.main_form.lemma,
                "canonical_reading": word.main_form.reading,
                "pos": word.pos_json,
                "matched_lemma": form.lemma,
                "matched_reading": form.reading,
                "ruby": [
                    {
                        "text": segment.text,
                        "reading": segment.reading,
                    }
                    for segment in form.ruby_segments
                ],
                "meaning_zh_hans": word.meaning_zh_hans,
                "meaning_zh_hant": word.meaning_zh_hant,
                "jlpt_profile": {
                    "level": word.deck.level,
                    "frequency_class": word.deck.frequency_class,
                },
                "examples": [
                    {
                        "relation_type": example.relation_type,
                        "sentence_ja": example.sentence_ja,
                        "sentence_furigana": example.sentence_furigana,
                        "sentence_zh_hans": example.sentence_zh_hans,
                        "sentence_zh_hant": example.sentence_zh_hant,
                        "audio_filename": example.audio_filename,
                    }
                    for example in word.dictionary_examples
                ],
            }
        )
    return matches
