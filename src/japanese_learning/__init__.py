"""Local Japanese learning database and subtitle analysis core."""

from .enums import (
    ExampleRelation,
    FrequencyClass,
    JlptLevel,
    PartOfSpeech,
)
from .furigana import FuriganaReport, enrich_furigana
from .importer import ImportReport, import_collection
from .paths import default_db_path

__all__ = [
    "ExampleRelation",
    "FrequencyClass",
    "FuriganaReport",
    "ImportReport",
    "JlptLevel",
    "PartOfSpeech",
    "default_db_path",
    "enrich_furigana",
    "import_collection",
]
__version__ = "0.1.0"
