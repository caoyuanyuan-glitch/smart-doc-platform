<template>
  <div class="qa-container">
    <div v-if="currentView === 'chat'">
      <h2 class="page-title">智能问答</h2>

      <div class="qa-layout">
        <aside class="knowledge-panel">
          <div class="panel-title">选择知识库</div>
          <div
            v-for="kb in knowledgeBases"
            :key="kb.id"
            class="kb-item"
            :class="{ active: selectedKb.includes(kb.id) }"
            @click="toggleKb(kb.id)"
          >
            <div class="kb-icon" :style="{ background: kb.color }">
              <el-icon><Collection /></el-icon>
            </div>
            <div class="kb-info">
              <div class="kb-name">{{ kb.name }}</div>
              <div class="kb-desc">{{ kb.desc }}</div>
            </div>
            <el-checkbox :model-value="selectedKb.includes(kb.id)" @change="() => toggleKb(kb.id)" />
          </div>

          <div class="quick-title">快捷问题</div>
          <div
            v-for="(q, i) in quickQuestions"
            :key="i"
            class="quick-item"
            @click="sendQuestion(q)"
          >
            {{ q }}
          </div>
        </aside>

        <section class="chat-panel">
          <div class="chat-messages" ref="chatBox">
            <div v-for="(msg, i) in messages" :key="i" class="message" :class="msg.role">
              <div class="avatar" :class="msg.role">
                <el-icon v-if="msg.role === 'user'"><User /></el-icon>
                <el-icon v-else><ChatDotRound /></el-icon>
              </div>
              <div class="bubble-wrap">
                <div class="bubble">{{ msg.content }}</div>
                <div v-if="msg.sources && msg.sources.length" class="sources">
                  <div class="sources-title">参考来源：</div>
                  <div v-for="(s, si) in msg.sources" :key="si" class="source-item">{{ s }}</div>
                </div>
              </div>
            </div>
            <div v-if="loading" class="message assistant">
              <div class="avatar assistant"><el-icon><ChatDotRound /></el-icon></div>
              <div class="bubble typing">正在思考中<span class="dots">...</span></div>
            </div>
          </div>
          <div class="chat-input">
            <el-input
              v-model="question"
              type="textarea"
              :rows="2"
              placeholder="请输入您的问题，按Enter发送，Shift+Enter换行..."
              @keydown.enter.exact.prevent="sendQuestion(question)"
            />
            <el-button type="primary" :loading="loading" @click="sendQuestion(question)">发送</el-button>
          </div>
        </section>
      </div>
    </div>

    <div v-if="currentView === 'library'">
      <h2 class="page-title">知识库管理</h2>
      <div class="panel">
        <div class="panel-header">
          <span>已有知识库</span>
          <el-button type="primary" size="small">新增知识库</el-button>
        </div>
        <el-table :data="knowledgeBases" border>
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="desc" label="描述" />
          <el-table-column prop="docs" label="文档数" width="100" />
          <el-table-column prop="updated_at" label="更新时间" width="180" />
          <el-table-column label="操作" width="160">
            <template #default>
              <el-button size="small">管理</el-button>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { qaAPI } from '@/api'
import { User, ChatDotRound, Collection } from '@element-plus/icons-vue'

const route = useRoute()
const question = ref('')
const loading = ref(false)
const chatBox = ref(null)
const selectedKb = ref(['tech', 'experience'])

const knowledgeBases = ref([
  { id: 'tech', name: '技术文档库', desc: '产品技术规格、API文档、开发指南', docs: 128, color: '#3b82f6', updated_at: '2025-01-10 10:30' },
  { id: 'experience', name: '历史经验库', desc: '过往项目经验总结与问题排查记录', docs: 86, color: '#7c3aed', updated_at: '2025-01-08 15:20' },
  { id: 'manual', name: '产品说明书', desc: '各型号产品使用说明书与操作手册', docs: 64, color: '#10b981', updated_at: '2025-01-05 09:15' },
  { id: 'architecture', name: '系统架构文档', desc: '系统设计、架构图、部署文档', docs: 42, color: '#f59e0b', updated_at: '2024-12-28 14:00' },
  { id: 'ops', name: '运维文档', desc: '运维手册、故障处理流程、监控指标', docs: 55, color: '#ef4444', updated_at: '2025-01-03 11:45' },
  { id: 'security', name: '安全文档', desc: '安全规范、漏洞说明、合规文档', docs: 38, color: '#0891b2', updated_at: '2024-12-30 16:20' }
])

const quickQuestions = [
  '产品的技术规格有哪些？',
  '如何处理常见的系统故障？',
  '请说明设备的使用注意事项',
  '系统部署的基本流程是？'
]

const sampleAnswers = {
  '产品的技术规格有哪些？': '根据技术文档库与历史经验，产品核心技术规格如下：\n\n1. 检测原理：免疫层析法\n2. 检测时间：15分钟内出结果\n3. 储存温度：2~30°C\n4. 样本类型：血清/血浆/全血\n5. 适用环境：温度15~30°C，湿度≤80%\n\n详细规格请参考对应型号的产品说明书（文档编号：TECH-2025-001）。',
  '如何处理常见的系统故障？': '基于历史经验库，常见系统故障及处理建议：\n\n1. 检测结果无显示 → 检查试剂是否过期、操作是否规范\n2. 信号值偏低 → 确认样本采集方式与体积\n3. 设备报错E-01 → 重新启动，若持续请联系技术支持\n\n如问题未解决，建议查阅「故障排查手册V2.0」或联系400客服。',
  '请说明设备的使用注意事项': '根据产品说明书与安全规范：\n\n1. 使用前必须阅读完整说明书\n2. 试剂需在有效期内使用，过期试剂禁止使用\n3. 本产品仅用于体外诊断，不得直接接触体内组织\n4. 使用完毕请按医疗废弃物处理\n5. 操作人员需接受专业培训\n\n详细安全说明见《产品使用说明书》第3章。',
  '系统部署的基本流程是？': '标准部署流程（参考系统架构文档）：\n\n1. 环境确认 → 检查操作系统、数据库、依赖版本\n2. 获取安装包 → 从官方渠道下载对应版本\n3. 初始化配置 → 修改application.yml中的数据库与密钥配置\n4. 服务启动 → 执行启动脚本，观察日志确认无异常\n5. 功能验证 → 登录后检查核心模块可用性\n6. 接入监控 → 接入Prometheus/Grafana监控\n\n完整步骤见《系统部署指南V3.0》。'
}

const messages = ref([
  { role: 'assistant', content: '您好！我是智能文档助手。已为您加载「技术文档库」和「历史经验库」，您可以直接向我提问，或点击左侧快捷问题。', sources: [] }
])

const currentView = computed(() => (route.path === '/qa/library' ? 'library' : 'chat'))

function toggleKb(id) {
  const idx = selectedKb.value.indexOf(id)
  if (idx > -1) selectedKb.value.splice(idx, 1)
  else selectedKb.value.push(id)
}

async function sendQuestion(q) {
  const text = (typeof q === 'string' ? q : question.value).trim()
  if (!text) return
  if (selectedKb.value.length === 0) {
    ElMessage.info('请至少选择一个知识库')
    return
  }
  messages.value.push({ role: 'user', content: text, sources: [] })
  question.value = ''
  loading.value = true
  await nextTick()
  scrollToBottom()

  setTimeout(async () => {
    let answer = sampleAnswers[text] || ('根据' + selectedKb.value.join('、') + '知识库的内容，针对您的问题「' + text + '」，建议从以下几个方面分析：\n\n1. 明确问题的核心诉求\n2. 查阅对应章节的详细说明\n3. 结合实际场景进行判断\n\n如需更精确的回答，建议上传相关文档后再次提问。')
    let sources = ['技术文档库 - 产品规格说明.pdf', '历史经验库 - 常见问题汇编.docx']
    try {
      const resp = await qaAPI.askGeneral(text, selectedKb.value)
      if (resp.data) {
        if (resp.data.answer) answer = resp.data.answer
        if (resp.data.sources && Array.isArray(resp.data.sources)) sources = resp.data.sources
      }
    } catch (e) {
      // 使用示例答案
    }
    messages.value.push({ role: 'assistant', content: answer, sources: sources })
    loading.value = false
    await nextTick()
    scrollToBottom()
  }, 1000)
}

function scrollToBottom() {
  if (chatBox.value) {
    chatBox.value.scrollTop = chatBox.value.scrollHeight
  }
}
</script>

<style>
.qa-container { padding: 0; }

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 20px;
}

.qa-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 20px;
  min-height: 600px;
}

.knowledge-panel {
  background: #fff;
  border-radius: 10px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.panel-title {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.kb-item {
  display: flex;
  align-items: center;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 6px;
  transition: background 0.2s;
}

.kb-item:hover { background: #f5f7fa; }
.kb-item.active { background: #dbeafe; }

.kb-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 10px;
  flex-shrink: 0;
}

.kb-info { flex: 1; min-width: 0; }
.kb-name { font-size: 14px; font-weight: 500; color: #1f2937; }
.kb-desc { font-size: 12px; color: #6b7280; }

.quick-title {
  margin-top: 20px;
  font-weight: 600;
  color: #1f2937;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 10px;
}

.quick-item {
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 6px;
  color: #475569;
  font-size: 13px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.quick-item:hover { background: #3b82f6; color: #fff; }

.chat-panel {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background: #f8fafc;
  min-height: 500px;
  max-height: 600px;
}

.message {
  display: flex;
  margin-bottom: 20px;
  gap: 10px;
}

.message.user { flex-direction: row-reverse; }

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.avatar.user { background: #3b82f6; }
.avatar.assistant { background: #7c3aed; }

.bubble-wrap { max-width: 70%; }

.bubble {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.7;
  color: #374151;
  font-size: 14px;
  white-space: pre-wrap;
}

.message.user .bubble {
  background: #3b82f6;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .bubble {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-bottom-left-radius: 4px;
}

.sources {
  margin-top: 8px;
  padding: 10px 12px;
  background: #f1f5f9;
  border-radius: 8px;
  font-size: 12px;
}

.sources-title { color: #64748b; margin-bottom: 4px; font-weight: 500; }
.source-item { color: #475569; padding: 2px 0; }

.typing { color: #94a3b8; font-style: italic; }

.chat-input {
  display: flex;
  gap: 10px;
  padding: 16px;
  border-top: 1px solid #e5e7eb;
  background: #fff;
  align-items: flex-end;
}

.chat-input .el-textarea { flex: 1; }

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
  color: #1f2937;
}

@media (max-width: 900px) {
  .qa-layout { grid-template-columns: 1fr; }
}
</style>
