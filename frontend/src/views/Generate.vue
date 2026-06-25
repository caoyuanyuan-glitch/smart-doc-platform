<template>
  <div class="gen-container">
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ viewMeta.title }}</h2>
        <p class="page-desc">{{ viewMeta.desc }}</p>
      </div>
    </div>

    <div v-if="currentView === 'image'">
      <div class="panel">
        <div class="panel-header">
          <span>上传图片并配置描述方式</span>
          <el-tag type="info" size="small">支持多张图片合并生成</el-tag>
        </div>

        <el-form label-width="110px" class="form-layout image-form-layout">
          <el-form-item label="图片文件">
            <el-upload
              ref="imageUploadRef"
              class="image-upload"
              action="#"
              multiple
              :auto-upload="false"
              :show-file-list="true"
              list-type="picture-card"
              accept="image/*"
              :on-change="handleImageChange"
              :on-remove="handleImageRemove"
            >
              <div class="upload-trigger">
                <div class="upload-trigger-plus">+</div>
                <div class="upload-trigger-text">选择图片</div>
              </div>
            </el-upload>
          </el-form-item>
          <el-form-item label="模板文件">
            <input
              ref="templateFileInputRef"
              type="file"
              accept=".txt,.md,.docx,.pdf"
              class="hidden-file-input"
              @change="handleTemplateChange"
            >
            <el-input
              :model-value="templateFileName"
              readonly
              class="readonly-guide-input template-file-input"
              placeholder="点击选择模板文件"
              @click="openTemplateFilePicker"
            />
          </el-form-item>
          <el-form-item label="风格指南">
            <el-input :model-value="currentStyleGuideName" readonly class="readonly-guide-input" />
          </el-form-item>
          <el-form-item label="补充要求">
            <el-input
              v-model="imageForm.prompt"
              type="textarea"
              :rows="4"
              placeholder="例如：按界面操作顺序输出，明确点击对象、输入内容和页面跳转结果"
            />
          </el-form-item>
          <el-form-item>
              <el-button type="primary" :loading="imageLoading" :disabled="imageFiles.length === 0" @click="generateImageDescription">提交</el-button>
              <el-button @click="resetImageForm">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div v-if="imageResult" class="panel">
        <div class="panel-header">
          <span>生成结果</span>
          <div class="panel-actions">
            <el-tag size="small" type="info">模型：{{ imageResult.model || 'kimi' }}</el-tag>
            <el-button size="small" @click="copyText(buildImageResultText(imageResult))">复制</el-button>
            <el-button size="small" type="primary" @click="downloadText('图片操作步骤.txt', buildImageResultText(imageResult))">下载</el-button>
          </div>
        </div>

        <el-alert
          v-if="imageResult.warning"
          :title="imageResult.warning"
          type="warning"
          show-icon
          :closable="false"
          class="result-warning"
        />

        <div class="result-stack">
          <div class="result-block">
            <ol class="step-list">
              <li v-for="step in imageResult.steps" :key="step">{{ step }}</li>
            </ol>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="currentView === 'manual'">
      <div class="panel">
        <div class="panel-header">
          <span>参考说明书生成初稿</span>
          <el-tag type="success" size="small">支持 Word / DITA / InDesign 导出需求标记</el-tag>
        </div>

        <el-form :model="manualForm" label-width="120px" class="form-layout">
          <el-form-item label="产品名称">
            <el-input v-model="manualForm.productName" placeholder="例如：智能检测终端 T-500" />
          </el-form-item>
          <el-form-item label="说明书类型">
            <el-select v-model="manualForm.manualType" style="width: 100%">
              <el-option label="用户说明书" value="用户说明书" />
              <el-option label="安装手册" value="安装手册" />
              <el-option label="操作维护手册" value="操作维护手册" />
            </el-select>
          </el-form-item>
          <el-form-item label="参考文件">
            <el-upload
              action="#"
              multiple
              :auto-upload="false"
              :show-file-list="true"
              accept=".doc,.docx,.pdf,.dita,.xml,.indd"
              :on-change="handleReferenceChange"
              :on-remove="handleReferenceRemove"
            >
              <el-button plain>上传参考说明书</el-button>
            </el-upload>
          </el-form-item>
          <el-form-item label="简单描述">
            <el-input
              v-model="manualForm.brief"
              type="textarea"
              :rows="5"
              placeholder="例如：面向医院检验科，重点覆盖开机、样本检测、故障处理与维护章节"
            />
          </el-form-item>
          <el-form-item label="输出格式">
            <el-checkbox-group v-model="manualForm.formats">
              <el-checkbox label="Word" />
              <el-checkbox label="DITA" />
              <el-checkbox label="INDD" />
            </el-checkbox-group>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="manualLoading" @click="generateManualDraft">生成初稿</el-button>
            <el-button @click="resetManualForm">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div v-if="manualResult" class="panel">
        <div class="panel-header">
          <span>说明书初稿</span>
          <div class="panel-actions">
            <el-tag size="small" type="info">{{ manualResult.formats.join(' / ') }}</el-tag>
            <el-button size="small" @click="copyText(manualResult.content)">复制</el-button>
            <el-button size="small" type="primary" @click="downloadText(`${manualForm.productName || '说明书'}_初稿.txt`, manualResult.content)">下载</el-button>
          </div>
        </div>

        <div class="result-stack">
          <div class="result-block">
            <div class="result-label">章节规划</div>
            <el-steps :active="manualResult.sections.length" finish-status="success" align-center>
              <el-step v-for="section in manualResult.sections" :key="section" :title="section" />
            </el-steps>
          </div>
          <div class="result-block">
            <div class="result-label">初稿内容</div>
            <pre>{{ manualResult.content }}</pre>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="currentView === 'paragraph'">
      <div class="panel">
        <div class="panel-header">
          <span>段落文字生成</span>
          <el-tag type="warning" size="small">适合简介、卖点、使用说明等短内容</el-tag>
        </div>

        <el-form :model="paragraphForm" label-width="110px" class="form-layout">
          <el-form-item label="应用场景">
            <el-select v-model="paragraphForm.scene" style="width: 100%">
              <el-option label="产品简介" value="产品简介" />
              <el-option label="功能亮点" value="功能亮点" />
              <el-option label="操作步骤" value="操作步骤" />
              <el-option label="维护保养" value="维护保养" />
            </el-select>
          </el-form-item>
          <el-form-item label="文字风格">
            <el-radio-group v-model="paragraphForm.tone">
              <el-radio-button label="专业" value="专业" />
              <el-radio-button label="简洁" value="简洁" />
              <el-radio-button label="说明式" value="说明式" />
            </el-radio-group>
          </el-form-item>
          <el-form-item label="关键词">
            <el-select v-model="paragraphForm.keywords" multiple filterable allow-create default-first-option style="width: 100%" placeholder="输入多个关键词后回车">
              <el-option v-for="item in paragraphForm.keywords" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="简单描述">
            <el-input
              v-model="paragraphForm.prompt"
              type="textarea"
              :rows="5"
              placeholder="例如：突出检测速度快、操作步骤少、适合基层门诊使用"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="paragraphLoading" @click="generateParagraph">生成段落</el-button>
            <el-button @click="resetParagraphForm">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div v-if="paragraphResult" class="panel">
        <div class="panel-header">
          <span>生成段落</span>
          <div class="panel-actions">
            <el-button size="small" @click="copyText(paragraphResult)">复制</el-button>
            <el-button size="small" type="primary" @click="downloadText('段落生成结果.txt', paragraphResult)">下载</el-button>
          </div>
        </div>
        <div class="result-block">
          <pre>{{ paragraphResult }}</pre>
        </div>
      </div>
    </div>

    <div v-else-if="currentView === 'templates'">
      <div class="panel">
        <div class="panel-header">
          <span>模板管理</span>
        </div>
        <el-table :data="templates" border>
          <el-table-column prop="name" label="模板名称" />
          <el-table-column prop="type" label="类型" width="140" />
          <el-table-column prop="lang" label="语言" width="100" />
          <el-table-column prop="fields" label="字段数" width="100" />
          <el-table-column prop="updated_at" label="更新时间" width="180" />
          <el-table-column label="适配能力" min-width="220">
            <template #default="scope">
              <el-tag v-for="tag in scope.row.scenes" :key="tag" size="small" class="scene-tag">{{ tag }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { generateAPI, knowledgeAPI } from '@/api'

const route = useRoute()

const AUTO_GUIDE_TEXT = '当前为自动匹配模式，系统会按图片中的主要语言选择合适的风格指南'

const viewConfig = {
  image: {
    title: '图片描述生成',
    desc: '根据多张图片生成描述文字，适合产品图、界面截图和结构示意图。'
  },
  manual: {
    title: '说明书初稿生成',
    desc: '参考现有说明书并结合简单描述，生成一本说明书初稿。'
  },
  paragraph: {
    title: '段落文字生成',
    desc: '输入简单描述后快速生成段落内容，适合简介、亮点和说明段落。'
  },
  templates: {
    title: '模板管理',
    desc: '统一管理当前可复用的内容生成模板。'
  }
}

const currentView = computed(() => {
  if (route.path === '/generate/image-descriptions') return 'image'
  if (route.path === '/generate/manual-draft') return 'manual'
  if (route.path === '/generate/paragraph') return 'paragraph'
  if (route.path === '/generate/templates') return 'templates'
  return 'image'
})

const viewMeta = computed(() => viewConfig[currentView.value])

const imageUploadRef = ref(null)
const templateFileInputRef = ref(null)
const imageFiles = ref([])
const templateFile = ref(null)
const imageLoading = ref(false)
const styleGuideLoading = ref(false)
const styleGuideOptions = ref([])
const resolvedStyleGuideName = ref(AUTO_GUIDE_TEXT)
const imageForm = ref({
  styleGuideId: 'auto',
  prompt: ''
})
const imageResult = ref(null)

const currentStyleGuideName = computed(() => {
  return resolvedStyleGuideName.value
})

const templateFileName = computed(() => templateFile.value?.name || '')

const manualLoading = ref(false)
const referenceFiles = ref([])
const manualForm = ref({
  productName: '',
  manualType: '用户说明书',
  brief: '',
  formats: ['Word', 'DITA']
})
const manualResult = ref(null)

const paragraphLoading = ref(false)
const paragraphForm = ref({
  scene: '产品简介',
  tone: '专业',
  keywords: [],
  prompt: ''
})
const paragraphResult = ref('')

const templates = ref([
  { name: '标准产品说明书模板', type: 'manual', lang: '中文', fields: 15, updated_at: '2025-01-10 10:30', scenes: ['说明书初稿', '段落生成'] },
  { name: '图文描述模板', type: 'image', lang: '中文', fields: 8, updated_at: '2025-01-09 14:20', scenes: ['图片描述生成'] },
  { name: '技术规格文档模板', type: 'spec', lang: '中英文', fields: 22, updated_at: '2025-01-08 09:15', scenes: ['说明书初稿', '段落生成'] }
])

function handleImageChange(file, fileList) {
  imageFiles.value = fileList.map((item) => item.raw || item)
}

function handleImageRemove(file, fileList) {
  imageFiles.value = fileList.map((item) => item.raw || item)
}

function openTemplateFilePicker() {
  templateFileInputRef.value?.click?.()
}

function handleTemplateChange(event) {
  const nextFile = event?.target?.files?.[0] || null
  templateFile.value = nextFile
}

async function generateImageDescription() {
  if (imageFiles.value.length === 0) {
    ElMessage.info('请先上传图片')
    return
  }
  imageLoading.value = true
  try {
    const formData = new FormData()
    imageFiles.value.forEach((file) => formData.append('files', file))
    if (templateFile.value) {
      formData.append('template_file', templateFile.value)
    }
    formData.append('prompt', imageForm.value.prompt)
    if (imageForm.value.styleGuideId !== 'auto') {
      formData.append('style_guide_id', String(imageForm.value.styleGuideId))
    }
    const resp = await generateAPI.generateImageSteps(formData)
    const data = resp.data || {}
    if (!(data.steps || []).length) {
      throw new Error(data.detail || 'empty image steps result')
    }
    imageResult.value = {
      summary: data.summary || '',
      relation_summary: data.relation_summary || '',
      steps: data.steps || [],
      model: data.model || 'kimi',
      warning: data.warning || ''
    }
    resolvedStyleGuideName.value = data.used_style_guide_name || AUTO_GUIDE_TEXT
    clearUploadedImages()
    ElMessage[data.warning ? 'warning' : 'success'](data.warning ? '当前为兜底结果' : '操作步骤已生成')
  } catch (error) {
    imageResult.value = buildImageFallback()
    ElMessage.warning(error?.response?.data?.detail || error?.message || '生成失败，已展示示例结果')
  } finally {
    imageLoading.value = false
  }
}

function resetImageForm() {
  clearUploadedImages()
  clearTemplateFile()
  imageForm.value = { styleGuideId: 'auto', prompt: '' }
  resolvedStyleGuideName.value = AUTO_GUIDE_TEXT
  imageResult.value = null
}

function clearUploadedImages() {
  imageFiles.value = []
  imageUploadRef.value?.clearFiles?.()
}

function clearTemplateFile() {
  templateFile.value = null
  if (templateFileInputRef.value) {
    templateFileInputRef.value.value = ''
  }
}

function buildImageFallback() {
  const steps = imageFiles.value.map((file, index) => `步骤 ${index + 1}：参照 ${file.name} 中展示的状态完成当前操作，并确认进入下一步前所需条件已经满足。`)
  return {
    summary: `已基于 ${imageFiles.value.length} 张图片整理操作说明。${imageForm.value.prompt ? `补充要求：${imageForm.value.prompt}` : ''}`,
    relation_summary: '当前结果按上传顺序组织，并将每张图片视为连续流程中的一个关键节点。',
    steps,
    model: 'fallback',
    warning: '当前环境未接通 Kimi 多模态模型，结果来自本地兜底逻辑，不能作为正式操作说明。'
  }
}

function buildImageResultText(result) {
  return (result.steps || []).map((step, index) => `${index + 1}. ${step}`).join('\n')
}

function inferGuideLanguageLabel(name) {
  const text = String(name || '').toLowerCase()
  if (text.includes('英文') || text.includes('english')) return '（英文）'
  if (text.includes('中文') || text.includes('chinese')) return '（中文）'
  return ''
}

function collectFilesRecursively(node, currentPath) {
  const files = (node.files || []).map((file) => ({
    id: file.id,
    label: `${[...currentPath, file.name].join(' / ')}${inferGuideLanguageLabel(file.name)}`
  }))
  const children = (node.children || []).flatMap((child) => collectFilesRecursively(child, [...currentPath, child.name]))
  return [...files, ...children]
}

function collectStyleGuides(nodes, targetPath, currentPath = []) {
  const guides = []
  for (const node of nodes || []) {
    const nextPath = [...currentPath, node.name]
    const isTarget = nextPath.length >= targetPath.length
      && targetPath.every((name, index) => nextPath[nextPath.length - targetPath.length + index] === name)
    if (isTarget) {
      guides.push(...collectFilesRecursively(node, nextPath))
      continue
    }
    guides.push(...collectStyleGuides(node.children || [], targetPath, nextPath))
  }
  return guides
}

async function loadStyleGuides() {
  styleGuideLoading.value = true
  try {
    const resp = await knowledgeAPI.getTree()
    styleGuideOptions.value = collectStyleGuides(resp.data || [], ['写作规范', '写作风格指南'])
      .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
  } catch (error) {
    styleGuideOptions.value = []
    ElMessage.warning('写作风格指南加载失败，当前保留自动匹配模式')
  } finally {
    styleGuideLoading.value = false
  }
}

watch(currentView, (view) => {
  if (view === 'image' && !styleGuideLoading.value && !styleGuideOptions.value.length) {
    loadStyleGuides()
  }
}, { immediate: true })

function handleReferenceChange(file, fileList) {
  referenceFiles.value = fileList.map((item) => item.raw || item)
}

function handleReferenceRemove(file, fileList) {
  referenceFiles.value = fileList.map((item) => item.raw || item)
}

async function generateManualDraft() {
  if (!manualForm.value.productName || !manualForm.value.brief) {
    ElMessage.info('请填写产品名称和简单描述')
    return
  }
  manualLoading.value = true
  try {
    const resp = await generateAPI.create(
      manualForm.value.productName,
      referenceFiles.value.length ? `${referenceFiles.value.length}份参考文件` : '参考说明书',
      manualForm.value.manualType,
      '产品概述,安装准备,操作流程,维护保养,故障处理'
    )
    const data = resp.data || {}
    manualResult.value = {
      formats: manualForm.value.formats.length ? [...manualForm.value.formats] : ['Word'],
      sections: ['产品概述', '安全信息', '安装准备', '操作流程', '维护保养', '故障处理'],
      content: data.content || buildManualFallback()
    }
    ElMessage.success('说明书初稿已生成')
  } catch (error) {
    manualResult.value = {
      formats: manualForm.value.formats.length ? [...manualForm.value.formats] : ['Word'],
      sections: ['产品概述', '安全信息', '安装准备', '操作流程', '维护保养', '故障处理'],
      content: buildManualFallback()
    }
    ElMessage.info('接口调用失败，已展示示例初稿')
  } finally {
    manualLoading.value = false
  }
}

function buildManualFallback() {
  const referenceText = referenceFiles.value.length
    ? `已参考 ${referenceFiles.value.map((item) => item.name).join('、')} 的章节组织方式。`
    : '当前初稿基于简单描述生成，可在后续接入参考说明书解析能力。'

  return `${manualForm.value.productName}${manualForm.value.manualType}初稿

一、文档定位
本说明书面向目标用户提供完整的产品介绍、安装操作和维护指引。${referenceText}

二、产品概述
${manualForm.value.productName}适用于典型业务场景，文档编写重点如下：${manualForm.value.brief}

三、建议章节结构
1. 产品概述
2. 安全信息
3. 安装准备
4. 操作流程
5. 日常维护
6. 故障处理

四、输出格式建议
当前选择输出格式：${(manualForm.value.formats.length ? manualForm.value.formats : ['Word']).join('、')}。
Word 适合编辑评审，DITA 适合结构化发布，INDD 适合排版输出。

五、初稿正文示例
开机前请确认设备外观完整，附件齐全，电源与环境条件符合要求。完成初始化后，按操作界面提示逐步执行检测或配置流程。使用结束后，按维护章节要求完成清洁、关机与记录归档。`
}

function resetManualForm() {
  referenceFiles.value = []
  manualForm.value = {
    productName: '',
    manualType: '用户说明书',
    brief: '',
    formats: ['Word', 'DITA']
  }
  manualResult.value = null
}

async function generateParagraph() {
  if (!paragraphForm.value.prompt) {
    ElMessage.info('请填写简单描述')
    return
  }
  paragraphLoading.value = true
  try {
    const resp = await generateAPI.create(
      paragraphForm.value.scene,
      paragraphForm.value.tone,
      '段落生成',
      paragraphForm.value.prompt
    )
    const data = resp.data || {}
    paragraphResult.value = data.content || buildParagraphFallback()
    ElMessage.success('段落已生成')
  } catch (error) {
    paragraphResult.value = buildParagraphFallback()
    ElMessage.info('接口调用失败，已展示示例段落')
  } finally {
    paragraphLoading.value = false
  }
}

function buildParagraphFallback() {
  const keywords = paragraphForm.value.keywords.length ? `关键词包括${paragraphForm.value.keywords.join('、')}。` : ''
  return `${paragraphForm.value.scene}建议采用${paragraphForm.value.tone}风格表达，围绕“${paragraphForm.value.prompt}”展开组织。${keywords}生成内容可先概括核心价值，再补充使用方式、性能特点或注意事项，使整段文字更适合直接放入说明书、产品页或培训材料中。`
}

function resetParagraphForm() {
  paragraphForm.value = {
    scene: '产品简介',
    tone: '专业',
    keywords: [],
    prompt: ''
  }
  paragraphResult.value = ''
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制')).catch(() => ElMessage.info('复制失败，请手动复制'))
}

function downloadText(fileName, content) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('下载已开始')
}
</script>

<style>
.gen-container {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 6px;
}

.page-desc {
  margin: 0;
  color: #6b7280;
  line-height: 1.6;
}

.panel {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
  font-weight: 600;
  color: #1f2937;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.result-warning {
  margin-bottom: 16px;
}

.image-upload :deep(.el-upload-list--picture-card) {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
  width: 100%;
  padding-bottom: 0;
}

.image-upload :deep(.el-upload--picture-card),
.image-upload :deep(.el-upload-list__item) {
  width: 120px;
  min-width: 120px;
  height: 120px;
}

.hidden-file-input {
  display: none;
}

.template-file-input {
  width: 100%;
}

.template-file-input :deep(.el-input__wrapper) {
  cursor: pointer;
}

.upload-trigger {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #475569;
}

.upload-trigger-plus {
  font-size: 30px;
  line-height: 1;
  margin-bottom: 8px;
}

.upload-trigger-text {
  font-size: 13px;
}

.form-layout {
  max-width: 860px;
}

.image-form-layout {
  max-width: 100%;
}

.result-stack {
  display: grid;
  gap: 16px;
}

.result-block {
  background: #f8fafc;
  padding: 18px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.result-label {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 12px;
}

.result-block pre {
  line-height: 1.8;
  color: #374151;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  margin: 0;
}

.readonly-guide-input :deep(.el-input__inner) {
  color: var(--el-text-color-placeholder) !important;
  -webkit-text-fill-color: var(--el-text-color-placeholder) !important;
}

.readonly-guide-input :deep(.el-input__wrapper) {
  color: var(--el-text-color-placeholder) !important;
}

.step-list li {
  line-height: 1.8;
}

.step-list {
  margin: 0;
  padding-left: 20px;
  color: #374151;
}

.scene-tag {
  margin-right: 6px;
}

@media (max-width: 960px) {
  .page-header {
    flex-direction: column;
  }
}
</style>
