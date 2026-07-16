<template>
  <div class="polish-container" :class="{ 'document-mode': currentView === 'document' }">
    <div v-if="currentView === 'document'" class="document-view">
      <div class="page-title-row">
        <h2 class="page-title">文档润色</h2>
        <div class="stats-card">
          <span class="stats-label">准确率</span>
          <span class="stats-value" :class="{ 'stats-green': docFeedbackStats.averageAccuracy >= 50, 'stats-red': docFeedbackStats.averageAccuracy < 50 }">{{ docFeedbackStats.averageAccuracy }}%</span>
          <span class="stats-divider">|</span>
          <span class="stats-label">共润色</span>
          <span class="stats-count-wrap">
            <span class="stats-count" :class="{ 'stats-green': docFeedbackStats.averageAccuracy >= 50, 'stats-red': docFeedbackStats.averageAccuracy < 50 }">{{ docFeedbackStats.totalDocs }}</span>
            <span class="stats-unit">文档</span>
          </span>
        </div>
        <div v-if="loading" class="polish-progress-float" :class="{ done: polishProgress >= 100 }">
          <div class="progress-float-bar">
            <el-icon class="is-loading" v-if="polishProgress < 100"><Loading /></el-icon>
            <span class="progress-float-text">{{ polishProgressMsg || '润色中...' }}</span>
          </div>
          <div v-if="polishProgress < 100" class="progress-float-body">
            <el-progress :percentage="polishProgress" :stroke-width="10" />
          </div>
        </div>
      </div>

      <div class="doc-layout" :class="{ 'doc-layout-result-only': docResult }">
        <div v-if="!docResult" class="doc-left">
          <div class="panel doc-input-panel">
            <div class="form-item">
              <label class="form-label">句式清单文件</label>
              <div class="input-with-button">
                <el-select v-model="formData.sentenceFileId" class="full-width" placeholder="选择句式清单文件" clearable>
                  <el-option v-for="f in sentenceFileOptions" :key="f.id" :label="f.label" :value="f.id" />
                </el-select>
              </div>
            </div>

            <div class="form-item">
              <label class="form-label">术语对照表</label>
              <div class="input-with-button">
                <el-select v-model="formData.terminologyFileId" class="full-width" placeholder="留空则使用数据库术语" clearable @change="onDocumentTerminologyChange">
                  <el-option v-for="f in termFileOptions" :key="f.id" :label="f.label" :value="f.id" />
                </el-select>
              </div>
            </div>

            <div class="form-item">
              <label class="form-label">待润色文件</label>
              <div class="input-with-button">
                <el-input v-model="formData.sourceFile" readonly placeholder="选择本地文件" />
                <el-button type="primary" @click="openLocalFilePicker()">选择文件</el-button>
              </div>
            </div>

            <div class="form-item">
              <label class="form-label">润色要求</label>
              <el-input v-model="formData.requirements" type="textarea" :rows="3" placeholder="请输入额外的润色要求（选填）" />
            </div>

            <div class="button-group doc-button-group">
              <el-button @click="resetForm">重置</el-button>
              <el-button type="primary" :loading="loading" @click="submitPolish">提交</el-button>
            </div>
          </div>

        </div>

        <div class="doc-right">
          <div v-if="docResult" class="panel doc-result-panel">
            <div class="panel-header">
              <span>润色结果</span>
              <div class="panel-actions">
                <el-button size="small" @click="downloadPolishedDoc">下载文档</el-button>
                <el-button size="small" @click="downloadReport">润色报告</el-button>
                <el-button type="primary" size="small" :loading="docFeedbackLoading || docDecisionSaving" @click="submitDocumentFeedback">写入平台反馈句式清单</el-button>
              </div>
            </div>

            <div ref="docPreviewRef" class="doc-review-panel">
              <div class="doc-review-summary">
                <div class="doc-review-count">共 {{ docResult.changes }} 处问题</div>
                <div class="doc-review-confirmed">已确认 {{ confirmedDocChangeCount }}/{{ docResult.changes }}</div>
              </div>

              <div class="doc-review-toolbar">
                <div class="doc-review-filters">
                  <span class="filter-label">筛选：</span>
                  <el-select v-model="docFilterType" size="small" placeholder="全部类型" class="doc-filter-select">
                    <el-option label="全部类型" value="" />
                    <el-option v-for="item in docIssueTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
                  </el-select>
                  <el-select v-model="docFilterTriggerLevel" size="small" placeholder="全部触发次数" class="doc-filter-select">
                    <el-option label="全部触发次数" value="" />
                    <el-option label="高" value="high" />
                    <el-option label="中" value="medium" />
                    <el-option label="低" value="low" />
                  </el-select>
                </div>
                <div class="doc-review-bulk-actions">
                  <el-button size="small" type="success" :loading="docDecisionSaving" @click="acceptAllDocumentIssues">全部接受</el-button>
                  <el-button size="small" type="danger" plain :loading="docDecisionSaving" @click="rejectAllDocumentIssues">全部拒绝</el-button>
                </div>
              </div>

              <div v-if="filteredDocIssues.length" class="doc-issue-list">
                <div
                  v-for="issue in filteredDocIssues"
                  :key="issue.rowKey"
                  class="doc-issue-card"
                  :class="{
                    'is-accepted': issue.status === 'accepted' || issue.status === 'custom',
                    'is-rejected': issue.status === 'rejected'
                  }"
                >
                  <div class="doc-issue-header">
                    <div class="doc-issue-title">问题 #{{ issue.displayIndex }}</div>
                    <div class="doc-issue-meta">
                      <el-tag size="small" :type="issue.typeTagType">{{ issue.typeLabel }}</el-tag>
                      <span class="trigger-pill" :class="`trigger-${issue.triggerLevel}`">触发次数 {{ issue.triggerCount }}</span>
                      <span class="paragraph-pill">段落 #{{ issue.paragraph }}</span>
                    </div>
                  </div>

                  <div class="doc-issue-body">
                    <div class="issue-line">
                      <span class="issue-label">原文：</span>
                      <span class="issue-text">{{ issue.before || issue.after }}</span>
                    </div>
                    <div class="issue-line">
                      <span class="issue-label">建议：</span>
                      <span class="issue-text" v-html="renderIssueSuggestion(issue)"></span>
                    </div>
                    <div class="issue-line issue-basis">
                      <span class="issue-label">依据：</span>
                      <span>{{ issueBasisText(issue) }}</span>
                    </div>
                  </div>

                  <div v-if="issue.editing" class="custom-edit-row">
                    <el-input v-model="issue.customAfter" size="small" placeholder="输入自定义替换文本" />
                    <el-button size="small" type="primary" :loading="docDecisionSaving" @click="saveCustomDocumentIssue(issue)">保存</el-button>
                    <el-button size="small" @click="cancelCustomDocumentIssue(issue)">取消</el-button>
                  </div>

                  <div class="doc-issue-actions">
                    <el-button size="small" type="success" plain :disabled="docDecisionSaving" @click="acceptDocumentIssue(issue)">接受</el-button>
                    <el-button size="small" type="danger" plain :disabled="docDecisionSaving" @click="rejectDocumentIssue(issue)">拒绝</el-button>
                    <el-button size="small" @click="editDocumentIssue(issue)">自定义</el-button>
                    <el-tag v-if="issue.status === 'accepted'" size="small" type="success">已接受</el-tag>
                    <el-tag v-if="issue.status === 'rejected'" size="small" type="danger">已拒绝</el-tag>
                    <el-tag v-if="issue.status === 'custom'" size="small" type="warning">已自定义</el-tag>
                  </div>
                </div>
              </div>
              <div v-else class="doc-change-empty">当前没有可确认的润色结果</div>

              <div class="doc-review-footer">
                <el-button @click="resetForm">返回</el-button>
                <el-button type="primary" @click="scrollToDocumentPreview">预览修改</el-button>
              </div>
            </div>
          </div>

          <div v-else class="panel result-placeholder doc-result-panel">
            <div class="panel-header">
              <span>润色结果</span>
            </div>
            <div class="placeholder-text">提交文档后，这里会展示润色结果和每条修改的确认状态。</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="currentView === 'text'">
      <div class="page-title-row">
        <h2 class="page-title">文本润色</h2>
        <div class="stats-card">
          <span class="stats-label">准确率</span>
          <span class="stats-value" :class="{ 'stats-green': feedbackStats.averageAccuracy >= 50, 'stats-red': feedbackStats.averageAccuracy < 50 }">{{ feedbackStats.averageAccuracy }}%</span>
          <span class="stats-divider">|</span>
          <span class="stats-label">共润色</span>
          <span class="stats-count-wrap">
            <span class="stats-count" :class="{ 'stats-green': feedbackStats.averageAccuracy >= 50, 'stats-red': feedbackStats.averageAccuracy < 50 }">{{ feedbackStats.totalCount }}</span>
            <span class="stats-unit">次</span>
          </span>
        </div>
      </div>

      <!-- 文件选择行 -->
      <div class="panel">
        <div class="panel-header">
          <span>参考文件</span>
        </div>
        <div class="file-select-row">
          <div class="file-select-col">
            <label class="form-label">句式清单文件</label>
            <div class="input-with-button">
              <el-select v-model="textSentenceFileId" size="small" class="full-width" placeholder="留空则加载全部" clearable>
                <el-option v-for="f in sentenceFileOptions" :key="f.id" :label="f.label" :value="f.id" />
              </el-select>
            </div>
          </div>
          <div class="file-select-col">
            <label class="form-label">术语对照表</label>
            <div class="input-with-button">
              <el-select v-model="textTerminologyFileId" size="small" class="full-width" placeholder="留空则使用数据库术语" clearable>
                <el-option v-for="f in termFileOptions" :key="f.id" :label="f.label" :value="f.id" />
              </el-select>
            </div>
          </div>
        </div>
      </div>

      <!-- 左右分栏：输入 + 结果 -->
      <div class="content-row">
        <div class="content-left">
          <div class="panel">
            <div class="panel-header">
              <span>请输入需要润色的文本</span>
              <div class="panel-actions">
                <el-button type="primary" size="small" :loading="loading" @click="doPolish">开始润色</el-button>
                <el-button size="small" @click="clearAll">清空</el-button>
              </div>
            </div>
            <el-input
              v-model="originalText"
              type="textarea"
              placeholder="请输入需要润色的文本..."
            />
          </div>
        </div>
        <div class="content-right">
          <div v-if="result" class="panel result-panel">
              <div class="panel-header">
                <div class="result-header-main">
                  <span>润色结果</span>
                  <el-tag size="small" type="success">当前引擎：{{ currentPolishEngine }}</el-tag>
                </div>
                <div class="panel-actions">
                  <el-tag type="info" size="small">修改 {{ result.changes }} 处</el-tag>
                  <el-button size="small" @click="copyResult">复制</el-button>
                  <el-button size="small" @click="downloadResult">导出</el-button>
                </div>
              </div>
              <div class="result-grid-vertical">
                <div class="result-col-v">
                  <div class="col-title"><span class="dot dot-green"></span>润色结果</div>
                  <div class="col-content col-content-compact" v-html="highlightedPolishedHtml"></div>
                </div>
              </div>
          </div>
          <div v-else class="panel result-placeholder">
            <div class="panel-header">
              <span>润色结果</span>
            </div>
            <div class="placeholder-text">点击"开始润色"查看结果</div>
          </div>
        </div>
      </div>

      <!-- 意见反馈行（独立） -->
      <div v-if="result" class="panel feedback-panel">
        <div class="panel-header">
          <span>意见反馈</span>
        </div>
        <div class="feedback-row">
          <div class="feedback-left">
            <div class="form-item">
              <label class="form-label">准确率评分 (0-100%)</label>
              <el-slider v-model="feedbackAccuracy" :min="0" :max="100" :step="5" show-input />
            </div>
          </div>
          <div class="feedback-right">
            <div class="form-item">
              <label class="form-label">需修正的词语/句子</label>
              <el-input
                v-model="feedbackCorrections"
                type="textarea"
                :rows="3"
                :placeholder="feedbackPlaceholder"
              />
              <div class="feedback-hint">{{ feedbackHint }}</div>
            </div>
          </div>
        </div>
        <div class="feedback-bottom">
          <div class="form-item">
            <label class="form-label">写入目标（将写入上方选中的对应文件）</label>
            <el-radio-group v-model="feedbackTarget">
              <el-radio value="terminology">术语对照表</el-radio>
              <el-radio value="sentence_guide">句式清单文件</el-radio>
            </el-radio-group>
          </div>
          <div style="text-align: right">
            <el-button type="primary" :loading="feedbackLoading" @click="submitFeedback">提交反馈</el-button>
          </div>
        </div>
      </div>
    </div>

    <input
      ref="localFileInputRef"
      type="file"
      style="display: none"
      accept=".txt,.md,.docx"
      @change="onLocalFileSelected"
    />

    <el-dialog v-model="filePickerVisible" title="从知识库选择文件" width="480px">
      <div class="file-picker-content">
        <div v-if="knowledgeTreeList.length === 0" class="picker-empty">暂无知识库文件</div>
        <div v-else class="picker-list">
          <button
            v-for="item in knowledgeTreeList"
            :key="item.nodeKey"
            type="button"
            class="picker-row"
            :class="{ 'is-file': item.isFile, 'is-folder': !item.isFile, 'is-selected': selectedKnowledgeFile?.nodeKey === item.nodeKey }"
            :style="{ paddingLeft: `${12 + item.depth * 20}px` }"
            @click="onTreeNodeClick(item)"
          >
            <span class="node-icon">{{ item.isFile ? '📄' : '📁' }}</span>
            <span class="picker-name">{{ item.name }}</span>
          </button>
        </div>
        <div v-if="selectedKnowledgeFile" class="selected-info">
          已选择：{{ selectedKnowledgeFile.name }}
        </div>
      </div>
      <template #footer>
        <el-button @click="filePickerVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmKnowledgeFile" :disabled="!selectedKnowledgeFile">确认</el-button>
      </template>
    </el-dialog>

    <!-- 需修正弹窗 -->
    <el-dialog
      v-model="correctionDialogVisible"
      title="填写正确描述"
      width="500px"
      :close-on-click-modal="false"
      append-to-body
    >
      <div>
        <p style="margin-bottom: 10px; color: #64748b; font-size: 13px;">
          原文：<strong>{{ correctionForm.original }}</strong>
        </p>
        <p style="margin-bottom: 12px; color: #64748b; font-size: 13px;">
          润色后：<strong>{{ correctionForm.polished }}</strong>
        </p>
        <el-input
          v-model="correctionForm.correction"
          type="textarea"
          :rows="4"
          placeholder="请填写正确的句子描述..."
        />
      </div>
      <template #footer>
        <el-button @click="closeCorrectionDialog">取消</el-button>
        <el-button type="primary" :loading="correctionSubmitting" @click="submitCorrection">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { polishAPI, knowledgeAPI, systemAPI } from '@/api'
import { Loading } from '@element-plus/icons-vue'
import { usePolishStore } from '@/store/polish'

const route = useRoute()
const polishStore = usePolishStore()
const { documentDraft, documentSession } = storeToRefs(polishStore)
const localFileInputRef = ref(null)
const docPreviewRef = ref(null)
const filePickerVisible = ref(false)
const knowledgeTree = ref([])
const knowledgeTreeList = ref([])
const selectedKnowledgeFile = ref(null)
const currentPickerField = ref(null)

// ── 下拉框选项 ──
const sentenceFileOptions = ref([])
const termFileOptions = ref([])

// ── 加载句式清单 / 术语库下拉选项 ──
async function loadDropdownOptions() {
  try {
    const resp = await knowledgeAPI.getTree()
    const rawData = resp.data || []
    const sentenceNode = findNodeByName(rawData, '句式清单')
    const termNode = findNodeByName(rawData, '术语库')
    sentenceFileOptions.value = flattenFileOptions(sentenceNode ? [sentenceNode] : [])
    termFileOptions.value = flattenFileOptions(termNode ? [termNode] : [])
  } catch (e) {
    console.warn('加载知识库下拉选项失败', e)
  }
}

function flattenFileOptions(nodes) {
  const result = []
  function walk(list, prefix = '') {
    if (!Array.isArray(list)) return
    list.forEach(node => {
      const label = prefix ? `${prefix} / ${node.name}` : node.name
      const files = node.files || []
      files.forEach(f => {
        result.push({ id: f.id, name: f.name, label: f.name, groupLabel: label })
      })
      if (node.children && node.children.length > 0) {
        walk(node.children, label)
      }
    })
  }
  walk(nodes)
  return result
}

const originalText = ref('')
const textSentenceFileName = ref('')
const textSentenceFileId = ref(null)
const textTerminologyFileName = ref('')
const textTerminologyFileId = ref(null)
const result = ref(null)
const docResult = ref(null)
const docFilterType = ref('')
const docFilterTriggerLevel = ref('')
const loading = ref(false)
const polishProgress = ref(0)
const polishProgressMsg = ref('')
const docFeedbackLoading = ref(false)
const docDecisionSaving = ref(false)
const docFeedbackStats = ref({ totalDocs: 0, averageAccuracy: 0 })
// 反馈相关
const feedbackAccuracy = ref(80)
const feedbackCorrections = ref('')
const feedbackTarget = ref('terminology')
const feedbackLoading = ref(false)
const feedbackStats = ref({ totalCount: 0, averageAccuracy: 0 })
const currentPolishEngine = ref('检测中')

const feedbackPlaceholder = computed(() => (
  feedbackTarget.value === 'sentence_guide'
    ? '每行一条，直接填写需补充或修正的词语/句子\n例如：请勿在开机状态下断开电源。'
    : '每行一条，格式：非标准词 → 标准词\n例如：移液枪 → 移液器'
))

const feedbackHint = computed(() => (
  feedbackTarget.value === 'sentence_guide'
    ? '句式清单文件：将自动写入平台反馈的句式清单，每行一条。'
    : '术语对照表：将自动写入平台反馈的术语对照表，按"非标准词 → 标准词"填写。'
))

// 文档润色 - 需修正弹窗
const correctionDialogVisible = ref(false)
const correctionSubmitting = ref(false)
const correctionForm = ref({ index: -1, original: '', polished: '', correction: '' })

function onCorrectionChecked(index, item) {
  if (item.needCorrection) {
    correctionForm.value = {
      index,
      original: item.before || '',
      polished: item.after || '',
      correction: ''
    }
    correctionDialogVisible.value = true
  }
}

function closeCorrectionDialog() {
  correctionDialogVisible.value = false
  if (correctionForm.value.index >= 0) {
    const items = docResult.value?.changeDetails
    if (items && items[correctionForm.value.index]) {
      items[correctionForm.value.index].needCorrection = false
    }
  }
}

async function submitCorrection() {
  if (!correctionForm.value.correction.trim()) {
    ElMessage.warning('请填写正确的句子描述')
    return
  }
  correctionSubmitting.value = true
  try {
    const resp = await polishAPI.submitFeedback(
      correctionForm.value.original,
      correctionForm.value.polished,
      0,  // 准确率不适用
      correctionForm.value.correction.trim(),
      'sentence_guide',
      null,  // 不走选中术语文件
      null   // 不走选中句式文件
    )
    const data = resp.data || {}
    ElMessage.success(`已写入平台反馈句式清单`)
    correctionDialogVisible.value = false
    if (correctionForm.value.index >= 0) {
      const items = docResult.value?.changeDetails
      if (items && items[correctionForm.value.index]) {
        items[correctionForm.value.index].needCorrection = false
      }
    }
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`提交失败：${errorMsg}`)
  } finally {
    correctionSubmitting.value = false
  }
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const semanticPunctuationMap = {
  '，': ',',
  '。': '.',
  '；': ';',
  '：': ':',
  '！': '!',
  '？': '?',
  '（': '(',
  '）': ')',
  '【': '[',
  '】': ']',
  '《': '<',
  '》': '>',
  '“': '"',
  '”': '"',
  '‘': "'",
  '’': "'",
  '、': ',',
  '｜': '|'
}

const lowSignalAnchorTokens = new Set(['的', '地', '得', '了', '着', '过', '吗', '呢', '吧', '啊', '呀', '将', '把', '被', '和', '及', '与'])

function normalizeSemanticUnit(text) {
  const raw = String(text || '')
  if (!raw) {
    return ''
  }
  if (/^\s+$/.test(raw)) {
    return ' '
  }
  return Array.from(raw)
    .map(char => semanticPunctuationMap[char] || char)
    .join('')
    .toLowerCase()
}

function createDiffToken(text) {
  const raw = String(text || '')
  const normalized = normalizeSemanticUnit(raw)
  const isWhitespace = /^\s+$/.test(raw)
  const isPunctuation = /^[,.;:!?()\[\]<>"'|]+$/.test(normalized)
  return {
    text: raw,
    key: normalized,
    ignorable: isWhitespace,
    anchorIgnorable: isWhitespace || isPunctuation || lowSignalAnchorTokens.has(normalized)
  }
}

function splitChars(text) {
  return Array.from(String(text || '')).map(char => createDiffToken(char))
}

function splitByRegex(text) {
  const matches = String(text || '').match(/\s+|[A-Za-z0-9_]+|[\u3400-\u9fff]+|[^\sA-Za-z0-9_\u3400-\u9fff]/g) || []
  return matches.map(part => createDiffToken(part))
}

function segmentText(text) {
  const raw = String(text || '')
  if (!raw) {
    return []
  }

  if (typeof Intl !== 'undefined' && typeof Intl.Segmenter === 'function') {
    const segmenter = new Intl.Segmenter('zh-CN', { granularity: 'word' })
    return Array.from(segmenter.segment(raw), item => createDiffToken(item.segment))
  }

  return splitByRegex(raw)
}

function buildFallbackDiffSegments(leftTokens, rightTokens) {
  let prefix = 0
  const leftLength = leftTokens.length
  const rightLength = rightTokens.length

  while (prefix < leftLength && prefix < rightLength && leftTokens[prefix].key === rightTokens[prefix].key) {
    prefix += 1
  }

  let leftSuffix = leftLength - 1
  let rightSuffix = rightLength - 1
  while (leftSuffix >= prefix && rightSuffix >= prefix && leftTokens[leftSuffix].key === rightTokens[rightSuffix].key) {
    leftSuffix -= 1
    rightSuffix -= 1
  }

  return {
    left: [
      { text: leftTokens.slice(0, prefix).map(item => item.text).join(''), changed: false },
      { text: leftTokens.slice(prefix, leftSuffix + 1).map(item => item.text).join(''), changed: true },
      { text: leftTokens.slice(leftSuffix + 1).map(item => item.text).join(''), changed: false }
    ],
    right: [
      { text: rightTokens.slice(0, prefix).map(item => item.text).join(''), changed: false },
      { text: rightTokens.slice(prefix, rightSuffix + 1).map(item => item.text).join(''), changed: true },
      { text: rightTokens.slice(rightSuffix + 1).map(item => item.text).join(''), changed: false }
    ]
  }
}

function buildCharDiffSegments(leftText, rightText) {
  const leftTokens = splitChars(leftText)
  const rightTokens = splitChars(rightText)
  const leftLength = leftTokens.length
  const rightLength = rightTokens.length

  if (!leftLength && !rightLength) {
    return { left: [], right: [] }
  }

  if (leftLength * rightLength > 120000) {
    return buildFallbackDiffSegments(leftTokens, rightTokens)
  }

  const dp = Array.from({ length: leftLength + 1 }, () => Array(rightLength + 1).fill(0))

  for (let i = leftLength - 1; i >= 0; i -= 1) {
    for (let j = rightLength - 1; j >= 0; j -= 1) {
      if (leftTokens[i].key === rightTokens[j].key) {
        dp[i][j] = dp[i + 1][j + 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1])
      }
    }
  }

  const left = []
  const right = []
  let i = 0
  let j = 0

  function findNextIndex(tokens, startIndex, target) {
    for (let index = startIndex; index < tokens.length; index += 1) {
      if (tokens[index].key === target.key) {
        return index
      }
    }
    return -1
  }

  function shouldPreferInsert(leftIndex, rightIndex) {
    const leftChar = leftTokens[leftIndex]
    const rightChar = rightTokens[rightIndex]
    const leftCharNextInRight = findNextIndex(rightTokens, rightIndex + 1, leftChar)
    const rightCharNextInLeft = findNextIndex(leftTokens, leftIndex + 1, rightChar)

    if (leftCharNextInRight === -1 && rightCharNextInLeft === -1) {
      return false
    }
    if (leftCharNextInRight === -1) {
      return false
    }
    if (rightCharNextInLeft === -1) {
      return true
    }

    const insertDistance = leftCharNextInRight - rightIndex
    const deleteDistance = rightCharNextInLeft - leftIndex
    return insertDistance < deleteDistance
  }

  while (i < leftLength && j < rightLength) {
    if (leftTokens[i].key === rightTokens[j].key) {
      left.push({ text: leftTokens[i].text, changed: false })
      right.push({ text: rightTokens[j].text, changed: false })
      i += 1
      j += 1
      continue
    }

    if (dp[i + 1][j] > dp[i][j + 1]) {
      left.push({ text: leftTokens[i].text, changed: true })
      i += 1
      continue
    }

    if (dp[i + 1][j] < dp[i][j + 1]) {
      right.push({ text: rightTokens[j].text, changed: true })
      j += 1
      continue
    }

    if (shouldPreferInsert(i, j)) {
      right.push({ text: rightTokens[j].text, changed: true })
      j += 1
      continue
    }

    if (rightTokens[j + 1] && leftTokens[i].key === rightTokens[j + 1].key) {
      right.push({ text: rightTokens[j].text, changed: true })
      j += 1
      continue
    }

    right.push({ text: rightTokens[j].text, changed: true })
    left.push({ text: leftTokens[i].text, changed: true })
    i += 1
    j += 1
  }

  while (i < leftLength) {
    left.push({ text: leftTokens[i].text, changed: true })
    i += 1
  }

  while (j < rightLength) {
    right.push({ text: rightTokens[j].text, changed: true })
    j += 1
  }

  return {
    left: mergeDiffSegments(left),
    right: mergeDiffSegments(right)
  }
}

function collectAnchors(leftTokens, rightTokens) {
  const leftComparable = leftTokens.filter(token => !token.anchorIgnorable)
  const rightComparable = rightTokens.filter(token => !token.anchorIgnorable)

  if (!leftComparable.length && !rightComparable.length) {
    return []
  }

  if (leftComparable.length * rightComparable.length > 40000) {
    return null
  }

  const dp = Array.from({ length: leftComparable.length + 1 }, () => Array(rightComparable.length + 1).fill(0))

  for (let i = leftComparable.length - 1; i >= 0; i -= 1) {
    for (let j = rightComparable.length - 1; j >= 0; j -= 1) {
      if (leftComparable[i].key === rightComparable[j].key) {
        dp[i][j] = dp[i + 1][j + 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1])
      }
    }
  }

  const anchors = []
  let i = 0
  let j = 0
  while (i < leftComparable.length && j < rightComparable.length) {
    if (leftComparable[i].key === rightComparable[j].key) {
      anchors.push({
        leftIndex: leftComparable[i].index,
        rightIndex: rightComparable[j].index,
        leftText: leftComparable[i].text,
        rightText: rightComparable[j].text
      })
      i += 1
      j += 1
      continue
    }
    if (dp[i + 1][j] >= dp[i][j + 1]) {
      i += 1
    } else {
      j += 1
    }
  }

  return anchors
}

function buildTokenDiffSegments(leftText, rightText) {
  const leftTokens = segmentText(leftText).map((token, index) => ({ ...token, index }))
  const rightTokens = segmentText(rightText).map((token, index) => ({ ...token, index }))
  const anchors = collectAnchors(leftTokens, rightTokens)

  if (anchors === null) {
    return buildCharDiffSegments(leftText, rightText)
  }

  const left = []
  const right = []
  let leftCursor = 0
  let rightCursor = 0

  function pushGap(nextLeft, nextRight) {
    const leftGap = leftTokens.slice(leftCursor, nextLeft).map(token => token.text).join('')
    const rightGap = rightTokens.slice(rightCursor, nextRight).map(token => token.text).join('')
    const refined = buildCharDiffSegments(leftGap, rightGap)
    left.push(...refined.left)
    right.push(...refined.right)
  }

  for (const anchor of anchors) {
    pushGap(anchor.leftIndex, anchor.rightIndex)
    left.push({ text: anchor.leftText, changed: false })
    right.push({ text: anchor.rightText, changed: false })
    leftCursor = anchor.leftIndex + 1
    rightCursor = anchor.rightIndex + 1
  }

  pushGap(leftTokens.length, rightTokens.length)

  return {
    left: mergeDiffSegments(left),
    right: mergeDiffSegments(right)
  }
}

function buildDiffSegments(leftText, rightText) {
  return buildTokenDiffSegments(leftText, rightText)
}

function mergeDiffSegments(segments) {
  const merged = []
  for (const segment of segments) {
    if (!segment.text) {
      continue
    }
    const last = merged[merged.length - 1]
    if (last && last.changed === segment.changed) {
      last.text += segment.text
      continue
    }
    merged.push({ ...segment })
  }
  return merged
}

const orderedListLeadPattern = /^(首先|其次|再次|然后|最后|一是|二是|三是|四是|五是|其一|其二|其三|其四|其五|第[一二三四五六七八九十]+|[（(]?\d+[)）][、.]?)/
const orderedSplitPattern = /(首先|其次|再次|然后|最后|一是|二是|三是|四是|五是|其一|其二|其三|其四|其五|第[一二三四五六七八九十]+|[（(]?\d+[)）][、.]?)/g

function collectRangeItems(text, regex) {
  const items = []
  let match = regex.exec(text)
  while (match) {
    const value = match[0].trim()
    if (value) {
      items.push({
        start: Array.from(text.slice(0, match.index)).length,
        end: Array.from(text.slice(0, match.index + match[0].length)).length,
        text: value
      })
    }
    match = regex.exec(text)
  }
  return items
}

function collectSequentialMarkerItems(text) {
  const raw = String(text || '')
  const matches = [...raw.matchAll(orderedSplitPattern)]
  if (matches.length < 2) {
    return []
  }

  return matches.map((match, index) => {
    const start = Array.from(raw.slice(0, match.index)).length
    const nextIndex = index + 1 < matches.length ? matches[index + 1].index : raw.length
    const chunk = raw.slice(match.index, nextIndex).trim()
    return {
      start,
      end: start + Array.from(chunk).length,
      text: chunk
    }
  }).filter(item => item.text.length >= 6)
}

function splitCommaClauses(text) {
  return String(text || '')
    .split(/[，,](?=(?:首先|其次|再次|然后|最后|一是|二是|三是|四是|五是|其一|其二|其三|其四|其五))/)
    .map(item => item.trim())
    .filter(Boolean)
}

function detectLongParagraphList(text) {
  const raw = String(text || '')
  const compact = raw.trim()
  if (!compact || compact.length < 30 || /\n/.test(compact)) {
    return null
  }

  const sequentialItems = collectSequentialMarkerItems(raw)
  if (sequentialItems.length >= 2 && sequentialItems.length <= 8) {
    return { type: 'ol', items: sequentialItems }
  }

  const commaOrderedParts = splitCommaClauses(raw)
  if (commaOrderedParts.length >= 2 && commaOrderedParts.length <= 8) {
    return {
      type: 'ol',
      items: (() => {
        const items = []
        let searchStart = 0
        for (const part of commaOrderedParts) {
          const found = raw.indexOf(part, searchStart)
          const start = found === -1 ? searchStart : Array.from(raw.slice(0, found)).length
          const end = start + Array.from(part).length
          items.push({ start, end, text: part })
          searchStart = found === -1 ? searchStart + part.length : found + part.length
        }
        return items
      })()
    }
  }

  const semicolonItems = collectRangeItems(raw, /[^；;]+[；;]?\s*/g)
  if (
    semicolonItems.length >= 2 &&
    semicolonItems.length <= 8 &&
    semicolonItems.every(item => item.text.length >= 6 && item.text.length <= 120)
  ) {
    return { type: 'ul', items: semicolonItems }
  }

  const sentenceItems = collectRangeItems(raw, /[^。！？!?]+[。！？!?]?\s*/g)
  if (sentenceItems.length >= 2 && sentenceItems.length <= 6) {
    const orderedCount = sentenceItems.filter(item => orderedListLeadPattern.test(item.text)).length
    if (orderedCount >= 1) {
      return { type: 'ol', items: sentenceItems }
    }
    if (sentenceItems.every(item => item.text.length >= 8 && item.text.length <= 80)) {
      return { type: 'ul', items: sentenceItems }
    }
  }

  const commaItems = collectRangeItems(raw, /[^，,]+[，,]?\s*/g)
  if (
    compact.length >= 40 &&
    commaItems.length >= 3 &&
    commaItems.length <= 6 &&
    commaItems.every(item => item.text.length >= 6 && item.text.length <= 40)
  ) {
    return { type: 'ul', items: commaItems }
  }

  return null
}

function sliceSegmentsByRange(segments, start, end) {
  const result = []
  let cursor = 0

  for (const segment of segments) {
    const chars = Array.from(segment.text)
    const nextCursor = cursor + chars.length
    if (nextCursor <= start) {
      cursor = nextCursor
      continue
    }
    if (cursor >= end) {
      break
    }

    const from = Math.max(0, start - cursor)
    const to = Math.min(chars.length, end - cursor)
    const textPart = chars.slice(from, to).join('')
    if (textPart) {
      result.push({ text: textPart, changed: segment.changed })
    }
    cursor = nextCursor
  }

  return mergeDiffSegments(result)
}

function renderSegmentsHtml(segments) {
  return mergeDiffSegments(segments)
    .map(segment => {
      const content = escapeHtml(segment.text)
      return segment.changed ? `<span class="diff-highlight">${content}</span>` : content
    })
    .join('')
}

function renderDiffHtml(sourceText, targetText, mode) {
  const displayText = mode === 'original' ? sourceText : targetText
  const otherText = mode === 'original' ? targetText : sourceText
  if (String(displayText || '').length + String(otherText || '').length > 20000) {
    return `<div class="result-text-block">${escapeHtml(displayText || '')}</div>`
  }
  const structuredList = detectLongParagraphList(displayText)

  if (structuredList) {
    const tagName = structuredList.type
    const itemsHtml = structuredList.items.map((item, idx) => {
      const subSource = mode === 'original' ? item.text : findListItemInOther(item.text, idx, otherText)
      const subTarget = mode === 'original' ? findListItemInOther(item.text, idx, otherText) : item.text
      const diff = buildDiffSegments(subSource, subTarget)
      const segments = mode === 'original' ? diff.left : diff.right
      return `<li>${renderSegmentsHtml(segments).trim()}</li>`
    }).join('')
    return `<${tagName} class="result-auto-list">${itemsHtml}</${tagName}>`
  }

  const diff = buildDiffSegments(sourceText, targetText)
  const segments = mode === 'original' ? diff.left : diff.right
  return `<div class="result-text-block">${renderSegmentsHtml(segments)}</div>`
}

function findListItemInOther(itemText, index, otherText) {
  const otherList = detectLongParagraphList(otherText)
  if (otherList && otherList.items.length > index) {
    return otherList.items[index].text
  }
  const idx = otherText.indexOf(itemText)
  if (idx !== -1) {
    return otherText.slice(idx, idx + itemText.length)
  }
  return itemText
}

const highlightedPolishedHtml = computed(() => renderDiffHtml(result.value?.original, result.value?.polished, 'polished'))
const highlightedDocOriginalHtml = computed(() => renderDiffHtml(docResult.value?.original, docResult.value?.polished, 'original'))
const highlightedDocPolishedHtml = computed(() => renderDiffHtml(docResult.value?.original, docResult.value?.polished, 'polished'))

const formData = ref({
  sentenceFile: documentDraft.value.sentenceFile || '',
  sentenceFileId: documentDraft.value.sentenceFileId || null,
  terminologyFile: documentDraft.value.terminologyFile || '',
  terminologyFileId: documentDraft.value.terminologyFileId || null,
  sourceFile: documentDraft.value.sourceFile || '',
  outputPath: documentDraft.value.outputPath || '已润色文档',
  requirements: documentDraft.value.requirements || ''
})

const currentView = computed(() => (route.path === '/polish/document' ? 'document' : 'text'))

let pendingLocalFile = null
let documentProgressTimer = null

const acceptedDocChangeCount = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.filter(item => item.status === 'accepted' || item.status === 'custom').length
})

const confirmedDocChangeCount = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.filter(item => item.status !== 'pending').length
})

const allDocumentChangesSelected = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.length > 0 && items.every(item => item.status === 'accepted' || item.status === 'custom')
})

function toggleAllDocumentChanges() {
  const items = docResult.value?.changeDetails || []
  const nextValue = !allDocumentChangesSelected.value
  items.forEach(item => {
    item.accepted = nextValue
    item.status = nextValue ? 'accepted' : 'pending'
  })
}

async function persistDocumentDecisions(showMessage = false, resetAfterSubmit = false) {
  if (!docResult.value || !docResult.value.changeDetails?.length) {
    ElMessage.warning('当前没有可提交的润色结果')
    return null
  }

  const payload = docResult.value.changeDetails.map(item => ({
    before: item.before,
    after: item.after,
    type: item.type,
    status: item.status,
    paragraph: item.paragraph,
    accepted: item.status === 'accepted' || item.status === 'custom'
  }))

  docDecisionSaving.value = true
  try {
    const resp = await polishAPI.submitDocumentFeedback(
      docResult.value.id,
      docResult.value.sourceName,
      payload
    )
    const data = resp.data || {}
    if (docResult.value && data.document_id) {
      docResult.value.id = data.document_id
    }
    if (docResult.value && data.raw_url) {
      docResult.value.rawUrl = data.raw_url
    }
    if (showMessage) {
      if (data.processed_count > 0) {
        ElMessage.success(`已写入 ${data.processed_count} 条平台反馈句式`)
      } else {
        ElMessage.success('文档反馈已提交，本次没有新增句式写入')
      }
    }
    await loadDocumentFeedbackStats()
    if (resetAfterSubmit) {
      resetForm()
    }
    return data
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`提交失败：${errorMsg}`)
    return null
  } finally {
    docDecisionSaving.value = false
  }
}

async function acceptDocumentIssue(issue) {
  issue.status = 'accepted'
  issue.accepted = true
  issue.editing = false
  await persistDocumentDecisions()
}

async function rejectDocumentIssue(issue) {
  issue.status = 'rejected'
  issue.accepted = false
  issue.editing = false
  await persistDocumentDecisions()
}

function editDocumentIssue(issue) {
  issue.customAfter = issue.after
  issue.editing = true
}

async function saveCustomDocumentIssue(issue) {
  const nextValue = String(issue.customAfter || '').trim()
  if (!nextValue) {
    ElMessage.warning('请填写自定义替换文本')
    return
  }
  issue.after = nextValue
  issue.status = 'custom'
  issue.accepted = true
  issue.editing = false
  await persistDocumentDecisions()
}

function cancelCustomDocumentIssue(issue) {
  issue.customAfter = issue.after
  issue.editing = false
}

async function acceptAllDocumentIssues() {
  filteredDocIssues.value.forEach(issue => {
    issue.status = 'accepted'
    issue.accepted = true
    issue.editing = false
  })
  await persistDocumentDecisions()
}

async function rejectAllDocumentIssues() {
  filteredDocIssues.value.forEach(issue => {
    issue.status = 'rejected'
    issue.accepted = false
    issue.editing = false
  })
  await persistDocumentDecisions()
}

function scrollToDocumentPreview() {
  if (!docResult.value?.id) {
    ElMessage.warning('暂无可预览的 Word 文件')
    return
  }
  window.open(docResult.value.rawUrl || `/api/polish/${docResult.value.id}/raw`, '_blank')
}

function renderIssueSuggestion(issue) {
  const before = String(issue.before || '')
  const after = String(issue.after || '')
  if (!after) return ''
  if (!before || before === after) return escapeHtml(after)

  let prefixLength = 0
  const maxPrefixLength = Math.min(before.length, after.length)
  while (prefixLength < maxPrefixLength && before[prefixLength] === after[prefixLength]) {
    prefixLength += 1
  }

  let suffixLength = 0
  const maxSuffixLength = Math.min(before.length - prefixLength, after.length - prefixLength)
  while (
    suffixLength < maxSuffixLength &&
    before[before.length - 1 - suffixLength] === after[after.length - 1 - suffixLength]
  ) {
    suffixLength += 1
  }

  const prefix = after.slice(0, prefixLength)
  const changed = after.slice(prefixLength, after.length - suffixLength)
  const suffix = suffixLength > 0 ? after.slice(after.length - suffixLength) : ''
  if (!changed) return escapeHtml(after)
  return `${escapeHtml(prefix)}<mark class="mark-after">${escapeHtml(changed)}</mark>${escapeHtml(suffix)}`
}

const docIssueTypeOptions = [
  { label: '系统规则', value: 'system_rule' },
  { label: '术语替换', value: 'replacement_rule' },
  { label: '禁止规则', value: 'forbidden_rule' },
  { label: '句式适用', value: 'sentence_applicability_rule' },
  { label: '祈使句规则', value: 'imperative_rule' },
  { label: '格式规则', value: 'format_rule' }
]

const filteredDocIssues = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.filter(item => {
    if (docFilterType.value && item.filterType !== docFilterType.value) return false
    if (docFilterTriggerLevel.value && item.triggerLevel !== docFilterTriggerLevel.value) return false
    return true
  })
})

function normalizeChangeType(type) {
  const typeMap = {
    ai: '系统规则',
    term: '术语替换',
    terminology: '术语替换',
    terminology_rule: '术语替换',
    forbidden: '禁止规则',
    forbidden_rule: '禁止规则',
    imperative: '祈使句规则',
    imperative_rule: '祈使句规则',
    preferred_sentences: '句式',
    forbidden_words: '禁用词',
    passive_voice: '语态',
    double_negative: '句式',
    informal: '表达',
    sentence_length: '长句',
    pronoun_reference: '指代',
    style: '句式适用',
    sentence_applicability_rule: '句式适用',
    format: '格式规则',
    punctuation: '格式规则'
  }
  return typeMap[type] || (type ? String(type) : '润色')
}

function normalizeDocFilterType(type) {
  const value = String(type || '')
  if (['term', 'terminology', 'terminology_rule', 'replacement_rule'].includes(value)) return 'replacement_rule'
  if (['forbidden', 'forbidden_rule', 'forbidden_words'].includes(value)) return 'forbidden_rule'
  if (['imperative', 'imperative_rule'].includes(value)) return 'imperative_rule'
  if (['style', 'preferred_sentences', 'sentence_applicability_rule', 'passive_voice', 'double_negative', 'informal', 'sentence_length', 'pronoun_reference'].includes(value)) return 'sentence_applicability_rule'
  if (['format', 'punctuation', 'format_rule'].includes(value)) return 'format_rule'
  return 'system_rule'
}

function getDocTypeTagType(filterType) {
  const typeMap = {
    system_rule: 'info',
    replacement_rule: 'primary',
    forbidden_rule: 'danger',
    imperative_rule: 'warning',
    format_rule: 'info',
    sentence_applicability_rule: 'success'
  }
  return typeMap[filterType] || 'info'
}

function getTriggerLevel(count) {
  if (count >= 3) return 'high'
  if (count >= 2) return 'medium'
  return 'low'
}

function buildDocIssueReason(change, index) {
  if (change.reason) return change.reason
  if (change.rule_name) return change.rule_name
  const filterType = normalizeDocFilterType(change.type)
  if (filterType === 'replacement_rule') return `术语对照表 #${change.rule_id || index + 1}`
  if (filterType === 'forbidden_rule') return '禁止规则'
  if (filterType === 'imperative_rule') return '祈使句规则'
  if (filterType === 'sentence_applicability_rule') return '句式适用规则'
  if (filterType === 'system_rule') return '系统规则'
  return '格式规则'
}

function issueBasisText(issue) {
  const parts = []
  parts.push(issue.ruleName || issue.reason || issue.typeLabel || '润色规则')
  if (issue.type) parts.push(`type=${issue.type}`)
  if (issue.paragraph) parts.push(`段落 #${issue.paragraph}`)
  return parts.join(' / ')
}

function stripTrailingPunctuation(text) {
  return String(text || '').trim().replace(/[。.!！？?，,;；:：]+$/g, '')
}

function isLowValueDocChange(item) {
  const before = String(item.before || '').trim()
  const after = String(item.after || '').trim()
  if (!before || !after) return false
  const beforeCore = stripTrailingPunctuation(before)
  const afterCore = stripTrailingPunctuation(after)
  if (beforeCore.length <= 4 && afterCore === `请${beforeCore}`) return true
  if (beforeCore.startsWith('请') && beforeCore.length <= 4 && afterCore === beforeCore.slice(1)) return true
  if (item.ruleName && item.ruleName !== '基础规范化') return false
  if (!['format_rule'].includes(item.filterType)) return false
  if (beforeCore === afterCore) return true
  return before.length <= 4 && after.startsWith(before)
}

function getDocDisplayPriority(filterType) {
  const priorityMap = {
    sentence_applicability_rule: 100,
    replacement_rule: 90,
    forbidden_rule: 80,
    imperative_rule: 70,
    system_rule: 40,
    format_rule: 10
  }
  return priorityMap[filterType] || 30
}

function dedupeDocIssues(items) {
  const selected = new Map()
  const order = []
  items.forEach(item => {
    const before = String(item.before || '').replace(/\s+/g, ' ').trim()
    const after = String(item.after || '').replace(/\s+/g, ' ').trim()
    const key = before || after
    if (!key) return
    const existing = selected.get(key)
    if (!existing) {
      selected.set(key, item)
      order.push(key)
      return
    }
    if (getDocDisplayPriority(item.filterType) > getDocDisplayPriority(existing.filterType)) {
      selected.set(key, item)
    }
  })
  return order.map(key => selected.get(key)).filter(Boolean)
}

function normalizeDocumentChanges(changes) {
  const rawItems = (changes || []).map((change, index) => {
    const before = change.before || change.original || ''
    const after = change.after || change.polished || ''
    const filterType = normalizeDocFilterType(change.type)
    return {
      rowKey: `${index}-${before}-${after}`,
      displayIndex: index + 1,
      before,
      after,
      type: change.type || '',
      ruleName: change.rule_name || '',
      filterType,
      typeLabel: normalizeChangeType(change.type),
      typeTagType: getDocTypeTagType(filterType),
      paragraph: change.paragraph || change.paragraph_index || null,
      reason: buildDocIssueReason(change, index),
      status: 'pending',
      editing: false,
      customAfter: after,
      accepted: false,
      needCorrection: false
    }
  })
  const hasPreferredItem = rawItems.some(item => item.filterType !== 'format_rule')
  const filteredItems = rawItems.filter(item => {
    const before = (item.before || '').replace(/\s+/g, ' ').trim()
    const after = (item.after || '').replace(/\s+/g, ' ').trim()
    if (hasPreferredItem && item.filterType === 'format_rule') {
      return false
    }
    if (!before && !after) {
      return false
    }
    if (isLowValueDocChange(item)) {
      return false
    }
    return before !== after || (!before && after) || (before && !after)
  })

  const countMap = filteredItems.reduce((acc, item) => {
    const key = `${item.filterType}:${item.before}:${item.after}`
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})

  const visibleItems = dedupeDocIssues(filteredItems)

  return visibleItems.map(item => {
    const triggerCount = countMap[`${item.filterType}:${item.before}:${item.after}`] || 1
    return {
      ...item,
      triggerCount,
      triggerLevel: getTriggerLevel(triggerCount)
    }
  })
}

function applyDocumentResult(data, fallbackSourceName = '') {
  const normalizedChanges = normalizeDocumentChanges(data?.changes || [])
  docFilterType.value = ''
  docFilterTriggerLevel.value = ''
  docResult.value = {
    id: data?.id,
    sourceName: fallbackSourceName || formData.value.sourceFile || data?.download_filename || '',
    original: data?.original || '',
    polished: data?.polished || '',
    changes: normalizedChanges.length,
    changeDetails: normalizedChanges,
    reportFile: data?.report_file || data?.reportFile,
    rawUrl: data?.raw_url || (data?.id ? `/api/polish/${data.id}/raw` : ''),
    download_filename: data?.download_filename,
    file_type: data?.file_type
  }
}

function onDocumentTerminologyChange(fileId) {
  const selected = termFileOptions.value.find(item => item.id === fileId)
  formData.value.terminologyFile = selected?.name || ''
}

function startDocumentProgress() {
  stopDocumentProgress()
  polishProgress.value = 3
  polishProgressMsg.value = '正在上传文件...'
  documentProgressTimer = window.setInterval(() => {
    if (!loading.value) {
      stopDocumentProgress()
      return
    }
    if (polishProgress.value < 25) {
      polishProgress.value += 4
      polishProgressMsg.value = '正在解析文档...'
      return
    }
    if (polishProgress.value < 55) {
      polishProgress.value += 3
      polishProgressMsg.value = '正在加载规则...'
      return
    }
    if (polishProgress.value < 88) {
      polishProgress.value += 2
      polishProgressMsg.value = '正在润色内容...'
    }
  }, 500)
}

function stopDocumentProgress() {
  if (documentProgressTimer) {
    window.clearInterval(documentProgressTimer)
    documentProgressTimer = null
  }
}

function openFilePicker(field, type) {
  currentPickerField.value = field
  if (type === 'knowledge') {
    loadKnowledgeTree()
    selectedKnowledgeFile.value = null
    filePickerVisible.value = true
  }
}

function openTextSentencePicker() {
  openFilePicker('textSentenceFile', 'knowledge')
}

function openTextTerminologyPicker() {
  openFilePicker('textTerminologyFile', 'knowledge')
}

function clearTextSentenceFile() {
  textSentenceFileName.value = ''
  textSentenceFileId.value = null
}

function clearTextTerminologyFile() {
  textTerminologyFileName.value = ''
  textTerminologyFileId.value = null
}

async function loadKnowledgeTree() {
  try {
    const resp = await knowledgeAPI.getTree()
    const rawData = resp.data || []
    knowledgeTree.value = flattenTree(rawData)
    // Filter: only show files from the relevant subtree
    let filteredData = rawData
    if (currentPickerField.value === 'sentenceFile' || currentPickerField.value === 'textSentenceFile') {
      const n = findNodeByName(rawData, '句式清单')
      filteredData = n ? [n] : rawData
    } else if (currentPickerField.value === 'textTerminologyFile') {
      const n = findNodeByName(rawData, '术语库')
      filteredData = n ? [n] : rawData
    }
    knowledgeTreeList.value = flattenKnowledgeList(filteredData)
    selectedKnowledgeFile.value = null
  } catch (e) {
    ElMessage.error('加载知识库失败')
  }
}

function findNodeByName(nodes, name) {
  for (const node of nodes) {
    if (node.name === name) return node
    if (node.children && node.children.length > 0) {
      const found = findNodeByName(node.children, name)
      if (found) return found
    }
  }
  return null
}

function flattenTree(nodes) {
  return nodes.map(node => {
    const files = (node.files || []).map(f => ({
      ...f,
      nodeKey: `file-${f.id}`,
      children: [],
      isFile: true,
      parentFolder: node.name
    }))
    const children = flattenTree(node.children || [])
    return {
      ...node,
      nodeKey: `folder-${node.id}`,
      children: [...files, ...children]
    }
  })
}

function flattenKnowledgeList(nodes, depth = 0) {
  const items = []
  nodes.forEach(node => {
    items.push({
      ...node,
      nodeKey: `folder-${node.id}`,
      depth,
      isFile: false
    })

    const files = (node.files || []).map(file => ({
      ...file,
      nodeKey: `file-${file.id}`,
      depth: depth + 1,
      isFile: true,
      parentFolder: node.name
    }))
    items.push(...files)

    if (node.children && node.children.length > 0) {
      items.push(...flattenKnowledgeList(node.children, depth + 1))
    }
  })
  return items
}

function onTreeNodeClick(data) {
  if (data.isFile || data.file_path) {
    selectedKnowledgeFile.value = data
  } else {
    selectedKnowledgeFile.value = null
  }
}

function confirmKnowledgeFile() {
  if (selectedKnowledgeFile.value && currentPickerField.value) {
    if (currentPickerField.value === 'textSentenceFile') {
      textSentenceFileName.value = selectedKnowledgeFile.value.name
      textSentenceFileId.value = selectedKnowledgeFile.value.id
    } else if (currentPickerField.value === 'textTerminologyFile') {
      textTerminologyFileName.value = selectedKnowledgeFile.value.name
      textTerminologyFileId.value = selectedKnowledgeFile.value.id
    } else {
      formData.value[currentPickerField.value] = selectedKnowledgeFile.value.name
      formData.value[currentPickerField.value + 'Id'] = selectedKnowledgeFile.value.id
    }
    filePickerVisible.value = false
    selectedKnowledgeFile.value = null
  }
}

function openLocalFilePicker() {
  currentPickerField.value = 'sourceFile'
  localFileInputRef.value?.click()
}

function onLocalFileSelected(event) {
  const file = event.target.files?.[0]
  if (file) {
    pendingLocalFile = file
    formData.value.sourceFile = file.name
  }
  if (localFileInputRef.value) {
    localFileInputRef.value.value = ''
  }
}

async function submitPolish() {
  if (!pendingLocalFile) {
    ElMessage.warning('请选择待润色文件')
    return
  }
  
  loading.value = true
  startDocumentProgress()
  
  const payload = new FormData()
  payload.append('file', pendingLocalFile)
  if (formData.value.sentenceFileId) {
    payload.append('sentence_file_id', formData.value.sentenceFileId)
  }
  if (formData.value.terminologyFileId) {
    payload.append('terminology_file_id', formData.value.terminologyFileId)
  }
  if (formData.value.requirements) {
    payload.append('requirements', formData.value.requirements)
  }
  
  try {
    const sourceName = pendingLocalFile?.name || formData.value.sourceFile || ''
    const data = await polishStore.submitDocumentPolish(payload, sourceName)
    polishProgress.value = 100
    polishProgressMsg.value = '润色完成'
    stopDocumentProgress()
    applyDocumentResult(data, sourceName)
    ElMessage.success('润色成功')
    // 清空已选择的文件
    pendingLocalFile = null
    if (localFileInputRef.value) {
      localFileInputRef.value.value = ''
    }
    await nextTick()
    formData.value.sourceFile = ''
    formData.value.sentenceFile = ''
    formData.value.sentenceFileId = null
    formData.value.terminologyFile = ''
    formData.value.terminologyFileId = null
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`润色失败：${errorMsg}`)
    polishProgress.value = 0
    polishProgressMsg.value = ''
    stopDocumentProgress()
  } finally {
    loading.value = false
    stopDocumentProgress()
    // pendingLocalFile 在成功/失败分支已处理，此处不再重复清空
  }
}

function resetForm() {
  formData.value = {
    sentenceFile: '',
    sentenceFileId: null,
    terminologyFile: '',
    terminologyFileId: null,
    sourceFile: '',
    outputPath: '已润色文档',
    requirements: ''
  }
  pendingLocalFile = null
  selectedKnowledgeFile.value = null
  docResult.value = null
  docFeedbackLoading.value = false
  polishProgress.value = 0
  polishProgressMsg.value = ''
  stopDocumentProgress()
  polishStore.clearDocumentSession()
}

function downloadPolishedDoc() {
  if (!docResult.value) {
    ElMessage.warning('暂无润色结果')
    return
  }
  // 如果后端已保存 DOCX 文件，通过 API 下载原始文件
  if (docResult.value.id) {
    const downloadName = docResult.value.download_filename || 'polished_document.docx'
    polishAPI.downloadPolishedFile(docResult.value.id, downloadName)
    return
  }
  // 纯文本结果 fallback
  const ext = docResult.value.fileType === 'docx' ? '.docx' : '.txt'
  const blob = new Blob([docResult.value.polished], { type: 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `polished_document${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

function downloadReport() {
  if (!docResult.value || !docResult.value.reportFile || !docResult.value.id) {
    ElMessage.warning('暂无润色报告')
    return
  }
  polishAPI.downloadPolishedReport(docResult.value.id, docResult.value.reportFile)
}

async function doPolish() {
  if (!originalText.value.trim()) {
    ElMessage.info('请先输入需要润色的文本')
    return
  }
  loading.value = true
  try {
    const resp = await polishAPI.text(originalText.value, textSentenceFileId.value, textTerminologyFileId.value)
    const data = resp.data || {}
    result.value = {
      original: data.original || originalText.value,
      polished: data.polished || data.original || originalText.value,
      changes: data.changes?.length || 0
    }
    if (!data.polished || data.polished === data.original) {
      ElMessage.info('润色完成，未检测到需要修改的内容')
    } else {
      ElMessage.success('润色完成')
    }
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`润色失败：${errorMsg}`)
    result.value = null
  } finally {
    loading.value = false
  }
}

function clearAll() {
  originalText.value = ''
  result.value = null
  textSentenceFileName.value = ''
  textSentenceFileId.value = null
  feedbackAccuracy.value = 80
  feedbackCorrections.value = ''
  feedbackTarget.value = 'terminology'
}

function copyResult() {
  navigator.clipboard.writeText(result.value.polished).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => ElMessage.info('复制失败，请手动复制'))
}

function downloadResult() {
  const blob = new Blob([result.value.polished], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'polished_document.txt'
  a.click()
  URL.revokeObjectURL(url)
}

async function submitFeedback() {
  if (!result.value) {
    ElMessage.warning('请先完成润色再提交反馈')
    return
  }
  // 验证文件选择（准确率100%时无需修正，跳过文件校验）
  if (feedbackAccuracy.value < 100) {
  }
  feedbackLoading.value = true
  try {
    const resp = await polishAPI.submitFeedback(
      result.value.original,
      result.value.polished,
      feedbackAccuracy.value,
      feedbackCorrections.value,
      feedbackTarget.value,
      textTerminologyFileId.value,
      textSentenceFileId.value
    )
    const data = resp.data || {}
    const targetName = feedbackTarget.value === 'terminology' ? '平台反馈的术语对照表' : '平台反馈的句式清单'
    if (data.processed_count > 0) {
      ElMessage.success(`反馈已提交，已将 ${data.processed_count} 条修正写入${targetName}`)
    } else {
      ElMessage.success('反馈已提交')
    }
    feedbackCorrections.value = ''
    await loadFeedbackStats()
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`反馈失败：${errorMsg}`)
  } finally {
    feedbackLoading.value = false
  }
}

async function loadFeedbackStats() {
  try {
    const resp = await polishAPI.getFeedbackStats()
    feedbackStats.value = { totalCount: resp.data.total_count || 0, averageAccuracy: resp.data.average_accuracy || 0 }
  } catch (e) {
    console.error('加载准确率统计失败:', e)
  }
}

async function loadPolishEngineStatus() {
  try {
    const resp = await systemAPI.getAIStatus()
    const providers = resp.data?.providers || {}
    if (providers.kimi?.status === 'ok') {
      currentPolishEngine.value = 'Kimi'
      return
    }
    currentPolishEngine.value = '本地润色'
  } catch (e) {
    console.error('加载润色引擎状态失败:', e)
    currentPolishEngine.value = '本地润色'
  }
}

async function loadDocumentFeedbackStats() {
  try {
    const resp = await polishAPI.getDocumentFeedbackStats()
    docFeedbackStats.value = {
      totalDocs: resp.data.total_docs || 0,
      averageAccuracy: resp.data.average_accuracy || 0
    }
  } catch (e) {
    console.error('加载文档润色统计失败:', e)
  }
}

async function submitDocumentFeedback() {
  docFeedbackLoading.value = true
  try {
    await persistDocumentDecisions(true, true)
  } finally {
    docFeedbackLoading.value = false
  }
}

watch(formData, (value) => {
  polishStore.updateDocumentDraft({
    sentenceFile: value.sentenceFile,
    sentenceFileId: value.sentenceFileId || null,
    terminologyFile: value.terminologyFile,
    terminologyFileId: value.terminologyFileId || null,
    sourceFile: value.sourceFile,
    outputPath: value.outputPath,
    requirements: value.requirements
  })
}, { deep: true })

watch(documentSession, (session) => {
  loading.value = session.loading
  polishProgress.value = session.progress || 0
  polishProgressMsg.value = session.message || ''
  if (session.result) {
    applyDocumentResult(session.result, documentDraft.value.sourceFile || '')
  } else if (!session.loading) {
    docResult.value = null
  }
}, { deep: true, immediate: true })

onMounted(async () => {
  const pendingPolishText = sessionStorage.getItem('pendingPolishText')
  if (pendingPolishText) {
    originalText.value = pendingPolishText
    sessionStorage.removeItem('pendingPolishText')
  }
  loadKnowledgeTree()
  loadDropdownOptions()
  await loadPolishEngineStatus()
  await loadFeedbackStats()
  await loadDocumentFeedbackStats()
})
</script>

<style scoped>
.polish-container { 
  padding: 0 0 40px; 
  max-width: none;
  width: 100%;
}

.polish-container.document-mode {
  height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.document-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 标题行 ── */
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #111827;
  margin: 0;
}

.page-title-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 14px;
  margin-bottom: 18px;
  flex: 0 0 auto;
}

.title-progress-inline {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: #3b82f6;
  font-weight: 600;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 20px;
  padding: 3px 14px;
}

/* ── 统计卡片 ── */
.stats-card {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  padding: 4px 16px;
  font-size: 13px;
}

.stats-label {
  color: #64748b;
  font-weight: 600;
  font-size: 20px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
}

.stats-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  position: relative;
  top: -1px;
}

.stats-green {
  color: #16a34a;
}

.stats-red {
  color: #dc2626;
}

.stats-divider {
  color: #cbd5e1;
  font-size: 22px;
  margin: 0 2px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
}

.stats-count-wrap {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.stats-count {
  font-weight: 700;
  font-size: 24px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  position: relative;
  top: -1px;
}

.stats-unit {
  color: #64748b;
  font-weight: 600;
  font-size: 20px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
}

/* ── 面板 ── */
.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 16px;
}

.doc-layout {
  display: flex;
  gap: 18px;
  align-items: stretch;
  width: 100%;
  flex: 1;
  height: 0;
  min-height: 0;
  overflow: hidden;
}

.doc-left {
  flex: 1 1 0;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.doc-right {
  flex: 2 1 0;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.doc-layout-result-only .doc-right {
  flex: 1 1 100%;
  width: 100%;
}

.doc-left {
  margin-top: 2mm;
}

.doc-right {
  margin-top: 2mm;
}

.doc-input-panel {
  width: 100%;
  flex: 1;
  margin-bottom: 0;
}

.doc-button-group {
  margin-top: 18px;
  margin-bottom: 0;
}

.doc-result-panel {
  flex: 1;
  height: 100%;
  min-height: 0;
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.doc-result-preview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
  height: 220px;
  min-height: 0;
  flex: 0 0 220px;
}

.doc-result-table-wrap {
  height: 400px;
  min-height: 400px;
  max-height: 400px;
  flex: 0 0 400px;
}

.doc-review-panel {
  flex: 1;
  min-height: 0;
  height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px;
  background: #f8fafc;
}

.doc-review-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #111827;
}

.doc-review-count {
  font-size: 16px;
  font-weight: 700;
}

.doc-review-confirmed {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.doc-review-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.doc-review-filters,
.doc-review-bulk-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-label {
  font-size: 13px;
  color: #64748b;
}

.doc-filter-select {
  width: 150px;
}

.doc-issue-list {
  flex: 1;
  min-height: 0;
  height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 4px;
}

.doc-issue-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  padding: 14px;
  transition: opacity 0.2s ease, border-color 0.2s ease;
}

.doc-issue-card.is-accepted {
  opacity: 0.62;
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.doc-issue-card.is-rejected {
  opacity: 0.62;
  border-color: #fecaca;
  background: #fef2f2;
}

.doc-issue-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.doc-issue-title {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}

.doc-issue-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.trigger-pill,
.paragraph-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.trigger-high {
  background: #dcfce7;
  color: #166534;
}

.trigger-medium {
  background: #fef3c7;
  color: #92400e;
}

.trigger-low {
  background: #fee2e2;
  color: #991b1b;
}

.paragraph-pill {
  background: #eef2ff;
  color: #3730a3;
}

.doc-issue-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
}

.issue-line {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}

.issue-label {
  flex: 0 0 48px;
  color: #64748b;
  font-weight: 600;
}

.issue-text {
  min-width: 0;
  word-break: break-word;
}

.issue-text mark {
  background: #fef3c7;
  color: #92400e;
  padding: 1px 4px;
  border-radius: 4px;
}

.issue-text .mark-after {
  background: #dcfce7;
  color: #166534;
}

.issue-basis {
  color: #64748b;
}

.custom-edit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.doc-issue-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.doc-review-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 2px;
}

.doc-change-table-scroll {
  height: 400px;
  min-height: 400px;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.doc-change-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}

.doc-change-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #e5e7eb;
  font-weight: 700;
  color: #111827;
  padding: 12px 10px;
  border-bottom: 1px solid #d1d5db;
  text-align: left;
  font-size: 13px;
}

.doc-change-table tbody td {
  vertical-align: top;
  padding: 12px 10px;
  border-bottom: 1px solid #eef2f7;
  color: #374151;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}

.doc-change-table tbody tr:nth-child(even) {
  background: #fafafa;
}

.doc-change-table .col-index {
  width: 70px;
}

.doc-change-table .col-type {
  width: 110px;
}

.doc-change-table .col-accepted {
  width: 180px;
}

.doc-change-table .col-accepted :deep(.el-checkbox) {
  align-items: flex-start;
  margin-right: 12px;
}

.doc-change-empty {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
  color: #94a3b8;
  font-size: 13px;
  background: #fafbfc;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f3f4f6;
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── 文件选择行 ── */
.file-select-row {
  display: flex;
  gap: 16px;
}

.file-select-col {
  flex: 1;
  min-width: 0;
}

/* ── 左右分栏 ── */
.content-row {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.content-left {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.content-left .panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.content-left .panel :deep(.el-textarea) {
  flex: 1;
  display: flex;
}

.content-left .panel :deep(.el-textarea__inner) {
  flex: 1;
  resize: vertical;
  min-height: 320px;
}

.content-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.content-right .panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* ── 结果面板 ── */
.result-panel {
  margin-bottom: 0;
  overflow: hidden;
}

.result-header-main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.result-panel .result-grid-vertical {
  flex: 1;
  overflow-y: auto;
  min-height: 320px;
}

.result-placeholder {
  border-style: dashed;
  border-color: #e5e7eb;
  background: #fafbfc;
  display: flex;
  flex-direction: column;
}

.placeholder-text {
  text-align: center;
  padding: 36px 20px;
  color: #94a3b8;
  font-size: 13px;
}

.result-grid-vertical {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.result-col-v {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.col-content-compact {
  flex: 1;
  min-height: 60px;
  max-height: 160px;
  overflow-y: auto;
  padding: 12px 14px;
  line-height: 1.7;
  color: #374151;
  font-size: 13px;
  white-space: pre-wrap;
}

.col-content-compact :deep(.diff-highlight) {
  color: #dc2626;
  background: #fecaca;
  font-weight: 600;
  border-radius: 3px;
}

.doc-change-table td :deep(.diff-highlight) {
  color: #dc2626;
  background: #fecaca;
  font-weight: 600;
  border-radius: 3px;
}

.title-progress-inline {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: #3b82f6;
  font-weight: 600;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 20px;
  padding: 3px 14px;
}

/* ── 进度条（准确率区块后面） ── */
.polish-progress-float {
  display: inline-flex;
  align-items: center;
  gap: 0;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  overflow: hidden;
  font-size: 13px;
  min-width: 280px;
  padding: 4px 16px;
}

.polish-progress-float.done {
  opacity: 0.5;
}

.progress-float-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #374151;
  font-weight: 600;
  white-space: nowrap;
}

.progress-float-text {
  white-space: nowrap;
}

.progress-float-body {
  margin-left: 14px;
  min-width: 140px;
  flex: 1;
}

/* ── 意见反馈 ── */
.feedback-panel {
  margin-top: 16px;
}

.feedback-row {
  display: flex;
  gap: 20px;
}

.feedback-left {
  flex: 0 0 260px;
}

.feedback-right {
  flex: 1;
  min-width: 0;
}

.feedback-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid #f3f4f6;
}

/* ── 表单 ── */
.form-item { margin-bottom: 14px; }

.form-label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #374151;
  font-size: 13px;
}

.feedback-hint {
  margin-top: 6px;
  color: #6b7280;
  font-size: 12px;
}

.input-with-button {
  display: flex;
  gap: 8px;
  align-items: center;
}

.input-with-button .el-input,
.input-with-button .el-select {
  flex: 1;
  min-width: 0;
}

.full-width {
  width: 100%;
}

.button-group {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

/* ── 旧样式保留 ── */
.col-title {
  padding: 8px 14px;
  background: #fff;
  font-weight: 500;
  font-size: 13px;
  color: #374151;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}

.dot-blue { background: #3b82f6; }
.dot-green { background: #10b981; }

.file-picker-content {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px;
}

.picker-empty {
  padding: 24px 12px;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
}

.picker-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.picker-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #111827;
  cursor: pointer;
  text-align: left;
}

.picker-row:hover {
  background: #f8fafc;
}

.picker-row.is-folder {
  font-weight: 600;
  color: #334155;
}

.picker-row.is-file {
  color: #475569;
}

.picker-row.is-selected {
  background: #ecfdf5;
  color: #065f46;
}

.picker-name {
  min-width: 0;
  word-break: break-all;
}

.tree-node-content {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.node-icon {
  font-size: 14px;
}

.selected-info {
  margin-top: 10px;
  color: #059669;
  font-size: 13px;
}

.progress-card {
  margin-top: 16px;
  padding: 14px 18px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.progress-dialog-body {
  padding: 6px 2px 2px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

@media (max-width: 960px) {
  .doc-layout,
  .content-row,
  .file-select-row,
  .feedback-row {
    flex-direction: column;
  }

  .doc-result-preview {
    grid-template-columns: 1fr;
  }

  .doc-result-panel,
  .doc-review-panel,
  .doc-issue-list,
  .doc-result-table-wrap,
  .doc-change-table-scroll {
    max-height: none;
    height: auto;
    min-height: 0;
  }

  .feedback-left {
    flex: 1 1 auto;
  }

  .feedback-bottom {
    align-items: flex-start;
    gap: 12px;
  }
}

.progress-msg {
  flex: 1;
  font-size: 13px;
  color: #374151;
}

.progress-pct {
  font-size: 13px;
  font-weight: 600;
  color: #2563eb;
}

@media (max-width: 768px) {
  .polish-container { max-width: 100%; }
  .content-row { flex-direction: column; }
  .feedback-row { flex-direction: column; }
}
</style>
