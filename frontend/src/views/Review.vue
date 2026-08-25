<template>
  <div class="review-container">
    <!-- 开始审核 -->
    <div v-if="currentView === 'documents'">
      <h2 class="page-title">开始审核</h2>
      <el-tabs v-model="reviewSubTab" class="review-subtabs">
        <el-tab-pane label="单文档审核" name="single">
          <div class="upload-section">
            <el-upload
              class="upload-demo"
              :http-request="uploadDocument"
              :before-upload="beforeUpload"
              accept=".pdf,.docx,.xlsx,.xls,.md,.zip,.txt,.idml"
              :auto-upload="true"
              :show-file-list="false"
            >
              <el-button type="primary">上传文档</el-button>
              <template #tip>
                <div class="upload-tip">支持 PDF、DOCX、Excel、MD、TXT、IDML 格式，单文件最大 50MB</div>
              </template>
            </el-upload>
            <div class="review-mode-toolbar">
              <span class="review-mode-label">审核模式</span>
              <el-radio-group v-model="reviewMode" size="small">
                <el-radio-button label="rule">快速审核</el-radio-button>
                <el-radio-button label="hybrid">完整审核</el-radio-button>
              </el-radio-group>
              <span class="review-mode-hint">
                {{ reviewMode === 'rule' ? '只检查规则问题，速度快。' : '规则问题 + AI 深度检查，结果更全。' }}
              </span>
            </div>
            <div v-if="reviewMode === 'hybrid'" class="review-mode-toolbar ai-model-toolbar">
              <span class="review-mode-label">AI 模型</span>
              <el-select
                v-model="selectedProvider"
                size="small"
                style="width: 280px"
                :disabled="providerLoading"
                placeholder="选择模型"
              >
                <el-option
                  v-for="m in availableModels"
                  :key="m.name"
                  :label="m.label"
                  :value="m.name"
                />
              </el-select>
              <span v-if="providerLoading" class="review-mode-hint">正在检测可用模型...</span>
              <span v-else-if="availableModels.length === 0" class="review-mode-hint" style="color: #e6a23c">
                未检测到可用 AI 模型，请检查 API Key 配置
              </span>
              <span v-else class="review-mode-hint">
                {{ `当前使用 ${selectedProviderLabel}` }}
              </span>
            </div>
            <div v-if="uploadProgress > 0 && uploadProgress < 100" class="progress-section">
              <el-progress :percentage="uploadProgress" :stroke-width="4" />
              <span class="progress-text">{{ uploadProgressText }}</span>
            </div>
          </div>

          <div class="table-section">
            <h3>文档列表</h3>
            <el-table :data="documents" border>
              <el-table-column prop="id" label="ID" width="80" />
              <el-table-column prop="filename" label="文件名" />
              <el-table-column prop="file_type" label="类型" width="100" />
              <el-table-column prop="file_size" label="大小" width="100">
                <template #default="scope">
                  {{ formatSize(scope.row.file_size) }}
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="上传时间" width="180" />
              <el-table-column label="审核状态" width="200">
                <template #default="scope">
                  <div v-if="docReviewStatus[scope.row.id]">
                    <el-progress
                      v-if="docReviewStatus[scope.row.id].progress < 100"
                      :percentage="docReviewStatus[scope.row.id].progress"
                      :text-inside="true"
                      :stroke-width="18"
                      :status="docReviewStatus[scope.row.id].status === 'failed' ? 'exception' : ''"
                    />
                    <span style="font-size:12px;color:#666">{{ reviewStatusText(docReviewStatus[scope.row.id]) }}</span>
                  </div>
                  <span v-else style="color:#999">未审核</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="260">
                <template #default="scope">
                  <el-button
                    size="small"
                    :disabled="!canStartReview(scope.row)"
                    @click="startReview(scope.row.id)"
                  >
                    {{ docReviewStatus[scope.row.id]?.status === 'running' ? '审核中...' : '开始审核' }}
                  </el-button>
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    :disabled="!docReviewStatus[scope.row.id]?.review_id || docReviewStatus[scope.row.id]?.status !== 'completed'"
                    @click="goReviewTasks"
                  >
                    去历史任务处理
                  </el-button>
                  <el-button size="small" type="danger" @click="deleteDocument(scope.row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <el-tab-pane label="对比审核" name="compare">
          <div class="upload-section compare-audit-section">
            <div class="compare-upload-grid">
              <div class="compare-upload-card">
                <div class="compare-upload-title">主文档</div>
                <el-upload
                  :auto-upload="false"
                  :show-file-list="true"
                  :limit="1"
                  accept=".pdf,.docx,.xlsx,.xls,.md,.zip,.txt,.idml"
                  :on-change="handleCompareMainChange"
                  :on-remove="clearCompareMainFile"
                  :file-list="compareMainFileList"
                >
                  <el-button type="primary" plain>上传主文档</el-button>
                </el-upload>
                <div class="upload-tip">用于产出最终对比审核结果</div>
              </div>

              <div class="compare-upload-card">
                <div class="compare-upload-title">参考文件</div>
                <el-upload
                  :auto-upload="false"
                  :show-file-list="true"
                  multiple
                  accept=".pdf,.docx,.xlsx,.xls,.md,.zip,.txt,.idml"
                  :on-change="handleCompareReferenceChange"
                  :on-remove="handleCompareReferenceRemove"
                  :file-list="compareReferenceFileList"
                >
                  <el-button type="primary" plain>上传参考文件</el-button>
                </el-upload>
                <div class="upload-tip">至少上传 1 个参考文件；仅检查白名单核心参数与主干流程</div>
              </div>
            </div>

            <div class="review-mode-toolbar compare-mode-toolbar">
              <span class="review-mode-label">对比模式</span>
              <el-radio-group v-model="compareMode" size="small">
                <el-radio-button label="both">核心参数 + 主干流程</el-radio-button>
              </el-radio-group>
              <span class="review-mode-hint">按属性-值方式识别参数，一致项默认折叠。</span>
            </div>

            <div class="compare-action-row">
              <el-button type="primary" :loading="compareSubmitting" @click="startCompareAudit">开始对比审核</el-button>
            </div>
          </div>

          <div v-if="compareResult" class="report-section compare-result-section">
            <h3>对比审核结果</h3>
            <div class="compare-summary-grid">
              <div class="compare-summary-card">
                <div class="gold-label">主文档</div>
                <div class="compare-summary-name">{{ compareResult.main_document?.filename || '-' }}</div>
              </div>
              <div class="compare-summary-card">
                <div class="gold-label">参考文件数</div>
                <div class="gold-value">{{ compareResult.summary?.reference_count || 0 }}</div>
              </div>
              <div class="compare-summary-card">
                <div class="gold-label">P0 / P1</div>
                <div class="gold-value">{{ (compareResult.summary?.p0_count || 0) }} / {{ (compareResult.summary?.p1_count || 0) }}</div>
              </div>
              <div class="compare-summary-card">
                <div class="gold-label">P2 / 一致</div>
                <div class="gold-value">{{ (compareResult.summary?.p2_count || 0) }} / {{ (compareResult.summary?.match_count || 0) }}</div>
              </div>
            </div>

            <div class="compare-result-toolbar">
              <div class="compare-result-toolbar-text">
                当前默认只展示差异项，便于直接处理高优先级问题。
              </div>
              <el-switch v-model="showCompareConsistent" active-text="显示一致项" inactive-text="隐藏一致项" />
            </div>

            <div class="compare-result-block">
              <h4>核心参数差异明细表</h4>
              <div class="compare-table-wrap">
                <el-table :data="visibleCompareRows" border style="width: 100%" :fit="false" class="compare-diff-table">
                  <el-table-column prop="dimension" label="检查维度" width="120" fixed="left" />
                  <el-table-column prop="parameter_name" label="参数名称" width="180" fixed="left" />
                  <el-table-column label="主文档（说明书）内容" width="320" show-overflow-tooltip fixed="left">
                    <template #default="scope">
                      <span class="compare-main-value" v-html="renderCompareMainValue(scope.row)"></span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    v-for="(column, index) in compareReferenceColumns"
                    :key="`${column.filename || 'reference'}-${index}`"
                    :label="column.filename || `参考文件${index + 1}`"
                    width="240"
                    show-overflow-tooltip
                  >
                    <template #default="scope">
                      <span>{{ renderCompareReferenceValue(scope.row, index) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="异常说明 / 差异结论" width="320">
                    <template #default="scope">
                      <div class="compare-conclusion-cell">
                        <el-tag size="small" :type="compareLevelTagType(scope.row.level)">{{ scope.row.level }}</el-tag>
                        <span>{{ scope.row.conclusion }}</span>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>

            <el-empty
              v-if="!visibleCompareRows.length"
              description="当前筛选条件下没有可展示的差异项"
            />

            <div v-if="compareResult.review_id" class="report-actions">
              <el-button type="primary" plain @click="exportReviewHtml(compareResult.review_id)">HTML报告</el-button>
              <el-button @click="goReviewTasks">查看历史任务</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 历史审核任务 - 行内展开显示报告 -->
    <div v-if="currentView === 'tasks'">
      <h2 class="page-title">历史审核任务</h2>
      <div class="table-section">
          <el-table :data="reviews" border>
          <!-- 问题详情已迁移到下方弹窗 (openIssueDialog) -->
          <el-table-column prop="id" label="任务ID" width="80" />
          <el-table-column prop="document_name" label="文档名" min-width="200" show-overflow-tooltip />
          <el-table-column label="模式" width="140">
            <template #default="scope">
              {{ reviewModeLabel(scope.row.mode) }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90">
            <template #default="scope">
              <el-tag :type="scope.row.status === 'completed' ? 'success' : scope.row.status === 'failed' ? 'danger' : 'info'">
                {{ scope.row.status === 'completed' ? '已完成' : scope.row.status === 'failed' ? '失败' : '进行中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" min-width="220">
            <template #default="scope">
              <div v-if="scope.row.status === 'running' && scope.row.progress">
                <el-progress :percentage="scope.row.progress.progress || 0" :stroke-width="16" />
                <div class="task-progress-text">{{ reviewProgressText(scope.row.progress) }}</div>
              </div>
              <span v-else-if="scope.row.status === 'completed'">审核完成</span>
              <span v-else-if="scope.row.status === 'failed'">{{ reviewFailureText(scope.row) }}</span>
              <span v-else style="color:#999">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="total_issues" label="问题数" width="100" />
          <el-table-column label="判定状态" width="180">
            <template #default="scope">
              <span v-if="judgmentStats[scope.row.id]">
                <el-tag type="success" size="small" effect="plain" style="margin-right:4px">已确认 {{ judgmentStats[scope.row.id].confirmed }}</el-tag>
                <el-tag type="info" size="small" effect="plain" style="margin-right:4px">误报 {{ judgmentStats[scope.row.id].false_positive }}</el-tag>
                <el-tag type="warning" size="small" effect="plain" style="margin-right:4px">补充 {{ judgmentStats[scope.row.id].manual }}</el-tag>
                <el-tag type="warning" size="small" effect="plain">待审 {{ judgmentStats[scope.row.id].pending }}</el-tag>
              </span>
              <span v-else style="color:#999">-</span>
            </template>
          </el-table-column>
          <el-table-column label="开始时间" width="180">
            <template #default="scope">
              {{ formatDateTime(scope.row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="360" fixed="right">
            <template #default="scope">
              <el-button 
                size="small" 
                type="primary" 
                :disabled="scope.row.status !== 'completed'"
                @click="openIssueDialog(scope.row)"
              >
                查看问题
              </el-button>
              <el-button 
                size="small" 
                :disabled="scope.row.status !== 'completed'"
                @click="batchConfirmAll(scope.row.id)"
              >
                一键确认
              </el-button>
              <el-button
                v-if="shouldShowDownloadResult(scope.row)"
                size="small"
                type="success"
                :disabled="scope.row.status !== 'completed'"
                @click="downloadReviewResult(scope.row)"
              >
                {{ resultButtonLabel(scope.row.document_file_type) }}
              </el-button>
              <el-button 
                size="small" 
                type="success" 
                plain
                :disabled="scope.row.status !== 'completed'"
                @click="exportReviewHtml(scope.row.id)"
              >
                HTML报告
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 问题详情弹窗 -->
    <el-dialog v-model="issueDialogVisible" :title="`问题详情 - 任务#${currentTaskId}`" width="95%" top="5vh">
      <div class="issue-dialog-toolbar">
        <el-input v-model="issueFilter.keyword" placeholder="搜索原文/上下文/建议" style="width:300px" clearable />
        <el-select v-model="issueFilter.category" placeholder="分类" clearable style="width:140px;margin-left:8px">
          <el-option v-for="cat in dialogCategories" :key="cat" :label="cat" :value="cat" />
        </el-select>
          <el-select v-model="issueFilter.status" placeholder="状态" clearable style="width:120px;margin-left:8px">
          <el-option label="待确认" value="pending" />
          <el-option label="已确认" value="confirmed" />
          <el-option label="误报" value="false_positive" />
        </el-select>
        <el-select v-model="issueFilter.severity" placeholder="严重度" clearable style="width:120px;margin-left:8px">
          <el-option label="致命" value="fatal" />
          <el-option label="严重" value="serious" />
          <el-option label="一般" value="general" />
          <el-option label="建议" value="suggestion" />
        </el-select>
        <el-button size="small" type="info" plain style="margin-left:8px" @click="showAuditTraces = !showAuditTraces">
          {{ showAuditTraces ? '隐藏AI追踪' : 'AI调用追踪' }}
          <el-badge v-if="auditTraces.length > 0 && !showAuditTraces" :value="auditTraces.length" class="trace-badge" />
        </el-button>
        <span style="margin-left:auto">
          <el-button size="small" type="warning" plain @click="openManualIssueDialog">补充上报</el-button>
          <el-button size="small" type="success" plain :disabled="!currentTaskId" @click="batchConfirmAll(currentTaskId)">确认全部待审</el-button>
          <el-button size="small" @click="batchSetStatus('confirmed')">批量确认</el-button>
          <el-button size="small" @click="batchSetStatus('false_positive')">批量标记误报</el-button>
        </span>
      </div>

      <!-- AI调用追踪面板 -->
      <el-card v-if="showAuditTraces" class="audit-trace-panel" shadow="never">
        <template #header>
          <div class="trace-panel-header">
            <span>AI审核调用追踪</span>
            <el-tag size="small" type="info">{{ auditTraces.length }} 次调用</el-tag>
            <span v-if="auditTraces.length > 0" style="margin-left:12px;font-size:12px;color:#888">
              总Token: {{ totalTraceTokens.toLocaleString() }} | 
              总延迟: {{ totalTraceLatency }}ms | 
              Provider: {{ traceProviders.join(', ') }}
            </span>
          </div>
        </template>
        <div v-if="auditTraces.length === 0" style="text-align:center;color:#999;padding:20px">
          暂无AI调用记录（可能为纯规则审核或审核尚未完成）
        </div>
        <el-table v-else :data="auditTraces" border size="small" max-height="300">
          <el-table-column prop="chunk_index" label="分块" width="70" />
          <el-table-column prop="chunk_size" label="块大小" width="90">
            <template #default="scope">
              {{ scope.row.chunk_size ? scope.row.chunk_size.toLocaleString() : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="provider" label="Provider" width="100">
            <template #default="scope">
              <el-tag size="small" :type="providerTagType(scope.row.provider)">{{ scope.row.provider }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="model" label="模型" min-width="140" show-overflow-tooltip />
          <el-table-column label="Token" width="140">
            <template #default="scope">
              <span style="font-size:12px">
                P:{{ scope.row.prompt_tokens?.toLocaleString() || 0 }}
                C:{{ scope.row.completion_tokens?.toLocaleString() || 0 }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="total_tokens" label="总计" width="80">
            <template #default="scope">
              {{ scope.row.total_tokens?.toLocaleString() || 0 }}
            </template>
          </el-table-column>
          <el-table-column label="延迟" width="90">
            <template #default="scope">
              <span :style="{ color: scope.row.latency_ms > 30000 ? '#f56c6c' : '#67c23a' }">
                {{ formatLatency(scope.row.latency_ms) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90">
            <template #default="scope">
              <el-tag size="small" :type="traceStatusTagType(scope.row.status)">
                {{ traceStatusLabel(scope.row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="parsed_issue_count" label="检出" width="70" />
          <el-table-column prop="error_message" label="备注" min-width="120" show-overflow-tooltip>
            <template #default="scope">
              <span v-if="scope.row.error_message" style="color:#f56c6c;font-size:12px">{{ scope.row.error_message }}</span>
              <span v-else style="color:#ccc">-</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 审核覆盖率统计 -->
      <el-card v-if="coverageData" class="coverage-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>审核覆盖率统计</span>
            <el-tag :type="coverageQualityType(coverageData.quality_score)" size="small" effect="dark">
              质量评分 {{ coverageData.quality_score }}
            </el-tag>
            <el-button size="small" type="text" style="margin-left:8px" @click="showCoverage = !showCoverage">
              {{ showCoverage ? '收起' : '展开详情' }}
            </el-button>
          </div>
        </template>
        <!-- 概要 -->
        <div class="coverage-summary">
          <div class="coverage-item">
            <span class="coverage-label">检出问题</span>
            <span class="coverage-value">{{ coverageData.total_issues }}</span>
          </div>
          <div class="coverage-item">
            <span class="coverage-label">规则覆盖</span>
            <span class="coverage-value">{{ coverageData.rules_triggered }}/{{ coverageData.total_available_rules }} ({{ coverageData.rule_coverage_pct }}%)</span>
          </div>
          <div class="coverage-item">
            <span class="coverage-label">AI调用</span>
            <span class="coverage-value">{{ coverageData.ai_stats?.total_traces || 0 }} 次</span>
          </div>
          <div class="coverage-item">
            <span class="coverage-label">Token消耗</span>
            <span class="coverage-value">{{ (coverageData.ai_stats?.total_tokens || 0).toLocaleString() }}</span>
          </div>
        </div>

        <!-- 详情 -->
        <div v-if="showCoverage" class="coverage-detail">
          <!-- 严重度分布 -->
          <div class="coverage-section">
            <h4>严重度分布</h4>
            <div class="severity-bars">
              <div v-for="(count, sev) in coverageData.severity_distribution" :key="sev" class="severity-bar-row">
                <span class="severity-bar-label">{{ severityLabelCN(sev) }}</span>
                <el-progress
                  :percentage="Math.round(count / coverageData.total_issues * 100)"
                  :color="severityColor(sev)"
                  :stroke-width="18"
                  style="flex:1; margin: 0 12px"
                >
                  <span style="font-size:12px">{{ count }}</span>
                </el-progress>
              </div>
            </div>
          </div>

          <!-- 类别分布 -->
          <div class="coverage-section" v-if="Object.keys(coverageData.category_distribution || {}).length > 0">
            <h4>问题类别分布</h4>
            <div style="display:flex;flex-wrap:wrap;gap:8px">
              <el-tag
                v-for="(count, cat) in coverageData.category_distribution"
                :key="cat"
                size="small"
                :type="cat === '术语' ? 'danger' : cat === '合规' ? 'warning' : 'info'"
              >
                {{ cat }}: {{ count }}
              </el-tag>
            </div>
          </div>

          <!-- Top 规则命中 -->
          <div class="coverage-section" v-if="Object.keys(coverageData.rule_hits || {}).length > 0">
            <h4>规则命中 Top 10</h4>
            <div style="display:flex;flex-direction:column;gap:4px;font-size:12px">
              <div v-for="(count, rule, idx) in Object.entries(coverageData.rule_hits).slice(0,10)" :key="rule" style="display:flex;align-items:center">
                <span style="width:24px;color:#999">{{ idx + 1 }}</span>
                <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ rule }}</span>
                <el-tag size="small" type="primary">{{ count }}次</el-tag>
              </div>
            </div>
          </div>

          <!-- AI统计 -->
          <div class="coverage-section" v-if="coverageData.ai_stats?.total_traces > 0">
            <h4>AI调用统计</h4>
            <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px">
              <span>总Token: <b>{{ (coverageData.ai_stats.total_tokens || 0).toLocaleString() }}</b></span>
              <span>总延迟: <b>{{ formatLatency(coverageData.ai_stats.total_latency_ms) }}</b></span>
              <span>平均延迟: <b>{{ formatLatency(coverageData.ai_stats.avg_latency_ms) }}</b></span>
              <span v-if="coverageData.ai_stats.provider_distribution">
                Provider: 
                <el-tag v-for="(c, p) in coverageData.ai_stats.provider_distribution" :key="p" size="small" style="margin-left:4px">
                  {{ p }} ×{{ c }}
                </el-tag>
              </span>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 术语匹配率分析面板 -->
      <el-card v-if="terminologyData" class="terminology-card" shadow="hover" style="margin-bottom:12px">
        <template #header>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <span style="font-weight:600">术语库匹配率分析</span>
              <el-tag :type="terminologyQualityType(terminologyData.summary?.quality_score)" size="small" effect="dark" style="margin-left:8px">
                {{ terminologyData.summary?.quality_score || 0 }} 分
              </el-tag>
            </div>
            <div>
              <el-button size="small" @click="terminologyData = null" circle>✕</el-button>
            </div>
          </div>
        </template>

        <div v-if="terminologyData.distribution" class="match-distribution">
          <div class="dist-title">匹配率分布</div>
          <div class="dist-bars">
            <div class="dist-bar" v-for="item in terminologyDistItems" :key="item.key">
              <div class="dist-label">{{ item.label }}</div>
              <div class="dist-track">
                <div class="dist-fill" :style="{width: item.pct + '%', background: item.color}"></div>
              </div>
              <div class="dist-count">
                <b :style="{color: item.color}">{{ item.value }}</b>
                <span style="font-size:11px;color:#909399;margin-left:2px">({{ item.pct }}%)</span>
              </div>
            </div>
          </div>
        </div>

        <el-divider style="margin:12px 0" />

        <div style="display:flex;gap:20px;flex-wrap:wrap">
          <div class="term-stat-item">
            <div class="term-stat-label">术语库总量</div>
            <div class="term-stat-value">{{ terminologyData.summary?.total_terms_in_db || 0 }}</div>
          </div>
          <div class="term-stat-item">
            <div class="term-stat-label">文档命中</div>
            <div class="term-stat-value" style="color:#67c23a">{{ terminologyData.summary?.terms_found || 0 }}</div>
          </div>
          <div class="term-stat-item">
            <div class="term-stat-label">未命中术语</div>
            <div class="term-stat-value" style="color:#e6a23c">{{ terminologyData.summary?.terms_not_found || 0 }}</div>
          </div>
          <div class="term-stat-item">
            <div class="term-stat-label">匹配总数</div>
            <div class="term-stat-value">{{ terminologyData.distribution?.total_occurrences || 0 }}</div>
          </div>
          <div class="term-stat-item">
            <div class="term-stat-label">匹配率</div>
            <div class="term-stat-value" :style="{color: terminologyData.distribution?.match_rate > 60 ? '#67c23a' : '#e6a23c'}">
              {{ terminologyData.distribution?.match_rate || 0 }}%
            </div>
          </div>
        </div>

        <div v-if="terminologyData.matches?.length > 0" style="margin-top:11px">
          <div style="font-size:13px;font-weight:600;margin-bottom:6px;color:#606266">
            术语匹配详情 ({{ terminologyData.matches.length }} 条)
          </div>
          <el-table :data="terminologyData.matches.slice(0,20)" size="small" max-height="240" border>
            <el-table-column prop="non_standard" label="非规范术语" width="160" />
            <el-table-column prop="standard" label="规范术语" width="160" />
            <el-table-column prop="category" label="分类" width="100" />
            <el-table-column prop="match_type" label="匹配类型" width="110">
              <template #default="{ row }">
                <el-tag :type="matchTypeTag(row.match_type)" size="small">
                  {{ matchTypeLabel(row.match_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="match_score" label="得分" width="70" align="center">
              <template #default="{ row }">
                <span :style="{color: row.match_score >= 85 ? '#67c23a' : row.match_score >= 50 ? '#e6a23c' : '#f56c6c', fontWeight:'bold'}">
                  {{ row.match_score }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="suggestion" label="建议" min-width="200" show-overflow-tooltip />
          </el-table>
        </div>

        <div v-if="terminologyData.unmatched_terms?.length > 0" style="margin-top:11px">
          <div style="font-size:12px;color:#909399;margin-bottom:4px">
            未在文档中出现的术语 ({{ terminologyData.unmatched_terms.length }} 条)
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px">
            <el-tag v-for="t in terminologyData.unmatched_terms.slice(0,30)" :key="t.id" size="small" type="info">
              {{ t.non_standard }} → {{ t.standard }}
            </el-tag>
          </div>
        </div>
      </el-card>

      <el-table
        :data="filteredDialogIssues"
        border
        height="60vh"
        @selection-change="onIssueSelectionChange"
        ref="issueTableRef"
        row-key="id"
        class="issue-detail-table"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="ID" width="70">
          <template #default="scope">
            {{ formatIssueDisplayId(scope.$index) }}
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="级别" width="80">
          <template #default="scope">
            <el-tag size="small" :type="severityTagType(scope.row.severity)" effect="plain">
              {{ severityLabel(scope.row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="模型" width="110" v-if="showProviderColumn">
          <template #default="scope">
            <div class="provider-tags">
              <template v-if="scope.row.providers">
                <el-tag
                  v-for="p in parseProviders(scope.row.providers)"
                  :key="p"
                  size="small"
                  :type="providerTagType(p)"
                  effect="plain"
                  class="provider-tag-item"
                >
                  {{ providerDisplayName(p) }}
                </el-tag>
                <el-tooltip v-if="parseProviders(scope.row.providers).length > 1"
                  content="多模型交叉验证，置信度更高" placement="top">
                  <el-tag size="small" type="success" effect="dark" class="provider-tag-item">
                    ✓{{ parseProviders(scope.row.providers).length }}
                  </el-tag>
                </el-tooltip>
              </template>
              <span v-else style="color:#999;font-size:11px">-</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="110" />
        <el-table-column prop="chapter" label="章节名称" width="180" show-overflow-tooltip />
        <el-table-column label="原文" min-width="450">
          <template #default="scope">
            <span class="context-cell" v-html="renderIssueOriginalCell(scope.row, currentTaskMode)"></span>
          </template>
        </el-table-column>
        <el-table-column label="建议" min-width="340" class-name="suggestion-column">
          <template #default="scope">
            <div class="suggestion-wrap">
              <div v-if="issueSuggestionOverview(scope.row)" class="suggestion-overview">{{ issueSuggestionOverview(scope.row) }}</div>
              <div v-if="issueSuggestionSummary(scope.row)" class="suggestion-summary">{{ issueSuggestionSummary(scope.row) }}</div>
              <div
                v-if="issueSuggestionDiffHtml(scope.row)"
                class="suggestion-diff"
                v-html="issueSuggestionDiffHtml(scope.row)"
              ></div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="处理" min-width="220">
          <template #default="scope">
            <div class="issue-action-cell">
              <div class="issue-inline-actions">
                <el-button size="small" type="success" @click="judgeSingle(scope.row, 'confirmed')">确认</el-button>
                <el-button size="small" type="danger" plain @click="judgeSingle(scope.row, 'false_positive')">误报</el-button>
                <el-button size="small" type="warning" plain @click="markSimilarIssuesFalsePositive(scope.row)">同类误报</el-button>
                <el-button size="small" type="primary" plain @click="openTransferRuleDialog(scope.row)">转规则库</el-button>
              </div>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="dialog-footer">
        <span>共 {{ filteredDialogIssues.length }} 条<span v-if="filteredDialogExcelRowCount">，涉及 {{ filteredDialogExcelRowCount }} 行</span> (已选 {{ selectedIssueIds.length }} 条)</span>
        <el-button @click="issueDialogVisible = false">关闭</el-button>
      </div>
    </el-dialog>

    <el-dialog v-model="manualIssueDialogVisible" title="补充上报漏检问题" width="620px">
      <el-form :model="manualIssueForm" label-width="90px">
        <el-form-item label="严重度">
          <el-select v-model="manualIssueForm.severity" style="width: 180px">
            <el-option label="致命" value="fatal" />
            <el-option label="严重" value="serious" />
            <el-option label="一般" value="general" />
            <el-option label="建议" value="suggestion" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="manualIssueForm.category" placeholder="如：拼写/用词、格式规范、术语一致性" />
        </el-form-item>
        <el-form-item label="章节位置">
          <el-input v-model="manualIssueForm.chapter" placeholder="如：3.2 Storage Conditions" />
        </el-form-item>
        <el-form-item label="问题原文" required>
          <el-input v-model="manualIssueForm.original_text" type="textarea" :rows="2" placeholder="填写平台漏检的原文片段" />
        </el-form-item>
        <el-form-item label="修改建议">
          <el-input v-model="manualIssueForm.suggestion" type="textarea" :rows="2" placeholder="填写建议修改结果" />
        </el-form-item>
        <el-form-item label="问题说明">
          <el-input v-model="manualIssueForm.description" type="textarea" :rows="3" placeholder="说明为什么需要补充上报" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="manualIssueDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="manualIssueSaving" @click="saveManualIssue">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="parsedTextDialogVisible" title="平台解析文本" width="80%" top="6vh">
      <div v-loading="parsedTextLoading">
        <div v-if="parsedTextMeta" class="parsed-text-meta">
          <el-tag size="small" effect="plain">{{ parsedTextMeta.filename }}</el-tag>
          <el-tag size="small" effect="plain">字符 {{ parsedTextMeta.char_count }}</el-tag>
          <el-tag size="small" effect="plain">词数 {{ parsedTextMeta.word_count }}</el-tag>
          <el-tag v-if="parsedTextMeta.page_count" size="small" effect="plain">页数 {{ parsedTextMeta.page_count }}</el-tag>
        </div>
        <el-input v-model="parsedTextContent" type="textarea" :rows="22" readonly />
      </div>
    </el-dialog>

    <el-dialog v-model="goldCompareDialogVisible" title="标准答案对比" width="90%" top="5vh">
      <div v-loading="goldCompareLoading">
        <div v-if="goldCompareResult" class="gold-summary-grid">
          <div class="gold-summary-card"><div class="gold-label">标准答案</div><div class="gold-value">{{ goldCompareResult.gold_count }}</div></div>
          <div class="gold-summary-card"><div class="gold-label">平台检出</div><div class="gold-value">{{ goldCompareResult.platform_count }}</div></div>
          <div class="gold-summary-card"><div class="gold-label">TP</div><div class="gold-value">{{ goldCompareResult.tp }}</div></div>
          <div class="gold-summary-card"><div class="gold-label">FP</div><div class="gold-value">{{ goldCompareResult.fp }}</div></div>
          <div class="gold-summary-card"><div class="gold-label">FN</div><div class="gold-value">{{ goldCompareResult.fn }}</div></div>
          <div class="gold-summary-card"><div class="gold-label">检出率</div><div class="gold-value">{{ percentText(goldCompareResult.recall) }}</div></div>
          <div class="gold-summary-card"><div class="gold-label">准确率</div><div class="gold-value">{{ percentText(goldCompareResult.precision) }}</div></div>
          <div class="gold-summary-card"><div class="gold-label">原文不存在</div><div class="gold-value">{{ goldCompareResult.missing_in_parsed_text_count }}</div></div>
        </div>
        <el-alert
          v-if="goldCompareResult && goldCompareResult.missing_in_parsed_text_count > 0"
          type="warning"
          show-icon
          :closable="false"
          title="部分标准答案错误原文不存在于平台解析文本中，这类项应先排查 PDF 解析输入，再判断规则漏检。"
          style="margin: 12px 0"
        />
        <el-tabs v-if="goldCompareResult" class="gold-tabs">
          <el-tab-pane :label="`漏检 ${goldCompareResult.missed.length}`">
            <el-table :data="goldCompareResult.missed" border height="360" size="small">
              <el-table-column prop="index" label="序号" width="70" />
              <el-table-column prop="location" label="位置" width="180" show-overflow-tooltip />
              <el-table-column prop="wrong_text" label="错误内容" min-width="150" show-overflow-tooltip />
              <el-table-column prop="correct_text" label="正确内容" min-width="150" show-overflow-tooltip />
              <el-table-column prop="issue_type" label="问题类型" width="120" />
              <el-table-column label="错误原文存在" width="120">
                <template #default="scope">
                  <el-tag size="small" :type="scope.row.wrong_text_exists_in_parsed_text ? 'success' : 'warning'">
                    {{ scope.row.wrong_text_exists_in_parsed_text ? '存在' : '不存在' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="note" label="备注" min-width="180" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`误报 ${goldCompareResult.false_positive.length}`">
            <el-table :data="goldCompareResult.false_positive" border height="360" size="small">
              <el-table-column prop="rule" label="规则" width="110" />
              <el-table-column prop="category" label="分类" width="120" />
              <el-table-column prop="original_text" label="原文" min-width="180" show-overflow-tooltip />
              <el-table-column prop="suggestion" label="建议" min-width="220" show-overflow-tooltip />
              <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`命中 ${goldCompareResult.matches.length}`">
            <el-table :data="goldCompareResult.matches" border height="360" size="small">
              <el-table-column label="标准错误" min-width="180">
                <template #default="scope">{{ scope.row.gold?.wrong_text }}</template>
              </el-table-column>
              <el-table-column label="平台命中" min-width="220">
                <template #default="scope">{{ scope.row.issues?.map(item => item.original_text).join('；') }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>

    <el-dialog v-model="transferRuleDialogVisible" title="转入规则库" width="620px">
      <el-form :model="transferRuleForm" label-width="90px">
        <el-form-item label="规则编号">
          <el-input v-model="transferRuleForm.rule_no" placeholder="如：R001" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="transferRuleForm.category" placeholder="如：拼写" />
        </el-form-item>
        <el-form-item label="规则描述">
          <el-input v-model="transferRuleForm.description" type="textarea" :rows="2" placeholder="规则描述" />
        </el-form-item>
        <el-form-item label="正则">
          <el-input v-model="transferRuleForm.regex" placeholder="正则表达式" />
        </el-form-item>
        <el-form-item label="示例">
          <el-input v-model="transferRuleForm.example" type="textarea" :rows="2" placeholder="示例文本" />
        </el-form-item>
        <el-form-item label="建议">
          <el-input v-model="transferRuleForm.suggestion" type="textarea" :rows="2" placeholder="修改建议" />
        </el-form-item>
        <el-form-item label="审核依据">
          <el-input v-model="transferRuleForm.audit_basis" placeholder="审核依据来源" />
        </el-form-item>
        <el-form-item label="语言">
          <el-select v-model="transferRuleForm.language" placeholder="请选择语言">
            <el-option label="中英通用" value="both" />
            <el-option label="中文" value="cn" />
            <el-option label="英文" value="en" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferRuleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTransferredRule">保存到规则库</el-button>
      </template>
    </el-dialog>

    <!-- 规则管理 -->
    <div v-if="currentView === 'rules'">
      <h2 class="page-title">规则管理</h2>
      <div class="table-section">
        <div class="table-header-actions">
          <el-button type="primary" @click="showRuleDialog = true">添加规则</el-button>
          <el-button @click="exportRules">导出规则库</el-button>
          <el-upload
            class="upload-btn"
            :action="rulesImportUrl"
            :on-success="handleRulesImport"
            :before-upload="beforeRulesUpload"
            accept=".json"
          >
            <el-button>批量导入规则</el-button>
          </el-upload>
          <el-button v-if="selectedRules.length > 0" type="danger" @click="batchDeleteRules">批量删除</el-button>
        </div>
        <el-table 
          :data="rules" 
          border 
          :default-sort="{prop: 'rule_no', order: 'ascending'}"
          @selection-change="onRuleSelectionChange"
          @sort-change="handleSortChange"
        >
          <el-table-column type="selection" width="55" />
          <el-table-column 
            prop="rule_no" 
            label="规则编号" 
            width="100"
            sortable="custom"
          />
          <el-table-column prop="category" label="分类" width="120" />
          <el-table-column prop="description" label="规则描述" />
          <el-table-column prop="regex" label="正则" width="200" />
          <el-table-column prop="example" label="示例" width="160" />
          <el-table-column prop="suggestion" label="建议" width="150" />
          <el-table-column prop="audit_basis" label="审核依据" width="180" />
          <el-table-column prop="language" label="语言" width="100">
            <template #default="scope">{{ languageLabel(scope.row.language) }}</template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180" sortable="custom" />
          <el-table-column label="操作" width="180">
            <template #default="scope">
              <el-button size="small" @click="editRule(scope.row)">编辑</el-button>
              <el-button size="small" type="danger" @click="deleteRule(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-dialog v-model="showRuleDialog" :title="editingRule ? '编辑规则' : '添加规则'" width="550px">
        <el-form :model="ruleForm" label-width="80px">
          <el-form-item label="规则编号">
            <el-input v-model="ruleForm.rule_no" placeholder="如：R001" :disabled="!!editingRule" />
          </el-form-item>
          <el-form-item label="分类">
            <el-input v-model="ruleForm.category" placeholder="如：标点符号" />
          </el-form-item>
          <el-form-item label="规则描述">
            <el-input v-model="ruleForm.description" placeholder="规则描述" />
          </el-form-item>
          <el-form-item label="正则">
            <el-input v-model="ruleForm.regex" placeholder="正则表达式" />
          </el-form-item>
          <el-form-item label="示例">
            <el-input v-model="ruleForm.example" placeholder="示例文本" />
          </el-form-item>
          <el-form-item label="建议">
            <el-input v-model="ruleForm.suggestion" placeholder="修改建议" />
          </el-form-item>
          <el-form-item label="审核依据">
            <el-input v-model="ruleForm.audit_basis" placeholder="审核依据来源" />
          </el-form-item>
          <el-form-item label="语言">
            <el-select v-model="ruleForm.language" placeholder="请选择语言">
              <el-option label="中英通用" value="both" />
              <el-option label="中文" value="cn" />
              <el-option label="英文" value="en" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showRuleDialog = false">取消</el-button>
          <el-button type="primary" @click="saveRule">保存</el-button>
        </template>
      </el-dialog>
    </div>

    <!-- 审核报告 -->
    <div v-if="currentView === 'reports'">
      <h2 class="page-title">审核报告</h2>
      <div class="table-section">
        <el-table :data="reviews" border>
          <el-table-column prop="id" label="任务ID" width="100" />
          <el-table-column prop="document_id" label="文档ID" width="100" />
          <el-table-column prop="document_name" label="文档名" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.status === 'completed' ? 'success' : scope.row.status === 'failed' ? 'danger' : 'info'">
                {{ scope.row.status === 'completed' ? '已完成' : scope.row.status === 'failed' ? '失败' : '进行中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="total_issues" label="问题数" width="100" />
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column label="操作" width="140">
            <template #default="scope">
              <el-button size="small" @click="loadReport(scope.row.id)">查看报告</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="showReport" class="report-section">
        <h3>报告详情预览</h3>
        <div class="report-content">
          <div class="report-header">
            <div><strong>任务 ID：</strong>{{ currentReport.id }}</div>
            <div><strong>文档：</strong>{{ currentReport.document_name }}</div>
            <div><strong>模式：</strong>{{ currentReport.mode }}</div>
            <div><strong>状态：</strong>{{ currentReport.status === 'completed' ? '已完成' : currentReport.status === 'failed' ? '失败' : '进行中' }}</div>
            <div><strong>问题总数：</strong>{{ currentReport.total_issues }}</div>
            <div><strong>创建时间：</strong>{{ formatDateTime(currentReport.created_at) }}</div>
          </div>
          <div class="report-summary">
            <h4>概览</h4>
            <div class="stats-row">
              <span class="stat-item fatal">致命: {{ reportStats.fatal }}</span>
              <span class="stat-item serious">严重: {{ reportStats.serious }}</span>
              <span class="stat-item general">一般: {{ reportStats.general }}</span>
              <span class="stat-item suggestion">建议: {{ reportStats.suggestion }}</span>
            </div>
          </div>
          <div class="report-issues">
            <h4>问题列表</h4>
            <el-table :data="reportIssues" border>
              <el-table-column prop="display_id" label="编号" width="90" />
              <el-table-column prop="severity" label="级别" width="100">
                <template #default="scope">
                  <el-tag :type="getSeverityType(scope.row.severity)">{{ getSeverityLabel(scope.row.severity) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="模型" width="110" v-if="showReportProviderColumn">
                <template #default="scope">
                  <div class="provider-tags">
                    <template v-if="scope.row.providers">
                      <el-tag
                        v-for="p in parseProviders(scope.row.providers)"
                        :key="p"
                        size="small"
                        :type="providerTagType(p)"
                        effect="plain"
                        class="provider-tag-item"
                      >
                        {{ providerDisplayName(p) }}
                      </el-tag>
                      <el-tooltip v-if="parseProviders(scope.row.providers).length > 1"
                        content="多模型交叉验证，置信度更高" placement="top">
                        <el-tag size="small" type="success" effect="dark" class="provider-tag-item">
                          ✓{{ parseProviders(scope.row.providers).length }}
                        </el-tag>
                      </el-tooltip>
                    </template>
                    <span v-else style="color:#999;font-size:11px">-</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="category" label="分类" width="120" />
              <el-table-column prop="chapter" label="章节" width="180" />
              <el-table-column label="上下文" min-width="500">
                <template #default="scope">
                  <span class="context-text" v-html="renderIssueContext(scope.row, currentReport?.mode)"></span>
                </template>
              </el-table-column>
              <el-table-column prop="suggestion" label="建议" min-width="200" />
              <el-table-column prop="audit_basis" label="审核依据" min-width="200" />
            </el-table>
          </div>
        </div>
        <div class="report-actions">
          <el-button type="primary" @click="exportReport">导出报告</el-button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { documentAPI, reviewAPI, rulesAPI, getAPIErrorMessage } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const documents = ref([])
const reviews = ref([])
const documentReviews = ref([])
const issues = ref([])
const rules = ref([])

// 行内报告：按任务ID存储问题列表和筛选条件
const taskIssues = reactive({})
const rowFilters = reactive({})

// 文档审核状态 (按文档ID存储)
const docReviewStatus = reactive({})
let reviewsPollingTimer = null
let sseConnections = new Map()  // reviewId → EventSource

// 问题详情弹窗
const issueDialogVisible = ref(false)
const currentTaskId = ref(null)
const issueFilter = reactive({ keyword: '', category: '', status: '', severity: '' })
const selectedIssueIds = ref([])
const issueTableRef = ref(null)
const manualIssueDialogVisible = ref(false)
const manualIssueSaving = ref(false)
const manualIssueForm = ref({ severity: 'general', category: '人工补充', chapter: '', original_text: '', suggestion: '', description: '' })
const parsedTextDialogVisible = ref(false)
const parsedTextLoading = ref(false)
const parsedTextMeta = ref(null)
const parsedTextContent = ref('')
const goldCompareDialogVisible = ref(false)
const goldCompareLoading = ref(false)
const goldCompareResult = ref(null)
const auditTraces = ref([])  // AI调用追踪数据
const coverageData = ref(null) // 审核覆盖率数据
const showCoverage = ref(false) // 是否展示覆盖率面板
const terminologyData = ref(null) // 术语匹配率分析数据
const showTerminology = ref(false) // 是否展示术语面板
const showAuditTraces = ref(false)  // 是否展开AI追踪面板
const dialogCategories = computed(() => {
  const set = new Set()
  const list = taskIssues[currentTaskId.value] || []
  for (const i of list) {
    if (i.category) set.add(i.category)
  }
  return Array.from(set).sort()
})
const filteredDialogIssues = computed(() => {
  const list = taskIssues[currentTaskId.value] || []
  return list.filter(i => {
    if (issueFilter.category && i.category !== issueFilter.category) return false
    if (issueFilter.status && (i.status || 'pending') !== issueFilter.status) return false
    if (issueFilter.severity && i.severity !== issueFilter.severity) return false
    if (issueFilter.keyword) {
      const k = issueFilter.keyword.toLowerCase()
      const hay = `${i.original_text || ''} ${i.context || ''} ${issueSuggestionText(i)} ${i.description || ''}`.toLowerCase()
      if (!hay.includes(k)) return false
    }
    return true
  })
})
const terminologyDistItems = computed(() => {
  const d = terminologyData.value?.distribution
  if (!d) return []
  const total = d.total_occurrences || 1
  return [
    { key: 'golden', label: '102% 完美', value: d.golden_match || 0, color: '#00C853', pct: Math.round((d.golden_match || 0) / total * 100) },
    { key: 'context', label: '101% 上下文', value: d.context_match || 0, color: '#00E676', pct: Math.round((d.context_match || 0) / total * 100) },
    { key: 'perfect', label: '100% 完全', value: d.perfect_match || 0, color: '#67c23a', pct: Math.round((d.perfect_match || 0) / total * 100) },
    { key: 'high', label: '85-99%', value: d.high_match || 0, color: '#85CE61', pct: Math.round((d.high_match || 0) / total * 100) },
    { key: 'medium', label: '75-84%', value: d.medium_match || 0, color: '#E6A23C', pct: Math.round((d.medium_match || 0) / total * 100) },
    { key: 'low', label: '50-74%', value: d.low_match || 0, color: '#E6A23C', pct: Math.round((d.low_match || 0) / total * 100) },
    { key: 'vlow', label: '1-49%', value: d.very_low_match || 0, color: '#F56C6C', pct: Math.round((d.very_low_match || 0) / total * 100) },
    { key: 'new', label: '新句段', value: d.new_segment || 0, color: '#909399', pct: Math.round((d.new_segment || 0) / total * 100) },
  ]
})

const filteredDialogExcelRowCount = computed(() => {
  const rows = new Set()
  for (const issue of filteredDialogIssues.value) {
    const position = parseMaybeJson(issue.position)
    if (!position || !position.sheet || !position.row) continue
    rows.add(`${position.sheet}:${position.row}`)
  }
  return rows.size
})

// AI调用追踪计算属性
const totalTraceTokens = computed(() => {
  return auditTraces.value.reduce((sum, t) => sum + (t.total_tokens || 0), 0)
})
const totalTraceLatency = computed(() => {
  return auditTraces.value.reduce((sum, t) => sum + (t.latency_ms || 0), 0)
})
const traceProviders = computed(() => {
  return [...new Set(auditTraces.value.map(t => t.provider).filter(Boolean))]
})

function formatIssueDisplayId(index) {
  return String(index + 1).padStart(3, '0')
}

function issueSuggestionText(issue) {
  const suggestion = String(issue?.suggestion || '').trim()
  if (suggestion) return suggestion
  const description = normalizeIssueDescription(issue)
  if (description) return description
  return '-'
}

function issueSuggestionFullText(issue) {
  const suggestion = String(issue?.suggestion || '').trim()
  const description = normalizeIssueDescription(issue)
  if (suggestion && description && description !== suggestion) {
    return `${suggestion}\n\n说明：${description}`
  }
  return suggestion || description || '-'
}

function normalizeIssueDescription(issue) {
  let text = String(issue?.description || '')
    .trim()
    .replace(/^问题说明[:：]\s*/, '')
    .replace(/^问题[:：]\s*/, '')
    .replace(/\s+/g, ' ')
  text = text
    .replace(/原文片段[:：]\s*['"“”‘’]?[^；;。]*(?:[；;。]|$)/g, '')
    .replace(/疑似错误(?:词|短语)[:：]\s*\[[^\]]+\][；;。]?/g, '')
    .replace(/建议(?:修改词|修改为|修改短语)?[:：]?\s*\[[^\]]+\][；;。]?/g, '')
    .replace(/是否确定[:：]\s*确定[；;。]?/g, '')
    .replace(/；\s*；/g, '；')
    .replace(/^[；;。\s]+|[；;。\s]+$/g, '')
    .trim()
  return text
}

function compactSuggestionText(text, limit = 36) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized
}

function categoryProblemLabel(category) {
  const text = String(category || '').trim()
  if (!text) return ''
  if (/语法|主谓|时态|单复数/.test(text)) return '语法问题'
  if (/逻辑|步骤结构|操作步骤/.test(text)) return '操作步骤逻辑问题'
  if (/拼写/.test(text)) return '拼写问题'
  if (/术语|用词|写法/.test(text)) return '术语一致性问题'
  if (/标点|空格|格式/.test(text)) return '标点/格式问题'
  if (/合规|法规|注册/.test(text)) return '合规表述问题'
  if (/重复/.test(text)) return '重复内容问题'
  if (/结构/.test(text)) return '结构完整性问题'
  return `${text}问题`
}

function descriptionProblemLabel(description) {
  const text = String(description || '').trim()
  if (!text) return ''
  if (/主谓一致|describe[s]?\b|describes\b|单数|复数|时态|grammar/i.test(text)) return '语法问题'
  if (/跳号|跳到|编号|步骤|流程连续|逻辑/i.test(text)) return '操作步骤逻辑问题'
  if (/拼写|misspell|typo/i.test(text)) return '拼写问题'
  if (/术语|写法|统一|term/i.test(text)) return '术语一致性问题'
  if (/标点|空格|格式|punctuation|spacing/i.test(text)) return '标点/格式问题'
  if (/合规|法规|注册|ruo|compliance/i.test(text)) return '合规表述问题'
  if (/重复|冗余/i.test(text)) return '重复内容问题'
  return ''
}

function issueProblemLabel(issue) {
  const description = normalizeIssueDescription(issue)
  return descriptionProblemLabel(description) || categoryProblemLabel(issue?.category)
}

function escapeSuggestionHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function extractSuggestionReplacement(issue) {
  const suggestion = String(issue?.suggestion || '').trim()
  if (!suggestion) return ''
  const patterns = [
    /建议(?:改为|替换为|统一为)\s*[:：]?\s*(.+)$/i,
    /(?:->|→)\s*(.+)$/,
  ]
  for (const pattern of patterns) {
    const match = suggestion.match(pattern)
    if (!match) continue
    const candidate = String(match[1] || '').trim().replace(/[。；;]+$/, '')
    if (candidate && !/[，,。；;].{8,}/.test(candidate)) return candidate
  }
  if (suggestion.length <= 80 && !/^请|^需|^应|^确认/.test(suggestion)) return suggestion
  return ''
}

function buildSuggestionDiffMarkup(before, after) {
  if (!before || !after || before === after) return ''
  let prefix = 0
  const maxPrefix = Math.min(before.length, after.length)
  while (prefix < maxPrefix && before[prefix] === after[prefix]) prefix += 1

  let suffix = 0
  const maxSuffix = Math.min(before.length - prefix, after.length - prefix)
  while (
    suffix < maxSuffix
    && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
  ) {
    suffix += 1
  }

  const beforeHead = escapeSuggestionHtml(before.slice(0, prefix))
  const beforeMid = escapeSuggestionHtml(before.slice(prefix, before.length - suffix || before.length))
  const beforeTail = escapeSuggestionHtml(before.slice(before.length - suffix))
  const afterHead = escapeSuggestionHtml(after.slice(0, prefix))
  const afterMid = escapeSuggestionHtml(after.slice(prefix, after.length - suffix || after.length))
  const afterTail = escapeSuggestionHtml(after.slice(after.length - suffix))

  return `
    <div class="suggestion-diff-row"><span class="suggestion-diff-label">原文</span><span>${beforeHead}<span class="diff-remove">${beforeMid || '&nbsp;'}</span>${beforeTail}</span></div>
    <div class="suggestion-diff-row"><span class="suggestion-diff-label">建议</span><span>${afterHead}<span class="diff-add">${afterMid || '&nbsp;'}</span>${afterTail}</span></div>
  `
}

function describeSuggestionChange(original, replacement) {
  const before = String(original || '').trim()
  const after = String(replacement || '').trim()
  if (!before || !after || before === after) return ''

  let prefix = 0
  const maxPrefix = Math.min(before.length, after.length)
  while (prefix < maxPrefix && before[prefix] === after[prefix]) prefix += 1

  let suffix = 0
  const maxSuffix = Math.min(before.length - prefix, after.length - prefix)
  while (
    suffix < maxSuffix
    && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
  ) {
    suffix += 1
  }

  const removed = before.slice(prefix, before.length - suffix || before.length).trim()
  const added = after.slice(prefix, after.length - suffix || after.length).trim()
  if (removed && added) {
    if (removed.length <= 24 && added.length <= 32) {
      return `将“${removed}”改为“${added}”`
    }
    return `将相关表述改为“${compactSuggestionText(added)}”`
  }
  if (!removed && added) {
    return `补充“${compactSuggestionText(added)}”`
  }
  if (removed && !added) {
    return `删除“${compactSuggestionText(removed)}”`
  }
  return `建议改为“${compactSuggestionText(after)}”`
}

function issueSuggestionOverview(issue) {
  const replacement = extractSuggestionReplacement(issue)
  const original = String(issue?.original_text || '').trim()
  if (replacement && original && replacement !== original) {
    return describeSuggestionChange(original, replacement)
  }

  const suggestion = String(issue?.suggestion || '').trim()
  if (suggestion) return '建议按下方修改。'

  const problemLabel = issueProblemLabel(issue)
  if (problemLabel) return problemLabel

  return '该处需要处理。'
}

function issueSuggestionSummary(issue) {
  const description = normalizeIssueDescription(issue)
  if (description) return description

  const suggestion = String(issue?.suggestion || '').trim()
  if (suggestion) return suggestion

  return issueSuggestionFullText(issue)
}

function issueSuggestionDiffHtml(issue) {
  return ''
}

function percentText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '0%'
  return `${(number * 100).toFixed(1)}%`
}

function resetManualIssueForm() {
  manualIssueForm.value = { severity: 'general', category: '人工补充', chapter: '', original_text: '', suggestion: '', description: '' }
}

function openManualIssueDialog() {
  if (!currentTaskId.value) {
    ElMessage.warning('请先打开审核任务')
    return
  }
  resetManualIssueForm()
  manualIssueDialogVisible.value = true
}

async function saveManualIssue() {
  if (!currentTaskId.value) {
    ElMessage.warning('请先打开审核任务')
    return
  }
  if (!manualIssueForm.value.original_text.trim()) {
    ElMessage.warning('请填写问题原文')
    return
  }
  manualIssueSaving.value = true
  try {
    const response = await reviewAPI.createManualIssue(currentTaskId.value, manualIssueForm.value)
    const created = response.data
    taskIssues[currentTaskId.value] = [created, ...(taskIssues[currentTaskId.value] || [])]
    issues.value = [created, ...issues.value]
    manualIssueDialogVisible.value = false
    ElMessage.success('已补充上报漏检问题')
  } catch (error) {
    ElMessage.error(`补充上报失败: ${getAPIErrorMessage(error)}`)
  } finally {
    manualIssueSaving.value = false
  }
}

// 判定状态统计 (按任务ID)
const judgmentStats = computed(() => {
  const stats = {}
  for (const key in taskIssues) {
    const list = taskIssues[key]
    let confirmed = 0, false_positive = 0, pending = 0, manual = 0
    for (const i of list) {
      const s = i.status || 'pending'
      if (i.source === 'manual') manual++
      if (s === 'confirmed') confirmed++
      else if (s === 'false_positive') false_positive++
      else pending++
    }
    stats[key] = { confirmed, false_positive, pending, manual }
  }
  return stats
})

const showRuleDialog = ref(false)

// 多模型交叉验证：是否显示"模型"列
const showProviderColumn = computed(() => {
  return issues.value.some(issue => {
    try {
      const providers = typeof issue.providers === 'string'
        ? JSON.parse(issue.providers) : issue.providers
      return Array.isArray(providers) && providers.length > 0
    } catch { return false }
  })
})

const showReportProviderColumn = computed(() => {
  return reportIssues.value.some(issue => {
    try {
      const providers = typeof issue.providers === 'string'
        ? JSON.parse(issue.providers) : issue.providers
      return Array.isArray(providers) && providers.length > 0
    } catch { return false }
  })
})

function parseProviders(providers) {
  if (!providers) return []
  if (Array.isArray(providers)) return providers
  try {
    const parsed = JSON.parse(providers)
    return Array.isArray(parsed) ? parsed : [providers]
  } catch { return [providers] }
}

function providerDisplayName(provider) {
  const names = { qwen: 'Qwen', deepseek: 'DeepSeek', kimi: 'Kimi', arkclaw: 'ArkClaw', mcai: 'MCAI', proxy: 'Proxy' }
  return names[provider] || provider.toUpperCase()
}
const editingRule = ref(null)
const ruleForm = ref({ rule_no: '', category: '', description: '', regex: '', example: '', suggestion: '', audit_basis: '', language: 'both' })
const transferRuleDialogVisible = ref(false)
const transferRuleSourceIssue = ref(null)
const transferRuleForm = ref({ rule_no: '', category: '', description: '', regex: '', example: '', suggestion: '', audit_basis: '', language: 'both' })

const selectedRules = ref([])
const rulesImportUrl = '/api/rules/bulk'

const uploadUrl = '/api/documents/upload/'
const reviewMode = ref('hybrid')
const selectedProvider = ref('')
const availableModels = ref([])
const providerLoading = ref(true)

const selectedProviderLabel = computed(() => {
  if (!selectedProvider.value) return '默认'
  const model = availableModels.value.find(m => m.name === selectedProvider.value)
  return model ? model.label : selectedProvider.value
})
const reviewSubTab = ref('single')
const compareMode = ref('both')
const compareSubmitting = ref(false)
const compareResult = ref(null)
const showCompareConsistent = ref(false)
const compareMainFile = ref(null)
const compareMainFileList = ref([])
const compareReferenceFiles = ref([])
const compareReferenceFileList = ref([])

const visibleCompareRows = computed(() => {
  const rows = compareResult.value?.compare_rows || []
  if (showCompareConsistent.value) return rows
  return rows.filter((row) => row.level !== '一致')
})

const compareReferenceColumns = computed(() => {
  const documents = compareResult.value?.reference_documents || []
  if (documents.length) return documents
  const firstRow = compareResult.value?.compare_rows?.[0]
  return firstRow?.reference_values || []
})

watch(reviewSubTab, (tab) => {
  if (tab === 'single') {
    compareResult.value = null
    showCompareConsistent.value = false
  }
})

function goReviewTasks() {
  router.push('/review/tasks')
}
const uploadProgress = ref(0)
const uploadProgressText = ref('')
let uploadingTempId = 0

const filterKeyword = ref('')
const filterSeverity = ref('')
const filterCategory = ref('')

const sortField = ref('rule_no')
const sortOrder = ref('asc')

const currentView = computed(() => {
  if (route.path === '/review/tasks') return 'tasks'
  if (route.path === '/review/rules') return 'rules'
  return 'documents'
})

const issueStats = computed(() => {
  const stats = { fatal: 0, serious: 0, general: 0, suggestion: 0 }
  issues.value.forEach(issue => {
    if (stats[issue.severity] !== undefined) stats[issue.severity]++
  })
  return [
    { label: '致命', value: stats.fatal, class: 'stat-fatal' },
    { label: '严重', value: stats.serious, class: 'stat-serious' },
    { label: '一般', value: stats.general, class: 'stat-general' },
    { label: '建议', value: stats.suggestion, class: 'stat-suggestion' }
  ]
})

const reportStats = computed(() => {
  const stats = { fatal: 0, serious: 0, general: 0, suggestion: 0 }
  issues.value.forEach(issue => {
    if (stats[issue.severity] !== undefined) stats[issue.severity]++
  })
  return stats
})

const reportIssues = computed(() => {
  return issues.value.map((issue, index) => ({
    ...issue,
    display_id: `#${String(index + 1).padStart(4, '0')}`,
    db_id: issue.id,
  }))
})

const categories = computed(() => {
  const cats = new Set(issues.value.map(i => i.category))
  return Array.from(cats).filter(Boolean)
})

const filteredIssues = computed(() => {
  let result = [...issues.value]
  if (filterKeyword.value) {
    const keyword = filterKeyword.value.toLowerCase()
    result = result.filter(issue => 
      (issue.original_text && issue.original_text.toLowerCase().includes(keyword)) || 
      (issue.context && issue.context.toLowerCase().includes(keyword)) ||
      (issue.chapter && issue.chapter.toLowerCase().includes(keyword))
    )
  }
  if (filterSeverity.value) {
    result = result.filter(issue => issue.severity === filterSeverity.value)
  }
  if (filterCategory.value) {
    result = result.filter(issue => issue.category === filterCategory.value)
  }
  return result
})

watch(() => route.path, () => {
  loadByView()
})

onMounted(() => {
  loadByView()
  loadProviders()
})

function loadByView() {
  stopReviewsPolling()
  if (currentView.value === 'documents') loadDocuments()
  else if (currentView.value === 'tasks' || currentView.value === 'reports') loadReviews()
  else if (currentView.value === 'rules') loadRules()
}

async function loadProviders() {
  providerLoading.value = true
  try {
    const resp = await reviewAPI.getProviderStatus()
    const data = resp.data
    availableModels.value = (data.models || []).filter(m => m.available)
    // 设置默认 provider（单选默认）
    if (availableModels.value.length > 0) {
      const defaultName = data.default_provider
      const defaultMatch = availableModels.value.find(m => m.name === defaultName)
      if (defaultMatch) {
        selectedProvider.value = defaultMatch.name
      } else {
        selectedProvider.value = availableModels.value[0].name
      }
    }
  } catch (e) {
    console.error('Failed to load AI providers:', e)
    availableModels.value = []
  } finally {
    providerLoading.value = false
  }
}

async function loadDocuments() {
  try {
    const [docResp, reviewResp] = await Promise.all([
      documentAPI.list(),
      reviewAPI.list({ latest_only: true, limit: 500 })
    ])
    const uploadingDocs = documents.value.filter(doc => String(doc.id).startsWith('uploading-'))
    documents.value = [...uploadingDocs, ...(docResp.data || [])]
    documentReviews.value = reviewResp.data || []
    syncDocumentStatusesFromReviews(documentReviews.value)
    syncReviewsPolling()
  } catch (e) {
    ElMessage.error(`加载文档列表失败: ${getAPIErrorMessage(e)}`)
  }
}

async function loadReviews() {
  try {
    const resp = await reviewAPI.list({ limit: 500 })
    reviews.value = resp.data || []
    if (currentView.value === 'documents') {
      syncDocumentStatusesFromReviews(reviews.value)
    }
    syncReviewsPolling()
  } catch (e) {
    ElMessage.error(`加载任务列表失败: ${getAPIErrorMessage(e)}`)
  }
}

function syncDocumentStatusesFromReviews(reviewList) {
  const reviewMap = {}
  for (const review of reviewList || []) {
    if (!reviewMap[review.document_id] || review.id > reviewMap[review.document_id].id) {
      reviewMap[review.document_id] = review
    }
  }

  const activeDocIds = new Set()
  for (const doc of documents.value) {
    const latestReview = reviewMap[doc.id]
    const docCreatedAt = new Date(doc.created_at || 0).getTime()
    const reviewCreatedAt = new Date(latestReview?.created_at || 0).getTime()
    const hasValidReview = Boolean(latestReview) && (!docCreatedAt || !reviewCreatedAt || reviewCreatedAt >= docCreatedAt)

    if (!hasValidReview) {
      delete docReviewStatus[doc.id]
      continue
    }

    const progressInfo = latestReview.progress || null
    const progressValue = latestReview.status === 'completed'
      ? 100
      : latestReview.status === 'running'
        ? (progressInfo?.progress || 0)
        : 0
    const message = latestReview.status === 'completed'
      ? reviewCompletionText(latestReview)
      : latestReview.status === 'failed'
        ? reviewFailureText(latestReview)
        : reviewProgressText(progressInfo)

    docReviewStatus[doc.id] = {
      review_id: latestReview.id,
      status: latestReview.status,
      progress: progressValue,
      message,
      summary: latestReview.summary,
      total_issues: latestReview.total_issues
    }
    activeDocIds.add(String(doc.id))
  }

  Object.keys(docReviewStatus).forEach((docId) => {
    if (!activeDocIds.has(String(docId)) && !String(docId).startsWith('uploading-')) {
      delete docReviewStatus[docId]
    }
  })
}

function _getSSEBaseURL() {
  // 从 Vite 代理或直接 API 推导
  return import.meta.env.VITE_API_BASE || '/api'
}

function _connectSSEForReview(reviewId) {
  if (sseConnections.has(reviewId)) return  // 已连接

  const baseURL = _getSSEBaseURL()
  const url = `${baseURL}/review/${reviewId}/progress-stream`

  try {
    const es = new EventSource(url)
    sseConnections.set(reviewId, es)

    es.onmessage = (event) => {
      try {
        const progress = JSON.parse(event.data)
        const status = progress.status

        // 同步当前页面和文档页中的审核任务快照
        for (const reviewList of [reviews.value, documentReviews.value]) {
          const review = (reviewList || []).find(r => r.id === reviewId)
          if (review) {
            review.progress = progress
            review.status = status
            if (status === 'completed') {
              review.total_issues = progress.total_issues || review.total_issues
            }
          }
        }

        // 同步到文档状态
        if (currentView.value === 'documents') {
          // 找到对应文档并更新
          for (const doc of documents.value) {
            const ds = docReviewStatus[doc.id]
            if (ds && ds.review_id === reviewId) {
              ds.status = status
              ds.progress = progress?.progress || 0
              ds.message = status === 'completed'
                ? reviewCompletionText(review)
                : status === 'failed'
                  ? reviewFailureText(review)
                  : (progress?.message || progress?.step || '审核中...')
              if (progress?.summary) ds.summary = progress.summary
              break
            }
          }
        }

        // 审核完成/失败时断开 SSE
        if (status === 'completed' || status === 'failed' || status === 'error' || status === 'timeout') {
          es.close()
          sseConnections.delete(reviewId)

          // 完成后重新加载以获取完整结果
          if (status === 'completed') {
            setTimeout(() => {
              if (currentView.value === 'documents') loadDocuments()
              else loadReviews()
            }, 500)
          }
        }
      } catch (_) { /* 忽略解析错误 */ }
    }

    es.onerror = () => {
      // SSE 连接失败，关闭并回退到轮询
      es.close()
      sseConnections.delete(reviewId)
    }
  } catch (_) {
    // EventSource 不可用（如旧浏览器），回退到轮询
  }
}

function _disconnectAllSSE() {
  for (const [reviewId, es] of sseConnections) {
    es.close()
  }
  sseConnections.clear()
}

function _hasRunningReviews() {
  const activeReviews = currentView.value === 'documents' ? documentReviews.value : reviews.value
  return (activeReviews || []).some(review => review.status === 'running')
}

function syncReviewsPolling() {
  stopReviewsPolling()
  if (currentView.value !== 'documents' && currentView.value !== 'tasks' && currentView.value !== 'reports') return
  if (!_hasRunningReviews()) return

  // 优先使用 SSE 实时推送
  const activeReviews = currentView.value === 'documents' ? documentReviews.value : reviews.value
  const runningReviews = (activeReviews || []).filter(r => r.status === 'running')
  const supportsSSE = typeof EventSource !== 'undefined'

  if (supportsSSE) {
    for (const review of runningReviews) {
      _connectSSEForReview(review.id)
    }
  }

  // 轮询作为降级方案（每 10 秒一次，用于 SSE 不支持或连接断开时）
  reviewsPollingTimer = setInterval(async () => {
    // 检查是否有 SSE 活跃连接覆盖所有运行中的审核
    const allSSECovered = runningReviews.every(r => sseConnections.has(r.id))
    if (allSSECovered) {
      // SSE 覆盖良好，跳过本次轮询
      if (!_hasRunningReviews()) stopReviewsPolling()
      return
    }

    try {
      if (currentView.value === 'documents') {
        const resp = await reviewAPI.list({ latest_only: true, limit: 500 })
        documentReviews.value = resp.data || []
        syncDocumentStatusesFromReviews(documentReviews.value)
      } else {
        const runningIds = new Set((reviews.value || []).filter(review => review.status === 'running').map(review => review.id))
        const resp = await reviewAPI.list({ status: 'running', limit: 500 })
        const runningReviewsResp = resp.data || []
        const returnedIds = new Set(runningReviewsResp.map(review => review.id))
        const finishedDuringPolling = [...runningIds].some(reviewId => !returnedIds.has(reviewId))

        if (finishedDuringPolling) {
          await loadReviews()
          return
        }

        const reviewMap = new Map((reviews.value || []).map(review => [review.id, review]))
        for (const review of runningReviewsResp) {
          reviewMap.set(review.id, review)
        }
        reviews.value = [...reviewMap.values()].sort((left, right) => (right.id || 0) - (left.id || 0))
      }
      if (!_hasRunningReviews()) {
        stopReviewsPolling()
      }
    } catch (error) {
      stopReviewsPolling()
    }
  }, 10000)  // SSE 降级轮询频率降低到 10 秒
}

function stopReviewsPolling() {
  _disconnectAllSSE()
  if (reviewsPollingTimer) {
    clearInterval(reviewsPollingTimer)
    reviewsPollingTimer = null
  }
}

async function loadRules() {
  try {
    const resp = await rulesAPI.list()
    rules.value = resp.data || []
  } catch (e) {
    ElMessage.error(`加载规则列表失败: ${getAPIErrorMessage(e)}`)
  }
}

function formatSize(size) {
  if (!size) return '-'
  if (size < 1024) return size + ' B'
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB'
  return (size / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDateTime(dateStr) {
  if (!dateStr) return '-'
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(dateStr)
    ? dateStr
    : `${dateStr}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return String(dateStr).replace('T', ' ').slice(0, 19)
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-')
}

function beforeUpload(file) {
  const allowed = ['pdf', 'docx', 'xlsx', 'xls', 'md', 'zip', 'txt', 'idml']
  const ext = file.name.split('.').pop().toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.error('不支持的文件格式: .' + ext)
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小超过 50MB')
    return false
  }
  return true
}

function validateCompareUpload(file) {
  return Boolean(file && beforeUpload(file))
}

function handleCompareMainChange(uploadFile) {
  const rawFile = uploadFile.raw || uploadFile
  if (!validateCompareUpload(rawFile)) {
    compareMainFile.value = null
    compareMainFileList.value = []
    return
  }
  compareMainFile.value = rawFile
  compareMainFileList.value = [uploadFile]
}

function clearCompareMainFile() {
  compareMainFile.value = null
  compareMainFileList.value = []
}

function handleCompareReferenceChange(_uploadFile, uploadFiles) {
  const validFiles = []
  const validUploadFiles = []
  for (const item of uploadFiles) {
    const rawFile = item.raw || item
    if (!validateCompareUpload(rawFile)) {
      continue
    }
    validFiles.push(rawFile)
    validUploadFiles.push(item)
  }
  compareReferenceFiles.value = validFiles
  compareReferenceFileList.value = validUploadFiles
}

function handleCompareReferenceRemove(_uploadFile, uploadFiles) {
  compareReferenceFiles.value = uploadFiles.map((item) => item.raw || item).filter(Boolean)
  compareReferenceFileList.value = [...uploadFiles]
}

function formatCompareHits(hits = []) {
  if (!hits.length) return '-'
  return hits.map((hit) => `第${hit.line_no}行: ${hit.context}`).join(' | ')
}

async function startCompareAudit() {
  if (!compareMainFile.value) {
    ElMessage.warning('请先上传主文档')
    return
  }
  if (!compareReferenceFiles.value.length) {
    ElMessage.warning('未提供参考文件，无法进行对比')
    return
  }

  compareSubmitting.value = true
  try {
    const response = await reviewAPI.compareAudit(compareMainFile.value, compareReferenceFiles.value, compareMode.value)
    showCompareConsistent.value = false
    compareResult.value = response.data
    await loadReviews()
    await loadDocuments()
    ElMessage.success('对比审核完成')
  } catch (error) {
    compareResult.value = null
    ElMessage.error(`对比审核失败: ${getAPIErrorMessage(error)}`)
  } finally {
    compareSubmitting.value = false
  }
}

function insertUploadingPlaceholder(file) {
  const tempId = `uploading-${++uploadingTempId}`
  documents.value = [
    {
      id: tempId,
      filename: file.name,
      file_type: file.name.split('.').pop().toLowerCase(),
      file_size: file.size,
      status: 'uploading',
      created_at: new Date().toISOString()
    },
    ...documents.value.filter(doc => String(doc.id) !== tempId)
  ]
  return tempId
}

function removeUploadingPlaceholder(tempId) {
  documents.value = documents.value.filter(doc => String(doc.id) !== String(tempId))
}

function upsertDocumentRow(document) {
  if (!document?.id) return
  documents.value = [
    document,
    ...documents.value.filter(doc => String(doc.id) !== String(document.id) && !String(doc.id).startsWith('uploading-'))
  ]
}

function upsertReviewSnapshot(targetList, review) {
  if (!review?.id) return
  const next = [review, ...(targetList.value || []).filter(item => item.id !== review.id)]
  targetList.value = next.sort((left, right) => (right.id || 0) - (left.id || 0))
}

function beforeRulesUpload(file) {
  const ext = file.name.split('.').pop().toLowerCase()
  if (ext !== 'json') {
    ElMessage.error('仅支持 JSON 格式文件')
    return false
  }
  return true
}

async function uploadDocument(options) {
  const file = options.file
  const tempId = insertUploadingPlaceholder(file)
  uploadProgress.value = 1
  uploadProgressText.value = '上传中 1%'

  try {
    const response = await documentAPI.upload(file, {
      onUploadProgress: (event) => {
        if (!event.total) return
        const percent = Math.min(99, Math.max(1, Math.round((event.loaded / event.total) * 100)))
        uploadProgress.value = percent
        uploadProgressText.value = percent >= 99 ? '文件已上传，正在解析文档...' : `上传中 ${percent}%`
      }
    })
    uploadProgress.value = 100
    uploadProgressText.value = '文档已入库'
    removeUploadingPlaceholder(tempId)
    upsertDocumentRow(response.data)
    delete docReviewStatus[response.data.id]
    await loadDocuments()
    options.onSuccess?.(response.data)
    ElMessage.success('上传成功')
  } catch (error) {
    removeUploadingPlaceholder(tempId)
    options.onError?.(error)
    ElMessage.error(`上传失败: ${getAPIErrorMessage(error)}`)
  } finally {
    setTimeout(() => {
      uploadProgress.value = 0
      uploadProgressText.value = ''
    }, 600)
  }
}

function handleRulesImport(response) {
  ElMessage.success(`成功导入 ${response.message || '多条'} 规则`)
  loadRules()
}

async function startReview(documentId) {
  if (isTemporaryDocumentId(documentId)) {
    ElMessage.warning('文档仍在上传处理中，请等待上传完成后再开始审核')
    return
  }
  try {
    const provider = reviewMode.value === 'hybrid' && selectedProvider.value
      ? selectedProvider.value
      : null
    const response = await reviewAPI.create(documentId, reviewMode.value, provider)
    const reviewId = response.data.review_id
    const statusMessage = response.data.message || '审核任务已创建，正在初始化...'

    if (response.data.status === 'completed') {
      await loadReviewIssues(reviewId)
      await loadReviews()
      docReviewStatus[documentId] = {
        review_id: reviewId,
        status: 'completed',
        progress: 100,
        message: statusMessage,
        summary: JSON.stringify({ total: (taskIssues[reviewId] || []).length, cache_hit: true }),
        total_issues: (taskIssues[reviewId] || []).length
      }
      ElMessage.success(statusMessage)
      return
    }
    
    docReviewStatus[documentId] = {
      review_id: reviewId,
      status: 'running',
      progress: 0,
      message: statusMessage
    }
    upsertReviewSnapshot(documentReviews, {
      id: reviewId,
      document_id: documentId,
      status: 'running',
      mode: reviewMode.value,
      progress: { status: 'running', progress: 0, message: statusMessage },
      total_issues: 0,
      created_at: new Date().toISOString(),
    })
    syncReviewsPolling()
    await loadReviews()
  } catch (error) {
    docReviewStatus[documentId] = {
      status: 'failed',
      progress: 0,
      message: getAPIErrorMessage(error, '创建审核任务失败')
    }
    ElMessage.error(`审核失败，请重试: ${getAPIErrorMessage(error, '创建审核任务失败')}`)
  }
}

function isTemporaryDocumentId(documentId) {
  return String(documentId || '').startsWith('uploading-')
}

function canStartReview(document) {
  if (!document || isTemporaryDocumentId(document.id)) return false
  return docReviewStatus[document.id]?.status !== 'running'
}

async function loadReviewIssues(reviewId) {
  try {
    const response = await reviewAPI.getIssues(reviewId)
    const data = response.data || []
    issues.value = data
    taskIssues[reviewId] = data
    if (!rowFilters[reviewId]) {
      rowFilters[reviewId] = { keyword: '', severity: '', category: '' }
    }
  } catch (error) {
    taskIssues[reviewId] = []
    ElMessage.error('加载问题列表失败')
  }
}

// 行展开时加载问题列表
async function handleRowExpand(row, expandedRows) {
  if (!row) return
  if (taskIssues[row.id] === undefined) {
    await loadReviewIssues(row.id)
  }
}

// 计算任务问题统计
function computeIssueStats(issueList) {
  const stats = { fatal: 0, serious: 0, general: 0, suggestion: 0 }
  issueList.forEach(issue => {
    if (stats[issue.severity] !== undefined) stats[issue.severity]++
  })
  return [
    { label: '致命', value: stats.fatal, class: 'stat-fatal' },
    { label: '严重', value: stats.serious, class: 'stat-serious' },
    { label: '一般', value: stats.general, class: 'stat-general' },
    { label: '建议', value: stats.suggestion, class: 'stat-suggestion' }
  ]
}

// 筛选任务问题
function filterTaskIssues(taskId) {
  const list = taskIssues[taskId] || []
  const filter = rowFilters[taskId] || { keyword: '', severity: '', category: '' }
  let result = [...list]
  if (filter.keyword) {
    const kw = filter.keyword.toLowerCase()
    result = result.filter(issue =>
      (issue.original_text && issue.original_text.toLowerCase().includes(kw)) ||
      (issue.context && issue.context.toLowerCase().includes(kw)) ||
      (issue.chapter && issue.chapter.toLowerCase().includes(kw))
    )
  }
  if (filter.severity) {
    result = result.filter(issue => issue.severity === filter.severity)
  }
  if (filter.category) {
    result = result.filter(issue => issue.category === filter.category)
  }
  return result
}

function resetRowFilter(taskId) {
  if (rowFilters[taskId]) {
    rowFilters[taskId].keyword = ''
    rowFilters[taskId].severity = ''
    rowFilters[taskId].category = ''
  }
}

function exportTaskReport(row) {
  try {
    const taskId = row.id
    const taskIssuesList = taskIssues[taskId] || []
    const stats = computeIssueStats(taskIssuesList)

    let html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>审核报告 - ${row.document_name || ''}</title>
<style>body{font-family:"Microsoft YaHei",Arial,sans-serif;margin:30px}
.header{text-align:center;margin-bottom:30px;border-bottom:2px solid #333;padding-bottom:20px}
.report-info{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:20px;padding:15px;background:#f8f9fa;border-radius:8px}
.stats-row{display:flex;gap:20px;margin-bottom:20px}
.stat-item{padding:8px 16px;border-radius:20px;font-weight:bold}
.stat-fatal{background:#fef0f0;color:#dc3545}
.stat-serious{background:#fff7ed;color:#fd7e14}
.stat-general{background:#fffbeb;color:#ffc107}
.stat-suggestion{background:#ecfdf5;color:#10b981}
table{width:100%;border-collapse:collapse;margin-top:20px}
th,td{border:1px solid #ddd;padding:12px;text-align:left}
th{background:#f8f9fa;font-weight:bold}
.issue-row:hover{background:#f8f9fa}
.context-text{font-size:13px;color:#666}
</style></head><body>
<div class="header"><h1>智能技术文档审核报告</h1>
<p>生成时间：${new Date().toLocaleString('zh-CN')}</p></div>
<div class="report-info">
<div><strong>任务 ID：</strong>${row.id}</div>
<div><strong>文档名称：</strong>${row.document_name || '-'}</div>
<div><strong>审核模式：</strong>${row.mode || '-'}</div>
<div><strong>审核状态：</strong>${row.status === 'completed' ? '已完成' : row.status === 'failed' ? '失败' : '进行中'}</div>
<div><strong>问题总数：</strong>${row.total_issues || 0}</div>
<div><strong>创建时间：</strong>${formatDateTime(row.created_at)}</div>
</div>
<h2>问题统计</h2><div class="stats-row">`
    stats.forEach(s => {
      html += `<span class="stat-item stat-${s.class.split('-')[1]}">${s.label}: ${s.value}</span>`
    })
    html += `</div><h2>问题详情</h2><table><thead><tr>
<th>级别</th><th>分类</th><th>章节</th><th>原文</th><th>上下文</th><th>修改建议</th><th>审核依据</th></tr></thead><tbody>`

    filterTaskIssues(taskId).forEach(issue => {
      html += `<tr class="issue-row"><td>${getSeverityLabel(issue.severity)}</td>
<td>${issue.category || '-'}</td><td>${issue.chapter || '-'}</td>
<td>${issue.original_text || '-'}</td>
<td class="context-text">${issue.context || '-'}</td>
<td>${issue.suggestion || '-'}</td><td>${issue.audit_basis || '-'}</td></tr>`
    })

    html += '</tbody></table></body></html>'

    const blob = new Blob([html], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `audit_report_${row.id}_${new Date().toISOString().slice(0, 10)}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (error) {
    ElMessage.error('导出失败: ' + error.message)
  }
}

function resultButtonLabel(fileType) {
  if (fileType === 'docx') return '批注Word'
  if (fileType === 'xlsx') return '下载Excel'
  return '下载结果'
}

function reviewModeLabel(mode) {
  return {
    rule: '快速审核',
    hybrid: '完整审核',
    ai: 'AI审核',
    'compare:both': '对比审核',
    'compare:numbers': '对比审核',
    'compare:steps': '对比审核'
  }[mode] || mode || '-'
}

function compareLevelTagType(level) {
  return {
    P0: 'danger',
    P1: 'warning',
    P2: 'info',
    一致: 'success'
  }[level] || 'info'
}

function shouldShowDownloadResult(row) {
  if (String(row?.mode || '').startsWith('compare:')) return false
  return String(row?.document_file_type || '').toLowerCase() !== 'md'
}

function parseMaybeJson(value) {
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (!text || (text[0] !== '{' && text[0] !== '[')) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function reviewProgressText(progress) {
  const parsed = parseMaybeJson(progress?.message)
  if (parsed && typeof parsed === 'object') {
    return parsed.message || parsed.step || '审核进行中...'
  }
  return progress?.message || progress?.step || '审核进行中...'
}

function reviewFailureText(review) {
  const parsed = parseMaybeJson(review?.summary)
  if (parsed && typeof parsed === 'object') {
    return parsed.message || '审核失败'
  }
  return review?.summary || '审核失败'
}

function reviewCompletionText(review) {
  const parsed = parseMaybeJson(review?.summary ?? review?.message)
  if (String(review?.mode || '').startsWith('compare:')) {
    const total = parsed?.total_issue_count ?? review?.total_issues ?? 0
    return `对比完成，共 ${total} 项差异`
  }
  const matchedTotal = typeof review?.message === 'string'
    ? review.message.match(/(\d+)\s*个问题/)
    : null
  const total = parsed?.total ?? review?.total_issues ?? (matchedTotal ? Number(matchedTotal[1]) : 0)
  const prefix = parsed?.cache_hit ? '缓存命中，' : ''
  return `${prefix}审核完成，共 ${total} 个问题`
}

function reviewStatusText(statusInfo) {
  if (!statusInfo) return '未审核'
  if (statusInfo.status === 'completed') {
    return reviewCompletionText(statusInfo)
  }
  if (statusInfo.status === 'failed') {
    return reviewFailureText(statusInfo)
  }
  return reviewProgressText(statusInfo)
}

function clearFilters() {
  filterKeyword.value = ''
  filterSeverity.value = ''
  filterCategory.value = ''
}

// 打开问题详情弹窗
async function openIssueDialog(row) {
  currentTaskId.value = row.id
  issueFilter.keyword = ''
  issueFilter.category = ''
  issueFilter.status = ''
  issueFilter.severity = ''
  selectedIssueIds.value = []
  showAuditTraces.value = false
  auditTraces.value = []
  coverageData.value = null
  showCoverage.value = false
  terminologyData.value = null
  showTerminology.value = false
  issueDialogVisible.value = true
  if (taskIssues[row.id] === undefined) {
    await loadReviewIssues(row.id)
  }
  loadAuditTraces(row.id)
  loadCoverage(row.id)
  loadTerminology(row.id)
}

// 通过文档ID打开问题详情弹窗
async function openIssueDialogByDoc(documentId) {
  const status = docReviewStatus[documentId]
  if (!status || !status.review_id) {
    ElMessage.warning('暂无审核结果')
    return
  }
  const reviewId = status.review_id
  currentTaskId.value = reviewId
  issueFilter.keyword = ''
  issueFilter.category = ''
  issueFilter.status = ''
  issueFilter.severity = ''
  selectedIssueIds.value = []
  showAuditTraces.value = false
  auditTraces.value = []
  coverageData.value = null
  showCoverage.value = false
  terminologyData.value = null
  showTerminology.value = false
  issueDialogVisible.value = true
  if (taskIssues[reviewId] === undefined) {
    await loadReviewIssues(reviewId)
  }
  loadAuditTraces(reviewId)
  loadCoverage(reviewId)
  loadTerminology(reviewId)
}

async function loadAuditTraces(reviewId) {
  try {
    const response = await reviewAPI.getTraces(reviewId)
    auditTraces.value = response.data?.traces || []
  } catch (e) {
    console.log('AI调用追踪加载失败:', e)
    auditTraces.value = []
  }
}

async function loadCoverage(reviewId) {
  try {
    const response = await reviewAPI.getCoverage(reviewId)
    coverageData.value = response.data
  } catch (e) {
    console.log('审核覆盖率加载失败:', e)
    coverageData.value = null
  }
}

async function loadTerminology(reviewId) {
  try {
    const response = await reviewAPI.getTerminology(reviewId)
    terminologyData.value = response.data
  } catch (e) {
    console.log('术语匹配率分析加载失败:', e)
    terminologyData.value = null
  }
}

async function openParsedTextDialog() {
  if (!currentTaskId.value) {
    ElMessage.warning('请先打开审核任务')
    return
  }
  parsedTextDialogVisible.value = true
  parsedTextLoading.value = true
  try {
    const response = await reviewAPI.getParsedText(currentTaskId.value)
    parsedTextMeta.value = response.data || null
    parsedTextContent.value = response.data?.content || ''
  } catch (error) {
    ElMessage.error(`加载解析文本失败: ${getAPIErrorMessage(error)}`)
  } finally {
    parsedTextLoading.value = false
  }
}

async function compareGoldAnswer(options) {
  if (!currentTaskId.value) {
    ElMessage.warning('请先打开审核任务')
    return
  }
  const file = options.file
  if (!file || !/\.xlsx?$/i.test(file.name || '')) {
    ElMessage.warning('请上传 Excel 标准答案文件')
    return
  }
  goldCompareDialogVisible.value = true
  goldCompareLoading.value = true
  goldCompareResult.value = null
  try {
    const response = await reviewAPI.compareGold(currentTaskId.value, file)
    goldCompareResult.value = response.data
    ElMessage.success('标准答案对比完成')
  } catch (error) {
    ElMessage.error(`标准答案对比失败: ${getAPIErrorMessage(error)}`)
  } finally {
    goldCompareLoading.value = false
  }
}

async function downloadReviewResultByDoc(document) {
  const status = docReviewStatus[document.id]
  if (!status || !status.review_id) {
    ElMessage.warning('暂无审核结果')
    return
  }
  await downloadReviewResult({
    id: status.review_id,
    document_name: document.filename,
    document_file_type: document.file_type
  })
}

// 单个问题判定
async function judgeSingle(issue, status) {
  try {
    await reviewAPI.updateIssue(issue.id, status)
    if (status === 'false_positive') {
      removeLocalIssues(currentTaskId.value, [issue.id])
    } else {
      issue.status = status
    }
    ElMessage.success(`已标记为${statusLabel(status)}`)
  } catch (err) {
    ElMessage.error('判定失败: ' + (err.response?.data?.detail || err.message))
  }
}

function removeLocalIssues(taskId, issueIds) {
  const removeIds = new Set(issueIds)
  taskIssues[taskId] = (taskIssues[taskId] || []).filter(issue => !removeIds.has(issue.id))
  issues.value = issues.value.filter(issue => !removeIds.has(issue.id))
  selectedIssueIds.value = selectedIssueIds.value.filter(id => !removeIds.has(id))
}

function normalizeIssueText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim().toLowerCase()
}

function similarIssueSignature(issue) {
  return [
    normalizeIssueText(issue.rule),
    normalizeIssueText(issue.category),
    normalizeIssueText(issue.suggestion || issue.description)
  ].join('|')
}

async function markSimilarIssuesFalsePositive(issue) {
  const signature = similarIssueSignature(issue)
  const similarIssues = filteredDialogIssues.value.filter(item => {
    const status = item.status || 'pending'
    return status === 'pending' && similarIssueSignature(item) === signature
  })

  if (similarIssues.length === 0) {
    ElMessage.info('没有待处理的同类问题')
    return
  }

  try {
    await ElMessageBox.confirm(`将 ${similarIssues.length} 条同类问题标记为误报, 是否继续?`, '同类误报', {
      confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }

  try {
    const ids = similarIssues.map(item => item.id)
    const judgments = ids.map(id => ({ issue_id: id, status: 'false_positive' }))
    const res = await reviewAPI.batchJudge(currentTaskId.value, judgments)
    removeLocalIssues(currentTaskId.value, ids)
    ElMessage.success(`已标记 ${res.data.updated} 条同类问题为误报`)
  } catch (err) {
    ElMessage.error('同类误报失败: ' + (err.response?.data?.detail || err.message))
  }
}

function escapeRegexLiteral(text) {
  return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function nextReviewRuleNo() {
  const now = new Date()
  const stamp = [
    String(now.getFullYear()).slice(2),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0')
  ].join('')
  return `REV-${stamp}`
}

function openTransferRuleDialog(issue) {
  transferRuleSourceIssue.value = issue
  const originalText = issue.original_text || ''
  const category = issue.category || '其他'
  transferRuleForm.value = {
    rule_no: nextReviewRuleNo(),
    category,
    description: issue.description || `${category}问题：${originalText || issue.context || ''}`,
    regex: originalText ? escapeRegexLiteral(originalText) : '',
    example: originalText || issue.context || '',
    suggestion: issue.suggestion || '',
    audit_basis: issue.audit_basis || '审核确认问题转入',
    language: /[\u4e00-\u9fa5]/.test(`${originalText} ${issue.context || ''}`) ? 'both' : 'en'
  }
  transferRuleDialogVisible.value = true
}

async function saveTransferredRule() {
  try {
    if (!transferRuleForm.value.rule_no) {
      ElMessage.error('请填写规则编号')
      return
    }
    if (!transferRuleForm.value.category) {
      ElMessage.error('请填写分类')
      return
    }
    if (!transferRuleForm.value.description) {
      ElMessage.error('请填写规则描述')
      return
    }
    await rulesAPI.create(transferRuleForm.value)
    if (transferRuleSourceIssue.value) {
      transferRuleSourceIssue.value.transferred_to_rule = true
    }
    transferRuleDialogVisible.value = false
    ElMessage.success('已转入规则库')
    if (currentView.value === 'rules') {
      await loadRules()
    }
  } catch (error) {
    ElMessage.error('转入规则库失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 批量设置状态
async function batchSetStatus(status) {
  if (selectedIssueIds.value.length === 0) {
    ElMessage.warning('请先选择问题')
    return
  }
  try {
    const judgments = selectedIssueIds.value.map(id => ({ issue_id: id, status }))
    const res = await reviewAPI.batchJudge(currentTaskId.value, judgments)
    // 更新本地状态
    const list = taskIssues[currentTaskId.value] || []
    const selectedIds = [...selectedIssueIds.value]
    if (status === 'false_positive') {
      removeLocalIssues(currentTaskId.value, selectedIds)
    } else {
      for (const i of list) {
        if (selectedIds.includes(i.id)) i.status = status
      }
    }
    ElMessage.success(`已更新 ${res.data.updated} 条问题为${statusLabel(status)}`)
  } catch (err) {
    ElMessage.error('批量判定失败: ' + (err.response?.data?.detail || err.message))
  }
}

// 一键确认所有未判定问题
async function batchConfirmAll(taskId) {
  if (!taskId) {
    ElMessage.warning('请先打开审核任务')
    return
  }

  const task = reviews.value.find(r => r.id === taskId)
  if (task && task.status !== 'completed') {
    ElMessage.warning('任务完成后才能一键确认')
    return
  }

  if (taskIssues[taskId] === undefined) {
    await loadReviewIssues(taskId)
  }

  const list = taskIssues[taskId] || []
  const pending = list.filter(i => !i.status || i.status === 'pending')
  if (pending.length === 0) {
    ElMessage.info('没有待确认的问题')
    return
  }
  try {
    await ElMessageBox.confirm(`将确认 ${pending.length} 条问题为有效问题, 是否继续?`, '一键确认', {
      confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  try {
    const judgments = pending.map(i => ({ issue_id: i.id, status: 'confirmed' }))
    const res = await reviewAPI.batchJudge(taskId, judgments)
    for (const i of pending) i.status = 'confirmed'
    ElMessage.success(`已确认 ${res.data.updated} 条问题`)
  } catch (err) {
    ElMessage.error('批量确认失败: ' + (err.response?.data?.detail || err.message))
  }
}

// 导出 HTML 报告 (调用后端接口)
async function exportReviewHtml(taskId) {
  try {
    const res = await reviewAPI.exportHtml(taskId)
    const blob = new Blob([res.data], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `审核报告_${taskId}_${new Date().toISOString().slice(0, 10)}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (err) {
    ElMessage.error('导出失败: ' + (err.response?.data?.detail || err.message))
  }
}

async function downloadReviewResult(row) {
  try {
    const fileType = row.document_file_type || row.file_type || ''
    const res = await reviewAPI.exportResult(row.id)
    const blobType = fileType === 'docx'
      ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      : fileType === 'xlsx'
        ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        : 'text/html;charset=utf-8'
    const blob = new Blob([res.data], { type: blobType })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const baseName = (row.document_name || `task_${row.id}`).replace(/\.[^.]+$/, '')
    const suffix = fileType === 'docx' ? '.docx' : fileType === 'xlsx' ? '.xlsx' : '.html'
    link.download = `${baseName}_审核结果_${new Date().toISOString().slice(0, 10)}${suffix}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success(fileType === 'docx' ? 'Word审核结果下载成功' : fileType === 'xlsx' ? 'Excel审核结果下载成功' : 'HTML审核报告导出成功')
  } catch (err) {
    ElMessage.error('导出失败: ' + (err.response?.data?.detail || err.message))
  }
}

function onRuleSelectionChange(rows) {
  selectedRules.value = rows.map(row => row.id)
}

function languageLabel(language) {
  return { cn: '中文', en: '英文', both: '中英通用' }[language] || language || '-'
}

function onIssueSelectionChange(rows) {
  selectedIssueIds.value = rows.map(r => r.id)
}

function severityTagType(sev) {
  return { fatal: 'danger', serious: 'warning', general: 'info', suggestion: 'success' }[sev] || 'info'
}
function severityLabel(sev) {
  return { fatal: '致命', serious: '严重', general: '一般', suggestion: '建议' }[sev] || sev || '-'
}
function statusTagType(s) {
  return { confirmed: 'success', false_positive: 'info', pending: 'warning' }[s || 'pending'] || 'warning'
}
function statusLabel(s) {
  return { confirmed: '已确认', false_positive: '误报' }[s] || '待确认'
}

// AI追踪面板辅助函数
function providerTagType(provider) {
  const p = (provider || '').toLowerCase()
  if (p.includes('qwen')) return ''
  if (p.includes('kimi')) return 'success'
  if (p.includes('deepseek')) return 'primary'
  return 'info'
}
function traceStatusTagType(status) {
  return { success: 'success', timeout: 'warning', error: 'danger', pending: 'info' }[status] || 'info'
}
function traceStatusLabel(status) {
  return { success: '成功', timeout: '超时', error: '失败', pending: '等待中' }[status] || status || '-'
}
function formatLatency(ms) {
  if (!ms && ms !== 0) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}

// 覆盖率面板辅助函数
function coverageQualityType(score) {
  if (score >= 80) return 'success'
  if (score >= 60) return 'warning'
  return 'danger'
}
function terminologyQualityType(score) {
  if (score >= 80) return 'success'
  if (score >= 60) return 'warning'
  return 'danger'
}
function matchTypeTag(type) {
  return { perfect: 'success', fuzzy_high: '', fuzzy: 'warning', fuzzy_low: 'warning', partial: 'danger' }[type] || 'info'
}
function matchTypeLabel(type) {
  return { perfect: '100% 精确', fuzzy_high: '85-99%', fuzzy: '75-84%', fuzzy_low: '50-74%', partial: '<50%' }[type] || type
}
function severityColor(sev) {
  return { fatal: '#F56C6C', serious: '#E6A23C', general: '#409EFF', suggestion: '#909399' }[sev] || '#909399'
}
function severityLabelCN(sev) {
  return { fatal: '致命', serious: '严重', general: '一般', suggestion: '建议' }[sev] || sev || '-'
}

async function viewDocument(id) {
  try {
    await documentAPI.get(id)
    ElMessage.info('已加载文档信息')
  } catch (error) {
    ElMessage.error('查看失败')
  }
}

async function deleteDocument(id) {
  try {
    await documentAPI.delete(id)
    loadDocuments()
    ElMessage.success('删除成功')
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

function editRule(row) {
  editingRule.value = row
    ruleForm.value = {
      rule_no: row.rule_no || '',
      category: row.category || '',
      description: row.description || '',
      regex: row.regex || '',
      example: row.example || '',
      suggestion: row.suggestion || '',
      audit_basis: row.audit_basis || '',
      language: row.language || 'both'
    }
  showRuleDialog.value = true
}

async function saveRule() {
  try {
    if (!ruleForm.value.rule_no) {
      ElMessage.error('请填写规则编号')
      return
    }
    if (!ruleForm.value.category) {
      ElMessage.error('请填写分类')
      return
    }
    if (!ruleForm.value.description) {
      ElMessage.error('请填写规则描述')
      return
    }
    
    if (editingRule.value) {
      await rulesAPI.update(editingRule.value.id, ruleForm.value)
      ElMessage.success('更新成功')
    } else {
      await rulesAPI.create(ruleForm.value)
      ElMessage.success('添加成功')
    }
    showRuleDialog.value = false
    editingRule.value = null
    ruleForm.value = { rule_no: '', category: '', description: '', regex: '', example: '', suggestion: '', audit_basis: '', language: 'both' }
    loadRules()
  } catch (error) {
    ElMessage.error('保存失败: ' + (error.response?.data?.detail || error.message))
  }
}

async function deleteRule(id) {
  try {
    await ElMessageBox.confirm('确定要删除这条规则吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await rulesAPI.delete(id)
    loadRules()
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

async function batchDeleteRules() {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedRules.value.length} 条规则吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await rulesAPI.batchDelete(selectedRules.value)
    selectedRules.value = []
    loadRules()
    ElMessage.success('批量删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

async function exportRules() {
  try {
    const response = await rulesAPI.export()
    const dataStr = JSON.stringify(response.data, null, 2)
    const blob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `rules_export_${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error) {
    ElMessage.error('导出失败')
  }
}

function handleSortChange({ prop, order }) {
  sortField.value = prop
  sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  
  rules.value.sort((a, b) => {
    let aVal = a[prop]
    let bVal = b[prop]
    
    if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase()
      bVal = bVal.toLowerCase()
    }
    
    if (sortOrder.value === 'asc') {
      return aVal > bVal ? 1 : -1
    } else {
      return aVal < bVal ? 1 : -1
    }
  })
}

async function loadReport(id) {
  try {
    const report = reviews.value.find(r => r.id === id) || {}
    currentReport.value = report
    const response = await reviewAPI.getIssues(id)
    issues.value = response.data || []
    showReport.value = true
  } catch (error) {
    ElMessage.error('加载报告失败')
  }
}

async function exportReport() {
  try {
    if (!currentReport.value?.id) {
      ElMessage.warning('当前没有可导出的审核任务')
      return
    }
    const response = await reviewAPI.exportHtml(currentReport.value.id)
    const blob = new Blob([response.data], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const baseName = (currentReport.value.document_name || `task_${currentReport.value.id}`).replace(/\.[^.]+$/, '')
    link.download = `${baseName}_审核报告_${new Date().toISOString().slice(0, 10)}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (error) {
    ElMessage.error('导出失败: ' + error.message)
  }
}

function getSeverityType(severity) {
  const types = { fatal: 'danger', serious: 'warning', general: 'info', suggestion: 'success' }
  return types[severity] || 'info'
}

function getSeverityLabel(severity) {
  const labels = { fatal: '致命', serious: '严重', general: '一般', suggestion: '建议' }
  return labels[severity] || severity
}

function renderIssueContext(issue, mode = '') {
  if (String(mode || '').startsWith('compare:')) {
    return renderCompareIssueContext(issue)
  }
  return highlightOriginalText(issue?.context, issue?.original_text)
}

function renderIssueOriginalCell(issue, mode = '') {
  if (String(mode || '').startsWith('compare:')) {
    return renderCompareIssueContext(issue)
  }

  const originalText = normalizeDisplayText(issue?.original_text)
  const contextText = normalizeDisplayText(issue?.context)
  if (!originalText) {
    return highlightOriginalText(contextText, issue?.original_text)
  }

  return `<div class="issue-original-main">${highlightOriginalText(originalText, originalText)}</div>`
}

function normalizeDisplayText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim()
}

const currentTaskMode = computed(() => {
  const currentReview = reviews.value.find(item => item.id === currentTaskId.value)
  return currentReview?.mode || currentReport.value?.mode || ''
})

function renderCompareIssueContext(issue) {
  const entries = parseCompareIssueContext(issue?.context)
  const mainEntry = entries.find((item) => item.label === '主文档') || { label: '主文档', value: '-' }
  const referenceEntries = entries.filter((item) => item.label !== '主文档')
  const baseReference = referenceEntries.find((item) => item.value && item.value !== '-')?.value || ''
  const mainDiff = buildDiffMarkup(mainEntry.value, baseReference)
  const rows = [
    `<div class="compare-context-row main"><div class="compare-context-label">${escapeHtml(mainEntry.label)}</div><div class="compare-context-value">${mainDiff.mainHtml}</div></div>`
  ]
  for (const entry of referenceEntries) {
    const diff = buildDiffMarkup(mainEntry.value, entry.value)
    rows.push(`<div class="compare-context-row reference"><div class="compare-context-label">${escapeHtml(entry.label)}</div><div class="compare-context-value">${diff.referenceHtml}</div></div>`)
  }
  return `<div class="compare-context-block">${rows.join('')}</div>`
}

function parseCompareIssueContext(context) {
  const lines = String(context || '')
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter(Boolean)

  const entries = []
  for (const line of lines) {
    const match = line.match(/^([^：:]+)[：:]\s*([\s\S]*)$/)
    if (!match) continue
    entries.push({
      label: match[1].trim(),
      value: (match[2] || '').trim() || '-'
    })
  }

  if (!entries.length) {
    return [{ label: '主文档', value: String(context || '').trim() || '-' }]
  }
  return entries
}

function buildDiffMarkup(mainText, referenceText) {
  const left = String(mainText || '').trim()
  const right = String(referenceText || '').trim()
  const prefixLength = commonPrefixLength(left, right)
  const suffixLength = commonSuffixLength(left, right, prefixLength)
  return {
    mainHtml: renderDiffText(left, prefixLength, suffixLength),
    referenceHtml: renderDiffText(right, prefixLength, suffixLength)
  }
}

function renderCompareMainValue(row) {
  const mainValue = String(row?.main_value || '').trim()
  const referenceValue = firstCompareReferenceValue(row)
  const diff = buildDiffMarkup(mainValue, referenceValue)
  return diff.mainHtml
}

function renderCompareReferenceValue(row, index) {
  const item = row?.reference_values?.[index]
  return String(item?.value || '-').trim() || '-'
}

function firstCompareReferenceValue(row) {
  const firstValue = row?.reference_values?.find((item) => item?.value && item.value !== '-')?.value
  if (firstValue) return String(firstValue).trim()
  return simplifyReferenceValue(row?.reference_summary || row?.reference_value)
}

function simplifyReferenceValue(value) {
  const text = String(value || '').trim()
  if (!text || text === '-') return ''
  const noMajority = text.replace(/（众数[^）]*）/g, '').trim()
  const firstVariant = noMajority.split('；')[0] || noMajority
  return firstVariant.trim()
}

function commonPrefixLength(left, right) {
  const maxLength = Math.min(left.length, right.length)
  let index = 0
  while (index < maxLength && left[index] === right[index]) {
    index += 1
  }
  return index
}

function commonSuffixLength(left, right, prefixLength = 0) {
  const maxLength = Math.min(left.length, right.length) - prefixLength
  let count = 0
  while (
    count < maxLength &&
    left[left.length - 1 - count] === right[right.length - 1 - count]
  ) {
    count += 1
  }
  return count
}

function renderDiffText(text, prefixLength, suffixLength) {
  if (!text) {
    return '<span class="compare-empty">-</span>'
  }
  const safePrefix = Math.min(prefixLength, text.length)
  const maxSuffix = Math.max(0, text.length - safePrefix)
  const safeSuffix = Math.min(suffixLength, maxSuffix)
  const diffStart = safePrefix
  const diffEnd = text.length - safeSuffix
  const before = text.slice(0, diffStart)
  const changed = text.slice(diffStart, diffEnd)
  const after = text.slice(diffEnd)
  if (!changed && before === text) {
    return escapeHtml(text)
  }
  return `${escapeHtml(before)}${changed ? `<span class="compare-diff-mark">${escapeHtml(changed)}</span>` : ''}${escapeHtml(after)}`
}

function highlightOriginalText(context, originalText) {
  if (!context && !originalText) return '-'
  
  const text = context || originalText || ''
  const escapedText = escapeHtml(text)
  
  if (!originalText) {
    return escapedText
  }
  
  const exactRegex = new RegExp(`(${escapeRegExp(originalText)})`, 'gi')
  if (exactRegex.test(text)) {
    return highlightMatches(text, exactRegex)
  }

  const compactOriginal = String(originalText).replace(/\s+/g, '')
  if (compactOriginal.length > 1 && compactOriginal.length <= 80) {
    const flexiblePattern = compactOriginal.split('').map(escapeRegExp).join('\\s*')
    const flexibleRegex = new RegExp(`(${flexiblePattern})`, 'gi')
    if (flexibleRegex.test(text)) {
      return highlightMatches(text, flexibleRegex)
    }
  }

  return escapedText
}

function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function highlightMatches(text, regex) {
  regex.lastIndex = 0
  let result = ''
  let lastIndex = 0
  for (const match of String(text).matchAll(regex)) {
    const matchText = match[0]
    const matchIndex = match.index ?? 0
    result += escapeHtml(String(text).slice(lastIndex, matchIndex))
    result += `<span class="highlight-problem">${escapeHtml(matchText)}</span>`
    lastIndex = matchIndex + matchText.length
  }
  result += escapeHtml(String(text).slice(lastIndex))
  return result
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

onUnmounted(() => {
  stopReviewsPolling()
})
</script>

<style>
.review-container {
  padding: 20px;
}

.review-subtabs {
  margin-top: -4px;
}

.page-title {
  margin-bottom: 20px;
  color: #333;
  font-size: 20px;
  font-weight: 600;
}

.upload-section,
.table-section,
.issues-section,
.report-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.upload-tip {
  color: #909399;
  font-size: 12px;
  margin-top: 6px;
}

.review-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
}

.review-mode-label {
  font-size: 14px;
  color: #334155;
  font-weight: 600;
}

.review-mode-hint {
  font-size: 13px;
  color: #64748b;
}

.ai-model-toolbar {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
}

.compare-audit-section {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.compare-upload-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.compare-upload-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 16px;
  background: #f8fafc;
}

.compare-upload-title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.compare-mode-toolbar {
  margin-top: 0;
}

.compare-action-row {
  display: flex;
  justify-content: flex-start;
}

.compare-result-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.compare-result-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.compare-result-toolbar-text {
  font-size: 13px;
  color: #475569;
}

.compare-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.compare-summary-card {
  padding: 14px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.compare-summary-name {
  margin-top: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  word-break: break-word;
}

.compare-result-block h4 {
  margin: 0 0 10px;
  font-size: 14px;
  color: #334155;
}

.compare-table-wrap {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
}

.compare-table-wrap :deep(.el-table) {
  min-width: max-content;
}

.compare-table-wrap :deep(.el-table__header-wrapper),
.compare-table-wrap :deep(.el-table__body-wrapper),
.compare-table-wrap :deep(.el-scrollbar__wrap) {
  overflow-x: visible !important;
}

.compare-table-wrap :deep(.el-table__fixed),
.compare-table-wrap :deep(.el-table__fixed-right) {
  box-shadow: none;
}

.compare-table-wrap :deep(.el-table__fixed-right::before),
.compare-table-wrap :deep(.el-table__fixed::before) {
  background-color: #dbe4ee;
}

.compare-diff-table :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.compare-conclusion-cell {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  line-height: 1.6;
}

.compare-main-value {
  color: #1f2937;
}

.progress-section {
  margin-top: 15px;
  width: 260px;
}

.progress-text {
  display: block;
  text-align: left;
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}

.table-section h3,
.issues-section h3,
.report-section h3 {
  margin-bottom: 15px;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.table-header-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.upload-btn {
  display: inline-block;
}

.filter-section {
  display: flex;
  gap: 12px;
  margin-bottom: 15px;
  flex-wrap: wrap;
}

.filter-input {
  width: 200px;
}

.filter-select {
  width: 150px;
}

.issue-stats {
  margin-bottom: 15px;
}

.stat-badge {
  display: inline-block;
  padding: 5px 12px;
  border-radius: 20px;
  margin-right: 10px;
  font-size: 14px;
}

.stat-fatal { background: #fef0f0; color: #dc3545; }
.stat-serious { background: #fff7ed; color: #fd7e14; }
.stat-general { background: #fffbeb; color: #ffc107; }
.stat-suggestion { background: #ecfdf5; color: #10b981; }

.context-text {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  word-break: break-all;
}

.suggestion-wrap {
  display: block;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.5;
}

.issue-detail-table :deep(.el-table__cell) {
  vertical-align: top;
}

.issue-detail-table :deep(.suggestion-column .cell) {
  overflow: visible;
  white-space: normal;
}

.suggestion-summary {
  margin-top: 4px;
  color: #475467;
  font-size: 13px;
  white-space: pre-wrap;
}

.suggestion-overview {
  color: #101828;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.6;
}

.suggestion-diff {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fcfcfd;
  border: 1px solid #eaecf0;
  font-size: 12px;
  color: #4b5563;
}

.suggestion-diff-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.suggestion-diff-row + .suggestion-diff-row {
  margin-top: 4px;
}

.suggestion-diff-label {
  flex: 0 0 30px;
  color: #6b7280;
}

.diff-remove {
  color: #b42318;
  background: #fef3f2;
  border-radius: 4px;
  padding: 0 2px;
  text-decoration: line-through;
}

.diff-add {
  color: #b42318;
  background: #fff1f3;
  border-radius: 4px;
  padding: 0 2px;
  font-weight: 600;
}

.issue-action-cell {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.issue-inline-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.provider-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  align-items: center;
}

.provider-tag-item {
  font-size: 10px !important;
  padding: 0 5px !important;
  height: 18px !important;
  line-height: 18px !important;
}

.report-content {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 16px;
  background: #fafafa;
}

.report-header {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #ebeef5;
  line-height: 1.8;
}

.report-summary {
  margin-bottom: 16px;
}

.report-summary h4,
.report-issues h4 {
  margin-bottom: 10px;
  color: #333;
  font-size: 14px;
  font-weight: 600;
}

.report-summary p {
  color: #606266;
  line-height: 1.7;
}

.report-actions {
  margin-top: 20px;
  text-align: right;
}

.stats-row {
  display: flex;
  gap: 15px;
  flex-wrap: wrap;
}

.stat-item {
  padding: 6px 14px;
  border-radius: 18px;
  font-size: 14px;
}

.stat-item.fatal { background: #fef0f0; color: #dc3545; }
.stat-item.serious { background: #fff7ed; color: #fd7e14; }
.stat-item.general { background: #fffbeb; color: #ffc107; }
.stat-item.suggestion { background: #ecfdf5; color: #10b981; }

/* 行内报告样式 */
.inline-report {
  padding: 16px 24px;
  background: #fafafa;
  border-left: 3px solid #409eff;
}

.inline-report .report-meta {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #fff;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
}

.inline-report .meta-item {
  display: inline-block;
}

.inline-report .report-content {
  background: #fff;
  border-radius: 6px;
  padding: 16px;
}

.inline-report .loading-report {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px;
  color: #909399;
  font-size: 14px;
}

.inline-report .empty-report {
  padding: 24px;
}

.inline-report .issue-detail {
  line-height: 1.7;
}

.inline-report .issue-detail .suggestion-text,
.inline-report .issue-detail .basis-text {
  margin-top: 6px;
  font-size: 13px;
  color: #606266;
}

.inline-report .issue-detail .suggestion-text strong,
.inline-report .issue-detail .basis-text strong {
  color: #409eff;
}

.inline-report .issue-detail .context-text {
  font-size: 13px;
  color: #606266;
  word-break: break-word;
}

.inline-report .filter-section {
  margin: 12px 0;
}

/* 问题详情弹窗样式 */
.issue-dialog-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.audit-trace-panel {
  margin-bottom: 16px;
}
.audit-trace-panel .el-card__header {
  padding: 10px 16px;
  background: #f5f7fa;
}
.trace-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}
.trace-badge {
  margin-left: 4px;
}
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding: 8px 0;
  color: #606266;
}
.task-progress-text {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #606266;
}
.text-error { color: #f56c6c; font-family: 'Courier New', monospace; font-size: 13px; }
.text-success { color: #67c23a; font-size: 13px; }

/* 审核覆盖率面板 */
.coverage-card {
  margin-bottom: 12px;
}
.coverage-card .card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.coverage-summary {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}
.coverage-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 100px;
}
.coverage-label {
  font-size: 12px;
  color: #909399;
}
.coverage-value {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.coverage-detail {
  margin-top: 16px;
  border-top: 1px solid #EBEEF5;
  padding-top: 12px;
}
.coverage-section {
  margin-bottom: 16px;
}
.coverage-section h4 {
  font-size: 13px;
  color: #606266;
  margin: 0 0 8px 0;
  padding-bottom: 4px;
  border-bottom: 1px solid #F2F3F5;
}
.severity-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.severity-bar-row {
  display: flex;
  align-items: center;
}
.severity-bar-label {
  width: 48px;
  font-size: 12px;
  color: #606266;
  text-align: right;
}

.context-cell {
  font-size: 13px;
  line-height: 1.6;
  word-break: break-all;
  color: #303133;
}

.issue-original-main {
  color: #1f2937;
}

.issue-original-snippet {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}

.compare-context-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.compare-context-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.compare-context-row.reference {
  border-color: #fecaca;
}

.compare-context-label {
  padding-top: 1px;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.7;
  color: #475569;
}

.compare-context-row.reference .compare-context-label {
  color: #b42318;
}

.compare-context-value {
  font-size: 13px;
  line-height: 1.7;
  color: #1f2937;
  word-break: break-word;
  white-space: pre-wrap;
}

.compare-diff-mark {
  display: inline;
  color: #b42318;
  font-weight: 700;
}

.compare-empty {
  color: #98a2b3;
  font-style: italic;
}

.highlight-problem {
  color: #1f2937;
  font-weight: 500;
  background-color: #fff4cc;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid #f5e0a3;
}

.gold-upload {
  display: inline-flex;
  vertical-align: middle;
}

.parsed-text-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.gold-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
}

.gold-summary-card {
  padding: 12px 14px;
  border-radius: 8px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
}

.gold-label {
  font-size: 12px;
  color: #909399;
}

.gold-value {
  margin-top: 6px;
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}

.gold-tabs {
  margin-top: 12px;
}

@media (max-width: 900px) {
  .compare-upload-grid,
  .compare-summary-grid,
  .gold-summary-grid {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }

  .compare-result-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 640px) {
  .compare-upload-grid,
  .compare-summary-grid,
  .gold-summary-grid,
  .report-header {
    grid-template-columns: 1fr;
  }
}

/* 术语匹配率分析面板 */
.terminology-card {
  margin-bottom: 12px;
}
.match-distribution {
  margin-bottom: 4px;
}
.dist-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}
.dist-bars {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.dist-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dist-label {
  width: 90px;
  font-size: 11px;
  color: #606266;
  text-align: right;
  flex-shrink: 0;
}
.dist-track {
  flex: 1;
  height: 14px;
  background: #f0f0f0;
  border-radius: 7px;
  overflow: hidden;
}
.dist-fill {
  height: 100%;
  border-radius: 7px;
  transition: width 0.4s ease;
}
.dist-count {
  width: 65px;
  font-size: 12px;
  text-align: left;
  flex-shrink: 0;
}
.term-stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 80px;
}
.term-stat-label {
  font-size: 11px;
  color: #909399;
}
.term-stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}
</style>
