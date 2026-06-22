<template>
  <div class="compare-container">
    <div v-if="currentView === 'upload'">
      <h2 class="page-title">文档对比</h2>

      <div class="panel">
        <div class="panel-header">
          <span>上传两个文档进行对比</span>
          <div class="panel-actions">
            <el-tag size="small" type="info">支持 PDF / DOCX / MD / TXT / DITA / ZIP</el-tag>
          </div>
        </div>

        <div class="upload-grid">
          <div class="upload-slot">
            <div class="slot-label">文档A（原始版本）</div>
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :before-upload="(f) => { fileA = f; return false }"
              :on-change="(f) => { fileA = f.raw || f }"
              accept=".pdf,.docx,.doc,.md,.txt,.dita,.xml,.zip"
            >
              <div class="upload-box" :class="{ filled: fileA }">
                <el-icon style="font-size: 36px; color: #3b82f6; margin-bottom: 8px;"><Upload /></el-icon>
                <div v-if="!fileA" class="upload-hint">点击上传文档A</div>
                <div v-else class="upload-name">{{ fileA.name }}</div>
              </div>
            </el-upload>
          </div>

          <div class="vs-badge">VS</div>

          <div class="upload-slot">
            <div class="slot-label">文档B（对比版本）</div>
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :before-upload="(f) => { fileB = f; return false }"
              :on-change="(f) => { fileB = f.raw || f }"
              accept=".pdf,.docx,.doc,.md,.txt,.dita,.xml,.zip"
            >
              <div class="upload-box" :class="{ filled: fileB }">
                <el-icon style="font-size: 36px; color: #7c3aed; margin-bottom: 8px;"><Upload /></el-icon>
                <div v-if="!fileB" class="upload-hint">点击上传文档B</div>
                <div v-else class="upload-name">{{ fileB.name }}</div>
              </div>
            </el-upload>
          </div>
        </div>

        <div class="action-row">
          <el-button type="primary" size="large" :loading="loading" :disabled="!fileA || !fileB" @click="doCompare">
            <el-icon><Search /></el-icon> 开始对比
          </el-button>
          <el-button size="large" @click="clearFiles">清空</el-button>
        </div>

        <div v-if="progress > 0 && progress < 100" class="progress-panel">
          <el-progress :percentage="progress" :stroke-width="16" status="success" />
          <div class="progress-text">{{ progressText }}</div>
        </div>
      </div>

      <div v-if="result" class="result-panel">
        <div class="panel-header">
          <span>对比结果</span>
          <div class="panel-actions">
            <el-tag :type="verdictType" size="small">{{ result.verdict }}</el-tag>
            <el-tag type="info" size="small">差异数：{{ result.total_diffs || 0 }}</el-tag>
            <el-button size="small" type="primary" @click="previewReport">预览报告</el-button>
            <el-button size="small" @click="exportCompare">导出报告</el-button>
          </div>
        </div>

        <div v-if="showPreview" class="panel" style="background: #fafafa; margin-top: 12px;">
          <div class="panel-header">
            <span>报告预览</span>
            <el-button size="small" @click="showPreview = false">关闭预览</el-button>
          </div>
          <div style="max-height: 800px; overflow-y: auto; background: #fff; padding: 16px; border-radius: 6px;" v-html="reportContent"></div>
        </div>

        <div class="cards">
          <div class="card primary">
            <div class="num">{{ (result.similarity * 100).toFixed(1) }}%</div>
            <div class="lbl">整体一致性 · 模糊 Jaccard</div>
          </div>
          <div class="card">
            <div class="num">{{ (result.avg_match * 100).toFixed(1) }}%</div>
            <div class="lbl">匹配平均</div>
          </div>
          <div class="card">
            <div class="num">{{ result.n_matched_topics || 0 }}</div>
            <div class="lbl">匹配 topic</div>
          </div>
          <div class="card">
            <div class="num">{{ result.stat_full_match || 0 }}</div>
            <div class="lbl">完全一致</div>
          </div>
          <div class="card">
            <div class="num">{{ result.stat_high || 0 }}</div>
            <div class="lbl">高度相似</div>
          </div>
          <div class="card">
            <div class="num">{{ result.stat_partial || 0 }}</div>
            <div class="lbl">部分相似</div>
          </div>
          <div class="card">
            <div class="num">{{ result.stat_low || 0 }}</div>
            <div class="lbl">差异较大</div>
          </div>
          <div class="card">
            <div class="num">{{ result.n_only_a || 0 }}/{{ result.n_only_b || 0 }}</div>
            <div class="lbl">仅在 A / 仅在 B</div>
          </div>
        </div>

        <div class="explain">
          <b>当前算法: 全量 topic 模糊 Jaccard（方案 2）</b><br>
          按 ditamap 中 navtitle 标准化匹配 topic，对每个匹配上的 topic 抽出句段跑模糊 Jaccard。
          句段总数覆盖全部 topic，包括仅在 A / 仅在 B 的孤儿 topic；Jaccard = 匹配句段对数 / (A 全部句段数 + B 全部句段数 - 匹配句段对数)。<br>
          本次 A={{ result.n_a || 0 }} 句段，B={{ result.n_b || 0 }} 句段，
          匹配 topic={{ result.n_matched_topics || 0 }}，整体一致性=<b>{{ (result.similarity * 100).toFixed(2) }}%</b>。
          作为对照，加权一致性为 <b>{{ (result.weighted_sim * 100).toFixed(2) }}%</b>。<br>
          <span style="color:#888">判定：{{ result.verdict }}</span>
        </div>

        <div class="file-info">
          <h3>文件基本信息</h3>
          <div class="file-info-grid">
            <div class="label">文件A名称</div>
            <div class="value">{{ fileA?.name || '-' }}</div>
            <div class="label">文件B名称</div>
            <div class="value">{{ fileB?.name || '-' }}</div>
            <div class="label">文件A统计</div>
            <div class="value">{{ result.n_a || 0 }} 句段 / {{ result.n_topics_a || 0 }} topics</div>
            <div class="label">文件B统计</div>
            <div class="value">{{ result.n_b || 0 }} 句段 / {{ result.n_topics_b || 0 }} topics</div>
          </div>
        </div>

        <h2>差异点汇总 (按 ditamap 中 topic 顺序)</h2>
        <table class="summary">
          <thead>
            <tr>
              <th>序号</th>
              <th>一级章节</th>
              <th>小节 (topic)</th>
              <th>类型</th>
              <th>一致性</th>
              <th>相似度</th>
              <th>判定</th>
              <th>差异</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(topic, idx) in topics" :key="idx">
              <tr :class="[topic.row_class, 'row-main']" @click="toggleDiff(idx)">
                <td>{{ idx + 1 }}</td>
                <td>{{ topic.chapter }}</td>
                <td>{{ topic.navtitle }}</td>
                <td>
                  <span v-if="topic.type === 'only_a'" class="tag only-a">仅在 A</span>
                  <span v-else-if="topic.type === 'only_b'" class="tag only-b">仅在 B</span>
                  <span v-else class="tag ok">topic_match</span>
                </td>
                <td>
                  <div class="bar">
                    <div class="fill" :style="{ width: (topic.topic_sim * 100) + '%', background: topic.bar_color }"></div>
                    <span>{{ (topic.topic_sim * 100).toFixed(1) }}%</span>
                  </div>
                </td>
                <td>{{ (topic.topic_sim * 100).toFixed(1) }}%</td>
                <td>{{ topic.consistency_label }}</td>
                <td class="diff-cell"><b>{{ topic.n_diffs }}</b> 处</td>
              </tr>
              <tr v-if="expandedDiffs.includes(idx)" class="row-diff">
                <td colspan="8">
                  <div class="diffs">
                    <template v-if="topic.diffs && topic.diffs.length > 0">
                      <div v-for="(diff, dIdx) in topic.diffs" :key="dIdx" class="diff-row changed">
                        <span class="tag-c">
                          {{ diff.type === 'modify' ? 'A → B' : diff.type === 'only_a' ? 'A 独有' : 'B 独有' }}
                        </span>
                        <div class="text">
                          <div v-if="diff.text_a" class="side-a">{{ diff.text_a }}</div>
                          <div v-if="diff.text_b" class="side-b">{{ diff.text_b }}</div>
                        </div>
                      </div>
                    </template>
                    <div v-else class="diff-empty">✓ 该 topic 句段全部完全一致，无差异</div>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!topics || topics.length === 0">
              <td colspan="8" style="text-align:center;padding:40px;color:#888">
                <div class="diff-list">
                  <div v-for="(diff, index) in filteredDiffs" :key="index" class="diff-item" :class="[diff.diff_type, `severity-${diff.severity}`]">
                    <div class="diff-header">
                      <span class="diff-index">#{{ index + 1 }}</span>
                      <span class="diff-type">{{ getDiffTypeName(diff.diff_type) }}</span>
                      <span :class="['severity-tag', diff.severity]">{{ getSeverityName(diff.severity) }}</span>
                      <span class="similarity-tag">{{ (diff.similarity * 100).toFixed(1) }}%</span>
                    </div>
                    <div class="diff-content">
                      <div v-if="diff.text_a" class="diff-text diff-text-a">
                        <span class="text-label">文档A:</span>
                        <span>{{ diff.text_a }}</span>
                      </div>
                      <div v-if="diff.text_b" class="diff-text diff-text-b">
                        <span class="text-label">文档B:</span>
                        <span>{{ diff.text_b }}</span>
                      </div>
                    </div>
                  </div>
                  <div v-if="filteredDiffs.length === 0" class="empty-state">
                    <el-icon style="font-size: 48px; color: #999; margin-bottom: 10px;"><CircleCheck /></el-icon>
                    <div>暂无差异</div>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="currentView === 'tasks'">
      <h2 class="page-title">历史任务</h2>
      <div class="panel">
        <el-table :data="history" border style="width: 100%">
          <el-table-column prop="id" label="任务ID" width="100" />
          <el-table-column prop="file_a_name" label="文档A" />
          <el-table-column prop="file_b_name" label="文档B" />
          <el-table-column prop="similarity" label="相似度" width="120">
            <template #default="scope">
              <span :class="getSimilarityClass(scope.row.similarity)">{{ (scope.row.similarity * 100).toFixed(1) }}%</span>
            </template>
          </el-table-column>
          <el-table-column prop="verdict" label="判定" width="180">
            <template #default="scope">
              <el-tag :type="scope.row.verdict?.includes('通过') ? 'success' : (scope.row.verdict?.includes('强制') ? 'danger' : 'warning')" size="small">{{ scope.row.verdict }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="total_diffs" label="差异数" width="100" />
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="scope">
              {{ formatTime(scope.row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="scope">
              <el-button size="small" @click="viewTask(scope.row.id)">查看</el-button>
              <el-button size="small" @click="exportTaskReport(scope.row.id)">导出报告</el-button>
              <el-button size="small" type="danger" @click="deleteTask(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="selectedTask" class="result-panel" style="margin-top: 20px;">
        <div class="panel-header">
          <span>任务详情 - {{ selectedTask.id }}</span>
          <div class="panel-actions">
            <el-button size="small" type="primary" @click="previewTaskReport(selectedTask.id)">预览报告</el-button>
            <el-button size="small" @click="exportTaskReport(selectedTask.id)">导出报告</el-button>
            <el-button size="small" @click="selectedTask = null">关闭</el-button>
          </div>
        </div>

        <div v-if="showPreview" class="panel" style="background: #fafafa; margin-top: 12px;">
          <div class="panel-header">
            <span>报告预览 - 任务 {{ selectedTask.id }}</span>
            <el-button size="small" @click="showPreview = false">关闭预览</el-button>
          </div>
          <div style="max-height: 800px; overflow-y: auto; background: #fff; padding: 16px; border-radius: 6px;" v-html="reportContent"></div>
        </div>

        <div class="cards">
          <div class="card primary">
            <div class="num">{{ (selectedTask.similarity * 100).toFixed(1) }}%</div>
            <div class="lbl">整体一致性 · 模糊 Jaccard</div>
          </div>
          <div class="card">
            <div class="num">{{ (selectedTask.avg_match * 100).toFixed(1) }}%</div>
            <div class="lbl">匹配平均</div>
          </div>
          <div class="card">
            <div class="num">{{ selectedTask.n_matched_topics || 0 }}</div>
            <div class="lbl">匹配 topic</div>
          </div>
          <div class="card">
            <div class="num">{{ selectedTask.stat_full_match || 0 }}</div>
            <div class="lbl">完全一致</div>
          </div>
          <div class="card">
            <div class="num">{{ selectedTask.stat_high || 0 }}</div>
            <div class="lbl">高度相似</div>
          </div>
          <div class="card">
            <div class="num">{{ selectedTask.stat_partial || 0 }}</div>
            <div class="lbl">部分相似</div>
          </div>
          <div class="card">
            <div class="num">{{ selectedTask.stat_low || 0 }}</div>
            <div class="lbl">差异较大</div>
          </div>
          <div class="card">
            <div class="num">{{ selectedTask.n_only_a || 0 }}/{{ selectedTask.n_only_b || 0 }}</div>
            <div class="lbl">仅在 A / 仅在 B</div>
          </div>
        </div>

        <div class="explain">
          <b>当前算法: 全量 topic 模糊 Jaccard（方案 2）</b><br>
          本次 A={{ selectedTask.n_a || 0 }} 句段，B={{ selectedTask.n_b || 0 }} 句段，
          匹配 topic={{ selectedTask.n_matched_topics || 0 }}，整体一致性=<b>{{ (selectedTask.similarity * 100).toFixed(2) }}%</b>。<br>
          <span style="color:#888">判定：{{ selectedTask.verdict }}</span>
        </div>

        <div class="file-info">
          <h3>文件基本信息</h3>
          <div class="file-info-grid">
            <div class="label">文件A名称</div>
            <div class="value">{{ selectedTask.file_a_name || '-' }}</div>
            <div class="label">文件B名称</div>
            <div class="value">{{ selectedTask.file_b_name || '-' }}</div>
            <div class="label">文件A统计</div>
            <div class="value">{{ selectedTask.n_a || 0 }} 句段 / {{ selectedTask.n_topics_a || 0 }} topics</div>
            <div class="label">文件B统计</div>
            <div class="value">{{ selectedTask.n_b || 0 }} 句段 / {{ selectedTask.n_topics_b || 0 }} topics</div>
          </div>
        </div>

        <h2>差异点汇总 (按 ditamap 中 topic 顺序)</h2>
        <table class="summary">
          <thead>
            <tr>
              <th>序号</th>
              <th>一级章节</th>
              <th>小节 (topic)</th>
              <th>类型</th>
              <th>一致性</th>
              <th>相似度</th>
              <th>判定</th>
              <th>差异</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(topic, idx) in selectedTask.topics" :key="idx">
              <tr :class="[topic.row_class, 'row-main']" @click="toggleTaskDiff(idx)">
                <td>{{ idx + 1 }}</td>
                <td>{{ topic.chapter }}</td>
                <td>{{ topic.navtitle }}</td>
                <td>
                  <span v-if="topic.type === 'only_a'" class="tag only-a">仅在 A</span>
                  <span v-else-if="topic.type === 'only_b'" class="tag only-b">仅在 B</span>
                  <span v-else class="tag ok">topic_match</span>
                </td>
                <td>
                  <div class="bar">
                    <div class="fill" :style="{ width: (topic.topic_sim * 100) + '%', background: topic.bar_color }"></div>
                    <span>{{ (topic.topic_sim * 100).toFixed(1) }}%</span>
                  </div>
                </td>
                <td>{{ (topic.topic_sim * 100).toFixed(1) }}%</td>
                <td>{{ topic.consistency_label }}</td>
                <td class="diff-cell"><b>{{ topic.n_diffs }}</b> 处</td>
              </tr>
              <tr v-if="expandedTaskDiffs.includes(idx)" class="row-diff">
                <td colspan="8">
                  <div class="diffs">
                    <template v-if="topic.diffs && topic.diffs.length > 0">
                      <div v-for="(diff, dIdx) in topic.diffs" :key="dIdx" class="diff-row changed">
                        <span class="tag-c">
                          {{ diff.type === 'modify' ? 'A → B' : diff.type === 'only_a' ? 'A 独有' : 'B 独有' }}
                        </span>
                        <div class="text">
                          <div v-if="diff.text_a" class="side-a">{{ diff.text_a }}</div>
                          <div v-if="diff.text_b" class="side-b">{{ diff.text_b }}</div>
                        </div>
                      </div>
                    </template>
                    <div v-else class="diff-empty">✓ 该 topic 句段全部完全一致，无差异</div>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!selectedTask.topics || selectedTask.topics.length === 0">
              <td colspan="8" style="text-align:center;padding:40px;color:#888">
                <div class="diff-list">
                  <div v-for="(diff, index) in selectedTask.diffs" :key="index" class="diff-item" :class="[diff.diff_type, `severity-${diff.severity}`]">
                    <div class="diff-header">
                      <span class="diff-index">#{{ index + 1 }}</span>
                      <span class="diff-type">{{ getDiffTypeName(diff.diff_type) }}</span>
                      <span :class="['severity-tag', diff.severity]">{{ getSeverityName(diff.severity) }}</span>
                      <span class="similarity-tag">{{ (diff.similarity * 100).toFixed(1) }}%</span>
                    </div>
                    <div class="diff-content">
                      <div v-if="diff.text_a" class="diff-text diff-text-a">
                        <span class="text-label">文档A:</span>
                        <span>{{ diff.text_a }}</span>
                      </div>
                      <div v-if="diff.text_b" class="diff-text diff-text-b">
                        <span class="text-label">文档B:</span>
                        <span>{{ diff.text_b }}</span>
                      </div>
                    </div>
                  </div>
                  <div v-if="!selectedTask.diffs || selectedTask.diffs.length === 0" class="empty-state">
                    <el-icon style="font-size: 48px; color: #999; margin-bottom: 10px;"><CircleCheck /></el-icon>
                    <div>暂无差异</div>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="currentView === 'config'">
      <h2 class="page-title">对比配置</h2>
      <div class="panel">
        <el-form :model="config" label-width="200px" style="max-width: 700px;">
          <el-form-item label="匹配阈值">
            <el-slider v-model="config.threshold" :min="0.5" :max="0.95" :step="0.01" show-input />
          </el-form-item>
          <el-form-item label="对比精度">
            <el-radio-group v-model="config.precision">
              <el-radio label="paragraph">段落级</el-radio>
              <el-radio label="sentence">句子级</el-radio>
              <el-radio label="word">词语级</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="忽略空白字符">
            <el-switch v-model="config.ignoreWhitespace" />
          </el-form-item>
          <el-form-item label="忽略大小写">
            <el-switch v-model="config.ignoreCase" />
          </el-form-item>
          <el-form-item label="支持格式">
            <el-tag size="small" style="margin-right: 8px;">PDF</el-tag>
            <el-tag size="small" style="margin-right: 8px;">DOCX</el-tag>
            <el-tag size="small" style="margin-right: 8px;">MD</el-tag>
            <el-tag size="small" style="margin-right: 8px;">TXT</el-tag>
            <el-tag size="small" style="margin-right: 8px;">DITA</el-tag>
            <el-tag size="small">ZIP</el-tag>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveConfig">保存配置</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { compareAPI } from '@/api'
import { Upload, Search, CircleCheck } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const fileA = ref(null)
const fileB = ref(null)
const loading = ref(false)
const progress = ref(0)
const progressText = ref('')
const result = ref(null)
const history = ref([])
const diffFilter = ref('all')
const severityFilter = ref('all')
const selectedTask = ref(null)
const showPreview = ref(false)
const reportContent = ref('')
const expandedDiffs = ref([])
const expandedTaskDiffs = ref([])

const config = ref({
  threshold: 0.8,
  precision: 'sentence',
  ignoreWhitespace: true,
  ignoreCase: false
})

const currentView = computed(() => {
  if (route.path === '/compare/tasks') return 'tasks'
  if (route.path === '/compare/config') return 'config'
  return 'upload'
})

const topics = computed(() => {
  if (result.value && result.value.dita_full && result.value.dita_full.topics) {
    return result.value.dita_full.topics.map(tr => ({
      ...tr,
      chapter: tr.chapter_a || tr.chapter_b || '',
      row_class: tr.row_class || '',
      bar_color: tr.bar_color || '#1976d2',
    }))
  }
  return []
})

const verdictType = computed(() => {
  if (!result.value?.verdict) return 'info'
  if (result.value.verdict.includes('通过')) return 'success'
  if (result.value.verdict.includes('强制')) return 'danger'
  return 'warning'
})

const filteredDiffs = computed(() => {
  if (!result.value?.diffs) return []
  return result.value.diffs.filter(diff => {
    if (diffFilter.value !== 'all' && diff.diff_type !== diffFilter.value) return false
    if (severityFilter.value !== 'all' && diff.severity !== severityFilter.value) return false
    return true
  })
})

onMounted(async () => {
  if (currentView.value === 'tasks') {
    await loadHistory()
  }
})

async function loadHistory() {
  try {
    const resp = await compareAPI.list()
    if (resp.data && Array.isArray(resp.data)) {
      history.value = resp.data
    }
  } catch (e) {
    history.value = []
  }
}

function getSimilarityClass(similarity) {
  if (similarity >= 0.8) return 'similarity-high'
  if (similarity >= 0.6) return 'similarity-medium'
  return 'similarity-low'
}

function getDiffTypeName(type) {
  const map = { add: '新增', delete: '删除', modify: '修改', only_a: 'A独有', only_b: 'B独有' }
  return map[type] || type
}

function getSeverityName(severity) {
  const map = { critical: '严重', high: '高', medium: '中', low: '低' }
  return map[severity] || severity
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  if (typeof timestamp === 'object') return timestamp.toLocaleString()
  if (typeof timestamp === 'string') {
    return new Date(timestamp).toLocaleString()
  }
  return new Date(timestamp * 1000).toLocaleString()
}

function clearFiles() {
  fileA.value = null
  fileB.value = null
  result.value = null
  expandedDiffs.value = []
}

function updateProgress(pct, text) {
  return new Promise(resolve => {
    setTimeout(() => {
      progress.value = pct
      progressText.value = text
      resolve()
    }, 200)
  })
}

function toggleDiff(idx) {
  const i = expandedDiffs.value.indexOf(idx)
  if (i > -1) {
    expandedDiffs.value.splice(i, 1)
  } else {
    expandedDiffs.value.push(idx)
  }
}

function toggleTaskDiff(idx) {
  const i = expandedTaskDiffs.value.indexOf(idx)
  if (i > -1) {
    expandedTaskDiffs.value.splice(i, 1)
  } else {
    expandedTaskDiffs.value.push(idx)
  }
}

async function doCompare() {
  if (!fileA.value || !fileB.value) {
    ElMessage.info('请上传两个文档后再进行对比')
    return
  }
  loading.value = true
  progress.value = 0
  progressText.value = ''
  expandedDiffs.value = []
  
  try {
    await updateProgress(5, '正在初始化...')
    await updateProgress(10, '正在上传文件...')
    await updateProgress(15, '正在解析文档A...')
    
    const respPromise = compareAPI.create(fileA.value, fileB.value)
    
    for (let p = 20; p < 80; p += 5) {
      await updateProgress(p, `正在处理文档B... ${p}%`)
      await new Promise(r => setTimeout(r, 300))
    }
    
    await updateProgress(80, '正在对比分析...')
    
    const resp = await respPromise
    const data = resp.data || {}
    
    await updateProgress(90, '正在生成结果...')
    
    result.value = {
      similarity: data.similarity || 0,
      verdict: data.verdict || '',
      total_diffs: data.total_diffs || 0,
      stats: data.stats || data.diff_stats || {},
      diffs: data.diffs || [],
      exact_match: data.exact_match || 0,
      n_a: data.n_a || 0,
      n_b: data.n_b || 0,
      n_topics_a: data.dita_full?.n_topics_a || 0,
      n_topics_b: data.dita_full?.n_topics_b || 0,
      n_matched_topics: data.dita_full?.n_matched_topics || 0,
      n_only_a: data.dita_full?.n_only_a || 0,
      n_only_b: data.dita_full?.n_only_b || 0,
      stat_full_match: data.dita_full?.stat_full_match || 0,
      stat_high: data.dita_full?.stat_high || 0,
      stat_partial: data.dita_full?.stat_partial || 0,
      stat_low: data.dita_full?.stat_low || 0,
      avg_match: data.dita_full?.avg_match || 0,
      weighted_sim: data.dita_full?.weighted_sim || 0,
      dita_full: data.dita_full || {},
      comparison_id: data.comparison_id || data.task_id || 0,
      task_id: data.comparison_id || data.task_id || 0,
    }
    
    await updateProgress(95, '正在整理报告...')
    await updateProgress(100, '对比完成')
    
    setTimeout(() => { progress.value = 0 }, 1500)
    ElMessage.success('对比完成')
  } catch (e) {
    progress.value = 0
    ElMessage.error('对比失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function exportCompare() {
  if (!result.value) {
    ElMessage.warning('请先进行对比')
    return
  }
  
  const taskId = result.value.comparison_id || result.value.task_id
  if (!taskId) {
    ElMessage.warning('无法获取任务ID，请重新对比')
    return
  }
  
  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    const content = resp.data?.content || ''
    
    if (!content.trim()) {
      ElMessage.warning('报告内容为空')
      return
    }
    
    downloadFile(content, `compare_report_${taskId}_${Date.now()}.html`, 'text/html')
    ElMessage.success('对比报告已导出')
  } catch (e) {
    console.error('Export error:', e)
    ElMessage.error('导出失败：' + (e.message || '未知错误'))
  }
}

async function previewReport() {
  if (!result.value) {
    ElMessage.warning('请先进行对比')
    return
  }
  
  const taskId = result.value.comparison_id || result.value.task_id
  if (!taskId) {
    ElMessage.warning('无法获取任务ID，请重新对比')
    return
  }
  
  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    reportContent.value = resp.data?.content || ''
    
    if (!reportContent.value.trim()) {
      ElMessage.warning('报告内容为空')
      return
    }
    
    showPreview.value = true
    ElMessage.success('报告已加载')
  } catch (e) {
    console.error('Preview error:', e)
    ElMessage.error('预览失败：' + (e.message || '未知错误'))
  }
}

async function viewTask(taskId) {
  try {
    const resp = await compareAPI.get(taskId)
    const data = resp.data || {}
    
    let dita_full = {}
    try {
      if (data.dita_full && typeof data.dita_full === 'string') {
        dita_full = JSON.parse(data.dita_full)
      } else if (data.dita_full) {
        dita_full = data.dita_full
      }
    } catch (e) {
      dita_full = {}
    }
    
    const diffs = (data.diffs || []).map(d => {
      try {
        return {
          ...d,
          position_a: typeof d.position_a === 'string' ? JSON.parse(d.position_a) : (d.position_a || {}),
          position_b: typeof d.position_b === 'string' ? JSON.parse(d.position_b) : (d.position_b || {}),
        }
      } catch (e) {
        return d
      }
    })
    
    const topics = (dita_full.topics || []).map(tr => ({
      ...tr,
      chapter: tr.chapter_a || tr.chapter_b || '',
      row_class: tr.row_class || '',
      bar_color: tr.bar_color || '#1976d2',
    }))
    
    selectedTask.value = {
      id: taskId,
      similarity: data.similarity || 0,
      verdict: data.verdict || '',
      total_diffs: data.total_diffs || 0,
      stats: data.stats || data.diff_stats || {},
      diffs: diffs,
      exact_match: data.exact_match || 0,
      n_a: data.n_a || 0,
      n_b: data.n_b || 0,
      n_topics_a: dita_full.n_topics_a || 0,
      n_topics_b: dita_full.n_topics_b || 0,
      n_matched_topics: dita_full.n_matched_topics || 0,
      n_only_a: dita_full.n_only_a || 0,
      n_only_b: dita_full.n_only_b || 0,
      stat_full_match: dita_full.stat_full_match || 0,
      stat_high: dita_full.stat_high || 0,
      stat_partial: dita_full.stat_partial || 0,
      stat_low: dita_full.stat_low || 0,
      avg_match: dita_full.avg_match || 0,
      weighted_sim: dita_full.weighted_sim || 0,
      file_a_name: data.file_a_name || '',
      file_b_name: data.file_b_name || '',
      topics: topics,
    }
    expandedTaskDiffs.value = []
  } catch (e) {
    ElMessage.error('查看失败：' + (e.message || '未知错误'))
  }
}

async function exportTaskReport(taskId) {
  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    const content = resp.data?.content || ''
    downloadFile(content, `compare_report_${taskId}.html`, 'text/html')
    ElMessage.success('对比报告已导出')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || '未知错误'))
  }
}

async function previewTaskReport(taskId) {
  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    reportContent.value = resp.data?.content || ''
    
    if (!reportContent.value.trim()) {
      ElMessage.warning('报告内容为空')
      return
    }
    
    showPreview.value = true
    ElMessage.success('报告已加载')
  } catch (e) {
    console.error('Preview error:', e)
    ElMessage.error('预览失败：' + (e.message || '未知错误'))
  }
}

async function deleteTask(taskId) {
  try {
    await compareAPI.delete(taskId)
    await loadHistory()
    if (selectedTask.value?.id === taskId) {
      selectedTask.value = null
    }
    ElMessage.success('任务已删除')
  } catch (e) {
    ElMessage.error('删除失败：' + (e.message || '未知错误'))
  }
}

function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function saveConfig() {
  try {
    await compareAPI.updateConfig(config.value)
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}
</script>

<style>
.compare-container { padding: 0; }

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 20px;
}

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.result-panel {
  background: #fff;
  border-radius: 10px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
  color: #1f2937;
}

.panel-actions { display: flex; align-items: center; gap: 10px; }

.upload-grid {
  display: flex;
  align-items: flex-start;
  gap: 24px;
  justify-content: center;
}

.upload-slot { flex: 1; max-width: 400px; }

.slot-label {
  font-weight: 600;
  margin-bottom: 12px;
  color: #374151;
}

.upload-box {
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
}

.upload-box:hover { border-color: #3b82f6; background: #eff6ff; }

.upload-box.filled { border-color: #3b82f6; background: #f0f9ff; }

.upload-hint { color: #6b7280; font-size: 14px; }

.upload-name { color: #3b82f6; font-weight: 600; font-size: 14px; }

.vs-badge {
  font-size: 20px;
  font-weight: 700;
  color: #9ca3af;
  padding: 8px 16px;
}

.action-row {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 24px;
}

.progress-panel {
  margin-top: 20px;
  padding: 16px;
  background: #f8fafc;
  border-radius: 8px;
}

.progress-text {
  text-align: center;
  margin-top: 8px;
  color: #6b7280;
}

.cards { display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px; }
.card { background:#fff;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px; }
.card.primary { background:linear-gradient(135deg,#1976d2,#2c3e50);color:#fff;min-width:180px; }
.card.primary .lbl { color:rgba(255,255,255,.85); }
.card.primary .num { font-size:32px; }
.card .num { font-size:24px;font-weight:700; }
.card .lbl { color:#777;font-size:12px;margin-top:4px; }

.explain { background:#fffbea;border-left:4px solid #f9a825;padding:14px 18px;border-radius:6px;font-size:13px;line-height:1.8;color:#444;margin-bottom:22px; }

.file-info { background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:16px 18px;margin:0 0 22px; }
.file-info h3 { margin:0 0 12px;font-size:16px;color:#2c3e50; }
.file-info-grid { display:grid;grid-template-columns:120px 1fr;gap:8px 12px;font-size:13px;line-height:1.7; }
.file-info-grid .label { color:#666;font-weight:600; }
.file-info-grid .value { word-break:break-word;overflow-wrap:anywhere; }

table { width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);table-layout:fixed; }
th,td { padding:10px 12px;text-align:left;font-size:13px;border-bottom:1px solid #eee;vertical-align:top;word-break:break-word;overflow-wrap:anywhere; }
th { background:#2c3e50;color:#fff;font-weight:600;white-space:normal;font-size:12px; }
tr:hover { background:#f9fafb; }
code { background:#eef1f4;padding:1px 6px;border-radius:4px;font-size:12px; }

.tag { background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500; }
.tag.ok { background:#e8f5e9;color:#2e7d32; }
.tag.warn { background:#fff3e0;color:#e65100; }
.tag.danger { background:#ffebee;color:#c62828; }
.tag.only-a { background:#fff4f4;color:#c62828; }
.tag.only-b { background:#f4faf4;color:#2e7d32; }

.bar { position:relative;background:#eee;border-radius:10px;height:18px;width:100%;min-width:80px;overflow:hidden; }
.bar .fill { height:100%;border-radius:10px; }
.bar span { position:absolute;left:0;right:0;top:0;line-height:18px;text-align:center;font-size:11px;color:#000;font-weight:600; }

h2 { margin-top:32px;font-size:18px;border-left:4px solid #1976d2;padding-left:10px;color:#2c3e50;font-weight:600; }

.row-main { cursor:pointer; }
.row-main:hover { background:#f0f4f9; }
.row-main .diff-cell { color:#c62828;font-weight:600; }
.row-diff { display:none; }
.row-diff.open { display:table-row; }
.row-diff > td { background:#fafbfc;padding:0; }

.diffs { padding:12px 16px; }
.diff-empty { padding:14px 16px;color:#2e7d32;font-size:13px;background:#eaf6ec;border-radius:6px; }
.diff-row { display:flex;align-items:flex-start;gap:10px;padding:8px 10px;margin:6px 0;border-radius:6px;font-size:13px;line-height:1.6; }
.diff-row.changed { background:#fff8e1;border-left:3px solid #f9a825; }
.diff-row .text { flex:1;word-break:break-word; }
.diff-row .side-a,.diff-row .side-b { padding:4px 0; }
.diff-row .side-a::before { content:"A: ";color:#c62828;font-weight:600; }
.diff-row .side-b::before { content:"B: ";color:#2e7d32;font-weight:600; }

.tag-c { font-size:11px;padding:2px 8px;border-radius:10px;white-space:nowrap;font-weight:600;background:#f9a825;color:#fff;min-width:50px;text-align:center; }

.del { background:#ffd6d6;text-decoration:line-through;color:#a31515;padding:0 2px;border-radius:2px; }
.ins { background:#d6f5d6;color:#1a5e1a;padding:0 2px;border-radius:2px; }

table.summary td { vertical-align:top;font-size:13px;line-height:1.55; }
table.summary td:nth-child(1) { width:60px;text-align:center; }
table.summary td:nth-child(2) { width:120px;color:#666; }
table.summary td:nth-child(3) { font-weight:600;max-width:300px; }
table.summary td:nth-child(4) { width:80px; }
table.summary td:nth-child(5) { width:120px; }
table.summary td:nth-child(6) { width:80px;text-align:center;color:#888; }
table.summary td:nth-child(7) { width:100px;text-align:center;font-weight:600; }
table.summary td:nth-child(8) { width:80px;text-align:center;font-weight:600;color:#c62828; }

tr.ok-row td:nth-child(7) { color:#2e7d32; }
tr.high-row td:nth-child(7) { color:#558b2f; }
tr.mid-row td:nth-child(7) { color:#ef6c00; }
tr.low-row td:nth-child(7) { color:#c62828; }
tr.only-a-row { background:#fff4f4; }
tr.only-b-row { background:#f4faf4; }
tr.only-a-row td:nth-child(7), tr.only-b-row td:nth-child(7) { color:#666; }

.small { color:#888;font-size:12px; }

.diff-list { max-height: 600px; overflow-y: auto; }

.diff-item {
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  border-left: 4px solid;
}

.diff-item.add, .diff-item.only_b { background: #f0fdf4; border-left-color: #22c55e; }
.diff-item.delete, .diff-item.only_a { background: #fef2f2; border-left-color: #ef4444; }
.diff-item.modify { background: #fffbeb; border-left-color: #f59e0b; }

.diff-item.severity-critical { border-left-width: 6px; }
.diff-item.severity-high { border-left-width: 5px; }

.diff-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.diff-index {
  background: #e5e7eb;
  color: #6b7280;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.diff-type { font-weight: 600; }

.severity-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.severity-tag.critical { background: #fee2e2; color: #dc2626; }
.severity-tag.high { background: #fef3c7; color: #d97706; }
.severity-tag.medium { background: #dbeafe; color: #2563eb; }
.severity-tag.low { background: #dcfce7; color: #16a34a; }

.similarity-tag {
  font-size: 12px;
  background: #f3f4f6;
  color: #374151;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: auto;
}

.diff-content { margin-top: 8px; }

.diff-text {
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 8px;
}

.diff-text:last-child { margin-bottom: 0; }

.diff-text-a { background: #f3f4f6; }
.diff-text-b { background: #e0f2fe; }

.text-label {
  font-weight: 600;
  color: #6b7280;
  margin-right: 8px;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
}

.similarity-high { color: #86efac; }
.similarity-medium { color: #fcd34d; }
.similarity-low { color: #fca5a5; }
</style>