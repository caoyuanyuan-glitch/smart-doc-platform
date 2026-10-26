<template>
  <div class="compare-container">
    <h2 class="page-title">多文件一致性检查</h2>

    <div class="panel">
      <div class="panel-header">
        <span>上传基准文档和对比文档，填写要对比的参数名；不填则默认对比仪器尺寸、重量、环境温度/湿度/大气压、电源电压、额定功率、LCD尺寸、分辨率</span>
        <div class="panel-actions">
          <el-tag size="small" type="info">支持 Word / PDF / Excel</el-tag>
        </div>
      </div>

      <div class="upload-grid">
        <div class="upload-slot">
          <div class="slot-label">基准文档</div>
          <label class="upload-box" :class="{ filled: files[0] }">
            <input type="file" accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md" @change="pickFile(0, $event)" />
            <el-icon style="font-size:36px;color:#3b82f6;margin-bottom:8px;"><Upload /></el-icon>
            <div v-if="!files[0]" class="upload-hint">点击上传基准文档</div>
            <div v-else class="upload-name">{{ files[0].name }}</div>
          </label>
          <div class="slot-hint">对照标准，如旧版</div>
        </div>
        <div class="vs-col">
          <div class="slot-label vs-spacer-label" aria-hidden="true">&nbsp;</div>
          <div class="vs-badge">VS</div>
          <div class="slot-hint vs-spacer-hint" aria-hidden="true">&nbsp;</div>
        </div>
        <div class="upload-slot">
          <div class="slot-label">对比文档</div>
          <label class="upload-box" :class="{ filled: files[1] }">
            <input type="file" accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md" @change="pickFile(1, $event)" />
            <el-icon style="font-size:36px;color:#7c3aed;margin-bottom:8px;"><Upload /></el-icon>
            <div v-if="!files[1]" class="upload-hint">点击上传对比文档</div>
            <div v-else class="upload-name">{{ files[1].name }}</div>
          </label>
          <div class="slot-hint">要检查的版本，如新版</div>
        </div>
      </div>

      <div class="param-names-row">
        <div class="param-names-label">待对比参数</div>
        <el-select
          v-model="paramNames"
          multiple
          filterable
          allow-create
          placeholder="勾选或输入后按回车添加；留空则用默认规格项"
        >
          <el-option v-for="name in defaultParamNames" :key="name" :label="name" :value="name" />
        </el-select>
        <div class="param-names-hint">已选 {{ paramNames.length }} 项，开始对比时只检查这些参数</div>
      </div>

      <div class="action-row">
          <el-button type="primary" size="large" :loading="loading" :disabled="!files[0] || !files[1]" @click="doCompare">
            <el-icon><Search /></el-icon> 开始对比
          </el-button>
          <el-button size="large" @click="clearFiles">清空</el-button>
      </div>

      <div v-if="loading" class="progress-panel">
        <el-progress :percentage="progress" :stroke-width="6" :show-text="false" color="#3b82f6" />
        <div class="progress-text">{{ progressText }}</div>
      </div>
    </div>

    <div v-if="allResults.length > 0" class="result-panel">
      <div class="panel-header">
        <span>对比结果（{{ allResults.length }} 组）</span>
        <div class="panel-actions">
          <el-button size="small" type="primary" @click="exportReport">导出报告</el-button>
          <el-button size="small" @click="clearFiles">重新对比</el-button>
        </div>
      </div>

      <el-tabs v-model="activeTab" type="border-card" class="result-tabs">
        <el-tab-pane
          v-for="(r, ri) in allResults"
          :key="ri"
          :label="'对比 ' + (ri + 1) + ': ' + (r.file_b || '文档')"
          :name="ri"
        >
          <div class="pair-header">
            <div class="doc-info">
              <div>基准文档：{{ r.file_a }}</div>
              <div>对比文档：{{ r.file_b }}</div>
              <div>检查项：{{ (r.param_names && r.param_names.length ? r.param_names : paramNames).join('、') }}</div>
            </div>
            <div class="pair-tags">
              <el-tag type="success" size="small">一致: {{ r.match_count }}</el-tag>
              <el-tag type="danger" size="small">不一致: {{ r.diff_count }}</el-tag>
              <el-tag type="warning" size="small">建议优化: {{ suggestionCount(r) }}</el-tag>
            </div>
          </div>

          <div class="cards">
            <div class="card primary">
              <div class="num">{{ issueTotal(r) }}</div>
              <div class="lbl">合计</div>
            </div>
            <div class="card">
              <div class="num" style="color:#ef4444">{{ severeCount(r) }}</div>
              <div class="lbl">严重不一致</div>
            </div>
            <div class="card">
              <div class="num" style="color:#f59e0b">{{ suggestionCount(r) }}</div>
              <div class="lbl">建议优化</div>
            </div>
          </div>

          <h3 class="section-title">对比矩阵</h3>
          <div class="param-table-wrapper">
            <div class="custom-table-container">
              <table class="param-table">
                <thead>
                  <tr>
                    <th>检查项</th>
                    <th>{{ docLabel(r.file_a) }}</th>
                    <th>{{ docLabel(r.file_b) }}</th>
                    <th>是否一致</th>
                    <th>所在章节</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, idx) in paginateResults(foundRows(r), ri)"
                    :key="idx"
                  >
                    <td class="param-name-cell">{{ row.param }}</td>
                    <td class="value-cell">
                      <div v-if="isStructured(row.value_a) || isStructured(row.value_b)" class="struct-block">
                        <div v-if="structureParts(row.value_a).intro" class="struct-intro">
                          <template v-if="row.match === '不一致'">
                            <span
                              v-for="(seg, si) in valueDiff(structureParts(row.value_a).intro, structureParts(row.value_b).intro).left"
                              :key="'ai-' + idx + '-' + si"
                              :class="{ 'hl-diff': seg.diff }"
                            >{{ seg.text }}</span>
                          </template>
                          <template v-else>{{ structureParts(row.value_a).intro }}</template>
                        </div>
                        <table class="mini-struct">
                          <thead><tr><th>{{ structHeaders(row).name }}</th><th>{{ structHeaders(row).desc }}</th></tr></thead>
                          <tbody>
                            <tr v-for="(item, ii) in alignedStructRows(row)" :key="'ar-' + idx + '-' + ii">
                              <th>{{ item.name }}</th>
                              <td :class="{ 'cell-diff': item.diff && row.match === '不一致' }">{{ item.descA || '-' }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                      <template v-else-if="row.match === '不一致'">
                        <span
                          v-for="(seg, si) in valueDiff(row.value_a, row.value_b).left"
                          :key="'a-' + idx + '-' + si"
                          :class="{ 'hl-diff': seg.diff }"
                        >{{ seg.text }}</span>
                      </template>
                      <template v-else>{{ displayValue(row.value_a) }}</template>
                    </td>
                    <td class="value-cell">
                      <div v-if="isStructured(row.value_a) || isStructured(row.value_b)" class="struct-block">
                        <div v-if="structureParts(row.value_b).intro" class="struct-intro">
                          <template v-if="row.match === '不一致'">
                            <span
                              v-for="(seg, si) in valueDiff(structureParts(row.value_a).intro, structureParts(row.value_b).intro).right"
                              :key="'bi-' + idx + '-' + si"
                              :class="{ 'hl-diff': seg.diff }"
                            >{{ seg.text }}</span>
                          </template>
                          <template v-else>{{ structureParts(row.value_b).intro }}</template>
                        </div>
                        <table class="mini-struct">
                          <thead><tr><th>{{ structHeaders(row).name }}</th><th>{{ structHeaders(row).desc }}</th></tr></thead>
                          <tbody>
                            <tr v-for="(item, ii) in alignedStructRows(row)" :key="'br-' + idx + '-' + ii">
                              <th>{{ item.name }}</th>
                              <td :class="{ 'cell-diff': item.diff && row.match === '不一致' }">{{ item.descB || '-' }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                      <template v-else-if="row.match === '不一致'">
                        <span
                          v-for="(seg, si) in valueDiff(row.value_a, row.value_b).right"
                          :key="'b-' + idx + '-' + si"
                          :class="{ 'hl-diff': seg.diff }"
                        >{{ seg.text }}</span>
                      </template>
                      <template v-else>{{ displayValue(row.value_b) }}</template>
                    </td>
                    <td class="match-cell">
                      <el-tag
                        :type="row.match === '一致' ? 'success' : row.match === '不一致' ? 'danger' : row.match === '仅A有' ? 'warning' : 'info'"
                        size="small"
                      >
                        {{ matchLabel(row.match) }}
                      </el-tag>
                    </td>
                    <td class="source-cell">{{ chapterLabel(row) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="pagination-row" v-if="foundRows(r).length > pageSize">
              <el-pagination
                v-model:current-page="pages[ri]"
                :page-size="pageSize"
                :total="foundRows(r).length"
                layout="prev, pager, next, total"
                background
                small
              />
            </div>
            <div class="matrix-note">未找到的检查项未展示。</div>
          </div>

        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Search } from '@element-plus/icons-vue'
import { instance } from '@/api'

const files = ref([null, null])
const loading = ref(false)
const progress = ref(0)
const progressText = ref('')
const allResults = ref([])
const activeTab = ref(0)
const pageSize = ref(20)
const pages = reactive({})
const defaultParamNames = [
  '预期用途',
  '适用范围',
  '结构组成',
  '符合标准清单',
  '产品性能-技术指标',
  '仪器尺寸',
  '重量',
  '操作/运行环境温度',
  '湿度',
  '大气压',
  '电源电压',
  '额定功率',
  'LCD尺寸',
  '分辨率',
]
const paramNames = ref([...defaultParamNames])

function paginateResults(results, tabIdx) {
  if (!results) return []
  const start = ((pages[tabIdx] || 1) - 1) * pageSize.value
  if (pages[tabIdx] === undefined) pages[tabIdx] = 1
  return results.slice(start, start + pageSize.value)
}

function foundRows(r) {
  return (r.results || []).filter(row => {
    if (row.match === '缺失') return false
    return Boolean(String(row.value_a || '').trim() || String(row.value_b || '').trim())
  })
}

function displayValue(val) {
  const s = String(val || '').trim()
  return s || '-'
}

function structureParts(val) {
  const lines = String(val || '').split('\n').map(s => s.trim()).filter(Boolean)
  const intro = []
  const rows = []
  for (const line of lines) {
    if (line.includes(' | ')) {
      const i = line.indexOf(' | ')
      rows.push({ name: line.slice(0, i), desc: line.slice(i + 3) })
    } else if (!/^各部件功能说明如下[:：]?$/.test(line)) {
      intro.push(line)
    }
  }
  return { intro: intro.join('\n'), rows }
}

function isStructured(val) {
  return structureParts(val).rows.length >= 2
}

function structHeaders(row) {
  const name = String(row.param || '')
  if (name.includes('标准')) return { name: '标准号', desc: '内容' }
  return { name: '部件', desc: '功能' }
}

function alignedStructRows(row) {
  const a = structureParts(row.value_a).rows
  const b = structureParts(row.value_b).rows
  const names = []
  const seen = {}
  for (const item of a.concat(b)) {
    if (!seen[item.name]) {
      seen[item.name] = true
      names.push(item.name)
    }
  }
  const mapA = {}
  const mapB = {}
  for (const item of a) mapA[item.name] = item.desc
  for (const item of b) mapB[item.name] = item.desc
  return names.map(name => ({
    name,
    descA: mapA[name] || '',
    descB: mapB[name] || '',
    diff: (mapA[name] || '') !== (mapB[name] || ''),
  }))
}

function tokenizeValue(text) {
  const s = String(text || '')
  const tokens = []
  const re = /[A-Za-z0-9]+(?:[./\-_][A-Za-z0-9]+)*|[\u4e00-\u9fff]|./g
  let m
  while ((m = re.exec(s))) tokens.push(m[0])
  return tokens
}

function mergeDiffSegs(segs) {
  const out = []
  for (const seg of segs) {
    const last = out[out.length - 1]
    if (last && last.diff === seg.diff) last.text += seg.text
    else out.push({ text: seg.text, diff: seg.diff })
  }
  return out
}

function valueDiff(aRaw, bRaw) {
  const a = String(aRaw || '')
  const b = String(bRaw || '')
  if (!a && !b) {
    return {
      left: [{ text: '-', diff: false }],
      right: [{ text: '-', diff: false }],
    }
  }
  const ta = tokenizeValue(a)
  const tb = tokenizeValue(b)
  const n = ta.length
  const m = tb.length
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = ta[i] === tb[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const left = []
  const right = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (ta[i] === tb[j]) {
      left.push({ text: ta[i], diff: false })
      right.push({ text: tb[j], diff: false })
      i += 1
      j += 1
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      left.push({ text: ta[i], diff: true })
      i += 1
    } else {
      right.push({ text: tb[j], diff: true })
      j += 1
    }
  }
  while (i < n) {
    left.push({ text: ta[i], diff: true })
    i += 1
  }
  while (j < m) {
    right.push({ text: tb[j], diff: true })
    j += 1
  }
  return { left: mergeDiffSegs(left), right: mergeDiffSegs(right) }
}

function segsToHtml(segs) {
  if (!segs || !segs.length) return '-'
  return segs.map(seg => {
    const text = _esc(seg.text || '')
    return seg.diff ? '<span class="hl-diff">' + text + '</span>' : text
  }).join('')
}

function pickFile(idx, ev) {
  const f = ev.target.files && ev.target.files[0]
  if (f) files.value[idx] = f
  ev.target.value = ''
}

function clearFiles() {
  files.value = [null, null]
  allResults.value = []
  activeTab.value = 0
}

function updateProgress(pct, text) {
  return new Promise(resolve => {
    setTimeout(() => {
      progress.value = pct
      progressText.value = text
      resolve()
    }, 100)
  })
}

async function doCompare() {
  const validFiles = files.value.filter(f => f)
  if (validFiles.length < 2) {
    ElMessage.warning('请至少上传2个文档')
    return
  }

  loading.value = true
  allResults.value = []

  try {
    await updateProgress(10, '正在上传文件...')
    await updateProgress(25, '正在提取参数...')

    const formData = new FormData()
    validFiles.forEach(f => formData.append('files', f))
    formData.append('param_names', (paramNames.value || []).join(','))

    await updateProgress(50, '正在对比参数数值...')

    const resp = await instance.post('/compare/params/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    await updateProgress(90, '正在整理结果...')

    allResults.value = resp.data.results || []

    await updateProgress(100, '对比完成')
    ElMessage.success(`参数对比完成，共 ${allResults.value.length} 组结果`)

    setTimeout(() => {
      progress.value = 0
      progressText.value = ''
    }, 1500)
  } catch (e) {
    ElMessage.error('对比失败：' + (e.response?.data?.detail || e.message || '未知错误'))
    progress.value = 0
  } finally {
    loading.value = false
  }
}

function exportReport() {
  const results = allResults.value
  if (!results || results.length === 0) {
    ElMessage.warning('没有可导出的对比结果')
    return
  }

  const now = new Date().toLocaleString('zh-CN', { hour12: false })
  const rowsHtml = results.map((r, ri) => {
    const items = foundRows(r)
    const rows = items.map(row => {
      const matchClass = row.match === '一致' ? 'match-ok' : row.match === '不一致' ? 'match-diff' : 'match-only'
      const mismatched = row.match === '不一致'
      const segs = mismatched ? valueDiff(row.value_a, row.value_b) : null
      const htmlA = mismatched ? segsToHtml(segs.left) : _esc(displayValue(row.value_a))
      const htmlB = mismatched ? segsToHtml(segs.right) : _esc(displayValue(row.value_b))
      return '<tr>' +
        '<td class="param-name">' + _esc(row.param) + '</td>' +
        '<td>' + htmlA + '</td>' +
        '<td>' + htmlB + '</td>' +
        '<td><span class="tag ' + matchClass + '">' + _esc(matchLabel(row.match)) + '</span></td>' +
        '<td class="source-cell">' + _esc(chapterLabel(row)) + '</td>' +
        '</tr>'
    }).join('')

    const checkedNames = (r.param_names && r.param_names.length ? r.param_names : paramNames.value) || []
    return '<div class="pair-section">' +
      '<h2>1. 文档信息</h2>' +
      '<p>基准文档：' + _esc(r.file_a || '') + '</p>' +
      '<p>对比文档：' + _esc(r.file_b || '') + '</p>' +
      '<p>检查项：' + _esc(checkedNames.join('、')) + '</p>' +
      '<h2>2. 问题汇总</h2>' +
      '<div class="cards">' +
      '<div class="card"><div class="num" style="color:#ef4444">' + severeCount(r) + '</div><div class="lbl">严重不一致</div></div>' +
      '<div class="card"><div class="num" style="color:#f59e0b">' + suggestionCount(r) + '</div><div class="lbl">建议优化</div></div>' +
      '<div class="card primary"><div class="num">' + issueTotal(r) + '</div><div class="lbl">合计</div></div>' +
      '</div>' +
      '<h2>3. 对比矩阵</h2>' +
      '<table class="param-table">' +
      '<thead><tr>' +
      '<th>检查项</th>' +
      '<th>' + _esc(docLabel(r.file_a)) + '</th>' +
      '<th>' + _esc(docLabel(r.file_b)) + '</th>' +
      '<th>是否一致</th>' +
      '<th>所在章节</th>' +
      '</tr></thead>' +
      '<tbody>' + rows + '</tbody>' +
      '</table>' +
      '<p class="matrix-note">未找到的检查项未展示。</p>' +
      '<h2>4. 审核结论</h2>' +
      '<p>结论：' + (issueTotal(r) ? '需修改后复审' : '通过') + '</p>' +
      '</div>'
  }).join('')

  const htmlContent = '<!DOCTYPE html>\n' +
    '<html lang="zh-CN">\n' +
    '<head>\n' +
    '<meta charset="UTF-8">\n' +
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n' +
    '<title>多文件一致性审核报告</title>\n' +
    '<style>\n' +
    'body{font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#1a1a1a}\n' +
    '.wrap{max-width:1180px;margin:0 auto;padding:32px 24px}\n' +
    'h1{font-size:26px;margin:0 0 4px}\n' +
    '.meta{color:#666;font-size:13px;margin-bottom:24px}\n' +
    '.cards{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px}\n' +
    '.card{background:#fff;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px}\n' +
    '.card.primary{background:linear-gradient(135deg,#1976d2,#2c3e50);color:#fff;min-width:180px}\n' +
    '.card.primary .lbl{color:rgba(255,255,255,.85)}\n' +
    '.card.primary .num{font-size:32px}\n' +
    '.card .num{font-size:28px;font-weight:700}\n' +
    '.card .lbl{color:#777;font-size:13px;margin-top:4px}\n' +
    '.pair-section{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:24px;margin-bottom:24px}\n' +
    '.pair-section h2{font-size:18px;margin:0 0 20px;color:#1f2937}\n' +
    '.param-table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}\n' +
    '.param-table thead{position:sticky;top:0;z-index:10}\n' +
    '.param-table th{background:#f5f7fa;color:#303133;font-weight:600;font-size:13px;padding:12px 10px;text-align:left;border-bottom:2px solid #dcdfe6;white-space:nowrap}\n' +
    '.param-table td{padding:10px;border-bottom:1px solid #ebeef5;color:#303133;vertical-align:top;white-space:pre-wrap;word-break:break-word}\n' +
    '.param-table tbody tr:hover{background:#f5f7fa}\n' +
    '.param-name{font-weight:600;color:#1f2937;white-space:nowrap}\n' +
    '.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600}\n' +
    '.tag.match-ok{background:#f0fdf4;color:#16a34a}\n' +
    '.tag.match-diff{background:#fef2f2;color:#dc2626}\n' +
    '.tag.match-only{background:#fffbeb;color:#d97706}\n' +
    '.tag.tag-info{background:#eff6ff;color:#3b82f6}\n' +
    '.tag.tag-ok{background:#f0fdf4;color:#16a34a}\n' +
    '.fuzzy-cell{text-align:center;font-size:12px}\n' +
    '.source-cell{font-size:12px;color:#606266;white-space:nowrap}\n' +
    '.text-muted{color:#c0c4cc}\n' +
    '.matched-name{font-size:11px;color:#909399;margin-top:2px}\n' +
    '.hl-diff{background:#fecaca;color:#991b1b;border-radius:2px}\n' +
    '.matrix-note{margin:12px 0 0;font-size:12px;color:#6b7280}\n' +
    '@media print{.wrap{max-width:100%}}\n' +
    '</style>\n' +
    '</head>\n' +
    '<body>\n' +
    '<div class="wrap">\n' +
    '<h1>多文件一致性审核报告</h1>\n' +
    '<div class="meta">生成时间: ' + now + ' | 对比组数: ' + results.length + '</div>\n' +
    rowsHtml +
    '\n</div>\n' +
    '</body>\n' +
    '</html>'

  const blob = new Blob([htmlContent], { type: 'text/html;charset=UTF-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '多文件一致性审核报告_' + new Date().toISOString().slice(0, 10) + '.html'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success('报告已导出')
}

function _esc(str) {
  if (!str) return ''
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function docLabel(name) {
  const s = String(name || '').trim()
  if (!s) return '文档'
  return s.replace(/\.(pdf|docx?|xlsx?|txt|md)$/i, '')
}

function isSuggestionItem(param) {
  return /带宽|格式|单位/.test(param || '')
}

function diffRows(r) {
  return (r.results || []).filter(row => row.match === '不一致')
}

function severeCount(r) {
  return diffRows(r).filter(row => !isSuggestionItem(row.param)).length
}

function suggestionCount(r) {
  return diffRows(r).filter(row => isSuggestionItem(row.param)).length
}

function issueTotal(r) {
  return severeCount(r) + suggestionCount(r)
}

function chapterLabel(row) {
  const a = (row.chapter_a || '').trim()
  const b = (row.chapter_b || '').trim()
  if (!a && !b) return '-'
  if (a && b && a === b) return a
  if (a && b) return a + ' / ' + b
  return a || b
}

function matchLabel(match) {
  if (match === '一致') return '是'
  if (match === '不一致') return '否'
  return '-'
}
</script>

<style scoped>
.compare-container { padding: 0; }

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 20px;
}

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.05);
}

.result-panel {
  background: #fff;
  border-radius: 10px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,.08);
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

.panel-actions { display: flex; align-items: center; gap: 10px; }

.upload-grid {
  display: flex;
  justify-content: center;
  align-items: stretch;
  gap: 16px;
}

.upload-slot,
.vs-col {
  width: 240px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.vs-col {
  width: 64px;
}

.slot-label {
  font-weight: 600;
  color: #374151;
  text-align: center;
  width: 240px;
  line-height: 22px;
  margin-bottom: 10px;
}

.slot-hint {
  margin-top: 10px;
  font-weight: 400;
  font-size: 12px;
  color: #6b7280;
  text-align: center;
  width: 240px;
  line-height: 18px;
}

.vs-spacer-label,
.vs-spacer-hint {
  visibility: hidden;
}

.upload-box {
  position: relative;
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 30px 16px;
  text-align: center;
  cursor: pointer;
  transition: all .3s;
  width: 240px;
  min-height: 160px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.upload-box input[type="file"] {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.upload-box:hover { border-color: #3b82f6; background: #eff6ff; }

.upload-box.filled { border-color: #3b82f6; background: #f0f9ff; }

.upload-hint { color: #6b7280; font-size: 14px; }

.upload-name { color: #3b82f6; font-weight: 600; font-size: 14px; }

.vs-badge {
  flex: 1;
  font-size: 20px;
  font-weight: 700;
  color: #9ca3af;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
}

.vs-spacer {
  width: 80px;
}

.param-names-row {
  max-width: 720px;
  margin: 20px auto 0;
}

.param-names-label {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
}

.param-names-row :deep(.el-select) {
  width: 100%;
}

.param-names-row :deep(.el-select__wrapper) {
  min-height: 42px;
  height: auto;
  align-items: flex-start;
}

.param-names-row :deep(.el-select__selection) {
  flex-wrap: wrap;
}

.param-names-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #6b7280;
}

.action-row {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 24px;
}

.progress-panel {
  max-width: 240px;
  margin: 16px auto 0;
  padding: 0;
}

.progress-text {
  text-align: center;
  margin-top: 6px;
  color: #6b7280;
  font-size: 12px;
}

.result-tabs { margin-top: 16px; }

.pair-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 6px;
}

.doc-info {
  font-size: 14px;
  color: #1f2937;
  line-height: 1.7;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  margin: 8px 0 12px;
}

.issue-list {
  margin-bottom: 20px;
}

.issue-block {
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
  font-size: 13px;
  color: #374151;
  line-height: 1.7;
}

.issue-title {
  font-weight: 600;
  color: #9a3412;
  margin-bottom: 6px;
}

.issue-line {
  margin-top: 4px;
}

.issue-indent {
  padding-left: 1.5em;
  color: #4b5563;
}

.pair-label {
  font-size: 15px;
  color: #1f2937;
}

.pair-label strong { color: #3b82f6; margin: 0 8px; }

.pair-tags { display: flex; gap: 8px; }

.cards { display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px; }
.card { background:#fff;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px; }
.card.primary { background:linear-gradient(135deg,#1976d2,#2c3e50);color:#fff;min-width:180px; }
.card.primary .lbl { color:rgba(255,255,255,.85); }
.card.primary .num { font-size:32px; }
.card .num { font-size:24px;font-weight:700; }
.card .lbl { color:#777;font-size:12px;margin-top:4px; }

.param-table-wrapper {
  margin-top: 8px;
}

.custom-table-container {
  overflow-x: auto;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
}

.param-table {
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;
  background: #fff;
  font-size: 13px;
}

.param-table thead {
  position: sticky;
  top: 0;
  z-index: 10;
}

.param-table th {
  background: #f5f7fa;
  color: #303133;
  font-weight: 600;
  font-size: 13px;
  padding: 12px 10px;
  text-align: left;
  border-bottom: 2px solid #dcdfe6;
  white-space: nowrap;
}

.param-table td {
  padding: 10px;
  border-bottom: 1px solid #ebeef5;
  color: #303133;
  vertical-align: top;
}

.param-table tbody tr:hover {
  background: #f5f7fa;
}

.param-name-cell {
  font-weight: 600;
  color: #1f2937;
  white-space: nowrap;
}

.match-cell {
  text-align: center;
  white-space: nowrap;
}

.fuzzy-cell {
  text-align: center;
  font-size: 12px;
}

.source-cell {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}

.value-cell {
  white-space: pre-wrap;
  word-break: break-word;
  max-width: 420px;
  line-height: 1.65;
}

.struct-block {
  white-space: normal;
}

.struct-intro {
  margin-bottom: 8px;
}

.mini-struct {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.mini-struct th,
.mini-struct td {
  border: 1px solid #e5e7eb;
  padding: 6px 8px;
  vertical-align: top;
  text-align: left;
}

.mini-struct thead th {
  background: #f8fafc;
  font-weight: 600;
  white-space: nowrap;
}

.mini-struct tbody th {
  width: 72px;
  font-weight: 600;
  color: #374151;
  background: #fafafa;
  white-space: nowrap;
}

.cell-diff {
  background: #fecaca;
  color: #991b1b;
}

.hl-diff {
  background: #fecaca;
  color: #991b1b;
  border-radius: 2px;
}

.matrix-note {
  margin-top: 12px;
  font-size: 12px;
  color: #6b7280;
}

.text-muted {
  color: #c0c4cc;
}

.matched-name {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}

.pagination-row {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.debug-text {
  background: #f5f5f5;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  max-height: 400px;
  overflow-y: auto;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
  color: #374151;
}
</style>
