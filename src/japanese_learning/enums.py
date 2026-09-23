from __future__ import annotations

from enum import StrEnum


class JlptLevel(StrEnum):
    """JLPT 等级。"""

    N5 = "N5"
    N4 = "N4"
    N3 = "N3"
    N2 = "N2"
    N1 = "N1"


class FrequencyClass(StrEnum):
    """5mdld 的真题出现频率分类。"""

    HIGH = "高频"
    MEDIUM = "中频"
    LOW = "低频"


class PartOfSpeech(StrEnum):
    """按学校文法术语命名的词性分类。"""

    NOUN = "名词"
    PRONOUN = "代词"
    NA_ADJECTIVE = "形容动词"
    I_ADJECTIVE = "形容词"
    TARU_ADJECTIVE = "トタル型形容动词"
    ADVERB = "副词"
    PREFIX = "接头词"
    SUFFIX = "接尾词"
    CONJUNCTION = "接续词"
    ATTRIBUTIVE = "连体词"
    INTERJECTION = "感叹词"
    PHRASE = "词组"
    IDIOM = "惯用语"
    WORD_FORMING = "构词成分"
    VERB_V1 = "五段动词"
    TRANSITIVE_V1 = "他动词（五段）"
    INTRANSITIVE_V1 = "自动词（五段）"
    TRANSITIVE_INTRANSITIVE_V1 = "自他动词（五段）"
    TRANSITIVE_V2 = "他动词（一段）"
    INTRANSITIVE_V2 = "自动词（一段）"
    TRANSITIVE_INTRANSITIVE_V2 = "自他动词（一段）"
    TRANSITIVE_V3 = "他动词（不规则）"
    INTRANSITIVE_V3 = "自动词（不规则）"
    TRANSITIVE_INTRANSITIVE_V3 = "自他动词（不规则）"
    AUXILIARY_VERB = "补助动词"
    AUXILIARY_ADJECTIVE = "补助形容词"
    ADVERBIAL_PARTICLE = "副助词"
    CONJUNCTIVE_PARTICLE = "接续助词"
    CASE_PARTICLE = "格助词"
    FINAL_PARTICLE = "终助词"


class ExampleRelation(StrEnum):
    """例句与目标词之间的关系。"""

    EXAMPLE = "普通例句"
    RELATED = "关联词"
    ANTONYM = "反义词"
