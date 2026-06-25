<template>
  <div class="memory-container">
    <div class="page-header">
      <h2 class="page-title">记忆库</h2>
      <p class="page-desc">管理翻译记忆库，存储并检索历史翻译记录，提升翻译一致性和效率</p>
    </div>

    <div class="toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索原文、译文或标签..."
        clearable
        style="width: 320px"
        @input="onSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button type="primary" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon>
        添加记录
      </el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="entries" v-loading="loading" stripe empty-text="暂无记忆库记录">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="source_text" label="原文" min-width="200" show-overflow-tooltip />
        <el-table-column prop="translated_text" label="译文" min-width="200" show-overflow-tooltip />
        <el-table-column prop="source_lang" label="源语言" width="80" align="center" />
        <el-table-column prop="target_lang" label="目标语言" width="80" align="center" />
        <el-table-column prop="tags" label="标签" width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="80" align="center" fixed="right">
          <template #default="scope">
            <el-popconfirm title="确定要删除这条记忆库记录吗？" @confirm="handleDelete(scope.row.id)">
              <template #reference>
                <el-button type="danger" size="small" link>
                  <el-icon><Delete /></el-icon>
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadEntries"
          @current-change="loadEntries"
        />
      </div>
    </el-card>

    <el-dialog v-model="showAddDialog" title="添加记忆库记录" width="560px" destroy-on-close>
      <el-form :model="addForm" label-width="90px">
        <el-form-item label="原文">
          <el-input v-model="addForm.source_text" type="textarea" :rows="4" placeholder="请输入原文" />
        </el-form-item>
        <el-form-item label="译文">
          <el-input v-model="addForm.translated_text" type="textarea" :rows="4" placeholder="请输入译文" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="源语言">
              <el-select v-model="addForm.source_lang" style="width: 100%">
                <el-option label="中文" value="zh" />
                <el-option label="英文" value="en" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="目标语言">
              <el-select v-model="addForm.target_lang" style="width: 100%">
                <el-option label="英文" value="en" />
                <el-option label="中文" value="zh" />
                <el-option label="日文" value="ja" />
                <el-option label="韩文" value="ko" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="标签">
          <el-input v-model="addForm.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleAdd">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Plus, Delete } from '@element-plus/icons-vue'
import { translationAPI } from '@/api'

const loading = ref(false)
const entries = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const searchKeyword = ref('')
let searchTimer = null

const showAddDialog = ref(false)
const adding = ref(false)
const addForm = reactive({
  source_text: '',
  translated_text: '',
  source_lang: 'zh',
  target_lang: 'en',
  tags: ''
})

onMounted(() => {
  loadEntries()
})

async function loadEntries() {
  loading.value = true
  try {
    const skip = (page.value - 1) * pageSize.value
    const res = await translationAPI.getMemory(skip, pageSize.value, searchKeyword.value || undefined)
    entries.value = res.data || []
    total.value = entries.value.length
  } catch (e) {
    ElMessage.error('加载记忆库失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadEntries()
  }, 300)
}

async function handleAdd() {
  if (!addForm.source_text.trim() || !addForm.translated_text.trim()) {
    ElMessage.warning('请填写原文和译文')
    return
  }
  adding.value = true
  try {
    await translationAPI.addMemory({ ...addForm })
    ElMessage.success('添加成功')
    showAddDialog.value = false
    Object.assign(addForm, { source_text: '', translated_text: '', source_lang: 'zh', target_lang: 'en', tags: '' })
    loadEntries()
  } catch (e) {
    ElMessage.error('添加失败')
  } finally {
    adding.value = false
  }
}

async function handleDelete(id) {
  try {
    await translationAPI.deleteMemory(id)
    ElMessage.success('删除成功')
    loadEntries()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}
</script>

<style scoped>
.memory-container {
  padding: 0;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.page-desc {
  font-size: 14px;
  color: #6b7280;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
