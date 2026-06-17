# STUM\-TT004：Stereo-seq转录组FFPE套装用户手册

# **STOmics**

# **STEREO\-seq转录组FFPE套装用户手册**



**目录号：211SN114（4反应）/ 211SN114\-CG（4反应）**

**试剂盒版本：V1.0**

**手册版本：B\_2**

STUM\-TT004

---

修订历史

| 手册版本 | 试剂盒版本 | 日期 | 描述 |
|---|---|---|---|
| A | V1.0 | 2024年7月 | - 首次发布。 |
| B | V1.0 | 2024年10月<br> | - 修正了试剂准备表中的小错误。<br>- 更新了组织荧光染色液的计算总量。<br>- 对语言进行了整体细微的一致性修订。<br>- 更新了暂停点描述。 |
| B\_1 | V1.0 | 2025年7月<br> | - 增加了仅限美国使用的目录号。<br>- 调整了文档超链接以提高可访问性和用户体验。<br>- 更新了STOmics试剂和芯片的储存及运输温度。<br>- 更新了对PE001的引用，并注明即将被PE002替代。 |
| B\_2 | V1.0 | 2025年10月 | - 更新了Stereo-seq芯片玻片的储存温度。 |

**注意：请下载最新版本的手册，并与相应的Stereo-seq转录组N试剂盒配合使用。**



©2025 深圳华大生命科学研究院，版权所有。

1. 本产品仅限研究使用，不适用于诊断程序。
2. 本手册内容可能全部或部分受到适用的知识产权法律保护。深圳华大生命科学研究院和/或相应权利主体依法拥有其知识产权，包括但不限于商标权、版权等。
3. 深圳华大生命科学研究院不授予或暗示任何使用我们或任何第三方版权内容或商标（注册或未注册）的权利或许可。未经我们书面同意，任何人不得未经授权使用、修改、复制、公开传播、更改、分发或发布本手册的程序或内容，不得使用该设计或使用设计技巧来使用或占有我们或我们关联公司的商标、标识或其他专有信息（包括图像、文本、网页设计或形式）。
4. 本文包含的任何内容均无意于且不应被解释为对本手册所列或所述任何产品性能的任何明示或暗示保证。适用于本手册所列任何产品的任何及所有保证均在购买该产品时随附的适用销售条款和条件中规定。深圳华大生命科学研究院对本手册所述任何第三方产品或方案的使用不作任何保证，并特此免除任何及所有相关保证。

---



# **工作流程**

![图片](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MTY5NzNiY2ZiZjQ2YjRhOTg2OWIyMDU5ZjAyODk4NjlfNzc2MmVlYWJiMmEwOGUxMGRhOTg1OWY5MTY2YTkzMGZfSUQ6NzM5MTMyNTQ0MzY4Mjc5NTUyMV8xNzgxNjU4OTU2OjE3ODE3NDUzNTZfVjM)

![图片](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZWVkZGU1YmQ5NjJkMDAzNzk3NTgxZmJiZmU3MGYzYzNfNjcxY2ZiMmNiMGZiNzIxZDUyOTRlNzE0ZjIzZDBiNDNfSUQ6NzQzMDc2MTI1MjUyMTc3MTAxMF8xNzgxNjU4OTU1OjE3ODE3NDUzNTVfVjM)

# 第1章：引言

## 1.1 预期用途

STOmics Stereo-seq转录组FFPE套装旨在从福尔马林固定石蜡包埋（FFPE）生物组织切片中生成空间分辨的总RNA文库。基于DNA纳米球（DNB）技术，STOmics Stereo-seq转录组FFPE套装通过*原位*捕获整个转录组，提供从组织到数据的解决方案，具备纳米级分辨率和厘米级视场。本试剂盒使用随机引物进行RNA*原位*捕获。每个从特定位点捕获的RNA合成的cDNA均与其空间条形码探针连接，从而允许在测序并使用StereoMap可视化平台进行可视化分析后，进行组织切片的基因表达图谱绘制。

本试剂盒提供的所有试剂均通过严格的质量控制和功能验证，确保性能稳定性和重现性。

## 1.2 测序指南

使用Stereo-seq转录组套装制备的测序文库需要配合DNBSEQ测序平台使用。有关详细信息，请参阅[**Stereo\-seq OMNI FFPE文库制备用户手册（文档编号：STUM\-LP001）**](https://c8h5lvcitj.feishu.cn/docx/Twg3dvxeSoGSV7xOyTLcXiKLnAd)

用于Stereo\-seq分析工作流程生物信息学管线的Stereo\-seq FFPE转录组文库所需输入参数如下：

`--kit-version`= 'Stereo\-seq N FFPE V1\.0'

`--sequencing-type` = 'PE75\_25\+59'

或 `--sequencing-type` = 'PE75\_25\+62'（适用于SAW v8\.1\.3及以上版本）

## 1.3 试剂盒组分清单

每套Stereo\-seq转录组FFPE套装包含：

- Stereo-seq转录组N试剂盒 V1.0 \*1（4反应）

- Stereo-seq芯片N玻片（1厘米 \* 1厘米）\*1（4片）

- STOmics FFPE辅助试剂盒 \*3

Stereo-seq 16反应文库制备试剂盒不包含在Stereo-seq转录组FFPE套装中，需另行购买。如需自行构建Stereo-seq FFPE转录组文库，请参考[**STUM\-LP001 Stereo\-seq OMNI FFPE文库制备用户手册**](https://c8h5lvcitj.feishu.cn/docx/Twg3dvxeSoGSV7xOyTLcXiKLnAd)了解详情。

![图片](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MGQyNTg5YzA4NTVmY2VjMWM2NjI2NmUzODNhZWNlNDBfOTFmNDVkMzhhMzVmOGFlNWY4ZTc5N2Q3MjRkZmM0MWZfSUQ6NzM5MTMyODMyMzE5ODk1OTYxN18xNzgxNjU4OTU2OjE3ODE3NDUzNTZfVjM)

兼容辅助但未包含在内：

- Stereo-seq PCR适配器 \*1（2个）

![图片](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=OWYyMDNlYWE2ZWU3ZDU5YTEzOTBlZmI2NDkwYWI1MWZfMWE2MGQ5OWJkZGEyNGUwYjM2YmNiYmI4MmNjMzU0MDZfSUQ6NzM5MTMyODM5NjYzMjA4MDM4NV8xNzgxNjU4OTU1OjE3ODE3NDUzNTVfVjM)

目录号、试剂盒组分及规格列于下表（表1-1至表1-4）。

**注意：收到Stereo-seq芯片N玻片（1厘米\*1厘米）后，请按照[**Stereo-seq芯片玻片接收、处理与存放操作指南**](https://enfile.stomics.tech/Stereo-seq%20Chip%20Slide%20Operation%20Guide%20For%20Receiving,%20Handling%20And%20Storing.pdf)中的说明妥善保存未使用的Stereo-seq芯片N玻片。**

**产品性能仅在其有效期内得到保证。其正常性能的表现也取决于产品在适宜条件下的运输、储存和使用。**

表 1-1 Stereo-seq转录组N试剂盒组分

|**试剂盒**|**组分**|**试剂目录号**|**管盖颜色**|**数量（管）**|
|---|---|---|---|---|
|Stereo-seq转录组N试剂盒<br>目录号：211KN114 / 211KN114\-CG <br>|RI|1000028499|橙色|300 μL × 1|
||FFPE封片剂|1000047466|紫色|100 μL × 1|
||FFPE解交联试剂|1000047464|绿色|1725 μL × 2|
||PR酶|1000028500|红色|10 mg × 1|
||FFPE RT缓冲液混合物|1000047460|透明|700 μL × 1|
||FFPE RT Oligo|1000047461|透明|44 μL × 1|
||FFPE RT酶混合物|1000047462|透明|132 μL × 1|
||FFPE Dimer|1000047463|黄色|10 μL × 1|
||cDNA释放缓冲液|1000028512|黑色|1725 μL × 2|
||cDNA释放酶|1000028511|黑色|88 μL × 1|
||cDNA扩增混合物|1000028514|蓝色|220 μL × 1|
||FFPE cDNA引物混合物|1000047465|蓝色|36 μL × 1|
|储存温度：\-25°C \~ \-15°C<br>||运输温度：\-25°C \~ \-15°C<br>||有效期：参见标签|

![图片](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MmVmN2NkZjczNmEzN2FiOGI3OTQ0ZDE4ZmE3ZWIyZjhfZjFlYzEzOTQ3ZGM5YjdjMjZkZGNjOTY0ZGY5Y2U3NmZfSUQ6NzM5MjQyMjE3MDY1MzkwMDgwNF8xNzgxNjU4OTU1OjE3ODE3NDUzNTVfVjM)

表 1-2 Stereo-seq芯片N玻片