<template>
  <div class="compare-container">
    <h2 class="page-title">参数数值对比</h2>

    <div class="panel">
      <div class="panel-header">
        <span>上传参照文档和多个对比文档，对比相同参数的数值是否一致</span>
        <div class="panel-actions">
          <el-tag size="small" type="info">支持 Word / PDF / Excel</el-tag>
        </div>
      </div>

      <div class="upload-grid">
        <div class="upload-slot">
          <div class="slot-label">参照文档</div>
          <el-upload
            action="#"
            :auto-upload="false"
            :show-file-list="false"
            :before-upload="(f) => { files[0] = f; return false }"
            :on-change="(f) => { files[0] = f.raw || f }"
            accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md"
          >
            <div class="upload-box" :class="{ filled: files[0] }">
              <el-icon style="font-size:36px;color:#3b82f6;margin-bottom:8px;"><Upload /></el-icon>
              <div v-if="!files[0]" class="upload-hint">点击上传参照文档</div>
              <div v-else class="upload-name">{{ files[0].name }}</div>
            </div>
          </el-upload>
        </div>

        <template v-for="(file, idx) in files.slice(1)" :key="idx">
          <div class="vs-badge">VS</div>
          <div class="upload-slot">
            <div class="slot-label">
              对比文档 {{ idx + 1 }}
              <el-button v-if="files.length > 2" type="danger" size="small" circle @click="removeFile(idx + 1)" style="margin-left:6px;">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :before-upload="(f) => { files[idx + 1] = f; return false }"
              :on-change="(f) => { files[idx + 1] = f.raw || f }"
              accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md"
            >
              <div class="upload-box" :class="{ filled: files[idx + 1] }">
                <el-icon style="font-size:36px;color:#7c3aed;margin-bottom:8px;"><Upload /></el-icon>
                <div v-if="!files[idx + 1]" class="upload-hint">点击上传对比文档</div>
                <div v-else class="upload-name">{{ files[idx + 1].name }}</div>
              </div>
            </el-upload>
          </div>
        </template>
      </div>

      <div class="action-row">
        <el-button type="primary" size="large" :loading="loading" :disabled="!files[0] || !files[1]" @click="doCompare">
          <el-icon><Search /></el-icon> 开始对比
        </el-button>
        <el-button size="large" type="success" @click="addFile" :disabled="files.length >= 8">
          <el-icon><Plus /></el-icon> 添加文件
        </el-button>
        <el-button size="large" @click="clearFiles">清空</el-button>
      </div>

      <div v-if="loading" class="progress-panel">
        <el-progress :percentage="progress" :stroke-width="16" status="success" />
        <div class="progress-text">{{ progressText }}</div>
      </div>
    </div>

    <div v-if="allResults.length > 0" class="result-panel">
      <div class="panel-header">
        <span>对比结果（{{ allResults.length }} 组）</span>
        <div class="panel-actions">
          <el-button size="small" @click="clearFiles">重新对比</el-button>
        </div>
      </div>

      <el-tabs v-model="activeTab" type="border-card" class="result-tabs">
        <el-tab-pane
          v-for="(r, ri) in allResults"
          :key="ri"
          :label="'对比 ' + (ri + 1) + ': ' + (r.file_b || '文档')"
          :name="ri"
        >
          <div class="pair-header">
            <span class="pair-label">
              {{ r.file_a }} <strong>VS</strong> {{ r.file_b }}
            </span>
            <div class="pair-tags">
              <el-tag type="success" size="small">一致: {{ r.match_count }}</el-tag>
              <el-tag type="danger" size="small">不一致: {{ r.diff_count }}</el-tag>
              <el-tag type="warning" size="small">仅参照: {{ r.only_a_count }}</el-tag>
              <el-tag size="small">仅对方: {{ r.only_b_count }}</el-tag>
            </div>
          </div>

          <div class="cards">
            <div class="card primary">
              <div class="num">{{ r.total }}</div>
              <div class="lbl">参数总数</div>
            </div>
            <div class="card">
              <div class="num" style="color:#22c55e">{{ r.match_count }}</div>
              <div class="lbl">一致</div>
            </div>
            <div class="card">
              <div class="num" style="color:#ef4444">{{ r.diff_count }}</div>
              <div class="lbl">不一致</div>
            </div>
            <div class="card">
              <div class="num" style="color:#f59e0b">{{ r.only_a_count }}</div>
              <div class="lbl">仅参照有</div>
            </div>
            <div class="card">
              <div class="num" style="color:#8b5cf6">{{ r.only_b_count }}</div>
              <div class="lbl">仅对方有</div>
            </div>
          </div>

          <div class="param-table-wrapper">
            <div class="custom-table-container">
              <table class="param-table">
                <thead>
                  <tr>
                    <th>参数名称</th>
                    <th>{{ r.file_a || '参照文档' }}</th>
                    <th>{{ r.file_b || '对比文档' }}</th>
                    <th>一致性</th>
                    <th>匹配方式</th>
                    <th>数据来源</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in paginateResults(r.results || [], ri)" :key="idx">
                    <td class="param-name-cell">{{ row.param }}</td>
                    <td>{{ row.value_a || '—' }}</td>
                    <td>{{ row.value_b || '—' }}</td>
                    <td class="match-cell">
                      <el-tag
                        :type="row.match === '一致' ? 'success' : row.match === '不一致' ? 'danger' : row.match === '仅A有' ? 'warning' : 'info'"
                        size="small"
                      >
                        {{ row.match }}
                      </el-tag>
                    </td>
                    <td class="fuzzy-cell">
                      <template v-if="row.match === '仅A有' || row.match === '仅B有'">
                        <span class="text-muted">—</span>
                      </template>
                      <template v-else-if="row.fuzzy">
                        <el-tag size="small" type="info" effect="plain">
                          模糊匹配({{ row.fuzzy_score }})
                        </el-tag>
                        <div class="matched-name">→{{ row.matched_param }}</div>
                      </template>
                      <template v-else>
                        <el-tag size="small" type="success" effect="plain">精确匹配</el-tag>
                      </template>
                    </td>
                    <td class="source-cell">
                      <div>参照: {{ row.source_a || '—' }}</div>
                      <div>对比: {{ row.source_b || '—' }}</div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="pagination-row" v-if="(r.results || []).length > pageSize">
              <el-pagination
                v-model:current-page="pages[ri]"
                :page-size="pageSize"
                :total="(r.results || []).length"
                layout="prev, pager, next, total"
                background
                small
              />
            </div>
          </div>

          <el-collapse v-if="r.extracted_text_a || r.extracted_text_b" style="margin-top:16px">
            <el-collapse-item title="查看提取的原始文本（调试）" name="debug">
              <el-tabs>
                <el-tab-pane label="参照文档 提取文本" v-if="r.extracted_text_a">
                  <pre class="debug-text">{{ r.extracted_text_a }}</pre>
                  <div style="margin-top:4px;color:#9ca3af;font-size:12px">
                    从参照文档中提取到 {{ r.params_a_count }} 个参数
                  </div>
                </el-tab-pane>
                <el-tab-pane label="对比文档 提取文本" v-if="r.extracted_text_b">
                  <pre class="debug-text">{{ r.extracted_text_b }}</pre>
                  <div style="margin-top:4px;color:#9ca3af;font-size:12px">
                    从对比文档中提取到 {{ r.params_b_count }} 个参数
                  </div>
                </el-tab-pane>
              </el-tabs>
            </el-collapse-item>
          </el-collapse>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Search, Plus, Close } from '@element-plus/icons-vue'
import { instance } from '@/api'

const files = ref([null, null])
const loading = ref(false)
const progress = ref(0)
const progressText = ref('')
const allResults = ref([])
const activeTab = ref(0)
const pageSize = ref(20)
const pages = reactive({})

function paginateResults(results, tabIdx) {
  if (!results) return []
  const start = ((pages[tabIdx] || 1) - 1) * pageSize.value
  if (pages[tabIdx] === undefined) pages[tabIdx] = 1
  return results.slice(start, start + pageSize.value)
}

function addFile() {
  if (files.value.length < 8) {
    files.value.push(null)
  }
}

function removeFile(index) {
  if (files.value.length > 2) {
    files.value.splice(index, 1)
  }
}

function clearFiles() {
  files.value = [null, null]
  allResults.value = []
  activeTab.value = 0
}

function updateProgress(pct, text) {
  return new Promise(resolve => {
    setTimeout(() => {
      progress.value = pct
      progressText.value = text
      resolve()
    }, 100)
  })
}

async function doCompare() {
  const validFiles = files.value.filter(f => f)
  if (validFiles.length < 2) {
    ElMessage.warning('请至少上传2个文档')
    return
  }

  loading.value = true
  allResults.value = []

  try {
    await updateProgress(10, '正在上传文件...')
    await updateProgress(25, '正在提取参数...')

    const formData = new FormData()
    validFiles.forEach(f => formData.append('files', f))

    await updateProgress(50, '正在对比参数数值...')

    const resp = await instance.post('/compare/params/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    await updateProgress(90, '正在整理结果...')

    allResults.value = resp.data.results || []

    await updateProgress(100, '对比完成')
    ElMessage.success(`参数对比完成，共 ${allResults.value.length} 组结果`)

    setTimeout(() => {
      progress.value = 0
      progressText.value = ''
    }, 1500)
  } catch (e) {
    ElMessage.error('对比失败：' + (e.response?.data?.detail || e.message || '未知错误'))
    progress.value = 0
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
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
  box-shadow: 0 1px 3px rgba(0,0,0,.05);
}

.result-panel {
  background: #fff;
  border-radius: 10px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.08);
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
  flex-wrap: wrap;
}

.upload-slot { flex: 1; max-width: 400px; min-width: 200px; }

.slot-label {
  font-weight: 600;
  margin-bottom: 12px;
  color: #374151;
  display: flex;
  align-items: center;
}

.upload-box {
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  cursor: pointer;
  transition: all .3s;
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
  display: flex;
  align-items: center;
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

.result-tabs { margin-top: 16px; }

.pair-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 6px;
}

.pair-label {
  font-size: 15px;
  color: #1f2937;
}

.pair-label strong { color: #3b82f6; margin: 0 8px; }

.pair-tags { display: flex; gap: 8px; }

.cards { display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px; }
.card { background:#fff;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px; }
.card.primary { background:linear-gradient(135deg,#1976d2,#2c3e50);color:#fff;min-width:180px; }
.card.primary .lbl { color:rgba(255,255,255,.85); }
.card.primary .num { font-size:32px; }
.card .num { font-size:24px;font-weight:700; }
.card .lbl { color:#777;font-size:12px;margin-top:4px; }

.param-table-wrapper {
  margin-top: 8px;
}

.custom-table-container {
  overflow-x: auto;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
}

.param-table {
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;
  background: #fff;
  font-size: 13px;
}

.param-table thead {
  position: sticky;
  top: 0;
  z-index: 10;
}

.param-table th {
  background: #f5f7fa;
  color: #303133;
  font-weight: 600;
  font-size: 13px;
  padding: 12px 10px;
  text-align: left;
  border-bottom: 2px solid #dcdfe6;
  white-space: nowrap;
}

.param-table td {
  padding: 10px;
  border-bottom: 1px solid #ebeef5;
  color: #303133;
  vertical-align: top;
}

.param-table tbody tr:hover {
  background: #f5f7fa;
}

.param-name-cell {
  font-weight: 600;
  color: #1f2937;
  white-space: nowrap;
}

.match-cell {
  text-align: center;
  white-space: nowrap;
}

.fuzzy-cell {
  text-align: center;
  font-size: 12px;
}

.source-cell {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}

.text-muted {
  color: #c0c4cc;
}

.matched-name {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

.pagination-row {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.debug-text {
  background: #f5f5f5;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  max-height: 400px;
  overflow-y: auto;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  color: #374151;
}
</style>
