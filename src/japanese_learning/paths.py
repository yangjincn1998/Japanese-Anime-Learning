from __future__ import annotations

from pathlib import Path


def default_db_path() -> Path:
    return Path.home() / ".jlpt-study" / "jlpt_library.sqlite"
