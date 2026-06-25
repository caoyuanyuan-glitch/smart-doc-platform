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

      <div class="doc-layout">
        <div class="doc-left">
          <div class="panel doc-input-panel">
            <div class="form-item">
              <label class="form-label">句式清单文件</label>
              <div class="input-with-button">
                <el-input v-model="formData.sentenceFile" readonly placeholder="选择知识库中的句式清单文件" />
                <el-button type="primary" @click="openFilePicker('sentenceFile', 'knowledge')">选择文件</el-button>
              </div>
            </div>

            <div class="form-item">
              <label class="form-label">术语对照表</label>
              <div class="input-with-button">
                <el-input v-model="formData.terminologyFile" readonly placeholder="选择知识库中的术语对照表" />
                <el-button type="primary" @click="openFilePicker('terminologyFile', 'knowledge')">选择文件</el-button>
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
              <label class="form-label">输出文件路径</label>
              <div class="input-with-button">
                <el-input v-model="formData.outputPath" readonly placeholder="已润色文档（默认）" />
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
                <el-tag type="info" size="small">修改 {{ docResult.changes }} 处</el-tag>
                <el-tag type="success" size="small">已选 {{ acceptedDocChangeCount }} 处</el-tag>
                <el-button size="small" @click="toggleAllDocumentChanges">{{ allDocumentChangesSelected ? '反选' : '全选' }}</el-button>
                <el-button size="small" @click="downloadPolishedDoc">下载文档</el-button>
                <el-button size="small" @click="downloadReport">润色报告</el-button>
                <el-button type="primary" size="small" :loading="docFeedbackLoading" @click="submitDocumentFeedback">写入平台反馈句式清单</el-button>
              </div>
            </div>

            <div class="doc-result-preview">
              <div class="result-col-v">
                <div class="col-title"><span class="dot dot-blue"></span>原文预览</div>
                <div class="col-content-compact" v-html="highlightedDocOriginalHtml"></div>
              </div>
              <div class="result-col-v">
                <div class="col-title"><span class="dot dot-green"></span>润色预览</div>
                <div class="col-content-compact" v-html="highlightedDocPolishedHtml"></div>
              </div>
            </div>

            <div class="doc-result-table-wrap">
              <div v-if="docResult.changeDetails?.length" class="doc-change-table-scroll">
                <table class="doc-change-table">
                  <thead>
                    <tr>
                      <th class="col-index">序号</th>
                      <th class="col-before">原文</th>
                      <th class="col-after">润色后</th>
                      <th class="col-type">修改类型</th>
                      <th class="col-accepted">是否接受</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(item, index) in docResult.changeDetails" :key="`${index}-${item.before}-${item.after}`">
                      <td class="col-index">{{ index + 1 }}</td>
                      <td class="col-before" v-html="renderDiffHtml(item.before, item.after, 'original')"></td>
                      <td class="col-after" v-html="renderDiffHtml(item.before, item.after, 'polished')"></td>
                      <td class="col-type">{{ item.typeLabel }}</td>
                      <td class="col-accepted">
                        <div><el-checkbox v-model="item.accepted">是</el-checkbox></div>
                        <div><el-checkbox v-model="item.needCorrection" @change="onCorrectionChecked(index, item)">修正后接受</el-checkbox></div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else class="doc-change-empty">当前没有可确认的润色结果</div>
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
              <el-input v-model="textSentenceFileName" size="small" readonly placeholder="留空则加载全部" />
              <el-button type="primary" size="small" @click="openTextSentencePicker">选择文件</el-button>
              <el-button v-if="textSentenceFileId" size="small" @click="clearTextSentenceFile">清除</el-button>
            </div>
          </div>
          <div class="file-select-col">
            <label class="form-label">术语对照表</label>
            <div class="input-with-button">
              <el-input v-model="textTerminologyFileName" size="small" readonly placeholder="留空则使用数据库术语" />
              <el-button type="primary" size="small" @click="openTextTerminologyPicker">选择文件</el-button>
              <el-button v-if="textTerminologyFileId" size="small" @click="clearTextTerminologyFile">清除</el-button>
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
              <span>润色结果</span>
              <div class="panel-actions">
                <el-tag type="info" size="small">修改 {{ result.changes }} 处</el-tag>
                <el-button size="small" @click="copyResult">复制</el-button>
                <el-button size="small" @click="downloadResult">导出</el-button>
              </div>
            </div>
            <div class="result-grid-vertical">
              <div class="result-col-v">
                <div class="col-title"><span class="dot dot-blue"></span>原文</div>
                <div class="col-content col-content-compact" v-html="highlightedOriginalHtml"></div>
              </div>
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
import { polishAPI, knowledgeAPI } from '@/api'
import { Loading } from '@element-plus/icons-vue'
import { usePolishStore } from '@/store/polish'

const route = useRoute()
const polishStore = usePolishStore()
const { documentDraft, documentSession } = storeToRefs(polishStore)
const localFileInputRef = ref(null)
const filePickerVisible = ref(false)
const knowledgeTree = ref([])
const knowledgeTreeList = ref([])
const selectedKnowledgeFile = ref(null)
const currentPickerField = ref(null)

const originalText = ref('')
const textSentenceFileName = ref('')
const textSentenceFileId = ref(null)
const textTerminologyFileName = ref('')
const textTerminologyFileId = ref(null)
const result = ref(null)
const docResult = ref(null)
const loading = ref(false)
const polishProgress = ref(0)
const polishProgressMsg = ref('')
const docFeedbackLoading = ref(false)
const docFeedbackStats = ref({ totalDocs: 0, averageAccuracy: 0 })
// 反馈相关
const feedbackAccuracy = ref(80)
const feedbackCorrections = ref('')
const feedbackTarget = ref('terminology')
const feedbackLoading = ref(false)
const feedbackStats = ref({ totalCount: 0, averageAccuracy: 0 })

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

const highlightedOriginalHtml = computed(() => renderDiffHtml(result.value?.original, result.value?.polished, 'original'))
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
  return items.filter(item => item.accepted).length
})

const allDocumentChangesSelected = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.length > 0 && items.every(item => item.accepted)
})

function toggleAllDocumentChanges() {
  const items = docResult.value?.changeDetails || []
  const nextValue = !allDocumentChangesSelected.value
  items.forEach(item => {
    item.accepted = nextValue
  })
}

function normalizeChangeType(type) {
  const typeMap = {
    ai: 'AI',
    terminology: '术语',
    terminology_rule: '术语',
    preferred_sentences: '句式',
    forbidden_words: '禁用词',
    passive_voice: '语态',
    double_negative: '句式',
    informal: '表达',
    sentence_length: '长句',
    pronoun_reference: '指代',
    format: '格式'
  }
  return typeMap[type] || (type ? String(type) : '润色')
}

function normalizeDocumentChanges(changes) {
  return (changes || []).map((change, index) => {
    const before = change.before || change.original || ''
    const after = change.after || change.polished || ''
    return {
      rowKey: `${index}-${before}-${after}`,
      before,
      after,
      type: change.type || '',
      typeLabel: normalizeChangeType(change.type),
      accepted: false,
      needCorrection: false
    }
  }).filter(item => {
    const before = (item.before || '').replace(/\s+/g, ' ').trim()
    const after = (item.after || '').replace(/\s+/g, ' ').trim()
    if (!before && !after) {
      return false
    }
    return before !== after || (!before && after) || (before && !after)
  })
}

function applyDocumentResult(data, fallbackSourceName = '') {
  const normalizedChanges = normalizeDocumentChanges(data?.changes || [])
  docResult.value = {
    id: data?.id,
    sourceName: fallbackSourceName || formData.value.sourceFile || data?.download_filename || '',
    original: data?.original || '',
    polished: data?.polished || '',
    changes: normalizedChanges.length,
    changeDetails: normalizedChanges,
    reportFile: data?.report_file || data?.reportFile,
    download_filename: data?.download_filename,
    file_type: data?.file_type
  }
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
    knowledgeTreeList.value = flattenKnowledgeList(rawData)
    selectedKnowledgeFile.value = null
  } catch (e) {
    ElMessage.error('加载知识库失败')
  }
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
  if (!docResult.value || !docResult.value.changeDetails?.length) {
    ElMessage.warning('当前没有可提交的润色结果')
    return
  }

  docFeedbackLoading.value = true
  try {
    const payload = docResult.value.changeDetails.map(item => ({
      before: item.before,
      after: item.after,
      type: item.type,
      accepted: item.accepted
    }))
    const resp = await polishAPI.submitDocumentFeedback(
      docResult.value.id,
      docResult.value.sourceName,
      payload
    )
    const data = resp.data || {}
    if (data.processed_count > 0) {
      ElMessage.success(`已写入 ${data.processed_count} 条平台反馈句式`) 
    } else {
      ElMessage.success('文档反馈已提交，本次没有新增句式写入')
    }
    await loadDocumentFeedbackStats()
    resetForm()
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`提交失败：${errorMsg}`)
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
  loadKnowledgeTree()
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
  overflow: visible;
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

.input-with-button .el-input {
  flex: 1;
  min-width: 0;
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
