<template>
  <div class="convert-rules-page">
    <div class="page-header">
      <h2>转换规则库</h2>
      <p class="page-desc">管理格式转换过程中应用的规则，所有启用的规则将在每次转换时自动执行验证</p>
    </div>

    <div class="panel">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="margin:0">规则列表</h3>
        <div>
          <el-button v-if="selectedRuleIds.length" type="danger" size="small" @click="batchDeleteRules">
            批量删除 ({{ selectedRuleIds.length }})
          </el-button>
          <el-button type="primary" size="small" @click="showRuleDialog = true">新增规则</el-button>
        </div>
      </div>
      <el-table :data="convertRules" border style="width:100%" v-loading="rulesLoading"
        @selection-change="onRuleSelectionChange">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="rule_number" label="编号" width="80" />
        <el-table-column prop="category" label="分类" width="100">
          <template #default="scope">
            <el-tag size="small" :type="categoryTagType(scope.row.category)">{{ scope.row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="规则描述" min-width="300" />
        <el-table-column prop="created_at" label="创建时间" width="120">
          <template #default="scope">
            {{ scope.row.created_at ? scope.row.created_at.slice(0,10) : '' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="scope">
            <el-button size="small" type="danger" link @click="deleteRule(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="convertRules.length === 0 && !rulesLoading" class="empty-hint">暂无转换规则</div>
    </div>

    <el-dialog v-model="showRuleDialog" title="新增转换规则" width="480px">
      <el-form label-width="80px">
        <el-form-item label="分类">
          <el-select v-model="newRule.category" placeholder="选择分类" style="width:100%">
            <el-option label="内容" value="内容" />
            <el-option label="图片" value="图片" />
            <el-option label="编号" value="编号" />
            <el-option label="表格标题" value="表格标题" />
            <el-option label="列表-无序" value="列表-无序" />
            <el-option label="列表-有序" value="列表-有序" />
            <el-option label="结构" value="结构" />
            <el-option label="模板" value="模板" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则描述">
          <el-input v-model="newRule.description" type="textarea" :rows="3" placeholder="描述规则的具体行为" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRuleDialog = false">取消</el-button>
        <el-button type="primary" @click="addRule" :loading="addingRule">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { convertRulesAPI } from '@/api'

const convertRules = ref([])
const rulesLoading = ref(false)
const selectedRuleIds = ref([])
const showRuleDialog = ref(false)
const addingRule = ref(false)
const newRule = ref({ category: '内容', description: '' })

function categoryTagType(cat) {
  const map = { '内容': '', '图片': 'success', '编号': 'info', '表格标题': 'warning', '列表-无序': '', '列表-有序': '', '结构': 'danger', '模板': 'warning' }
  return map[cat] || ''
}

async function loadRules() {
  rulesLoading.value = true
  try {
    const resp = await convertRulesAPI.list()
    if (resp.data && Array.isArray(resp.data)) {
      convertRules.value = resp.data
    }
  } catch (e) {
    console.error('加载规则失败', e)
  } finally {
    rulesLoading.value = false
  }
}

function onRuleSelectionChange(selection) {
  selectedRuleIds.value = selection.map(r => r.id)
}

async function addRule() {
  if (!newRule.value.description) {
    ElMessage.warning('请填写规则描述')
    return
  }
  addingRule.value = true
  try {
    await convertRulesAPI.create(newRule.value.category, newRule.value.description)
    ElMessage.success('规则已添加')
    showRuleDialog.value = false
    newRule.value = { category: '内容', description: '' }
    loadRules()
  } catch (e) {
    ElMessage.error('添加失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    addingRule.value = false
  }
}

async function deleteRule(row) {
  try {
    await ElMessageBox.confirm(`确定删除规则 ${row.rule_number}？`, '确认', { type: 'warning' })
    await convertRulesAPI.delete(row.id)
    ElMessage.success('已删除')
    loadRules()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error('删除失败')
    }
  }
}

async function batchDeleteRules() {
  try {
    await ElMessageBox.confirm(`确定批量删除 ${selectedRuleIds.value.length} 条规则？`, '确认', { type: 'warning' })
    await convertRulesAPI.bulkDelete(selectedRuleIds.value)
    ElMessage.success(`已删除 ${selectedRuleIds.value.length} 条`)
    selectedRuleIds.value = []
    loadRules()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error('批量删除失败')
    }
  }
}

onMounted(() => loadRules())
</script>

<style scoped>
.convert-rules-page { padding: 0; }

.page-header {
  margin-bottom: 20px;
}
.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 6px 0;
}
.page-desc {
  color: #6b7280;
  font-size: 13px;
  margin: 0;
}

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.panel h3 {
  font-size: 16px;
  color: #374151;
}

.empty-hint {
  text-align: center;
  padding: 30px;
  color: #9ca3af;
  font-size: 13px;
}
</style>
