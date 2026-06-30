<template>
  <div class="rules-manage-container">
    <div class="page-title-row">
      <h2 class="page-title">润色规则管理</h2>
    </div>

    <div class="panel rules-panel">
      <div class="rules-toolbar">
        <div class="rules-actions">
          <el-button type="primary" @click="openAddDialog">添加规则</el-button>
          <el-button :disabled="selection.length === 0" @click="batchDelete">批量删除 ({{ selection.length }})</el-button>
          <el-dropdown @command="handleExport">
            <el-button>导出规则<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
<el-dropdown-item command="json">JSON格式导出</el-dropdown-item>
              <el-dropdown-item command="csv">CSV格式导出</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button @click="triggerImport">导入规则</el-button>
          <el-dropdown @command="downloadTemplate">
            <el-button>下载模板<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
<el-dropdown-item command="json">JSON格式模板</el-dropdown-item>
              <el-dropdown-item command="csv">CSV格式模板</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <input ref="importInputRef" type="file" style="display: none" accept=".json,.csv" @change="onFileImport" />
        </div>
        <div class="rules-filters">
          <el-select v-model="filterType" placeholder="分类" clearable style="width: 160px" @change="fetchRules">
            <el-option label="全部" value="" />
            <el-option label="系统规则" value="system_rule" />
            <el-option label="术语替换" value="replacement_rule" />
            <el-option label="禁止规则" value="forbidden_rule" />
            <el-option label="句式适用" value="sentence_applicability_rule" />
          </el-select>
          <el-select v-model="filterEnabled" clearable style="width: 120px" @change="fetchRules">
            <el-option label="全部状态" :value="undefined" />
            <el-option label="启用" :value="true" />
            <el-option label="禁用" :value="false" />
          </el-select>
        </div>
      </div>

      <el-table
        :data="rulesData"
        style="width: 100%"
        @selection-change="onSelectionChange"
        border
        stripe
        v-loading="loading"
      >
        <el-table-column type="selection" width="42" />
        <el-table-column prop="id" label="编号" width="60" />
        <el-table-column prop="rule_name" label="规则名称" width="140">
          <template #default="{ row }">
            <template v-if="row.rule_name">{{ row.rule_name }}</template>
            <template v-else>
              <el-tag :type="typeTag(row.rule_type)" size="small">{{ typeLabel(row.rule_type) }}</el-tag>
            </template>
          </template>
        </el-table-column>
        <el-table-column prop="rule_type" label="分类" width="100">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.rule_type)" size="small">{{ typeLabel(row.rule_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="match_pattern" label="匹配模式" min-width="200" show-overflow-tooltip />
        <el-table-column prop="replacement_text" label="替换文本" min-width="200" show-overflow-tooltip />
        <el-table-column prop="priority_level" label="优先级" width="80" align="center" />
        <el-table-column prop="trigger_count" label="触发次数" width="90" align="center" />
        <el-table-column prop="enabled" label="状态" width="70" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="(val) => toggleRule(row.id, val)" />
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="removeRule(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="rules-pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchRules"
        />
      </div>
    </div>

    <!-- 添加/编辑弹窗 -->
    <el-dialog
      v-model="formDialog"
      :title="formMode === 'add' ? '添加规则' : '编辑规则'"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" label-width="100px">
        <el-form-item label="规则名称" required>
          <el-input v-model="form.rule_name" placeholder="如'术语替换''祈使句规范'" />
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="form.rule_type" style="width: 100%" :disabled="formMode === 'edit'">
            <el-option label="系统规则" value="system_rule" />
            <el-option label="术语替换" value="replacement_rule" />
            <el-option label="禁止规则" value="forbidden_rule" />
            <el-option label="句式适用" value="sentence_applicability_rule" />
          </el-select>
        </el-form-item>
        <el-form-item label="匹配模式" required>
          <el-input v-model="form.match_pattern" type="textarea" :rows="2" placeholder="匹配的正则或原文" />
        </el-form-item>
        <el-form-item label="替换文本" required>
          <el-input v-model="form.replacement_text" type="textarea" :rows="2" placeholder="替换后的文本" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="用途描述（选填）" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="form.priority_level" :min="0" :max="1000" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.enabled" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formDialog = false">取消</el-button>
        <el-button type="primary" :loading="formSubmitting" @click="submitForm">
          {{ formMode === 'add' ? '添加' : '保存' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'

const API = '/api/polish-rules'

const loading = ref(false)
const rulesData = ref([])
const selection = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterType = ref('')
const filterEnabled = ref(undefined)
const importInputRef = ref(null)

const formDialog = ref(false)
const formMode = ref('add')
const formSubmitting = ref(false)
const formRef = ref(null)
const editingId = ref(null)
const form = ref({
  rule_name: '',
  rule_type: 'system_rule',
  engine_key: '',
  rule_key: '',
  match_pattern: '',
  replacement_text: '',
  description: '',
  priority_level: 0,
  enabled: true,
})

function genRuleKey() {
  return `manual:${form.value.rule_type}:${Date.now()}`
}

function resetForm() {
  form.value = { rule_name: '', rule_type: 'system_rule', engine_key: '', rule_key: '', match_pattern: '', replacement_text: '', description: '', priority_level: 0, enabled: true }
  editingId.value = null
}

function openAddDialog() {
  formMode.value = 'add'
  resetForm()
  form.value.rule_key = genRuleKey()
  formDialog.value = true
}

function onSelectionChange(s) { selection.value = s }

async function fetchRules() {
  loading.value = true
  try {
    const p = new URLSearchParams({
      skip: String((page.value - 1) * pageSize.value),
      limit: String(pageSize.value),
    })
    if (filterType.value) p.set('rule_type', filterType.value)
    if (filterEnabled.value !== undefined && filterEnabled.value !== '') p.set('enabled', String(filterEnabled.value))
    const resp = await fetch(`${API}/?${p}`)
    const data = await resp.json()
    rulesData.value = data.items || []
    total.value = data.total || 0
  } catch { ElMessage.error('加载规则失败') } finally { loading.value = false }
}

function openEditDialog(row) {
  formMode.value = 'edit'
  editingId.value = row.id
  form.value = { rule_name: row.rule_name || '', rule_type: row.rule_type, engine_key: row.engine_key || '', rule_key: row.rule_key, match_pattern: row.match_pattern, replacement_text: row.replacement_text || '', description: row.description || '', priority_level: row.priority_level, enabled: row.enabled }
  formDialog.value = true
}

async function submitForm() {
  if (!form.value.rule_name) { ElMessage.warning('规则名称不能为空'); return }
  if (!form.value.match_pattern) { ElMessage.warning('匹配模式不能为空'); return }
  if (!form.value.replacement_text) { ElMessage.warning('替换文本不能为空'); return }
  formSubmitting.value = true
  try {
    if (formMode.value === 'add') {
      await fetch(`${API}/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form.value) })
      ElMessage.success('已添加')
    } else {
      await fetch(`${API}/${editingId.value}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form.value) })
      ElMessage.success('已更新')
    }
    formDialog.value = false
    await fetchRules()
  } catch { ElMessage.error('操作失败') } finally { formSubmitting.value = false }
}

async function removeRule(id) {
  try {
    await ElMessageBox.confirm('确定删除该规则？', '确认删除', { type: 'warning' })
    await fetch(`${API}/${id}`, { method: 'DELETE' })
    ElMessage.success('已删除')
    await fetchRules()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

async function batchDelete() {
  if (selection.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selection.value.length} 条规则？`, '批量删除', { type: 'warning' })
    await fetch(`${API}/batch-delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: selection.value.map(r => r.id) }) })
    ElMessage.success('批量删除完成')
    selection.value = []
    await fetchRules()
  } catch (e) { if (e !== 'cancel') ElMessage.error('批量删除失败') }
}

async function toggleRule(id, enabled) {
  try { await fetch(`${API}/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) }) }
  catch { ElMessage.error('操作失败'); await fetchRules() }
}

function handleExport(format) {
  const p = new URLSearchParams()
  if (filterType.value) p.set('rule_type', filterType.value)
  window.open(`${API}/export/${format}?${p}`, '_blank')
}

function triggerImport() { if (importInputRef.value) { importInputRef.value.value = ''; importInputRef.value.click() } }

function downloadTemplate(format) {
  const sample = {
    规则名称: '示例规则名称',
    规则分类: 'replacement_rule',
    匹配模式: '待匹配的原文或正则',
    替换文本: '替换后的文本',
    说明: '规则说明（可选）。分类可选值: system_rule/系统规则, replacement_rule/术语替换, forbidden_rule/禁止规则, sentence_applicability_rule/句式适用',
    优先级: 0,
    是否启用: true,
  }

  let content, filename, mime
  if (format === 'json') {
    content = JSON.stringify([sample], null, 2)
    filename = '润色规则模板.json'
    mime = 'application/json'
  } else {
    const headers = Object.keys(sample).join(',')
    const values = Object.values(sample).map(v => {
      if (typeof v === 'string' && v.includes(',')) return `"${v}"`
      return String(v)
    }).join(',')
    content = '\uFEFF' + headers + '\n' + values
    filename = '润色规则模板.csv'
    mime = 'text/csv'
  }

  const blob = new Blob([content], { type: `${mime};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url)
}

async function onFileImport(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const ext = file.name.split('.').pop().toLowerCase()
  const fd = new FormData(); fd.append('file', file)
  try {
    const resp = await fetch(`${API}/import/${ext}`, { method: 'POST', body: fd })
    const data = await resp.json()
    if (data.ok) { ElMessage.success(`导入完成：新增 ${data.created} 条，更新 ${data.updated} 条`); await fetchRules() }
    else ElMessage.error('导入失败')
  } catch { ElMessage.error('导入失败') }
}

function typeLabel(t) {
  const m = { system_rule: '系统规则', replacement_rule: '术语替换', forbidden_rule: '禁止规则', sentence_applicability_rule: '句式适用' }
  return m[t] || t
}

function typeTag(t) {
  const m = { system_rule: 'primary', replacement_rule: '', forbidden_rule: 'danger', sentence_applicability_rule: 'warning' }
  return m[t] || ''
}

function fmtTime(dt) { return dt ? new Date(dt).toLocaleString('zh-CN', { hour12: false }) : '' }

onMounted(fetchRules)
</script>

<style scoped>
.rules-manage-container { width: 100%; }
.page-title-row { display: flex; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 22px; font-weight: 700; color: #111827; margin: 0; }
.rules-panel { padding: 20px; }
.rules-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
.rules-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.rules-filters { display: flex; gap: 8px; }
.rules-pagination { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
