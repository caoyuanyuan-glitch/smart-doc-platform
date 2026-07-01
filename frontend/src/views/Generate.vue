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
              :limit="MAX_IMAGE_STEP_FILES"
              :on-change="handleImageChange"
              :on-remove="handleImageRemove"
              :on-preview="handleImagePreview"
              :on-exceed="handleImageExceed"
            >
              <div class="upload-trigger">
                <div class="upload-trigger-plus">+</div>
                <div class="upload-trigger-text">选择图片</div>
              </div>
            </el-upload>
          </el-form-item>
          <el-form-item label="选择生成意图">
            <el-radio-group v-model="imageForm.generationIntent" class="intent-options">
              <el-radio-button label="product_appearance">产品外观描述</el-radio-button>
              <el-radio-button label="operation_steps">操作步骤说明</el-radio-button>
              <el-radio-button label="interface_manual">界面功能说明</el-radio-button>
              <el-radio-button label="custom">自定义</el-radio-button>
            </el-radio-group>
            <el-input
              v-if="imageForm.generationIntent === 'custom'"
              v-model="imageForm.customIntent"
              class="custom-intent-input"
              placeholder="请输入自定义生成意图"
            />
          </el-form-item>
          <el-form-item label="输出格式">
            <el-radio-group v-model="imageForm.outputFormat">
              <el-radio-button label="plain_text">纯文本</el-radio-button>
              <el-radio-button label="numbered_steps">带编号步骤</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="语言风格">
            <el-radio-group v-model="imageForm.languageStyle">
              <el-radio-button label="formal_technical">正式技术文档</el-radio-button>
              <el-radio-button label="concise">简要说明</el-radio-button>
            </el-radio-group>
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
            <div v-if="imageLoading" class="image-progress-wrap">
              <el-progress :percentage="imageProgress" :stroke-width="10" striped striped-flow />
              <span class="image-progress-text">正在生成操作步骤，请稍候</span>
            </div>
            <template v-else>
              <el-button type="primary" :loading="imageLoading" :disabled="imageFiles.length === 0" @click="generateImageDescription">提交</el-button>
              <el-button @click="resetImageForm">重置</el-button>
            </template>
          </el-form-item>
        </el-form>
      </div>

      <div v-if="imageResult" class="panel">
        <div class="panel-header">
          <span>生成结果</span>
          <div class="panel-actions">
            <el-tag size="small" type="info">模型：{{ imageResult.model || 'kimi' }}</el-tag>
            <el-button size="small" @click="toggleImageEdit">{{ imageEditing ? '完成编辑' : '编辑' }}</el-button>
            <el-button size="small" :loading="imageLoading" @click="regenerateImageDescription">重新生成</el-button>
            <el-button size="small" @click="copyText(currentImageResultText)">复制</el-button>
            <el-button size="small" type="primary" @click="saveImageResult">保存</el-button>
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
            <el-input
              v-if="imageEditing"
              v-model="imageEditText"
              type="textarea"
              :rows="10"
            />
            <pre v-else-if="imageForm.outputFormat === 'plain_text'">{{ currentImageResultText }}</pre>
            <ol v-else class="step-list">
              <li v-for="step in imageResult.steps" :key="step">{{ stripStepNumber(step) }}</li>
            </ol>
          </div>
        </div>
      </div>

      <el-dialog v-model="imagePreviewVisible" title="图片预览" width="min(900px, 92vw)">
        <img v-if="imagePreviewUrl" :src="imagePreviewUrl" class="image-preview-img" alt="图片预览">
      </el-dialog>
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
          <span>智能续写</span>
          <el-tag type="warning" size="small">片段生成完整内容</el-tag>
        </div>

        <el-form :model="paragraphForm" label-width="130px" class="form-layout continuation-form">
          <el-form-item label="现有内容">
            <el-input
              v-model="paragraphForm.sourceText"
              type="textarea"
              :rows="7"
              placeholder="例如：将样本放入样本槽中，关闭槽盖。"
            />
            <div class="field-hint">已输入 {{ continuationCharCount }} 字</div>
          </el-form-item>
          <el-form-item label="续写意图">
            <el-radio-group v-model="paragraphForm.intent" class="vertical-radio-group">
              <el-radio label="next_step">续写下一步操作（基于上下文推断）</el-radio>
              <el-radio label="expand_detail">扩写详细说明（增加参数/注意事项）</el-radio>
              <el-radio label="safety_warning">补充安全警告（识别风险点）</el-radio>
              <el-radio label="troubleshooting">补充故障处理（基于操作步骤）</el-radio>
              <el-radio label="custom">自定义续写</el-radio>
            </el-radio-group>
            <el-input
              v-if="paragraphForm.intent === 'custom'"
              v-model="paragraphForm.customIntent"
              class="custom-intent-input"
              placeholder="请输入自定义续写要求"
            />
          </el-form-item>
          <el-form-item label="续写长度">
            <el-radio-group v-model="paragraphForm.length">
              <el-radio-button label="short">简短（1-2句）</el-radio-button>
              <el-radio-button label="detailed">详细（1段）</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="续写设置">
            <el-checkbox v-model="paragraphForm.keepTerminology">保持术语一致（自动使用术语库）</el-checkbox>
            <el-checkbox v-model="paragraphForm.keepSentenceStyle">保持句式风格（自动匹配句式手册）</el-checkbox>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="paragraphLoading" @click="generateParagraph">生成续写内容</el-button>
            <el-button @click="resetParagraphForm">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div v-if="paragraphResult" class="panel">
        <div class="panel-header">
          <span>生成结果</span>
          <div class="panel-actions">
            <el-tag v-if="paragraphResult.model" size="small" type="info">模型：{{ paragraphResult.model }}</el-tag>
            <el-button size="small" @click="copyText(currentContinuationText)">复制</el-button>
            <el-button size="small" type="primary" @click="saveContinuationToDocument">保存到文档</el-button>
          </div>
        </div>

        <div class="result-stack">
          <div class="result-block continuation-result">
            <div class="result-label">续写内容</div>
            <el-input
              v-if="paragraphEditing"
              v-model="paragraphEditText"
              type="textarea"
              :rows="8"
            />
            <pre v-else>{{ paragraphResult.continuation }}</pre>
          </div>
          <div class="panel-actions continuation-actions">
            <el-button type="primary" @click="acceptContinuation">接受并插入</el-button>
            <el-button :loading="paragraphLoading" @click="generateParagraph">重新生成</el-button>
            <el-button @click="toggleParagraphEdit">{{ paragraphEditing ? '完成编辑后插入' : '编辑后插入' }}</el-button>
          </div>
          <div class="panel-actions continuation-actions">
            <el-button @click="continueContinuation">继续续写</el-button>
            <el-button @click="saveContinuationToDocument">保存到文档</el-button>
            <el-button @click="goToPolish">去润色</el-button>
          </div>
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
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { generateAPI } from '@/api'

const route = useRoute()
const router = useRouter()

const MAX_IMAGE_STEP_FILES = 4
const MAX_RAW_FILE_SIZE = 5 * 1024 * 1024

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
    title: '智能续写',
    desc: '输入已有内容片段，基于上下文语义推断并续写完整说明。'
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
const imageFiles = ref([])
const imagePreviewVisible = ref(false)
const imagePreviewUrl = ref('')
const imageLoading = ref(false)
const imageProgress = ref(0)
let imageProgressTimer = null
const imageForm = ref({
  generationIntent: 'operation_steps',
  customIntent: '',
  outputFormat: 'numbered_steps',
  languageStyle: 'formal_technical',
  prompt: ''
})
const imageResult = ref(null)
const imageEditing = ref(false)
const imageEditText = ref('')

const currentImageResultText = computed(() => {
  if (imageEditing.value) return imageEditText.value
  return buildImageResultText(imageResult.value)
})

function compressImageFile(file, maxEdge = 900, quality = 0.72) {
  if (!file?.type?.startsWith('image/')) return Promise.resolve(file)
  return new Promise((resolve) => {
    const timeoutId = setTimeout(() => {
      resolve(file)
    }, 5000)
    const image = new Image()
    const objectUrl = URL.createObjectURL(file)
    image.onload = () => {
      URL.revokeObjectURL(objectUrl)
      const scale = Math.min(1, maxEdge / Math.max(image.width, image.height))
      if (scale >= 1) {
        clearTimeout(timeoutId)
        resolve(file)
        return
      }
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(image.width * scale))
      canvas.height = Math.max(1, Math.round(image.height * scale))
      const context = canvas.getContext('2d')
      context.drawImage(image, 0, 0, canvas.width, canvas.height)
      canvas.toBlob((blob) => {
        clearTimeout(timeoutId)
        if (!blob) {
          resolve(file)
          return
        }
        resolve(new File([blob], file.name, { type: 'image/jpeg', lastModified: file.lastModified }))
      }, 'image/jpeg', quality)
    }
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      clearTimeout(timeoutId)
      resolve(file)
    }
    image.src = objectUrl
  })
}

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
  sourceText: '',
  intent: 'next_step',
  customIntent: '',
  length: 'short',
  keepTerminology: true,
  keepSentenceStyle: true
})
const paragraphResult = ref(null)
const paragraphEditing = ref(false)
const paragraphEditText = ref('')

const continuationCharCount = computed(() => paragraphForm.value.sourceText.length)
const currentContinuationText = computed(() => {
  if (!paragraphResult.value) return ''
  return paragraphEditing.value ? paragraphEditText.value : paragraphResult.value.continuation
})

const templates = ref([
  { name: '标准产品说明书模板', type: 'manual', lang: '中文', fields: 15, updated_at: '2025-01-10 10:30', scenes: ['说明书初稿', '智能续写'] },
  { name: '图文描述模板', type: 'image', lang: '中文', fields: 8, updated_at: '2025-01-09 14:20', scenes: ['图片描述生成'] },
  { name: '技术规格文档模板', type: 'spec', lang: '中英文', fields: 22, updated_at: '2025-01-08 09:15', scenes: ['说明书初稿', '智能续写'] }
])

function handleImageChange(file, fileList) {
  if (file.raw && file.raw.size > MAX_RAW_FILE_SIZE) {
    ElMessage.warning(`${file.name} 文件过大 (${(file.raw.size / 1024 / 1024).toFixed(1)}MB)，当前只支持 ${MAX_RAW_FILE_SIZE / 1024 / 1024}MB 以内的图片，请压缩后重试`)
    imageUploadRef.value?.handleRemove?.(file)
    return
  }
  if (fileList.length > MAX_IMAGE_STEP_FILES) {
    ElMessage.warning(`当前最多支持 ${MAX_IMAGE_STEP_FILES} 张图片，请分批处理`)
  }
  imageFiles.value = fileList.slice(0, MAX_IMAGE_STEP_FILES).map((item) => item.raw || item)
}

function handleImageRemove(file, fileList) {
  imageFiles.value = fileList.map((item) => item.raw || item)
}

function handleImagePreview(file) {
  const rawFile = file.raw || file
  imagePreviewUrl.value = file.url || URL.createObjectURL(rawFile)
  imagePreviewVisible.value = true
}

function handleImageExceed() {
  ElMessage.warning(`当前最多支持 ${MAX_IMAGE_STEP_FILES} 张图片，请分批处理`)
}

function startImageProgress() {
  imageProgress.value = 8
  if (imageProgressTimer) window.clearInterval(imageProgressTimer)
  imageProgressTimer = window.setInterval(() => {
    if (imageProgress.value < 90) {
      imageProgress.value += imageProgress.value < 60 ? 6 : 2
    }
  }, 1200)
}

function stopImageProgress(done = false) {
  if (imageProgressTimer) {
    window.clearInterval(imageProgressTimer)
    imageProgressTimer = null
  }
  imageProgress.value = done ? 100 : 0
}

async function generateImageDescription() {
  if (imageFiles.value.length === 0) {
    ElMessage.info('请先上传图片')
    return
  }
  if (imageFiles.value.length > MAX_IMAGE_STEP_FILES) {
    ElMessage.warning(`当前最多支持 ${MAX_IMAGE_STEP_FILES} 张图片，请分批处理`)
    return
  }
  imageLoading.value = true
  startImageProgress()
  imageResult.value = null
  try {
    const formData = new FormData()
    const preparedFiles = await Promise.all(imageFiles.value.map((file) => compressImageFile(file)))
    const maxCompressed = 2 * 1024 * 1024
    const oversized = preparedFiles.find((f) => f.size > maxCompressed)
    if (oversized) {
      ElMessage.warning(`${oversized.name} 压缩后仍超过 2MB，图片可能过大，建议缩小尺寸后重试`)
      imageLoading.value = false
      return
    }
    preparedFiles.forEach((file) => formData.append('files', file))
    formData.append('prompt', imageForm.value.prompt)
    formData.append('generation_intent', imageForm.value.generationIntent)
    formData.append('custom_intent', imageForm.value.customIntent)
    formData.append('output_format', imageForm.value.outputFormat)
    formData.append('language_style', imageForm.value.languageStyle)
    const resp = await generateAPI.generateImageSteps(formData)
    const data = resp.data || {}
    if (!(data.steps || []).length) {
      throw new Error(data.detail || 'empty image steps result')
    }
    imageResult.value = {
      summary: data.summary || '',
      relation_summary: data.relation_summary || '',
      steps: normalizeImageSteps(data.steps || []),
      model: data.model || 'kimi',
      warning: data.warning || ''
    }
    imageEditText.value = buildImageResultText(imageResult.value)
    imageEditing.value = false
    stopImageProgress(true)
    ElMessage[data.warning ? 'warning' : 'success'](data.warning ? '当前为兜底结果' : '操作步骤已生成')
  } catch (error) {
    stopImageProgress(false)
    ElMessage.error(error?.response?.data?.detail || error?.message || '生成失败，请查看后端日志')
  } finally {
    imageLoading.value = false
  }
}

function resetImageForm() {
  clearUploadedImages()
  imageForm.value = {
    generationIntent: 'operation_steps',
    customIntent: '',
    outputFormat: 'numbered_steps',
    languageStyle: 'formal_technical',
    prompt: ''
  }
  imageResult.value = null
  imageEditing.value = false
  imageEditText.value = ''
}

function clearUploadedImages() {
  imageFiles.value = []
  imageUploadRef.value?.clearFiles?.()
}

function buildImageResultText(result) {
  if (!result) return ''
  const steps = normalizeImageSteps(result.steps || [])
  if (imageForm.value.outputFormat === 'plain_text') {
    return steps.join('\n')
  }
  return steps.map((step, index) => {
    const text = String(step || '').trim()
    return /^\d+[.)、]\s*/.test(text) ? text : `${index + 1}. ${text}`
  }).join('\n')
}

function cleanImageResultStep(step) {
  const raw = String(step || '').trim()
  if (/^\s*\*{0,2}"?(summary|relation_summary|used_style_guide_name)"?\*{0,2}\s*:/i.test(raw)) {
    return ''
  }
  return raw
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/```$/g, '')
    .replace(/^\s*\*{0,2}"?steps"?\*{0,2}\s*:\s*\[?/i, '')
    .replace(/^\s*["'`]+|["'`,，]+\s*$/g, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .trim()
}

function normalizeImageSteps(steps) {
  return (steps || [])
    .flatMap((step) => String(step || '').split('\n'))
    .map(cleanImageResultStep)
    .filter((step) => step && !/^(\{|\}|\[|\]|\],?)$/.test(step))
    .filter((step) => !/^(summary|relation_summary|used_style_guide_name|steps)\b/i.test(step))
}

function parseImageResultText(text) {
  return String(text || '')
    .split('\n')
    .map((line) => line.replace(/^\s*(?:\d+[.)、]|[-*])\s*/, '').trim())
    .filter(Boolean)
}

function stripStepNumber(step) {
  return cleanImageResultStep(step).replace(/^\s*\d+[.)、]\s*/, '')
}

function toggleImageEdit() {
  if (!imageResult.value) return
  if (imageEditing.value) {
    const steps = parseImageResultText(imageEditText.value)
    if (!steps.length) {
      ElMessage.warning('编辑内容不能为空')
      return
    }
    imageResult.value = { ...imageResult.value, steps }
    imageEditText.value = buildImageResultText(imageResult.value)
    imageEditing.value = false
    ElMessage.success('编辑已应用')
    return
  }
  imageEditText.value = buildImageResultText(imageResult.value)
  imageEditing.value = true
}

function regenerateImageDescription() {
  imageEditing.value = false
  generateImageDescription()
}

function saveImageResult() {
  const content = currentImageResultText.value
  if (!content.trim()) {
    ElMessage.warning('暂无可保存内容')
    return
  }
  downloadText('图片描述生成结果.txt', content)
}

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
  if (!paragraphForm.value.sourceText.trim()) {
    ElMessage.info('请填写现有内容')
    return
  }
  if (paragraphForm.value.intent === 'custom' && !paragraphForm.value.customIntent.trim()) {
    ElMessage.info('请填写自定义续写要求')
    return
  }
  paragraphLoading.value = true
  try {
    const resp = await generateAPI.continueText({
      source_text: paragraphForm.value.sourceText,
      intent: paragraphForm.value.intent,
      custom_intent: paragraphForm.value.customIntent,
      length: paragraphForm.value.length,
      keep_terminology: paragraphForm.value.keepTerminology,
      keep_sentence_style: paragraphForm.value.keepSentenceStyle
    })
    const data = resp.data || {}
    paragraphResult.value = {
      source_text: data.source_text || paragraphForm.value.sourceText,
      continuation: cleanContinuationText(data.continuation || buildParagraphFallback()),
      used_terminology_files: data.used_terminology_files || [],
      used_style_guide_name: data.used_style_guide_name || '',
      model: data.model || 'kimi',
      warning: data.warning || ''
    }
    paragraphEditText.value = paragraphResult.value.continuation
    paragraphEditing.value = false
    ElMessage[data.warning ? 'warning' : 'success'](data.warning || '续写内容已生成')
  } catch (error) {
    paragraphResult.value = {
      source_text: paragraphForm.value.sourceText,
      continuation: buildParagraphFallback(),
      used_terminology_files: [],
      used_style_guide_name: '',
      model: 'fallback',
      warning: '接口调用失败，已展示本地示例续写。'
    }
    paragraphEditText.value = paragraphResult.value.continuation
    paragraphEditing.value = false
    ElMessage.info('接口调用失败，已展示示例续写')
  } finally {
    paragraphLoading.value = false
  }
}

function buildParagraphFallback() {
  if (paragraphForm.value.intent === 'safety_warning') {
    return '请确认相关部件已正确放置并保持稳定，避免因安装不到位导致处理失败。操作过程中如发现异常提示，应停止当前流程并按故障处理说明进行检查。'
  }
  if (paragraphForm.value.intent === 'troubleshooting') {
    return '若系统未进入下一步，请检查样本位置、槽盖状态和界面提示信息。确认条件满足后，重新执行当前操作并观察系统反馈。'
  }
  if (paragraphForm.value.intent === 'expand_detail') {
    return '执行该操作前，应确认样本、耗材和设备状态均满足使用要求。完成操作后，观察界面状态变化，并根据提示继续后续流程。'
  }
  return '请确认当前操作对象已正确就位，然后点击界面中的开始按钮启动处理流程。系统进入下一步后，按照页面提示继续完成后续操作。'
}

function cleanContinuationText(text) {
  return String(text || '')
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/```$/g, '')
    .replace(/^\s*["'`]+|["'`,，]+\s*$/g, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .trim()
}

function applyContinuationToSource() {
  if (!paragraphResult.value) return ''
  const continuation = cleanContinuationText(paragraphEditing.value ? paragraphEditText.value : paragraphResult.value.continuation)
  paragraphForm.value.sourceText = [paragraphResult.value.source_text, continuation].filter(Boolean).join('\n')
  paragraphResult.value.source_text = paragraphForm.value.sourceText
  paragraphResult.value.continuation = continuation
  paragraphEditText.value = continuation
  paragraphEditing.value = false
  return continuation
}

function acceptContinuation() {
  const continuation = applyContinuationToSource()
  if (continuation) {
    paragraphResult.value = null
    paragraphEditText.value = ''
    ElMessage.success('续写内容已插入现有内容')
  }
}

function continueContinuation() {
  acceptContinuation()
  paragraphResult.value = null
  generateParagraph()
}

function toggleParagraphEdit() {
  if (!paragraphResult.value) return
  if (paragraphEditing.value) {
    if (!paragraphEditText.value.trim()) {
      ElMessage.warning('编辑内容不能为空')
      return
    }
    acceptContinuation()
    return
  }
  paragraphEditText.value = paragraphResult.value.continuation
  paragraphEditing.value = true
}

function saveContinuationToDocument() {
  const content = currentContinuationText.value
  if (!content.trim()) {
    ElMessage.warning('暂无可保存内容')
    return
  }
  downloadText('智能续写结果.txt', content)
}

function goToPolish() {
  const content = currentContinuationText.value
  if (content.trim()) {
    sessionStorage.setItem('pendingPolishText', content)
  }
  router.push('/polish')
}

function resetParagraphForm() {
  paragraphForm.value = {
    sourceText: '',
    intent: 'next_step',
    customIntent: '',
    length: 'short',
    keepTerminology: true,
    keepSentenceStyle: true
  }
  paragraphResult.value = null
  paragraphEditing.value = false
  paragraphEditText.value = ''
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

.image-progress-wrap {
  width: min(460px, 100%);
}

.image-progress-text {
  display: block;
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
}

.intent-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.custom-intent-input {
  display: block;
  margin-top: 10px;
  max-width: 520px;
}

.result-warning {
  margin-bottom: 16px;
}

.image-upload :deep(.el-upload-list--picture-card) {
  display: grid;
  grid-template-columns: repeat(auto-fill, 88px);
  gap: 10px;
  width: 100%;
  padding-bottom: 0;
}

.image-upload :deep(.el-upload--picture-card),
.image-upload :deep(.el-upload-list__item) {
  width: 88px;
  min-width: 88px;
  height: 88px;
}

.image-preview-img {
  display: block;
  max-width: 100%;
  max-height: 72vh;
  margin: 0 auto;
  object-fit: contain;
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
  font-size: 24px;
  line-height: 1;
  margin-bottom: 6px;
}

.upload-trigger-text {
  font-size: 12px;
}

.form-layout {
  max-width: 860px;
}

.image-form-layout {
  max-width: 100%;
}

.continuation-form {
  max-width: 900px;
}

.field-hint {
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
}

.vertical-radio-group {
  display: grid;
  gap: 10px;
}

.vertical-radio-group :deep(.el-radio) {
  margin-right: 0;
  white-space: normal;
  line-height: 1.5;
}

.continuation-result {
  display: grid;
  gap: 12px;
}

.continuation-actions {
  flex-wrap: wrap;
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
