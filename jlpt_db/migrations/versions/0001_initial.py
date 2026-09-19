"""Initial JLPT database schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-19
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_deck",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("frequency_class", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        comment="5mdld 来源卡组及其唯一的 JLPT 等级和频率分类。",
    )
    op.create_table(
        "word",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("main_form_id", sa.Integer(), nullable=False),
        sa.Column("deck_id", sa.BigInteger(), nullable=False),
        sa.Column("pos_json", sa.JSON(), nullable=False),
        sa.Column("meaning_zh_hans", sa.Text(), nullable=False),
        sa.Column("meaning_zh_hant", sa.Text(), nullable=False),
        sa.Column("fields_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["main_form_id"],
            ["word_form.id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(["deck_id"], ["source_deck.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="与 5mdld source note 一一对应的单词词条。",
    )
    op.create_table(
        "word_form",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("lemma", sa.Text(), nullable=False),
        sa.Column("reading", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["word.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "word_id",
            "lemma",
            "reading",
            name="uq_word_form_word_lemma_reading",
        ),
        comment="单词的书写形式和对应平假名读音。",
    )
    op.create_index("word_form_lookup", "word_form", ["lemma", "reading"])
    op.create_index("word_form_reading", "word_form", ["reading"])
    op.create_table(
        "word_form_ruby",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_form_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("reading", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["word_form_id"],
            ["word_form.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "word_form_id",
            "position",
            name="uq_word_form_ruby_position",
        ),
        comment="来自 JmdictFurigana 的词形振假名分段。",
    )
    op.create_index("word_form_ruby_form", "word_form_ruby", ["word_form_id"])
    op.create_table(
        "dictionary_example",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("sentence_ja", sa.Text(), nullable=False),
        sa.Column("sentence_furigana", sa.Text(), nullable=True),
        sa.Column("sentence_zh_hans", sa.Text(), nullable=True),
        sa.Column("sentence_zh_hant", sa.Text(), nullable=True),
        sa.Column("audio_filename", sa.Text(), nullable=True),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["word_id"], ["word.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="来自 5mdld 词典内容的例句、翻译和音频引用。",
    )
    op.create_index(
        "dictionary_example_word",
        "dictionary_example",
        ["word_id"],
    )


def downgrade() -> None:
    op.drop_index("dictionary_example_word", table_name="dictionary_example")
    op.drop_table("dictionary_example")
    op.drop_index("word_form_ruby_form", table_name="word_form_ruby")
    op.drop_table("word_form_ruby")
    op.drop_index("word_form_reading", table_name="word_form")
    op.drop_index("word_form_lookup", table_name="word_form")
    op.drop_table("word_form")
    op.drop_table("word")
    op.drop_table("source_deck")
