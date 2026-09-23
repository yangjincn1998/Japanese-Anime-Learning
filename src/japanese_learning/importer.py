from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from .engine import initialize_database
from .enums import ExampleRelation, FrequencyClass, JlptLevel, PartOfSpeech
from .models import DictionaryExample, SourceDeck, Word, WordForm
from .normalization import (
    canonicalize_lemma,
    canonicalize_reading,
    clean_text,
    derive_primary_reading,
    extract_obvious_variants,
    is_canonical_reading,
)

COLLECTION_NAMES = (
    "collection.anki21b",
    "collection.anki21",
    "collection.anki2",
)
LEVEL_RE = re.compile(r"N([1-5])")
POS_SEPARATOR_RE = re.compile(r"[・/／]+")
ACCENT_MARK_RE = re.compile(r"[①②③④⑤⓪]")
POS_SOURCE_MAP = {
    "名": PartOfSpeech.NOUN,
    "代": PartOfSpeech.PRONOUN,
    "ナ形": PartOfSpeech.NA_ADJECTIVE,
    "イ形": PartOfSpeech.I_ADJECTIVE,
    "形動トタル": PartOfSpeech.TARU_ADJECTIVE,
    "副": PartOfSpeech.ADVERB,
    "接頭": PartOfSpeech.PREFIX,
    "接尾": PartOfSpeech.SUFFIX,
    "接": PartOfSpeech.CONJUNCTION,
    "連体": PartOfSpeech.ATTRIBUTIVE,
    "感": PartOfSpeech.INTERJECTION,
    "連語": PartOfSpeech.PHRASE,
    "成句": PartOfSpeech.IDIOM,
    "造": PartOfSpeech.WORD_FORMING,
    "動1": PartOfSpeech.VERB_V1,
    "他動1": PartOfSpeech.TRANSITIVE_V1,
    "自動1": PartOfSpeech.INTRANSITIVE_V1,
    "自他動1": PartOfSpeech.TRANSITIVE_INTRANSITIVE_V1,
    "他動2": PartOfSpeech.TRANSITIVE_V2,
    "自動2": PartOfSpeech.INTRANSITIVE_V2,
    "自他動2": PartOfSpeech.TRANSITIVE_INTRANSITIVE_V2,
    "他動3": PartOfSpeech.TRANSITIVE_V3,
    "自動3": PartOfSpeech.INTRANSITIVE_V3,
    "自他動3": PartOfSpeech.TRANSITIVE_INTRANSITIVE_V3,
    "補動": PartOfSpeech.AUXILIARY_VERB,
    "補形": PartOfSpeech.AUXILIARY_ADJECTIVE,
    "副助": PartOfSpeech.ADVERBIAL_PARTICLE,
    "接助": PartOfSpeech.CONJUNCTIVE_PARTICLE,
    "格助": PartOfSpeech.CASE_PARTICLE,
    "終助": PartOfSpeech.FINAL_PARTICLE,
}


@dataclass
class ParsedExample:
    relation_type: ExampleRelation
    sentence_ja: str
    sentence_furigana: str
    sentence_zh_hans: str
    sentence_zh_hant: str
    audio_filename: str


@dataclass
class ParsedNote:
    anki_note_id: int
    deck_id: int
    deck_name: str
    fields: dict[str, str]
    headword: str
    reading: str
    pos_values: list[PartOfSpeech]
    meaning_zh_hans: str
    meaning_zh_hant: str
    variants: list[str]
    supplement_unparsed: bool
    level: JlptLevel
    frequency_class: FrequencyClass | None
    examples: list[ParsedExample]


@dataclass
class ImportReport:
    source: str
    source_version: str | None
    source_asset: str
    source_sha256: str
    output: str
    note_count: int
    deck_count: int
    word_count: int
    form_count: int
    example_count: int
    variants_added: int
    unparsed_supplements: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_version": self.source_version,
            "source_asset": self.source_asset,
            "source_sha256": self.source_sha256,
            "output": self.output,
            "note_count": self.note_count,
            "deck_count": self.deck_count,
            "word_count": self.word_count,
            "form_count": self.form_count,
            "example_count": self.example_count,
            "variants_added": self.variants_added,
            "unparsed_supplements": self.unparsed_supplements,
            "warnings": self.warnings,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_collection(apkg: Path, directory: Path) -> Path:
    with zipfile.ZipFile(apkg) as archive:
        names = set(archive.namelist())
        name = next((item for item in COLLECTION_NAMES if item in names), None)
        if name is None:
            raise ValueError(
                f"No Anki collection database found in {apkg}: "
                f"expected one of {COLLECTION_NAMES}"
            )
        if name.endswith("anki21b"):
            raise ValueError(
                "collection.anki21b requires zstd support; use collection.anki21"
            )
        output = directory / name
        with archive.open(name) as source, output.open("wb") as target:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                target.write(chunk)
        return output


@contextlib.contextmanager
def _collection_source(source: Path) -> Iterator[Path]:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if zipfile.is_zipfile(source):
        with tempfile.TemporaryDirectory(prefix="japanese-learning-") as directory:
            yield _extract_collection(source, Path(directory))
        return
    yield source


def _model_for(
    connection: sqlite3.Connection,
    requested_name: str | None,
) -> tuple[int, dict[str, Any]]:
    row = connection.execute("SELECT models FROM col LIMIT 1").fetchone()
    if row is None:
        raise ValueError("Anki collection has no col row")
    models = json.loads(row["models"])
    if requested_name:
        for model_id, model in models.items():
            if model.get("name") == requested_name:
                return int(model_id), model
        raise ValueError(f"Model not found: {requested_name}")
    if len(models) != 1:
        names = sorted(model.get("name", "") for model in models.values())
        raise ValueError(
            "Collection has multiple models; pass --model explicitly: "
            + ", ".join(names)
        )
    model_id, model = next(iter(models.items()))
    return int(model_id), model


def _required_fields(model: dict[str, Any]) -> list[str]:
    return [field["name"] for field in model["flds"]]


def _parse_level(value: str) -> JlptLevel:
    match = LEVEL_RE.search(value)
    if match is None:
        raise ValueError(f"JLPT level not found in source deck: {value!r}")
    return JlptLevel(f"N{match.group(1)}")


def _parse_frequency(value: str) -> FrequencyClass | None:
    return next((label for label in FrequencyClass if label in value), None)


def _parse_pos_values(value: str) -> list[PartOfSpeech]:
    values = []
    for part in POS_SEPARATOR_RE.split(value):
        normalized = clean_text(ACCENT_MARK_RE.sub("", part))
        if not normalized:
            continue
        part_of_speech = POS_SOURCE_MAP.get(normalized)
        if part_of_speech is None:
            raise ValueError(f"Unknown part of speech: {normalized!r}")
        values.append(part_of_speech)
    return list(dict.fromkeys(values))


def _audio_filename(value: str) -> str:
    match = re.search(r"\[sound:([^\]]+)\]", value)
    return match.group(1) if match else ""


def _parse_examples(fields: dict[str, str]) -> list[ParsedExample]:
    examples = []
    relation_map = {
        "": ExampleRelation.EXAMPLE,
        "関": ExampleRelation.RELATED,
        "対": ExampleRelation.ANTONYM,
    }
    for slot in range(1, 5):
        sentence = clean_text(fields.get(f"SentKanji{slot}", ""))
        if not sentence:
            continue
        raw_relation = clean_text(fields.get(f"SentType{slot}", ""))
        relation_type = relation_map.get(raw_relation)
        if relation_type is None:
            raise ValueError(f"Unknown example relation: {raw_relation!r}")
        examples.append(
            ParsedExample(
                relation_type=relation_type,
                sentence_ja=sentence,
                sentence_furigana=clean_text(fields.get(f"SentFurigana{slot}", "")),
                sentence_zh_hans=clean_text(fields.get(f"SentDefSC{slot}", "")),
                sentence_zh_hant=clean_text(fields.get(f"SentDefTC{slot}", "")),
                audio_filename=_audio_filename(fields.get(f"SentAudio{slot}", "")),
            )
        )
    return examples


def _parse_note(
    note: sqlite3.Row,
    fields: dict[str, str],
    decks: dict[str, dict[str, Any]],
) -> ParsedNote:
    deck_id = int(note["deck_id"]) if note["deck_id"] is not None else None
    if deck_id is None:
        raise ValueError(f"Source note {note['anki_note_id']} has no deck")
    deck_name = str(decks.get(str(deck_id), {}).get("name", ""))
    level_source = f"{deck_name} {note['tags']}"
    headword = canonicalize_lemma(fields["VocabKanji"])
    raw_reading = clean_text(fields["VocabFurigana"])
    reading = derive_primary_reading(headword, raw_reading)
    if not is_canonical_reading(reading):
        raise ValueError(
            f"Reading is not canonical hiragana for {note['anki_note_id']}: "
            f"{reading!r}"
        )
    variants, unparsed = extract_obvious_variants(
        headword,
        clean_text(fields.get("VocabPlus", "")),
    )
    return ParsedNote(
        anki_note_id=int(note["anki_note_id"]),
        deck_id=deck_id,
        deck_name=deck_name,
        fields=fields,
        headword=headword,
        reading=reading,
        pos_values=_parse_pos_values(fields.get("VocabPoS", "")),
        meaning_zh_hans=clean_text(fields.get("VocabDefSC", "")),
        meaning_zh_hant=clean_text(fields.get("VocabDefTC", "")),
        variants=variants,
        supplement_unparsed=unparsed,
        level=_parse_level(level_source),
        frequency_class=_parse_frequency(level_source),
        examples=_parse_examples(fields),
    )


def _read_notes(
    connection: sqlite3.Connection,
    model_id: int,
    fields: list[str],
) -> list[ParsedNote]:
    deck_row = connection.execute("SELECT decks FROM col LIMIT 1").fetchone()
    decks = json.loads(deck_row["decks"]) if deck_row else {}
    rows = connection.execute(
        """
        SELECT
          n.id AS anki_note_id,
          n.tags AS tags,
          n.flds AS flds,
          MIN(c.did) AS deck_id
        FROM notes n
        LEFT JOIN cards c ON c.nid = n.id
        WHERE n.mid = ?
        GROUP BY n.id
        ORDER BY n.id
        """,
        (model_id,),
    )
    notes = []
    for row in rows:
        values = str(row["flds"]).split("\x1f")
        if len(values) != len(fields):
            raise ValueError(
                f"Note {row['anki_note_id']} has {len(values)} fields; "
                f"model expects {len(fields)}"
            )
        field_values = dict(zip(fields, values, strict=True))
        notes.append(_parse_note(row, field_values, decks))
    return notes


def _build_records(
    notes: list[ParsedNote],
) -> tuple[
    list[SourceDeck],
    list[Word],
    list[WordForm],
    list[DictionaryExample],
    int,
]:
    decks: dict[int, SourceDeck] = {}
    words: list[Word] = []
    forms: list[WordForm] = []
    examples: list[DictionaryExample] = []
    next_form_id = 1
    variants_added = 0

    for note in sorted(
        notes,
        key=lambda item: (
            int(item.level[1:]),
            item.deck_id,
            item.anki_note_id,
        ),
    ):
        deck = decks.get(note.deck_id)
        if deck is None:
            deck = SourceDeck(
                id=note.deck_id,
                level=note.level,
                frequency_class=note.frequency_class,
            )
            decks[note.deck_id] = deck

        word_id = len(words) + 1
        primary_form = WordForm(
            id=next_form_id,
            word_id=word_id,
            lemma=note.headword,
            reading=note.reading,
        )
        next_form_id += 1
        form_keys = {(primary_form.lemma, primary_form.reading)}
        forms.append(primary_form)

        for variant in note.variants:
            lemma = canonicalize_lemma(variant)
            key = (lemma, note.reading)
            if key in form_keys:
                continue
            form_keys.add(key)
            forms.append(
                WordForm(
                    id=next_form_id,
                    word_id=word_id,
                    lemma=lemma,
                    reading=note.reading,
                )
            )
            next_form_id += 1
            variants_added += 1

        words.append(
            Word(
                id=word_id,
                main_form_id=primary_form.id,
                deck_id=note.deck_id,
                pos_json=note.pos_values,
                meaning_zh_hans=note.meaning_zh_hans,
                meaning_zh_hant=note.meaning_zh_hant,
                fields_json=note.fields,
            )
        )
        for example in note.examples:
            examples.append(
                DictionaryExample(
                    word_id=word_id,
                    sentence_ja=example.sentence_ja,
                    sentence_furigana=example.sentence_furigana,
                    sentence_zh_hans=example.sentence_zh_hans,
                    sentence_zh_hant=example.sentence_zh_hant,
                    audio_filename=example.audio_filename,
                    relation_type=example.relation_type,
                )
            )

    # Store the per-note variant count in a lightweight side channel so the
    # caller can report a useful total without keeping a second accumulator.
    return (
        list(decks.values()),
        words,
        forms,
        examples,
        variants_added,
    )


def _insert_records(
    session: Session,
    decks: list[SourceDeck],
    words: list[Word],
    forms: list[WordForm],
    examples: list[DictionaryExample],
) -> None:
    session.execute(text("PRAGMA defer_foreign_keys = ON"))
    session.execute(
        insert(SourceDeck.__table__),
        [
            {
                "id": deck.id,
                "level": deck.level,
                "frequency_class": deck.frequency_class,
            }
            for deck in decks
        ],
    )
    session.execute(
        insert(Word.__table__),
        [
            {
                "id": word.id,
                "main_form_id": word.main_form_id,
                "deck_id": word.deck_id,
                "pos_json": word.pos_json,
                "meaning_zh_hans": word.meaning_zh_hans,
                "meaning_zh_hant": word.meaning_zh_hant,
                "fields_json": word.fields_json,
            }
            for word in words
        ],
    )
    session.execute(
        insert(WordForm.__table__),
        [
            {
                "id": form.id,
                "word_id": form.word_id,
                "lemma": form.lemma,
                "reading": form.reading,
            }
            for form in forms
        ],
    )
    session.execute(
        insert(DictionaryExample.__table__),
        [
            {
                "id": example.id,
                "word_id": example.word_id,
                "sentence_ja": example.sentence_ja,
                "sentence_furigana": example.sentence_furigana,
                "sentence_zh_hans": example.sentence_zh_hans,
                "sentence_zh_hant": example.sentence_zh_hant,
                "audio_filename": example.audio_filename,
                "relation_type": example.relation_type,
            }
            for example in examples
        ],
    )
    session.commit()


def import_collection(
    source: str | Path,
    output: str | Path,
    *,
    model_name: str | None = None,
    replace: bool = False,
) -> ImportReport:
    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if output_path.exists() and not replace:
        raise FileExistsError(
            f"{output_path} already exists; pass replace=True to rebuild it"
        )

    with _collection_source(source_path) as collection_path:
        source_hash = _sha256(collection_path)
        input_connection = sqlite3.connect(collection_path)
        input_connection.row_factory = sqlite3.Row
        try:
            model_id, model = _model_for(input_connection, model_name)
            fields = _required_fields(model)
            required = {
                "NoteID",
                "VocabKanji",
                "VocabFurigana",
                "VocabPoS",
                "VocabDefSC",
                "VocabDefTC",
                "VocabPlus",
                "Order",
            }
            missing = required - set(fields)
            if missing:
                raise ValueError(
                    f"Model {model.get('name')} is missing fields: {sorted(missing)}"
                )
            notes = _read_notes(input_connection, model_id, fields)
        finally:
            input_connection.close()

    decks, words, forms, examples, variants_added = _build_records(notes)
    engine = initialize_database(output_path, replace=True)
    try:
        with Session(engine) as session:
            _insert_records(session, decks, words, forms, examples)
    finally:
        engine.dispose()

    report = ImportReport(
        source="5mdld",
        source_version=None,
        source_asset=source_path.name,
        source_sha256=source_hash,
        output=str(output_path),
        note_count=len(notes),
        deck_count=len(decks),
        word_count=len(words),
        form_count=len(forms),
        example_count=len(examples),
        variants_added=variants_added,
        unparsed_supplements=sum(1 for note in notes if note.supplement_unparsed),
    )
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report
