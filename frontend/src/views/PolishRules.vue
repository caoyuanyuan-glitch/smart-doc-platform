<template>
  <div class="rules-container">
    <div class="page-header">
      <h2>润色规则说明</h2>
      <p>以下为文档润色模块的核心检测规则。规则按优先级依次应用：术语替换 → 祈使句规范 → 数字单位空格 → 中英文空格 → 标点规范。</p>
    </div>

    <!-- Rule 1 -->
    <div class="rule-card">
      <div class="rule-header">
        <el-tag type="primary" size="large">规则 1</el-tag>
        <h3>术语替换（保守匹配）</h3>
        <el-tag size="small" type="info">保守匹配</el-tag>
      </div>
      <div class="rule-body">
        <p>只替换完整词且明确错误的非标准说法，避免误伤通用名词。</p>

        <el-table :data="termExamples" border size="small" class="rule-table">
          <el-table-column prop="level" label="级别" width="100" />
          <el-table-column prop="original" label="原文" width="150" />
          <el-table-column prop="replacement" label="替换为" width="150" />
          <el-table-column prop="rule" label="判定依据" />
        </el-table>

        <h4>不匹配的场景</h4>
        <ul>
          <li>"仪器" — 通用名词，非设备自称</li>
          <li>"本机" — 约定俗成用法，非错误术语</li>
          <li>"操作界面" — 标准技术用语</li>
        </ul>
      </div>
    </div>

    <!-- Rule 2 -->
    <div class="rule-card">
      <div class="rule-header">
        <el-tag type="success" size="large">规则 2</el-tag>
        <h3>祈使句规范</h3>
      </div>
      <div class="rule-body">
        <p>根据动词类型自动判断是否需要添加"请"字。</p>

        <el-table :data="imperativeSpec" border size="small" class="rule-table">
          <el-table-column prop="category" label="动词类型" width="120" />
          <el-table-column prop="verbs" label="示例" />
          <el-table-column prop="addQing" label='是否加"请"' width="100" />
          <el-table-column label="说明" width="220">
            <template #default="{ row }">
              <span v-if="row.addQing === '✅ 加'">建议类操作，加"请"表示礼貌</span>
              <span v-else-if="row.addQing === '❌ 不加'">操作类动作，直接陈述</span>
              <span v-else>警告用词已含否定祈使，保持原样</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="example-box">
          <div class="example-item">
            <span class="example-tag incorrect">修改前</span>
            <code>检查电源线是否连接正确</code>
          </div>
          <div class="example-item">
            <span class="example-tag correct">修改后</span>
            <code>请检查电源线是否连接正确</code>
          </div>
        </div>
      </div>
    </div>

    <!-- Rule 3 -->
    <div class="rule-card">
      <div class="rule-header">
        <el-tag type="warning" size="large">规则 3</el-tag>
        <h3>数字单位空格</h3>
      </div>
      <div class="rule-body">
        <p>数字与物理单位之间添加半角空格，符合 GB/T 3100 国际标准。</p>

        <el-table :data="numberSpaceExamples" border size="small" class="rule-table">
          <el-table-column prop="original" label="原文" width="150" />
          <el-table-column prop="replacement" label="修改后" width="180" />
          <el-table-column prop="note" label="说明" />
        </el-table>

        <h4>常见单位列表</h4>
        <div class="unit-tags">
          <el-tag v-for="u in commonUnits" :key="u" size="small" class="unit-tag">{{ u }}</el-tag>
        </div>
      </div>
    </div>

    <!-- Rule 4 -->
    <div class="rule-card">
      <div class="rule-header">
        <el-tag type="danger" size="large">规则 4</el-tag>
        <h3>中英文空格</h3>
      </div>
      <div class="rule-body">
        <p>中文与英文单词/缩写之间添加半角空格，提升可读性。</p>

        <el-table :data="cnEnSpaceExamples" border size="small" class="rule-table">
          <el-table-column prop="original" label="原文" width="220" />
          <el-table-column prop="replacement" label="修改后" width="220" />
        </el-table>

        <h4>例外情况</h4>
        <ul>
          <li>英文缩写与数字之间不加空格（如 V1.0、v2.3 保持不变）</li>
          <li>中文标点后的英文不加空格（如：这是AIO。→ 不加）</li>
          <li>已存在空格的保持不变</li>
        </ul>
      </div>
    </div>

    <!-- Rule 5 -->
    <div class="rule-card">
      <div class="rule-header">
        <el-tag size="large" style="background:#e6a23c;border-color:#e6a23c;color:#fff">规则 5</el-tag>
        <h3>标点规范</h3>
      </div>
      <div class="rule-body">
        <p>检查中文句子的标点完整性，确保每句话以合适的标点结尾。</p>

        <el-table :data="punctuationSpec" border size="small" class="rule-table">
          <el-table-column prop="check" label="检查项" width="160" />
          <el-table-column prop="rule" label="规则" />
          <el-table-column label="示例" width="300">
            <template #default="{ row }">
              <div class="example-line" v-if="row.original">
                <span class="example-tag incorrect">修改前</span>
                <code>{{ row.original }}</code>
              </div>
              <div class="example-line" v-if="row.replacement">
                <span class="example-tag correct">修改后</span>
                <code>{{ row.replacement }}</code>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="rule-card rule-note">
      <h4>执行顺序</h4>
      <p>规则按以下优先级依次应用，前一规则匹配成功后不再检查后续冲突规则：</p>
      <div class="priority-flow">
        <el-tag type="primary" size="large">术语替换</el-tag>
        <el-icon><ArrowRight /></el-icon>
        <el-tag type="success" size="large">祈使句规范</el-tag>
        <el-icon><ArrowRight /></el-icon>
        <el-tag type="warning" size="large">数字单位空格</el-tag>
        <el-icon><ArrowRight /></el-icon>
        <el-tag type="danger" size="large">中英文空格</el-tag>
        <el-icon><ArrowRight /></el-icon>
        <el-tag size="large" style="background:#e6a23c;color:#fff">标点规范</el-tag>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'

const termExamples = [
  { level: '高置信度', original: '试验台', replacement: '操作台', rule: '术语对照表 #12' },
  { level: '低置信度', original: '建库仪', replacement: '本仪器', rule: '自我指代需确认上下文' }
]

const imperativeSpec = [
  { category: '操作类', verbs: '点击、选择、输入、将、打开、关闭、放置', addQing: '❌ 不加' },
  { category: '建议类', verbs: '检查、确认、确保、避免、防止、联系', addQing: '✅ 加' },
  { category: '警告类', verbs: '严禁、禁止、请勿、不得', addQing: '保持原样' }
]

const numberSpaceExamples = [
  { original: '200μL', replacement: '200 μL', note: '数字与单位间用半角空格' },
  { original: '20℃', replacement: '20 ℃', note: '温度单位同样适用' },
  { original: '100rpm', replacement: '100 rpm', note: '转速单位' }
]

const commonUnits = ['μL', 'mL', 'L', 'mg', 'g', 'kg', 'mm', 'cm', 'm', '℃', 'rpm', 'V', 'A', 'W', 'Hz', 'Pa', 'N', 's', 'min', 'h']

const cnEnSpaceExamples = [
  { original: 'AIO基因', replacement: 'AIO 基因' },
  { original: 'DNBelab-D4RS测序', replacement: 'DNBelab-D4RS 测序' }
]

const punctuationSpec = [
  { check: '句尾缺标点', rule: '中文句尾应使用 。！？ 之一', original: '本仪器适用于实验室环境', replacement: '本仪器适用于实验室环境。' },
  { check: '条件句缺逗号', rule: '条件从句后加逗号', original: '如需修改密码可点击', replacement: '如需修改密码，可点击' }
]
</script>

<style scoped>
.rules-container {
  max-width: 900px;
  margin: 0 auto;
  padding-bottom: 40px;
}

.page-header {
  margin-bottom: 28px;
}

.page-header h2 {
  font-size: 22px;
  font-weight: 700;
  color: #1f2937;
  margin-bottom: 8px;
}

.page-header p {
  color: #6b7280;
  font-size: 14px;
  line-height: 1.7;
}

.rule-card {
  background: #fff;
  border-radius: 12px;
  padding: 24px 28px;
  margin-bottom: 20px;
  border: 1px solid #e5e7eb;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.rule-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.rule-header h3 {
  font-size: 17px;
  font-weight: 600;
  color: #1f2937;
}

.rule-body p {
  color: #4b5563;
  font-size: 14px;
  line-height: 1.7;
  margin-bottom: 16px;
}

.rule-body h4 {
  font-size: 14px;
  color: #374151;
  margin: 16px 0 8px;
}

.rule-body ul {
  margin: 0 0 12px;
  padding-left: 20px;
  color: #4b5563;
  font-size: 14px;
  line-height: 1.8;
}

.rule-table {
  margin-bottom: 12px;
}

.example-box {
  background: #f9fafb;
  border-radius: 8px;
  padding: 14px 18px;
  margin-top: 12px;
}

.example-item {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.example-item:last-child {
  margin-bottom: 0;
}

.example-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
  min-width: 52px;
  text-align: center;
}

.example-tag.incorrect {
  background: #fce8e6;
  color: #c5221f;
}

.example-tag.correct {
  background: #e6f4ea;
  color: #137333;
}

.example-item code {
  font-size: 13px;
  color: #374151;
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 3px;
}

.example-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.example-line:last-child {
  margin-bottom: 0;
}

.unit-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.unit-tag {
  font-family: monospace;
}

.rule-note {
  background: #f0f7ff;
  border-color: #bfdbfe;
}

.rule-note h4 {
  margin-top: 0;
}

.priority-flow {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.priority-flow .el-icon {
  color: #9ca3af;
  font-size: 18px;
}
</style>
