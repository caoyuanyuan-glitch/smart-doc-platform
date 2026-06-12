<template>
  <div class="audit-basis-container">
    <div class="upload-section">
      <h3>审核依据管理</h3>
      <el-upload
        class="upload-demo"
        action="/api/audit_basis/upload"
        :headers="{ Authorization: `Bearer ${token}` }"
        :on-success="handleUploadSuccess"
        :on-error="handleUploadError"
        accept=".pdf,.docx,.md,.txt"
      >
        <el-button type="primary">上传审核依据</el-button>
      </el-upload>
    </div>

    <div class="list-section">
      <el-table :data="bases" border>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="file_type" label="类型" width="100" />
        <el-table-column prop="created_at" label="上传时间" width="180" />
        <el-table-column label="操作" width="150">
          <template #default="scope">
            <el-button size="small" @click="viewBasis(scope.row.id)">查看</el-button>
            <el-button size="small" type="danger" @click="deleteBasis(scope.row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog title="审核依据内容" :visible.sync="showContentModal" width="800px">
      <div class="content-preview">
        <pre>{{ basisContent }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { auditBasisAPI } from '@/api'
import { ElMessage } from 'element-plus'

const token = localStorage.getItem('token')
const bases = ref([])
const showContentModal = ref(false)
const basisContent = ref('')

onMounted(async () => {
  await loadBases()
})

async function loadBases() {
  try {
    const response = await auditBasisAPI.list()
    bases.value = response.data
  } catch (error) {
    ElMessage.error('加载审核依据失败')
  }
}

function handleUploadSuccess() {
  ElMessage.success('上传成功')
  loadBases()
}

function handleUploadError() {
  ElMessage.error('上传失败')
}

async function viewBasis(id) {
  try {
    const response = await auditBasisAPI.get(id)
    basisContent.value = response.data.content
    showContentModal.value = true
  } catch (error) {
    ElMessage.error('查看失败')
  }
}

async function deleteBasis(id) {
  try {
    await auditBasisAPI.delete(id)
    loadBases()
    ElMessage.success('删除成功')
  } catch (error) {
    ElMessage.error('删除失败')
  }
}
</script>

<style>
.audit-basis-container {
  padding: 20px;
}

.upload-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.upload-section h3 {
  margin-bottom: 15px;
  color: #333;
}

.list-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
}

.content-preview {
  max-height: 500px;
  overflow-y: auto;
  padding: 15px;
  background: #f5f7fa;
  border-radius: 8px;
}

.content-preview pre {
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  line-height: 1.6;
}
</style>
