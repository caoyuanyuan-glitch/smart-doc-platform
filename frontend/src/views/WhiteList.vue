<template>
  <div class="whitelist-container">
    <div class="page-header">
      <h2>白名单管理</h2>
      <div class="header-actions">
        <el-button type="primary" @click="handleAdd">
          <el-icon><Plus /></el-icon> 新增条目
        </el-button>
        <el-button @click="handleImport">
          <el-icon><Upload /></el-icon> 批量导入
        </el-button>
        <el-button @click="handleExport" :disabled="selectedRows.length === 0">
          <el-icon><Download /></el-icon> 导出选中
        </el-button>
        <el-button type="danger" @click="handleBatchDelete" :disabled="selectedRows.length === 0">
          <el-icon><Delete /></el-icon> 批量删除
        </el-button>
      </div>
    </div>

    <el-tabs v-model="activeCategory" @tab-change="handleCategoryChange">
      <el-tab-pane label="全部" name="all">
        <span slot="label">
          全部 <el-badge :value="totalCount" :max="999" class="badge" />
        </span>
      </el-tab-pane>
      <el-tab-pane v-for="cat in categories" :key="cat.key" :label="cat.name" :name="cat.key">
        <span slot="label">
          {{ cat.name }} <el-badge :value="cat.count" :max="999" class="badge" />
        </span>
      </el-tab-pane>
    </el-tabs>

    <div class="table-toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索词条..."
        prefix-icon="Search"
        clearable
        style="width: 300px"
        @input="handleSearch"
      />
      <span class="total-text">共 {{ filteredData.length }} 条</span>
    </div>

    <el-table
      ref="tableRef"
      :data="filteredData"
      border
      stripe
      style="width: 100%"
      @selection-change="handleSelectionChange"
      row-key="id"
      :key="tableKey"
    >
      <el-table-column type="selection" width="55" />
      <el-table-column prop="word" label="词条" min-width="200" fixed>
        <template #default="scope">
          <template v-if="scope.row.isEditing">
            <el-input v-model="scope.row.editWord" size="small" />
          </template>
          <template v-else>
            <span class="word-text">{{ scope.row.word }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="120">
        <template #default="scope">
          <template v-if="scope.row.isEditing">
            <el-select v-model="scope.row.editCategory" size="small" style="width: 100%">
              <el-option label="产品名" value="产品名" />
              <el-option label="品牌名" value="品牌名" />
              <el-option label="文档编号" value="文档编号" />
              <el-option label="版本号" value="版本号" />
              <el-option label="货号" value="货号" />
              <el-option label="科学术语" value="科学术语" />
              <el-option label="生化术语" value="生化术语" />
              <el-option label="设备型号" value="设备型号" />
              <el-option label="域名" value="域名" />
              <el-option label="邮箱" value="邮箱" />
            </el-select>
          </template>
          <template v-else>
            <el-tag size="small" :type="getCategoryTagType(scope.row.category)">
              {{ scope.row.category }}
            </el-tag>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="250">
        <template #default="scope">
          <template v-if="scope.row.isEditing">
            <el-input v-model="scope.row.editDescription" size="small" />
          </template>
          <template v-else>
            <span class="description-text">{{ scope.row.description || '-' }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="scope">
          <template v-if="scope.row.isEditing">
            <el-button size="small" type="success" @click="handleSave(scope.row)">保存</el-button>
            <el-button size="small" @click="handleCancelEdit(scope.row)">取消</el-button>
          </template>
          <template v-else>
            <el-button size="small" type="primary" @click="handleEdit(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="importDialogVisible"
      title="批量导入白名单"
      width="500px"
    >
      <div class="import-tips">
        <p>请选择或拖拽文件上传，支持 CSV 或 TXT 格式</p>
        <p class="tips-detail">
          格式说明：每行一个词条，格式为 <code>词条,分类,描述</code><br/>
          例如：<code>MGISP-960,产品名,MGI样本制备系统</code>
        </p>
      </div>
      <el-upload
        ref="uploadRef"
        class="import-upload"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".csv,.txt"
        :on-change="handleFileChange"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">将文件拖到此处，或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 csv、txt 格式</div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitImport" :loading="importLoading">确认导入</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="addDialogVisible"
      title="新增白名单条目"
      width="500px"
    >
      <el-form :model="addForm" label-width="80px">
        <el-form-item label="词条" required>
          <el-input v-model="addForm.word" placeholder="请输入词条" />
        </el-form-item>
        <el-form-item label="分类" required>
          <el-select v-model="addForm.category" placeholder="请选择分类" style="width: 100%">
            <el-option label="产品名" value="产品名" />
            <el-option label="品牌名" value="品牌名" />
            <el-option label="文档编号" value="文档编号" />
            <el-option label="版本号" value="版本号" />
            <el-option label="货号" value="货号" />
            <el-option label="科学术语" value="科学术语" />
            <el-option label="生化术语" value="生化术语" />
            <el-option label="设备型号" value="设备型号" />
            <el-option label="域名" value="域名" />
            <el-option label="邮箱" value="邮箱" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="addForm.description" type="textarea" :rows="3" placeholder="请输入描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAdd" :loading="addLoading">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, Download, Delete, UploadFilled, Search } from '@element-plus/icons-vue'
import axios from 'axios'

const activeCategory = ref('all')
const searchKeyword = ref('')
const selectedRows = ref([])
const tableKey = ref(0)
const tableRef = ref(null)
const categories = ref([])
const tableData = ref([])
const importDialogVisible = ref(false)
const addDialogVisible = ref(false)
const importLoading = ref(false)
const addLoading = ref(false)
const uploadRef = ref(null)
const importFileContent = ref('')

const addForm = reactive({
  word: '',
  category: '',
  description: ''
})

const categoryNames = {
  'products': '产品名',
  'brands': '品牌名',
  'document_ids': '文档编号',
  'terms': '专业术语',
  'domains': '域名邮箱'
}

const totalCount = computed(() => tableData.value.length)

const filteredData = computed(() => {
  let data = tableData.value
  
  if (activeCategory.value !== 'all') {
    const categoryName = categoryNames[activeCategory.value] || activeCategory.value
    data = data.filter(item => item.category === categoryName)
  }
  
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    data = data.filter(item => 
      item.word.toLowerCase().includes(keyword) ||
      (item.description && item.description.toLowerCase().includes(keyword))
    )
  }
  
  return data
})

function getCategoryTagType(category) {
  const typeMap = {
    '产品名': 'success',
    '品牌名': 'primary',
    '文档编号': 'warning',
    '版本号': 'warning',
    '货号': 'warning',
    '科学术语': 'info',
    '生化术语': 'info',
    '设备型号': 'info',
    '域名': 'danger',
    '邮箱': 'danger'
  }
  return typeMap[category] || ''
}

async function fetchCategories() {
  try {
    const token = localStorage.getItem('token')
    const response = await axios.get('/api/whitelist/categories', {
      headers: { Authorization: `Bearer ${token}` }
    })
    categories.value = response.data.map(cat => ({
      key: cat.key,
      name: cat.name,
      count: cat.count
    }))
  } catch (error) {
    console.error('获取分类失败:', error)
  }
}

async function fetchData() {
  try {
    const token = localStorage.getItem('token')
    const response = await axios.get('/api/whitelist/items', {
      headers: { Authorization: `Bearer ${token}` }
    })
    tableData.value = response.data.items.map(item => ({
      ...item,
      isEditing: false,
      editWord: '',
      editCategory: '',
      editDescription: ''
    }))
  } catch (error) {
    console.error('获取数据失败:', error)
    ElMessage.error('获取数据失败')
  }
}

function handleCategoryChange() {
  tableKey.value++
}

function handleSearch() {
  tableKey.value++
}

function handleSelectionChange(selection) {
  selectedRows.value = selection
}

function handleAdd() {
  addForm.word = ''
  addForm.category = ''
  addForm.description = ''
  addDialogVisible.value = true
}

async function submitAdd() {
  if (!addForm.word || !addForm.category) {
    ElMessage.warning('请填写词条和分类')
    return
  }
  
  addLoading.value = true
  try {
    const token = localStorage.getItem('token')
    await axios.post('/api/whitelist/items', addForm, {
      headers: { Authorization: `Bearer ${token}` }
    })
    ElMessage.success('添加成功')
    addDialogVisible.value = false
    await fetchData()
    await fetchCategories()
  } catch (error) {
    console.error('添加失败:', error)
    ElMessage.error('添加失败')
  } finally {
    addLoading.value = false
  }
}

function handleEdit(row) {
  row.isEditing = true
  row.editWord = row.word
  row.editCategory = row.category
  row.editDescription = row.description
}

async function handleSave(row) {
  if (!row.editWord || !row.editCategory) {
    ElMessage.warning('请填写词条和分类')
    return
  }
  
  try {
    const token = localStorage.getItem('token')
    await axios.put(`/api/whitelist/items/${row.id}`, {
      word: row.editWord,
      category: row.editCategory,
      description: row.editDescription
    }, {
      headers: { Authorization: `Bearer ${token}` }
    })
    ElMessage.success('更新成功')
    row.isEditing = false
    await fetchData()
    await fetchCategories()
  } catch (error) {
    console.error('更新失败:', error)
    ElMessage.error('更新失败')
  }
}

function handleCancelEdit(row) {
  row.isEditing = false
  row.editWord = ''
  row.editCategory = ''
  row.editDescription = ''
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除词条 "${row.word}" 吗？`,
      '删除确认',
      { type: 'warning' }
    )
    
    const token = localStorage.getItem('token')
    await axios.delete(`/api/whitelist/items/${row.id}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    ElMessage.success('删除成功')
    await fetchData()
    await fetchCategories()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

async function handleBatchDelete() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要删除的条目')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedRows.value.length} 条词条吗？`,
      '批量删除确认',
      { type: 'warning' }
    )
    
    const token = localStorage.getItem('token')
    const ids = selectedRows.value.map(row => row.id)
    await axios.post('/api/whitelist/items/batch-delete', ids, {
      headers: { Authorization: `Bearer ${token}` }
    })
    ElMessage.success('批量删除成功')
    selectedRows.value = []
    await fetchData()
    await fetchCategories()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量删除失败:', error)
      ElMessage.error('批量删除失败')
    }
  }
}

function handleImport() {
  importFileContent.value = ''
  importDialogVisible.value = true
}

function handleFileChange(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    importFileContent.value = e.target.result
  }
  reader.readAsText(file.raw)
}

async function submitImport() {
  if (!importFileContent.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  
  importLoading.value = true
  try {
    const lines = importFileContent.value.split('\n').filter(line => line.trim())
    const items = []
    
    for (const line of lines) {
      const parts = line.split(',').map(p => p.trim())
      if (parts.length >= 2) {
        items.push({
          word: parts[0],
          category: parts[1],
          description: parts[2] || ''
        })
      }
    }
    
    if (items.length === 0) {
      ElMessage.warning('文件格式不正确，请检查文件内容')
      return
    }
    
    const token = localStorage.getItem('token')
    const response = await axios.post('/api/whitelist/import', items, {
      headers: { Authorization: `Bearer ${token}` }
    })
    
    ElMessage.success(`导入成功：新增 ${response.data.added_count} 条，跳过 ${response.data.skipped} 条（已存在）`)
    importDialogVisible.value = false
    await fetchData()
    await fetchCategories()
  } catch (error) {
    console.error('导入失败:', error)
    ElMessage.error('导入失败')
  } finally {
    importLoading.value = false
  }
}

function handleExport() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要导出的条目')
    return
  }
  
  let content = '词条,分类,描述\n'
  selectedRows.value.forEach(item => {
    const description = item.description ? item.description.replace(/,/g, ';') : ''
    content += `${item.word},${item.category},${description}\n`
  })
  
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `白名单导出_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
  
  ElMessage.success('导出成功')
}

onMounted(() => {
  fetchData()
  fetchCategories()
})
</script>

<style scoped>
.whitelist-container {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 16px 0;
}

.total-text {
  color: #909399;
  font-size: 14px;
}

.word-text {
  font-weight: 500;
  color: #409eff;
}

.description-text {
  color: #606266;
  font-size: 13px;
}

.badge {
  margin-left: 4px;
}

.import-tips {
  margin-bottom: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

.import-tips p {
  margin: 0 0 8px 0;
  color: #606266;
}

.tips-detail {
  font-size: 13px;
  color: #909399;
}

.tips-detail code {
  background: #e9e9eb;
  padding: 2px 4px;
  border-radius: 2px;
  font-family: monospace;
}

.import-upload {
  text-align: center;
}

.upload-icon {
  font-size: 48px;
  color: #909399;
  margin-bottom: 8px;
}

.upload-text {
  color: #606266;
}

.upload-text em {
  color: #409eff;
  font-style: normal;
}

:deep(.el-table) {
  border-radius: 8px;
  overflow: hidden;
}

:deep(.el-table th) {
  background-color: #f5f7fa !important;
  font-weight: 600;
  color: #606266;
}

:deep(.el-tabs__item) {
  font-size: 14px;
}
</style>
