<template>
  <el-drawer
    v-model="drawerVisible"
    title="管理问答卡片"
    size="640px"
    @open="loadCards"
  >
    <div class="manager-body">
      <div class="manager-toolbar">
        <span class="manager-hint">卡片顺序与首页显示状态会自动保存</span>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建卡片
        </el-button>
      </div>

      <div v-if="loading" class="manager-empty">正在加载卡片...</div>
      <div v-else-if="!cards.length" class="manager-empty">暂无问答卡片</div>
      <div v-else class="card-list">
        <div v-for="(card, index) in cards" :key="card.id" class="card-row">
          <span class="card-mark" :style="{ background: card.accent }"></span>
          <div class="card-main">
            <div class="card-title-line">
              <span class="card-title">{{ card.title }}</span>
              <el-tag v-if="!card.home_visible" size="small" type="info">已隐藏</el-tag>
            </div>
            <div class="card-meta">{{ card.kicker }} · {{ card.folder_ids.length }} 个目录</div>
          </div>
          <div class="card-actions">
            <el-button size="small" text :disabled="index === 0 || savingOrder" @click="move(index, -1)">上移</el-button>
            <el-button size="small" text :disabled="index === cards.length - 1 || savingOrder" @click="move(index, 1)">下移</el-button>
            <el-switch :model-value="card.home_visible" size="small" @change="toggleVisible(card, $event)" />
            <el-button size="small" text @click="openEdit(card)">编辑</el-button>
            <el-button size="small" text type="danger" @click="removeCard(card)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="formVisible"
      :title="editingId ? '编辑卡片' : '新建卡片'"
      width="620px"
      append-to-body
      destroy-on-close
    >
      <el-form label-position="top" class="card-form">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" maxlength="30" show-word-limit placeholder="例如：查规范与自检" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="分类标签">
            <el-input v-model="form.kicker" maxlength="12" placeholder="例如：写作规范" />
          </el-form-item>
          <el-form-item label="主题色">
            <el-color-picker v-model="form.accent" :predefine="PRESET_COLORS" />
          </el-form-item>
        </div>
        <el-form-item label="说明">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            maxlength="120"
            show-word-limit
            placeholder="一句话说明这张卡片能查什么"
          />
        </el-form-item>
        <el-form-item label="推荐问题">
          <el-input
            v-model="form.suggestionsText"
            type="textarea"
            :rows="4"
            placeholder="每行一条，最多 6 条"
          />
        </el-form-item>
        <el-form-item label="首页显示">
          <el-switch v-model="form.homeVisible" />
          <span class="form-hint">关闭后仍会出现在统计面板的资料清单中</span>
        </el-form-item>
        <el-form-item label="知识库文件夹" required>
          <div class="folder-picker">
            <div class="folder-picker-head">
              <span>勾选父目录会自动包含子目录</span>
              <el-button v-if="checkedFolderIds.length" size="small" text @click="clearFolderSelection">清空</el-button>
            </div>
            <el-tree
              ref="folderTreeRef"
              :key="treeRenderKey"
              :data="folderTreeData"
              node-key="id"
              show-checkbox
              default-expand-all
              :props="{ label: 'name', children: 'children' }"
              class="folder-tree"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCard">保存</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import { computed, nextTick, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { qaAPI } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  treeData: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'changed'])

const PRESET_COLORS = ['#1d4ed8', '#0f766e', '#be123c', '#334155', '#b45309', '#6d28d9', '#047857']
const DEFAULT_ACCENT = '#1d4ed8'
const AGENT_KB_NAME = 'AI agent知识库'

const drawerVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const cards = ref([])
const loading = ref(false)
const saving = ref(false)
const savingOrder = ref(false)
const formVisible = ref(false)
const editingId = ref(null)
const folderTreeRef = ref(null)
const treeRenderKey = ref(0)
const checkedFolderIds = ref([])

const form = reactive({
  title: '',
  kicker: '',
  description: '',
  accent: DEFAULT_ACCENT,
  suggestionsText: '',
  homeVisible: true,
})

function filterAgentNodes(nodes) {
  const result = []
  for (const node of nodes || []) {
    if (node.name === AGENT_KB_NAME) continue
    result.push({
      ...node,
      children: filterAgentNodes(node.children || []),
    })
  }
  return result
}

const folderTreeData = computed(() => filterAgentNodes(props.treeData))

const folderParentMap = computed(() => {
  const map = {}
  const walk = (nodes, parentId = null) => {
    for (const node of nodes || []) {
      map[node.id] = parentId
      walk(node.children || [], node.id)
    }
  }
  walk(folderTreeData.value)
  return map
})

function pruneCheckedFolderIds(ids) {
  const selected = new Set(ids)
  return ids.filter((id) => {
    let parentId = folderParentMap.value[id]
    while (parentId !== null && parentId !== undefined) {
      if (selected.has(parentId)) return false
      parentId = folderParentMap.value[parentId]
    }
    return true
  })
}

async function loadCards() {
  loading.value = true
  try {
    const response = await qaAPI.getCards({ include_hidden: true })
    cards.value = response.data?.cards || []
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '卡片加载失败')
    cards.value = []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  form.title = ''
  form.kicker = ''
  form.description = ''
  form.accent = DEFAULT_ACCENT
  form.suggestionsText = ''
  form.homeVisible = true
  checkedFolderIds.value = []
}

function openCreate() {
  resetForm()
  formVisible.value = true
  treeRenderKey.value += 1
  nextTick(() => folderTreeRef.value?.setCheckedKeys([], false))
}

function openEdit(card) {
  resetForm()
  editingId.value = card.id
  form.title = card.title || ''
  form.kicker = card.kicker || ''
  form.description = card.description || ''
  form.accent = card.accent || DEFAULT_ACCENT
  form.suggestionsText = (card.suggestions || []).join('\n')
  form.homeVisible = card.home_visible !== false
  checkedFolderIds.value = [...(card.folder_ids || [])]
  formVisible.value = true
  treeRenderKey.value += 1
  nextTick(() => {
    folderTreeRef.value?.setCheckedKeys(checkedFolderIds.value, false)
  })
}

function clearFolderSelection() {
  checkedFolderIds.value = []
  folderTreeRef.value?.setCheckedKeys([], false)
}

function parseSuggestions() {
  const result = []
  const seen = new Set()
  for (const line of String(form.suggestionsText || '').split('\n')) {
    const text = line.trim()
    if (!text || seen.has(text)) continue
    seen.add(text)
    result.push(text)
  }
  return result
}

async function saveCard() {
  const title = form.title.trim()
  if (!title) {
    ElMessage.warning('请填写卡片标题')
    return
  }
  const checked = folderTreeRef.value?.getCheckedKeys() || []
  const folderIds = pruneCheckedFolderIds(checked)
  if (!folderIds.length) {
    ElMessage.warning('请至少选择一个知识库文件夹')
    return
  }
  const suggestions = parseSuggestions()
  if (suggestions.length > 6) {
    ElMessage.warning('推荐问题最多 6 条')
    return
  }
  if (suggestions.some((item) => item.length > 120)) {
    ElMessage.warning('单条推荐问题不能超过 120 个字符')
    return
  }

  const payload = {
    title,
    kicker: form.kicker.trim(),
    description: form.description.trim(),
    accent: form.accent || DEFAULT_ACCENT,
    suggestions,
    folder_ids: folderIds,
    home_visible: form.homeVisible,
  }

  saving.value = true
  try {
    if (editingId.value) {
      await qaAPI.updateCard(editingId.value, payload)
    } else {
      await qaAPI.createCard(payload)
    }
    formVisible.value = false
    ElMessage.success('卡片已保存')
    await loadCards()
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function cardPayload(card) {
  return {
    title: card.title,
    kicker: card.kicker,
    description: card.description,
    accent: card.accent,
    suggestions: card.suggestions || [],
    folder_ids: card.folder_ids || [],
    home_visible: card.home_visible,
  }
}

async function toggleVisible(card, value) {
  const previous = card.home_visible
  card.home_visible = value
  try {
    await qaAPI.updateCard(card.id, cardPayload(card))
    ElMessage.success(value ? '卡片已显示在首页' : '卡片已从首页隐藏')
    emit('changed')
  } catch (error) {
    card.home_visible = previous
    ElMessage.error(error?.response?.data?.detail || '更新失败')
  }
}

async function move(index, offset) {
  const target = index + offset
  if (target < 0 || target >= cards.value.length || savingOrder.value) return
  const next = [...cards.value]
  const [item] = next.splice(index, 1)
  next.splice(target, 0, item)
  cards.value = next
  savingOrder.value = true
  try {
    await qaAPI.reorderCards(next.map((card) => card.id))
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '排序保存失败')
    await loadCards()
  } finally {
    savingOrder.value = false
  }
}

async function removeCard(card) {
  try {
    await ElMessageBox.confirm(`确定删除「${card.title}」吗？`, '删除卡片', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await qaAPI.deleteCard(card.id)
    ElMessage.success('卡片已删除')
    await loadCards()
    emit('changed')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.manager-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.manager-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.manager-hint {
  color: #94a3b8;
  font-size: 12px;
}

.manager-empty {
  padding: 48px 0;
  text-align: center;
  color: #94a3b8;
}

.card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.card-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid #e7e5e4;
  border-radius: 12px;
  background: #fffdf9;
}

.card-mark {
  width: 6px;
  height: 36px;
  border-radius: 6px;
  flex: 0 0 auto;
}

.card-main {
  min-width: 0;
  flex: 1;
}

.card-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title {
  color: #1c1917;
  font-weight: 600;
}

.card-meta {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 12px;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 120px;
  gap: 12px;
}

.form-hint {
  margin-left: 10px;
  color: #94a3b8;
  font-size: 12px;
}

.folder-picker {
  width: 100%;
  border: 1px solid #e7e5e4;
  border-radius: 10px;
  padding: 8px 10px;
  background: #fff;
}

.folder-picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #94a3b8;
  font-size: 12px;
  margin-bottom: 6px;
}

.folder-tree {
  max-height: 280px;
  overflow: auto;
}
</style>
