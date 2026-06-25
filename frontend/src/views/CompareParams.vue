<template>
  <div class="compare-container">
    <h2 class="page-title">参数数值对比</h2>

    <div class="panel">
      <div class="panel-header">
        <span>上传两个文档，对比相同参数的数值是否一致</span>
        <div class="panel-actions">
          <el-tag size="small" type="info">支持 Word / PDF / Excel</el-tag>
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
            accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md"
          >
            <div class="upload-box" :class="{ filled: fileA }">
              <el-icon style="font-size:36px;color:#3b82f6;margin-bottom:8px;"><Upload /></el-icon>
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
            accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md"
          >
            <div class="upload-box" :class="{ filled: fileB }">
              <el-icon style="font-size:36px;color:#7c3aed;margin-bottom:8px;"><Upload /></el-icon>
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

      <div v-if="loading" class="progress-panel">
        <el-progress :percentage="progress" :stroke-width="16" status="success" />
        <div class="progress-text">{{ progressText }}</div>
      </div>
    </div>

    <div v-if="result" class="result-panel">
      <div class="panel-header">
        <span>对比结果</span>
        <div class="panel-actions">
          <el-tag type="success" size="small">一致: {{ result.match_count }}</el-tag>
          <el-tag type="danger" size="small">不一致: {{ result.diff_count }}</el-tag>
          <el-tag type="warning" size="small">仅A: {{ result.only_a_count }}</el-tag>
          <el-tag size="small">仅B: {{ result.only_b_count }}</el-tag>
        </div>
      </div>

      <div class="cards">
        <div class="card primary">
          <div class="num">{{ result.total }}</div>
          <div class="lbl">参数总数</div>
        </div>
        <div class="card">
          <div class="num" style="color:#22c55e">{{ result.match_count }}</div>
          <div class="lbl">一致</div>
        </div>
        <div class="card">
          <div class="num" style="color:#ef4444">{{ result.diff_count }}</div>
          <div class="lbl">不一致</div>
        </div>
        <div class="card">
          <div class="num" style="color:#f59e0b">{{ result.only_a_count }}</div>
          <div class="lbl">仅A有</div>
        </div>
        <div class="card">
          <div class="num" style="color:#8b5cf6">{{ result.only_b_count }}</div>
          <div class="lbl">仅B有</div>
        </div>
      </div>

      <div class="param-table-wrapper">
        <div class="custom-table-container">
          <table class="param-table">
            <thead>
              <tr>
                <th>参数名称</th>
                <th>文档A内容</th>
                <th>文档B内容</th>
                <th>一致性</th>
                <th>匹配方式</th>
                <th>数据来源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in paginatedResults" :key="idx">
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
                  <div>A: {{ row.source_a || '—' }}</div>
                  <div>B: {{ row.source_b || '—' }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="pagination-row" v-if="result.total > pageSize">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="result.total"
            layout="prev, pager, next, total"
            background
            small
          />
        </div>
      </div>

      <el-collapse v-if="result.extracted_text_a || result.extracted_text_b" style="margin-top:16px">
        <el-collapse-item title="查看提取的原始文本（调试）" name="debug">
          <el-tabs>
            <el-tab-pane label="文档A 提取文本" v-if="result.extracted_text_a">
              <pre class="debug-text">{{ result.extracted_text_a }}</pre>
              <div style="margin-top:4px;color:#9ca3af;font-size:12px">
                从文档A中提取到 {{ result.params_a_count }} 个参数
              </div>
            </el-tab-pane>
            <el-tab-pane label="文档B 提取文本" v-if="result.extracted_text_b">
              <pre class="debug-text">{{ result.extracted_text_b }}</pre>
              <div style="margin-top:4px;color:#9ca3af;font-size:12px">
                从文档B中提取到 {{ result.params_b_count }} 个参数
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Search } from '@element-plus/icons-vue'
import { instance } from '@/api'

const fileA = ref(null)
const fileB = ref(null)
const loading = ref(false)
const progress = ref(0)
const progressText = ref('')
const result = ref(null)
const currentPage = ref(1)
const pageSize = ref(20)

const paginatedResults = computed(() => {
  if (!result.value?.results) return []
  const start = (currentPage.value - 1) * pageSize.value
  return result.value.results.slice(start, start + pageSize.value)
})

function clearFiles() {
  fileA.value = null
  fileB.value = null
  result.value = null
  currentPage.value = 1
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
  if (!fileA.value || !fileB.value) {
    ElMessage.warning('请上传两个文档')
    return
  }

  loading.value = true
  result.value = null
  currentPage.value = 1

  try {
    await updateProgress(10, '正在上传文件...')
    await updateProgress(25, '正在提取参数...')

    const formData = new FormData()
    formData.append('file_a', fileA.value)
    formData.append('file_b', fileB.value)

    await updateProgress(50, '正在对比参数数值...')

    const resp = await instance.post('/compare/params/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    await updateProgress(90, '正在整理结果...')

    result.value = resp.data

    await updateProgress(100, '对比完成')
    ElMessage.success('参数对比完成')

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
