from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from .engine import create_database_engine
from .models import WordForm, WordFormRuby
from .normalization import canonicalize_lemma, canonicalize_reading


@dataclass
class FuriganaReport:
    source: str
    source_sha256: str
    matched_forms: int
    unmatched_forms: int
    segments: int
    duplicate_keys: int
    invalid_entries: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_stream(path: Path) -> Iterator[BinaryIO]:
    with path.open("rb") as probe:
        magic = probe.read(4)

    if magic.startswith(b"PK"):
        with zipfile.ZipFile(path) as archive:
            name = next(
                (
                    item
                    for item in archive.namelist()
                    if item.endswith("JmdictFurigana.json")
                ),
                None,
            )
            if name is None:
                raise ValueError(f"JmdictFurigana.json not found in {path}")
            with archive.open(name) as handle:
                yield handle
        return

    if magic.startswith(b"\x1f\x8b"):
        try:
            with tarfile.open(path, mode="r:gz") as archive:
                member = next(
                    (
                        item
                        for item in archive.getmembers()
                        if item.name.endswith("JmdictFurigana.json")
                    ),
                    None,
                )
                if member is None:
                    raise ValueError(f"JmdictFurigana.json not found in {path}")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ValueError(f"Cannot read {member.name} from {path}")
                with handle:
                    yield handle
            return
        except tarfile.ReadError:
            with gzip.open(path, "rb") as handle:
                yield handle
            return

    if path.suffix.casefold() == ".gz":
        with gzip.open(path, "rb") as handle:
            yield handle
        return

    with path.open("rb") as handle:
        yield handle


def _load_entries(path: Path) -> list[dict[str, Any]]:
    for stream in _json_stream(path):
        data = json.load(stream)
        if not isinstance(data, list):
            raise ValueError("JmdictFurigana JSON must contain a top-level array")
        return data
    raise ValueError(f"Cannot read {path}")


def _segments(
    entry: dict[str, Any],
) -> tuple[str, str, list[tuple[str, str | None]]] | None:
    text = canonicalize_lemma(str(entry.get("text", "")))
    reading = canonicalize_reading(str(entry.get("reading", "")))
    raw_segments = entry.get("furigana")
    if not text or not reading or not isinstance(raw_segments, list):
        return None

    segments = []
    for item in raw_segments:
        if not isinstance(item, dict):
            return None
        segment_text = canonicalize_lemma(str(item.get("ruby", "")))
        if not segment_text:
            return None
        raw_rt = item.get("rt")
        segment_reading = canonicalize_reading(str(raw_rt)) if raw_rt else None
        segments.append((segment_text, segment_reading))

    if "".join(segment[0] for segment in segments) != text:
        return None
    reconstructed = "".join(
        reading_part or text_part for text_part, reading_part in segments
    )
    if reconstructed != reading:
        return None
    return text, reading, segments


def enrich_furigana(
    database: str | Path,
    furigana_json: str | Path,
) -> FuriganaReport:
    """Replace word-form ruby data using a JmdictFurigana JSON release."""

    source = Path(furigana_json).resolve()
    entries = _load_entries(source)
    engine = create_database_engine(database, must_exist=True)
    matched_forms = 0
    unmatched_forms = 0
    segment_count = 0
    duplicate_keys = 0
    invalid_entries = 0

    try:
        with Session(engine) as session:
            forms = session.execute(
                select(
                    WordForm.id,
                    WordForm.lemma,
                    WordForm.reading,
                )
            ).all()
            needed: dict[tuple[str, str], list[int]] = defaultdict(list)
            for form_id, lemma, reading in forms:
                needed[(lemma, reading)].append(form_id)

            session.execute(delete(WordFormRuby))
            seen_keys: set[tuple[str, str]] = set()
            ruby_rows = []
            for entry in entries:
                parsed = _segments(entry)
                if parsed is None:
                    invalid_entries += 1
                    continue
                key = (parsed[0], parsed[1])
                form_ids = needed.get(key)
                if not form_ids:
                    continue
                if key in seen_keys:
                    duplicate_keys += 1
                    continue
                seen_keys.add(key)
                for form_id in form_ids:
                    matched_forms += 1
                    for position, (text, reading) in enumerate(parsed[2]):
                        ruby_rows.append(
                            {
                                "word_form_id": form_id,
                                "position": position,
                                "text": text,
                                "reading": reading,
                            }
                        )
                        segment_count += 1
            if ruby_rows:
                session.execute(insert(WordFormRuby.__table__), ruby_rows)
            session.commit()
            unmatched_forms = len(forms) - matched_forms
    finally:
        engine.dispose()

    return FuriganaReport(
        source=str(source),
        source_sha256=_sha256(source),
        matched_forms=matched_forms,
        unmatched_forms=unmatched_forms,
        segments=segment_count,
        duplicate_keys=duplicate_keys,
        invalid_entries=invalid_entries,
    )
