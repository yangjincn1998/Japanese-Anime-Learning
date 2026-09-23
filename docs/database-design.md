# Database Design

The database is managed with SQLAlchemy 2.0 and Alembic.

## Migration Rules

- Use Alembic-generated revision IDs and filenames.
- Do not manually renumber revisions.
- Implement both `upgrade()` and `downgrade()`.
- Verify `upgrade -> downgrade -> upgrade` against a temporary database.
- Run `alembic check` before committing.

## Learning Schema

`analysis_request` represents one submitted analysis action. A request analyzes
one or more directories through `analyzes`, and exactly one directory is its
root.

`subtitle_directory` is the local directory entity. Its normalized path is
unique, while parent relationships form the directory tree.

`deck`, `root_deck`, and `normal_deck` implement the Anki deck hierarchy:

- `deck` is the common superclass.
- `root_deck` maps a directory to an Anki root deck.
- `normal_deck` maps a non-root directory to an ordinary Anki deck.

One word has at most one Anki note in a root deck:

```text
(word_id, collection_root_deck_id) -> anki_note
```

One note can reference many subtitle occurrences through
`anki_note_occurrence`.

Model outputs are not cached in this database. Batch objects are runtime
artifacts, not persistent relations.
