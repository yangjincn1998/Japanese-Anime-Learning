from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.orm import Session

from .engine import create_database_engine, current_revision, upgrade_database
from .furigana import enrich_furigana
from .importer import import_collection
from .paths import default_db_path
from .repositories import database_stats, lookup_forms


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _import(args: argparse.Namespace) -> int:
    source = args.apkg or args.collection
    report = import_collection(
        source,
        args.output,
        model_name=args.model,
        replace=args.replace,
    )
    if args.json:
        _print_json(report.to_dict())
    else:
        print(f"database={report.output}")
        print(f"notes={report.note_count}")
        print(f"decks={report.deck_count}")
        print(f"words={report.word_count}")
        print(f"forms={report.form_count}")
        print(f"examples={report.example_count}")
        print(f"variants_added={report.variants_added}")
        print(f"unparsed_supplements={report.unparsed_supplements}")
    return 0


def _stats(args: argparse.Namespace) -> int:
    engine = create_database_engine(args.db, must_exist=True)
    try:
        with Session(engine) as session:
            _print_json(database_stats(session))
    finally:
        engine.dispose()
    return 0


def _lookup(args: argparse.Namespace) -> int:
    engine = create_database_engine(args.db, must_exist=True)
    try:
        with Session(engine) as session:
            matches = lookup_forms(session, args.lemma, args.reading)
        if not matches:
            _print_json({"query": args.lemma, "matches": []})
            return 1
        _print_json({"query": args.lemma, "matches": matches})
    finally:
        engine.dispose()
    return 0


def _db_upgrade(args: argparse.Namespace) -> int:
    engine = create_database_engine(args.db, must_exist=True)
    try:
        upgrade_database(engine)
        print(current_revision(engine) or "")
    finally:
        engine.dispose()
    return 0


def _db_current(args: argparse.Namespace) -> int:
    engine = create_database_engine(args.db, must_exist=True)
    try:
        print(current_revision(engine) or "")
    finally:
        engine.dispose()
    return 0


def _enrich_furigana(args: argparse.Namespace) -> int:
    report = enrich_furigana(args.db, args.input)
    _print_json(report.__dict__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="japanese-learning")
    sub = parser.add_subparsers(dest="command", required=True)

    importer = sub.add_parser("import", help="import a 5mdld APKG or collection")
    source = importer.add_mutually_exclusive_group(required=True)
    source.add_argument("--apkg", type=Path)
    source.add_argument("--collection", type=Path)
    importer.add_argument("--output", type=Path, default=default_db_path())
    importer.add_argument("--model")
    importer.add_argument("--replace", action="store_true")
    importer.add_argument("--json", action="store_true")
    importer.set_defaults(func=_import)

    stats = sub.add_parser("stats", help="show database counts")
    stats.add_argument("--db", type=Path, default=default_db_path())
    stats.set_defaults(func=_stats)

    lookup = sub.add_parser("lookup", help="look up a lemma or form")
    lookup.add_argument("--db", type=Path, default=default_db_path())
    lookup.add_argument("--reading")
    lookup.add_argument("lemma")
    lookup.set_defaults(func=_lookup)

    database = sub.add_parser("db", help="manage database migrations")
    database_sub = database.add_subparsers(dest="db_command", required=True)
    db_upgrade = database_sub.add_parser("upgrade", help="upgrade to head")
    db_upgrade.add_argument("--db", type=Path, default=default_db_path())
    db_upgrade.set_defaults(func=_db_upgrade)
    db_current = database_sub.add_parser("current", help="show revision")
    db_current.add_argument("--db", type=Path, default=default_db_path())
    db_current.set_defaults(func=_db_current)

    furigana = sub.add_parser(
        "enrich-furigana",
        help="replace ruby data from a JmdictFurigana JSON release",
    )
    furigana.add_argument("--db", type=Path, default=default_db_path())
    furigana.add_argument("--input", type=Path, required=True)
    furigana.set_defaults(func=_enrich_furigana)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"japanese-learning: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
