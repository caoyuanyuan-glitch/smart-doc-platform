<template>
  <div class="rules-container">
    <div class="header-section">
      <h3>规则管理</h3>
      <el-button type="primary" @click="showAddModal = true">添加规则</el-button>
    </div>

    <div class="table-section">
      <el-table :data="rules" border>
        <el-table-column prop="rule_no" label="规则编号" width="120" />
        <el-table-column prop="category" label="分类" width="100" />
        <el-table-column prop="description" label="规则描述" />
        <el-table-column prop="regex" label="正则表达式" width="200" />
        <el-table-column prop="example" label="示例" width="150" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="150">
          <template #default="scope">
            <el-button size="small" @click="editRule(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteRule(scope.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog title="添加规则" :visible.sync="showAddModal">
      <el-form :model="ruleForm" label-width="100px">
        <el-form-item label="规则编号">
          <el-input v-model="ruleForm.rule_no" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="ruleForm.category">
            <el-option label="字词" value="字词" />
            <el-option label="句子" value="句子" />
            <el-option label="标点" value="标点" />
            <el-option label="段落" value="段落" />
            <el-option label="逻辑" value="逻辑" />
            <el-option label="拼写" value="拼写" />
            <el-option label="句式" value="句式" />
            <el-option label="语法" value="语法" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则描述">
          <el-input v-model="ruleForm.description" />
        </el-form-item>
        <el-form-item label="正则表达式">
          <el-input v-model="ruleForm.regex" />
        </el-form-item>
        <el-form-item label="示例">
          <el-input v-model="ruleForm.example" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveRule">保存</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { rulesAPI } from '@/api'
import { ElMessage } from 'element-plus'

const rules = ref([])
const showAddModal = ref(false)
const editingRule = ref(null)

const ruleForm = ref({
  rule_no: '',
  category: '',
  description: '',
  regex: '',
  example: ''
})

onMounted(async () => {
  await loadRules()
})

async function loadRules() {
  try {
    const response = await rulesAPI.list()
    rules.value = response.data
  } catch (error) {
    ElMessage.error('加载规则失败')
  }
}

function editRule(rule) {
  editingRule.value = rule
  ruleForm.value = {
    rule_no: rule.rule_no,
    category: rule.category,
    description: rule.description,
    regex: rule.regex,
    example: rule.example
  }
  showAddModal.value = true
}

async function saveRule() {
  try {
    if (editingRule.value) {
      await rulesAPI.update(editingRule.value.id, ruleForm.value)
      ElMessage.success('更新成功')
    } else {
      await rulesAPI.create(ruleForm.value)
      ElMessage.success('创建成功')
    }
    showAddModal.value = false
    editingRule.value = null
    ruleForm.value = { rule_no: '', category: '', description: '', regex: '', example: '' }
    loadRules()
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

async function deleteRule(id) {
  try {
    await rulesAPI.delete(id)
    loadRules()
    ElMessage.success('删除成功')
  } catch (error) {
    ElMessage.error('删除失败')
  }
}
</script>

<style>
.rules-container {
  padding: 20px;
}

.header-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-section h3 {
  margin: 0;
  color: #333;
}

.table-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
}
</style>
