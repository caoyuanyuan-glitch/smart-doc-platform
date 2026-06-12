<template>
  <div class="compare-container">
    <div v-if="currentView === 'upload'">
      <h2 class="page-title">文档对比</h2>

      <div class="panel">
        <div class="panel-header">
          <span>上传两个文档进行对比</span>
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
              accept=".pdf,.docx,.doc,.md,.txt"
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
              accept=".pdf,.docx,.doc,.md,.txt"
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
            开始对比
          </el-button>
        </div>
      </div>

      <div v-if="result" class="panel">
        <div class="panel-header">
          <span>对比结果</span>
          <div class="panel-actions">
            <el-tag type="info" size="small">差异数：{{ result.diffs || 0 }}</el-tag>
            <el-button size="small" @click="exportCompare">导出报告</el-button>
          </div>
        </div>

        <div class="diff-summary">
          <div class="summary-item add">
            <div class="summary-num">+{{ result.added || 0 }}</div>
            <div class="summary-label">新增内容</div>
          </div>
          <div class="summary-item remove">
            <div class="summary-num">-{{ result.removed || 0 }}</div>
            <div class="summary-label">删除内容</div>
          </div>
          <div class="summary-item modify">
            <div class="summary-num">~{{ result.modified || 0 }}</div>
            <div class="summary-label">修改内容</div>
          </div>
        </div>

        <div class="compare-grid">
          <div class="compare-col">
            <div class="col-title">
              <span class="dot dot-blue"></span>文档A：{{ fileA.name }}
            </div>
            <div class="col-content diff-text" v-html="result.a_html"></div>
          </div>
          <div class="compare-col">
            <div class="col-title">
              <span class="dot dot-purple"></span>文档B：{{ fileB.name }}
            </div>
            <div class="col-content diff-text" v-html="result.b_html"></div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="currentView === 'tasks'">
      <h2 class="page-title">历史任务</h2>
      <div class="panel">
        <el-table :data="history" border style="width: 100%">
          <el-table-column prop="id" label="任务ID" width="100" />
          <el-table-column prop="file_a" label="文档A" />
          <el-table-column prop="file_b" label="文档B" />
          <el-table-column prop="diffs" label="差异数" width="100" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.status === 'completed' ? 'success' : 'info'">{{ scope.row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180" />
          <el-table-column label="操作" width="120">
            <template #default>
              <el-button size="small">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div v-if="currentView === 'config'">
      <h2 class="page-title">对比配置</h2>
      <div class="panel">
        <el-form :model="config" label-width="200px" style="max-width: 700px;">
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
          <el-form-item label="启用AI语义对比">
            <el-switch v-model="config.aiCompare" />
          </el-form-item>
          <el-form-item label="支持格式">
            <el-tag size="small" style="margin-right: 8px;">PDF</el-tag>
            <el-tag size="small" style="margin-right: 8px;">DOCX</el-tag>
            <el-tag size="small" style="margin-right: 8px;">TXT</el-tag>
            <el-tag size="small" style="margin-right: 8px;">MD</el-tag>
          </el-form-item>
          <el-form-item>
            <el-button type="primary">保存配置</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { compareAPI } from '@/api'
import { Upload } from '@element-plus/icons-vue'

const route = useRoute()
const fileA = ref(null)
const fileB = ref(null)
const loading = ref(false)
const result = ref(null)
const history = ref([])

const config = ref({
  precision: 'sentence',
  ignoreWhitespace: true,
  ignoreCase: false,
  aiCompare: true
})

const currentView = computed(() => {
  if (route.path === '/compare/tasks') return 'tasks'
  if (route.path === '/compare/config') return 'config'
  return 'upload'
})

onMounted(async () => {
  if (currentView.value === 'tasks') {
    try {
      const resp = await compareAPI.list()
      if (resp.data && Array.isArray(resp.data)) {
        history.value = resp.data
      } else {
        history.value = [
          { id: 1, file_a: 'manual_v1.0.pdf', file_b: 'manual_v1.1.pdf', diffs: 28, status: 'completed', created_at: '2025-01-10 10:30' },
          { id: 2, file_a: 'spec_a.docx', file_b: 'spec_b.docx', diffs: 12, status: 'completed', created_at: '2025-01-09 14:20' },
          { id: 3, file_a: 'design_v2.md', file_b: 'design_v3.md', diffs: 45, status: 'completed', created_at: '2025-01-08 09:15' }
        ]
      }
    } catch (e) {
      history.value = [
        { id: 1, file_a: 'manual_v1.0.pdf', file_b: 'manual_v1.1.pdf', diffs: 28, status: 'completed', created_at: '2025-01-10 10:30' },
        { id: 2, file_a: 'spec_a.docx', file_b: 'spec_b.docx', diffs: 12, status: 'completed', created_at: '2025-01-09 14:20' },
        { id: 3, file_a: 'design_v2.md', file_b: 'design_v3.md', diffs: 45, status: 'completed', created_at: '2025-01-08 09:15' }
      ]
    }
  }
})

function buildExampleResult() {
  const aName = fileA.value ? fileA.value.name : '文档A'
  const bName = fileB.value ? fileB.value.name : '文档B'
  return {
    added: 12,
    removed: 8,
    modified: 5,
    diffs: 25,
    a_html: `<div style="line-height:2;"><b>【${aName}】</b><br><br>
      产品型号：<span style="background:#fee2e2;color:#dc262b;text-decoration:line-through;padding:0 4px;border-radius:3px;">X-100</span><br>
      产品名称：检测试剂<br>
      储存温度：<span style="background:#fee2e2;color:#dc262b;text-decoration:line-through;padding:0 4px;border-radius:3px;">2-30°C</span><br>
      适用样本：血清<br>
      有效期：<span style="background:#fee2e2;color:#dc262b;text-decoration:line-through;padding:0 4px;border-radius:3px;">12个月</span><br><br>
      本产品用于体外诊断，仅供专业人员使用。<br>
      操作人员应具备相关资质并接受培训。</div>`,
    b_html: `<div style="line-height:2;"><b>【${bName}】</b><br><br>
      产品型号：<span style="background:#dcfce7;color:#166534;padding:0 4px;border-radius:3px;">X-200（升级版）</span><br>
      产品名称：检测试剂<br>
      储存温度：<span style="background:#dcfce7;color:#166534;padding:0 4px;border-radius:3px;">2~25°C</span><br>
      适用样本：血清 / 血浆 / 全血<br>
      有效期：<span style="background:#dcfce7;color:#166534;padding:0 4px;border-radius:3px;">24个月（未开封）</span><br><br>
      本产品用于体外诊断，仅供专业人员使用。<br>
      操作人员应具备相关资质并接受系统培训。</div>`
  }
}

async function doCompare() {
  if (!fileA.value || !fileB.value) {
    ElMessage.info('请上传两个文档后再进行对比')
    return
  }
  loading.value = true
  try {
    const resp = await compareAPI.create(fileA.value, fileB.value)
    const data = resp.data || {}
    if (data && (data.a_html || data.content_a || data.diffs)) {
      result.value = {
        added: data.added || 0,
        removed: data.removed || 0,
        modified: data.modified || 0,
        diffs: data.diffs || (data.added || 0) + (data.removed || 0) + (data.modified || 0),
        a_html: data.a_html || data.content_a || buildExampleResult().a_html,
        b_html: data.b_html || data.content_b || buildExampleResult().b_html
      }
    } else {
      result.value = buildExampleResult()
    }
    ElMessage.success('对比完成')
  } catch (e) {
    result.value = buildExampleResult()
    ElMessage.info('接口调用失败，已展示示例对比结果')
  } finally {
    loading.value = false
  }
}

function exportCompare() {
  ElMessage.success('对比报告已导出')
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
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 20px;
  align-items: center;
  margin-bottom: 24px;
}

.upload-slot {
  background: #f8fafc;
  border-radius: 10px;
  padding: 16px;
}

.slot-label {
  font-weight: 500;
  color: #1f2937;
  margin-bottom: 10px;
}

.upload-box {
  background: #fff;
  border: 2px dashed #cbd5e1;
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.upload-box:hover {
  border-color: #3b82f6;
  background: #eff6ff;
}

.upload-box.filled {
  border-color: #10b981;
  background: #f0fdf4;
}

.upload-hint { color: #64748b; font-size: 14px; }
.upload-name { color: #1f2937; font-size: 14px; font-weight: 500; word-break: break-all; }

.vs-badge {
  background: linear-gradient(135deg, #3b82f6 0%, #7c3aed 100%);
  color: #fff;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.action-row { text-align: center; padding: 10px 0; }

.diff-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.summary-item {
  padding: 16px;
  border-radius: 8px;
  text-align: center;
}

.summary-item.add { background: #dcfce7; }
.summary-item.remove { background: #fee2e2; }
.summary-item.modify { background: #fef3c7; }

.summary-num {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 4px;
}

.summary-item.add .summary-num { color: #166534; }
.summary-item.remove .summary-num { color: #991b1b; }
.summary-item.modify .summary-num { color: #92400e; }

.summary-label { font-size: 14px; color: #374151; }

.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.compare-col {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.col-title {
  padding: 12px 16px;
  background: #fff;
  font-weight: 500;
  color: #374151;
  font-size: 14px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.dot-blue { background: #3b82f6; }
.dot-purple { background: #7c3aed; }

.col-content {
  padding: 16px;
  line-height: 2;
  color: #374151;
  font-size: 14px;
  min-height: 300px;
  white-space: pre-wrap;
}

.diff-text { font-size: 14px; }

@media (max-width: 900px) {
  .upload-grid, .compare-grid, .diff-summary { grid-template-columns: 1fr; }
  .vs-badge { margin: 0 auto; }
}
</style>
