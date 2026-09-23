# Anki 日语学习 MVP 开发背景

## 目标

本项目是一个仅供个人使用的日语学习辅助工具。它不是通用词典，也不是
面向多用户的学习平台。当前目标是用本地动画、字幕、5mdld 词库和 Anki，
建立一个可靠、可重复、低人工维护的日语学习闭环。

学习方法采用 N+1 / i+1 comprehensible input 思路：

- 一个例句主要引入一个当前值得学习的新词或语法。
- 优先使用用户实际观看内容中的原句和原声。
- 卡片可以持续追加后续出现的新例句，但保持稳定身份。
- 不追求区分所有义项，也不追求第一版覆盖所有语言学习场景。

## 两个闭环

### 预习闭环

目标是在观看一集内容之前，生成适度的预习卡片。

```text
现成字幕文件
  -> 标准化为 TSV
  -> Agent 询问用户目标、等级和每集卡片预算
  -> Agent 根据字幕上下文选择词汇、语法和时间戳
  -> 可并行拆分给多个子 Agent
  -> 标准化输出 JSONL/TSV
  -> 确定性归一化与去重
  -> 查询本地词典与已有卡片状态
  -> 生成原始音频和 TTS 资源
  -> 构建 APKG
```

预习闭环的输入是完整字幕，但 Agent 不应该直接处理未经清洗的整份 ASS：

- 字幕解析和来源配对属于 `subtitle-acquisition`。
- 歌词、片头片尾、字幕组说明、屏幕字和注释必须先过滤。
- Agent 只处理规范化的对白和有限上下文窗口。

### 复习闭环

目标是在观看过程中或观看后，根据用户自己的感受补充卡片。

```text
用户观看动画
  -> 标记“没听懂、重要、有趣、值得记”等感受和时间点
  -> Agent 读取标记和对应字幕上下文
  -> Agent 生成候选词汇、语法和时间戳
  -> 本地标准化与第一次去重
  -> 拉取现有 Anki 卡片状态
  -> 第二次去重与 create/update/append/skip 决策
  -> 生成缺失的媒体和 TTS 资源
  -> 构建或更新卡片
  -> 按用户命令同步 Anki
```

复习闭环强调用户感受，而不是单纯词频。一个用户主动标记的片段，即使词频
不高，也可能比高频但已掌握的词更值得制卡。

## 共同确定性核心

两个闭环只在“输入和用户意图”上不同，后半段必须共用同一套契约和实现：

```text
SelectionRecord
  -> normalize
  -> resolve against local dictionary
  -> deduplicate
  -> reconcile with Anki
  -> build assets
  -> CardDraft
  -> APKG / AnkiConnect
```

### Agent 负责

- 理解用户目标、等级和反馈。
- 从有限上下文中选择学习价值更高的词或语法。
- 判断具体语境中的语义、用法和语域。
- 对有限候选做消歧。
- 必要时向用户追问。

### 确定性程序负责

- SRT/ASS/TSV/JSONL 解析和校验。
- Unicode、假名、读音、lemma 和振假名规范化。
- 词典查询、候选去重和 occurrence 维护。
- 时间戳和媒体文件校验。
- 音频切片、TTS 缓存和媒体生成。
- 稳定 card identity、GUID 和 CardDraft。
- APKG 渲染、Anki 状态读取、对账和同步。

LLM 不得直接写 SQLite、APKG 或 Anki 数据库。Agent 的职责是生成和消费
标准数据，不是绕过确定性核心。

## 本地词典

本地词典只以 5mdld 为词条事实来源。

当前表结构：

```text
source_deck
  id
  level
  frequency_class

word
  id
  main_form_id
  deck_id
  pos_json
  meaning_zh_hans
  meaning_zh_hant
  fields_json

word_form
  id
  word_id
  lemma
  reading

word_form_ruby
  id
  word_form_id
  position
  text
  reading

dictionary_example
  id
  word_id
  sentence_ja
  sentence_furigana
  sentence_zh_hans
  sentence_zh_hant
  audio_filename
  relation_type
```

约束和原则：

- 一条 5mdld note 对应一个 `word`。
- `main_form_id` 是 word 的主形式属性。
- `word_form` 保存该 word 的全部书写形式和假名读音。
- `(lemma, reading)` 是查询键，不是全局唯一键。
- `dictionary_example` 只保存词典来源的例句。
- `word_form_ruby` 来自 JmdictFurigana，只负责显示层振假名。
- JmdictFurigana 不参与 word identity，也不引入新的词条来源。
- 动画例句以后单独建模，不混入 `dictionary_example`。

## 组件边界

### Skills

- `subtitle-to-anki`：预习闭环的 Agent 入口。
- `capture-to-anki`：复习闭环的 Agent 入口。
- `mediacap`：中立地记录媒体时间点、上下文和用户评论。

Skill 是 Agent 交互和工作流入口，不承载数据库、APKG 和同步实现。

### Packages

- `japanese-learning`：本地词典、字幕、occurrence 和 Anki 映射。
- `av-subtitles`：字幕生成和确定性媒体处理。
- `anki-bridge`：CardDraft 与 Anki/AnkiConnect 对账组件。

`anki-bridge` 首先是 package/component，不是用户直接调用的 Skill。只有当
用户明确要求“同步 Anki”时，Agent 才通过一个很薄的入口调用它。

### External

- Anki：卡片存在性和调度状态的最终事实来源。
- AnkiConnect：本地同步接口。
- 5mdld：本地词典唯一事实来源。
- JmdictFurigana：可选振假名显示增强。

## 当前范围

```text
包含：
  5mdld 本地词库
  字幕标准化
  预习选词
  观看感受驱动的复习选词
  本地去重
  Anki 状态对账
  TTS 和原始音频
  APKG 构建
  AnkiConnect 同步

暂不包含：
  义项拆分
  多词典词条合并
  JmdictFurigana 之外的 JMdict 语义导入
  动画例句表
  商业化
  多用户
  LLM API 自动配置产品
```

当前入口可以是 Agent 和 Skill。以后如果制作独立应用，应用只替换入口和
LLM 调用方式，确定性核心与数据契约保持不变。

## 开发阶段

1. 完成并稳定 `japanese-learning`。
2. 定义规范化的字幕输入契约。
3. 跑通预习闭环。
4. 跑通基于观看感受的复习闭环。
5. 实现 Anki 状态对账和稳定 CardDraft。
6. 将重复流程提取为可复用 package。
7. 最后再决定独立产品入口和 LLM API 配置体验。

## MVP 验收标准

- 相同输入重复构建不会产生重复卡片。
- 每个字形都能追溯到本地词典中的 word/form。
- 预习卡片来自实际字幕时间戳和媒体片段。
- 复习卡片来自用户标记的观看感受和上下文。
- 词典例句与未来的动画例句可以明确区分。
- 输出 JSONL 可审计，APKG 可重建，Anki 状态可对账。
- 所有确定性步骤都有测试，不依赖 Agent 临时记忆。
