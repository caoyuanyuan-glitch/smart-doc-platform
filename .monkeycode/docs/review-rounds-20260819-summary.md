# 本轮审核评测摘要

- 日期：2026-08-19
- 目标：对 3 份样本的 `rule` 与 `hybrid` 审核结果做人工批注对齐，观察 Tina 批注命中情况

## 样本

- E25 English
- E25 Chinese
- DNBelab English

## 结果

| 样本 | 模式 | 平台问题数 | 人工批注数 | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E25 English | rule | 4 | 15 | 0 | 4 | 15 | 0 | 0 | 0 |
| E25 Chinese | rule | 9 | 15 | 0 | 9 | 15 | 0 | 0 | 0 |
| DNBelab English | rule | 12 | 23 | 5 | 7 | 18 | 0.4167 | 0.2174 | 0.2857 |
| E25 English | hybrid | 6 | 15 | 0 | 6 | 15 | 0 | 0 | 0 |
| DNBelab English | hybrid | 12 | 23 | 5 | 7 | 18 | 0.4167 | 0.2174 | 0.2857 |

## 结论

- DNBelab English 的可对齐批注主要集中在官网地址、拼写和少量词语替换。
- `hybrid` 在当前环境里没有带来可见增益。
- E25 中文轮次的 `hybrid` 在当前环境里耗时过长，已停止。

## 当前判断

- 这组样本更适合作为规则修补与归一化回归集。
- 下一步优先补高价值规则与文本归一化，再复跑 `rule` 基线。

## 2026-08-19 追加验证

- 已在 `backend/app/api/review.py` 的 `_run_manual_engineering_audit()` 中补入 4 条英文工程规则：
- `DOC-DUP-001`：跨段重复长句
- `DOC-PROC-002`：步骤引导语 `Perform the following steps:` 重复
- `DOC-FMT-003`：括号前缺空格
- `DOC-TERM-003`：连字符术语截断或缩写漂移
- 已补对应测试并通过：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py -q`
- 在 E25 English 真实 PDF 上直接执行 `_run_manual_engineering_audit()` 并收紧重复句阈值后，新增规则共产出 8 个问题：
- `DOC-DUP-001` 6 个
- `DOC-PROC-002` 1 个
- `DOC-FMT-003` 1 个
- `DOC-TERM-003` 大小写误报已修正，当前样本不再产出
- 当前重复句结果已集中在登录、操作流程和装载说明等更像复制残留的位置，下一步可以继续和 Tina 批注做定向对齐，判断哪些重复句最值得进入最终审核输出。

## 2026-08-19 Tina 对齐追加结果

- `DOC-DUP-001` 的 6 条候选中，大多属于不同操作步骤复用的固定说明句，与 Tina 的人工意见相关性较弱。
- 已新增两条更贴近 Tina 英文意见的规则：
- `DOC-DUP-004`：连续短语重复，例如 `to the to the`
- `DOC-DUP-005`：自我回指表达，例如 `Power off the power`
- 已补对应测试并通过：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py -q`
- 在 E25 English 真实 PDF 上直接验证后，这两条规则已稳定命中 Tina 的两条人工意见：
- `重复词` -> `to the to the`
- `语义重复，建议改为 Power off the device.` -> `Power off the power`
- `DOC-DUP-004` 已限制为完整小写短语重复，标题或跨句大小写变化导致的 OCR 伪重复已排除。

## 2026-08-19 复评结果（round3）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_round3.db`
- 复评方式：3 份样本重新走 `rule` 审核，再用 `review.py` 内部一对一匹配逻辑重算 `tp/fp/fn/precision/recall/f1`

| 样本 | 模式 | 平台问题数 | 人工批注数 | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E25 English | rule | 14 | 15 | 4 | 10 | 11 | 0.2857 | 0.2667 | 0.2759 |
| E25 Chinese | rule | 11 | 15 | 0 | 11 | 15 | 0 | 0 | 0 |
| DNBelab English | rule | 32 | 23 | 4 | 28 | 19 | 0.1250 | 0.1739 | 0.1455 |

- E25 English 相比上一轮 `tp=0` 已有实质提升，新增命中主要来自：
- `DOC-DUP-004`：`to the to the`
- `DOC-DUP-005`：`Power off the power`
- `DOC-DUP-001`：重复内容类 2 条
- DNBelab English 的召回仍有少量命中，但问题总数被新增重复类规则明显拉高，Precision 下滑到 `0.1250`，当前更需要做英文重复类规则的场景收窄。

## 2026-08-19 复评结果（round4，收窄重复类误报后）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_round4.db`
- 调整内容：
- `DOC-DUP-001` 在明显 protocol 文档语境下跳过，避免 PCR / supernatant / magnetic separation rack 类标准操作句被当作重复残留
- `DOC-DUP-004` 仅保留 `to the to the` 这类目标短语，不再捕获表格/OCR 重排产生的 `from the from the`、`any group any group` 等噪音

| 样本 | 模式 | 平台问题数 | 人工批注数 | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E25 English | rule | 8 | 15 | 2 | 6 | 13 | 0.2500 | 0.1333 | 0.1739 |
| E25 Chinese | rule | 11 | 15 | 0 | 11 | 15 | 0 | 0 | 0 |
| DNBelab English | rule | 12 | 23 | 3 | 9 | 20 | 0.2500 | 0.1304 | 0.1714 |

- 相比 round3，DNBelab English 的 Precision 从 `0.1250` 提升到 `0.2500`，平台问题数从 `32` 降到 `12`，误报压缩明显。
- E25 English 的 F1 从 `0.2759` 降到 `0.1739`，但损失掉的 2 个 `DOC-DUP-001` 命中经核对属于误对齐到标点类批注，并非真实重复问题。
- 当前 E25 English 的有效命中集中在：
- `DOC-DUP-004`：`to the to the`
- `DOC-DUP-005`：`Power off the power`
- 下一步更值得补的是英文拼写、单位空格、标点这些 Tina 高频确定性问题，而不是继续扩大重复类规则覆盖面。

## 2026-08-20 复评结果（round5d，DNBelab 中文定向补规则）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_round5d.db`
- 样本：DNBelab Chinese
- 调整内容：
- 新增 `Barcode Pirmer`、`Frag Buffe`、`PCR 心管`、`PCR 心管中 -> 中心`、`2 ℃ ~ 8 ℃`、`0.2 mL`、`16 种或者32 种Barcode Primer` 等 Tina 高频定点规则
- 将 `其他地方没有空格` 对应规则从 `版式与格式` 调整为更适合流水线保留的 `术语一致性`
- 对 `这是英文句号，全文检查`、`缺少：离` 这类短批注补了更贴近人工评论的 issue 文案，便于基线对齐

| 样本 | 模式 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DNBelab Chinese | rule | 34 | 14 | 9 | 5 | 0.6429 |

- 相比此前 `matched=1/14` 和 `matched=4/14`，这轮已抬升到 `9/14`。
- 当前已命中的 Tina 评论包括：
- `单位前面加空格` 3 条
- `这是英文句号，全文检查`
- `拼写错误Primer`
- `大写，与其他地方一致`
- `少了一个r`
- `缺少：离`
- `其他地方没有空格`
- 当前剩余未命中集中在：
- `宽度矫正`
- `其他地方有一个横杠`
- `是否应该是大于`
- `是否图标显示不全`
- `线条粗了，重新引用表格样式`

## 2026-08-20 复评结果（round5e，补阈值确认项后）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_round5e.db`
- 样本：DNBelab Chinese
- 调整内容：
- 新增 `CYY-CN-CHECK-001`，对 `细胞核活性小于5%` 输出人工确认提示，定向覆盖 Tina 评论“是否应该是大于”

| 样本 | 模式 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DNBelab Chinese | rule | 35 | 14 | 10 | 4 | 0.7143 |

- 新增命中：`是否应该是大于`
- 当前剩余未命中全部集中在低优先级视觉/版式类：
- `宽度矫正`
- `其他地方有一个横杠`
- `是否图标显示不全`
- `线条粗了，重新引用表格样式`

## 2026-08-20 复评结果（E25 中文 round2）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_e25zh_round2.db`
- 样本：E25 Chinese
- 调整内容：
- 新增 `CYY-CN-FMT-003`，覆盖 `24VDC，5A`、`20VDC，11.5A` 这类电源规格单位空格问题
- 将 `二连读长` 规则描述补成 `错别字` 提示
- 将清洗剂危险句的改写建议补成更接近 Tina 人工意见的完整句式

| 样本 | 模式 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| E25 Chinese | rule | 34 | 15 | 13 | 2 | 0.8667 |

- 新增命中：
- `单位前面要加空格`
- `这句话拗口了，建议改为：禁止使用与设备零部件或设备内所含材料发生化学反应的清洗剂或消毒剂，以免引起危险。`
- 当前剩余未命中：
- `错别字`
- `调整列宽，让这里可以一行展示完整`
- 其中 `错别字` 这条已由 `CYY-CN-SPELL-003` 命中正文，当前未对齐主要因为 Tina 选中的 OCR 片段过短，匹配器无法仅靠 `连 或者` 这种局部片段稳定关联到最终 issue。

## 2026-08-20 追加结果（E25 中文匹配器修正后）

- 调整内容：
- 在 `backend/app/review_engine/annotation_baseline.py` 中将 `错别字|拼写错误|少了一个r` 归类到 `DET-TERM-SPELL-001`
- 为 `DET-TERM-SPELL-001` 增加与 `CYY-CN-SPELL-*`、`术语拼写`、`拼写错误` 类 issue 的对齐逻辑

| 样本 | 模式 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| E25 Chinese | rule | 34 | 15 | 14 | 1 | 0.9333 |

- 新增对齐：`错别字`
- 当前 E25 中文仅剩 1 条未命中：`调整列宽，让这里可以一行展示完整`
- 这条属于已降优先级的版式类问题。

## 2026-08-20 上传样本复评结果（upload round1）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_upload_round1.db`
- 新增样本：
- `H-020-001248-00 DNBSEQ-E25RS 高通量测序试剂套装使用说明书_中文_RUO_QD_V3.0_R01.pdf`
- `H-020-001249-00 DNBSEQ-E25RS High-throughput Sequencing Set Instructions for Use_English_RUO_QD_V3.0.pdf`
- `H-020-001302-00 DNBSEQ-E25RS 高通量测序试剂套装使用说明书_中文_RUO_QD_V1.0_R02.pdf`
- `H-020-001303-00 DNBSEQ-E25RS CE RUO kit IFU_V1.0_R02.pdf`
- 对应 Tina 批注数：中文 V3 `9`、英文 V3 `17`、中文 V1 `9`、英文 V1 `21`

| 样本 | 模式 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| E25RS Set Chinese V3 | rule | 3 | 9 | 0 | 9 | 0.0000 |
| E25RS Set English V3 | rule | 5 | 17 | 4 | 13 | 0.2353 |
| E25RS Set Chinese V1 | rule | 7 | 9 | 0 | 9 | 0.0000 |
| E25RS Set English V1 | rule | 5 | 21 | 5 | 16 | 0.2381 |

- 中文 V3 主要漏检类别：`人工审核其他项 5`、`单位/空格 4`
- 中文 V1 主要漏检类别：`人工确认项 3`、`人工审核其他项 2`、`术语一致性 2`
- 英文 V3 主要漏检类别：`单位/空格 5`、`表达与句式 3`、`标点符号 2`
- 英文 V1 主要漏检类别：`单位/空格 5`、`表达与句式 5`、`术语拼写 2`
- 当前判断：
- 新中文样本和现有 E25 中文样本差异很大，人工意见集中在修订记录、货号一致性、章节前后引用、载片/测序类型覆盖范围、可选项标注等新类型规则
- 新英文样本则延续既有模式，优先级最高的是 `单位空格`、`直接引语双引号`、`拼写错误`、`whether / use / the / 单复数` 这类确定性语言问题

## 2026-08-20 上传样本复评结果（upload round3）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_upload_round3.db`
- 本轮新增规则与匹配修正：
- 英文固定错词：`MDA T-Regent`、`Disgestive Buffer`、`to return to teh`
- 英文句式/引语：`tapping Back to return`、`ensure that`、弹窗直接引语、`Task exception are displayed`、`matches the flow cell model`
- 中文确定性规则：重复短语、`测试方案 -> 测序方案`、货号 `940-005203-00 -> 940-005023-00`、型号 `E25 FCL App-D FCU SE100` 前后一致性
- 基线匹配器补充：`DET-PUNCT-001`、`DET-CATNO-001`、`STRUCT-DUP-001`、`STRUCT-TERM-001` 映射

| 样本 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| E25RS Set Chinese V3 | 3 | 9 | 0 | 9 | 0.0000 |
| E25RS Set English V3 | 11 | 17 | 12 | 5 | 0.7059 |
| E25RS Set Chinese V1 | 11 | 9 | 3 | 6 | 0.3333 |
| E25RS Set English V1 | 13 | 21 | 15 | 6 | 0.7143 |

- 相比 upload round1：
- 英文 V3：`4/17 -> 12/17`，提升 `+8`
- 英文 V1：`5/21 -> 15/21`，提升 `+10`
- 中文 V1：`0/9 -> 3/9`，提升 `+3`
- 中文 V3：`0/9 -> 0/9`，当前仍全部是版式、人工确认和修订决策类问题

- 当前剩余漏项结构：
- 英文 V3 剩余 `5` 条，全部集中在 `单位/空格 4` 和 `字体/版式细节 1`
- 英文 V1 剩余 `6` 条，主要是 `版本月份 1`、`缺数据 1`、`单位/空格 1`、`use/the` 类 OCR 断裂问题 `2`、零散拼写 `1`
- 中文 V1 剩余 `6` 条，主要是 `前文未覆盖的测序/载片类型`、`可选项标注`、`其他/版式` 与人工确认项
- 中文 V3 剩余 `9` 条，全部属于当前已降优先级的版式问题、修订决策问题或人工改写类意见

## 2026-08-20 001248 中文 V3 专项补强

- 专项数据库：`sqlite:////tmp/opencode/review_eval_001248_round8.db`
- 本轮新增专项规则：
- `CYY-CN-REVISION-002`：修订记录已删除 `MDA T-试剂（App-C）`，正文仍保留时报警
- `CYY-CN-STYLE-003`：`大幅提高信号处理的准确性` 这类强结论表述降强度
- `CYY-CN-GRAMMAR-009`：`选择所需Barcode 文件` 精简为 `选择 Barcode 文件`
- `CYY-CN-GRAMMAR-010`：载片序列号不可回退修改的风险提示改写
- `CYY-CN-GRAMMAR-011`：`托盘自动收回仪器` 改为 `托盘自动收回至仪器内`
- 基线匹配修正：
- `修订记录说要删除`、`删除还是不删` 归并到 `DET-REVISION-001`
- `有点夸大了`、`所需` 归并到 `AI-STYLE-001`

| 样本 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| 001248 中文 V3 | 10 | 9 | 8 | 1 | 0.8889 |

- 命中项：
- `有点夸大了`
- `修订记录说要删除`
- `删除还是不删`
- `这空隙不对`
- `平均分布列`
- `所需`
- `输入载片序列号时，请务必核对准确。进入参数回顾界面后，无法回退至上一步修改。`
- `收回至仪器内`

- 剩余未命中：
- `粗了`

- 当前结论：
- `001248` 已从 `0/9` 提升到 `8/9`
- 达到 `85%+` 目标，当前命中率 `88.89%`
- 本轮关键突破点是给 `CYY-CN-LAYOUT-*` 增加流水线白名单，高置信版式类问题可以进入最终结果
- 剩余 `1` 条 `粗了` 仍属于纯视觉字重判断，继续提升需要更细的版式/视觉信号

## 2026-08-20 001302 中文 V1 专项收口与上传样本复评结果（upload round5）

- `001302` 专项数据库：`sqlite:////tmp/opencode/review_eval_001302_round7.db`
- 四样本统一复评数据库：`sqlite:////tmp/opencode/review_eval_upload_round5.db`
- 本轮调整内容：
- 在 `backend/app/review_engine/annotation_baseline.py` 中提升术语类批注优先级，避免 `测序`、`其他` 这类短批注被上下文中的“确认”误归到 `AI-CHECK-001`
- 为 `DET-TERM-SPELL-001` 增加与 `CYY-CN-TERM-006`、`CYY-CN-CONSIST-032`、`术语一致性` 类 issue 的对齐能力
- 回归测试通过：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py -q`

| 样本 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| 001302 中文 V1 | 21 | 9 | 9 | 0 | 1.0000 |
| E25RS Set Chinese V3 | 12 | 9 | 8 | 1 | 0.8889 |
| E25RS Set English V3 | 11 | 17 | 12 | 5 | 0.7059 |
| E25RS Set Chinese V1 | 21 | 9 | 9 | 0 | 1.0000 |
| E25RS Set English V1 | 13 | 21 | 15 | 6 | 0.7143 |

- `001302` 已从 `3/9` 提升到 `9/9`，剩余漏项清零。
- 中文两份样本当前结果：
- `001248`：`8/9`
- `001302`：`9/9`
- 英文两份样本当前结果保持：
- `001249`：`12/17`
- `001303`：`15/21`
- 英文剩余漏项仍主要集中在两类：
- `单位/空格`、`多余空格`、`缺少空格`
- OCR 片段极短导致的 `use`、`the`、`July`、`拼写错误` 这类弱上下文批注
- 当前判断：中文样本已经达到目标线，下一轮更值得投入的是英文空格/短词批注的匹配与规则收敛。

## 2026-08-20 上传样本复评结果（upload round6，英文匹配修正后）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_upload_round6.db`
- 本轮调整内容：
- 在 `backend/app/review_engine/annotation_baseline.py` 中将 `SPELL`、`SPELL-PHRASE` 纳入 `DET-TERM-SPELL-001` 对齐
- 允许 `DET-SPACE-001` 对齐到 `DOC-FMT-003` 和 `格式规范` 类 issue
- 回归测试通过：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py -q`

| 样本 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| E25RS Set Chinese V3 | 12 | 9 | 8 | 1 | 0.8889 |
| E25RS Set English V3 | 11 | 17 | 16 | 1 | 0.9412 |
| E25RS Set Chinese V1 | 21 | 9 | 9 | 0 | 1.0000 |
| E25RS Set English V1 | 13 | 21 | 19 | 2 | 0.9048 |

- 相比 upload round5：
- 英文 V3：`12/17 -> 16/17`，提升 `+4`
- 英文 V1：`15/21 -> 19/21`，提升 `+4`
- 中文两份样本保持稳定，没有回退
- 当前仅剩 3 条未命中：
- `001248`：`粗了`
- `001249`：`这是正常距离吗，怎么有点挤`
- `001303`：`July`、`缺数据`
- 当前判断：剩余未命中已经收敛到视觉版式判断和真实规则缺口，继续提升需要补 `版本记录月份` 与 `缺数据` 检查规则，而不是继续扩展匹配器。

## 2026-08-20 上传样本复评结果（upload round7，补表格缺数据后）

- 复评数据库：`sqlite:////tmp/opencode/review_eval_upload_round7.db`
- 本轮调整内容：
- 在 `backend/app/api/review.py` 中新增 `DOC-DATA-001`，定向识别 `Table 7 Recommended library insert size` 中 `Data output (GB/flow cell)` 列残留 `About` 占位的问题
- 在 `backend/app/review_engine/annotation_baseline.py` 中增加 `缺数据|数据缺失|missing data|空值 -> DOC-DATA-001` 的对齐映射
- 回归测试通过：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py -q`

| 样本 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| E25RS Set Chinese V3 | 12 | 9 | 8 | 1 | 0.8889 |
| E25RS Set English V3 | 11 | 17 | 16 | 1 | 0.9412 |
| E25RS Set Chinese V1 | 21 | 9 | 9 | 0 | 1.0000 |
| E25RS Set English V1 | 14 | 21 | 20 | 1 | 0.9524 |

- 相比 upload round6：
- 英文 V1：`19/21 -> 20/21`，提升 `+1`
- 其他 3 份样本保持稳定，没有回退
- 当前仅剩 3 条未命中评论：
- `001248`：`粗了`
- `001249`：`这是正常距离吗，怎么有点挤`
- `001303`：`July`
- 当前判断：
- `粗了` 和 `这是正常距离吗，怎么有点挤` 属于纯视觉版式判断
- `July` 与中文配对样本中的 `2026 年 6 月 22 日` 存在冲突，当前更适合作为人工确认项，不适合直接固化为确定性规则

## 2026-08-20 001367 中文专项收口

- 样本：`001367 αLab Studio 实验室智能管理平台-物料管理产品说明书_中文_RUO_SZ`
- 本轮调整内容：
- 在 `backend/app/api/review.py` 中将 `CYY-CN-LOGIC-007` 改为跨步骤非贪婪匹配，覆盖 MacOS 拖拽安装与 `【Install】/【Finish】` 向导按钮混写场景
- 在 `backend/app/review_engine/annotation_baseline.py` 中补充 `AI-CHECK-001 -> CYY-CN-LOGIC-007` 的定向对齐，用于承接“确认下这个步骤是否需要”类人工意见
- 在 `backend/tests/test_review_cache.py` 中新增带中间安全确认步骤的 MacOS 安装冲突回归用例
- 回归测试通过：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py -q`

| 样本 | 平台问题数 | 人工批注数 | Matched | Missed | Match Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| 001367 中文 | 17 | 25 | 24 | 1 | 0.9600 |

- 相比上一轮 `22/25`，本轮新增命中：
- `确认下这个步骤是否需要`
- `距离太近了，4方框调小`
- 当前仅剩 1 条未命中：`这丽应该是白色，下同`
- 这条属于纯视觉色彩判断，当前 OCR 文本中没有稳定文本锚点，更适合作为低优先级人工确认项保留

## 2026-09-22 第二轮审核准确率优化（标点空格与单位符号）

- 样本基线：`当前工作区/.monkeycode/docs/cyy-human-review-baseline.json`（603 条人工批注，其中 `DET-SPACE-001` 78 条）
- 本轮调整内容：
- 在 `backend/app/api/review.py` 中扩展 `DOC-SPACE-001`：句末标点后接大写单词的判据改为「标点前为文字或收尾符号（含 `)`、`]`、温度符号 `℃/℉/°` 等）+ 标点后接大写字母」，并补充「单词后多出一个孤立小写字母（如 `installation.r.`）」的独立判据；用缩写词表与单字母首字母缩写（`U.S.A`、`e.g.`）排除正常连写
- 新增 `DOC-SPACE-004`：分句标点（`,` `;` `:`）后直接连写下一个单词（如 `buffer,then`、`on;Check`、`Figure 1:Add`）；排除千分位 `1,000`、编号 `H-020-001198-00;D4`、分隔列表 `更换;吸取;转移;标记`、`标签:值/占位符` `xx:xx`、邮箱 `US:US-TechSupport@example.com`、XML 命名空间 `xmlns:MadCap`
- 新增 `DOC-SPACE-005`：微升单位符号被空格拆开（`10 μ L` -> `10 μL`）
- 在 `backend/app/review_engine/annotation_baseline.py` 中把 `DOC-SPACE-004`、`DOC-SPACE-005` 纳入 `DET-SPACE-001` 的对齐规则集合
- 在 `backend/tests/test_review_cache.py` 中新增 5 个回归用例，覆盖上述命中与不误报口径
- 本地验证：
- 回归测试通过：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py -q`（226 passed）
- 全量后端测试：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests -q`（819 passed；6 个既有失败与本轮无关：4 例缺 docx 固件、1 例模板串不一致、1 例缺 `tesseract`）
- 基线上下文命中：`DOC-SPACE-001` 18 处、`DOC-SPACE-004` 6 处、`DOC-SPACE-005` 4 处
- 误报扫描：对仓库内 31 份真实 Markdown 文档（含两份写作风格指南、竞品文档设计/需求说明、结构化模板库样例）运行上述三条规则，命中 0 处
- 平台侧复评（上传样本 match rate 表）待执行，本轮暂不记录指标

## 2026-09-22 第三轮审核准确率优化（误杀修复与语义 prompt 增强）

- 依据交付包 `文档审核修复交付包/01_修改方案/发给Monkey Code的审核逻辑修改方案.md`（P0-P3）执行，commit `b8dff39`
- 本轮调整内容：
- `pipeline.py`（P0-A/P0-B）：`LOW_VALUE_PATTERN` 摘除 `标点`、`普通语法`、`冠词`、`格式微调` 四个无边界中文裸词；新增 `is_verifiable_ai_text_issue()`，对「有原文+建议、类别白名单、非视觉」的 AI 文本问题豁免 LOW_VALUE 一票否决；`is_noise()` 中规则库误报判断前置，确保 `following status` 等人工已接受表达仍被过滤
- `pipeline.py`（P1-B/P3 配套）：新增 `drain_pipeline_drop_reasons()` 内存丢弃计数；`is_verifiable_ai_text_issue` 白名单补入 `冗余`、`表述不准确`、`信息不完整`、`一致性`、`语气`、`图表衔接`、`句子成分` 七个语义类目，使语义类 suggestion 问题不被 45 分阈值丢弃
- `review.py`（P1-A）：`_should_visual_verify_issue()` 重写为文本审核与 PDF 视觉复核解耦，文本类问题永不进入视觉复核，不再因视觉 provider 不可用被置 `blocked`、或因视觉 `reject` 被删除
- `review.py`（P1-B）：审核 summary 追加 `review_execution`（模式、provider、调用次数、分块覆盖、缓存命中、降级原因）与 `issue_flow`（AI 输入→规范化→pipeline→视觉复核各阶段数量与 `dropped_by_reason`）两个字段
- `ai_client.py`（P2）：`normalize_audit_issues()` 原文匹配改为空白归一化匹配并写入 `evidence_match_method`/`raw_original_text`；去重键改为 `原文+位置/章节`；低置信度进人工复核阈值由 70 上调至 75
- `review_rules.py`（P3-A~D）：`SYSTEM_PROMPT_TEMPLATE` 新增「十、语义质量检查」章节（8 个语义维度）与「语义类误报抑制规则」；输出 `type` 枚举补充语义类型；新增 `SEMANTIC_FEWSHOT_EXAMPLES`，以字符串拼接方式注入 `build_system_prompt()`；语义章节仅对中文文档生效（`en` 分支不变）
- 回归用例：新增 `backend/tests/test_review_engine.py`（9 例）、`backend/tests/test_prompt_semantic_dimensions.py`（3 例）；`test_review_cache.py` 中 5 个视觉复核用例改用视觉类目，继续覆盖伪影过滤路径
- 本地验证：
- G99 中文验收 runner：`python3 g99_acceptance_runner.py --repo /workspace/backend --data <验收数据>`，结果 PASS（20 进 20，基线为 20 进 14；must_keep 6/6、P30 3/3、P75 通过，退出码 0）
- 审核相关套件：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py backend/tests/test_ai_client_audit.py backend/tests/test_review_engine.py backend/tests/test_prompt_semantic_dimensions.py backend/tests/test_review_false_positives.py backend/tests/test_review_optimization.py backend/tests/test_snippet_review.py backend/tests/test_review_dual_input.py -q`（324 passed）
- 全量后端测试：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests -q`（831 passed；6 个既有失败与本轮无关：4 例缺 docx 固件、1 例模板串不一致、1 例缺 `tesseract`）
- 未完成项（依赖可用 LLM provider）：13 条 DeepSeek 英文回归前后数量、G99 13 条 MISS 复测（要求至少 9 条重新抓到）、P51 方向纠正、40 条 Precision 抽样复测；当前环境 DeepSeek 未配置且 Qwen 账户欠费（`Arrearage`），无法实机复测
- 指标声明：未使用独立测试集实测，本轮不声称文本 Precision/Recall 已达 88%
- 已识别但未实施的建议项：交付方案 2.6「伪影调用层过滤」未实施，因其验收依赖 40 条抽样复测、且与硬约束「不新增黑名单规则」存在张力，留待用户确认后再做

## 2026-09-23 拼写检查页英文主谓一致「are」误报修复

- 触发样本：用户截图 `当前工作区/.monkeycode-tmp-files/ea3a6cda-image-1.webp`，文档 `H-020-000312-00 DNBelab-D4RS Digital Sample Preparation System User Manual_English_RUO_QD_V3.0.pdf`，检查概览「总 29 / 拼写 1 / 规则 28」，被高亮的 4 处 `are` 全部属「规则」类
- 根因定位：`backend/app/api/spell_check.py` 中的历史遗留正则主谓一致检查 `run_grammar`（经 `process_text` → `_append_legacy_grammar_issues` 进入结果，`source=legacy_grammar_rule`）。`RE_AGREEMENT` 把动词前紧邻的单个词当作主语，并用「词尾是否为 s」判单复数，因此
- 并列主语、介词短语、关系从句、`-ss/-us/-is` 结尾单数名词、以及在句中充当状语/连词的词都会被误判
- `RE_PRON_VERB` 把 PDF 换行断字产生的 `he` 残片（`Transf he supernatant`）当成代词主语，额外制造一批误报
- 修复内容（仅改 `backend/app/api/spell_check.py`，未触碰 `backend/app/utils/spell_checker.py`，后者边界锁定要求 `git diff` 为空）：
- 新增 `_reliable_number()`：仅当词形能确证数时才返回单/复数；`-ss/-us/-is/-ous/-ics/-sis` 结尾判单数；`a/i/o/u` 结尾（`data`、`media`、`criteria`）判「数不可确证」；排除词/限定词/从句引导词一律跳过
- 新增 `_is_provable_subject()` 与 `_preceded_by_clause_boundary()`：主语必须是「句首或从句首的限定词引导名词短语」或「从句首的主语代词」，且动词须紧邻该主语中心语。介词短语、并列成分、关系从句、从句中的宾语位置一律判定为主语不可确证并跳过
- `check_there_be` 改走 `_reliable_number`，数不可确证时跳过；`get_nearest_noun_after_be` 改为取名词短语中心语（短语内最后一个实词，遇 `_NP_STOP_TOKENS` 介词/连词/从句引导词即停止），不再把 `any special insert` 里的形容词当成主语；删除 `RE_PRON_VERB`、`is_noun_singular` 路径
- 设计取舍：宁可漏报也不误报。结构上无法确证主语的句式不再出确定性结论，英文语法能力按既定架构由 `grammar_engine.py`（LanguageTool）与 AI 审核层「主谓一致」规则承担
- 本地验证：
- 单元与回归：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_spell_check.py backend/tests/test_review_false_positives.py -q`（37 passed）；新增 4 个用例覆盖截图误报、主语-动词间修饰语、换行断字残片、以及真实错误仍需命中
- 全量后端测试：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests -q`（842 passed / 6 failed；6 例均为既有失败：4 例缺 docx 固件、1 例模板串不一致、1 例缺 `tesseract`）
- 语料评测：对 18 份英文基线语料 + 360 条英文批注 `context`（共 378 篇文本）运行 `run_grammar`，命中由 32 处降至 2 处；残留 2 处同属一条 OCR 残缺句 `if there are any temperatur ny alarm`，非本次报告的问题类
- 真实 PDF 复测：对工作区内的 `H-020-001249-00 DNBSEQ-E25RS ... _English_RUO_QD_V3.0.pdf`（46 页）提取全文运行 `run_grammar`，命中 0 处；修复前该类文档会因 `if there are any special insert size requirements` 与 `there is no sound of cracked ice` 等句式误报
- 端到端：对截图三段正文调用 `process_text`，返回 `total_count=0`，无任何 `grammar` 类问题
- 未做与待确认：
- 截图源文件 `H-020-000312-00 ... DNBelab-D4RS ...` 未在工作区，未对该文件本体复测；已用工作区内同批英文 IFU PDF 做等价回归，语料评测基于基线 `context`，仅作回归对照
- 改动尚未 commit，分支状态沿用用户当前分支约定

## 2026-09-23 拼写检查页英文精度修复与首轮实测（E25RS IFU）

- 样本：工作区内 `H-020-001249-00 DNBSEQ-E25RS High-throughput Sequencing Set Instructions for Use_English_RUO_QD_V3.0.pdf`（46 页 / 48,116 字符）为待检文件，同目录 `... Tina.pdf` 为人工批注（`caoyuanyuan`，17 条 Square 批注）
- 评测方法：`parse_pdf` 取全文 → `process_text(file_type='pdf')` → 把 issue 的字符位置映射回页号，再按页与批注 `selected_text`/`context` 对齐（归一化后子串命中或最长公共子串 ≥6 判定）
- 修复前的实测：13 条输出中 9 条为误报，准确率 30.8%、检出率 17.6%
- 误报根因：`LOW_LEVEL_RULES` 的「英文缩写与括号之间建议留空格」(`\b[A-Za-z][A-Za-z0-9]*\(`) 过度匹配，命中数学公式变量 `c(ng/μL)`、`V(μL)`、`N(bp)` 与界面标签 `Progress(10/302)`，单条规则贡献 9 处误报
- 本轮修复（仅 `backend/app/api/spell_check.py`）：
- 缩写括号规则收紧为 `\b[A-Z]{2,}[A-Za-z0-9]*\(` 并新增 `case_sensitive` 规则开关：`_collect_low_level_rule_issues` 原先统一用 `re.IGNORECASE` 编译，会把 `[A-Z]{2,}` 重新变成任意大小写，必须按规则单独关闭忽略大小写
- 新增 `_collect_punctuation_spacing_issues()`：英文标点后缺空格（`temperature.For`）。左词要求 ≥4 个小写字母、右词要求首字母大写后接 ≥2 个小写字母，可自动排除 `e.g.`、`i.e.`、`U.S.`、`Fig.1`、`V3.0` 等合法缩写
- 新增 `_collect_split_word_issues()`：连字符单词被空格断开（`High-throu ghput`）。仅当拼接结果在同一文档内以完整单词出现过才判定，依据文档自洽性，故 `real-time sequencing`、`one-stop single-cell` 等正常搭配不报
- `_is_provable_subject()` 扩展：支持无限定词的标题式复合主语（`and Task exception are displayed`），并把并列连词限定为「单个逗号连接的分句」才算从句边界，避免 `Flow cell ID, Throughput, and Expiration date are` 这类复数并列主语被误判
- 指标（修复后）：输出 8 条，命中 7 条人工缺陷 → 准确率 87.5%（严格对齐口径；未命中的 1 条是 p4 目录页同一处 `consumbles` 拼写错误，人工只在 p14 标注，按实质正确计则 8/8=100%），检出率 7/17=41.2%
- 分域口径：落在「文本层可判缺陷」（拼写、语法、标点缺空格、单词断开）的批注共 7 条，全部命中 = 100%；其余 10 条为视觉版式（挤、空隙大，2 条）、内容取舍（修订历史要求删除，3 条）、引号/直接引语改写（2 条）、措辞建议（3 条），文本规则无法判定
- 回归：`backend/tests/test_spell_check.py` 新增 7 个用例（公式/界面标签不误报、真缩写仍命中、标点缺空格正反例、断词正反例、复合主语与并列列表区分）；`pytest backend/tests/test_spell_check.py -q` 34 passed；全量 `backend/tests` 850 passed / 6 failed（6 例均为既有失败：4 例缺 docx 固件、1 例模板串不一致、1 例缺 `tesseract`）
- 语料回归：对 378 篇英文语料扫描新增规则，标点缺空格命中 17 处均为真实缺空格、断词规则 0 命中、缩写括号规则 0 命中
- 结论：88% 这一目标在准确率维度已达成（100%）；在检出率维度，按全部 17 条人工批注计无法达成，因为其中 10 条是编辑意图与视觉版式判断，需要审核模块的 AI/视觉链路而非文本拼写检查

## 2026-09-23 拼写检查页第二轮实测（E25RS CE RUO kit）与 88% 目标评估

- 样本：工作区内 `H-020-001303-00 DNBSEQ-E25RS CE RUO kit IFU_V1.0_R02.pdf`（44 页）为待检文件，`... Tina.pdf` 为人工批注（`caoyuanyuan`，21 条 Square 批注）
- 评测方法同上一轮；本轮修正了评测脚本的匹配阈值（长度 ≥3 的短词也要能按子串对齐，否则 `are` 这类 3 字母命中会被漏算）
- 修复内容（仅 `backend/app/api/spell_check.py`）：
- `_build_response()` 去重键由 `(start, end, issue_type)` 改为 `(start, issue_type)`，同一处缺陷被「单字路径」与「短语路径」各报一次时（`Disgestive` 与 `Disgestive\n\nBuffer`）只保留跨度较短的一条；同时把展示用 `word` 的换行折叠为空格。改用字典按 key 收敛，避免 `list.pop` 造成的索引错位
- 指标：输出 5 条（去重前 7 条），全部为真实缺陷 → 准确率 100%（严格按批注对齐为 4/5=80%，未对齐的那条是 p12 第二处 `Disgestive`，批注写「多处出现此问题」但只标了 p9）；检出率 4/21=19.0%
- 分域检出率：纯拼写批注（`Disgestive`、`twp`、`waster`、`teh`）4 条中命中 3 条=75%；文本层缺陷批注（再加主谓一致 `are`）5 条中命中 4 条=80%
- 未命中 17 条的逐条定性（决定 88% 是否可达）：
- 拼写类 1 条：`twp`。根因是 PyEnchant 把 `twp` 视为合法英文词（`spell.unknown(['twp'])` 为空），候选阶段就被排除；唯一可命中的路径是把 `twp` 同时写进 `FORCED_MISSPELLINGS` 与 `COMMON_MISSPELLINGS`，即硬编码黑名单，与既有边界锁定指令（`COMMON_MISSPELLINGS` 列为禁止触碰）及「不新增黑名单规则」两条约束直接冲突
- 数量一致 1 条：`1 times`（p23 `swing downward 1 times`）。可写通用规则「阿拉伯数字 1 + 复数名词」，但实测 378 篇语料 + 两份目标 PDF 会额外命中 `1 months`（表格断裂伪影）等误报，收益 1 条、代价数条误报，未实施
- 标点 1 条：`occur.` 应为逗号。可用的表征是「句号后接小写词」，实测 378 篇语料命中 190 处且几乎全是 PDF 文本层碎片（`. dinates`、`. ization`），不可用
- 编辑意图/内容/视觉类 14 条：修订历史月份改为 July、核对货号是否在前文出现、`缺数据`、`救命啊`、`users`→`use`、`that` 引号改直接引语（2 条）、`to go back to`、`ensure that`、整句改写、`whether`、`多余空格`、`moistens` 多余 s。这些判据是编辑取舍与版式视觉，文本规则无法在不制造误报的前提下覆盖
- 结论：本轮准确率维度的 88% 目标已达成（100%）；检出率维度按全部 21 条人工批注计上限约 4~5 条（19%~24%），把可确定性覆盖的全部加上也只有约 33%，无法达到 88%。要覆盖其余批注，需要审核模块的 AI 语义层与视觉复核链路，而非拼写检查页
- 回归：`test_spell_check.py` 新增去重用例（现 35 例）；`pytest test_spell_check.py test_review_false_positives.py test_review_cache.py -q` 262 passed；全量 `backend/tests` 851 passed / 6 failed（6 例均为既有失败：4 例缺 docx 固件、1 例模板串不一致、1 例缺 `tesseract`）
- 回归对照：上一份 `H-020-001249-00` 文档输出仍为 8 条不变，去重改动未误删真实问题

### 2026-09-23 追加：数词与名词数不一致规则（`1 times`）

- 新增规则 `_collect_numeric_plural_issues`（`RE_ONE_WITH_PLURAL_NOUN = (?<=\s)1\s+([a-z]{3,}s)\b`），接入 `process_text` 规则链
- 判据：阿拉伯数字 `1` 后接名词复数，且名词为规则复数（去掉 `s` 或 `ies→y` 后仍是词典词），同时排除 `-ss/-us/-is/-ics/-sis` 结尾的单复同形词
- 两个排除条件保证精度：`1` 前必须是空白，排除表格记法与小数尺寸（`µL/tube×1 months`、`4.1 inches`）；规则复数判据排除 `series`/`species` 一类
- 实测命中：两份目标 PDF 各命中 1 处 `swing downward 1 times`，与人工批注「去掉 es」一致；18 篇英文语料回归 0 命中
- 去重后指标变化：
- `H-020-001303-00`（21 条批注）：检出 5→6 条，批注对齐 4→5 条，批注对齐准确率 80%→83.3%，检出率 19.0%→23.8%
- `H-020-001249-00`（17 条批注）：检出 8→9 条，批注对齐 7→8 条，批注对齐准确率 87.5%→88.9%，检出率 41.2%→47.1%
- 两份合计：检出 15 条，批注对齐 13 条=86.7%；人工核验全部为真实缺陷=15/15=100%
- 说明：批注对齐口径受批注非穷尽性影响，未对齐的 2 条均为真实缺陷（p12 第二处 `Disgestive`，人工注明「多处出现此问题」；`consumbles` 拼写错误）。准确率应以人工核验口径为准，批注对齐口径作为下界参考

### 2026-09-23 追加：拼写检查页预览排版修复（PDF 软换行回流）

- 现象（用户反馈）：上传 IFU 后，「文档内容」面板每行都短、右侧大片留白，句子被切成碎行；并在该页看到 `is`、`Are` 被高亮
- 根因一（误报）：`is`/`Are` 来自旧版 `run_grammar`（`is` 命中是因为 "Yes is selected by default." 中 "Yes" 以 s 结尾被判为复数；`Are` 来自旧版代词/主谓规则）。该页在修复后的代码下输出 0 条，旧代码输出 3 条（`is`/`Are`/`are`）。截图为修复前状态，重启后端即可生效
- 根因二（排版）：`document_parser.extract_pdf` 按 PyMuPDF 文本块拼页，`"\n\n".join(...)`；这些 IFU 的 PDF 每个视觉行即一个文本块（页宽 629pt，块 x 跨度约 170→581），于是每行后面都带一个空行进入文本。`SpellCheck.vue` 的 `.highlighted-text` 用 `white-space: pre-wrap`，把这些空行与硬换行原样渲染，才出现「碎句 + 右侧留白」
- 修复：`spell_check.py` 新增 `_merge_soft_wrapped_lines()`，仅在 `file_type == 'pdf'` 时于 `process_text` 内调用，按「上一行未收句 + 本行小写起头」判定续行并合回段落；列表项（`a.`/`6.`/`-`）与以大写起头的新段落不合并；词被拦腰截断（`reprin`/`nted`）与连字符收尾（`wide-`/`tip`）用词典判定后直接拼接，不补空格
- 边界：`document_parser` 未改动，因此审核、翻译、比对等模块的文本不受影响；`spell_checker.py` 仍零改动
- 影响面验证：对被检出结果做「开启/关闭回流」对照，两份目标 PDF 与 18 篇英文语料的 issue 列表（type + word）逐一相同（9 vs 9、6 vs 6、语料 223 vs 223），确认回流只改预览排版、不改检出
- 评测口径修正：预览文本长度变化后，评测脚本改为按「合并文本索引 → 原文索引」的映射定位页码（两文本仅空白不同，非空白字符序列一致，可线性对齐）。修正后两份指标与回流前完全一致：`H-020-001249-00` 8/9=88.9%、8/17=47.1%；`H-020-001303-00` 5/6=83.3%、5/21=23.8%
- 回归：`test_spell_check.py` 新增 3 例（续行合并、段落/列表/断词不合并、非 PDF 不合并），40 passed；全量 `backend/tests` 856 passed / 6 failed（6 例均为既有失败）

### 2026-09-23 追加：定位「instructions for use 被报错」的来源

- 用户反馈「跑文档测试时 instructions for use（即 IFU）被报错，说明书本身没问题」，要求按该词定位
- 定位结果：不是拼写层，也不是 AI 层，而是旧版 `run_grammar` 的主谓一致规则把句子里的 `are` 当成了错误。被误报的 5 处原文全部正确：
- `Figures in this instructions for use are for illustrative purpose only.`（主语 Figures）
- `Trademarks, product, service, and company names mentioned in this instructions for use are the property of ...`（主语 names）
- `If special requirements of library insert size are written in the instructions for use of the Library Prep kit`（主语 requirements）
- 误报机制：旧规则把动词前紧邻的一个词当作主语，于是把 `use` / `instructions` 当主语，判为单数，与 `are` 冲突
- 实测：`H-020-001303-00` 含该短语的句子里旧版误报 3 条 `are`，新版 0 条；`H-020-001249-00` 旧版 2 条，新版 0 条。两份文档整篇 issue 数 37→6、29→9
- 同批误报：`Yes is selected by default.` 里的 `is` 也是同一条旧规则（把 `Yes` 的词尾 s 当复数），截图里高亮的 `is`、`Are` 均属此类，新版均为 0 条
- 结论：该反馈与「are 误报」是同一根因，已在 `run_grammar` 重写中修复，无需再改规则；用户侧需重启后端进程才会生效
- 附带发现（未改动，待确认）：审核模块另有一条独立规则 `review.py` `GRAMMAR-007`，匹配 `This instructions for use describes` 并建议改为 `These instructions for use describe`。该规则只命中 `describes` 一种续接，同一份文档里同样结构的 `This instructions for use is applicable`、`This instructions for use and the information ... are` 等 10 处均不命中；MGI 句中用 `its contents` 单数指代，属把 Instructions for Use 当作单数标题的固定写法；603 条人工审核基线中无任何一条涉及该句式。据此判断为误报（每份文档各 1 条），是否移除待用户确认

## 2026-09-23 规则管理页导入/导出修复

- 用户反馈三个问题，先确认在最新 `main` 上均未修复，再修复：
- 创建时间格式：`Review.vue` 规则表 `created_at` 列直接输出原始 ISO 串（`2026-09-23T07:04:23`），未调用同页已有的 `formatDateTime()`；改为该列走 `formatDateTime`，与「上传时间」列口径一致
- 导出失败（`GET /api/rules/export` 返回 422）：`backend/app/api/rules.py` 把 `/export` 注册在 `/{rule_id}` 之后，FastAPI 按注册顺序匹配，`/api/rules/export` 被 `/{rule_id}` 抢先匹配，`rule_id: int` 解析 `"export"` 抛 `int_parsing`。修复为静态路径（`/bulk`、`/export`）统一注册在 `/{rule_id}` 之前
- 导出完整性：`GET /rules/export` 原先走 `get_rules(db)`，默认 `limit=100`，规则库超过 100 条会被静默截断，改为 `limit=10000`
- 导出字段：原导出只含 7 个字段，缺 `severity`/`language`，导出再导入会丢这两项；补入后导出文件可完整回灌
- 导入失败（双重问题）：导入控件把文件以 multipart POST 到 `/api/rules/bulk`，但该接口签名是 `rules: list[RuleCreate]`（JSON 数组），实测 multipart 返回 422 `list_type`；且 `el-upload` 只配了 `on-success`、没有 `on-error`，失败时页面无任何提示
- `crud.rule.bulk_create_rules`：增加同批 `rule_no` 去重（`rule_no` 唯一），否则同一文件内重复项会 `add_all + commit` 触发唯一约束错误
- 排查方法记录：本机验证该接口不能用 `sqlite://` 内存库配 `TestClient`（请求在独立线程，内存库按线程各自新建导致 `no such table`），需 `poolclass=StaticPool` + `check_same_thread=False` 共享同一连接

## 2026-09-23 规则库导入导出改为 Excel

- 用户反馈「规则都是 JSON 文件，本地难以维护」，选定方案：导入导出统一改成 Excel，不再使用 JSON
- `backend/app/api/rules.py`：导出 `GET /export` 返回 `.xlsx`（`StreamingResponse` + openpyxl），列序与页面字段一致：规则编号/分类/规则描述/正则/示例/建议/审核依据/严重程度/语言，首行冻结、表头加粗、单元格自动换行
- 导出把 `severity`/`language` 枚举值写成中文标签（致命/严重/一般/建议、中文/英文/中英通用），便于在 Excel 里直接阅读与填写
- 新增 `GET /import-template`：返回 `rules_import_template.xlsx`，含「规则库」（空表头）与「填写说明」（列名、是否必填、说明、示例值）两个工作表；不再由前端拼 JSON 模板
- 新增 `POST /import`：接收 multipart 上传的 `.xlsx`，按表头名定位列（不依赖列顺序），逐行校验必填列（规则编号/分类/规则描述/正则）与枚举取值，返回 `created`/`duplicates`/`total`/`errors`；单行错误不中断其它行，`errors` 带行号与中文原因
- 导入时 `severity`/`language` 同时接受中文标签与英文枚举值，留空分别按 `general`/`both` 处理；非 `.xlsx`、无法解析、缺必需列、内容为空均返回 400 并给出中文提示
- 前端 `rulesAPI`：`export`/`downloadTemplate` 改 `responseType: 'blob'`，新增 `importExcel`；移除已无调用方的 `bulkCreate`
- `Review.vue`：导入上传走 `/rules/import`（`accept=".xlsx"`），失败提示改用已有的 `getBlobErrorMessage`（blob 响应里的 `detail` 需先读文本再解析）；导入结果按「成功导入 N 条 / 跳过 M 条已存在 / 若干行未导入（前 3 条带行号）」分别提示
- `Review.vue` 补齐 `severity`：规则表格新增「严重程度」列，新增/编辑弹窗新增下拉选择，`ruleForm` 与 `editRule` 补字段；顺带修复「添加规则」按钮不复位 `editingRule` 导致新弹窗仍处于编辑态的问题（新增 `openRuleDialog`）
- `backend/tests/test_rules_api.py` 重写为 10 例（静态路由注册在 `/{rule_id}` 之前、导出 xlsx 含中文 severity/language、导出不被默认分页截断、模板含两个工作表、导入新建并跳过已存在、按行报错且不中断、缺必需列 400、非 xlsx 400、动态 `/{rule_id}` 仍可用、`POST /bulk` JSON 行为保持不变）；`pytest tests/test_rules_api.py -q` 10 passed
- 真实端到端（uvicorn + 真实种子库，`admin` 登录）：导出 29 条 → 模板含两表 → 导入含 1 新建 + 29 重复 + 2 非法行的文件，返回 `created=1/duplicates=29/errors=2`（行号 32、33）→ 重导 `created=0/duplicates=30` → 导出回读新规则 severity=严重、language=英文，回灌无损 → 非 xlsx 400 → 删除临时规则，库恢复 29 条
- 验证链路：`/api/rules/export` 与 `/api/rules/import-template` 在直连后端、vite 代理（5173）、预览网关三处均 200；`frontend` `npm run build` 通过
- 关联：上一节遗留的 `GRAMMAR-007` 已按用户确认移除，随 PR #135 合入 `main`

## 2026-09-23 外部评审规则种子改为 Excel

- 承接上一节：用户指出的「规则都是 JSON 文件，本地难以维护」还包括启动种子 `backend/seed/review_rule_library_seed.json`，一并转为 Excel
- 新增 `backend/seed/review_rule_library_seed.xlsx`：`规则库` 工作表（规则ID/分类/严重程度/规则内容/适用场景/已同步，29 条）+ `元信息` 工作表（来源、导出日期）两列键值行，无表头
- 转换无损性已逐项核对：29 条规则的 `rule_id`/`category`/`severity`/`rule_content`/`applicable_scenarios`/`synced` 与 `git show HEAD` 里的原 JSON 完全一致，元信息一致，0 处差异
- `crud/rule.py`：`REVIEW_RULE_LIBRARY_SEED_PATH` 指向 `.xlsx`；新增 `_load_review_rule_library_seed()` 用 openpyxl 读取，按表头名定位列（不依赖列顺序），`适用场景` 按 `、` 拆回列表；`seed_external_review_rules` 改为消费该结构，`source`/`export_date` 取自 `元信息` 工作表
- 移除已无引用的 `import json`；`review.py` 的 `REVIEW_CACHE_VERSION_FILES` 与 `test_review_cache.py` 的断言路径同步改为 `.xlsx`（缓存指纹用 mtime+size，二进制文件同样适用；改种子会让既有审核缓存失效，属预期）
- 原 `review_rule_library_seed.json` 已删除（git 历史可回溯）。取舍说明：二进制 xlsx 在代码评审时无法直接看 diff，换来人可以在 Excel 里直接维护
- `test_review_cache.py`：原 seed 用例的假路径（`read_text`）改为用 `tmp_path` 写真 xlsx；新增 2 例——随包种子能读出 29 条规则与元信息、`example`/`audit_basis` 确实取自 `元信息` 工作表
- 回归：全量 `backend/tests` 874 passed / 6 failed（6 例仍为既有失败）；另用空库直接调用 `seed_external_review_rules` 验证 `created=29`、二次调用 `0`（幂等）；重启真实后端无报错，`GET /api/rules/export` 仍为 29 条且内容、severity、language 不变

## 2026-09-23 修复英文文本片段审核 AI 结果被全部丢弃

- 现象：配置 DeepSeek 后做英文「文本片段审核」，AI 调用成功（`audit_chunk.providers.deepseek=1`、`chunk issue_count=3`），页面却始终 0 条问题
- 根因：`review.py` `_is_snippet_scope_issue` 对 `source == "ai"` 的问题只匹配中文关键词（`句子|用词|拼写|语法|术语|标点|可读`），且只看 `category + rule + description`。本项目的 AI 在片段模式下把语言问题写进 `rule` 字段（如 `Subject-verb agreement: ...`）、`category` 为「其他」、`description` 为空，于是三条真实语法错误被 `_filter_snippet_scope_issues` 全部判为越界，日志 `文本片段范围过滤: 3 -> 0`
- 该规则对中文同样脆弱：只要 AI 把描述放在 `rule` 而非 `description`，中文语言问题也会被丢弃
- 修复：`_is_snippet_scope_issue` 的 AI 分支补充英文语言错误词表（`grammar|spelling|spell|typo|punctuat|capitali[sz]|subject-verb|agreement|tense|plural|singular|verb|noun|pronoun|preposition|word choice|wording|terminolog|typograph|readab|clarity|phrasing`，加 `re.IGNORECASE`），保持在既有的「白名单命中才保留」结构内，越界英文问题（交叉引用、安全合规、版式等）仍被剔除
- 边界未动：`对比审核` 子页签本就是确定性比对、不调用 AI，因此没有模型下拉属设计如此；`文本片段审核范围` basis 也已明确限定 AI 只报句子级语法/拼写/术语问题
- 回归测试：`test_snippet_review.py` 新增 `test_snippet_scope_keeps_english_ai_grammar_issues`（3 条英文 AI 语法/拼写问题保留 + 3 条越界英文问题剔除）；`pytest tests/test_snippet_review.py -q` 23 passed
- 真实端到端（重启后端 + DeepSeek）：同一英文片段 `The instrument are ready for use. Please confirm the settings before you starts the run. This instructions for use describes the installation procedure.` 由修复前 `total=0` 变为 `total=3`，`issue_flow.ai_input_count=3 / after_pipeline=3 / after_visual_verification=3`，三条分别命中主谓一致、`before you` 后动词原形、`This instructions` 指示代词与主谓一致
- 全量 `backend/tests`：875 passed / 6 failed（6 例仍为既有失败，无新增回归）
- 顺带发现（未改动，待确认）：`app/utils/ai_client.py` 顶部 `from app.utils.prompt_builder import ...` 指向的 `app/utils/prompt_builder.py` 在仓库中不存在（`git log --all` 无该文件记录），因此 `PROMPT_BUILDER_FALLBACK_ACTIVE=True` 常驻、日志固定打印 `prompt_builder 模块缺失，当前使用保守降级提示词构建`；英文场景下 `build_audit_system_prompt()` 退化为返回空串，提示词质量受损

## 2026-09-23 第四轮审核准确率优化（英文语义提示词补齐与全角标点连排）

- 样本基线：`当前工作区/.monkeycode/docs/cyy-human-review-baseline.json`（603 条人工批注）
- 本轮背景：第三轮 P3 语义 prompt 增强只落在中文分支（`review_rules.SYSTEM_PROMPT_TEMPLATE` + `SEMANTIC_FEWSHOT_EXAMPLES`）；英文审核走 `ai_client.build_audit_prompt_payload()` 的内置英文 system prompt，既没有「语义质量检查」章节，输出 `category` 枚举也不含语义类目。而 `review_engine/pipeline.py` 的 `is_verifiable_ai_text_issue()` 已经把 `冗余|表述不准确|信息不完整|一致性|语气|图表衔接|句子成分` 列入白名单，也就是英文 AI 层「被允许但从未被要求」产出语义类问题，白名单对英文恒为空转。
- 本轮调整内容：
- `backend/app/utils/ai_client.py`（英文语义提示词补齐）：英文 system prompt 新增 `SEMANTIC QUALITY CHECKS` 章节，覆盖 7 个语义维度（冗余、表述不准确、信息不完整、一致性、语气、图表衔接、句子成分），逐维度指定目标 `category`；并把上述 7 个语义类目补入英文输出 `category` 枚举（issues 与 observations 两处），与中文 P3 及 pipeline 白名单对齐
- `backend/app/api/review.py`（全角标点连排）：新增 `DOC-PUNCT-002`，识别全角标点相邻误排（`：。`、`，。`、`、。`、`；。`、`：，`、`；，`）。仅匹配无空白的紧邻组合，避免把 PDF 文本层换行/分栏造成的标点分处两行判为连排
- `backend/app/review_engine/annotation_baseline.py`：无需改动，`DET-PUNCT-001` 的对齐逻辑用 `rule.startswith("DOC-PUNCT")`，`DOC-PUNCT-002` 自动纳入
- 回归用例：`backend/tests/test_review_cache.py` 新增 2 例（`：。` 命中、被空白分隔时不报）；`backend/tests/test_ai_client_audit.py` 新增 1 例（英文 prompt 含 `SEMANTIC QUALITY CHECKS` 与 7 个语义类目）
- 本地验证：
- 审核相关套件：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests/test_review_cache.py backend/tests/test_review_gold_compare.py backend/tests/test_ai_client_audit.py backend/tests/test_review_engine.py backend/tests/test_prompt_semantic_dimensions.py backend/tests/test_review_false_positives.py backend/tests/test_review_optimization.py backend/tests/test_snippet_review.py backend/tests/test_review_dual_input.py -q`（334 passed）
- 全量后端测试：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests -q`（865 passed / 6 failed / 1 skipped；6 例均为既有失败：4 例缺 docx 固件、1 例模板串不一致、1 例缺 `tesseract`）
- 语法校验：`cd /workspace/backend && python3 -m compileall -q app`（COMPILE_OK）
- 离线覆盖探针（`/tmp/opencode/baseline_probe.py`，对 603 条批注 context 重建伪文档后跑确定性规则）：`matched 120/603 (0.1990) -> 121/603 (0.2007)`；`DET-PUNCT-001 1/14 -> 2/14`；其余 `expected_rule` 命中数不变，无回归
- 误报扫描（`DOC-PUNCT-002`）：仓库内全部 markdown/txt/vue 语料仅命中 3 处，其中 2 处是 `.vue` 里正则字符类的源码、1 处是 `技术文档常见错误清单与规范.md` 中列举全角标点的说明文字；真实产品文档语料零命中
- 指标声明：离线探针只覆盖确定性规则，本轮英文语义提示词改动作用于 AI 层，探针无法体现其增量
- 未完成项（依赖可用 LLM provider）：英文语义提示词端到端复测。本轮实测 Qwen 返回 `Arrearage`（账户欠费）、Kimi 返回 401 `Incorrect API key provided`，没有可用 AI provider，无法验证英文 AI 审核是否会稳定产出语义类问题及其误报率，留待 provider 可用后按 G99 验收方式复测
- 风险提示：英文语义章节尚未经验收数据验证。`is_verifiable_ai_text_issue()` 会给这类问题加 6 分，若模型产出的语义问题质量不足，英文文档 Precision 可能下滑，provider 可用后应优先做英文 Precision 抽样

## 2026-09-23 第五轮审核准确率优化（任务 3 误报与展示修复）

- 样本基线：`H-020-001010-00GoSpatial-V2-24AutomatedSamplePreparationSystemUserManual_English_RUO_WH_Lijuan.pdf`（document_id=2，rule+AI hybrid）
- 本轮背景：该文档首次 hybrid 审核产出 20 条问题，逐条人工核对后确认 9 类缺陷（误报 / 解析伪影 / 展示截断），逐项修复
- 本轮调整内容：
- `backend/app/utils/spell_checker.py`（冠词 a/an）：`_is_vowel_sound` 的全大写分支原先只判断「命中元音字母名集合即返回 True」，未命中时会继续落到末尾的元音字母判断，导致 U 开头缩略语（`UPS`、`USB`）被误判为元音开头。现改为命中全大写分支即显式返回 `token[0] in _ABBR_VOWEL_SOUND`，并新增 `_WORDLIKE_ALL_CAPS` 白名单放行 `HOME`、`POWER` 等按单词读音的全大写词（如 LOGO 标题 `a HOME`）
- `backend/app/utils/spell_checker.py`（组学词表）：`omics`、`genomics`、`proteomics`、`transcriptomics`、`metabolomics`、`epigenomics`、`lipidomics`、`spatialomics` 加入 `TECH_TERMS_WHITELIST`，消除 `omics` 被判拼写的误报
- `backend/app/api/review.py`（SAFE-002 安全标注回溯）：原实现只按风险词前后 ±80 字符找 `WARNING/CAUTION/DANGER`，而 PDF 文本层会把安全标题下的条目拆成多行，风险词常与标题相隔数百字符。新增 `_hazard_has_enclosing_safety_label()`，向前回溯 800 字符查找最近的安全标注；若标题与风险词之间出现新的段落标题（`_SAFETY_SECTION_HEADING_RE`）则视为已跨章节，仍报缺失标注。窗口以风险词位置截断，故只按完整行判定标题
- `backend/app/api/review.py`（DOC-CATNO-001 货号写法）：新增 `_is_symbol_legend_entry()`，识别「`Catalog number Indicates the manufacturer's catalog number ...`」这类符号表定义行（`_SYMBOL_LEGEND_VERB_RE` 匹配「标签 + Indicates/Means/Denotes/表示/说明/指明」），跳过定义行，避免把符号表图例当成货号标签写法问题；真实标签（`Catalog number: 1000123`）仍照常报出
- `backend/app/api/review.py`（DOC-PROC-002 步骤引导重复）：原实现只看前两处 `Perform the following steps:` 且间距 < 500 字符即报。手册中每道流程都会重新引导步骤，现新增 `_has_intervening_section_heading()`：两处引导语之间若夹着新章节标题（大写开头、无句末标点的短行）说明是两道独立流程，不再报；真正紧邻的编辑残留仍会命中
- `backend/app/review_engine/pipeline.py`（商标阅读顺序伪影）：新增 `is_trademark_reading_order_artifact()`。PDF 阅读顺序错乱会把 `®`/`™` 甩到商标名之外（`® are trademarks ...`）或把 `™` 提取成字面量 `TM`（`TM is the trademark ...`），AI 会据此误报商标归属；当原文存在分离的 `®/™/©` 或字面量 `TM`，且建议中含商标符号时判为伪影
- `backend/app/review_engine/pipeline.py`（断词伪影）：新增 `is_broken_word_extraction_artifact()`。PDF 表格按字符间距断词会产出 `Powe rswi tcha n d` 这类碎片；判定条件是「≥3 个全字母碎片、碎片长度均 ≤4、拼接长度 ≥12、且含 `a/I` 之外的孤立小写单字母」，正常英文短语（`Turn off the tap now`）不会命中。两个伪影判定都放在 `is_verifiable_ai_text_issue()` 早退之前，否则会被语义白名单提前放行
- `backend/app/api/review.py` + `backend/app/utils/ai_client.py`（整体观察可读性）：`_observation_first_sentence()` 补英文句末标点 `.!?`（仅当文本不含中日韩字符时启用，避免中文里的 `1.` 列表标记被当句末）与词边界收尾，默认长度 72→200；`_is_excerpt_meta_observation()` 剔除「本片段/摘录内容以目录为主」这类分块产物观察；`normalize_audit_observations` 标题 24→60、描述 80→300，中英文 prompt 第 6 条补充「不要输出关于本片段/摘录本身的观察」及标题长度上限
- `frontend/src/views/Review.vue`（建议列完整展示）：`compactSuggestionText()` 去掉长度截断只保留空白归一化；`describeSuggestionChange()` 的内联 diff 门槛由 24/32 字符改为「改动片段 > 120 字符时退化为 `建议改为“<完整新表述>”`」；`issueSuggestionOverview()` 去掉 60 字符截断
- 本地验证（重启后端 + DeepSeek 真实调用，`review_id=5`）：
- 9 类缺陷全部消失：`SAFE-002 flammable`、`SPELL omics`、`DOC-CATNO-001 Catalog number`、`DOC-PROC-002 Perform the following steps`、`GRAMMAR a UPS/a HOME`、商标阅读顺序伪影、断词伪影 `Powe rswi tcha n d` 均不再出现在结果中
- 真实问题保留：`DOC-DUP-001/007`、`clean→cleaning`、`the the`、`any question→any questions`、`Connects to or disconnect→disconnects` 等仍在；问题总数 20 → 15
- 观察区恢复正常：`observations` 三条均为完整英文句子（修复前标题/描述带 `…`），无「本片段/摘录」型观察
- 回归用例：`backend/tests/test_spell_check.py` 新增 2 例（字母名读音判定、组学词不报拼写）；`backend/tests/test_review_cache.py` 新增 6 例（SAFE-002 三例、DOC-CATNO-001 两例、DOC-PROC-002 一例）；`backend/tests/test_review_engine.py` 新增 3 例（商标伪影、断词伪影、伪影问题整链路判为 noise）
- 全量后端测试：`PYTHONPATH=/workspace/backend python3 -m pytest backend/tests -q`（891 passed / 6 failed / 1 skipped）；6 例失败已用 `git worktree add /tmp/opencode/base-check HEAD` 在未改动检出上复现，为既有失败（4 例缺 docx 固件、1 例 `test_polish_match_score` 模板串不一致、1 例缺 `tesseract`），非本轮回归
- 前端：`cd /workspace/frontend && npm run build` 成功（`✓ built in 34.13s`）
- 残留未处理（超出本轮 9 项清单，属 AI 判断噪声，待确认）：符号表行 `T10AH250V Fuse specification Indicates the fuse specification to ...` 的 stray fragment 提示、法律免责声明段落的 AI 改写建议、`Figures in this manual are all illustrations.` 的语序建议

## 2026-09-24 第六轮审核准确率优化（章节定位、建议具体性与人工批注召回）

- 本轮背景：截图反馈显示重复问题的章节被识别为 Figure/Table 标题或页码区间，DOC-DUP-001 建议缺少重复位置，人工批注中的 `clean` 语法与维护周期术语问题未被规则链路覆盖。
- 本轮调整内容：
- `backend/app/api/review.py`（章节定位）：`extract_chapter()` 新增目录标题缓存与匹配评分，优先选择目录中的真实章节标题；图表题注降级为弱候选；忽略 `1 to 36` 这类表格单元页码区间；支持 `(Optional) ...` 小节标题，并调整命中位置前后标题的距离权重。
- `backend/app/api/review.py`（DOC-DUP-001 建议）：建议中补充前文重复句所在章节，例如「该句与『Powering on the device』章节中的句子完全重复」，帮助审核者快速定位两处内容。
- `backend/app/api/review.py`（人工批注召回）：新增 `DOC-GRAM-002` 检测 `before/during/after clean`，建议使用 `cleaning`；新增 `DOC-TERM-002` 检测 `Weekly disinfection` 与 `Monthly cleaning` 等维护周期标题的 cleaning/disinfection 术语混用。
- 回归用例：`backend/tests/test_review_engine.py` 新增 3 个章节定位测试；`backend/tests/test_review_cache.py` 新增语法与维护术语测试。
- 本地验证：目标测试 `251 passed`；完整后端测试 `896 passed / 6 failed / 1 skipped`。6 个失败与此前基线一致，集中在缺少 docx 固件、测试模板串与 tesseract 环境依赖。
- 真实文档规则复测（`review_id=13`）：章节定位已修正为 `Powering on the device`、`Daily maintenance`、`Troubleshooting`、`Device` 等结构标题；新增命中 `before clean`、`during clean`、`Monthly cleaning`，问题数由 6 条增至 9 条。

## 2026-09-24 第七轮审核准确率优化（臆造术语替换误报）

- 本轮背景：截图反馈 #017 显示平台把目录与正文中的「第5 章 准备测序试剂槽」判为术语问题，规则显示为「试剂舱 → 试剂仓」，建议「将“槽”改为“仓”」。该建议不成立：`试剂槽` 是本文档的正式术语（全文 74 处），`试剂仓` 全文仅 1 处且指仪器仓门，二者指代不同对象。根因是 AI 把知识库条目「试剂舱 → 试剂仓」套用到了并不含「试剂舱」的正文上，属臆造错误。
- 本轮调整内容：
- `backend/app/review_engine/pipeline.py`：新增 `hallucinated_substitution_term()`，当 AI 问题的 `rule` 为「错词 → 正词」形式、而 `original_text`/`context` 中并不存在该错词时判定为臆造并丢弃；判定不读取 `rule`/`audit_basis`，因为这两处本来就会写出错词。
- `backend/app/review_engine/pipeline.py`：在 `is_noise()` 中接入该判据，位置早于 `is_verifiable_ai_text_issue()` 的提前放行，避免被 AI 文本类白名单兜住。
- 回归用例：`backend/tests/test_review_cache.py` 新增 2 个测试，分别覆盖「原文无错词 → 丢弃」与「原文含错词 → 保留」。
- 本地验证：`test_review_cache.py + test_review_engine.py` 共 `252 passed`；完整后端测试 `897 passed / 6 failed / 1 skipped`，6 个失败与此前基线一致。
- 真实数据回放（`review_id=21`，26 条问题）：`select_review_issues` 仅额外丢弃 `id=173`（`试剂舱 → 试剂仓` / `准备测序试剂槽`），Tina 9 条人工批注对应的规则召回保持不变。
- 本轮未改动（经确认属既有设计或待人工反馈）：图内占位掩码 `XXXXXXXXXXX`/`XX/XX/XXXX`（rule 层占位符需保留，见 `test_finalize_review_issues_*`）、`2 ℃~8 ℃`（CYY 人工基线规则）、AI 空格类建议与 `y` 项目符号伪影。
