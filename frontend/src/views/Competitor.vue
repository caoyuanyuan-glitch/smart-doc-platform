<template>
  <div class="competitor-container">
    <!-- ================= 上传分析视图 ================= -->
    <div v-if="currentView === 'upload'">
      <h2 class="page-title">竞品文档分析</h2>

      <div class="panel">
        <div class="panel-header">
          <span>上传竞品文档或输入网页手册链接，自动识别编辑工具、分析可读性与体验三维度（可获得性 / 易查找性 / 可用性），并生成可执行的改进建议</span>
          <div class="panel-actions">
            <el-tag size="small" type="info">支持 PDF / DOCX / MD / TXT / HTML 链接</el-tag>
          </div>
        </div>

        <el-tabs v-model="inputMode" class="input-tabs">
          <el-tab-pane label="文件上传" name="file">
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :on-change="handleFileChange"
              :before-upload="() => false"
              accept=".pdf,.docx,.md,.markdown,.txt,.html,.htm"
              drag
              style="width: 100%;"
            >
              <div class="upload-box large">
                <el-icon style="font-size: 44px; color: #3b82f6; margin-bottom: 10px;"><UploadFilled /></el-icon>
                <div v-if="!selectedFile" class="upload-hint">
                  将竞品文档拖拽到此处，或点击选择文件
                </div>
                <div v-else class="upload-name">{{ selectedFile.name }}</div>
                <div class="upload-sub" v-if="!selectedFile">支持 PDF（含元数据工具识别）、Word、Markdown 纯文本、本地 HTML（适合 JS 渲染页面另存后上传）</div>
              </div>
            </el-upload>
          </el-tab-pane>

          <el-tab-pane label="网页链接" name="url">
            <div class="url-box">
              <div class="url-label">输入竞品网页版手册链接</div>
              <el-input
                v-model="sourceUrl"
                size="large"
                placeholder="https://example.com/manual.html"
                clearable
                @input="handleUrlInput"
              />
              <div class="upload-sub">适合官网手册、帮助中心、HTML 说明页。当前抓取单页正文内容。</div>
            </div>
          </el-tab-pane>
        </el-tabs>

        <div class="action-row">
          <el-button type="primary" size="large" :loading="analyzing" :disabled="analyzeDisabled" @click="doAnalyze">
            <el-icon><Search /></el-icon> 开始分析
          </el-button>
          <el-button size="large" @click="resetUpload">清空</el-button>
        </div>
      </div>

      <!-- 分析结果 -->
      <template v-if="detail">
        <div class="result-summary-grid">
          <div class="summary-card">
            <div class="summary-card-label">编辑工具识别</div>
            <div class="summary-card-value small" :class="toolOkClass">{{ toolSummary }}</div>
            <div class="summary-card-sub" v-if="toolMeta.pages">格式 {{ toolMeta.format }} · {{ toolMeta.pages }} 页</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-label">可读性综合评分</div>
            <div class="summary-card-value score">{{ readability.overall_score ?? '样本不足' }}</div>
            <div class="summary-card-sub">
              <el-tag v-if="readability.overall_score != null" :type="levelTagType(readability.level)" size="small">{{ readability.level }}</el-tag>
              <span style="margin-left: 8px; color: #64748b;">{{ readability.language === 'zh' ? '中文' : '英文' }}</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <span>分析结果</span>
            <div class="panel-actions">
              <el-button size="small" type="primary" :disabled="!reportMd" @click="downloadReport">
                <el-icon><Download /></el-icon> 下载 Markdown 报告
              </el-button>
              <el-button size="small" type="success" @click="goToCompare">
                <el-icon><Switch /></el-icon> 与我方文件对比
              </el-button>
              <el-button size="small" @click="resetUpload">重新分析</el-button>
            </div>
          </div>

          <el-tabs v-model="activeTab">
            <!-- 标签页一：结构化结果 -->
            <el-tab-pane label="结构化结果" name="result">
              <div class="result-body">
                <!-- 编辑工具识别 -->
                <h3 class="block-title">一、编辑工具识别</h3>
                <el-descriptions :column="2" border size="small" class="meta-desc">
                  <el-descriptions-item label="文档格式">{{ toolMeta.format || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="页数">{{ toolMeta.pages || 0 }}</el-descriptions-item>
                  <el-descriptions-item label="Producer">{{ toolMeta.producer || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="Creator">{{ toolMeta.creator || '-' }}</el-descriptions-item>
                  <el-descriptions-item v-if="toolMeta.source_url" label="来源链接" :span="2">
                    <a :href="toolMeta.source_url" target="_blank" rel="noopener noreferrer" class="source-link">{{ toolMeta.source_url }}</a>
                  </el-descriptions-item>
                </el-descriptions>

                <div v-if="tools.length" class="sub-block">
                  <div class="sub-title">识别到的工具</div>
                  <el-table :data="tools" size="small" border>
                    <el-table-column prop="name" label="工具" min-width="160" />
                    <el-table-column prop="category" label="类别" min-width="140" />
                    <el-table-column label="置信度" width="100">
                      <template #default="{ row }">
                        <el-tag :type="confidenceType(row.confidence)" size="small">{{ row.confidence }}</el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column prop="source" label="识别依据" min-width="220" show-overflow-tooltip />
                  </el-table>
                </div>

                <div v-if="fontSignals.length" class="sub-block">
                  <div class="sub-title">字体信号（佐证）</div>
                  <div v-for="fs in fontSignals" :key="fs.name" class="font-signal">
                    <el-icon style="color: #f59e0b; margin-right: 6px;"><MagicStick /></el-icon>
                    {{ fs.hint }}
                    <span class="font-signal-sub">（{{ fs.embedded ? '嵌入' : '未嵌入' }}）</span>
                  </div>
                </div>

                <!-- 结构统计（客观指标） -->
                <template v-if="structureStats">
                  <h3 class="block-title" style="margin-top: 24px;">二、结构统计（客观指标）</h3>
                  <el-descriptions :column="3" border size="small">
                    <el-descriptions-item label="页数">{{ structureStats.page_count ?? '—' }}</el-descriptions-item>
                    <el-descriptions-item label="章节数">{{ structureStats.heading_count ?? '—' }}</el-descriptions-item>
                    <el-descriptions-item label="图片数">{{ structureStats.figure_count ?? '—' }}</el-descriptions-item>
                    <el-descriptions-item label="表格数">{{ structureStats.table_count ?? '—' }}</el-descriptions-item>
                    <el-descriptions-item label="安全警告数">{{ structureStats.warning_count ?? '—' }}</el-descriptions-item>
                    <el-descriptions-item v-if="(structureStats.warning_symbol_count || 0) > 0" label="警告符号（文本层）">{{ structureStats.warning_symbol_count }}</el-descriptions-item>
                  </el-descriptions>
                  <div v-for="(note, i) in structureStats.notes || []" :key="i" class="dim-desc" style="color: #d97706;">
                    ⚠ {{ note }}
                  </div>
                </template>

                <!-- 可读性分析 -->
                <h3 class="block-title" style="margin-top: 24px;">{{ structureStats ? '三、' : '二、' }}可读性分析</h3>
                <div class="dim-list">
                  <div v-for="dim in dimRows" :key="dim.key" class="dim-row">
                    <div class="dim-head">
                      <span class="dim-name">{{ dim.label }}</span>
                      <span class="dim-value">{{ dim.score == null ? 'N/A' : dim.score }}</span>
                    </div>
                    <el-progress :percentage="dim.score || 0" :stroke-width="10" :color="scoreColor(dim.score)" :show-text="false" />
                    <div class="dim-desc">{{ dim.desc }}</div>
                  </div>
                </div>

                <div class="stats-row">
                  <el-statistic title="句子总数" :value="stats.sentence_count" />
                  <el-statistic title="平均句长" :value="stats.avg_sentence_len" :precision="1" />
                  <el-statistic title="平均段落长度" :value="stats.avg_paragraph_len" :precision="0" />
                  <el-statistic title="术语密度" :value="stats.term_density_pct" suffix="%" :precision="1" />
                  <el-statistic title="被动句比例" :value="stats.passive_ratio_pct" suffix="%" :precision="1" />
                </div>

                <!-- 问题例句 -->
                <template v-if="sampleGroups.length">
                  <h3 class="block-title" style="margin-top: 24px;">典型问题例句</h3>
                  <div v-for="group in sampleGroups" :key="group.key" class="sub-block">
                    <div class="sub-title">{{ group.label }}</div>
                    <div v-for="(s, i) in group.samples" :key="i" class="sample-line">
                      <el-tag size="small" :type="scoreColorTag(group.score)" effect="plain">第 {{ s.page || '?' }} 页</el-tag>
                      <span class="sample-text">{{ s.text }}</span>
                    </div>
                  </div>
                </template>

                <!-- 改进建议 -->
                <div v-if="suggestions.length" class="sub-block">
                  <div class="sub-title">改进建议</div>
                  <div v-for="(sg, i) in suggestions" :key="i" class="suggestion-line">
                    <el-icon style="color: #22c55e; margin-right: 6px;"><CircleCheck /></el-icon>
                    {{ sg }}
                  </div>
                </div>

                <!-- 体验三维度（可获得性/易查找性/可用性，V1.2） -->
                <template v-for="sec in experienceSections" :key="sec.key">
                  <h3 class="block-title" style="margin-top: 24px;">{{ sec.number }}、{{ sec.title }}</h3>
                  <div style="margin-bottom: 8px;">
                    <el-tag v-if="sec.overall != null" :type="levelTagType(sec.level)" size="small">
                      综合 {{ sec.overall }} 分 · {{ sec.level }}
                    </el-tag>
                    <span v-else class="dim-desc">样本不足（未评分）</span>
                  </div>
                  <div class="dim-list">
                    <div v-for="dim in sec.rows" :key="dim.key" class="dim-row">
                      <div class="dim-head">
                        <span class="dim-name">{{ dim.label }}</span>
                        <span class="dim-value">{{ dim.score == null ? 'N/A' : dim.score }}</span>
                      </div>
                      <el-progress :percentage="dim.score || 0" :stroke-width="10" :color="scoreColor(dim.score)" :show-text="false" />
                      <div class="dim-desc">{{ dim.desc }}</div>
                    </div>
                  </div>
                  <div v-for="(note, i) in sec.notes" :key="'note' + i" class="dim-desc" style="color: #d97706;">
                    {{ note }}
                  </div>
                </template>

                <!-- 体验维度改进建议 -->
                <div v-if="experienceSuggestions.length" class="sub-block">
                  <div class="sub-title">体验维度改进建议</div>
                  <div v-for="(sg, i) in experienceSuggestions" :key="i" class="suggestion-line">
                    <el-icon style="color: #3b82f6; margin-right: 6px;"><CircleCheck /></el-icon>
                    {{ sg }}
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <!-- 标签页二：Markdown 报告 -->
            <el-tab-pane label="Markdown 报告" name="md">
              <div class="md-preview">
                <pre class="report-pre">{{ reportMd || '报告生成中…' }}</pre>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </template>
    </div>

    <!-- ================= 历史任务视图 ================= -->
    <div v-else>
      <h2 class="page-title">竞品分析历史任务</h2>

      <div class="panel">
        <div class="panel-header">
          <span>全部分析任务</span>
          <div class="panel-actions">
            <el-button size="small" @click="loadTasks">刷新</el-button>
            <el-button size="small" type="primary" @click="goUpload">上传新文档</el-button>
          </div>
        </div>

        <el-table :data="tasks" v-loading="tasksLoading" border style="width: 100%;">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
          <el-table-column label="大小" width="100">
            <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="可读性评分" width="130">
            <template #default="{ row }">
              <span v-if="readabilityOf(row)">
                <template v-if="readabilityOf(row).overall_score != null">{{ readabilityOf(row).overall_score }} 分（{{ readabilityOf(row).level }}）</template>
                <template v-else>样本不足</template>
              </span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link :disabled="row.status !== 'completed'" @click="viewTask(row)">
                查看
              </el-button>
              <el-button size="small" link :disabled="row.status !== 'completed'" @click="downloadReportOf(row)">
                下载报告
              </el-button>
              <el-button size="small" type="danger" link @click="confirmDelete(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 任务详情对话框 -->
    <el-dialog v-model="detailVisible" :title="`分析详情 - ${detail?.file_name || ''}`" width="860px" top="6vh" destroy-on-close>
      <template v-if="detail">
        <div class="dialog-summary">
          <div class="dialog-summary-item">
            <span class="dialog-summary-label">编辑工具</span>
            <span class="dialog-summary-value">{{ detailToolSummary }}</span>
          </div>
          <div class="dialog-summary-item">
            <span class="dialog-summary-label">可读性评分</span>
            <span class="dialog-summary-value">
              <template v-if="detailReadability.overall_score != null">{{ detailReadability.overall_score }} 分（{{ detailReadability.level }}）</template>
              <template v-else>样本不足</template>
            </span>
          </div>
        </div>
        <el-tabs v-model="dialogTab">
          <el-tab-pane label="结构化结果" name="result">
            <div class="result-body" style="max-height: 60vh; overflow: auto;">
              <h3 class="block-title">一、编辑工具识别</h3>
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item label="格式">{{ detailToolMeta.format || '-' }}</el-descriptions-item>
                <el-descriptions-item label="页数">{{ detailToolMeta.pages || 0 }}</el-descriptions-item>
                <el-descriptions-item label="Producer">{{ detailToolMeta.producer || '-' }}</el-descriptions-item>
                <el-descriptions-item label="Creator">{{ detailToolMeta.creator || '-' }}</el-descriptions-item>
                <el-descriptions-item v-if="detailToolMeta.source_url" label="来源链接" :span="2">
                  <a :href="detailToolMeta.source_url" target="_blank" rel="noopener noreferrer" class="source-link">{{ detailToolMeta.source_url }}</a>
                </el-descriptions-item>
              </el-descriptions>
              <div v-if="detailTools.length" class="sub-block">
                <div class="sub-title">识别到的工具</div>
                <el-table :data="detailTools" size="small" border>
                  <el-table-column prop="name" label="工具" min-width="150" />
                  <el-table-column prop="category" label="类别" min-width="130" />
                  <el-table-column label="置信度" width="90">
                    <template #default="{ row }">
                      <el-tag :type="confidenceType(row.confidence)" size="small">{{ row.confidence }}</el-tag>
                    </template>
                  </el-table-column>
                </el-table>
              </div>

              <template v-if="detailStructureStats">
                <h3 class="block-title" style="margin-top: 20px;">二、结构统计（客观指标）</h3>
                <el-descriptions :column="5" border size="small">
                  <el-descriptions-item label="页数">{{ detailStructureStats.page_count ?? '—' }}</el-descriptions-item>
                  <el-descriptions-item label="章节">{{ detailStructureStats.heading_count ?? '—' }}</el-descriptions-item>
                  <el-descriptions-item label="图">{{ detailStructureStats.figure_count ?? '—' }}</el-descriptions-item>
                  <el-descriptions-item label="表">{{ detailStructureStats.table_count ?? '—' }}</el-descriptions-item>
                  <el-descriptions-item label="警告">{{ detailStructureStats.warning_count ?? '—' }}</el-descriptions-item>
                  <el-descriptions-item v-if="(detailStructureStats.warning_symbol_count || 0) > 0" label="警告符号">{{ detailStructureStats.warning_symbol_count }}</el-descriptions-item>
                </el-descriptions>
                <div v-for="(note, i) in detailStructureStats.notes || []" :key="i" class="dim-desc" style="color: #d97706;">
                  ⚠ {{ note }}
                </div>
              </template>

              <h3 class="block-title" style="margin-top: 20px;">{{ detailStructureStats ? '三、' : '二、' }}可读性分析</h3>
              <div class="dim-list">
                <div v-for="dim in detailDimRows" :key="dim.key" class="dim-row">
                  <div class="dim-head">
                    <span class="dim-name">{{ dim.label }}</span>
                    <span class="dim-value">{{ dim.score == null ? 'N/A' : dim.score }}</span>
                  </div>
                  <el-progress :percentage="dim.score || 0" :stroke-width="8" :color="scoreColor(dim.score)" :show-text="false" />
                  <div class="dim-desc">{{ dim.desc }}</div>
                </div>
              </div>
              <div v-if="detailSuggestions.length" class="sub-block">
                <div class="sub-title">改进建议</div>
                <div v-for="(sg, i) in detailSuggestions" :key="i" class="suggestion-line">
                  <el-icon style="color: #22c55e; margin-right: 6px;"><CircleCheck /></el-icon>
                  {{ sg }}
                </div>
              </div>

              <!-- 体验三维度（可获得性/易查找性/可用性，V1.2） -->
              <template v-for="sec in detailExperienceSections" :key="sec.key">
                <h3 class="block-title" style="margin-top: 20px;">{{ sec.number }}、{{ sec.title }}</h3>
                <div style="margin-bottom: 8px;">
                  <el-tag v-if="sec.overall != null" :type="levelTagType(sec.level)" size="small">
                    综合 {{ sec.overall }} 分 · {{ sec.level }}
                  </el-tag>
                  <span v-else class="dim-desc">样本不足（未评分）</span>
                </div>
                <div class="dim-list">
                  <div v-for="dim in sec.rows" :key="dim.key" class="dim-row">
                    <div class="dim-head">
                      <span class="dim-name">{{ dim.label }}</span>
                      <span class="dim-value">{{ dim.score == null ? 'N/A' : dim.score }}</span>
                    </div>
                    <el-progress :percentage="dim.score || 0" :stroke-width="8" :color="scoreColor(dim.score)" :show-text="false" />
                    <div class="dim-desc">{{ dim.desc }}</div>
                  </div>
                </div>
                <div v-for="(note, i) in sec.notes" :key="'note' + i" class="dim-desc" style="color: #d97706;">
                  {{ note }}
                </div>
              </template>

              <!-- 体验维度改进建议 -->
              <div v-if="detailExperienceSuggestions.length" class="sub-block">
                <div class="sub-title">体验维度改进建议</div>
                <div v-for="(sg, i) in detailExperienceSuggestions" :key="i" class="suggestion-line">
                  <el-icon style="color: #3b82f6; margin-right: 6px;"><CircleCheck /></el-icon>
                  {{ sg }}
                </div>
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane label="Markdown 报告" name="md">
            <pre class="report-pre" style="max-height: 60vh;">{{ detailReportMd }}</pre>
          </el-tab-pane>
        </el-tabs>
      </template>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button :disabled="!detail?.id" @click="goToCompare">与我方文件对比</el-button>
        <el-button type="primary" :disabled="!detailReportMd" @click="downloadReportOf(detail)">下载报告</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, UploadFilled, Download, MagicStick, CircleCheck, Switch } from '@element-plus/icons-vue'
import { competitorAPI, getAPIErrorMessage } from '@/api'

const route = useRoute()
const router = useRouter()

const currentView = computed(() => (route.path === '/competitor/tasks' ? 'tasks' : 'upload'))

const inputMode = ref('file')
const selectedFile = ref(null)
const sourceUrl = ref('')
const analyzing = ref(false)
const detail = ref(null)          // 最近一次分析结果 / 查看详情对象
const activeTab = ref('result')
const dialogTab = ref('result')
const detailVisible = ref(false)

const tasks = ref([])
const tasksLoading = ref(false)

// ---------- 上传与分析 ----------
function handleFileChange(file) {
  selectedFile.value = file?.raw || file || null
  if (selectedFile.value) {
    inputMode.value = 'file'
    detail.value = null
    activeTab.value = 'result'
  }
}

function handleUrlInput() {
  if (sourceUrl.value) {
    inputMode.value = 'url'
    detail.value = null
    activeTab.value = 'result'
  }
}

function resetUpload() {
  inputMode.value = 'file'
  selectedFile.value = null
  sourceUrl.value = ''
  detail.value = null
  activeTab.value = 'result'
}

const analyzeDisabled = computed(() => {
  if (inputMode.value === 'url') return !sourceUrl.value.trim()
  return !selectedFile.value
})

function isValidHttpUrl(value) {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

async function doAnalyze() {
  analyzing.value = true
  try {
    let resp
    if (inputMode.value === 'url') {
      const url = sourceUrl.value.trim()
      if (!isValidHttpUrl(url)) {
        ElMessage.warning('请输入有效的 http 或 https 链接')
        return
      }
      resp = await competitorAPI.createFromUrl(url)
    } else {
      const f = selectedFile.value
      if (!f) return
      const okExt = /\.(pdf|docx|md|markdown|txt|html|htm)$/i.test(f.name || '')
      if (!okExt) {
        ElMessage.warning('仅支持 PDF / DOCX / MD / TXT / HTML 格式')
        return
      }
      if (f.size > 50 * 1024 * 1024) {
        ElMessage.warning('文件大小不能超过 50MB')
        return
      }
      resp = await competitorAPI.create(selectedFile.value)
    }
    detail.value = resp.data
    activeTab.value = 'result'
    ElMessage.success('分析完成')
  } catch (e) {
    ElMessage.error(getAPIErrorMessage(e, '分析失败'))
  } finally {
    analyzing.value = false
  }
}

// ---------- JSON 解析工具 ----------
function safeParse(value, fallback = {}) {
  if (!value) return fallback
  if (typeof value === 'object') return value
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

const toolAnalysis = computed(() => safeParse(detail.value?.tool_analysis))
const readability = computed(() => safeParse(detail.value?.readability))
const toolSummary = computed(() => toolAnalysis.value.summary || '未知')
const toolMeta = computed(() => toolAnalysis.value.meta || {})
const tools = computed(() => toolAnalysis.value.tools || [])
const fontSignals = computed(() => toolAnalysis.value.font_signals || [])
// 结构统计（客观指标）：旧任务无该字段时为 null，对应章节不渲染
const structureStats = computed(() => toolAnalysis.value.structure_stats || null)
const reportMd = computed(() => detail.value?.report_md || '')
const stats = computed(() => readability.value.stats || {})

const dimRows = computed(() => {
  const dims = readability.value.dimensions || {}
  const names = {
    sentence_length: '平均句长',
    term_density: '术语密度',
    passive_ratio: '被动句比例',
    paragraph_length: '段落长度',
    modifier_stack: '修饰词堆叠'
  }
  return Object.keys(names).map((key) => {
    const dim = dims[key] || {}
    return { key, label: names[key], score: dim.score == null ? null : Math.round(dim.score), desc: dim.label || '' }
  })
})

const sampleGroups = computed(() => {
  // 样本不足（overall_score 为 null）时不展示例句，避免把低样本量样本当问题
  if (readability.value.overall_score == null) return []
  const dims = readability.value.dimensions || {}
  const names = {
    sentence_length: '超长句',
    term_density: '术语堆砌句',
    passive_ratio: '被动句',
    modifier_stack: '修饰词堆叠',
    paragraph_length: '超长段落'
  }
  const groups = []
  for (const [key, label] of Object.entries(names)) {
    const dim = dims[key] || {}
    // 与报告口径一致：仅得分 <75 的维度展示例句
    if (!(dim.score != null && dim.score < 75)) continue
    const samples = (dim.samples || []).filter((s) => s && s.text)
    if (samples.length) {
      groups.push({ key, label, score: dim.score, samples })
    }
  }
  return groups
})

const suggestions = computed(() => readability.value.suggestions || [])

// 体验三维度低分维度 → 前端直接生成改进建议（与后端 insights 互补，保持单份报告可视化完整）
// 公共生成函数：主视图与详情对话框共用（P2-9 修复，避免双份逻辑漂移）
function buildExperienceSuggestions(exp) {
  if (!exp) return []
  const list = []
  const sections = [
    { key: 'access', label: '可获得性' },
    { key: 'findability', label: '易查找性' },
    { key: 'usability', label: '可用性' }
  ]
  const dimActions = {
    access_barrier: '确保文档公开可访问，避免强制登录/注册',
    formats: '提供多格式输出（PDF + 在线 HTML）',
    has_search: '配置站内检索或完善目录/索引',
    mobile_adaptation: '采用响应式布局适配移动端',
    languages: '评估目标市场语言覆盖',
    version_transparency: '标注文档版本号与更新日期',
    offline_available: '提供可下载离线包',
    toc_completeness: '建立层级清晰的目录与书签导航',
    has_breadcrumb: '添加面包屑导航帮助定位',
    has_index_glossary: '添加术语索引与词汇表',
    url_semantic: '使用描述性 URL 路径',
    seo_metadata: '配置页面 SEO 元数据',
    quick_links: '在首页放置常用操作快捷入口',
    task_oriented_headings: '标题采用任务导向写法',
    step_completeness: '操作步骤包含前置条件、动作、预期结果',
    error_recovery: '添加常见错误提示与恢复方法',
    consistency: '统一术语、单位与排版规范',
    link_validity: '定期巡检超链接有效性',
    imperative_instructions: '使用祈使句明确用户动作'
  }
  for (const sec of sections) {
    const part = exp[sec.key]
    if (!part || !part.dimensions) continue
    for (const [dk, dv] of Object.entries(part.dimensions)) {
      // 与后端 _EXPERIENCE_DIM_ACTIONS 对齐：has_search 仅在 Access 区生成建议（P2-3 修复）
      if (sec.key === 'findability' && dk === 'has_search') continue
      // 类型与适用性校验（P2-8 修复：score 须为数值，避免字符串隐式比较造成前后端分歧）
      if (typeof dv !== 'object' || dv === null || dv.applicable === false || typeof dv.score !== 'number') continue
      if (dv.score < 55) {
        list.push(`【${sec.label}·${dimActions[dk] || dk}】竞品明显偏弱（${dv.score} 分），我方应${dimActions[dk] || '优化该维度'}，形成差异化优势。`)
      } else if (dv.score < 70) {
        list.push(`【${sec.label}·${dimActions[dk] || dk}】竞品有改进空间（${dv.score} 分），我方保持${dimActions[dk] || '优化'}即可领先。`)
      }
    }
  }
  return list.slice(0, 10)
}

const experienceSuggestions = computed(() => buildExperienceSuggestions(safeParse(detail.value?.experience)))

// ---------- 体验三维度（可获得性/易查找性/可用性，V1.2） ----------
// 中文章节号：与后端报告动态编号对齐（P1 修复：结构统计缺失时顺延，不硬编码四五六）
const CN_NUMS = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
const EXPERIENCE_SECTIONS = [
  {
    key: 'access', title: '可获得性分析',
    dims: [
      ['access_barrier', '获取门槛'], ['formats', '格式选择'], ['has_search', '站内搜索'],
      ['mobile_adaptation', '移动端适配'], ['languages', '多语言支持'],
      ['version_transparency', '版本透明度'], ['offline_available', '离线可用性']
    ]
  },
  {
    key: 'findability', title: '易查找性分析',
    dims: [
      ['has_search', '站内搜索'], ['toc_completeness', '目录（TOC）'], ['has_breadcrumb', '面包屑导航'],
      ['has_index_glossary', '索引与术语表'], ['url_semantic', 'URL 语义化'],
      ['seo_metadata', 'SEO 元数据'], ['quick_links', '关键内容直达']
    ]
  },
  {
    key: 'usability', title: '可用性分析',
    dims: [
      ['task_oriented_headings', '任务导向标题'], ['step_completeness', '步骤完整性'],
      ['error_recovery', '错误恢复信息'], ['consistency', '信息一致性'],
      ['link_validity', '链接有效性'], ['imperative_instructions', '可操作指令']
    ]
  }
]

function buildExperienceRows(exp, hasStructure) {
  if (!exp) return []
  // 体验章节起始编号：结构统计存在 → 四、；缺失 → 三、（与后端报告动态编号一致）
  const startIdx = hasStructure ? 3 : 2
  return EXPERIENCE_SECTIONS
    .map((sec, i) => {
      const part = exp[sec.key] || {}
      const dims = part.dimensions || {}
      const rows = sec.dims
        .map(([key, label]) => {
          const dim = dims[key] || {}
          return { key, label, score: dim.score == null ? null : Math.round(dim.score), desc: dim.note || '' }
        })
        .filter((d) => dims[d.key])
      return {
        key: sec.key,
        number: CN_NUMS[startIdx + i] || sec.title.slice(0, 1),
        title: sec.title,
        overall: part.overall_score,
        level: part.level || '',
        notes: part.notes || [],
        rows
      }
    })
    .filter((s) => s.rows.length > 0)
}

const experience = computed(() => safeParse(detail.value?.experience))
const experienceSections = computed(() => buildExperienceRows(experience.value, !!structureStats.value))

// ---------- 历史任务 ----------
async function loadTasks() {
  tasksLoading.value = true
  try {
    const resp = await competitorAPI.list({ skip: 0, limit: 200 })
    tasks.value = resp.data || []
  } catch (e) {
    ElMessage.error(getAPIErrorMessage(e, '加载任务列表失败'))
  } finally {
    tasksLoading.value = false
  }
}

function readabilityOf(row) {
  return safeParse(row.readability)
}

async function viewTask(row) {
  // 列表接口不含 report_md，需拉取完整详情再打开对话框（否则报告 tab / 下载按钮不可用）
  detail.value = row
  dialogTab.value = 'result'
  detailVisible.value = true
  try {
    const resp = await competitorAPI.get(row.id)
    if (resp.data) detail.value = resp.data
  } catch (e) {
    ElMessage.error(getAPIErrorMessage(e, '加载任务详情失败'))
  }
}

async function confirmDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除任务「${row.file_name}」？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await competitorAPI.delete(row.id)
    ElMessage.success('已删除')
    loadTasks()
  } catch (e) {
    ElMessage.error(getAPIErrorMessage(e, '删除失败'))
  }
}

// ---------- 报告下载 ----------
function triggerMdDownload(text, filename) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

async function downloadReport() {
  const md = reportMd.value || (detail.value?.report_md)
  if (!md) return
  const name = (detail.value?.file_name || 'competitor').replace(/\.(pdf|docx|md|markdown|txt|html|htm)$/i, '')
  triggerMdDownload(md, `${name}_竞品分析报告.md`)
}

async function downloadReportOf(row) {
  try {
    const resp = await competitorAPI.getReport(row.id)
    // 接口返回 {content, format}（与 compare 报告接口对齐）
     const md = resp.data?.content || resp.data || ''
     if (!md) return
     const name = (row.file_name || 'competitor').replace(/\.(pdf|docx|md|markdown|txt|html|htm)$/i, '')
     triggerMdDownload(md, `${name}_竞品分析报告.md`)
  } catch (e) {
    ElMessage.error(getAPIErrorMessage(e, '下载报告失败'))
  }
}

function goToCompare() {
  const taskId = detail.value?.id
  if (!taskId) {
    ElMessage.warning('当前无有效任务，请先完成分析')
    return
  }
  router.push({ path: '/competitor/compare', query: { preselect: String(taskId) } })
}

// ---------- 详情对话框数据 ----------
const detailToolAnalysis = computed(() => safeParse(detail.value?.tool_analysis))
const detailReadability = computed(() => safeParse(detail.value?.readability))
const detailToolSummary = computed(() => detailToolAnalysis.value.summary || '未知')
const detailToolMeta = computed(() => detailToolAnalysis.value.meta || {})
const detailTools = computed(() => detailToolAnalysis.value.tools || [])
const detailStructureStats = computed(() => detailToolAnalysis.value.structure_stats || null)
const detailReportMd = computed(() => detail.value?.report_md || '')
const detailDimRows = computed(() => {
  const dims = detailReadability.value.dimensions || {}
  const names = {
    sentence_length: '平均句长',
    term_density: '术语密度',
    passive_ratio: '被动句比例',
    paragraph_length: '段落长度',
    modifier_stack: '修饰词堆叠'
  }
  return Object.keys(names).map((key) => {
    const dim = dims[key] || {}
    return { key, label: names[key], score: dim.score == null ? null : Math.round(dim.score), desc: dim.label || '' }
  })
})
const detailSuggestions = computed(() => detailReadability.value.suggestions || [])
const detailExperience = computed(() => safeParse(detail.value?.experience))
const detailExperienceSections = computed(() => buildExperienceRows(detailExperience.value, !!detailStructureStats.value))

// 详情对话框：体验维度改进建议（复用公共生成函数，与主视图保持一致）
const detailExperienceSuggestions = computed(() => buildExperienceSuggestions(detailExperience.value))

// ---------- 展示辅助 ----------
function formatSize(size) {
  const n = Number(size || 0)
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${n} B`
}

function formatTime(ts) {
  if (!ts) return '-'
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return String(ts)
  const pad = (x) => String(x).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function statusText(status) {
  return { pending: '等待中', processing: '分析中', completed: '已完成', failed: '失败' }[status] || status
}

function statusType(status) {
  return { pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' }[status] || 'info'
}

function confidenceType(confidence) {
  return { high: 'success', medium: 'warning', low: 'info' }[confidence] || 'info'
}

function scoreColor(score) {
  if (score == null) return '#94a3b8'  // 样本不足/未评分：灰色
  if (score >= 85) return '#22c55e'
  if (score >= 70) return '#f59e0b'
  return '#ef4444'
}

function scoreColorTag(score) {
  if (score == null) return 'info'
  if (score >= 85) return 'success'
  if (score >= 70) return 'warning'
  return 'danger'
}

function levelTagType(level) {
  return { excellent: 'success', good: 'success', fair: 'warning', poor: 'danger', insufficient: 'info' }[level] || 'info'
}

const toolOkClass = computed(() => (tools.value.length ? '' : 'muted'))

function goUpload() {
  router.push('/competitor')
}

watch(currentView, (view) => {
  if (view === 'tasks') loadTasks()
}, { immediate: true })
</script>

<style scoped>
.competitor-container {
  max-width: 1180px;
  margin: 0 auto;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 16px;
}

.panel {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  padding: 20px;
  margin-bottom: 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  font-weight: 600;
  color: #1e293b;
  font-size: 15px;
}

.input-tabs {
  margin-top: 4px;
}

.upload-box {
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
  background: #f8fafc;
}

.upload-box:hover {
  border-color: #3b82f6;
  background: #eff6ff;
}

.upload-hint {
  color: #475569;
  font-size: 14px;
  font-weight: 600;
}

.upload-sub {
  margin-top: 6px;
  color: #94a3b8;
  font-size: 12px;
}

.upload-name {
  color: #1d4ed8;
  font-size: 14px;
  font-weight: 700;
  word-break: break-all;
}

.url-box {
  padding: 12px 0 4px;
}

.url-label {
  margin-bottom: 10px;
  color: #334155;
  font-size: 14px;
  font-weight: 600;
}

.action-row {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

.result-summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}

.summary-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  padding: 18px 20px;
}

.summary-card-label {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 8px;
}

.summary-card-value {
  font-size: 20px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.3;
}

.summary-card-value.score {
  font-size: 32px;
  color: #2563eb;
}

.summary-card-value.muted {
  color: #94a3b8;
  font-size: 15px;
}

.summary-card-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #94a3b8;
}

.result-body {
  color: #1e293b;
}

.block-title {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  margin: 8px 0 12px;
}

.meta-desc {
  margin-bottom: 8px;
}

.source-link {
  color: #2563eb;
  word-break: break-all;
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}

.sub-block {
  margin-top: 14px;
}

.sub-title {
  font-size: 13px;
  font-weight: 700;
  color: #475569;
  margin-bottom: 8px;
}

.font-signal {
  display: flex;
  align-items: center;
  font-size: 13px;
  color: #475569;
  padding: 6px 0;
}

.font-signal-sub {
  color: #94a3b8;
  font-size: 12px;
}

.dim-list {
  display: grid;
  gap: 12px;
}

.dim-row {
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #eef2f7;
}

.dim-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.dim-name {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
}

.dim-value {
  font-size: 14px;
  font-weight: 800;
  color: #2563eb;
}

.dim-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #94a3b8;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-top: 16px;
}

.sample-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: #475569;
}

.sample-text {
  flex: 1;
  line-height: 1.5;
  word-break: break-all;
}

.suggestion-line {
  display: flex;
  align-items: flex-start;
  padding: 5px 0;
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
}

.report-pre {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 65vh;
  overflow: auto;
  font-family: 'SF Mono', Consolas, Menlo, monospace;
}

.dialog-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #eff6ff;
  border-radius: 8px;
}

.dialog-summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dialog-summary-label {
  font-size: 12px;
  color: #64748b;
}

.dialog-summary-value {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}
</style>
