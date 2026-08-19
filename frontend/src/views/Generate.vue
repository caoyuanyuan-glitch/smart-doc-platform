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
          <el-form-item label="选择模板">
            <el-button @click="templateDialogVisible = true">
              {{ templateFile ? templateFile.name : '选择模板文件' }}
            </el-button>
            <el-button v-if="templateFile" type="danger" plain size="small" style="margin-left: 8px;" @click="clearTemplateFile">清除</el-button>
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
            <el-button v-if="imageResult.draftRaw || imageResult.refinedRaw" size="small" type="warning" @click="debugDialogVisible = true">调试</el-button>
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

      <el-dialog v-model="debugDialogVisible" title="调试：模型原始输出" width="min(1100px, 96vw)">
        <div v-if="imageResult?.templateDebugContent" style="margin-bottom: 20px;">
          <h4>参考模板文件：{{ imageResult.templateName }}</h4>
          <pre class="debug-raw-output" style="max-height: 500px;">{{ imageResult.templateDebugContent }}</pre>
        </div>
        <div v-if="imageResult?.draftPrompt" style="margin-bottom: 20px;">
          <h4>初稿提示词 (Kimi Vision Prompt)</h4>
          <pre class="debug-raw-output">{{ imageResult.draftPrompt }}</pre>
        </div>
        <div v-if="imageResult?.draftRaw" style="margin-bottom: 20px;">
          <h4>初稿原始输出 (Kimi Vision Response)</h4>
          <pre class="debug-raw-output">{{ imageResult.draftRaw }}</pre>
        </div>
        <div v-if="imageResult?.refinedPrompt" style="margin-bottom: 20px;">
          <h4>润色提示词 (Refine Prompt)</h4>
          <pre class="debug-raw-output" style="max-height: 600px;">{{ imageResult.refinedPrompt }}</pre>
        </div>
        <div v-if="imageResult?.refinedRaw">
          <h4>润色后原始输出 (Refine Response)</h4>
          <pre class="debug-raw-output">{{ imageResult.refinedRaw }}</pre>
        </div>
        <div v-if="!imageResult?.templateDebugContent && !imageResult?.draftRaw && !imageResult?.refinedRaw && !imageResult?.draftPrompt && !imageResult?.refinedPrompt" style="color: #999;">
          暂无原始输出数据
        </div>
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
      <div class="panel continuation-panel">
        <div class="continuation-card">
          <div class="continuation-card-head">
            <div class="continuation-icon">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2a4 4 0 0 1 4 4v2h1a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h1V6a4 4 0 0 1 4-4Z"/>
                <circle cx="9" cy="15" r="1" fill="currentColor"/>
                <circle cx="15" cy="15" r="1" fill="currentColor"/>
                <path d="M9 11h6"/>
              </svg>
            </div>
            <div class="continuation-title-wrap">
              <span class="continuation-title">智能续写</span>
              <span class="continuation-subtitle">片段生成完整内容</span>
            </div>
          </div>

          <el-form :model="paragraphForm" label-width="130px" class="form-layout continuation-form">
            <div class="template-switch-row">
              <span class="template-switch-label">参考模板文件</span>
              <el-switch
                v-model="templateSwitchOn"
                active-color="#409EFF"
              />
              <template v-if="templateAnalyzeStatus === 'analyzing'">
                <span class="template-file-badge" style="background:#ecf5ff;border-color:#409EFF;">
                  📄 {{ templateJobFilename }} · 分析中… ({{ templateAnalyzeLabel }})
                </span>
                <el-progress :percentage="Math.min(20 * templateAnalyzeStep, 100)" :stroke-width="6" style="margin-left:12px;width:160px;" />
              </template>
              <template v-else-if="templateAnalyzeStatus === 'done'">
                <span class="template-file-badge" :style="templateParseStatus === 'fallback' ? 'background:#fdf6ec;border-color:#e6a23c;color:#b88230;' : ''">
                  ✅ {{ templateJobFilename }}
                  <el-icon class="template-file-clear" @click="clearTemplateFileAndSwitch"><Close /></el-icon>
                </span>
                <span v-if="templateParseStatus === 'fallback'" class="template-switch-hint" style="color:#e6a23c;">（部分降级为本地轻量解析）</span>
              </template>
              <template v-else-if="templateAnalyzeStatus === 'failed'">
                <span class="template-file-badge" style="background:#fef0f0;border-color:#f56c6c;color:#c45656;">
                  ⚠️ 分析失败：{{ templateAnalyzeLabel }}
                  <el-icon class="template-file-clear" @click="clearTemplateFileAndSwitch"><Close /></el-icon>
                </span>
              </template>
              <span v-else-if="templateSwitchOn" class="template-switch-hint">请上传模板文件并点击确认开始分析</span>
              <span v-else class="template-switch-hint">开启后可上传模板说明书，AI 将参考其风格和结构进行续写</span>
            </div>

            <el-form-item label="现有内容">
              <el-input
                v-model="paragraphForm.sourceText"
                type="textarea"
                :rows="7"
                placeholder="例如：将样本放入样本槽中，关闭槽盖。"
              />
              <div class="field-hint">已输入 {{ continuationCharCount }} 字</div>
            </el-form-item>

            <el-form-item label="当前标题/章节名">
              <el-input
                v-model="paragraphForm.chapterTitle"
                placeholder="选填，例如：2.3 启动操作 / 样本制备流程"
                clearable
              />
            </el-form-item>

            <el-form-item label="续写意图">
              <el-select
                v-model="paragraphForm.intent"
                class="intent-select"
                placeholder="请选择续写意图"
              >
                <el-option
                  v-for="opt in intentOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <div
                v-if="paragraphForm.intent === 'custom'"
                class="custom-intent-wrap"
              >
                <el-input
                  v-model="paragraphForm.customIntent"
                  placeholder="请输入自定义续写要求"
                />
              </div>
            </el-form-item>

            <el-form-item label="续写长度">
              <el-radio-group v-model="paragraphForm.length">
                <el-radio-button label="auto">自动</el-radio-button>
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
            <el-button :loading="paragraphLoading" @click="regenerateParagraph">重新生成</el-button>
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

    <el-dialog v-model="templateDialogVisible" title="上传模板文件" width="min(520px, 90vw)">
      <el-upload
        ref="templateUploadRef"
        class="template-dialog-upload"
        action="#"
        :auto-upload="false"
        :show-file-list="false"
        :limit="1"
        :size-limit="MAX_TEMPLATE_SIZE"
        accept=".docx,.md,.pdf,.txt"
        :on-change="handleTemplateDialogChange"
        :on-exceed="handleTemplateExceed"
        drag
      >
        <div class="upload-drag-area">
          <div class="upload-drag-icon">+</div>
          <div class="upload-drag-text">将文件拖到此处，或点击选择</div>
          <div class="upload-drag-hint">支持 .docx .md .pdf .txt（≤ 10 MB）</div>
        </div>
      </el-upload>
      <div v-if="templateFile" style="margin-top: 12px; padding: 8px 12px; border-radius: 6px; font-size: 13px;" :style="templateFile.size > MAX_TEMPLATE_SIZE ? 'background:#fef0f0;color:#c45656;' : 'background:#f0f9eb;color:#374151;'">
        已选择：{{ templateFile.name }} ({{ (templateFile.size / 1024).toFixed(1) }} KB)
        <span v-if="templateFile.size > MAX_TEMPLATE_SIZE" style="margin-left:8px;font-weight:500;">⚠️ 超过 10 MB 限制</span>
      </div>
      <template #footer>
        <el-button @click="cancelTemplateDialog">取消</el-button>
        <el-button type="primary" :disabled="!templateFile || templateFile.size > MAX_TEMPLATE_SIZE" @click="confirmTemplateAnalyze">确认并开始分析</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import { generateAPI } from '@/api'

const route = useRoute()
const router = useRouter()

const MAX_IMAGE_STEP_FILES = 4
const MAX_RAW_FILE_SIZE = 5 * 1024 * 1024
const MAX_TEMPLATE_SIZE = 10 * 1024 * 1024
const PARAGRAPH_STATE_KEY = 'smart_doc_continuation_paragraph_state'

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
const templateFile = ref(null)
const imageResult = ref(null)
const imageEditing = ref(false)
const imageEditText = ref('')
const debugDialogVisible = ref(false)
const templateDialogVisible = ref(false)
const templateUploadRef = ref(null)

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
  chapterTitle: '',
  intent: 'next_step',
  customIntent: '',
  length: 'auto',
  keepTerminology: true,
  keepSentenceStyle: true
})
const paragraphResult = ref(null)
const paragraphEditing = ref(false)
const paragraphEditText = ref('')
const regenerateSeq = ref(0)

const templateSwitchOn = ref(false)

const templateJobId = ref('')
const templateAnalyzeStatus = ref('idle') // idle | analyzing | done | failed
const templateAnalyzeStep = ref(0)
const templateAnalyzeLabel = ref('')
const templateParseStatus = ref('') // ai | fallback | ''
const templateJobFilename = ref('')
let templatePollingTimer = null

watch(templateSwitchOn, (val) => {
  if (val) {
    if (!templateJobId.value) {
      templateDialogVisible.value = true
    }
  } else {
    stopPolling()
    templateAnalyzeStatus.value = 'idle'
    templateAnalyzeStep.value = 0
    templateAnalyzeLabel.value = ''
    templateParseStatus.value = ''
    templateJobFilename.value = ''
    clearTemplateFile()
    templateJobId.value = ''
    persistParagraphState()
  }
})

watch(paragraphForm, persistParagraphState, { deep: true })

function clearTemplateFileAndSwitch() {
  clearTemplateFile()
  templateJobId.value = ''
  templateAnalyzeStatus.value = 'idle'
  templateAnalyzeStep.value = 0
  templateAnalyzeLabel.value = ''
  templateParseStatus.value = ''
  templateJobFilename.value = ''
  stopPolling()
  templateSwitchOn.value = false
  stopPolling()
  clearParagraphState()
  persistParagraphState()
}

function cancelTemplateDialog() {
  templateDialogVisible.value = false
  clearTemplateFile()
  if (templateSwitchOn.value && !templateJobId.value) {
    templateSwitchOn.value = false
  }
}

// ── localStorage 持久化 ──────────────────────────────────────────────

function persistParagraphState() {
  try {
    const payload = {
      templateSwitchOn: templateSwitchOn.value,
      templateJobId: templateJobId.value,
      templateAnalyzeStatus: templateAnalyzeStatus.value,
      templateAnalyzeStep: templateAnalyzeStep.value,
      templateAnalyzeLabel: templateAnalyzeLabel.value,
      templateParseStatus: templateParseStatus.value,
      templateJobFilename: templateJobFilename.value,
      paragraphForm: { ...paragraphForm.value },
    }
    localStorage.setItem(PARAGRAPH_STATE_KEY, JSON.stringify(payload))
  } catch (e) {
    // localStorage 满了忽略
  }
}

function restoreParagraphState() {
  try {
    const raw = localStorage.getItem(PARAGRAPH_STATE_KEY)
    if (!raw) return
    const payload = JSON.parse(raw)
    if (payload.paragraphForm) {
      paragraphForm.value = { ...paragraphForm.value, ...payload.paragraphForm }
    }
    if (payload.templateSwitchOn) templateSwitchOn.value = payload.templateSwitchOn
    if (payload.templateJobId) templateJobId.value = payload.templateJobId
    if (payload.templateAnalyzeStatus) templateAnalyzeStatus.value = payload.templateAnalyzeStatus
    if (payload.templateAnalyzeStep) templateAnalyzeStep.value = payload.templateAnalyzeStep
    if (payload.templateAnalyzeLabel) templateAnalyzeLabel.value = payload.templateAnalyzeLabel
    if (payload.templateParseStatus) templateParseStatus.value = payload.templateParseStatus
    if (payload.templateJobFilename) templateJobFilename.value = payload.templateJobFilename

    if (templateJobId.value && templateAnalyzeStatus.value === 'analyzing') {
      startPolling(templateJobId.value, true)
    }
  } catch (e) {}
}

function clearParagraphState() {
  try { localStorage.removeItem(PARAGRAPH_STATE_KEY) } catch (e) {}
}

// ── 模板异步分析（卡点 1-A）─────────────────────────────────────────

async function confirmTemplateAnalyze() {
  if (!templateFile.value) {
    ElMessage.warning('请先选择模板文件')
    return
  }
  if (templateFile.value.size > MAX_TEMPLATE_SIZE) {
    ElMessage.error(
      `文件过大（${(templateFile.value.size / 1024 / 1024).toFixed(1)} MB），` +
      `请上传 10 MB 以内的文件`
    )
    return
  }
  templateDialogVisible.value = false
  await startTemplateAnalyze(templateFile.value)
}

async function startTemplateAnalyze(rawFile) {
  templateAnalyzeStatus.value = 'analyzing'
  templateAnalyzeStep.value = 0
  templateJobFilename.value = rawFile.name
  templateAnalyzeLabel.value = '已提交，等待处理'
  persistParagraphState()

  try {
    const fd = new FormData()
    fd.append('template_file', rawFile)
    const resp = await generateAPI.templateAnalyze(fd)
    const job = resp.data || {}
    templateJobId.value = job.job_id
    templateAnalyzeStep.value = job.step || 0
    templateAnalyzeLabel.value = job.step_label || '已提交'
    persistParagraphState()
    startPolling(templateJobId.value)
  } catch (e) {
    const msg = e?.response?.data?.detail || '模板分析提交失败'
    templateAnalyzeStatus.value = 'failed'
    templateAnalyzeLabel.value = typeof msg === 'string' ? msg : '提交失败'
    persistParagraphState()
    ElMessage.error(templateAnalyzeLabel.value)
  }
}

function startPolling(jobId, silent = false) {
  stopPolling()
  templatePollingTimer = setInterval(async () => {
    try {
      const resp = await generateAPI.templateStatus(jobId)
      const job = resp.data || {}
      templateAnalyzeStep.value = job.step || 0
      templateAnalyzeLabel.value = job.step_label || '处理中'

      if (job.status === 'done') {
        templateAnalyzeStatus.value = 'done'
        templateParseStatus.value = job.parse_status || ''
        stopPolling()
        if (templateParseStatus.value === 'fallback') {
          ElMessage.warning(
            '模板解析已完成，但部分内容降级为本地方案（可能影响续写效果）'
          )
        } else if (!silent) {
          ElMessage.success('模板分析完成，可以开始续写了')
        }
        persistParagraphState()
      } else if (job.status === 'failed') {
        templateAnalyzeStatus.value = 'failed'
        templateAnalyzeLabel.value = job.error || '分析失败'
        stopPolling()
        persistParagraphState()
        if (!silent) ElMessage.error(templateAnalyzeLabel.value)
      }
    } catch (e) {
      // 单次轮询失败不致命，继续下一轮
    }
  }, 1500)
}

function stopPolling() {
  if (templatePollingTimer) {
    clearInterval(templatePollingTimer)
    templatePollingTimer = null
  }
}

const intentOptions = [
  { value: 'next_step', label: '续写下一步操作' },
  { value: 'expand_detail', label: '扩写详细说明' },
  { value: 'supplement_parameters', label: '补充参数说明' },
  { value: 'supplement_notices', label: '补充注意事项' },
  { value: 'safety_warning', label: '补充安全警告' },
  { value: 'troubleshooting', label: '补充故障处理' },
  { value: 'custom', label: '自定义续写' }
]

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

function handleTemplateDialogChange(file) {
  templateFile.value = file.raw
}

function clearTemplateFile() {
  templateFile.value = null
  templateUploadRef.value?.clearFiles?.()
  templateJobId.value = ''
  templateAnalyzeStatus.value = 'idle'
  templateAnalyzeStep.value = 0
  templateAnalyzeLabel.value = ''
  templateParseStatus.value = ''
  templateJobFilename.value = ''
  stopPolling()
  persistParagraphState()
}

function handleTemplateExceed() {
  ElMessage.warning('最多只能选择一个模板文件')
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
    if (templateFile.value) {
      formData.append('template_file', templateFile.value)
    }
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
      warning: data.warning || '',
      draftRaw: data.draft_raw || '',
      refinedRaw: data.refined_raw || '',
      draftPrompt: data.draft_prompt || '',
      refinedPrompt: data.refined_prompt || '',
      templateName: data.template_name || '',
      templateContent: data.template_content || '',
      templateDebugContent: data.template_debug_content || ''
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
  templateFile.value = null
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

async function regenerateParagraph() {
  // 累加重写序号，让后端注入温度抖动和角度提示，保证每次结果不同
  regenerateSeq.value += 1
  await generateParagraph()
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
    const formData = new FormData()
    formData.append('source_text', paragraphForm.value.sourceText)
    formData.append('chapter_title', paragraphForm.value.chapterTitle || '')
    formData.append('intent', paragraphForm.value.intent)
    formData.append('custom_intent', paragraphForm.value.customIntent)
    formData.append('length', paragraphForm.value.length)
    formData.append('keep_terminology', paragraphForm.value.keepTerminology)
    formData.append('keep_sentence_style', paragraphForm.value.keepSentenceStyle)
    formData.append('regenerate_seq', regenerateSeq.value)
    if (templateSwitchOn.value) {
      if (templateJobId.value && templateAnalyzeStatus.value === 'done') {
        formData.append('template_job_id', templateJobId.value)
      } else if (templateJobId.value && templateAnalyzeStatus.value === 'analyzing') {
        ElMessage.warning('模板仍在分析中，请稍候')
        paragraphLoading.value = false
        return
      } else if (templateFile.value) {
        formData.append('template_file', templateFile.value)
      }
    }
    const resp = await generateAPI.continueText(formData)
    const data = resp.data || {}
    paragraphResult.value = {
      source_text: data.source_text || paragraphForm.value.sourceText,
      continuation: cleanContinuationText(data.continuation || buildParagraphFallback()),
      used_terminology_files: data.used_terminology_files || [],
      used_style_guide_name: data.used_style_guide_name || '',
      model: data.model || 'kimi',
      warning: data.warning || '',
      audit: data.audit || null
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
  const intent = paragraphForm.value.intent
  if (intent === 'next_step') {
    return '完成当前操作后，在控制面板点击确认按钮，等待系统响应并观察界面状态变化。'
  }
  if (intent === 'expand_detail') {
    return '该步骤的执行效果受样本初始状态、环境温湿度及设备校准精度共同影响，操作前需确保各项前置条件满足说明书规定。'
  }
  if (intent === 'supplement_parameters') {
    return '工作电压：DC 12V ± 5%\n环境温度：15 ℃ ~ 30 ℃\n相对湿度：≤ 75%\n样本容量：0.5 mL ~ 2.0 mL\n运行时长：约 45 分钟'
  }
  if (intent === 'supplement_notices') {
    return '操作前请核对样本编号与录入信息是否一致。\n运行过程中请勿触碰设备外壳。\n更换耗材后请注意及时关闭舱门。\n操作完成后建议对工作台进行清洁。'
  }
  if (intent === 'safety_warning') {
    return '⚠️ 舱门未完全关闭即启动设备，可能导致样本飞溅或运动部件外露，务必确认锁定后再执行。\n⚠️ 长时间连续运行会使设备过热，建议每 4 小时停机休息 10 分钟。\n⚠️ 请勿将磁性物品靠近控制主板，可能影响传感器读数准确性。'
  }
  if (intent === 'troubleshooting') {
    return '异常标志：设备启动后界面无响应 → 检查电源插头是否插紧，重新上电重试。\n异常标志：槽盖关闭后系统仍提示未锁定 → 检查槽盖传感器是否被异物遮挡，清理后再次关闭。\n异常标志：实验中途暂停 → 查看样本是否偏离采样位，复位后点击继续按钮。'
  }
  if (intent === 'custom' && paragraphForm.value.customIntent.trim()) {
    return `（示例续写）${paragraphForm.value.customIntent.trim()}：请确认操作对象就位后，按界面提示完成后续步骤。`
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
    chapterTitle: '',
    intent: 'next_step',
    customIntent: '',
    length: 'auto',
    keepTerminology: true,
    keepSentenceStyle: true
  }
  paragraphResult.value = null
  paragraphEditing.value = false
  paragraphEditText.value = ''
  regenerateSeq.value = 0
  templateSwitchOn.value = false
  stopPolling()
  clearParagraphState()
  clearTemplateFile()
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

onMounted(() => {
  restoreParagraphState()
})

onBeforeUnmount(() => {
  stopPolling()
  persistParagraphState()
})
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

.custom-intent-wrap {
  width: 100%;
  margin-top: 10px;
}

.custom-intent-wrap :deep(.el-input) {
  width: 100%;
}

.template-upload-wrap {
  width: 100%;
  margin-top: 10px;
}

.template-upload :deep(.el-upload-list) {
  margin-top: 8px;
}

.template-upload .el-upload__tip {
  color: #6b7280;
  font-size: 12px;
  margin-top: 4px;
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

.continuation-panel {
  padding: 0;
  overflow: hidden;
}

.continuation-card {
  padding: 28px 28px 8px;
}

.continuation-card-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 20px;
}

.continuation-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-radius: 12px;
  flex-shrink: 0;
}

.continuation-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.continuation-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
}

.continuation-subtitle {
  font-size: 13px;
  color: #6b7280;
}

.intent-select {
  width: 100%;
}

.intent-select :deep(.el-select__wrapper) {
  border-radius: 8px;
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

.debug-raw-output {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 8px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow-y: auto;
}

.upload-drag-area {
  padding: 40px 20px;
  text-align: center;
}

.upload-drag-icon {
  font-size: 40px;
  color: #c0c4cc;
  margin-bottom: 8px;
}

.upload-drag-text {
  font-size: 14px;
  color: #606266;
  margin-bottom: 4px;
}

.upload-drag-hint {
  font-size: 12px;
  color: #c0c4cc;
}

@media (max-width: 960px) {
  .page-header {
    flex-direction: column;
  }
}

.template-switch-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 20px;
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.template-switch-label {
  font-weight: 600;
  font-size: 14px;
  color: #1f2937;
  margin-right: 4px;
}

.template-switch-hint {
  font-size: 12px;
  color: #94a3b8;
}

.template-file-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #2563eb;
  background: #eff6ff;
  padding: 4px 10px;
  border-radius: 6px;
}

.template-file-clear {
  cursor: pointer;
  color: #94a3b8;
  font-size: 14px;
  transition: color 0.15s;
}

.template-file-clear:hover {
  color: #ef4444;
}
</style>
