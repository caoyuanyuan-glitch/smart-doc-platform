# Word to DITA Conversion Rules

适用范围：当前项目的 Word/WPS 转 DITA 批量转换、InDesign（IDML）转 DITA 批量转换，以及原生 Markdown（`.md` / `.markdown`）转 DITA。Note、列表、表格、图片与验收规则共用；源格式差异写在各自的解析章节。

## 目标

- 输出结构以源 Word 为准。
- 文本内容保持原文语义与顺序。
- 仅在 IME/DITA 平台需要的地方做结构适配。

## 模板复用规则

- `Cover` topic 直接复用参考 DITA zip 包中的原始 topic。
- 复用模板封面 topic 时，源 Word 的封面不再单独生成 topic，也不在 ditamap 中重复挂载。
- 源 Word 的 `Version History` / `版本记录` 正文（含修订表）必须写进该 topic；复用模板封面时不得把这份内容带进 Cover 后丢掉。
- 验收时源 Word 的封面标题与封面正文不计入标题结构和内容完整性比对范围。
- `booklists/toc` 继续复用参考 DITA zip 包。
- `Manufacturer information` 按源 Word 生成，不复用模板 appendix 内容。
- `<frontmatter>` 内顺序为：封面（Cover）、`关于说明书`、`版本记录`；`关于说明书`、`版本记录` 与封面平级，排在封面之后，不嵌套在封面下。
- `制造商信息` 不是固定前部 topic，按源文档框架放置：IDML 中 `Title-Appen. n` 样式输出为正文之后的 `<appendix>`；Word 中按源章节位置生成。

 - 参考包若是快速操作指南（frontmatter 只有封面 topic，没有关于说明书和 toc），输出包跟随参考包：封面 topic 复用参考包结构，不生成关于说明书，不挂 booklists/toc。源 MD 标题前的适用平台并入第一章正文；文档日期写入封面「修订日期」，不再并入第一章。用户已填的封面字段（手册名称、编号、修订日期、版本）按该封面输出。

- 英文输出的章节、topic 标题使用 sentence style：首字母大写，其余小写；ZARC、FASTQ、GZIP、CLI 等专有名词和缩写保留。封面标题与书名不改。
- 快速操作指南英文包的命令速查表输出为 `<chapter>`，下挂 chapterTopic，不用 `<appendix>`。

## Word 预处理规则

- `.wps` 如本质为 OOXML 压缩包，可按 `.docx` 链路直接处理。
- Word 自带目录块不进入 DITA 正文。
- 纯页码段落不进入 DITA 正文。
- Word 里因排版产生的句内断行需要自动合并，避免一句话被切成多段。

## 标题与结构规则

- DITA 层级按源 Word 标题层级建树，章节结构需要与 Word 层级 100% 一致。
- 源 Word 里仅作分组、没有正文的 `Appendix` / `附录` 父标题不生成 topic，也不进入 ditamap。
- 其下每个附录提升为独立 `<appendix>`：容器 `navtitle` 为附录名，先挂同名 `chapterTopic`，再挂该附录的子 topic；叶子附录的正文写在该 `chapterTopic` 中。
- `Revision history` 视为真实章节。
 - `Version History` 与 `Revision history` 同义，视为真实章节，挂在 `<frontmatter>` 中与 Cover、关于说明书平级；不得随复用封面一起丢弃。
- `Contents` 视为目录，不视为正文章节。
- `Formula N ...` 和包含等式的公式行保留在正文中，不拆成 topic。
- `Cover` 正文里的产品编号、版本号等短行优先留在封面正文，不单独生成 topic。
- 标题不保留手工编号：`第一章`、`2.1`、`3.1.1`、`附录A`、`B-1` 等前缀在转换时去掉，编号由 IME 样式自动生成。
- 去掉编号时不能误伤正文数字：`3'RNA`、`1.13×`、`2.0 mL` 这类以数字开头的内容保持原样。
- 只有 Word 标题样式（以及既有的短标题、括号标题启发式）才生成 topic，以下内容保留为父 topic 正文：
  - 紧跟表格的整行加粗标签，例如 `常温试剂`、`低温试剂`、`试剂槽试剂`、`细胞相（1.13×）`。
  - 英文同类表格分组标签同样保留为正文，例如 `Cell phase (1.13×)`、`Magnetic bead phase (1.13×)`。
  - 产品套装型号行，例如 `MGISEQ-2000RS 高通量测序试剂套装(FCL PE100) (Cat. No. 1000012554)`。
- 带 Word 编号的短段落，例如 `cDNA产物扩增循环数参考`；它属于编号列表项，不是章节标题。

## IME 主题类型

- 封面使用 `sCoverTopic`。
- 章容器下挂的章级 topic 使用 `chapterTopic`。
- 其余所有生成 topic 一律使用 IME 主题类型 `sDitaTopic`（根元素 `<topic>` / `<body>`）和编号前缀 `DTO`，包括原按标题关键词判为 concept / task / reference 的小节。
- IME 按编号前缀显示类型：`DTO` 为「主题 Topic」，`DTC` 为「主题 Concept」。正文小节不得再生成 `DTC` 或 `sDitaConcept`。
 - XML 已是 `sDitaTopic` 但文件名 / `cms:number` 仍为 `DTC` 时，IME 仍显示「主题 Concept」，必须把 IME 编号前缀改成 `DTO`。
 - 改写已有 IME 导出包时，下列位置必须一起改前缀与模板：`.dita` 文件名、`cms:number`、ditamap 的 `href` / `keys` / `cms:template` / `cms:imesofttype`、正文 `<xref>` 的 `href` / `keyref`、`jsonData.json`（`code`、`fileName`、`softType`、`iba_keys`）、`infotree.xml` 及其 `out/` 副本。只改 `.dita` 时 IME 仍按 jsonData / infotree 的旧前缀显示类型。
 - 占位编号（如 `cms:keys="DTC041001"`、`cms:placeHolder`）可保留；已分配的 IME 编号（如 `DTC048831`）改为 `DTO048831`。
 - 封面与章级保持 `sCoverTopic` / `chapterTopic`，不改成 Topic。
 - 编号前缀从 `DTC` 改为 `DTO` 后，IME 按原编号匹配不到节点，导入时选新增。

## 列表规则

- 有序步骤列表转换为 `ol` 时保持连续。
- 编号列表项即使很短且没有标点，也要保留列表编号，不能因为"短文本"被降级为普通段落。
- 步骤下的图片、表格、note 挂到对应步骤项下。
- 图片、表格、note 不打断同一个 `ol`。
- 步骤之间穿插的 note 必须挂到它所属的那个步骤项内，不能把整个 `ol` 吞进 note。
- 只有标签的 note（如单独一行 `注意：`）例外，它继续包裹其后的列表作为 note 正文。
- Word 操作步骤中的加粗强调文本需要保留并转换为 `b` 标签。
- IDML 的 `Bulleted list`/`Numbered list` 列表项即使正文字面命中 note 关键词（如 `警告`、`注意`、`切勿`），也必须保留为普通列表项：IDML 的警告/注意以提示框表格表达，列表项不得被提升为 note 并折叠进上一条。
- 一个 IDML 列表段落里的每一项（含 `<Br/>` 分隔出的步骤）必须各自成项，不得把多项合并进同一个 `<li>`。

- `ul` / `ol` 的每个条目文本都包在 `<p>` 里：`<li><p>…</p></li>`。嵌套列表、note、图片、续段仍挂在该 `<li>` 内、条目 `<p>` 之后。
 - 原生 Markdown 中，列表项后缩进的续段仍挂在该 `<li>` 内；空行之后未缩进的独立段落结束当前列表，不得挂到上一项。Word/IDML 的列表续段策略不变。

### UI 控件（`uicontrol`）

- 凡源文件中出现在界面上的文本都归入 `uicontrol`，既包含按钮、字段、页签等短控件名（`【登录】`、`【测序类型】`、`【确定】`），也包含对话框里的整句提示（如 `【请确认是否退出测序？已装载的耗材不可复用】`）。
- 中文源用 `【】` 包裹屏上文本；输出为独立的 `<uicontrol>文本</uicontrol>`，只取括号内文本（`【】` 由 IME 自动渲染）。
- 英文源的屏上控件用 `Silk screen` 字符样式标记（该样式自带加粗外观），等价于中文的 `【】`；同样输出 `<uicontrol>`。加粗的英文操作步骤文本也按屏上控件处理。
 - 英文 Word 源若用方括号包裹屏上文本（如 `[DNBelabC-YellowR16]`、`[Login]`），同样输出 `<uicontrol>`；纯数字方括号（`[1]`、`[12]`）不是控件名。
- `【N】`（数字起首）是 note 的条目序号，不是控件名，保持原样交由 note 条目合并逻辑处理。
 - 英文 Word 的 `[N]`（如 `[1]`、`[12]`）与中文 `【N】` 同类，是 note 条目序号，不是控件名。
- `uicontrol` 去首尾空白；纯空格的对屏文本段保留为普通空格，不生成空控件。

## Note 规则

### Note 类型判定（统一口径）

- 警告类内容输出 `type="warning"`：文本标签 `警告`、`小心`、`请勿`、`切勿`，以及英文 `Warning`、`Danger`。
- 注意类内容输出 `type="caution"`：文本标签 `注意`，以及 `Caution`。
- 提示类内容输出 `type="tip"`：文本标签 `提示`、`Tips`，英文 Word 的 `Note:`，以及无法判定为警告或注意的内容。
- 未指定类型的普通 note 默认 `type="tip"`。
- 上面三条对「文本标签类」note 生效；IDML 提示框则以图标判定类型（见下），不按正文文字改类型。

### 文本标签

- 中文 note 识别标签词：`注意事项`、`其他注意事项`、`注意`、`提示`、`警告`、`小心`。
- 英文 note 识别标签词：`Warning`、`Caution`、`Tips`、`Danger`、`StopPoint`、`Stop point`。
 - 英文 Word 另识别 `Note:`，按提示类输出 `type="tip"`。
- 英文普通 `Do not ...` 句子保持正文段落。
- note 图标图片不输出到最终 DITA。
- 标签词被加粗包裹（如 `[[B]]注意：[[/B]]正文`）时仍按 note 处理，标签词丢弃。
- 标签词前若有多余的加粗空格（如 `[[B]] [[/B]][[B]]注意：[[/B]]正文`，Word 排版残留），仍按 note 处理；markdown 生成阶段也不再为纯空白加粗 run 添加 `[[B]]`/`[[/B]]`。
- 整行加粗时保留正文加粗（如 `[[B]]注意：请先进行样本加载[[/B]]` 输出 `<note><p><b>请先进行样本加载</b></p></note>`）。
- 只有标签的 note（如单独一行 `注意：`）吸收其后连续的 `【N】` 条目，合并为同一个 note。
- note 内的 `【N】` 条目合并为同一个 `ul`，每项转为 `li`。
 - 英文 `Note:` 同样吸收其后连续的 `[N]` 条目（含 `Note: [1] ...` 写在同一行、`[2]` 另起一行的写法），合并为同一个 note 内的 `ul`/`li`。
- note 内每个句段各自一个 `<p>`；note 内 `ul` / `ol` 的每个条目同样写成 `<li><p>…</p></li>`。
- IDML 提示框正文若采用 `Warning sentence list` 等“句子列表”样式，段落内由 `<Br/>` 分隔的每句话各成一个列表项，整体输出为 note 内的 `<ul><li><p>…</p></li></ul>`；普通提示框正文仍按 `<p>` 输出。

### IDML 提示框（callout box）

- IDML 中警告、注意、提示以“提示框”形式出现。真实版式常见为 **两列表格**：第 0 列只放符号图标（`ParagraphStyle` 常为 `Text:Symbols-*`，格内无正文），第 1 列放正文（`ParagraphStyle` 常为 `Table:Warning sentence-*`、`Table:Single sentence-*`）。也有退化为单列或 1×1 的形态。判定口径：表格 `HeaderRowCount=0` 且列数 ≤2、首列单元格在各行都没有正文文本（只含图标/符号样式）时，视为提示框。
- 这类表格必须输出为 `<note>`，不能输出为无标题表格。
- note 类型由符号图标文件名判定：
  - 图标名含 `Warning`、`Danger`、`warn` → `type="warning"`。
  - 图标名含 `Caution` → `type="caution"`。
  - 图标名含 `Tips`、`icon_note`，或无图标 → `type="tip"`。
- 提示框内多段正文合并为同一个 note，每段一个 `<p>`；图标列不输出。
- 相邻的两个提示框必须各自成独立 `<note>`，不能合并为一张多行表格；表格之间的空行即结束当前表格。
- 提示框类型只看图标/样式，正文文字不改类型；即图标为 `Tips` 时，即使正文含 `切勿`，仍为 `type="tip"`（与参考包保持一致）。
- 提示框位于步骤列表内时，note 挂到所属 `<li>` 内，不打断 `ol` 编号；位于列表末尾的提示框挂到最后一个 `<li>`。

## IDML 源解析规则

- IDML 段落样式映射到标题层级：`Title-L<n>`（可带 `For reagent kit only:`、`Operation guide:` 等前缀）为第 n 级标题；`Title in first page`、`Title-Appen` 视为一级标题。
- 目录样式（`Contents :*`、`TOC*`）丢弃，目录由 IME 重新生成。
- 页眉页脚、空白页标记、`$ID/NormalParagraphStyle` 等无正文内容的 story 整体丢弃。
- 表格使用 `<Table>` 直接子节点 `<Cell Name="col:row">` 定位（**第一段是列、第二段是行**，与 `ColumnCount`/`RowCount` 及真实文档一致），不用嵌套的 Row→Cell 结构。曾误按 `row:col` 解析，会把整张表转置，必须避免。
- 表格合并单元格：单元格 `ColumnSpan>1` / `RowSpan>1` 时，markdown 阶段保留 `[[SPAN:colspan,rowspan]]` 标记，被覆盖格输出 `[[SPANC]]`；DITA 阶段还原为 `namest`/`nameend`（列合并）与 `morerows="rowspan-1"`（行合并）。含合并单元格的 IDML 表格不再套用 Word 的“删除重复首行/合并首列”启发式。
- 表题：IDML 用 `Table-title` 样式（经 `[[TABCAP]]` 标记传递），DITA 阶段提升为 `<table><title>表题</title>`，由 IME 重新编号。
- 表头行数由 `HeaderRowCount` 决定：解析阶段输出 `[[THEAD:n]]` 标记，DITA 阶段把前 n 行全部放入同一个 `<thead>`。两行表头必须保留两行，不能只取第一行或把第二行降到 `<tbody>`。
- 表格单元格内的图标（如 `icon_emergencystop.ai` 状态图标）必须保留为该 `<entry>` 内的 `<image>`，不得因为单元格没有正文而丢弃；单元格文字与嵌套表格正文只输出一次。
- 段落内可锚定提示框表格（`ParagraphStyleRange → CharacterStyleRange → Table`）：必须先输出段落自身文字，再输出锚定表格，不能因嵌套表格跳过段落正文。
 - 图片由外部链接引用（`Link` 元素），常见 `.ai`/`.png`；同名 `.svg` 视为其可用的替代资源。源 zip 含 `.idml` 与同级 `Links/`，`Links/` 放与链接主干同名的 `.svg`（`.ai` 按同名 `.svg` 替换）。无对应资源的链接不输出图片。
 - 无原生 InDesign `Links/` 时，可用 IME 导出包 `image/` 中的 SVG：去掉文件名 `G\d+_` 前缀，按主干（大小写不敏感）对齐 IDML `Link` 主干，写入源 zip 的 `Links/{主干}.svg`。note 图标（`icon_note`、`Warning` 等）仍不输出。
- 链接 URI 必须先做百分号解码（`urllib.parse.unquote`）再匹配资源；InDesign 会把名称中的空格与中文编码成 `%20`/`%xx`，不解码会导致这些图片全部漏配。
- 图题段落以 `Figure-title` 样式标识（如 `For reagent kit only:Figure-title-CN/-EN`），转换时打上 `[[FIGCAP]]` 标记，供 DITA 层包装为图。
- IDML 有序/无序列表的 `<Br/>` 是**步骤分隔符**：同一个 `Numbered list`/`Bulleted list` 段落里由 `<Br/>` 分开的多段文本代表多个步骤，必须各自输出为独立的 `1. `/`- ` 列表项，不能拼成一行。步骤之间内嵌的图标 `<Link>` 属于当前步骤，不拆分该步骤。
- 步骤列表内穿插的提示框表格、图片按其在段落中的顺序输出到所属步骤项，保证 `ol` 编号连续（`准备DNB制备混合液`、`回顾参数`、`DNB浓度不合格` 等步骤数须与源一致）。
- 源文档的列表层级（`Level n` 样式）必须保留：解析阶段在列表项行首输出 `[[LVL:n]]` 标记，DITA 阶段按层级构建嵌套 `<ul>`/`<ol>`。例如步骤下的 `Level 3` 项目符号成为该 `<li>` 内的 `<ul>`，其下 `Level 4` 编号项成为嵌套的 `<ol>`；不得把子列表压平到父级。
 - 列表项之后的说明段落、公式图必须挂在所属 `<li>` 内，并保持源文档顺序：出现在嵌套子列表之前的 `<p>`/note/图紧跟步骤正文；出现在嵌套子列表之后的说明挂在子列表后面。这些内容不能冲出整个 `<ul>` 变成兄弟节点。
- 列表层级标记不得影响章节类型判定：行首带 `[[LVL:n]]` 的编号步骤仍须识别为任务（DTO）。
- 步骤内联按钮图标必须留在它所属的步骤项内：出现在列表项文本之后的 `<Link>` 图标挂到该 `<li>`；出现在最后一个步骤之后的图标，也要在 `</ol>` 关闭前挂进最后一个 `<li>`，不能落到列表之外。
- 内联图标若排在提示框（note）之前，输出顺序须保持“图标 → note”，不能因为提示框先冲刷而把图标挤到 note 之后。
- 内联按钮图标必须保持它在句中的原始位置，不能下沉到段落/列表项末尾：例如源为「点击[icon]，托盘将自动收回…」时，输出须为 `<li><p>点击<image href="…"/>，托盘将自动收回…</p></li>`，图标夹在 `点击` 与 `，` 之间。图标在解析阶段以占位符随文本一起传递，避免位置丢失。
- 段落正文中的状态图标（文件名以 `icon` 开头，如 `icon_status sequencing_1_1.ai`）按内联图片输出，段落保持为正文而不是被拆成独立的块级图片。
  - 交叉引用（`CrossReferenceSource`，源文形态为 `第<页码>页“目标标题”`）在解析阶段转成 `[[XREF:目标标题#页码]]` 标记（分隔符不用竖线，避免拆坏 markdown 表格）；页码取自 `TextVariableInstance/@ResultText`。DITA 阶段输出空标签 `<xref href="目标topic.dita" cms:title="目标标题"/>`，不把「第N 页标题」写进 xref 体内，页码由 IME 按目标 topic 生成。找不到对应 topic 时回退为纯文本 `第N 页“标题”`，不产出无效 `<xref>`。
  - 交叉引用的 `cms:title` 不带源文档或 IME 的章节编号（如 `9.1`），也不含页码。数字/英文后紧跟汉字处的空格只用于未解析回退文本（`第12 页`、`测定DNB 浓度`）。
  - IDML 斜体字符样式转为 `<i>`：`Cross reference` / `Cross reference-in para.-CN` 等（公式变量 `N`/`c`/`V`、书名）以及 `Subtle Emphasis`、`FontStyle="Italic"`。相邻斜体 run 合并。屏上控件样式优先于斜体。
 - 页码变量解析失败时省略“第N页”，只输出标题；不得残留 `第页“目标标题”` 这类空页码形式。
 - 非列表正文段落里的 `<Br/>` 是段落分隔（如 `关于说明书` 的 `Text in first page` 用一个段落样式写下多段声明）：每一截输出独立 `<p>`，不能拼成一个 `<p>`。
 - 表格单元格若使用 `Table:Bulleted list` / `Table:Numbered list` / `sentence list` 样式，单元格内由 `<Br/>` 分开的各项输出为该 `<entry>` 内的 `<ul>`/`<ol>`（版本记录的修订摘要即此结构）；`Table:Single sentence` 仍为纯文本。

## 图片规则

- 图片保留到输出包中。
- 图片不输出 `alt` 标签。
- 紧邻 note 文本的小图标图片视为 note 图标，跳过输出。
- 紧邻 note 的真实图片必须保留，只有尺寸很小（或无法读取）的图片才视为 note 图标。
- 出现在正文句子中的小按钮图标（如“点击界面右上角的 [按钮] 按键”）必须保留，并以内联 `<image>` 输出在句内。
 - 内联保留的判定范围：小图（尺寸不超过 220×120）所在段落同时含正文文本时内联输出；紧跟在上一句正文之后的孤立小图标也并入该句，不得拆成独立块图。
 - note 段落内的小图视为装饰，丢弃。
 - 句中图标若无法读取尺寸，只要该段同时含正文且不是 note/图题，仍按内联图标保留，不得拆成独立块图。
- 图像与图题包装为 `<fig><title>图题</title><image href="image/…" placement="break"></image></fig>`；编号由 IME 自动生成，`<title>` 内不放 `图 N`/`Figure N`。
- 同一图题段落内的多张实质图并入同一个 `<fig>`，不要拆成图题后的裸 `<image>`。
 - 图题后连续多图仍并入当前 `<fig>`；若下一张图后面紧跟另一条图题，则该图是下一图的配图，不得并入当前图。
- Word 装饰残图不输出：1 像素细条、扁长横幅，以及图题/说明句之后空段落里的小图。
- 图题识别：Word 用 `图 N`/`Figure N` 前缀；IDML 用 `Figure-title` 样式（经 `[[FIGCAP]]` 标记传递），图题无需自带编号。
- 块图后面紧跟的短说明（无 `图 N`/`Figure N` 前缀）包装为 `<fig><title>…</title>`，不要留成图下的普通 `<p>`。
- 图题后面没有紧跟图片时，回退为普通段落并保留原文编号，避免正文内容丢失。
- 输出包中的图片文件名保持源图片包（`Links/`）的原始名称，包含空格与中文；不做 `image_NNN` 重命名。参考包亦保留原始名（如 `G002708_image_loading flow cell.svg`）。
- 同名图片冲突时才追加 `_N` 后缀；图片管线不做压缩，保真优先。

## 表格规则

- 表格标题去掉 `Table N` 或 `表 N` 编号前缀。
- 表题编号前缀支持字母编号形式，例如 `表B-1 Barcode Primer使用规则` 去掉前缀后作为表题，不生成 topic。
- 仅有表题没有表体时，保留为普通段落，不伪造空表。
- DOCX 合并单元格按共享 `_tc` 保留真实内容，避免内容被误清空。
- Word 表头行数尊重 `w:tblHeader`：有 N 行 `tblHeader` 则前 N 行进 `<thead>`；没有 `tblHeader` 且首行存在向下 `vMerge` 时 `header_rows=0`，不得把数据行造成假表头。
- 若整张表每一行都带 `tblHeader`（常见于只有两行的推荐值表），只保留首行为 `<thead>`，其余进 `<tbody>`。
- 没有垂直合并的标签首行（如 `Workbench Position`）可作为 1 行 `<thead>`。
- Word `w:vMerge` / `w:gridSpan` 在解析阶段输出 `[[SPAN:c,r]]` / `[[SPANC]]`，DITA 阶段还原为 `morerows` 与 `namest`/`nameend`。
- 超宽表输出 `<table outputclass="180mm">`：`Sequencing Parameters` 整章、`Flexible-throughput` / `Consumable Usage` 等宽表章节，或列数 ≥ 7（覆盖 Barcode / Appendix C–E）。
- Word 表格跨页后重复出现的表头行，需要在转换后自动删除。
- 若同一 Markdown 表中出现嵌入式 `Table N ...` 行，视为下一张表的标题并拆分为独立表格。
- 被合并单元格拆碎的英文表题片段需自动拼回完整标题。

- 表格单元格内每个句段包在 `<p>`：`<entry><p>…</p></entry>`。空单元格保持 `<entry></entry>`。
- 单元格内列表同样每个 `<li>` 包 `<p>`。
- 正文每个句段各自一个 `<p>`，含 note 内文字。
 - IDML 表格列宽取自 `Column/@SingleColumnWidth`，按列宽占比写成 `<colspec colwidth="0.30*"/>` 这类相对宽度（各列之和为 `1.00*`）。解析阶段用 `[[COLW:0.30*,0.70*]]` 传递。缺少列宽时仍用 `1.00*`。提示框表格不写 colwidth。

## 验收口径

- 标题数量与结构和源 Word 对齐。
- 图片按有效内容去重后不丢失。
- note 图标图片不计入图片丢失。
- 表格标题、图片标题、列表、note 转换结果都应通过自动校验。
- 内容完整性：源文档全部段落必须出现在输出 DITA 中（用“源段落 → 输出全文”归一化比对，缺失数应为 0）。
- 结构合法性：输出的每个 `.dita` / `.ditamap` 必须可解析，ditamap 中所有 `href` 必须可达。
 - 每次转换完成后必须做一轮与原文核对：按本文件逐条检查模板复用、标题树、列表、note、uicontrol、图题/表题、图片和扉页；先跑单测与 `verify_word_to_dita_package.py`，再人工对照源 Word/IDML 与输出 DITA，把违规项按严重程度列出后再交给用户。

## Markdown 源解析规则

- 原生 `.md` / `.markdown` 先归一成与 Word/IDML 相同的中间标记，再走同一套 DITA 生成逻辑。
- ATX（`#` 到 `######`）与 Setext（`===` / `---`）标题都生成 topic；层级与源标题一致。
- 无标题文档输出为单个 topic，标题为 `文档`；第一个标题之前的引言单独输出为 `正文` topic。
- YAML front matter 的 `title` 在无标题或仅有引言时作为 topic 标题。
- `**加粗**` 转为 `<b>`；`*斜体*` 转为 `<i>`。行内代码不用 `<codeph>`；`.fq.gz`、`.arc` 这类格式名转为 `<i>`，其余行内代码输出为普通文本。
- `[文本](url)` 转为 `<xref>`；`http://` / `https://` 链接带 `scope="external" format="html"`。
- 围栏代码块（` ``` ` / `~~~`）转为 `<codeblock xml:space="preserve">`，语言写入 `outputclass`。
- 引用行去掉 `>` 后按正文处理；`注意` / `Note:` / `警告` / `Warning` 等标签仍按 Note 规则输出。
- 缩进列表按缩进层级构建嵌套 `<ul>` / `<ol>`，不得把子列表冲出父步骤。
- 单独一行的 `---` / `***` / `___` 视为分隔线，不输出段落。
- 围栏代码块内部的加粗、链接和引用标记保持原文，不做二次转换。
 - 正文中的 `Section 3.2` / `3.2 节` 转为指向该编号标题对应 topic 的 `<xref>`；其后的 step / 第 N 点保持原文。
 - 英文快速操作指南中，章容器标题 `Frequently asked questions & support` 保持不变，其下 chapterTopic 的可见标题改为 `Frequently asked questions & solutions`。

## 当前批量转换基线

- 当前稳定基线输出包：`当前工作区/backend/static/uploads/outputs/output_20260813_061625.zip`
- 当前核心实现文件：`当前工作区/backend/app/api/convert.py`
- 当前包级验收脚本：`当前工作区/backend/tools/verify_word_to_dita_package.py`

## 规则维护约定

- 本文件是 Word/WPS 与 IDML 转 DITA 转换规则的唯一基线，新增或调整转换规则时先更新本文件，再落实现与测试。
- 转换实现的回归测试见 `当前工作区/backend/tests/test_convert_dita_generation.py`；修改规则后必须同步补充/更新用例。
- 每次批量转换完成后，先跑单测与包级验收，再交给用户做平台侧导入验证。
 - 包级验收通过仍须做原文核对；不得只交 zip、不对照源文档和本规则。

原生 Markdown（`.md` / `.markdown`）转 DITA 共用同一套 Note、列表、表格、图片与验收规则；Markdown 特有语法写在“Markdown 源解析规则”小节。
 - 本文件是 Word/WPS、IDML 与 Markdown 转 DITA 转换规则的唯一基线，新增或调整转换规则时先更新本文件，再落实现与测试。
 - 原生 Markdown 的 `**加粗**` 即使出现在英文步骤列表中也转为 `<b>`，不按 Word 英文屏上控件处理。
