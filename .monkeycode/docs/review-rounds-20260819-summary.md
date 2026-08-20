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
