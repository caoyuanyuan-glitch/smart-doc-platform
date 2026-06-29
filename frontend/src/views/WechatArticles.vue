<template>
  <div class="wechat-articles-container">
    <div class="page-header">
      <h2>公众号文章管理</h2>
      <el-button type="primary" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon>添加文章
      </el-button>
    </div>

    <div class="search-bar">
      <el-select v-model="searchCompetitorId" placeholder="筛选竞品" clearable style="width: 150px" @change="loadArticles">
        <el-option v-for="c in competitors" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select v-model="searchCategory" placeholder="筛选分类" clearable style="width: 120px; margin-left: 10px" @change="loadArticles">
        <el-option label="产品介绍" value="产品介绍" />
        <el-option label="技术分享" value="技术分享" />
        <el-option label="行业动态" value="行业动态" />
        <el-option label="活动推广" value="活动推广" />
        <el-option label="其他" value="其他" />
      </el-select>
      <el-input v-model="searchKeyword" placeholder="搜索标题或内容" clearable style="width: 200px; margin-left: 10px" @keyup.enter="loadArticles">
        <template #append><el-button @click="loadArticles">搜索</el-button></template>
      </el-input>
    </div>

    <el-table :data="articles" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="competitor_name" label="竞品" width="120">
        <template #default="{ row }">
          {{ getCompetitorName(row.competitor_id) }}
        </template>
      </el-table-column>
      <el-table-column prop="account_name" label="公众号" width="120" />
      <el-table-column prop="title" label="文章标题" min-width="200">
        <template #default="{ row }">
          <a :href="row.url" target="_blank" class="article-link">{{ row.title }}</a>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.category" size="small" :type="getCategoryType(row.category)">{{ row.category }}</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="tags" label="标签" width="150">
        <template #default="{ row }">
          <span v-if="row.tags">{{ row.tags }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="publish_date" label="发布时间" width="120">
        <template #default="{ row }">{{ formatDate(row.publish_date) }}</template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" width="150">
        <template #default="{ row }">
          <el-tag v-if="row.summary" size="small" type="success">已生成</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="viewArticle(row)">详情</el-button>
          <el-button type="success" link size="small" @click="generateSummary(row)" v-if="row.content && !row.summary">摘要</el-button>
          <el-button type="warning" link size="small" @click="editArticle(row)">编辑</el-button>
          <el-button type="danger" link size="small" @click="deleteArticle(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadArticles"
        @current-change="loadArticles"
      />
    </div>

    <!-- 添加文章对话框 -->
    <el-dialog v-model="showAddDialog" title="添加公众号文章" width="600px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="所属竞品" required>
          <el-select v-model="addForm.competitorId" placeholder="选择竞品" style="width: 100%" @change="loadWechatAccountsForAdd">
            <el-option v-for="c in competitors" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="公众号" required>
          <el-select v-model="addForm.wechatAccountId" placeholder="选择公众号" style="width: 100%">
            <el-option v-for="a in wechatAccountsForAdd" :key="a.id" :label="a.account_name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="文章标题" required>
          <el-input v-model="addForm.title" placeholder="请输入文章标题" />
        </el-form-item>
        <el-form-item label="文章链接" required>
          <el-input v-model="addForm.url" placeholder="请输入文章URL" />
        </el-form-item>
        <el-form-item label="作者">
          <el-input v-model="addForm.author" placeholder="作者名称" />
        </el-form-item>
        <el-form-item label="发布时间">
          <el-date-picker v-model="addForm.publishDate" type="datetime" placeholder="选择发布时间" style="width: 100%" />
        </el-form-item>
        <el-form-item label="文章内容">
          <el-input v-model="addForm.content" type="textarea" :rows="5" placeholder="粘贴文章内容（用于AI摘要生成）" />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="addForm.keywords" placeholder="多个关键词用逗号分隔" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="addForm.category" placeholder="选择分类" style="width: 100%">
            <el-option label="产品介绍" value="产品介绍" />
            <el-option label="技术分享" value="技术分享" />
            <el-option label="行业动态" value="行业动态" />
            <el-option label="活动推广" value="活动推广" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="createArticle" :loading="addLoading">添加</el-button>
      </template>
    </el-dialog>

    <!-- 文章详情对话框 -->
    <el-dialog v-model="showDetailDialog" title="文章详情" width="70%" top="5vh">
      <div v-if="currentArticle" class="article-detail">
        <div class="detail-header">
          <h3>{{ currentArticle.title }}</h3>
          <div class="meta">
            <span>竞品：{{ getCompetitorName(currentArticle.competitor_id) }}</span>
            <span>公众号：{{ currentArticle.account_name }}</span>
            <span>发布时间：{{ formatDate(currentArticle.publish_date) }}</span>
            <span v-if="currentArticle.author">作者：{{ currentArticle.author }}</span>
          </div>
          <div class="link">
            <a :href="currentArticle.url" target="_blank">查看原文 <el-icon><Link /></el-icon></a>
          </div>
        </div>

        <el-divider />

        <div v-if="currentArticle.summary" class="summary-box">
          <h4>AI摘要</h4>
          <p>{{ currentArticle.summary }}</p>
        </div>

        <div v-if="currentArticle.content" class="content-box">
          <h4>文章内容</h4>
          <div class="content-text">{{ currentArticle.content }}</div>
        </div>

        <div v-if="currentArticle.keywords" class="keywords-box">
          <h4>关键词</h4>
          <el-tag v-for="kw in currentArticle.keywords.split(',')" :key="kw" size="small" style="margin: 2px">{{ kw.trim() }}</el-tag>
        </div>

        <div v-if="currentArticle.tags" class="tags-box">
          <h4>标签</h4>
          <el-tag v-for="tag in currentArticle.tags.split(',')" :key="tag" type="warning" size="small" style="margin: 2px">{{ tag.trim() }}</el-tag>
        </div>

        <div v-if="currentArticle.notes" class="notes-box">
          <h4>备注</h4>
          <p>{{ currentArticle.notes }}</p>
        </div>
      </div>
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
        <el-button type="success" @click="generateSummary(currentArticle)" v-if="currentArticle && currentArticle.content && !currentArticle.summary">生成摘要</el-button>
        <el-button type="warning" @click="editArticle(currentArticle)">编辑</el-button>
      </template>
    </el-dialog>

    <!-- 编辑文章对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑文章" width="500px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="标签">
          <el-input v-model="editForm.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="editForm.category" placeholder="选择分类" style="width: 100%">
            <el-option label="产品介绍" value="产品介绍" />
            <el-option label="技术分享" value="技术分享" />
            <el-option label="行业动态" value="行业动态" />
            <el-option label="活动推广" value="活动推广" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.notes" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="updateArticle">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Link } from '@element-plus/icons-vue'
import { competitorAPI } from '@/api'

const loading = ref(false)
const addLoading = ref(false)

const articles = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

const competitors = ref([])
const searchCompetitorId = ref(null)
const searchCategory = ref(null)
const searchKeyword = ref('')

const wechatAccountsForAdd = ref([])
const showAddDialog = ref(false)
const showDetailDialog = ref(false)
const showEditDialog = ref(false)

const currentArticle = ref(null)

const addForm = reactive({
  competitorId: null,
  wechatAccountId: null,
  title: '',
  url: '',
  author: '',
  publishDate: null,
  content: '',
  keywords: '',
  category: ''
})

const editForm = reactive({
  tags: '',
  category: '',
  notes: ''
})

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

function getCategoryType(category) {
  const map = {
    '产品介绍': 'primary',
    '技术分享': 'success',
    '行业动态': 'warning',
    '活动推广': 'danger',
    '其他': 'info'
  }
  return map[category] || 'info'
}

function getCompetitorName(competitorId) {
  const c = competitors.value.find(x => x.id === competitorId)
  return c ? c.name : '-'
}

async function loadCompetitors() {
  try {
    const res = await competitorAPI.list({ page: 1, page_size: 100 })
    competitors.value = res.data.items || []
  } catch (e) {
    ElMessage.error('加载竞品列表失败')
  }
}

async function loadArticles() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value
    }
    if (searchCompetitorId.value) params.competitor_id = searchCompetitorId.value
    if (searchCategory.value) params.category = searchCategory.value
    if (searchKeyword.value) params.keyword = searchKeyword.value

    const res = await competitorAPI.getAllWechatArticles(params)
    articles.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    ElMessage.error('加载文章列表失败')
  } finally {
    loading.value = false
  }
}

async function loadWechatAccountsForAdd() {
  if (!addForm.competitorId) return
  try {
    const res = await competitorAPI.getWechatAccounts(addForm.competitorId)
    wechatAccountsForAdd.value = res.data.items || []
    if (wechatAccountsForAdd.value.length === 0) {
      ElMessage.warning('该竞品暂无公众号配置，请先添加公众号')
    }
  } catch (e) {
    ElMessage.error('加载公众号列表失败')
  }
}

async function createArticle() {
  if (!addForm.competitorId || !addForm.wechatAccountId || !addForm.title || !addForm.url) {
    ElMessage.warning('请填写必填项')
    return
  }
  addLoading.value = true
  try {
    await competitorAPI.createWechatArticle(addForm.competitorId, {
      wechat_account_id: addForm.wechatAccountId,
      title: addForm.title,
      url: addForm.url,
      author: addForm.author,
      publish_date: addForm.publishDate,
      content: addForm.content,
      keywords: addForm.keywords,
      category: addForm.category
    })
    ElMessage.success('添加成功')
    showAddDialog.value = false
    Object.assign(addForm, {
      competitorId: null,
      wechatAccountId: null,
      title: '',
      url: '',
      author: '',
      publishDate: null,
      content: '',
      keywords: '',
      category: ''
    })
    loadArticles()
  } catch (e) {
    ElMessage.error('添加失败')
  } finally {
    addLoading.value = false
  }
}

function viewArticle(row) {
  currentArticle.value = row
  showDetailDialog.value = true
}

function editArticle(row) {
  currentArticle.value = row
  editForm.tags = row.tags || ''
  editForm.category = row.category || ''
  editForm.notes = row.notes || ''
  showEditDialog.value = true
}

async function updateArticle() {
  try {
    await competitorAPI.updateWechatArticle(currentArticle.value.competitor_id, currentArticle.value.id, {
      tags: editForm.tags,
      category: editForm.category,
      notes: editForm.notes
    })
    ElMessage.success('更新成功')
    showEditDialog.value = false
    loadArticles()
  } catch (e) {
    ElMessage.error('更新失败')
  }
}

async function deleteArticle(row) {
  try {
    await ElMessageBox.confirm('确定要删除该文章吗？', '删除确认', { type: 'warning' })
    await competitorAPI.deleteWechatArticle(row.competitor_id, row.id)
    ElMessage.success('删除成功')
    loadArticles()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

async function generateSummary(row) {
  try {
    ElMessage.info('正在生成AI摘要...')
    const res = await competitorAPI.generateArticleSummary(row.competitor_id, row.id)
    ElMessage.success('摘要已生成')
    // 更新当前文章的摘要
    row.summary = res.data.summary
    if (currentArticle.value && currentArticle.value.id === row.id) {
      currentArticle.value.summary = res.data.summary
    }
  } catch (e) {
    ElMessage.error('生成摘要失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(() => {
  loadCompetitors()
  loadArticles()
})
</script>

<style scoped>
.wechat-articles-container {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
}

.search-bar {
  margin-bottom: 20px;
  display: flex;
  align-items: center;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.article-link {
  color: #409eff;
  text-decoration: none;
}

.article-link:hover {
  text-decoration: underline;
}

/* 文章详情 */
.article-detail .detail-header h3 {
  margin: 0 0 10px 0;
  font-size: 18px;
}

.article-detail .meta {
  color: #909399;
  font-size: 14px;
  margin-bottom: 10px;
}

.article-detail .meta span {
  margin-right: 20px;
}

.article-detail .link a {
  color: #409eff;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.summary-box, .content-box, .keywords-box, .tags-box, .notes-box {
  margin: 15px 0;
}

.summary-box h4, .content-box h4, .keywords-box h4, .tags-box h4, .notes-box h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #303133;
}

.summary-box p {
  background: #e8f4fd;
  padding: 15px;
  border-radius: 8px;
  color: #303133;
  line-height: 1.6;
}

.content-box .content-text {
  background: #f5f7fa;
  padding: 15px;
  border-radius: 8px;
  max-height: 400px;
  overflow-y: auto;
  line-height: 1.8;
}
</style>