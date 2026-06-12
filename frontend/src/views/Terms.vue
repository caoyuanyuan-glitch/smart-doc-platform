<template>
  <div class="terms-container">
    <div class="header-section">
      <h3>术语库</h3>
      <el-button type="primary" @click="showAddModal = true">添加术语</el-button>
    </div>

    <div class="table-section">
      <el-table :data="terms" border>
        <el-table-column prop="non_standard" label="非标准写法" width="150" />
        <el-table-column prop="standard" label="标准写法" width="150" />
        <el-table-column prop="category" label="分类" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="150">
          <template #default="scope">
            <el-button size="small" @click="editTerm(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteTerm(scope.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog title="添加术语" :visible.sync="showAddModal">
      <el-form :model="termForm" label-width="100px">
        <el-form-item label="非标准写法">
          <el-input v-model="termForm.non_standard" />
        </el-form-item>
        <el-form-item label="标准写法">
          <el-input v-model="termForm.standard" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="termForm.category" />
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="showAddModal = false">取消</el-button>
        <el-button type="primary" @click="saveTerm">保存</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { termsAPI } from '@/api'
import { ElMessage } from 'element-plus'

const terms = ref([])
const showAddModal = ref(false)
const editingTerm = ref(null)

const termForm = ref({
  non_standard: '',
  standard: '',
  category: ''
})

onMounted(async () => {
  await loadTerms()
})

async function loadTerms() {
  try {
    const response = await termsAPI.list()
    terms.value = response.data
  } catch (error) {
    ElMessage.error('加载术语失败')
  }
}

function editTerm(term) {
  editingTerm.value = term
  termForm.value = {
    non_standard: term.non_standard,
    standard: term.standard,
    category: term.category
  }
  showAddModal.value = true
}

async function saveTerm() {
  try {
    if (editingTerm.value) {
      await termsAPI.update(editingTerm.value.id, termForm.value)
      ElMessage.success('更新成功')
    } else {
      await termsAPI.create(termForm.value)
      ElMessage.success('创建成功')
    }
    showAddModal.value = false
    editingTerm.value = null
    termForm.value = { non_standard: '', standard: '', category: '' }
    loadTerms()
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

async function deleteTerm(id) {
  try {
    await termsAPI.delete(id)
    loadTerms()
    ElMessage.success('删除成功')
  } catch (error) {
    ElMessage.error('删除失败')
  }
}
</script>

<style>
.terms-container {
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
