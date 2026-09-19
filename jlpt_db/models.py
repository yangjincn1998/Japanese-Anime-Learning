"""JLPT 本地词库的 SQLAlchemy ORM 模型。

模型以 5mdld 为唯一事实来源。每条 word 对应一条 5mdld note，word_form
保存主形式和词形变体，dictionary_example 只保存词典例句。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enum_types import StrEnumListJSON, StrEnumType
from .enums import ExampleRelation, FrequencyClass, JlptLevel, PartOfSpeech


class Base(DeclarativeBase):
    pass


class SourceDeck(Base):
    """5mdld 来源卡组。

    Attributes:
        id: Anki deck ID。
        level: 卡组对应的 JLPT 等级。
        frequency_class: 卡组对应的频率分类；N5、N4 可为空。
    """

    __tablename__ = "source_deck"
    __table_args__ = ({"comment": "5mdld 来源卡组及其唯一的 JLPT 等级和频率分类。"},)

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        comment="5mdld 来源卡组 ID。",
    )
    level: Mapped[JlptLevel] = mapped_column(
        StrEnumType(JlptLevel),
        nullable=False,
        comment="卡组对应的 JLPT 等级枚举。",
    )
    frequency_class: Mapped[FrequencyClass | None] = mapped_column(
        StrEnumType(FrequencyClass),
        comment="卡组对应的频率分类枚举，N5、N4 可为空。",
    )

    words: Mapped[list[Word]] = relationship(back_populates="deck")


class Word(Base):
    """5mdld 单词词条。

    每条记录对应一条 5mdld source note。主形式通过 ``main_form_id`` 指向
    ``word_form``，其他词形通过 ``word_form.word_id`` 反向关联。

    Attributes:
        id: 单词内部自增主键。
        main_form_id: 主词形 ID。
        deck_id: 来源卡组 ID。
        pos_json: 词性枚举列表。
        meaning_zh_hans: 简体中文释义。
        meaning_zh_hant: 繁体中文释义。
        fields_json: 原始 5mdld 字段快照。
    """

    __tablename__ = "word"
    __table_args__ = ({"comment": "与 5mdld source note 一一对应的单词词条。"},)

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="单词内部自增主键。",
    )
    main_form_id: Mapped[int] = mapped_column(
        ForeignKey(
            "word_form.id",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
        comment="指向该单词主形式的词形 ID。",
    )
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("source_deck.id"),
        nullable=False,
        comment="该词条所属的 5mdld 来源卡组 ID。",
    )
    pos_json: Mapped[list[PartOfSpeech]] = mapped_column(
        StrEnumListJSON(PartOfSpeech),
        nullable=False,
        comment="词性枚举列表，数据库存为 JSON 字符串数组。",
    )
    meaning_zh_hans: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="简体中文释义。",
    )
    meaning_zh_hant: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="繁体中文释义。",
    )
    fields_json: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        comment="原始 5mdld 字段快照，JSON 对象。",
    )

    deck: Mapped[SourceDeck] = relationship(back_populates="words")
    main_form: Mapped[WordForm] = relationship(
        foreign_keys=[main_form_id],
        viewonly=True,
        lazy="joined",
    )
    forms: Mapped[list[WordForm]] = relationship(
        back_populates="word",
        foreign_keys="WordForm.word_id",
        cascade="all, delete-orphan",
    )
    dictionary_examples: Mapped[list[DictionaryExample]] = relationship(
        back_populates="word",
        cascade="all, delete-orphan",
    )


class WordForm(Base):
    """单词词形表。

    Attributes:
        id: 词形内部自增主键。
        word_id: 所属单词 ID。
        lemma: 规范化后的书写形式。
        reading: 规范化后的平假名读音，可保留长音符。
    """

    __tablename__ = "word_form"
    __table_args__ = (
        UniqueConstraint(
            "word_id",
            "lemma",
            "reading",
            name="uq_word_form_word_lemma_reading",
        ),
        Index("word_form_lookup", "lemma", "reading"),
        Index("word_form_reading", "reading"),
        {"comment": "单词的书写形式和对应平假名读音。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="词形内部自增主键。",
    )
    word_id: Mapped[int] = mapped_column(
        ForeignKey("word.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属单词 ID。",
    )
    lemma: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="规范化后的书写形式。",
    )
    reading: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="规范化后的平假名读音。",
    )

    word: Mapped[Word] = relationship(
        back_populates="forms",
        foreign_keys=[word_id],
    )
    ruby_segments: Mapped[list[WordFormRuby]] = relationship(
        back_populates="word_form",
        cascade="all, delete-orphan",
        order_by="WordFormRuby.position",
    )


class WordFormRuby(Base):
    """词形振假名分段表。

    Attributes:
        id: 振假名分段内部自增主键。
        word_form_id: 所属词形 ID。
        position: 在词形中的显示顺序。
        text: 原始文本片段。
        reading: 该片段的假名读音；纯假名片段可为空。
    """

    __tablename__ = "word_form_ruby"
    __table_args__ = (
        UniqueConstraint(
            "word_form_id",
            "position",
            name="uq_word_form_ruby_position",
        ),
        Index("word_form_ruby_form", "word_form_id"),
        {"comment": "来自 JmdictFurigana 的词形振假名分段。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="振假名分段内部自增主键。",
    )
    word_form_id: Mapped[int] = mapped_column(
        ForeignKey("word_form.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属词形 ID。",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="在词形中的显示顺序，从 0 开始。",
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="原始文本片段。",
    )
    reading: Mapped[str | None] = mapped_column(
        Text,
        comment="文本片段的假名读音；纯假名片段可为空。",
    )

    word_form: Mapped[WordForm] = relationship(back_populates="ruby_segments")


class DictionaryExample(Base):
    """词典例句表。

    Attributes:
        id: 例句内部自增主键。
        word_id: 所属单词 ID。
        sentence_ja: 日文例句。
        sentence_furigana: 带高亮标签的日文振假名文本。
        sentence_zh_hans: 简体中文翻译。
        sentence_zh_hant: 繁体中文翻译。
        audio_filename: 例句音频文件名。
        relation_type: 普通例句、关联词或反义词。
    """

    __tablename__ = "dictionary_example"
    __table_args__ = (
        Index("dictionary_example_word", "word_id"),
        {"comment": "来自 5mdld 词典内容的例句、翻译和音频引用。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="例句内部自增主键。",
    )
    word_id: Mapped[int] = mapped_column(
        ForeignKey("word.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属单词 ID。",
    )
    sentence_ja: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="日文例句。",
    )
    sentence_furigana: Mapped[str | None] = mapped_column(
        Text,
        comment="带高亮标签的日文振假名文本。",
    )
    sentence_zh_hans: Mapped[str | None] = mapped_column(
        Text,
        comment="简体中文翻译。",
    )
    sentence_zh_hant: Mapped[str | None] = mapped_column(
        Text,
        comment="繁体中文翻译。",
    )
    audio_filename: Mapped[str | None] = mapped_column(
        Text,
        comment="例句音频文件名。",
    )
    relation_type: Mapped[ExampleRelation] = mapped_column(
        StrEnumType(ExampleRelation),
        nullable=False,
        comment="例句关系枚举，数据库存为中文文本。",
    )

    word: Mapped[Word] = relationship(back_populates="dictionary_examples")


class SubtitleDirectory(Base):
    """本地字幕目录树的邻接表节点。

    每个节点只保存当前目录片段和父目录 ID；完整路径通过父链递归得到。

    Attributes:
        id: 字幕目录内部自增主键。
        parent_id: 父目录 ID；根目录为空。
        segment_name: 当前目录名称片段。
    """

    __tablename__ = "subtitle_directory"
    __table_args__ = (
        Index(
            "uq_subtitle_directory_sibling_name",
            "parent_id",
            "segment_name",
            unique=True,
            sqlite_where=text("parent_id IS NOT NULL"),
        ),
        Index(
            "uq_subtitle_directory_root_name",
            "segment_name",
            unique=True,
            sqlite_where=text("parent_id IS NULL"),
        ),
        {"comment": "本地字幕目录树的邻接表节点。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="字幕目录内部自增主键。",
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("subtitle_directory.id", ondelete="CASCADE"),
        comment="父目录 ID；根目录为空。",
    )
    segment_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="当前目录名称片段。",
    )

    parent: Mapped[SubtitleDirectory | None] = relationship(
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[list[SubtitleDirectory]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    files: Mapped[list[SubtitleFile]] = relationship(
        back_populates="directory",
        cascade="all, delete-orphan",
    )
    deck_binding: Mapped[SubtitleDirectoryDeck | None] = relationship(
        back_populates="directory",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SubtitleFile(Base):
    """字幕文件及其本地内容身份。

    Attributes:
        id: 字幕文件内部自增主键。
        directory_id: 所属字幕目录 ID。
        content_hash: 字幕文件内容哈希，用于识别文件变化，不用于去重。
        name: 字幕文件名称。
        path: 字幕文件的规范化绝对路径。
    """

    __tablename__ = "subtitle_file"
    __table_args__ = (
        UniqueConstraint(
            "directory_id",
            "name",
            name="uq_subtitle_file_directory_name",
        ),
        UniqueConstraint(
            "path",
            name="uq_subtitle_file_path",
        ),
        Index("subtitle_file_directory", "directory_id"),
        {"comment": "字幕目录中的本地字幕文件。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="字幕文件内部自增主键。",
    )
    directory_id: Mapped[int] = mapped_column(
        ForeignKey("subtitle_directory.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属字幕目录 ID。",
    )
    content_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="字幕文件内容哈希，用于识别文件变化，不用于去重。",
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="字幕文件名称。",
    )
    path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="字幕文件的规范化绝对路径。",
    )

    directory: Mapped[SubtitleDirectory] = relationship(
        back_populates="files",
    )
    entries: Mapped[list[SubtitleEntry]] = relationship(
        back_populates="subtitle_file",
        cascade="all, delete-orphan",
    )


class SubtitleEntry(Base):
    """字幕文件中的一条时间轴字幕。

    Attributes:
        id: 字幕条目内部自增主键。
        subtitle_file_id: 所属字幕文件 ID。
        number: 字幕文件中的条目编号。
        start_ms: 字幕开始时间，媒体相对毫秒。
        end_ms: 字幕结束时间，媒体相对毫秒。
        text_ja: 字幕中的日文文本。
        text_zh_hans: 字幕中的简体中文文本；没有翻译时为空。
    """

    __tablename__ = "subtitle_entry"
    __table_args__ = (
        UniqueConstraint(
            "subtitle_file_id",
            "number",
            name="uq_subtitle_entry_file_number",
        ),
        CheckConstraint("number >= 0", name="ck_subtitle_entry_number"),
        CheckConstraint("start_ms >= 0", name="ck_subtitle_entry_start_ms"),
        CheckConstraint("end_ms >= start_ms", name="ck_subtitle_entry_time_range"),
        Index("subtitle_entry_file", "subtitle_file_id", "number"),
        {"comment": "字幕文件中的一条时间轴字幕。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="字幕条目内部自增主键。",
    )
    subtitle_file_id: Mapped[int] = mapped_column(
        ForeignKey("subtitle_file.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属字幕文件 ID。",
    )
    number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="字幕文件中的条目编号。",
    )
    start_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="字幕开始时间，媒体相对毫秒。",
    )
    end_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="字幕结束时间，媒体相对毫秒。",
    )
    text_ja: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="字幕中的日文文本。",
    )
    text_zh_hans: Mapped[str | None] = mapped_column(
        Text,
        comment="字幕中的简体中文文本；没有翻译时为空。",
    )

    subtitle_file: Mapped[SubtitleFile] = relationship(
        back_populates="entries",
    )
    occurrences: Mapped[list[WordOccurrence]] = relationship(
        back_populates="subtitle_entry",
        cascade="all, delete-orphan",
    )


class WordOccurrence(Base):
    """一个词典词形在字幕条目中的一次具体出现。

    概念上它是字幕条目与词典词形之间的关系；因为具有自己的属性、候选键，
    并继续参与 Anki note 关联，所以在关系模型中重化为关联实体。

    Attributes:
        id: 词项出现内部自增主键。
        entry_id: 所属字幕条目 ID。
        word_form_id: 匹配到的词典词形 ID。
        matched_text: 在字幕日文文本中命中的实际文本。
        position: 同一个字幕条目内的出现位置标识。
    """

    __tablename__ = "word_occurrence"
    __table_args__ = (
        UniqueConstraint(
            "entry_id",
            "word_form_id",
            "position",
            name="uq_word_occurrence_entry_form_position",
        ),
        CheckConstraint("position >= 0", name="ck_word_occurrence_position"),
        Index("word_occurrence_entry", "entry_id"),
        Index("word_occurrence_form", "word_form_id"),
        {"comment": "字幕条目中已解析到词典词形的词项出现。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="词项出现内部自增主键。",
    )
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("subtitle_entry.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属字幕条目 ID。",
    )
    word_form_id: Mapped[int] = mapped_column(
        ForeignKey("word_form.id", ondelete="RESTRICT"),
        nullable=False,
        comment="匹配到的词典词形 ID。",
    )
    matched_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="在字幕日文文本中命中的实际文本。",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="同一个字幕条目内的出现位置标识。",
    )

    subtitle_entry: Mapped[SubtitleEntry] = relationship(
        back_populates="occurrences",
    )
    word_form: Mapped[WordForm] = relationship(
        foreign_keys=[word_form_id],
    )
    note_links: Mapped[list[AnkiNoteOccurrence]] = relationship(
        back_populates="occurrence",
        cascade="all, delete-orphan",
    )


class AnkiDeck(Base):
    """Anki deck 树的邻接表节点。

    Attributes:
        id: Anki deck 映射内部自增主键。
        parent_id: 父 deck ID；根 deck 为空。
        segment_name: 当前 deck 名称片段。
        external_deck_id: Anki 返回的远端 deck ID；尚未同步时为空。
        last_synced_at: 最后一次同步成功时间。
    """

    __tablename__ = "anki_deck"
    __table_args__ = (
        UniqueConstraint(
            "external_deck_id",
            name="uq_anki_deck_external_deck",
        ),
        Index(
            "uq_anki_deck_sibling_name",
            "parent_id",
            "segment_name",
            unique=True,
            sqlite_where=text("parent_id IS NOT NULL"),
        ),
        Index(
            "uq_anki_deck_root_name",
            "segment_name",
            unique=True,
            sqlite_where=text("parent_id IS NULL"),
        ),
        {"comment": "Anki deck 树的邻接表节点。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="Anki deck 映射内部自增主键。",
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("anki_deck.id", ondelete="CASCADE"),
        comment="父 deck ID；根 deck 为空。",
    )
    segment_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="当前 deck 名称片段。",
    )
    external_deck_id: Mapped[int | None] = mapped_column(
        BigInteger,
        comment="Anki 返回的远端 deck ID；尚未同步时为空。",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        comment="最后一次同步成功时间。",
    )

    parent: Mapped[AnkiDeck | None] = relationship(
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[list[AnkiDeck]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    directory_binding: Mapped[SubtitleDirectoryDeck | None] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SubtitleDirectoryDeck(Base):
    """字幕目录与 Anki deck 的一对一映射。

    映射只约束节点本身；父子关系同构约束由确定性核心校验。

    Attributes:
        directory_id: 字幕目录 ID。
        deck_id: Anki deck 映射 ID。
    """

    __tablename__ = "subtitle_directory_deck"
    __table_args__ = (
        UniqueConstraint(
            "deck_id",
            name="uq_subtitle_directory_deck_deck",
        ),
        {"comment": "字幕目录与 Anki deck 的一对一映射。"},
    )

    directory_id: Mapped[int] = mapped_column(
        ForeignKey("subtitle_directory.id", ondelete="CASCADE"),
        primary_key=True,
        comment="字幕目录 ID。",
    )
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("anki_deck.id", ondelete="CASCADE"),
        nullable=False,
        comment="Anki deck 映射 ID。",
    )

    directory: Mapped[SubtitleDirectory] = relationship(
        back_populates="deck_binding",
    )
    deck: Mapped[AnkiDeck] = relationship(
        back_populates="directory_binding",
    )


class AnkiNote(Base):
    """一个词典词条在一个根 deck 范围内对应的 Anki note。

    Attributes:
        id: Anki note 映射内部自增主键。
        word_id: 对应的词典词条 ID。
        collection_deck_id: 作为 collection 根节点的 Anki deck ID。
        deck_id: note 当前所在的 Anki deck ID。
        external_note_id: AnkiConnect 返回的远端 note ID；尚未同步时为空。
        anki_guid: Anki note 的真实 GUID；尚未取得时为空。
        external_card_id: Anki 返回的远端 card ID；尚未同步时为空。
        last_synced_at: 最后一次同步成功时间。
    """

    __tablename__ = "anki_note"
    __table_args__ = (
        UniqueConstraint(
            "word_id",
            "collection_deck_id",
            name="uq_anki_note_word_collection_deck",
        ),
        UniqueConstraint(
            "anki_guid",
            name="uq_anki_note_anki_guid",
        ),
        UniqueConstraint(
            "external_note_id",
            name="uq_anki_note_external_note",
        ),
        UniqueConstraint(
            "external_card_id",
            name="uq_anki_note_external_card",
        ),
        Index("anki_note_deck", "deck_id"),
        Index("anki_note_collection_deck", "collection_deck_id"),
        Index("anki_note_word", "word_id"),
        {"comment": "词典词条在某个根 deck 范围内的稳定 note 映射。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="Anki note 映射内部自增主键。",
    )
    word_id: Mapped[int] = mapped_column(
        ForeignKey("word.id", ondelete="RESTRICT"),
        nullable=False,
        comment="对应的词典词条 ID。",
    )
    collection_deck_id: Mapped[int] = mapped_column(
        ForeignKey("anki_deck.id", ondelete="RESTRICT"),
        nullable=False,
        comment="作为 collection 根节点的 Anki deck ID。",
    )
    deck_id: Mapped[int] = mapped_column(
        ForeignKey("anki_deck.id", ondelete="RESTRICT"),
        nullable=False,
        comment="note 当前所在的 Anki deck ID。",
    )
    external_note_id: Mapped[int | None] = mapped_column(
        BigInteger,
        comment="AnkiConnect 返回的远端 note ID；尚未同步时为空。",
    )
    anki_guid: Mapped[str | None] = mapped_column(
        Text,
        comment="Anki note 的真实 GUID；尚未取得时为空。",
    )
    external_card_id: Mapped[int | None] = mapped_column(
        BigInteger,
        comment="Anki 返回的远端 card ID；尚未同步时为空。",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        comment="最后一次同步成功时间。",
    )

    collection_deck: Mapped[AnkiDeck] = relationship(
        foreign_keys=[collection_deck_id],
    )
    deck: Mapped[AnkiDeck] = relationship(
        foreign_keys=[deck_id],
    )
    word: Mapped[Word] = relationship(
        foreign_keys=[word_id],
    )
    occurrence_links: Mapped[list[AnkiNoteOccurrence]] = relationship(
        back_populates="anki_note",
        cascade="all, delete-orphan",
    )


class AnkiNoteOccurrence(Base):
    """Anki note 与字幕词项出现之间的关联实体。

    Attributes:
        id: note 词项关联内部自增主键。
        anki_note_id: 所属 Anki note 映射 ID。
        occurrence_id: 已追加到该 note 的字幕词项出现 ID。
    """

    __tablename__ = "anki_note_occurrence"
    __table_args__ = (
        UniqueConstraint(
            "anki_note_id",
            "occurrence_id",
            name="uq_anki_note_occurrence_note_occurrence",
        ),
        Index("anki_note_occurrence_note", "anki_note_id"),
        Index("anki_note_occurrence_occurrence", "occurrence_id"),
        {"comment": "Anki note 已引用的字幕词项出现证据。"},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="note 词项关联内部自增主键。",
    )
    anki_note_id: Mapped[int] = mapped_column(
        ForeignKey("anki_note.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属 Anki note 映射 ID。",
    )
    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("word_occurrence.id", ondelete="CASCADE"),
        nullable=False,
        comment="已追加到该 note 的字幕词项出现 ID。",
    )

    anki_note: Mapped[AnkiNote] = relationship(
        back_populates="occurrence_links",
    )
    occurrence: Mapped[WordOccurrence] = relationship(
        back_populates="note_links",
    )
