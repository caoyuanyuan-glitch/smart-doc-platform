<template>
  <div class="polish-container" :class="{ 'document-mode': currentView === 'document' }">
    <div v-if="currentView === 'document'" class="document-view" :class="{ 'document-result-mode': docResult }">
      <div class="page-title-row">
        <h2 class="page-title">文档润色（AI调试）</h2>
        <el-tag type="warning" effect="plain">AI 增强调试副本</el-tag>
        <div v-if="loading" class="polish-progress-float" :class="{ done: polishProgress >= 100 }">
          <div class="progress-float-bar">
            <el-icon class="is-loading" v-if="polishProgress < 100"><Loading /></el-icon>
            <span class="progress-float-text">{{ polishProgressMsg || '润色中...' }}</span>
            <span v-if="documentProgressEtaText && polishProgress < 100" class="progress-float-eta">预计剩余 {{ documentProgressEtaText }}</span>
          </div>
          <div v-if="polishProgress < 100" class="progress-float-body">
            <el-progress :percentage="polishProgress" :stroke-width="10" />
          </div>
        </div>
      </div>

      <div class="doc-layout" :class="{ 'doc-layout-result-only': docResult }">
        <div v-if="!docResult" class="doc-left">
          <div class="panel doc-input-panel">
            <div class="form-item">
              <label class="form-label">产品类型</label>
              <el-select v-model="formData.productType" class="full-width" placeholder="选择产品类型" clearable @change="handleProductTypeChange">
                <el-option v-for="item in documentProductTypeOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </div>

            <div class="form-item">
              <label class="form-label">句式清单文件</label>
              <div class="input-with-button">
                <el-select v-model="formData.sentenceFileId" class="full-width" :placeholder="sentenceFileSelectPlaceholder" clearable @change="handleSentenceFileChange">
                  <el-option v-for="f in sentenceFileOptions" :key="String(f.id)" :label="f.label" :value="f.id" />
                </el-select>
              </div>
              <div class="form-helper-text">{{ sentenceFileHelperText }}</div>
            </div>

            <div class="form-item">
              <label class="form-label">术语对照表</label>
              <div class="input-with-button">
                <el-select v-model="formData.terminologyFileId" class="full-width" :placeholder="terminologyFileSelectPlaceholder" clearable @change="onDocumentTerminologyChange">
                  <el-option v-for="f in termFileOptions" :key="String(f.id)" :label="f.label" :value="f.id" />
                </el-select>
              </div>
              <div class="form-helper-text">{{ terminologyFileHelperText }}</div>
            </div>

            <div class="form-item">
              <label class="form-label">待润色文件</label>
              <div class="input-with-button">
                <el-input v-model="formData.sourceFile" readonly placeholder="选择本地文件" />
                <el-button type="primary" @click="openLocalFilePicker()">选择文件</el-button>
              </div>
            </div>

            <div class="form-item">
              <label class="form-label">润色要求</label>
              <el-input v-model="formData.requirements" type="textarea" :rows="3" placeholder="请输入额外的润色要求（选填）" />
            </div>

            <div v-if="showStandardDocumentWorkflow" class="form-item">
              <label class="form-label">处理模式</label>
              <el-radio-group v-model="formData.documentWorkflow" class="workflow-radio-group">
                <el-radio-button v-if="showStandardDocumentWorkflow" label="standard" value="standard">标准润色</el-radio-button>
                <el-radio-button label="cat" value="cat">句式辅助润色</el-radio-button>
              </el-radio-group>
              <div class="form-helper-text">
                <span v-if="showStandardDocumentWorkflow && formData.documentWorkflow !== 'cat'">标准模式会直接输出整篇润色结果和差异确认列表。</span>
                <span v-else>句式辅助模式会先抽取候选句式，再逐段确认后生成带修订的文档。</span>
              </div>
            </div>

            <div v-if="formData.documentWorkflow === 'cat'" class="form-item">
              <label class="form-label">AI 语义评分</label>
              <div class="cat-ai-switch-row">
                <el-switch v-model="formData.catAiSemanticScoring" inline-prompt active-text="开启" inactive-text="关闭" />
                <span class="form-helper-text cat-ai-switch-text">
                  <span v-if="formData.catAiSemanticScoring">匹配率高。调用AI语义评分和排序。</span>
                  <span v-else>匹配率低。只使用规则召回和字符串匹配，不调用AI语义评分。</span>
                </span>
              </div>
            </div>

            <div class="button-group doc-button-group">
              <el-button @click="resetForm">清空</el-button>
              <el-button type="primary" :loading="loading" @click="submitPolish">提交</el-button>
            </div>
          </div>

        </div>

        <div class="doc-right" :class="{ 'doc-right-full': docResult }">
          <template v-if="formData.documentWorkflow === 'cat'">
            <div v-if="catResult" class="panel doc-result-panel cat-result-panel">
              <div class="panel-header">
                <span>句式候选结果</span>
                <div class="panel-actions">
                  <el-tag v-if="catDocumentAccuracyRate !== null" size="small" type="success">文档准确率 {{ formatCatAccuracyRate(catDocumentAccuracyRate) }}</el-tag>
                </div>
              </div>

              <div class="doc-review-panel cat-review-panel">
                <div class="doc-review-summary">
                  <div class="doc-review-count">当前候选句 {{ catItems.length }} 条，待处理 {{ pendingCatCount }} 条，已确认 {{ confirmedCatCount }} 条</div>
                  <div class="doc-review-summary-actions">
                    <div class="doc-review-confirmed">AI 评分 {{ formData.catAiSemanticScoring ? catAiStatusLabel : '已关闭' }}</div>
                    <el-button v-if="catCandidateDebugSummaryText" text size="small" native-type="button" @click="catDiagnosticExpanded = !catDiagnosticExpanded">{{ catDiagnosticExpanded ? '收起召回诊断' : '展开召回诊断' }}</el-button>
                  </div>
                </div>

                <div v-if="catDiagnosticExpanded && catCandidateDebugSummaryText" class="cat-ai-status-banner" :class="catResult.aiScoringStatus || 'skipped'">
                  <span class="cat-ai-status-title">召回诊断</span>
                  <span class="cat-ai-status-text">{{ catCandidateDebugSummaryText }}</span>
                </div>

                <div class="doc-review-toolbar cat-review-toolbar">
                  <div class="doc-review-filters">
                    <span class="cat-toolbar-hint">处理流程：检查候选句子→选择处理动作→生成润色文档→下载带修订的润色文件</span>
                  </div>
                  <div class="doc-review-bulk-actions">
                    <el-button type="primary" size="small" native-type="button" :loading="catApplying" @click="applyCatSelections">生成润色文档</el-button>
                  </div>
                </div>

                <div v-if="catApplyResult" class="cat-apply-banner">
                  <div>
                    <div class="cat-apply-title">润色文档已生成</div>
                    <div class="cat-apply-meta">应用 {{ catApplyResult.appliedChangesCount }} 处，准确率 {{ formatCatAccuracyRate(catApplyResult.accuracyRate) }}</div>
                  </div>
                  <div class="cat-apply-actions">
                    <el-button v-if="catApplyResult.previewUrl" size="small" native-type="button" @click="openCatPreview">查看预览</el-button>
                    <el-button v-if="catApplyResult.reportDownloadUrl" size="small" native-type="button" @click="downloadCatReport">下载润色报告</el-button>
                    <el-button v-if="catApplyResult.downloadUrl" size="small" type="primary" native-type="button" @click="downloadCatResult">下载润色文档</el-button>
                  </div>
                </div>

                <div v-if="catItems.length" class="cat-item-list">
                <div v-for="item in catItems" :key="`cat-${item.sentenceIndex}`" class="cat-item-card" :class="[severityClass(selectedCatCandidate(item)), { 'is-collapsed': item.resultCollapsed }]">
                  <div class="cat-item-header">
                    <div>
                      <div class="cat-item-title">句子 #{{ item.sentenceIndex + 1 }} · 段落 #{{ item.sourceParagraphIndex + 1 }}</div>
                      <div v-if="categoryLabel(selectedCatCandidate(item))" class="cat-issue-tags">
                        <span class="cat-category-tag">{{ categoryLabel(selectedCatCandidate(item)) }}</span>
                      </div>
                    </div>
                    <div class="cat-item-header-actions">
                      <el-button text size="small" native-type="button" @click="toggleCatItemCollapsed(item)">{{ item.resultCollapsed ? '展开结果' : '收起结果' }}</el-button>
                      <el-tag size="small" :type="item.action === 'accept' ? 'success' : item.action === 'modify' ? 'warning' : item.action === 'reject' ? 'danger' : 'info'">
                        {{ item.action === 'accept' ? '接受' : item.action === 'modify' ? '自定义' : item.action === 'reject' ? '拒绝' : '待处理' }}
                      </el-tag>
                    </div>
                  </div>

                  <div v-if="item.resultCollapsed" class="cat-item-collapsed-preview">
                    <span class="cat-item-collapsed-label">{{ getCatCollapsedLabel(item) }}</span>
                    <div class="issue-diff-content issue-diff-original" v-html="renderCatCollapsedPreviewHtml(item)"></div>
                  </div>

                  <div v-show="!item.resultCollapsed && selectedCatCandidate(item)" class="issue-diff-card cat-issue-diff-card">
                    <div class="issue-diff-row">
                      <span class="issue-diff-label">原文</span>
                      <div class="issue-diff-content issue-diff-original" v-html="renderCatOriginalPanelHtml(item)"></div>
                    </div>
                    <div class="issue-diff-row">
                      <span class="issue-diff-label">{{ item.action === 'modify' && item.savedModifiedText ? '自定义' : '候选' }}</span>
                      <div class="issue-diff-content issue-diff-suggested">
                        <div v-html="renderCatSuggestedDiffHtml(item.originalText, getCatDisplayText(item))"></div>
                        <div v-if="item.action !== 'modify' && selectedCatCandidate(item)" class="cat-selected-meta">
                          <span class="cat-selected-source">{{ formatCatCandidateSource(selectedCatCandidate(item)) }}</span>
                          <span v-if="!isDiagnoseCandidate(selectedCatCandidate(item))">匹配率 {{ formatCatCandidateMatchRate(selectedCatCandidate(item)) }}</span>
                          <span v-if="!isDiagnoseCandidate(selectedCatCandidate(item)) && selectedCatCandidate(item)?.semantic_score !== null && selectedCatCandidate(item)?.semantic_score !== undefined">语义分 {{ formatCatScore(selectedCatCandidate(item).semantic_score) }}%</span>
                        </div>
                        <div v-if="isDiagnoseCandidate(selectedCatCandidate(item))" class="cat-diagnose-meta">
                          <div v-if="selectedCatCandidate(item)?.problem" class="cat-diagnose-problem">{{ selectedCatCandidate(item).problem }}</div>
                          <div v-if="selectedCatCandidate(item)?.rationale" class="cat-diagnose-rationale">{{ selectedCatCandidate(item).rationale }}</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div v-show="!item.resultCollapsed && item.candidates.length > 1" class="cat-item-section cat-item-section-surface cat-item-section-surface-muted">
                    <div class="cat-section-head">
                      <label class="cat-item-label">候选句式</label>
                      <span class="issue-candidate-count">共 {{ item.candidates.length }} 条</span>
                    </div>
                    <div class="cat-candidate-select-shell">
                      <div class="cat-candidate-select-overlay">{{ selectedCatCandidate(item)?.template_text || '' }}</div>
                      <el-select :ref="el => setCandidateSelectRef(item.rowKey, el)" v-model="item.selectedCandidateIndex" class="full-width cat-candidate-select" size="large" popper-class="cat-candidate-select-popper" placeholder="选择候选句式" @change="handleCatCandidateChange(item)">
                        <el-option
                          v-for="(candidate, candidateIndex) in item.candidates"
                          :key="`cat-${item.sentenceIndex}-candidate-${candidateIndex}`"
                          :label="candidate.template_text"
                          :value="candidateIndex"
                        >
                          <div class="cat-candidate-option">
                            <div class="cat-candidate-text">{{ candidate.template_text }}</div>
                            <div v-if="candidate.semantic_score !== null && candidate.semantic_score !== undefined" class="cat-candidate-score">语义分 {{ formatCatScore(candidate.semantic_score) }}%</div>
                          </div>
                        </el-option>
                      </el-select>
                    </div>
                  </div>

                  <div v-show="!item.resultCollapsed" class="cat-item-section cat-item-section-compact cat-item-section-surface">
                    <label class="cat-item-label">处理动作</label>
                    <el-radio-group v-model="item.action" size="small" class="cat-action-group">
                      <el-radio-button value="pending" @click="forceCatAction(item, 'pending')">待处理</el-radio-button>
                      <el-radio-button value="accept" @click="forceCatAction(item, 'accept')">接受候选</el-radio-button>
                      <el-radio-button value="modify" @click="forceCatAction(item, 'modify')">自定义</el-radio-button>
                      <el-radio-button value="reject" @click="forceCatAction(item, 'reject')">拒绝</el-radio-button>
                    </el-radio-group>
                    <div v-if="item.isDraftSaved || item.action === 'modify'" class="cat-item-status-row">
                      <span v-if="item.isDraftSaved" class="cat-item-saved-hint">{{ item.action === 'accept' ? '当前候选已保存，将以最新选择为准' : item.action === 'modify' ? '自定义文本已保存' : '当前处理结果已暂存' }}</span>
                      <el-button v-if="item.action === 'modify' && item.isDraftSaved && !item.modifyEditorVisible" size="small" text native-type="button" @click="reopenCatModifyEditor(item)">编辑自定义</el-button>
                    </div>
                  </div>

                  <div v-if="!item.resultCollapsed && item.action === 'modify' && item.modifyEditorVisible" class="cat-item-section cat-item-section-surface cat-item-section-surface-edit">
                    <label class="cat-item-label">自定义润色文本</label>
                    <el-input v-model="item.modifiedText" type="textarea" :rows="2" placeholder="输入你希望写入文档的最终文本" @input="markCatItemDirty(item)" />
                    <div class="cat-item-inline-actions">
                      <el-button v-if="item.candidates.length > 1" size="small" plain native-type="button" @click="focusCatCandidateSelect(item)">选择并更换候选</el-button>
                      <el-button size="small" type="primary" plain native-type="button" @click="saveCatModify(item)">保存</el-button>
                    </div>
                  </div>
                </div>
                </div>
                <div v-else class="doc-change-empty">{{ catEmptyStateText() }}</div>
              </div>
            </div>

            <div v-else class="panel result-placeholder doc-result-panel">
              <div class="panel-header">
                <span>句式候选结果</span>
              </div>
              <div class="placeholder-text">上传文档后，这里会展示命中的句式候选和逐段确认区。</div>
            </div>
          </template>

          <template v-else>
          <div v-if="docResult" class="panel doc-result-panel">
            <div class="panel-header">
              <span>润色结果</span>
              <div class="panel-actions">
                <el-button size="small" @click="downloadPolishedDoc">下载文档</el-button>
                <el-button size="small" @click="downloadReport">润色报告</el-button>
                <el-button type="primary" size="small" :loading="docFeedbackLoading || docDecisionSaving" @click="submitDocumentFeedback">写入平台反馈句式清单</el-button>
              </div>
            </div>

              <div ref="docPreviewRef" class="doc-review-panel">
                <div class="doc-review-summary">
                <div class="doc-review-count">当前筛选 {{ filteredDocIssues.length }} / {{ docResult.changes }} 条，待处理 {{ pendingDocIssueCount }} 条，接口原始 {{ docResult.rawChangeCount }} 条，过滤前 {{ docResult.preFilterChangeCount }} 条</div>
                <div class="doc-review-summary-actions">
                  <div class="doc-review-confirmed">已确认 {{ confirmedDocChangeCount }}/{{ docResult.changes }}</div>
                  <el-button text size="small" @click="docResultExpanded = !docResultExpanded">{{ docResultExpanded ? '收起详情' : '展开详情' }}</el-button>
                </div>
                </div>

              <div v-if="docResultExpanded && (docResult.taskId || docResult.debugInfo)" class="doc-review-debug-bar">
                <span v-if="docResult.processedAt" class="doc-debug-chip">本次生成 {{ docResult.processedAt }}</span>
                <span v-if="docResult.taskId" class="doc-debug-chip">任务 {{ shortTaskId(docResult.taskId) }}</span>
                <span v-if="docResult.debugInfo?.sentenceFileName" class="doc-debug-chip">句式 {{ docResult.debugInfo.sentenceFileName }}</span>
                <span v-if="docResult.debugInfo?.sentenceGuideChars" class="doc-debug-chip">规则 {{ docResult.debugInfo.sentenceGuideChars }} 字</span>
                <span v-if="docResult.debugInfo?.sentenceGuideSha1" class="doc-debug-chip">指纹 {{ docResult.debugInfo.sentenceGuideSha1 }}</span>
                <span v-if="docResult.debugInfo" class="doc-debug-chip">整篇AI {{ docResult.debugInfo.aiSkipped ? '已跳过' : '已执行' }}</span>
                <span v-if="docResult.debugInfo?.aiSkipped && docResult.debugInfo?.aiSkipReason" class="doc-debug-chip">原因 {{ docResult.debugInfo.aiSkipReason }}</span>
                <span v-if="docResult.rawChangeCount !== undefined" class="doc-debug-chip">原始 {{ docResult.rawChangeCount }}</span>
                <span v-if="docResult.preFilterChangeCount !== undefined" class="doc-debug-chip">过滤前 {{ docResult.preFilterChangeCount }}</span>
                <span v-if="docResult.changes !== undefined" class="doc-debug-chip">过滤后 {{ docResult.changes }}</span>
              </div>

              <div class="doc-review-toolbar">
                <div class="doc-review-filters">
                  <el-input
                    v-model="docKeywordFilter"
                    size="small"
                    clearable
                    placeholder="按关键词搜索"
                    class="doc-filter-search"
                  />
                  <el-button text size="small" @click="docAdvancedFiltersVisible = !docAdvancedFiltersVisible">{{ docAdvancedFiltersVisible ? '收起筛选' : '更多筛选' }}</el-button>
                  <el-select v-if="docAdvancedFiltersVisible" v-model="docConfidenceFilter" size="small" placeholder="按匹配分" class="doc-filter-select">
                    <el-option label="全部匹配分" value="all" />
                    <el-option label="高匹配（95% 及以上）" value="95plus" />
                    <el-option label="中匹配（75% - 94%）" value="75to94" />
                    <el-option label="低匹配（75% 以下）" value="below75" />
                  </el-select>
                  <el-select v-if="docAdvancedFiltersVisible" v-model="docStatusFilter" size="small" placeholder="按状态" class="doc-filter-select">
                    <el-option label="全部状态" value="all" />
                    <el-option label="待处理" value="pending" />
                    <el-option label="已接受" value="accepted" />
                    <el-option label="已拒绝" value="rejected" />
                  </el-select>
                  <el-select v-if="docAdvancedFiltersVisible" v-model="docFilterType" size="small" placeholder="全部类型" class="doc-filter-select">
                    <el-option label="全部类型" value="" />
                    <el-option v-for="item in docIssueTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
                  </el-select>
                </div>
                <div class="doc-review-bulk-actions">
                  <el-button size="small" :disabled="docDecisionSaving || !filteredDocIssues.length || allFilteredDocIssuesSelected" @click="selectFilteredDocumentIssues">全选当前筛选</el-button>
                  <el-button size="small" :disabled="docDecisionSaving || selectedDocIssueCount === 0" @click="clearSelectedDocumentIssues">全不选</el-button>
                  <el-button size="small" :disabled="docDecisionSaving || selectedDocIssueCount === 0" :loading="docDecisionSaving" @click="acceptSelectedDocumentIssues">接受已选{{ selectedDocIssueCount ? ` (${selectedDocIssueCount})` : '' }}</el-button>
                  <el-button size="small" type="success" :loading="docDecisionSaving" @click="acceptAllDocumentIssues">全部接受</el-button>
                  <el-button size="small" type="danger" plain :loading="docDecisionSaving" @click="rejectAllDocumentIssues">全部拒绝</el-button>
                </div>
              </div>

              <div v-if="filteredDocIssues.length" class="doc-issue-list">
                <div
                  v-for="issue in filteredDocIssues"
                  :key="issue.rowKey"
                  class="doc-issue-card"
                  :class="{
                    'is-accepted': issue.status === 'accepted' || issue.status === 'custom',
                    'is-rejected': issue.status === 'rejected'
                  }"
                >
                  <div class="doc-issue-header">
                    <div class="doc-issue-title-wrap">
                      <el-checkbox v-model="issue.selected" size="small" />
                      <span class="doc-issue-title">问题 #{{ issue.displayIndex }}</span>
                      <span v-if="issueScorePercent(issue) > 0" class="issue-score-inline">综合评分：{{ issueScorePercent(issue) }}%</span>
                    </div>
                    <div class="doc-issue-meta">
                      <el-tag size="small" :type="issue.typeTagType">{{ issue.typeLabel }}</el-tag>
                      <span class="paragraph-pill">段落 #{{ issue.paragraph }}</span>
                    </div>
                  </div>

                  <div class="doc-issue-body">
                    <div class="issue-diff-card">
                      <div class="issue-diff-row">
                        <span class="issue-diff-label">原文</span>
                        <div class="issue-diff-content issue-diff-original" v-html="renderIssueOriginalDiff(issue)"></div>
                      </div>
                      <div class="issue-diff-row">
                        <span class="issue-diff-label">建议</span>
                        <div class="issue-diff-content issue-diff-suggested" v-html="renderIssueSuggestedDiff(issue)"></div>
                      </div>
                    </div>

                    <div v-if="!isIssueCollapsed(issue) && shouldShowCandidateList(issue)" class="issue-candidate-list issue-candidate-list-inline">
                      <div class="issue-candidate-title">
                        <span>候选句式</span>
                        <span class="issue-candidate-count">共 {{ visibleCandidates(issue).length }} 条</span>
                      </div>
                      <el-select
                        v-model="issue.selectedCandidateKeys"
                        :ref="el => setCandidateSelectRef(issue.rowKey, el)"
                        multiple
                        collapse-tags
                        collapse-tags-tooltip
                        size="small"
                        popper-class="cat-candidate-select-popper"
                        placeholder="选择一个或多个候选句子"
                        class="issue-candidate-select"
                        @change="selectCandidateSuggestion(issue, $event)"
                      >
                        <el-option
                          v-for="(candidate, candidateIndex) in visibleCandidates(issue)"
                          :key="`${issue.rowKey}-candidate-${candidateIndex}`"
                          :label="candidate.template"
                          :value="String(candidateIndex)"
                        >
                          <div class="issue-candidate-option">
                            <div class="issue-candidate-option-main">
                              <div class="issue-candidate-option-head">
                                <span class="issue-candidate-option-text">{{ candidate.template }}</span>
                                <span v-if="candidate.aiSemanticScore !== null" class="issue-candidate-ai-badge" :class="candidate.aiSemanticRecommended ? 'is-recommended' : 'is-neutral'">
                                  {{ aiRecommendationLabel(candidate) }}
                                </span>
                              </div>
                              <span class="issue-candidate-option-meta">{{ candidateSummary(candidate) }}</span>
                              <span v-if="candidate.aiSemanticScore !== null" class="issue-candidate-option-ai">语义分 {{ candidate.aiSemanticScore }}{{ candidate.aiSemanticReason ? ` · ${candidate.aiSemanticReason}` : '' }}</span>
                            </div>
                            <span class="issue-candidate-option-percent">{{ candidate.overallPercent }}%</span>
                          </div>
                        </el-option>
                      </el-select>
                    </div>

                    <div v-if="!isIssueCollapsed(issue) && issue.matchDetail && issueHasAiAdvice(issue)" class="issue-match-card">
                      <div v-if="issueHasAiAdvice(issue)" class="issue-ai-card">
                        <div class="issue-ai-card-head">
                          <span class="issue-ai-title">AI 建议</span>
                          <span v-if="issuePrimaryCandidate(issue)?.aiSemanticScore !== null" class="issue-ai-score">语义分 {{ issuePrimaryCandidate(issue)?.aiSemanticScore }}</span>
                        </div>
                        <div class="issue-ai-card-reason">{{ issueAiReasonLabel(issue) }}：{{ issueSelectedCandidateReason(issue) }}</div>
                      </div>
                    </div>
                  </div>

                  <div v-if="!isIssueCollapsed(issue) && issue.editing" class="custom-edit-row">
                    <el-input v-model="issue.customAfter" size="small" placeholder="输入自定义替换文本" />
                    <el-button size="small" type="primary" :loading="docDecisionSaving" @click="saveCustomDocumentIssue(issue)">保存</el-button>
                    <el-button size="small" @click="cancelCustomDocumentIssue(issue)">取消</el-button>
                  </div>

                  <div v-if="!isIssueCollapsed(issue)" class="doc-issue-actions">
                    <el-button size="small" type="success" plain :disabled="docDecisionSaving" @click="acceptDocumentIssue(issue)">接受</el-button>
                    <el-button size="small" type="danger" plain :disabled="docDecisionSaving" @click="rejectDocumentIssue(issue)">拒绝</el-button>
                    <el-button size="small" @click="editDocumentIssue(issue)">自定义</el-button>
                    <el-tag v-if="issue.status === 'accepted'" size="small" type="success">已接受</el-tag>
                    <el-tag v-if="issue.status === 'rejected'" size="small" type="danger">已拒绝</el-tag>
                    <el-tag v-if="issue.status === 'custom'" size="small" type="warning">已自定义</el-tag>
                  </div>
                </div>
              </div>
              <div v-else class="doc-change-empty">当前没有可确认的润色结果</div>

              <div class="doc-review-footer">
                <el-button @click="resetForm">返回</el-button>
                <el-button type="primary" @click="scrollToDocumentPreview">预览修改</el-button>
              </div>
            </div>
          </div>

          <div v-else class="panel result-placeholder doc-result-panel">
            <div class="panel-header">
              <span>润色结果</span>
            </div>
            <div class="placeholder-text">提交文档后，这里会展示润色结果和每条修改的确认状态。</div>
          </div>
          </template>
        </div>
      </div>
    </div>

    <div v-if="currentView === 'text'">
      <div class="page-title-row">
        <h2 class="page-title">文本润色（AI调试）</h2>
        <el-tag type="warning" effect="plain">AI 增强调试副本</el-tag>
      </div>

      <!-- 文件选择行 -->
      <div class="panel">
        <div class="panel-header">
          <span>参考文件</span>
        </div>
        <div class="file-select-row">
          <div class="file-select-col">
            <label class="form-label">产品类型</label>
            <div class="input-with-button">
              <el-select v-model="textProductType" size="small" class="full-width" placeholder="选择产品类型" clearable @change="handleTextProductTypeChange">
                <el-option v-for="item in documentProductTypeOptions" :key="`text-${item}`" :label="item" :value="item" />
              </el-select>
            </div>
          </div>
          <div class="file-select-col">
            <label class="form-label">句式清单文件</label>
            <div class="input-with-button">
              <el-select v-model="textSentenceFileId" size="small" class="full-width" :placeholder="textSentenceFileSelectPlaceholder" clearable @change="handleTextSentenceFileChange">
                <el-option v-for="f in textSentenceFileOptions" :key="`text-sentence-${f.id}`" :label="f.label" :value="f.id" />
              </el-select>
            </div>
            <div class="form-helper-text">{{ textSentenceFileHelperText }}</div>
          </div>
          <div class="file-select-col">
            <label class="form-label">术语对照表</label>
            <div class="input-with-button">
              <el-select v-model="textTerminologyFileId" size="small" class="full-width" :placeholder="textTerminologyFileSelectPlaceholder" clearable @change="handleTextTerminologyChange">
                <el-option v-for="f in textTermFileOptions" :key="`text-term-${f.id}`" :label="f.label" :value="f.id" />
              </el-select>
            </div>
            <div class="form-helper-text">{{ textTerminologyFileHelperText }}</div>
          </div>
        </div>
      </div>

      <!-- 左右分栏：输入 + 结果 -->
      <div class="content-row">
        <div class="content-left">
          <div class="panel">
            <div class="panel-header">
              <span>输入待润色文本</span>
              <div class="panel-actions">
                <el-button type="primary" size="small" @click="doPolish">
                  <el-icon v-if="loading" class="is-loading button-loading-icon"><Loading /></el-icon>
                  <span>{{ loading ? '进行中' : '开始润色' }}</span>
                </el-button>
                <el-button size="small" @click="clearAll">清空</el-button>
              </div>
            </div>
            <div class="text-input-shell">
              <el-input
                v-model="originalText"
                type="textarea"
                placeholder="输入待润色文本..."
              />
            </div>
          </div>
        </div>
        <div class="content-right">
          <div v-if="result" class="panel result-panel">
              <div class="panel-header">
                <div class="result-header-inline">
                  <span>润色结果</span>
                  <el-tag size="small" type="success">{{ currentPolishEngineLabel }}</el-tag>
                </div>
                <div class="panel-actions">
                  <el-button size="small" @click="copyResult">复制</el-button>
                  <el-button size="small" @click="downloadResult">导出</el-button>
                </div>
              </div>
              <div class="result-grid-vertical">
                <div class="result-col-v">
                  <div class="col-content col-content-compact issue-diff-content issue-diff-suggested" v-html="highlightedPolishedResultHtml"></div>
                </div>
              </div>
              <div v-if="textCatPanelItems.length" class="text-cat-panel">
                <div class="text-cat-header">
                  <span>候选句子</span>
                  <span class="text-cat-count">共 {{ textCatCandidateCount }} 条</span>
                </div>
                <div class="text-cat-list">
                  <div v-for="item in textCatPanelItems" :key="item.rowKey" class="text-cat-item-row" :class="severityClass(selectedTextCatCandidate(item))">
                    <div class="cat-item-body">
                      <div class="cat-issue-tags" v-if="categoryLabel(selectedTextCatCandidate(item))">
                        <span class="cat-category-tag">{{ categoryLabel(selectedTextCatCandidate(item)) }}</span>
                      </div>
                      <el-select v-model="item.selectedCandidateIndex" class="full-width" size="large" placeholder="选择候选句式" placement="bottom-start" :popper-options="{ placement: 'bottom-start', modifiers: [{ name: 'flip', enabled: false }] }" @change="applyTextCatCandidate(item)">
                        <el-option
                          v-for="(candidate, candidateIndex) in item.candidates"
                          :key="`${item.rowKey}-${candidateIndex}`"
                          :label="candidate.template_text || ''"
                          :value="candidateIndex"
                        />
                      </el-select>
                      <div v-if="isDiagnoseCandidate(selectedTextCatCandidate(item))" class="cat-diagnose-meta">
                        <div v-if="selectedTextCatCandidate(item)?.problem" class="cat-diagnose-problem">{{ selectedTextCatCandidate(item).problem }}</div>
                        <div v-if="selectedTextCatCandidate(item)?.rationale" class="cat-diagnose-rationale">{{ selectedTextCatCandidate(item).rationale }}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
          </div>
          <div v-else class="panel result-placeholder">
            <div class="panel-header">
              <span>润色结果</span>
            </div>
            <div class="placeholder-text">点击"开始润色"查看结果</div>
          </div>
        </div>
      </div>

      <!-- 意见反馈行（独立） -->
      <div v-if="result" class="panel feedback-panel">
        <div class="panel-header">
          <span>意见反馈</span>
        </div>
        <div class="feedback-rating-row">
          <div class="form-item">
            <label class="form-label">准确度评分</label>
            <div class="feedback-rating-inline">
              <div class="feedback-rating-group">
                <button
                  v-for="star in feedbackStarSteps"
                  :key="star"
                  type="button"
                  class="feedback-rating-btn"
                  :class="{ active: star <= selectedFeedbackStars }"
                  @click="setFeedbackStars(star)"
                >
                  <span class="rating-star">★</span>
                </button>
              </div>
              <div class="feedback-rating-text">{{ feedbackRatingLabel }}</div>
            </div>
          </div>
        </div>
        <div class="feedback-type-row">
          <div class="form-item">
            <label class="form-label">反馈类型</label>
            <el-radio-group v-model="feedbackType">
              <el-radio value="term">术语修正</el-radio>
              <el-radio value="sentence">句式修正</el-radio>
            </el-radio-group>
          </div>
        </div>
        <div class="feedback-body">
          <template v-if="feedbackType === 'term'">
            <div v-for="(item, index) in termItems" :key="`term-${index}`" class="term-row">
              <el-input v-model="item.original" placeholder="原文用词" />
              <span class="term-arrow">→</span>
              <el-input v-model="item.standard" placeholder="标准用语" />
              <el-button text @click="removeTermItem(index)">删除</el-button>
            </div>
            <el-button type="primary" plain size="small" @click="addTermItem">+ 添加术语修正</el-button>
          </template>
          <template v-else>
            <el-input
              v-model="sentenceCorrections"
              type="textarea"
              :rows="3"
              placeholder="每行一条正确写法，例如：\n请勿在开机状态下断开电源。\n使用前请仔细阅读本说明书。"
            />
          </template>
          <div class="feedback-hint">{{ feedbackHint }}</div>
        </div>
        <div class="feedback-bottom">
          <div class="form-item">
            <el-button type="primary" :loading="feedbackLoading" @click="submitFeedback">提交反馈</el-button>
          </div>
        </div>
      </div>
    </div>

    <input
      ref="localFileInputRef"
      type="file"
      style="display: none"
      accept=".txt,.md,.docx"
      @change="onLocalFileSelected"
    />

    <el-dialog v-model="filePickerVisible" title="从知识库选择文件" width="480px">
      <div class="file-picker-content">
        <div v-if="knowledgeTreeLoading" class="picker-empty">正在加载知识库...</div>
        <div v-else-if="knowledgeTreeList.length === 0" class="picker-empty">暂无知识库文件</div>
        <div v-else class="picker-list">
          <button
            v-for="item in knowledgeTreeList"
            :key="item.nodeKey"
            type="button"
            class="picker-row"
            :class="{ 'is-file': item.isFile, 'is-folder': !item.isFile, 'is-selected': selectedKnowledgeFile?.nodeKey === item.nodeKey }"
            :style="{ paddingLeft: `${12 + item.depth * 20}px` }"
            @click="onTreeNodeClick(item)"
          >
            <span class="node-icon">{{ item.isFile ? '📄' : '📁' }}</span>
            <span class="picker-name">{{ item.name }}</span>
          </button>
        </div>
        <div v-if="selectedKnowledgeFile" class="selected-info">
          已选择：{{ selectedKnowledgeFile.name }}
        </div>
      </div>
      <template #footer>
        <el-button @click="filePickerVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmKnowledgeFile" :disabled="!selectedKnowledgeFile">确认</el-button>
      </template>
    </el-dialog>

    <!-- 需修正弹窗 -->
    <el-dialog
      v-model="correctionDialogVisible"
      title="填写正确描述"
      width="500px"
      :close-on-click-modal="false"
      append-to-body
    >
      <div>
        <p style="margin-bottom: 10px; color: #64748b; font-size: 13px;">
          原文：<strong>{{ correctionForm.original }}</strong>
        </p>
        <p style="margin-bottom: 12px; color: #64748b; font-size: 13px;">
          润色后：<strong>{{ correctionForm.polished }}</strong>
        </p>
        <el-input
          v-model="correctionForm.correction"
          type="textarea"
          :rows="4"
          placeholder="请填写正确的句子描述..."
        />
      </div>
      <template #footer>
        <el-button @click="closeCorrectionDialog">取消</el-button>
        <el-button type="primary" :loading="correctionSubmitting" @click="submitCorrection">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { polishLabAPI as polishAPI, knowledgeAPI, systemAPI, getAPIErrorMessage, getKnowledgeLoadErrorMessage } from '@/api'
import { Loading } from '@element-plus/icons-vue'
import { usePolishLabStore as usePolishStore } from '@/store/polishLab'

const route = useRoute()
const router = useRouter()
const polishStore = usePolishStore()
const { documentDraft, documentSession } = storeToRefs(polishStore)
const candidateSelectRefs = new Map()
const localFileInputRef = ref(null)
const docPreviewRef = ref(null)
const filePickerVisible = ref(false)
const knowledgeTreeLoading = ref(false)
const knowledgeTree = ref([])
const knowledgeTreeList = ref([])
const selectedKnowledgeFile = ref(null)
const currentPickerField = ref(null)
const CAT_SESSION_KEY = 'polish-lab-cat-session-v1'
const CAT_SESSION_VERSION = '2026-08-10-cat-item-collapse-2'
let knowledgeTreePromise = null
let catSessionPersistTimer = null
let activeTextPolishController = null
const documentProductTypeOptions = ['建库试剂', '测序试剂', '核酸提取', '测序仪', '自动化', '软件', '超声']

// ── 下拉框选项 ──
const allSentenceFileOptions = ref([])
const allTermFileOptions = ref([])
const sentenceFileOptions = ref([])
const termFileOptions = ref([])
const textSentenceFileOptions = ref([])
const textTermFileOptions = ref([])
const sentenceProductFolderMap = ref({})
const terminologyProductFolderMap = ref({})
const sentenceFileAutoSelected = ref(false)
const terminologyFileAutoSelected = ref(false)
const textSentenceFileAutoSelected = ref(false)
const textTerminologyFileAutoSelected = ref(false)

// ── 加载句式清单 / 术语库下拉选项 ──
async function loadDropdownOptions() {
  try {
    const rawData = await ensureKnowledgeTreeLoaded()
    const sentenceNode = findKnowledgePathNode(rawData, ['写作规范', '句式清单']) || findKnowledgeNode(rawData, ['句式清单'])
    const termNode = findKnowledgePathNode(rawData, ['资源库', '术语库']) || findKnowledgeNode(rawData, ['术语库'])
    allSentenceFileOptions.value = flattenFileOptions(sentenceNode ? [sentenceNode] : [])
    sentenceProductFolderMap.value = buildSentenceProductFolderMap(sentenceNode)
    allTermFileOptions.value = flattenFileOptions(termNode ? [termNode] : [])
    terminologyProductFolderMap.value = buildProductFolderMap(termNode, '/资源库/术语库')
    syncProductMatchedFileOptions()
    syncTextProductMatchedFileOptions()
  } catch (e) {
    console.warn('加载知识库下拉选项失败', e)
  }
}

async function ensureKnowledgeTreeLoaded(forceReload = false) {
  if (!forceReload && knowledgeTree.value.length) {
    return knowledgeTree.value
  }
  if (!forceReload && knowledgeTreePromise) {
    return knowledgeTreePromise
  }

  knowledgeTreePromise = (async () => {
    let lastError = null
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const resp = await knowledgeAPI.getTree()
        const rawData = Array.isArray(resp.data) ? resp.data : []
        knowledgeTree.value = rawData
        return rawData
      } catch (error) {
        lastError = error
      }
    }
    throw lastError
  })()

  try {
    return await knowledgeTreePromise
  } finally {
    knowledgeTreePromise = null
  }
}

function flattenFileOptions(nodes) {
  const result = []
  function walk(list, prefix = '') {
    if (!Array.isArray(list)) return
    list.forEach(node => {
      const label = prefix ? `${prefix} / ${node.name}` : node.name
      const files = node.files || []
      files.forEach(f => {
        result.push({
          id: f.id,
          name: f.name,
          label: f.name,
          groupLabel: label,
          createdAt: f.created_at || '',
          updatedAt: f.updated_at || ''
        })
      })
      if (node.children && node.children.length > 0) {
        walk(node.children, label)
      }
    })
  }
  walk(nodes)
  return result.sort(compareKnowledgeFilesByTimeDesc)
}

function toKnowledgeFileTimestamp(value) {
  const ts = Date.parse(String(value || ''))
  return Number.isNaN(ts) ? 0 : ts
}

function compareKnowledgeFilesByTimeDesc(a, b) {
  const timeDiff = toKnowledgeFileTimestamp(b?.updatedAt || b?.createdAt) - toKnowledgeFileTimestamp(a?.updatedAt || a?.createdAt)
  if (timeDiff !== 0) {
    return timeDiff
  }
  return Number(b?.id || 0) - Number(a?.id || 0)
}

function findKnowledgePathNode(nodes, pathNames) {
  if (!Array.isArray(nodes) || !Array.isArray(pathNames) || pathNames.length === 0) {
    return null
  }
  let currentList = nodes
  let currentNode = null
  for (const name of pathNames) {
    currentNode = Array.isArray(currentList) ? currentList.find(node => node.name === name) : null
    if (!currentNode) {
      return null
    }
    currentList = currentNode.children || []
  }
  return currentNode
}

function buildProductFolderMap(rootNode, rootPath) {
  const map = {}
  const children = Array.isArray(rootNode?.children) ? rootNode.children : []
  documentProductTypeOptions.forEach(productType => {
    const folderNode = children.find(node => node.name === productType)
    map[productType] = {
      folderNode: folderNode || null,
      path: folderNode ? `${rootPath}/${productType}` : '',
      files: flattenFileOptions(folderNode ? [folderNode] : [])
    }
  })
  return map
}

function buildSentenceProductFolderMap(sentenceNode) {
  return buildProductFolderMap(sentenceNode, '/写作规范/句式清单')
}

function getLatestMatchedFile(files) {
  return Array.isArray(files) && files.length > 0 ? files[0] : null
}

function syncAutoMatchedField(fieldName, options, autoSelectedRef) {
  const currentValue = formData.value[fieldName]
  const latestMatchedFile = getLatestMatchedFile(options)
  const exists = options.some(item => String(item.id) === String(currentValue))
  if (autoSelectedRef.value) {
    formData.value[fieldName] = latestMatchedFile?.id || null
    autoSelectedRef.value = Boolean(latestMatchedFile)
    return
  }
  if (currentValue && !exists) {
    formData.value[fieldName] = null
    autoSelectedRef.value = false
    return
  }
}

function syncProductMatchedFileOptions() {
  const productType = String(formData.value.productType || '').trim()
  const matchedSentence = productType ? sentenceProductFolderMap.value[productType] : null
  const matchedTerminology = productType ? terminologyProductFolderMap.value[productType] : null
  sentenceFileOptions.value = matchedSentence?.folderNode ? matchedSentence.files : allSentenceFileOptions.value
  termFileOptions.value = matchedTerminology?.folderNode ? matchedTerminology.files : allTermFileOptions.value
  syncAutoMatchedField('sentenceFileId', sentenceFileOptions.value, sentenceFileAutoSelected)
  syncAutoMatchedField('terminologyFileId', termFileOptions.value, terminologyFileAutoSelected)
  handleSentenceFileChange(formData.value.sentenceFileId, sentenceFileAutoSelected.value)
  onDocumentTerminologyChange(formData.value.terminologyFileId, terminologyFileAutoSelected.value)
}

function handleProductTypeChange() {
  formData.value.sentenceFileId = null
  formData.value.sentenceFile = ''
  formData.value.terminologyFileId = null
  formData.value.terminologyFile = ''
  sentenceFileAutoSelected.value = true
  terminologyFileAutoSelected.value = true
  syncProductMatchedFileOptions()
}

function handleSentenceFileChange(value, autoSelected = false) {
  sentenceFileAutoSelected.value = autoSelected
  const selected = sentenceFileOptions.value.find(item => String(item.id) === String(value))
  formData.value.sentenceFile = selected?.name || ''
}

function syncTextAutoMatchedField(fieldRef, options, autoSelectedRef, onSelected) {
  const currentValue = fieldRef.value
  const latestMatchedFile = getLatestMatchedFile(options)
  const exists = options.some(item => String(item.id) === String(currentValue))
  if (autoSelectedRef.value) {
    fieldRef.value = latestMatchedFile?.id || null
    autoSelectedRef.value = Boolean(latestMatchedFile)
  } else if (currentValue && !exists) {
    fieldRef.value = null
    autoSelectedRef.value = false
  }
  onSelected(fieldRef.value, autoSelectedRef.value)
}

function syncTextProductMatchedFileOptions(skipAutoMatch = false) {
  const productType = String(textProductType.value || '').trim()
  const matchedSentence = productType ? sentenceProductFolderMap.value[productType] : null
  const matchedTerminology = productType ? terminologyProductFolderMap.value[productType] : null
  textSentenceFileOptions.value = matchedSentence?.folderNode ? matchedSentence.files : allSentenceFileOptions.value
  textTermFileOptions.value = matchedTerminology?.folderNode ? matchedTerminology.files : allTermFileOptions.value
   if (skipAutoMatch) {
    handleTextSentenceFileChange(textSentenceFileId.value, false)
    handleTextTerminologyChange(textTerminologyFileId.value, false)
    return
  }
  syncTextAutoMatchedField(textSentenceFileId, textSentenceFileOptions.value, textSentenceFileAutoSelected, handleTextSentenceFileChange)
  syncTextAutoMatchedField(textTerminologyFileId, textTermFileOptions.value, textTerminologyFileAutoSelected, handleTextTerminologyChange)
}

function handleTextProductTypeChange() {
  textSentenceFileId.value = null
  textSentenceFileName.value = ''
  textTerminologyFileId.value = null
  textTerminologyFileName.value = ''
  textSentenceFileAutoSelected.value = true
  textTerminologyFileAutoSelected.value = true
  syncTextProductMatchedFileOptions()
}

function handleTextSentenceFileChange(value, autoSelected = false) {
  textSentenceFileAutoSelected.value = autoSelected
  const selected = textSentenceFileOptions.value.find(item => String(item.id) === String(value))
  textSentenceFileName.value = selected?.name || ''
}

function handleTextTerminologyChange(value, autoSelected = false) {
  textTerminologyFileAutoSelected.value = autoSelected
  const selected = textTermFileOptions.value.find(item => String(item.id) === String(value))
  textTerminologyFileName.value = selected?.name || ''
}

const originalText = ref('')
const textProductType = ref('')
const textSentenceFileName = ref('')
const textSentenceFileId = ref(null)
const textTerminologyFileName = ref('')
const textTerminologyFileId = ref(null)
const result = ref(null)
const textCatItems = ref([])
const docResult = ref(null)
const catResult = ref(null)
const catItems = ref([])
const catApplying = ref(false)
const catDiagnosticExpanded = ref(false)
const catApplyResult = ref(null)
const docKeywordFilter = ref('')
const docConfidenceFilter = ref('all')
const docStatusFilter = ref('all')
const docFilterType = ref('')
const docResultExpanded = ref(false)
const docAdvancedFiltersVisible = ref(false)
const loading = ref(false)
const polishProgress = ref(0)
const polishProgressMsg = ref('')
const documentProgressEtaText = ref('')
const docFeedbackLoading = ref(false)
const docDecisionSaving = ref(false)
// 反馈相关
const feedbackAccuracy = ref(null)
const feedbackStarSteps = [1, 2, 3, 4, 5]
const feedbackType = ref('term')
const termItems = ref([{ original: '', standard: '' }])
const sentenceCorrections = ref('')
const feedbackLoading = ref(false)
const currentPolishEngine = ref('检测中')
const feedbackScoreMap = {
  1: 20,
  2: 40,
  3: 60,
  4: 80,
  5: 100
}
const selectedFeedbackStars = computed(() => {
  if (!feedbackAccuracy.value) {
    return 0
  }
  return Object.entries(feedbackScoreMap).find(([, score]) => score === feedbackAccuracy.value)?.[0] * 1 || 0
})
const feedbackRatingLabel = computed(() => {
  const star = selectedFeedbackStars.value
  if (star === 5) return '非常准确'
  if (star === 4) return '比较准确'
  if (star === 3) return '部分准确'
  if (star === 2) return '准确度偏低'
  if (star === 1) return '准确度很低'
  return '请选择 1 到 5 星'
})

const feedbackTarget = computed(() => (
  feedbackType.value === 'term' ? 'terminology' : 'sentence_guide'
))

const feedbackHint = computed(() => (
  feedbackType.value === 'sentence'
    ? '句式修正将写入平台反馈的句式清单，每行一条。'
    : '术语修正将写入平台反馈的术语对照表，按“原文用词 → 标准用语”填写。'
))

const feedbackTargetHint = computed(() => (
  feedbackType.value === 'sentence'
    ? '将自动写入平台反馈句式清单'
    : '将自动写入平台反馈术语对照表'
))

function addTermItem() {
  termItems.value.push({ original: '', standard: '' })
}

function removeTermItem(index) {
  if (termItems.value.length === 1) {
    termItems.value[0] = { original: '', standard: '' }
    return
  }
  termItems.value.splice(index, 1)
}

function feedbackTargetLabel() {
  return feedbackType.value === 'term' ? '平台反馈的术语对照表' : '平台反馈的句式清单'
}

function buildTermCorrections() {
  return termItems.value
    .map(item => ({
      original: String(item.original || '').trim(),
      standard: String(item.standard || '').trim()
    }))
    .filter(item => item.original && item.standard)
    .map(item => `${item.original} -> ${item.standard}`)
    .join('\n')
}

function resetFeedbackForm() {
  feedbackAccuracy.value = null
  feedbackType.value = 'term'
  termItems.value = [{ original: '', standard: '' }]
  sentenceCorrections.value = ''
}

function setFeedbackStars(star) {
  feedbackAccuracy.value = feedbackScoreMap[star] || null
}

// 文档润色 - 需修正弹窗
const correctionDialogVisible = ref(false)
const correctionSubmitting = ref(false)
const correctionForm = ref({ index: -1, original: '', polished: '', correction: '' })

function onCorrectionChecked(index, item) {
  if (item.needCorrection) {
    correctionForm.value = {
      index,
      original: item.before || '',
      polished: item.after || '',
      correction: ''
    }
    correctionDialogVisible.value = true
  }
}

function closeCorrectionDialog() {
  correctionDialogVisible.value = false
  if (correctionForm.value.index >= 0) {
    const items = docResult.value?.changeDetails
    if (items && items[correctionForm.value.index]) {
      items[correctionForm.value.index].needCorrection = false
    }
  }
}

async function submitCorrection() {
  if (!correctionForm.value.correction.trim()) {
    ElMessage.warning('请填写正确的句子描述')
    return
  }
  correctionSubmitting.value = true
  try {
    const resp = await polishAPI.submitFeedback(
      correctionForm.value.original,
      correctionForm.value.polished,
      0,  // 准确率不适用
      correctionForm.value.correction.trim(),
      'sentence_guide',
      null,  // 不走选中术语文件
      null   // 不走选中句式文件
    )
    const data = resp.data || {}
    ElMessage.success(`已写入平台反馈句式清单`)
    correctionDialogVisible.value = false
    if (correctionForm.value.index >= 0) {
      const items = docResult.value?.changeDetails
      if (items && items[correctionForm.value.index]) {
        items[correctionForm.value.index].needCorrection = false
      }
    }
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`提交失败：${errorMsg}`)
  } finally {
    correctionSubmitting.value = false
  }
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const semanticPunctuationMap = {
  '，': ',',
  '。': '.',
  '；': ';',
  '：': ':',
  '！': '!',
  '？': '?',
  '（': '(',
  '）': ')',
  '【': '[',
  '】': ']',
  '《': '<',
  '》': '>',
  '“': '"',
  '”': '"',
  '‘': "'",
  '’': "'",
  '、': ',',
  '｜': '|'
}

const lowSignalAnchorTokens = new Set(['的', '地', '得', '了', '着', '过', '吗', '呢', '吧', '啊', '呀', '将', '把', '被', '和', '及', '与'])

function normalizeSemanticUnit(text) {
  const raw = String(text || '')
  if (!raw) {
    return ''
  }
  if (/^\s+$/.test(raw)) {
    return ' '
  }
  return Array.from(raw)
    .map(char => semanticPunctuationMap[char] || char)
    .join('')
    .toLowerCase()
}

function createDiffToken(text) {
  const raw = String(text || '')
  const normalized = normalizeSemanticUnit(raw)
  const isWhitespace = /^\s+$/.test(raw)
  const isPunctuation = /^[,.;:!?()\[\]<>"'|]+$/.test(normalized)
  return {
    text: raw,
    key: normalized,
    ignorable: isWhitespace,
    anchorIgnorable: isWhitespace || isPunctuation || lowSignalAnchorTokens.has(normalized)
  }
}

function splitChars(text) {
  return Array.from(String(text || '')).map(char => createDiffToken(char))
}

function splitByRegex(text) {
  const matches = String(text || '').match(/\s+|[A-Za-z0-9_]+|[\u3400-\u9fff]+|[^\sA-Za-z0-9_\u3400-\u9fff]/g) || []
  return matches.map(part => createDiffToken(part))
}

function segmentText(text) {
  const raw = String(text || '')
  if (!raw) {
    return []
  }

  if (typeof Intl !== 'undefined' && typeof Intl.Segmenter === 'function') {
    const segmenter = new Intl.Segmenter('zh-CN', { granularity: 'word' })
    return Array.from(segmenter.segment(raw), item => createDiffToken(item.segment))
  }

  return splitByRegex(raw)
}

function buildFallbackDiffSegments(leftTokens, rightTokens) {
  let prefix = 0
  const leftLength = leftTokens.length
  const rightLength = rightTokens.length

  while (prefix < leftLength && prefix < rightLength && leftTokens[prefix].key === rightTokens[prefix].key) {
    prefix += 1
  }

  let leftSuffix = leftLength - 1
  let rightSuffix = rightLength - 1
  while (leftSuffix >= prefix && rightSuffix >= prefix && leftTokens[leftSuffix].key === rightTokens[rightSuffix].key) {
    leftSuffix -= 1
    rightSuffix -= 1
  }

  return {
    left: [
      { text: leftTokens.slice(0, prefix).map(item => item.text).join(''), changed: false },
      { text: leftTokens.slice(prefix, leftSuffix + 1).map(item => item.text).join(''), changed: true },
      { text: leftTokens.slice(leftSuffix + 1).map(item => item.text).join(''), changed: false }
    ],
    right: [
      { text: rightTokens.slice(0, prefix).map(item => item.text).join(''), changed: false },
      { text: rightTokens.slice(prefix, rightSuffix + 1).map(item => item.text).join(''), changed: true },
      { text: rightTokens.slice(rightSuffix + 1).map(item => item.text).join(''), changed: false }
    ]
  }
}

function buildCharDiffSegments(leftText, rightText) {
  const leftTokens = splitChars(leftText)
  const rightTokens = splitChars(rightText)
  const leftLength = leftTokens.length
  const rightLength = rightTokens.length

  if (!leftLength && !rightLength) {
    return { left: [], right: [] }
  }

  if (leftLength * rightLength > 120000) {
    return buildFallbackDiffSegments(leftTokens, rightTokens)
  }

  const dp = Array.from({ length: leftLength + 1 }, () => Array(rightLength + 1).fill(0))

  for (let i = leftLength - 1; i >= 0; i -= 1) {
    for (let j = rightLength - 1; j >= 0; j -= 1) {
      if (leftTokens[i].key === rightTokens[j].key) {
        dp[i][j] = dp[i + 1][j + 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1])
      }
    }
  }

  const left = []
  const right = []
  let i = 0
  let j = 0

  function findNextIndex(tokens, startIndex, target) {
    for (let index = startIndex; index < tokens.length; index += 1) {
      if (tokens[index].key === target.key) {
        return index
      }
    }
    return -1
  }

  function shouldPreferInsert(leftIndex, rightIndex) {
    const leftChar = leftTokens[leftIndex]
    const rightChar = rightTokens[rightIndex]
    const leftCharNextInRight = findNextIndex(rightTokens, rightIndex + 1, leftChar)
    const rightCharNextInLeft = findNextIndex(leftTokens, leftIndex + 1, rightChar)

    if (leftCharNextInRight === -1 && rightCharNextInLeft === -1) {
      return false
    }
    if (leftCharNextInRight === -1) {
      return false
    }
    if (rightCharNextInLeft === -1) {
      return true
    }

    const insertDistance = leftCharNextInRight - rightIndex
    const deleteDistance = rightCharNextInLeft - leftIndex
    return insertDistance < deleteDistance
  }

  while (i < leftLength && j < rightLength) {
    if (leftTokens[i].key === rightTokens[j].key) {
      left.push({ text: leftTokens[i].text, changed: false })
      right.push({ text: rightTokens[j].text, changed: false })
      i += 1
      j += 1
      continue
    }

    if (dp[i + 1][j] > dp[i][j + 1]) {
      left.push({ text: leftTokens[i].text, changed: true })
      i += 1
      continue
    }

    if (dp[i + 1][j] < dp[i][j + 1]) {
      right.push({ text: rightTokens[j].text, changed: true })
      j += 1
      continue
    }

    if (shouldPreferInsert(i, j)) {
      right.push({ text: rightTokens[j].text, changed: true })
      j += 1
      continue
    }

    if (rightTokens[j + 1] && leftTokens[i].key === rightTokens[j + 1].key) {
      right.push({ text: rightTokens[j].text, changed: true })
      j += 1
      continue
    }

    right.push({ text: rightTokens[j].text, changed: true })
    left.push({ text: leftTokens[i].text, changed: true })
    i += 1
    j += 1
  }

  while (i < leftLength) {
    left.push({ text: leftTokens[i].text, changed: true })
    i += 1
  }

  while (j < rightLength) {
    right.push({ text: rightTokens[j].text, changed: true })
    j += 1
  }

  return {
    left: mergeDiffSegments(left),
    right: mergeDiffSegments(right)
  }
}

function collectAnchors(leftTokens, rightTokens) {
  const leftComparable = leftTokens.filter(token => !token.anchorIgnorable)
  const rightComparable = rightTokens.filter(token => !token.anchorIgnorable)

  if (!leftComparable.length && !rightComparable.length) {
    return []
  }

  if (leftComparable.length * rightComparable.length > 40000) {
    return null
  }

  const dp = Array.from({ length: leftComparable.length + 1 }, () => Array(rightComparable.length + 1).fill(0))

  for (let i = leftComparable.length - 1; i >= 0; i -= 1) {
    for (let j = rightComparable.length - 1; j >= 0; j -= 1) {
      if (leftComparable[i].key === rightComparable[j].key) {
        dp[i][j] = dp[i + 1][j + 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1])
      }
    }
  }

  const anchors = []
  let i = 0
  let j = 0
  while (i < leftComparable.length && j < rightComparable.length) {
    if (leftComparable[i].key === rightComparable[j].key) {
      anchors.push({
        leftIndex: leftComparable[i].index,
        rightIndex: rightComparable[j].index,
        leftText: leftComparable[i].text,
        rightText: rightComparable[j].text
      })
      i += 1
      j += 1
      continue
    }
    if (dp[i + 1][j] >= dp[i][j + 1]) {
      i += 1
    } else {
      j += 1
    }
  }

  return anchors
}

function buildTokenDiffSegments(leftText, rightText) {
  const leftTokens = segmentText(leftText).map((token, index) => ({ ...token, index }))
  const rightTokens = segmentText(rightText).map((token, index) => ({ ...token, index }))
  const anchors = collectAnchors(leftTokens, rightTokens)

  if (anchors === null) {
    return buildCharDiffSegments(leftText, rightText)
  }

  const left = []
  const right = []
  let leftCursor = 0
  let rightCursor = 0

  function pushGap(nextLeft, nextRight) {
    const leftGap = leftTokens.slice(leftCursor, nextLeft).map(token => token.text).join('')
    const rightGap = rightTokens.slice(rightCursor, nextRight).map(token => token.text).join('')
    const refined = buildCharDiffSegments(leftGap, rightGap)
    left.push(...refined.left)
    right.push(...refined.right)
  }

  for (const anchor of anchors) {
    pushGap(anchor.leftIndex, anchor.rightIndex)
    left.push({ text: anchor.leftText, changed: false })
    right.push({ text: anchor.rightText, changed: false })
    leftCursor = anchor.leftIndex + 1
    rightCursor = anchor.rightIndex + 1
  }

  pushGap(leftTokens.length, rightTokens.length)

  return {
    left: mergeDiffSegments(left),
    right: mergeDiffSegments(right)
  }
}

function buildDiffSegments(leftText, rightText) {
  return buildTokenDiffSegments(leftText, rightText)
}

function mergeDiffSegments(segments) {
  const merged = []
  for (const segment of segments) {
    if (!segment.text) {
      continue
    }
    const last = merged[merged.length - 1]
    if (last && last.changed === segment.changed) {
      last.text += segment.text
      continue
    }
    merged.push({ ...segment })
  }
  return merged
}

const orderedListLeadPattern = /^(首先|其次|再次|然后|最后|一是|二是|三是|四是|五是|其一|其二|其三|其四|其五|第[一二三四五六七八九十]+|[（(]?\d+[)）][、.]?)/
const orderedSplitPattern = /(首先|其次|再次|然后|最后|一是|二是|三是|四是|五是|其一|其二|其三|其四|其五|第[一二三四五六七八九十]+|[（(]?\d+[)）][、.]?)/g

function collectRangeItems(text, regex) {
  const items = []
  let match = regex.exec(text)
  while (match) {
    const value = match[0].trim()
    if (value) {
      items.push({
        start: Array.from(text.slice(0, match.index)).length,
        end: Array.from(text.slice(0, match.index + match[0].length)).length,
        text: value
      })
    }
    match = regex.exec(text)
  }
  return items
}

function collectSequentialMarkerItems(text) {
  const raw = String(text || '')
  const matches = [...raw.matchAll(orderedSplitPattern)]
  if (matches.length < 2) {
    return []
  }

  return matches.map((match, index) => {
    const start = Array.from(raw.slice(0, match.index)).length
    const nextIndex = index + 1 < matches.length ? matches[index + 1].index : raw.length
    const chunk = raw.slice(match.index, nextIndex).trim()
    return {
      start,
      end: start + Array.from(chunk).length,
      text: chunk
    }
  }).filter(item => item.text.length >= 6)
}

function splitCommaClauses(text) {
  return String(text || '')
    .split(/[，,](?=(?:首先|其次|再次|然后|最后|一是|二是|三是|四是|五是|其一|其二|其三|其四|其五))/)
    .map(item => item.trim())
    .filter(Boolean)
}

function detectLongParagraphList(text) {
  const raw = String(text || '')
  const compact = raw.trim()
  if (!compact || compact.length < 30 || /\n/.test(compact)) {
    return null
  }

  const sequentialItems = collectSequentialMarkerItems(raw)
  if (sequentialItems.length >= 2 && sequentialItems.length <= 8) {
    return { type: 'ol', items: sequentialItems }
  }

  const commaOrderedParts = splitCommaClauses(raw)
  if (commaOrderedParts.length >= 2 && commaOrderedParts.length <= 8) {
    return {
      type: 'ol',
      items: (() => {
        const items = []
        let searchStart = 0
        for (const part of commaOrderedParts) {
          const found = raw.indexOf(part, searchStart)
          const start = found === -1 ? searchStart : Array.from(raw.slice(0, found)).length
          const end = start + Array.from(part).length
          items.push({ start, end, text: part })
          searchStart = found === -1 ? searchStart + part.length : found + part.length
        }
        return items
      })()
    }
  }

  const semicolonItems = collectRangeItems(raw, /[^；;]+[；;]?\s*/g)
  if (
    semicolonItems.length >= 2 &&
    semicolonItems.length <= 8 &&
    semicolonItems.every(item => item.text.length >= 6 && item.text.length <= 120)
  ) {
    return { type: 'ul', items: semicolonItems }
  }

  const sentenceItems = collectRangeItems(raw, /[^。！？!?]+[。！？!?]?\s*/g)
  if (sentenceItems.length >= 2 && sentenceItems.length <= 6) {
    const orderedCount = sentenceItems.filter(item => orderedListLeadPattern.test(item.text)).length
    if (orderedCount >= 1) {
      return { type: 'ol', items: sentenceItems }
    }
    if (sentenceItems.every(item => item.text.length >= 8 && item.text.length <= 80)) {
      return { type: 'ul', items: sentenceItems }
    }
  }

  const commaItems = collectRangeItems(raw, /[^，,]+[，,]?\s*/g)
  if (
    compact.length >= 40 &&
    commaItems.length >= 3 &&
    commaItems.length <= 6 &&
    commaItems.every(item => item.text.length >= 6 && item.text.length <= 40)
  ) {
    return { type: 'ul', items: commaItems }
  }

  return null
}

function sliceSegmentsByRange(segments, start, end) {
  const result = []
  let cursor = 0

  for (const segment of segments) {
    const chars = Array.from(segment.text)
    const nextCursor = cursor + chars.length
    if (nextCursor <= start) {
      cursor = nextCursor
      continue
    }
    if (cursor >= end) {
      break
    }

    const from = Math.max(0, start - cursor)
    const to = Math.min(chars.length, end - cursor)
    const textPart = chars.slice(from, to).join('')
    if (textPart) {
      result.push({ text: textPart, changed: segment.changed })
    }
    cursor = nextCursor
  }

  return mergeDiffSegments(result)
}

function renderDiffTokenHtml(text) {
  return escapeHtml(String(text || ''))
    .replace(/ /g, '<span class="diff-space">&#183;</span>')
    .replace(/\t/g, '<span class="diff-space">&#8677;</span>')
}

function renderSegmentsHtml(segments, mode = 'suggested') {
  const changedClass = mode === 'original' ? 'diff-highlight diff-highlight-original' : 'diff-highlight diff-highlight-suggested'
  return mergeDiffSegments(segments)
    .map(segment => {
      const content = renderDiffTokenHtml(segment.text)
      return segment.changed ? `<span class="${changedClass}">${content}</span>` : content
    })
    .join('')
}

function renderCatCandidateDiffHtml(sourceText, targetText, mode = 'suggested') {
  if (String(sourceText || '').length + String(targetText || '').length > 20000) {
    const displayText = mode === 'original' ? sourceText : targetText
    return `<div class="result-text-block">${escapeHtml(displayText || '')}</div>`
  }
  return renderIssueDiffContent(sourceText, targetText, mode)
}

function renderCatOriginalDiffHtml(sourceText, targetText) {
  return renderCatCandidateDiffHtml(sourceText, targetText, 'original')
}

function renderCatSuggestedDiffHtml(sourceText, targetText) {
  return renderCatCandidateDiffHtml(sourceText, targetText, 'suggested')
}

function renderCatOriginalTextHtml(item) {
  const text = String(item?.originalText || '').trim()
  return `<div class="result-text-block">${escapeHtml(text)}</div>`
}

function renderCatOriginalPanelHtml(item) {
  if (item?.action === 'reject') {
    return renderCatOriginalTextHtml(item)
  }
  return renderCatOriginalDiffHtml(item?.originalText || '', getCatDisplayText(item))
}

function renderDiffHtml(sourceText, targetText, mode) {
  const displayText = mode === 'original' ? sourceText : targetText
  const otherText = mode === 'original' ? targetText : sourceText
  if (String(displayText || '').length + String(otherText || '').length > 20000) {
    return `<div class="result-text-block">${escapeHtml(displayText || '')}</div>`
  }
  const structuredList = detectLongParagraphList(displayText)

  if (structuredList) {
    const tagName = structuredList.type
    const itemsHtml = structuredList.items.map((item, idx) => {
      const subSource = mode === 'original' ? item.text : findListItemInOther(item.text, idx, otherText)
      const subTarget = mode === 'original' ? findListItemInOther(item.text, idx, otherText) : item.text
      const diff = buildDiffSegments(subSource, subTarget)
      const segments = mode === 'original' ? diff.left : diff.right
      return `<li>${renderSegmentsHtml(segments, mode).trim()}</li>`
    }).join('')
    return `<${tagName} class="result-auto-list">${itemsHtml}</${tagName}>`
  }

  const diff = buildDiffSegments(sourceText, targetText)
  const segments = mode === 'original' ? diff.left : diff.right
  return `<div class="result-text-block">${renderSegmentsHtml(segments, mode)}</div>`
}

function renderTextPolishedResultHtml(resultData, polishedText) {
  const nextText = String(polishedText || '').trim()
  if (!nextText) {
    return renderDiffHtml(resultData?.original, resultData?.polished, 'polished')
  }
  return renderDiffHtml(resultData?.original, nextText, 'polished')
}

function getDisplayedPolishedText(resultData, items) {
  const baseText = String(resultData?.basePolished || resultData?.polished || resultData?.original || '')
  if (!Array.isArray(items) || !items.length) {
    return baseText
  }
  return items.reduce((currentText, item) => {
    const candidateText = getTextCatCandidateValue(selectedTextCatCandidate(item))
    const originalSentence = String(item?.originalText || '').trim()
    if (!currentText || !candidateText || !originalSentence || !currentText.includes(originalSentence)) {
      return currentText
    }
    return currentText.replace(originalSentence, candidateText)
  }, baseText)
}

function findListItemInOther(itemText, index, otherText) {
  const otherList = detectLongParagraphList(otherText)
  if (otherList && otherList.items.length > index) {
    return otherList.items[index].text
  }
  const idx = otherText.indexOf(itemText)
  if (idx !== -1) {
    return otherText.slice(idx, idx + itemText.length)
  }
  return itemText
}

const textCatPanelItems = computed(() => textCatItems.value.filter(item => {
  if (!Array.isArray(item?.candidates) || !item.candidates.length) {
    return false
  }
  if (item.candidates.length >= 2) {
    return true
  }
  return item.candidates.some(candidate => isDiagnoseCandidate(candidate))
}))
const textCatCandidateCount = computed(() => textCatPanelItems.value.reduce((total, item) => total + (Array.isArray(item?.candidates) ? item.candidates.length : 0), 0))
const singleTextCatItem = computed(() => {
  if (textCatItems.value.length !== 1) {
    return null
  }
  const [item] = textCatItems.value
  return Array.isArray(item?.candidates) && item.candidates.length === 1 ? item : null
})
const activeTextCatMatchRate = computed(() => {
  const sourceItem = singleTextCatItem.value || textCatPanelItems.value[0] || null
  const candidate = selectedTextCatCandidate(sourceItem)
  const matchRate = formatCatCandidateMatchRate(candidate)
  if (!matchRate) {
    return ''
  }
  return matchRate
})
const currentPolishEngineLabel = computed(() => {
  if (currentPolishEngine.value === '本地润色' && activeTextCatMatchRate.value) {
    return `当前引擎：句式匹配/匹配率：${activeTextCatMatchRate.value}`
  }
  return `当前引擎：${currentPolishEngine.value}`
})
const highlightedPolishedHtml = computed(() => renderDiffHtml(result.value?.original, result.value?.polished, 'polished'))
const displayedPolishedText = computed(() => getDisplayedPolishedText(result.value, textCatItems.value))
const highlightedPolishedResultHtml = computed(() => renderTextPolishedResultHtml(result.value, displayedPolishedText.value))
const highlightedDocOriginalHtml = computed(() => renderDiffHtml(docResult.value?.original, docResult.value?.polished, 'original'))
const highlightedDocPolishedHtml = computed(() => renderDiffHtml(docResult.value?.original, docResult.value?.polished, 'polished'))
const currentSentenceProductFolder = computed(() => sentenceProductFolderMap.value[String(formData.value.productType || '').trim()] || null)
const currentTerminologyProductFolder = computed(() => terminologyProductFolderMap.value[String(formData.value.productType || '').trim()] || null)
const sentenceFileSelectPlaceholder = computed(() => {
  if (formData.value.productType) {
    return sentenceFileOptions.value.length ? '自动匹配当前产品类型文件' : '当前产品类型下暂无句式清单文件'
  }
  return '自动匹配全部句式清单文件'
})
const sentenceFileHelperText = computed(() => {
  if (!formData.value.productType) {
    return ''
  }
  if (!currentSentenceProductFolder.value?.folderNode) {
    return `当前产品类型未配置专属句式清单，已回退到全部知识库文件。`
  }
  return ''
})
const terminologyFileSelectPlaceholder = computed(() => {
  if (formData.value.productType) {
    return termFileOptions.value.length ? '自动匹配当前产品类型文件' : '当前产品类型下暂无术语文件'
  }
  return '自动匹配全部术语文件'
})
const terminologyFileHelperText = computed(() => {
  if (!formData.value.productType) {
    return ''
  }
  if (!currentTerminologyProductFolder.value?.folderNode) {
    return `当前产品类型未配置专属术语库，已回退到全部知识库文件。`
  }
  return ''
})
const currentTextSentenceProductFolder = computed(() => sentenceProductFolderMap.value[String(textProductType.value || '').trim()] || null)
const currentTextTerminologyProductFolder = computed(() => terminologyProductFolderMap.value[String(textProductType.value || '').trim()] || null)
const textSentenceFileSelectPlaceholder = computed(() => {
  if (textProductType.value) {
    return textSentenceFileOptions.value.length ? '自动匹配当前产品类型文件' : '当前产品类型下暂无句式清单文件'
  }
  return '自动匹配全部句式清单文件'
})
const textSentenceFileHelperText = computed(() => {
  if (!textProductType.value) {
    return ''
  }
  if (!currentTextSentenceProductFolder.value?.folderNode) {
    return '当前产品类型未配置专属句式清单，已回退到全部知识库文件。'
  }
  return ''
})
const textTerminologyFileSelectPlaceholder = computed(() => {
  if (textProductType.value) {
    return textTermFileOptions.value.length ? '自动匹配当前产品类型文件' : '当前产品类型下暂无术语文件'
  }
  return '自动匹配全部术语文件'
})
const textTerminologyFileHelperText = computed(() => {
  if (!textProductType.value) {
    return ''
  }
  if (!currentTextTerminologyProductFolder.value?.folderNode) {
    return '当前产品类型未配置专属术语库，已回退到全部知识库文件。'
  }
  return ''
})

const DEFAULT_DOCUMENT_WORKFLOW = 'cat'
const showStandardDocumentWorkflow = false

function normalizeDocumentWorkflow(workflow) {
  if (!showStandardDocumentWorkflow) {
    return DEFAULT_DOCUMENT_WORKFLOW
  }
  return workflow === 'standard' || workflow === 'cat' ? workflow : DEFAULT_DOCUMENT_WORKFLOW
}

const formData = ref({
  productType: documentDraft.value.productType || '',
  sentenceFile: documentDraft.value.sentenceFile || '',
  sentenceFileId: documentDraft.value.sentenceFileId || null,
  terminologyFile: documentDraft.value.terminologyFile || '',
  terminologyFileId: documentDraft.value.terminologyFileId || null,
  sourceFile: documentDraft.value.sourceFile || '',
  outputPath: documentDraft.value.outputPath || '已润色文档',
  requirements: documentDraft.value.requirements || '',
  documentWorkflow: normalizeDocumentWorkflow(documentDraft.value.documentWorkflow),
  catAiSemanticScoring: Boolean(documentDraft.value.catAiSemanticScoring)
})

const currentView = computed(() => (route.path === '/polish-lab/document' ? 'document' : 'text'))

let pendingLocalFile = null
let documentProgressTimer = null
let documentProgressStartedAt = 0

const acceptedDocChangeCount = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.filter(item => item.status === 'accepted' || item.status === 'custom').length
})

const autoAppliedDocIssueCount = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.filter(item => item.matchDetail?.autoApplied).length
})

const actionableDocIssueCount = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.filter(item => item.isActionable).length
})

const pendingDocIssueCount = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.filter(item => item.status === 'pending').length
})

function isCatItemConfirmed(item) {
  if (!item) {
    return false
  }
  return getEffectiveCatAction(item) !== 'pending'
}

const acceptedCatCount = computed(() => catItems.value.filter(item => getEffectiveCatAction(item) === 'accept').length)
const modifiedCatCount = computed(() => catItems.value.filter(item => getEffectiveCatAction(item) === 'modify').length)
const rejectedCatCount = computed(() => catItems.value.filter(item => getEffectiveCatAction(item) === 'reject').length)
const confirmedCatCount = computed(() => catItems.value.filter(isCatItemConfirmed).length)
const pendingCatCount = computed(() => catItems.value.length - confirmedCatCount.value)
const catDocumentAccuracyRate = computed(() => {
  if (!catItems.value.length || pendingCatCount.value > 0) {
    return null
  }
  if (catApplyResult.value?.accuracyRate !== null && catApplyResult.value?.accuracyRate !== undefined && catApplyResult.value?.accuracyRate !== '') {
    return Number(catApplyResult.value.accuracyRate)
  }
  const effectiveDecided = acceptedCatCount.value + modifiedCatCount.value + rejectedCatCount.value
  if (effectiveDecided <= 0) {
    return null
  }
  return Number((acceptedCatCount.value / effectiveDecided * 100).toFixed(1))
})

const catAiStatusLabel = computed(() => {
  const status = catResult.value?.aiScoringStatus || ''
  if (status === 'completed') return '已完成'
  if (status === 'no_api_key') return '未配置 Key，已降级'
  if (status === 'skipped') return '已跳过，已降级'
  if (status === 'failed' || status === 'error' || status === 'parse_error' || status === 'invalid_payload' || status === 'empty') return '调用失败，已降级'
  return '未知状态'
})

const catCandidateDebugSummaryText = computed(() => {
  const summary = catResult.value?.candidateDebugSummary
  if (!summary) {
    return ''
  }
  const templatePoolSize = Number(summary.templatePoolSize || 0)
  const templatesConsidered = Number(summary.templatesConsidered || 0)
  const templatesMatched = Number(summary.templatesMatched || 0)
  const returnedBeforeAi = Number(summary.returnedCandidatesBeforeAi || 0)
  const surfaceRuleCandidates = Number(summary.surfaceRuleCandidates || 0)
  const before = Number(summary.totalBeforeFilter || 0)
  const after = Number(summary.totalAfterFilter || 0)
  const review = Number(summary.needsReviewCount || 0)
  const dropped = summary.droppedByReason || {}
  const simpleMatchDropped = summary.simpleMatchDroppedByReason || {}
  const topReason = Object.entries(dropped)
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))[0]
  const topSimpleMatchReason = Object.entries(simpleMatchDropped)
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))[0]
  const topReasonText = topReason ? `，主要过滤原因 ${topReason[0]} ${topReason[1]} 条` : ''
  const simpleMatchText = topSimpleMatchReason ? `，_simple_match 主要拦截 ${topSimpleMatchReason[0]} ${topSimpleMatchReason[1]} 条` : ''
  const surfaceRuleText = surfaceRuleCandidates > 0 ? `，表层规则直出 ${surfaceRuleCandidates}` : ''
  return `模板池 ${templatePoolSize}，进入匹配 ${templatesConsidered}，召回通过 ${templatesMatched}${surfaceRuleText}，候选 ${returnedBeforeAi} -> ${before} -> ${after}，其中 ${review} 条需确认${topReasonText}${simpleMatchText}`
})

const confirmedDocChangeCount = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.filter(item => item.status !== 'pending').length
})

const allDocumentChangesSelected = computed(() => {
  const items = docResult.value?.changeDetails || []
  return items.length > 0 && items.every(item => item.status === 'accepted' || item.status === 'custom')
})

function toggleAllDocumentChanges() {
  const items = docResult.value?.changeDetails || []
  const nextValue = !allDocumentChangesSelected.value
  items.forEach(item => {
    item.accepted = nextValue
    item.status = nextValue ? 'accepted' : 'pending'
  })
}

async function persistDocumentDecisions(showMessage = false, resetAfterSubmit = false) {
  if (!docResult.value || !docResult.value.changeDetails?.length) {
    ElMessage.warning('当前没有可提交的润色结果')
    return null
  }

  const payload = docResult.value.changeDetails.map(item => ({
    before: item.before,
    after: item.after,
    type: item.type,
    status: item.status,
    paragraph: item.paragraph,
    accepted: item.status === 'accepted' || item.status === 'custom'
  }))

  docDecisionSaving.value = true
  try {
    const resp = await polishAPI.submitDocumentFeedback(
      docResult.value.id,
      docResult.value.sourceName,
      payload
    )
    const data = resp.data || {}
    if (docResult.value && data.document_id) {
      docResult.value.id = data.document_id
    }
    if (docResult.value && data.raw_url) {
      docResult.value.rawUrl = data.raw_url
    }
    if (showMessage) {
      if (data.processed_count > 0) {
        ElMessage.success(`已写入 ${data.processed_count} 条平台反馈句式`)
      } else {
        ElMessage.success('文档反馈已提交，本次没有新增句式写入')
      }
    }
    if (resetAfterSubmit) {
      resetForm()
    }
    return data
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`提交失败：${errorMsg}`)
    return null
  } finally {
    docDecisionSaving.value = false
  }
}

async function acceptDocumentIssue(issue) {
  issue.status = 'accepted'
  issue.accepted = true
  issue.selected = false
  issue.editing = false
  await persistDocumentDecisions()
}

async function rejectDocumentIssue(issue) {
  issue.status = 'rejected'
  issue.accepted = false
  issue.selected = false
  issue.editing = false
  await persistDocumentDecisions()
}

function editDocumentIssue(issue) {
  issue.customAfter = issue.matchDetail?.suggestedText || issue.after
  issue.editing = true
}

async function saveCustomDocumentIssue(issue) {
  const nextValue = String(issue.customAfter || '').trim()
  if (!nextValue) {
    ElMessage.warning('请填写自定义替换文本')
    return
  }
  issue.after = nextValue
  if (issue.matchDetail) {
    issue.matchDetail.suggestedText = nextValue
    issue.matchDetail.autoApplied = false
    issue.matchDetail.reviewMode = 'manual'
  }
  issue.status = 'custom'
  issue.accepted = true
  issue.selected = false
  issue.editing = false
  await persistDocumentDecisions()
}

function cancelCustomDocumentIssue(issue) {
  issue.customAfter = issue.matchDetail?.suggestedText || issue.after
  issue.editing = false
}

function candidateText(candidate) {
  return String(candidate?.candidate_text || candidate?.candidateText || candidate?.template || '').trim()
}

function splitStepPrefix(text) {
  const value = String(text || '').trim()
  if (!value) return ['', '']
  const match = value.match(/^(\d+(?:[.-]\d+)*[.)]?\s*)(.+)$/u)
  if (!match) return ['', value]
  return [match[1], String(match[2] || '').trim()]
}

function splitListMarkerPrefix(text) {
  const value = String(text || '')
  const match = value.match(/^(\s*[*\-•·]+\s*)(.+)$/u)
  if (!match) return ['', value.trim()]
  return [match[1], String(match[2] || '').trim()]
}

function splitNoticePrefix(text) {
  const value = String(text || '').trim()
  const match = value.match(/^((?:请)?注意[：:])\s*(.+)$/u)
  if (!match) return ['', value]
  return [match[1], String(match[2] || '').trim()]
}

function reapplySentencePrefix(original, suggestion) {
  let result = String(suggestion || '').trim()
  if (!result) return result

  const [stepPrefix] = splitStepPrefix(original)
  if (stepPrefix && !result.startsWith(stepPrefix)) {
    result = `${stepPrefix}${result}`
  }

  const [listPrefix] = splitListMarkerPrefix(original)
  if (listPrefix && !result.startsWith(listPrefix)) {
    result = `${listPrefix}${result}`
  }

  const [noticePrefix] = splitNoticePrefix(original)
  if (noticePrefix && !result.startsWith(noticePrefix)) {
    result = `${noticePrefix}${result}`
  }

  return result
}

function setCandidateSelectRef(rowKey, el) {
  if (!rowKey) return
  if (el) {
    candidateSelectRefs.set(rowKey, el)
  } else {
    candidateSelectRefs.delete(rowKey)
  }
}

function focusCatCandidateSelect(item) {
  const rowKey = item?.rowKey
  if (!rowKey) {
    return
  }
  const selectRef = candidateSelectRefs.get(rowKey)
  selectRef?.focus?.()
  selectRef?.toggleMenu?.()
}

function combineCandidateTexts(candidates) {
  return candidates
    .map(candidateText)
    .filter(Boolean)
    .join('')
    .trim()
}

function applyCandidateSuggestion(issue, candidates) {
  const nextValue = reapplySentencePrefix(
    issue?.before || issue?.after || '',
    combineCandidateTexts(Array.isArray(candidates) ? candidates : [candidates])
  )
  if (!nextValue) return
  issue.after = nextValue
  issue.customAfter = nextValue
  if (issue.matchDetail) {
    issue.matchDetail.suggestedText = nextValue
    issue.matchDetail.autoApplied = false
    issue.matchDetail.reviewMode = 'manual'
  }
  issue.status = 'pending'
  issue.accepted = false
  issue.editing = false
}

function selectCandidateSuggestion(issue, selectedKeys) {
  const candidates = visibleCandidates(issue)
  const keys = Array.isArray(selectedKeys) ? selectedKeys : [selectedKeys]
  const normalizedKeys = keys
    .map(key => Number(key))
    .filter(index => Number.isInteger(index) && index >= 0 && index < candidates.length)
  if (!normalizedKeys.length) return
  const selectedCandidatesList = normalizedKeys.map(index => candidates[index]).filter(Boolean)
  if (!selectedCandidatesList.length) return
  issue.selectedCandidateKeys = normalizedKeys.map(index => String(index))
  applyCandidateSuggestion(issue, selectedCandidatesList)
  nextTick(() => {
    candidateSelectRefs.get(issue?.rowKey)?.blur?.()
  })
}

function selectedCandidates(issue) {
  const candidates = visibleCandidates(issue)
  if (!candidates.length) return []
  const selectedIndexes = Array.isArray(issue?.selectedCandidateKeys)
    ? issue.selectedCandidateKeys.map(key => Number(key)).filter(index => Number.isInteger(index) && index >= 0 && index < candidates.length)
    : []
  if (selectedIndexes.length) {
    return selectedIndexes.map(index => candidates[index]).filter(Boolean)
  }
  const suggestedText = normalizeCandidateCompareText(issue?.matchDetail?.suggestedText || issue?.after || '')
  const exactMatch = candidates.find(candidate => {
    const text = normalizeCandidateCompareText(candidateText(candidate))
    return text && text === suggestedText
  })
  return exactMatch ? [exactMatch] : [candidates[0]]
}

function issueExactCandidateMatch(issue) {
  const candidates = Array.isArray(issue?.matchDetail?.candidates) ? issue.matchDetail.candidates : []
  if (!candidates.length) return null
  const suggestedText = normalizeCandidateCompareText(issue?.matchDetail?.suggestedText || issue?.after || '')
  if (!suggestedText) return null
  return candidates.find(candidate => normalizeCandidateCompareText(candidateText(candidate)) === suggestedText) || null
}

function candidateLevelLabel(matchLevel) {
  const labelMap = {
    L1: '精确召回',
    L2: '高匹配',
    L3: '弱匹配',
    NONE: '候选'
  }
  return labelMap[String(matchLevel || 'NONE')] || '候选'
}

function candidateSummary(candidate) {
  if (!candidate) return ''
  const parts = [candidateLevelLabel(candidate.matchLevel)]
  const segmentLabels = orderedSegmentScores(candidate.segmentScores)
    .filter(segment => segment?.applicable && Number(segment.percent || 0) >= 80)
    .slice(0, 2)
    .map(segment => `${segment.label}${segment.percent}%`)
  parts.push(...segmentLabels)
  const penalties = Array.isArray(candidate.penalty_reasons || candidate.penaltyReasons)
    ? (candidate.penalty_reasons || candidate.penaltyReasons)
    : []
  if (penalties.length) {
    parts.push(penalties[0])
  } else if (candidate.guardPassed) {
    parts.push('关键项一致')
  }
  return parts.filter(Boolean).join(' / ')
}

function issueScorePercent(issue) {
  const matchDetail = issue?.matchDetail || {}
  const baseSuggestedText = normalizeCandidateCompareText(matchDetail.baseSuggestedText || '')
  const currentSuggestedText = normalizeCandidateCompareText(matchDetail.suggestedText || issue?.after || '')
  if (baseSuggestedText && currentSuggestedText === baseSuggestedText) {
    return Number(matchDetail.baseOverallPercent ?? matchDetail.overallPercent ?? 0)
  }
  const matchedCandidate = issueExactCandidateMatch(issue)
  if (matchedCandidate) {
    return Number(matchedCandidate.overallPercent || 0)
  }
  return 0
}

function issuePrimaryCandidate(issue) {
  const candidates = selectedCandidates(issue)
  if (!candidates.length) return null
  return candidates.slice().sort((a, b) => {
    const scoreDiff = Number(b.aiSemanticScore ?? -1) - Number(a.aiSemanticScore ?? -1)
    if (scoreDiff !== 0) return scoreDiff
    return Number(b.overallPercent || 0) - Number(a.overallPercent || 0)
  })[0]
}

function aiRecommendationLabel(candidate) {
  const score = Number(candidate?.aiSemanticScore)
  if (Number.isFinite(score) && score === 0) return '不推荐'
  return candidate?.aiSemanticRecommended ? 'AI推荐' : 'AI待确认'
}

function issueSelectedCandidateReason(issue) {
  if (!Array.isArray(issue?.selectedCandidateKeys) || issue.selectedCandidateKeys.length === 0) {
    return ''
  }
  const reasons = selectedCandidates(issue)
    .map(candidate => String(candidate?.aiSemanticReason || '').trim())
    .filter(Boolean)
  return Array.from(new Set(reasons)).join('；')
}

function issueHasAiAdvice(issue) {
  return Boolean(issueSelectedCandidateReason(issue))
}

function issueAiReasonLabel(issue) {
  const score = Number(issuePrimaryCandidate(issue)?.aiSemanticScore)
  if (Number.isFinite(score) && score === 0) return '不推荐理由'
  return '推荐理由'
}

function isIssueCollapsed(issue) {
  return issue?.status === 'accepted' || issue?.status === 'custom'
}

function normalizeCandidateCompareText(text) {
  return String(text || '')
    .replace(/^\s*(?:\d+(?:[.-]\d+)*[.)]?|[A-Za-z][.)]|[（(]?[一二三四五六七八九十]+[)）])\s*/u, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function shouldShowCandidateList(issue) {
  const candidates = visibleCandidates(issue)
  if (!candidates.length) return false
  const suggestedText = normalizeCandidateCompareText(getIssueSuggestedText(issue))
  if (!suggestedText) return true
  return candidates.some(candidate => normalizeCandidateCompareText(candidateText(candidate)) !== suggestedText)
}

function renderIssueDiffContent(sourceText, targetText, mode) {
  const diff = buildDiffSegments(sourceText, targetText)
  const segments = mergeDiffSegments(mode === 'original' ? diff.left : diff.right)
  const changedClass = mode === 'original' ? 'diff-remove' : 'diff-add'
  const html = segments.map(segment => {
    const content = renderDiffTokenHtml(segment.text)
    return segment.changed ? `<span class="${changedClass}">${content}</span>` : content
  }).join('')
  return `<div class="result-text-block">${html}</div>`
}

function renderIssueOriginalDiff(issue) {
  const before = String(issue?.before || issue?.after || '')
  const after = String(issue?.matchDetail?.suggestedText || issue?.after || '')
  return renderIssueDiffContent(before, after, 'original')
}

function renderIssueSuggestedDiff(issue) {
  const before = String(issue?.before || '')
  const after = String(issue?.matchDetail?.suggestedText || issue?.after || '')
  return renderIssueDiffContent(before, after, 'suggested')
}

async function acceptAllDocumentIssues() {
  filteredDocIssues.value.forEach(issue => {
    issue.status = 'accepted'
    issue.accepted = true
    issue.selected = false
    issue.editing = false
  })
  await persistDocumentDecisions()
}

async function acceptSelectedDocumentIssues() {
  const selectedIssues = filteredDocIssues.value.filter(issue => issue.selected)
  if (!selectedIssues.length) {
    ElMessage.warning('请先选择要接受的问题')
    return
  }
  selectedIssues.forEach(issue => {
    issue.status = 'accepted'
    issue.accepted = true
    issue.selected = false
    issue.editing = false
  })
  await persistDocumentDecisions()
}

function selectFilteredDocumentIssues() {
  filteredDocIssues.value.forEach(issue => {
    issue.selected = true
  })
}

function clearSelectedDocumentIssues() {
  filteredDocIssues.value.forEach(issue => {
    issue.selected = false
  })
}

async function rejectAllDocumentIssues() {
  filteredDocIssues.value.forEach(issue => {
    issue.status = 'rejected'
    issue.accepted = false
    issue.selected = false
    issue.editing = false
  })
  await persistDocumentDecisions()
}

function scrollToDocumentPreview() {
  if (!docResult.value?.id) {
    ElMessage.warning('暂无可预览的 Word 文件')
    return
  }
  window.open(docResult.value.rawUrl || `/api/polish-lab/${docResult.value.id}/raw`, '_blank')
}

function renderIssueSuggestion(issue) {
  const before = String(issue.before || '')
  const after = String(issue.matchDetail?.suggestedText || issue.after || '')
  if (!after) return ''
  if (!before || before === after) return escapeHtml(after)

  let prefixLength = 0
  const maxPrefixLength = Math.min(before.length, after.length)
  while (prefixLength < maxPrefixLength && before[prefixLength] === after[prefixLength]) {
    prefixLength += 1
  }

  let suffixLength = 0
  const maxSuffixLength = Math.min(before.length - prefixLength, after.length - prefixLength)
  while (
    suffixLength < maxSuffixLength &&
    before[before.length - 1 - suffixLength] === after[after.length - 1 - suffixLength]
  ) {
    suffixLength += 1
  }

  const prefix = after.slice(0, prefixLength)
  const changed = after.slice(prefixLength, after.length - suffixLength)
  const suffix = suffixLength > 0 ? after.slice(after.length - suffixLength) : ''
  if (!changed) return escapeHtml(after)
  return `${escapeHtml(prefix)}<mark class="mark-after">${escapeHtml(changed)}</mark>${escapeHtml(suffix)}`
}

const docIssueTypeOptions = computed(() => {
  const items = docResult.value?.changeDetails || []
  const seen = new Set()
  const options = []
  for (const item of items) {
    const value = String(item.type || '')
    if (!value || seen.has(value)) continue
    seen.add(value)
    options.push({ value, label: item.typeLabel || value })
  }
  return options
})

const filteredDocIssues = computed(() => {
  const items = docResult.value?.changeDetails || []
  const keyword = String(docKeywordFilter.value || '').trim().toLowerCase().replace(/\s+/g, '')
  return items.filter(item => {
    const confidence = issueScorePercent(item)
    if (docConfidenceFilter.value === '95plus' && confidence < 95) return false
    if (docConfidenceFilter.value === '75to94' && (confidence < 75 || confidence >= 95)) return false
    if (docConfidenceFilter.value === 'below75' && confidence >= 75) return false
    if (docStatusFilter.value !== 'all' && item.status !== docStatusFilter.value) return false
    if (docFilterType.value && item.filterType !== docFilterType.value) return false
    if (keyword) {
      const searchable = [
        item.before,
        item.after,
        item.ruleName,
        item.reason,
        item.typeLabel,
        item.filterType,
        item.paragraph ? `段落${item.paragraph}` : '',
        item.matchDetail?.suggestedText,
        issueBasisText(item),
      ]
        .map(value => String(value || '').toLowerCase().replace(/\s+/g, ''))
        .join(' ')
      if (!searchable.includes(keyword)) return false
    }
    return true
  })
})

const selectedDocIssueCount = computed(() => {
  return filteredDocIssues.value.filter(item => item.selected).length
})

const allFilteredDocIssuesSelected = computed(() => {
  return filteredDocIssues.value.length > 0 && filteredDocIssues.value.every(item => item.selected)
})

function normalizeChangeType(type) {
  const typeMap = {
    ai: '系统规则',
    terminology: '术语替换',
    term: '术语替换',
    replacement_rule: '术语替换',
    terminology_rule: '术语替换',
    forbidden: '禁止规则',
    forbidden_rule: '禁止规则',
    imperative: '祈使句规则',
    imperative_rule: '祈使句规则',
    preferred_sentences: '句式模板',
    sentence_applicability_rule: '句式适用',
    style: '句式',
    format: '格式',
    format_rule: '格式',
    punctuation: '标点',
    passive_voice: '语态',
    double_negative: '双重否定',
    informal: '表达',
    sentence_length: '长句',
    pronoun_reference: '指代',
    forbidden_words: '禁用词'
  }
  return typeMap[type] || (type ? String(type) : '润色')
}

function normalizeDocFilterType(type) {
  const value = String(type || '')
  return value || 'system_rule'
}

function getDocTypeTagType(filterType) {
  const typeMap = {
    ai: 'info',
    terminology: 'primary',
    term: 'primary',
    replacement_rule: 'primary',
    terminology_rule: 'primary',
    forbidden: 'danger',
    forbidden_rule: 'danger',
    imperative: 'warning',
    imperative_rule: 'warning',
    preferred_sentences: 'success',
    sentence_applicability_rule: 'success',
    style: 'success',
    format: 'info',
    format_rule: 'info',
    punctuation: 'info'
  }
  return typeMap[filterType] || 'info'
}

function buildDocIssueReason(change, index) {
  if (change.reason) return change.reason
  if (change.rule_name) return change.rule_name
  const rawType = String(change.type || '')
  if (rawType === 'terminology' || rawType === 'term' || rawType === 'replacement_rule' || rawType === 'terminology_rule') return `术语规则 #${change.rule_id || index + 1}`
  if (rawType === 'forbidden' || rawType === 'forbidden_rule' || rawType === 'forbidden_words') return '禁止规则'
  if (rawType === 'imperative' || rawType === 'imperative_rule') return '祈使句规则'
  if (rawType === 'preferred_sentences') return '句式模板'
  if (rawType === 'sentence_applicability_rule') return '句式适用规则'
  if (rawType === 'style') return '句式规则'
  if (rawType === 'format' || rawType === 'format_rule' || rawType === 'punctuation') return '格式规则'
  if (rawType === 'ai') return '系统规则'
  return rawType ? `规则类型：${rawType}` : '润色规则'
}

function issueBasisText(issue) {
  const parts = []
  parts.push(issue.ruleName || issue.reason || issue.typeLabel || '润色规则')
  if (issue.type) parts.push(`type=${issue.type}`)
  if (issue.paragraph) parts.push(`段落 #${issue.paragraph}`)
  return parts.join(' / ')
}

function getMatchBandType(band) {
  if (band === '100%' || band === '95%-99%') return 'success'
  if (band === '85%-94%') return 'warning'
  if (band === '75%-84%') return 'info'
  if (band === '50%-74%') return 'danger'
  return 'info'
}

function orderedSegmentScores(segmentScores) {
  const order = ['condition', 'action', 'object', 'result', 'additional']
  return order
    .map(key => segmentScores?.[key])
    .filter(Boolean)
}

function visibleCandidates(issue) {
  const candidates = Array.isArray(issue?.matchDetail?.candidates) ? issue.matchDetail.candidates : []
  return candidates
    .slice()
    .sort((a, b) => Number(b.overallPercent || 0) - Number(a.overallPercent || 0))
    .filter(candidate => Number(candidate.overallPercent || 0) > 0)
    .slice(0, 8)
}

function normalizeCandidate(candidate) {
  if (!candidate) return null
  return {
    ...candidate,
    overallPercent: candidate.overall_percent ?? candidate.overallPercent ?? 0,
    matchLevel: candidate.match_level || candidate.matchLevel || 'NONE',
    guardPassed: Boolean(candidate.guard_passed ?? candidate.guardPassed),
    segmentScores: candidate.segment_scores || candidate.segmentScores || {},
    penaltyReasons: Array.isArray(candidate.penalty_reasons) ? candidate.penalty_reasons : (candidate.penaltyReasons || []),
    aiSemanticScore: candidate.ai_semantic_score ?? candidate.aiSemanticScore ?? null,
    aiSemanticRecommended: Boolean(candidate.ai_semantic_recommended ?? candidate.aiSemanticRecommended),
    aiSemanticReason: candidate.ai_semantic_reason || candidate.aiSemanticReason || '',
    aiRankScore: candidate.ai_rank_score ?? candidate.aiRankScore ?? null,
  }
}

function stripTrailingPunctuation(text) {
  return String(text || '').trim().replace(/[。.!！？?，,;；:：]+$/g, '')
}

function getIssueSuggestedText(item) {
  return String(item?.matchDetail?.suggestedText || item?.after || '').replace(/\s+/g, ' ').trim()
}

function isLowValueDocChange(item) {
  const before = String(item.before || '').trim()
  const after = String(item.after || '').trim()
  if (!before || !after) return false
  const beforeCore = stripTrailingPunctuation(before)
  const afterCore = stripTrailingPunctuation(after)
  if (beforeCore.length <= 4 && afterCore === `请${beforeCore}`) return true
  if (beforeCore.startsWith('请') && beforeCore.length <= 4 && afterCore === beforeCore.slice(1)) return true
  if (item.ruleName && item.ruleName !== '基础规范化') return false
  if (!['format_rule'].includes(item.filterType)) return false
  if (beforeCore === afterCore) return true
  return before.length <= 4 && after.startsWith(before)
}

function looksLikeFragmentText(text) {
  const value = String(text || '').replace(/\s+/g, ' ').trim()
  if (!value) return false
  if (/[。！？!?；;]/.test(value)) return false
  if (value.length <= 8) return true
  if (value.length > 16) return false
  const verbMarkers = ['将', '请', '点击', '选择', '输入', '打开', '关闭', '启动', '设置', '检查', '确认', '安装', '连接', '使用', '进行', '显示', '支持', '提供', '包含', '进入']
  return !verbMarkers.some(marker => value.includes(marker))
}

function shouldHideZeroConfidenceFragment(item) {
  const matchDetail = item.matchDetail || {}
  const overallPercent = Number(matchDetail.overallPercent || 0)
  if (overallPercent > 0) return false
  if (item.status && item.status !== 'pending') return false
  if (matchDetail.hasChange) return false
  if ((item.ruleName || '') === '基础规范化') return false
  const before = String(item.before || '').trim()
  const after = String(item.after || '').trim()
  if (!looksLikeFragmentText(before) && !looksLikeFragmentText(after)) return false
  const candidates = Array.isArray(matchDetail.candidates) ? matchDetail.candidates : []
  return candidates.length === 0 || candidates.every(candidate => Number(candidate.overallPercent || 0) <= 0)
}

function shouldHideZeroConfidenceIssue(item) {
  const matchDetail = item.matchDetail || {}
  const overallPercent = Number(matchDetail.overallPercent || 0)
  if (overallPercent > 0) return false
  if (item.status && item.status !== 'pending') return false
  const candidates = Array.isArray(matchDetail.candidates) ? matchDetail.candidates : []
  return candidates.length === 0 || candidates.every(candidate => Number(candidate.overallPercent || 0) <= 0)
}

function hasVisibleCandidateSuggestions(item) {
  const candidates = Array.isArray(item?.matchDetail?.candidates) ? item.matchDetail.candidates : []
  return candidates.some(candidate => Number(candidate.overallPercent || 0) > 0)
}

function getDocDisplayPriority(filterType) {
  const priorityMap = {
    preferred_sentences: 100,
    sentence_applicability_rule: 95,
    terminology: 90,
    term: 90,
    replacement_rule: 90,
    terminology_rule: 90,
    forbidden: 80,
    forbidden_rule: 80,
    imperative: 70,
    imperative_rule: 70,
    ai: 40,
    style: 35,
    format: 10,
    format_rule: 10,
    punctuation: 5
  }
  return priorityMap[filterType] || 30
}

function normalizeDocumentChanges(changes) {
  const rawItems = (changes || []).map((change, index) => {
    const before = change.before || change.original || ''
    const after = change.after || change.polished || ''
    const filterType = String(change.type || '')
    const filterCategory = normalizeDocFilterType(change.type)
    const matchDetail = change.match_detail ? {
      ...change.match_detail,
      overallPercent: change.match_detail.overall_percent ?? change.match_detail.overallPercent ?? 0,
      segmentScores: change.match_detail.segment_scores || change.match_detail.segmentScores || {},
      suggestedText: change.match_detail.suggested_text || change.match_detail.suggestedText || after,
      baseSuggestedText: change.match_detail.suggested_text || change.match_detail.suggestedText || after,
      baseOverallPercent: change.match_detail.overall_percent ?? change.match_detail.overallPercent ?? 0,
      autoApplied: false,
      reviewMode: 'manual',
      candidates: Array.isArray(change.match_detail.candidates)
        ? change.match_detail.candidates.map(normalizeCandidate).filter(Boolean)
        : []
    } : null
    const initialAccepted = false
    const overallPercent = Number(matchDetail?.overallPercent || 0)
    const hasMeaningfulSuggestion = Boolean(matchDetail?.hasChange)
    const isActionable = hasMeaningfulSuggestion && overallPercent >= 75
    return {
      rowKey: `${index}-${before}-${after}`,
      displayIndex: index + 1,
      before,
      after,
      type: change.type || '',
      ruleName: change.rule_name || '',
      filterType,
      filterCategory,
      typeLabel: normalizeChangeType(change.type),
      typeTagType: getDocTypeTagType(filterType),
      paragraph: change.paragraph || change.paragraph_index || null,
      isTitle: Boolean(change.is_title || change.isTitle),
      matchDetail,
      isActionable,
      isNewSinceLastPolish: Boolean(change.is_new_since_last_polish ?? change.isNewSinceLastPolish),
      reason: buildDocIssueReason(change, index),
      status: initialAccepted ? 'accepted' : 'pending',
      editing: false,
      showCandidates: false,
      showBasis: false,
      customAfter: matchDetail?.suggestedText || after,
      selectedCandidateKeys: [],
      selected: false,
      accepted: initialAccepted,
      needCorrection: false
    }
  })
  const hasPreferredItem = rawItems.some(item => item.filterType !== 'format' && item.filterType !== 'format_rule' && item.filterType !== 'punctuation')
  const filteredItems = rawItems.filter(item => {
    const before = (item.before || '').replace(/\s+/g, ' ').trim()
    const after = getIssueSuggestedText(item)
    const isFormatLike = item.filterType === 'format' || item.filterType === 'format_rule' || item.filterType === 'punctuation'
    if (item.isTitle && !item.matchDetail?.hasChange) {
      return false
    }
    if (hasPreferredItem && isFormatLike && !hasVisibleCandidateSuggestions(item)) {
      return false
    }
    if (!before && !after && !item.matchDetail) {
      return false
    }
    if (isLowValueDocChange(item)) {
      return false
    }
    if (shouldHideZeroConfidenceIssue(item)) {
      return false
    }
    if (shouldHideZeroConfidenceFragment(item)) {
      return false
    }
    if (before && after && before === after) {
      return false
    }
    if (item.matchDetail) {
      return true
    }
    return before !== after || (!before && after) || (before && !after)
  })

  const sortedItems = filteredItems
    .slice()
    .sort((a, b) => {
      const scoreDelta = issueScorePercent(b) - issueScorePercent(a)
      if (scoreDelta !== 0) return scoreDelta
      const priorityDelta = getDocDisplayPriority(b.filterType) - getDocDisplayPriority(a.filterType)
      if (priorityDelta !== 0) return priorityDelta
      const paragraphDelta = Number(a.paragraph || 0) - Number(b.paragraph || 0)
      if (paragraphDelta !== 0) return paragraphDelta
      return String(a.before || '').localeCompare(String(b.before || ''))
    })
    .map((item, index) => ({
      ...item,
      displayIndex: index + 1,
      triggerCount: 1,
      triggerLevel: 'low'
    }))

  return {
    items: sortedItems,
    rawChangeCount: Array.isArray(changes) ? changes.length : 0,
    preFilterChangeCount: rawItems.length,
  }
}

function applyDocumentResult(data, fallbackSourceName = '') {
  const normalized = normalizeDocumentChanges(data?.review_items || data?.reviewItems || data?.changes || [])
  const normalizedChanges = normalized.items
  clearCatResult()
  docKeywordFilter.value = ''
  docConfidenceFilter.value = 'all'
  docStatusFilter.value = 'all'
  docFilterType.value = ''
  docResultExpanded.value = false
  docAdvancedFiltersVisible.value = false
  docResult.value = {
    id: data?.id,
    sourceName: fallbackSourceName || formData.value.sourceFile || data?.download_filename || '',
    original: data?.original || '',
    polished: data?.polished || '',
    taskId: data?.task_id || null,
    processedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
    rawChangeCount: normalized.rawChangeCount,
    preFilterChangeCount: normalized.preFilterChangeCount,
    totalScored: Array.isArray(data?.review_items || data?.reviewItems) ? (data.review_items || data.reviewItems).length : normalizedChanges.length,
    changes: normalizedChanges.length,
    changeDetails: normalizedChanges,
    reportFile: data?.report_file || data?.reportFile,
    rawUrl: data?.raw_url || (data?.id ? `/api/polish-lab/${data.id}/raw` : ''),
    download_filename: data?.download_filename,
    file_type: data?.file_type,
    debugInfo: data?.debug_info ? {
      sentenceFileId: data.debug_info.sentence_file_id,
      sentenceFileName: data.debug_info.sentence_file_name,
      sentenceGuideChars: data.debug_info.sentence_guide_chars,
      sentenceGuideSha1: data.debug_info.sentence_guide_sha1,
      terminologyFileId: data.debug_info.terminology_file_id,
      terminologyFileName: data.debug_info.terminology_file_name,
      aiSkipped: data.debug_info.ai_skipped,
      aiSkipReason: data.debug_info.ai_skip_reason,
      aiChanged: data.debug_info.ai_changed,
      totalChangeCount: data.debug_info.total_change_count,
      visibleChangeCount: data.debug_info.visible_change_count,
      previousPolishFound: data.debug_info.previous_polish_found,
      previousNewChangeCount: data.debug_info.previous_new_change_count,
    } : null
  }
}

function shortTaskId(taskId) {
  const value = String(taskId || '').trim()
  if (!value) {
    return ''
  }
  return value.length > 12 ? value.slice(0, 12) : value
}

function onDocumentTerminologyChange(fileId, autoSelected = false) {
  terminologyFileAutoSelected.value = autoSelected
  const selected = termFileOptions.value.find(item => item.id === fileId)
  formData.value.terminologyFile = selected?.name || ''
}

function formatRemainingDuration(ms) {
  const totalSeconds = Math.max(1, Math.ceil(ms / 1000))
  if (totalSeconds < 60) {
    return `${totalSeconds}秒`
  }
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds ? `${minutes}分${seconds}秒` : `${minutes}分`
}

function updateDocumentProgressEta() {
  if (!loading.value || !documentProgressStartedAt || polishProgress.value >= 100 || polishProgress.value < 8) {
    documentProgressEtaText.value = ''
    return
  }
  const elapsed = Date.now() - documentProgressStartedAt
  if (elapsed < 1500) {
    documentProgressEtaText.value = ''
    return
  }
  const normalizedProgress = Math.max(0.08, Math.min(polishProgress.value / 100, 0.95))
  const estimatedTotal = elapsed / normalizedProgress
  const remaining = Math.max(1000, estimatedTotal - elapsed)
  documentProgressEtaText.value = formatRemainingDuration(remaining)
}

function startDocumentProgress() {
  stopDocumentProgress()
  documentProgressStartedAt = Date.now()
  polishProgress.value = 3
  polishProgressMsg.value = '正在上传文件...'
  documentProgressEtaText.value = ''
  documentProgressTimer = window.setInterval(() => {
    if (!loading.value) {
      stopDocumentProgress()
      return
    }
    if (polishProgress.value < 25) {
      polishProgress.value += 4
      polishProgressMsg.value = '正在解析文档...'
      updateDocumentProgressEta()
      return
    }
    if (polishProgress.value < 55) {
      polishProgress.value += 3
      polishProgressMsg.value = '正在加载规则...'
      updateDocumentProgressEta()
      return
    }
    if (polishProgress.value < 88) {
      polishProgress.value += 2
      polishProgressMsg.value = '正在润色内容...'
    }
    updateDocumentProgressEta()
  }, 500)
}

function stopDocumentProgress() {
  if (documentProgressTimer) {
    window.clearInterval(documentProgressTimer)
    documentProgressTimer = null
  }
  documentProgressStartedAt = 0
  documentProgressEtaText.value = ''
}

function openFilePicker(field, type) {
  currentPickerField.value = field
  if (type === 'knowledge') {
    selectedKnowledgeFile.value = null
    filePickerVisible.value = true
    loadKnowledgeTree()
  }
}

function openTextSentencePicker() {
  openFilePicker('textSentenceFile', 'knowledge')
}

function openTextTerminologyPicker() {
  openFilePicker('textTerminologyFile', 'knowledge')
}

function clearTextSentenceFile() {
  textSentenceFileName.value = ''
  textSentenceFileId.value = null
  textSentenceFileAutoSelected.value = false
}

function clearTextTerminologyFile() {
  textTerminologyFileName.value = ''
  textTerminologyFileId.value = null
  textTerminologyFileAutoSelected.value = false
}

async function loadKnowledgeTree() {
  knowledgeTreeLoading.value = true
  try {
    const rawData = await ensureKnowledgeTreeLoaded()
    knowledgeTree.value = flattenTree(rawData)
    // Filter: only show files from the relevant subtree
    let filteredData = []
    if (currentPickerField.value === 'sentenceFile' || currentPickerField.value === 'textSentenceFile') {
      const n = findKnowledgePathNode(rawData, ['写作规范', '句式清单']) || findKnowledgeNode(rawData, ['句式清单'])
      filteredData = n ? [n] : []
    } else if (currentPickerField.value === 'terminologyFile' || currentPickerField.value === 'textTerminologyFile') {
      const n = findKnowledgePathNode(rawData, ['资源库', '术语库']) || findKnowledgeNode(rawData, ['术语库'])
      filteredData = n ? [n] : []
    } else {
      filteredData = rawData
    }
    knowledgeTreeList.value = flattenKnowledgeList(filteredData)
    selectedKnowledgeFile.value = null
  } catch (e) {
    ElMessage.error(getKnowledgeLoadErrorMessage(e))
  } finally {
    knowledgeTreeLoading.value = false
  }
}

function findKnowledgeNode(nodes, names) {
  for (const node of nodes) {
    if (names.includes(node.name)) return node
    if (node.children && node.children.length > 0) {
      const found = findKnowledgeNode(node.children, names)
      if (found) return found
    }
  }
  return null
}

function flattenTree(nodes) {
  return nodes.map(node => {
    const files = (node.files || []).map(f => ({
      ...f,
      nodeKey: `file-${f.id}`,
      children: [],
      isFile: true,
      parentFolder: node.name
    }))
    const children = flattenTree(node.children || [])
    return {
      ...node,
      nodeKey: `folder-${node.id}`,
      children: [...files, ...children]
    }
  })
}

function flattenKnowledgeList(nodes, depth = 0) {
  const items = []
  nodes.forEach(node => {
    items.push({
      ...node,
      nodeKey: `folder-${node.id}`,
      depth,
      isFile: false
    })

    const files = (node.files || []).map(file => ({
      ...file,
      nodeKey: `file-${file.id}`,
      depth: depth + 1,
      isFile: true,
      parentFolder: node.name
    }))
    items.push(...files)

    if (node.children && node.children.length > 0) {
      items.push(...flattenKnowledgeList(node.children, depth + 1))
    }
  })
  return items
}

function onTreeNodeClick(data) {
  if (data.isFile || data.file_path) {
    selectedKnowledgeFile.value = data
  } else {
    selectedKnowledgeFile.value = null
  }
}

function confirmKnowledgeFile() {
  if (selectedKnowledgeFile.value && currentPickerField.value) {
    if (currentPickerField.value === 'textSentenceFile') {
      textSentenceFileName.value = selectedKnowledgeFile.value.name
      textSentenceFileId.value = selectedKnowledgeFile.value.id
      textSentenceFileAutoSelected.value = false
    } else if (currentPickerField.value === 'textTerminologyFile') {
      textTerminologyFileName.value = selectedKnowledgeFile.value.name
      textTerminologyFileId.value = selectedKnowledgeFile.value.id
      textTerminologyFileAutoSelected.value = false
    } else if (currentPickerField.value === 'sentenceFile') {
      formData.value.sentenceFile = selectedKnowledgeFile.value.name
      formData.value.sentenceFileId = selectedKnowledgeFile.value.id
      sentenceFileAutoSelected.value = false
    } else if (currentPickerField.value === 'terminologyFile') {
      formData.value.terminologyFile = selectedKnowledgeFile.value.name
      formData.value.terminologyFileId = selectedKnowledgeFile.value.id
      terminologyFileAutoSelected.value = false
    } else {
      formData.value[currentPickerField.value] = selectedKnowledgeFile.value.name
      formData.value[currentPickerField.value + 'Id'] = selectedKnowledgeFile.value.id
    }
    filePickerVisible.value = false
    selectedKnowledgeFile.value = null
  }
}

function openLocalFilePicker() {
  currentPickerField.value = 'sourceFile'
  localFileInputRef.value?.click()
}

function onLocalFileSelected(event) {
  const file = event.target.files?.[0]
  if (file) {
    pendingLocalFile = file
    formData.value.sourceFile = file.name
  }
  if (localFileInputRef.value) {
    localFileInputRef.value.value = ''
  }
}

function formatCatScore(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 0
  }
  return Math.round(Number(value) * 100)
}

function catCandidateMatchScore(candidate) {
  if (!candidate) {
    return 0
  }
  if (candidate.semantic_score !== null && candidate.semantic_score !== undefined && !Number.isNaN(Number(candidate.semantic_score))) {
    return Number(candidate.semantic_score)
  }
  return Number(candidate.string_score || 0)
}

function formatCatCandidateMatchRate(candidate) {
  return `${formatCatScore(catCandidateMatchScore(candidate))}%`
}

function formatCatCandidateSource(candidate) {
  const source = String(candidate?.rule_source || '').trim()
  if (source === 'surface_rules') {
    return '数字格式/术语替换'
  }
  if (source === 'sentence_guide') {
    return '句式匹配'
  }
  if (source === 'ai_diagnose') {
    return 'AI 诊断'
  }
  return '候选规则'
}

const CATEGORY_LABELS = {
  spelling: '拼写标点',
  grammar: '语法',
  word: '用词',
  term: '术语',
  ambiguity: '歧义',
  redundancy: '冗余',
  syntax: '句式',
  logic: '逻辑',
  missing: '缺失',
  register: '语体',
  audience: '受众',
  risk: '风险',
  other: '其他'
}

function isDiagnoseCandidate(candidate) {
  return String(candidate?.rule_source || '').trim() === 'ai_diagnose' || Boolean(candidate?.revised && candidate?.problem)
}

function categoryLabel(source) {
  const key = String(source?.category || '').trim()
  return CATEGORY_LABELS[key] || ''
}

function severityClass(source) {
  const severity = String(source?.severity || '').trim()
  if (severity === 'high' || severity === 'medium' || severity === 'low') {
    return `severity-${severity}`
  }
  return ''
}

function formatCatAccuracyRate(value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) {
    return '待评估'
  }
  return `${Number(value)}%`
}

function dedupeCatCandidates(candidates) {
  const bestByText = new Map()
  for (const candidate of candidates || []) {
    const templateText = String(candidate?.template_text || '')
      .replace(/\s+/g, '')
      .replace(/[，。！？!?；;：:、,.\s]+$/g, '')
    if (!templateText) {
      continue
    }
    const current = bestByText.get(templateText)
    if (!current || Number(candidate?.string_score || 0) > Number(current?.string_score || 0)) {
      bestByText.set(templateText, candidate)
    }
  }
  return Array.from(bestByText.values()).sort((a, b) => {
    const semanticDiff = Number(b?.semantic_score ?? -1) - Number(a?.semantic_score ?? -1)
    if (semanticDiff !== 0) {
      return semanticDiff
    }
    return Number(b?.string_score || 0) - Number(a?.string_score || 0)
  })
}

function normalizeCatItems(items) {
  return (items || [])
    .filter(item => item?.has_candidates && Array.isArray(item.candidates) && item.candidates.length > 0)
    .map(item => ({
      rowKey: `${item.source_paragraph_index ?? item.paragraph_index ?? 0}-${item.sentence_index ?? item.paragraph_index ?? 0}-${item.original_text || ''}`,
      paragraphIndex: item.paragraph_index,
      sentenceIndex: item.sentence_index ?? item.paragraph_index ?? 0,
      sourceParagraphIndex: item.source_paragraph_index ?? item.paragraph_index ?? 0,
      sourceParagraphText: item.source_paragraph_text || '',
      originalText: item.original_text || '',
      candidates: dedupeCatCandidates(item.candidates || []),
      selectedCandidateIndex: 0,
      action: 'pending',
      modifiedText: '',
      savedModifiedText: '',
      modifyEditorVisible: false,
      isDraftSaved: false,
      resultCollapsed: false
    }))
}

function catEmptyStateText() {
  if (!catResult.value) {
    return '上传文档后，这里会展示命中的句式候选和逐段确认区。'
  }
  if ((catResult.value.totalWithCandidates || 0) === 0) {
    return '本次分析完成，但没有命中可用的句式候选。'
  }
  if (!catItems.value.length) {
    return '候选结果已返回，但当前没有可展示的条目。'
  }
  return '当前文档没有命中句式候选'
}

function clearCatResult() {
  catResult.value = null
  catItems.value = []
  catApplyResult.value = null
  catDiagnosticExpanded.value = false
  clearCatSessionSnapshot()
}

function toggleCatItemCollapsed(item) {
  if (!item) {
    return
  }
  item.resultCollapsed = !item.resultCollapsed
}

function collapseCatItem(item) {
  if (!item) {
    return
  }
  item.resultCollapsed = true
}

function getCatCollapsedPreviewText(item) {
  if (!item) {
    return ''
  }
  if (item.action === 'reject') {
    const originalText = String(item.originalText || '').trim()
    return originalText || '当前条目已收起'
  }
  const text = String(getCatDisplayText(item) || item.originalText || '').trim()
  return text || '当前条目已收起'
}

function getCatCollapsedLabel(item) {
  if (item?.action === 'accept') {
    return '候选'
  }
  if (item?.action === 'modify') {
    return '自定义'
  }
  return '原文'
}

function renderCatCollapsedPreviewHtml(item) {
  if (!item) {
    return ''
  }
  return `<div class="result-text-block">${escapeHtml(getCatCollapsedPreviewText(item))}</div>`
}

function selectedCatCandidate(item) {
  if (!item || !Array.isArray(item.candidates) || !item.candidates.length) {
    return null
  }
  return item.candidates[item.selectedCandidateIndex] || item.candidates[0] || null
}

function selectedTextCatCandidate(item) {
  if (!item || !Array.isArray(item.candidates) || !item.candidates.length) {
    return null
  }
  return item.candidates[item.selectedCandidateIndex] || item.candidates[0] || null
}

function getTextCatCandidateValue(candidate) {
  return String(candidate?.raw_template_text || candidate?.template_text || '').trim()
}

function getTextCatDisplayText(item) {
  return getTextCatCandidateValue(selectedTextCatCandidate(item))
}

function normalizeTextCatItems(items) {
  return (items || [])
    .filter(item => Array.isArray(item?.candidates) && item.candidates.length > 0)
    .map(item => ({
      rowKey: `${item.paragraph_index ?? 0}-${item.sentence_index ?? 0}-${item.original_text || ''}`,
      paragraphIndex: item.paragraph_index ?? 0,
      sentenceIndex: item.sentence_index ?? 0,
      originalText: item.original_text || '',
      candidates: dedupeCatCandidates(item.candidates || []),
      selectedCandidateIndex: 0,
      applied: false,
    }))
}

function applyTextCatCandidate(item) {
  if (!result.value || !item) {
    return
  }
  const candidate = selectedTextCatCandidate(item)
  const originalSentence = String(item.originalText || '').trim()
  const candidateText = getTextCatCandidateValue(candidate)
  if (!candidateText || !originalSentence) {
    ElMessage.warning('当前候选不可用')
    return
  }
  const currentPolished = String(result.value.basePolished || result.value.polished || '')
  const appliedItems = textCatItems.value.filter(entry => entry && entry.applied)
  let nextPolished = currentPolished
  const pendingItems = [...appliedItems.filter(entry => entry.rowKey !== item.rowKey), { ...item, applied: true, selectedCandidateIndex: item.selectedCandidateIndex }]
  for (const entry of pendingItems) {
    const entryOriginal = String(entry.originalText || '').trim()
    const entryCandidateText = getTextCatCandidateValue(selectedTextCatCandidate(entry))
    if (entryOriginal && entryCandidateText && nextPolished.includes(entryOriginal)) {
      nextPolished = nextPolished.replace(entryOriginal, entryCandidateText)
    }
  }
  item.applied = true
  result.value = {
    ...result.value,
    polished: nextPolished,
    changes: pendingItems.length,
  }
  ElMessage.success('已应用候选句式')
}

function getCatDisplayText(item) {
  if (item?.action === 'modify' && item?.savedModifiedText) {
    return String(item.savedModifiedText || '').trim()
  }
  return String(selectedCatCandidate(item)?.template_text || '').trim()
}

function getEffectiveCatAction(item) {
  if (!item) {
    return 'pending'
  }
  if (item.action === 'accept') {
    return item.isDraftSaved ? 'accept' : 'pending'
  }
  if (item.action === 'modify') {
    return item.isDraftSaved ? 'modify' : 'pending'
  }
  if (item.action === 'reject') {
    return 'reject'
  }
  return 'pending'
}

function markCatItemDirty(item) {
  if (!item) {
    return
  }
  item.isDraftSaved = false
}

function handleCatCandidateChange(item) {
  if (!item) {
    return
  }
  const wasAccepted = item.action === 'accept'
  markCatItemDirty(item)
  if (wasAccepted) {
    item.action = 'pending'
  }
  item.resultCollapsed = false
}

function reopenCatModifyEditor(item) {
  if (!item) {
    return
  }
  item.modifyEditorVisible = true
}

function fillCatModifyFromCandidate(item) {
  if (!item) {
    return
  }
  const candidate = selectedCatCandidate(item)
  item.modifiedText = String(candidate?.template_text || item.originalText || '').trim()
  item.action = 'modify'
  markCatItemDirty(item)
}

function handleCatActionChange(item) {
  if (!item) {
    return
  }
  if (item.action === 'accept') {
    const candidate = selectedCatCandidate(item)
    if (!candidate?.template_text) {
      item.action = 'pending'
      ElMessage.warning('请先选择一个候选句式')
      return
    }
    item.isDraftSaved = true
    collapseCatItem(item)
    ElMessage.success('当前候选已保存')
    return
  }
  if (item.action === 'modify') {
    const candidate = selectedCatCandidate(item)
    item.modifiedText = String(item.savedModifiedText || candidate?.template_text || item.originalText || '').trim()
    item.modifyEditorVisible = true
    item.isDraftSaved = false
    item.resultCollapsed = false
    return
  }
  item.modifyEditorVisible = false
  if (item.action === 'reject') {
    collapseCatItem(item)
  }
  markCatItemDirty(item)
}

function forceCatAction(item, action) {
  if (!item) {
    return
  }
  item.action = action
  handleCatActionChange(item)
}

async function saveCatModify(item) {
  const text = String(item?.modifiedText || '').trim()
  if (!text) {
    ElMessage.warning('请先输入自定义润色文本')
    return
  }
  item.modifiedText = text
  item.savedModifiedText = text
  item.action = 'modify'
  item.isDraftSaved = true
  item.modifyEditorVisible = false
  collapseCatItem(item)
  try {
    const resp = await polishAPI.submitFeedback(
      item?.originalText || '',
      text,
      100,
      text,
      'sentence_guide',
      formData.value.terminologyFileId,
      formData.value.sentenceFileId
    )
    const data = resp?.data || {}
    if (data.processed_count > 0) {
      ElMessage.success('自定义润色文本已保存，并已写入平台反馈句式清单')
    } else {
      ElMessage.success('自定义润色文本已保存，句式清单中已存在相同内容')
    }
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`自定义润色文本已保存，本次写入句式清单失败：${errorMsg}`)
  }
}

function buildCatDecisionPayload() {
  return catItems.value.map(item => {
    const candidate = selectedCatCandidate(item)
    const action = getEffectiveCatAction(item)
    const payload = {
      paragraph_index: item.paragraphIndex,
      sentence_index: item.sentenceIndex,
      source_paragraph_index: item.sourceParagraphIndex,
      source_paragraph_text: item.sourceParagraphText,
      source_sentence_text: item.originalText,
      action,
      original_text: item.originalText,
      string_score: candidate?.string_score || 0,
      semantic_score: candidate?.semantic_score ?? null,
      ai_reason: candidate?.ai_reason || null
    }

    if (action === 'accept' && candidate) {
      payload.accepted_template = candidate.template_text || ''
      payload.accepted_template_id = candidate.template_id || ''
    }
    if (action === 'modify') {
      payload.modified_text = String(item.savedModifiedText || item.modifiedText || '').trim()
    }
    if (action === 'reject' && candidate) {
      payload.rejected_template = candidate.template_text || ''
      payload.rejected_template_id = candidate.template_id || ''
    }
    return payload
  })
}

async function submitCatAnalyze() {
  clearCatResult()
  const payload = new FormData()
  payload.append('file', pendingLocalFile)
  if (formData.value.productType) {
    payload.append('product_type', formData.value.productType)
  }
  if (formData.value.sentenceFileId && !sentenceFileAutoSelected.value) {
    payload.append('sentence_file_id', formData.value.sentenceFileId)
  }
  if (formData.value.terminologyFileId && !terminologyFileAutoSelected.value) {
    payload.append('terminology_file_id', formData.value.terminologyFileId)
  }
  if (formData.value.requirements) {
    payload.append('requirements', formData.value.requirements)
  }
  payload.append('ai_semantic_scoring', formData.value.catAiSemanticScoring ? 'true' : 'false')

  const resp = await polishAPI.catAnalyze(payload)
  const data = resp.data || {}
  docResult.value = null
  catApplyResult.value = null
  catResult.value = {
    analyzeId: data.analyze_id,
    totalParagraphs: data.total_paragraphs || 0,
    totalWithCandidates: data.total_with_candidates || 0,
    templateCoverage: data.template_coverage || 0,
    resolvedTermCount: data.resolved_term_count || 0,
    candidateDebugSummary: {
      templatePoolSize: data.candidate_debug_summary?.template_pool_size || 0,
      templatesConsidered: data.candidate_debug_summary?.templates_considered || 0,
      templatesMatched: data.candidate_debug_summary?.templates_matched || 0,
      returnedCandidatesBeforeAi: data.candidate_debug_summary?.returned_candidates_before_ai || 0,
      surfaceRuleCandidates: data.candidate_debug_summary?.surface_rule_candidates || 0,
      simpleMatchDroppedByReason: data.candidate_debug_summary?.simple_match_dropped_by_reason || {},
      totalBeforeFilter: data.candidate_debug_summary?.total_before_filter || 0,
      totalAfterFilter: data.candidate_debug_summary?.total_after_filter || 0,
      needsReviewCount: data.candidate_debug_summary?.needs_review_count || 0,
      droppedByReason: data.candidate_debug_summary?.dropped_by_reason || {}
    },
    sourceName: pendingLocalFile?.name || formData.value.sourceFile || '',
    aiScoringStatus: data.ai_scoring_status || '',
    aiScoringError: data.ai_scoring_error || ''
  }
  catItems.value = normalizeCatItems([...(data.items || []), ...(data.diagnose_items || [])])
  return data
}

async function applyCatSelections() {
  if (!catResult.value?.analyzeId) {
    ElMessage.warning('请先完成句式分析')
    return
  }

  const invalidModified = catItems.value.some(item => item.action === 'modify' && !String(item.modifiedText || '').trim())
  if (invalidModified) {
    ElMessage.warning('自定义项需要填写最终文本')
    return
  }

  catApplying.value = true
  try {
    const payload = {
      analyze_id: catResult.value.analyzeId,
      source_filename: catResult.value.sourceName || formData.value.sourceFile || 'polished.docx',
      decisions: buildCatDecisionPayload()
    }
    const resp = await polishAPI.catApply(payload)
    const data = resp.data || {}
    catApplyResult.value = {
      outputFile: data.output_file || '',
      downloadUrl: data.download_url || '',
      downloadFilename: data.download_filename || 'polished.docx',
      reportDownloadUrl: data.report_download_url || '',
      reportDownloadFilename: data.report_download_filename || 'polish_report.html',
      appliedChangesCount: Number.isFinite(data.applied_count) ? data.applied_count : (Array.isArray(data.applied_changes) ? data.applied_changes.length : 0),
      failedCount: Number.isFinite(data.failed_count) ? data.failed_count : 0,
      accuracyRate: data.accuracy?.accuracy_rate ?? null,
      docId: data.doc_id || null,
      previewUrl: data.preview_url || '',
      feedback: data.feedback || {}
    }
    if ((data.failed_count || 0) > 0) {
      ElMessage.warning(`润色文档已生成，但 ${data.failed_count} 处替换未能定位原文`)
    } else {
      ElMessage.success('润色文档已生成')
    }
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`生成失败：${errorMsg}`)
  } finally {
    catApplying.value = false
  }
}

async function downloadCatResult() {
  if (!catApplyResult.value?.downloadUrl) {
    ElMessage.warning('当前没有可下载的润色文档')
    return
  }
  try {
    await polishAPI.downloadCatOutput(catApplyResult.value.downloadUrl, catApplyResult.value.downloadFilename)
  } catch (error) {
    ElMessage.error(`下载润色文档失败：${getAPIErrorMessage(error, '下载失败')}`)
  }
}

async function downloadCatReport() {
  if (!catApplyResult.value?.reportDownloadUrl) {
    ElMessage.warning('当前没有可下载的润色报告')
    return
  }
  try {
    await polishAPI.downloadCatAsset(catApplyResult.value.reportDownloadUrl, catApplyResult.value.reportDownloadFilename)
  } catch (error) {
    ElMessage.error(`下载润色报告失败：${getAPIErrorMessage(error, '下载失败')}`)
  }
}

function openCatPreview() {
  if (!catApplyResult.value?.docId) {
    ElMessage.warning('当前没有可预览的润色结果')
    return
  }
  router.push({ name: 'PolishPreview', params: { id: catApplyResult.value.docId } })
}

function readCatSessionSnapshot() {
  if (typeof window === 'undefined') {
    return null
  }
  try {
    const raw = window.sessionStorage.getItem(CAT_SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function clearCatSessionSnapshot() {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.removeItem(CAT_SESSION_KEY)
}

function persistCatSessionSnapshot() {
  if (typeof window === 'undefined') {
    return
  }
  if (!catResult.value || formData.value.documentWorkflow !== 'cat') {
    clearCatSessionSnapshot()
    return
  }
  const payload = {
    version: CAT_SESSION_VERSION,
    formData: {
      productType: formData.value.productType,
      sentenceFile: formData.value.sentenceFile,
      sentenceFileId: formData.value.sentenceFileId || null,
      terminologyFile: formData.value.terminologyFile,
      terminologyFileId: formData.value.terminologyFileId || null,
      sourceFile: formData.value.sourceFile,
      requirements: formData.value.requirements,
      documentWorkflow: formData.value.documentWorkflow || 'cat',
      catAiSemanticScoring: Boolean(formData.value.catAiSemanticScoring)
    },
    catResult: catResult.value,
    catItems: catItems.value,
    catApplyResult: catApplyResult.value
  }
  try {
    window.sessionStorage.setItem(CAT_SESSION_KEY, JSON.stringify(payload))
  } catch {
    // Ignore storage quota errors and keep current interaction available.
  }
}

function persistCatSessionSnapshotDebounced() {
  if (catSessionPersistTimer) {
    window.clearTimeout(catSessionPersistTimer)
  }
  catSessionPersistTimer = window.setTimeout(() => {
    persistCatSessionSnapshot()
    catSessionPersistTimer = null
  }, 300)
}

function restoreCatSessionSnapshot() {
  const snapshot = readCatSessionSnapshot()
  if (!snapshot?.catResult) {
    return
  }
  if (snapshot.version !== CAT_SESSION_VERSION) {
    clearCatSessionSnapshot()
    return
  }
  const restoredFormData = snapshot.formData || {}
  formData.value = {
    ...formData.value,
    ...restoredFormData,
    documentWorkflow: normalizeDocumentWorkflow(restoredFormData.documentWorkflow),
    catAiSemanticScoring: Boolean(restoredFormData.catAiSemanticScoring)
  }
  catResult.value = snapshot.catResult || null
  catItems.value = Array.isArray(snapshot.catItems)
    ? snapshot.catItems.map(item => ({
      ...item,
      resultCollapsed: Boolean(item?.resultCollapsed)
    }))
    : []
  catApplyResult.value = snapshot.catApplyResult || null
  catDiagnosticExpanded.value = false
}

async function submitPolish() {
  if (!pendingLocalFile) {
    ElMessage.warning('请选择待润色文件')
    return
  }
  
  loading.value = true
  startDocumentProgress()
  
  try {
    const sourceName = pendingLocalFile?.name || formData.value.sourceFile || ''
    if (formData.value.documentWorkflow === 'cat') {
      await submitCatAnalyze()
    } else {
      const payload = new FormData()
      payload.append('file', pendingLocalFile)
      if (formData.value.productType) {
        payload.append('product_type', formData.value.productType)
      }
      if (formData.value.sentenceFileId && !sentenceFileAutoSelected.value) {
        payload.append('sentence_file_id', formData.value.sentenceFileId)
      }
      if (formData.value.terminologyFileId && !terminologyFileAutoSelected.value) {
        payload.append('terminology_file_id', formData.value.terminologyFileId)
      }
      if (formData.value.requirements) {
        payload.append('requirements', formData.value.requirements)
      }
      const data = await polishStore.submitDocumentPolish(payload, sourceName)
      applyDocumentResult(data, sourceName)
    }
    polishProgress.value = 100
    polishProgressMsg.value = formData.value.documentWorkflow === 'cat' ? '句式分析完成' : '润色完成'
    stopDocumentProgress()
    ElMessage.success(formData.value.documentWorkflow === 'cat' ? '句式分析完成' : '润色成功')
    // 清空已选择的文件
    pendingLocalFile = null
    if (localFileInputRef.value) {
      localFileInputRef.value.value = ''
    }
    await nextTick()
    formData.value.sourceFile = ''
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`润色失败：${errorMsg}`)
    polishProgress.value = 0
    polishProgressMsg.value = ''
    stopDocumentProgress()
  } finally {
    loading.value = false
    stopDocumentProgress()
    // pendingLocalFile 在成功/失败分支已处理，此处不再重复清空
  }
}

function resetForm() {
  if (loading.value && activeTextPolishController) {
    activeTextPolishController.abort()
    activeTextPolishController = null
  }
  formData.value = {
    productType: '',
    sentenceFile: '',
    sentenceFileId: null,
    terminologyFile: '',
    terminologyFileId: null,
    sourceFile: '',
    outputPath: '已润色文档',
    requirements: '',
    documentWorkflow: normalizeDocumentWorkflow(formData.value.documentWorkflow),
    catAiSemanticScoring: false
  }
  formData.value.documentWorkflow = showStandardDocumentWorkflow.value ? normalizeDocumentWorkflow(formData.value.documentWorkflow) : 'cat'
  formData.value.sentenceFile = ''
  formData.value.terminologyFile = ''
  sentenceFileAutoSelected.value = false
  terminologyFileAutoSelected.value = false
  textSentenceFileAutoSelected.value = false
  textTerminologyFileAutoSelected.value = false
  textSentenceFileId.value = null
  textTerminologyFileId.value = null
  textProductType.value = ''
  textSentenceFileName.value = ''
  textTerminologyFileName.value = ''
  sentenceFileOptions.value = allSentenceFileOptions.value
  termFileOptions.value = allTermFileOptions.value
  textSentenceFileOptions.value = allSentenceFileOptions.value
  textTermFileOptions.value = allTermFileOptions.value
  syncProductMatchedFileOptions()
  syncTextProductMatchedFileOptions(true)
  pendingLocalFile = null
  selectedKnowledgeFile.value = null
  docResult.value = null
  clearCatResult()
  result.value = null
  textCatItems.value = []
  originalText.value = ''
  resetFeedbackForm()
  docKeywordFilter.value = ''
  docFeedbackLoading.value = false
  polishProgress.value = 0
  polishProgressMsg.value = ''
  loading.value = false
  stopDocumentProgress()
  polishStore.clearDocumentSession()
}

function downloadPolishedDoc() {
  if (!docResult.value) {
    ElMessage.warning('暂无润色结果')
    return
  }
  // 如果后端已保存 DOCX 文件，通过 API 下载原始文件
  if (docResult.value.id) {
    const downloadName = docResult.value.download_filename || 'polished_document.docx'
    polishAPI.downloadPolishedFile(docResult.value.id, downloadName)
    return
  }
  // 纯文本结果 fallback
  const ext = docResult.value.fileType === 'docx' ? '.docx' : '.txt'
  const blob = new Blob([docResult.value.polished], { type: 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `polished_document${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

function downloadReport() {
  if (!docResult.value || !docResult.value.reportFile || !docResult.value.id) {
    ElMessage.warning('暂无润色报告')
    return
  }
  polishAPI.downloadPolishedReport(docResult.value.id, docResult.value.reportFile)
}

async function doPolish() {
  if (loading.value && activeTextPolishController) {
    activeTextPolishController.abort()
    activeTextPolishController = null
    loading.value = false
    ElMessage.error('已停止润色')
    return
  }
  if (!originalText.value.trim()) {
    ElMessage.info('请先输入需要润色的文本')
    return
  }
  const controller = new AbortController()
  activeTextPolishController = controller
  loading.value = true
  try {
    const resp = await polishAPI.text({
      text: originalText.value,
      productType: textProductType.value,
      styleGuideId: textSentenceFileAutoSelected.value ? null : textSentenceFileId.value,
      terminologyId: textTerminologyFileAutoSelected.value ? null : textTerminologyFileId.value
    }, {
      signal: controller.signal
    })
    const data = resp.data || {}
    result.value = {
      original: data.original || originalText.value,
      basePolished: data.base_polished || data.polished || data.original || originalText.value,
      polished: data.polished || data.original || originalText.value,
      changes: data.changes?.length || 0
    }
    textCatItems.value = normalizeTextCatItems(data.cat_items || [])
    const nextDisplayedText = getDisplayedPolishedText(result.value, textCatItems.value)
    if (!nextDisplayedText || nextDisplayedText === result.value.original) {
      ElMessage.info('润色完成，未检测到需要修改的内容')
    } else {
      ElMessage.success('润色完成')
    }
  } catch (e) {
    if (axios.isCancel(e) || e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') {
      return
    }
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`润色失败：${errorMsg}`)
    result.value = null
    textCatItems.value = []
  } finally {
    if (activeTextPolishController === controller) {
      activeTextPolishController = null
    }
    loading.value = false
  }
}

function clearAll() {
  if (loading.value && activeTextPolishController) {
    activeTextPolishController.abort()
    activeTextPolishController = null
  }
  originalText.value = ''
  result.value = null
  textCatItems.value = []
  textProductType.value = ''
  textSentenceFileName.value = ''
  textSentenceFileId.value = null
  textSentenceFileAutoSelected.value = false
  textTerminologyFileName.value = ''
  textTerminologyFileId.value = null
  textTerminologyFileAutoSelected.value = false
  textSentenceFileOptions.value = allSentenceFileOptions.value
  textTermFileOptions.value = allTermFileOptions.value
  loading.value = false
  syncTextProductMatchedFileOptions(true)
  resetFeedbackForm()
}

function copyResult() {
  navigator.clipboard.writeText(displayedPolishedText.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => ElMessage.info('复制失败，请手动复制'))
}

function downloadResult() {
  const blob = new Blob([displayedPolishedText.value], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'polished_document.txt'
  a.click()
  URL.revokeObjectURL(url)
}

async function submitFeedback() {
  if (!result.value) {
    ElMessage.warning('请先完成润色再提交反馈')
    return
  }
  if (!feedbackAccuracy.value) {
    ElMessage.warning('请先选择准确度评分')
    return
  }
  let corrections = feedbackType.value === 'term' ? buildTermCorrections() : String(sentenceCorrections.value || '').trim()
  if (feedbackAccuracy.value < 100 && !corrections) {
    try {
      await ElMessageBox.confirm(
        '需要提交修正信息，以便优化准确率吗？',
        '提示',
        {
          confirmButtonText: '是',
          cancelButtonText: '否',
          distinguishCancelAndClose: true,
          closeOnClickModal: false,
          closeOnPressEscape: false,
          type: 'warning',
        }
      )
      return
    } catch (action) {
      if (action !== 'cancel') {
        return
      }
      corrections = ''
    }
  }
  feedbackLoading.value = true
  try {
    const resp = await polishAPI.submitFeedback(
      result.value.original,
      displayedPolishedText.value,
      feedbackAccuracy.value,
      corrections,
      feedbackTarget.value,
      textTerminologyFileId.value,
      textSentenceFileId.value
    )
    const data = resp.data || {}
    const targetName = feedbackTargetLabel()
    if (data.processed_count > 0) {
      ElMessage.success(`反馈已提交，已将 ${data.processed_count} 条修正写入${targetName}`)
    } else {
      ElMessage.success('反馈已提交')
    }
    window.dispatchEvent(new CustomEvent('polish-text-feedback-submitted', {
      detail: {
        accuracy: feedbackAccuracy.value,
        target: feedbackTarget.value,
        createdAt: new Date().toISOString(),
      }
    }))
    resetFeedbackForm()
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`反馈失败：${errorMsg}`)
  } finally {
    feedbackLoading.value = false
  }
}

async function loadPolishEngineStatus() {
  try {
    const resp = await systemAPI.getAIStatus()
    const providers = resp.data?.providers || {}
    if (providers.kimi?.status === 'ok') {
      currentPolishEngine.value = 'Kimi'
      return
    }
    currentPolishEngine.value = '本地润色'
  } catch (e) {
    console.error('加载润色引擎状态失败:', e)
    currentPolishEngine.value = '本地润色'
  }
}

async function submitDocumentFeedback() {
  docFeedbackLoading.value = true
  try {
    const data = await persistDocumentDecisions(true, true)
    if (data) {
      window.dispatchEvent(new CustomEvent('polish-document-feedback-submitted', {
        detail: {
          documentId: data.document_id || docResult.value?.id || null,
          analyzeId: docResult.value?.id || null,
          sourceFilename: docResult.value?.sourceName || formData.value.sourceFile || '',
        },
      }))
    }
  } finally {
    docFeedbackLoading.value = false
  }
}

watch(formData, (value) => {
  polishStore.updateDocumentDraft({
    productType: value.productType,
    sentenceFile: value.sentenceFile,
    sentenceFileId: value.sentenceFileId || null,
    terminologyFile: value.terminologyFile,
    terminologyFileId: value.terminologyFileId || null,
    sourceFile: value.sourceFile,
    outputPath: value.outputPath,
    requirements: value.requirements,
    documentWorkflow: value.documentWorkflow || 'standard',
    catAiSemanticScoring: Boolean(value.catAiSemanticScoring)
  })
}, { deep: true })

watch(() => formData.value.documentWorkflow, (mode) => {
  if (mode === 'cat') {
    docResult.value = null
  } else {
    clearCatResult()
  }
})

watch(
  [() => catResult.value, () => catItems.value, () => catApplyResult.value, () => formData.value.documentWorkflow],
  () => {
    persistCatSessionSnapshotDebounced()
  },
  { deep: true }
)

watch(documentSession, (session) => {
  loading.value = session.loading
  polishProgress.value = session.progress || 0
  polishProgressMsg.value = session.message || ''
  if (session.result) {
    applyDocumentResult(session.result, documentDraft.value.sourceFile || '')
  } else if (!session.loading) {
    docResult.value = null
  }
}, { deep: true, immediate: true })

onMounted(async () => {
  const pendingPolishText = sessionStorage.getItem('pendingPolishLabText')
  if (pendingPolishText) {
    originalText.value = pendingPolishText
    sessionStorage.removeItem('pendingPolishLabText')
  }
  restoreCatSessionSnapshot()
  loadDropdownOptions()
  await loadPolishEngineStatus()
})
</script>

<style scoped>
.polish-container { 
  padding: 0 0 40px; 
  max-width: none;
  width: 100%;
}

.polish-container.document-mode {
  min-height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.document-view {
  flex: 1;
  min-height: auto;
  display: flex;
  flex-direction: column;
  overflow: visible;
}

/* ── 标题行 ── */
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #111827;
  margin: 0;
}

.page-title-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 14px;
  margin-bottom: 18px;
  flex: 0 0 auto;
}

.title-progress-inline {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: #3b82f6;
  font-weight: 600;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 20px;
  padding: 3px 14px;
}

/* ── 面板 ── */
.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 16px;
}

.workflow-radio-group {
  display: inline-flex;
}

.form-helper-text {
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.cat-ai-switch-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.cat-ai-switch-text {
  margin-top: 0;
}

.cat-result-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: auto;
  overflow: visible;
}

.cat-review-panel {
  gap: 12px;
  min-height: auto;
  height: auto;
}

.cat-review-debug-bar {
  margin-top: -2px;
}

.cat-review-toolbar {
  padding-top: 2px;
}

.cat-toolbar-hint {
  font-size: 13px;
  color: #475569;
}

.cat-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.cat-summary-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #f8fafc;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cat-summary-card strong {
  font-size: 22px;
  color: #0f172a;
}

.cat-summary-label {
  font-size: 12px;
  color: #64748b;
}

.cat-apply-banner {
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.cat-apply-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.cat-ai-status-banner {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  border: 1px solid #dbeafe;
  background: #f8fbff;
}

.cat-ai-status-banner.completed {
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.cat-ai-status-banner.no_api_key,
.cat-ai-status-banner.skipped,
.cat-ai-status-banner.failed,
.cat-ai-status-banner.error,
.cat-ai-status-banner.parse_error,
.cat-ai-status-banner.invalid_payload,
.cat-ai-status-banner.empty {
  border-color: #fde68a;
  background: #fffbeb;
}

.cat-ai-status-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.cat-ai-status-text {
  font-size: 12px;
  color: #475569;
}

.cat-apply-title {
  font-size: 14px;
  font-weight: 700;
  color: #1d4ed8;
}

.cat-apply-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #475569;
}

.cat-item-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: visible;
  padding-right: 0;
}

.cat-item-card {
  border: 1px solid #dbe4f0;
  border-left: 4px solid #94a3b8;
  border-radius: 14px;
  padding: 16px;
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.cat-item-card.severity-high,
.text-cat-item-row.severity-high {
  border-left-color: #dc2626;
}

.cat-item-card.severity-medium,
.text-cat-item-row.severity-medium {
  border-left-color: #f59e0b;
}

.cat-item-card.severity-low,
.text-cat-item-row.severity-low {
  border-left-color: #64748b;
}

.cat-issue-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}

.cat-category-tag {
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  height: 22px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 12px;
  line-height: 22px;
}

.cat-diagnose-meta {
  margin-top: 8px;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.cat-diagnose-problem {
  font-weight: 600;
  color: #334155;
}

.cat-diagnose-rationale {
  margin-top: 2px;
}

.cat-item-card.is-collapsed {
  padding-bottom: 12px;
}

.cat-item-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
}

.cat-item-header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.cat-item-collapsed-preview {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  line-height: 1.45;
  color: #475569;
  padding: 8px 10px 0;
  white-space: break-spaces;
}

.cat-item-collapsed-label {
  flex: 0 0 auto;
  color: #64748b;
  font-size: 12px;
  line-height: 1.8;
}

.cat-item-collapsed-preview .issue-diff-content {
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
}

.cat-item-title {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 6px;
}

.cat-item-section {
  margin-top: 14px;
}

.cat-item-section-compact {
  margin-top: 12px;
}

.cat-item-section-surface {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  padding: 12px 14px;
}

.cat-item-section-surface-muted {
  background: linear-gradient(180deg, #ffffff, #f8fafc);
}

.cat-item-section-surface-edit {
  background: linear-gradient(180deg, #fffdf7, #fff7ed);
  border-color: #fed7aa;
  padding: 12px 14px;
}

.cat-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.cat-issue-diff-card {
  margin-bottom: 6px;
  border-color: #dbe4f0;
  background: linear-gradient(180deg, #f8fbff, #f8fafc);
}

.cat-item-inline-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  flex-wrap: wrap;
}

.cat-item-status-row {
  margin-top: 10px;
}

.cat-item-saved-hint {
  color: #047857;
  font-size: 12px;
  font-weight: 600;
}

.cat-action-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.cat-action-group :deep(.el-radio-button__inner) {
  min-width: 84px;
  padding: 7px 12px;
}

.cat-compare-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.cat-compare-grid.is-single {
  grid-template-columns: minmax(0, 1fr);
}

.cat-compare-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #f8fafc;
  overflow: hidden;
}

.cat-compare-card.is-candidate {
  background: #f0fdf4;
  border-color: #bbf7d0;
}

.cat-compare-card.is-full-width {
  width: 100%;
}

.cat-compare-title {
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.cat-compare-content {
  padding: 12px;
  color: #0f172a;
  line-height: 1.8;
}

.cat-compare-content :deep(.diff-add) {
  background: #fee2e2;
  color: #991b1b;
  padding: 1px 4px;
  border-radius: 4px;
  font-weight: 600;
}

.cat-compare-content :deep(.diff-remove) {
  color: #b91c1c;
  text-decoration: line-through;
  text-decoration-color: #dc2626;
  text-decoration-thickness: 2px;
  margin-right: 2px;
}

.cat-candidate-meta-inline {
  padding: 0 12px 12px;
}

.cat-item-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
}

.cat-candidate-select-shell {
  position: relative;
}

.cat-candidate-select-overlay {
  position: absolute;
  top: 10px;
  left: 13px;
  right: 48px;
  z-index: 2;
  pointer-events: none;
  color: #0f172a;
  font-size: 14px;
  line-height: 1.65;
  white-space: break-spaces;
  word-break: break-word;
  max-height: 52px;
  overflow: hidden;
}

.cat-item-section-surface :deep(.el-select__wrapper) {
  min-height: 64px;
  height: auto;
  max-height: 80px;
  align-items: flex-start;
  padding-top: 9px;
  padding-bottom: 9px;
}

.cat-item-section-surface :deep(.el-select__selection) {
  align-items: flex-start;
  max-height: 52px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 20px;
  scrollbar-width: thin;
}

.cat-item-section-surface :deep(.el-select__selected-item) {
  display: block;
  white-space: normal;
  overflow: hidden;
  text-overflow: unset;
  line-height: 1.5;
  word-break: break-word;
  opacity: 0;
}

.cat-candidate-select :deep(.el-select__placeholder) {
  opacity: 0;
}

.cat-item-section-surface :deep(.el-select__placeholder) {
  white-space: normal;
  line-height: 1.45;
}

:deep(.cat-candidate-select-popper .el-select-dropdown__item) {
  min-height: 56px;
  height: auto;
  white-space: normal;
  align-items: stretch;
  line-height: 1.5;
  padding-top: 10px;
  padding-bottom: 10px;
}

:deep(.cat-candidate-select-popper .el-select-dropdown__wrap),
:deep(.cat-candidate-select-popper .el-scrollbar__wrap) {
  max-height: 420px;
  scrollbar-width: thin;
}

.cat-candidate-option {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  width: 100%;
  padding: 2px 0;
}

.cat-candidate-text {
  color: #0f172a;
  line-height: 1.5;
  white-space: break-spaces;
  word-break: break-word;
}

.cat-candidate-score {
  flex: 0 0 auto;
  font-size: 12px;
  color: #1d4ed8;
  font-weight: 700;
  line-height: 1.45;
  white-space: nowrap;
}

.doc-layout {
  display: flex;
  gap: 18px;
  align-items: stretch;
  width: 100%;
  flex: 1 0 auto;
  height: auto;
  min-height: auto;
  overflow: visible;
}

.doc-left {
  flex: 1 1 0;
  height: auto;
  min-width: 0;
  min-height: auto;
  display: flex;
  flex-direction: column;
}

.doc-right {
  flex: 2 1 0;
  height: auto;
  min-width: 0;
  min-height: auto;
  display: flex;
  flex-direction: column;
}

.document-result-mode {
  min-height: calc(100vh - 168px);
}

.doc-layout-result-only {
  display: block;
}

.doc-layout-result-only .doc-left {
  display: none;
}

.doc-layout-result-only .doc-right,
.doc-right-full {
  display: block;
  flex: none;
  width: 100%;
}

.doc-left {
  margin-top: 2mm;
}

.doc-right {
  margin-top: 2mm;
}

.doc-right-full {
  margin-top: 0;
}

.doc-input-panel {
  width: 100%;
  flex: 1;
  margin-bottom: 0;
}

.doc-button-group {
  margin-top: 18px;
  margin-bottom: 0;
}

.doc-result-panel {
  flex: 1;
  height: auto;
  min-height: auto;
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.doc-right-full .doc-result-panel {
  min-height: calc(100vh - 220px);
  height: 100%;
}

.doc-result-preview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
  height: 220px;
  min-height: 0;
  flex: 0 0 220px;
}

.doc-result-table-wrap {
  height: 400px;
  min-height: 400px;
  max-height: 400px;
  flex: 0 0 400px;
}

.doc-review-panel {
  flex: 1;
  min-height: auto;
  height: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px;
  background: #f8fafc;
}

.document-result-mode .doc-review-panel {
  min-height: 0;
  overflow: auto;
}

.doc-review-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #111827;
}

.doc-review-summary-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.doc-review-debug-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.doc-debug-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 10px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}

.doc-review-count {
  font-size: 16px;
  font-weight: 700;
}

.doc-review-confirmed {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.doc-review-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.doc-review-filters,
.doc-review-bulk-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-label {
  font-size: 13px;
  color: #64748b;
}

.doc-filter-select {
  width: 150px;
}

.doc-filter-search {
  width: 220px;
}

.doc-issue-list {
  flex: 1;
  min-height: 0;
  height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 4px;
}

.doc-issue-card {
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
  padding: 16px;
  transition: opacity 0.2s ease, border-color 0.2s ease;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.doc-issue-card.is-accepted {
  opacity: 0.62;
  border-color: #bbf7d0;
  background: #f0fdf4;
}

.doc-issue-card.is-rejected {
  opacity: 0.62;
  border-color: #fecaca;
  background: #fef2f2;
}

.doc-issue-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.doc-issue-title {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}

.doc-issue-title-wrap {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.doc-issue-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.issue-score-inline {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 110px;
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 12px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.trigger-pill,
.paragraph-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.trigger-high {
  background: #dcfce7;
  color: #166534;
}

.trigger-medium {
  background: #fef3c7;
  color: #92400e;
}

.trigger-low {
  background: #fee2e2;
  color: #991b1b;
}

.paragraph-pill {
  background: #eef2ff;
  color: #3730a3;
}

.doc-issue-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
}

.issue-line {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.issue-label {
  flex: 0 0 48px;
  color: #64748b;
  font-weight: 700;
}

.issue-text {
  min-width: 0;
  flex: 1;
  word-break: break-word;
}

.issue-diff-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid #e2e8f0;
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  border-radius: 12px;
  padding: 10px;
}

.issue-diff-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.issue-diff-label {
  flex: 0 0 40px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.8;
  text-transform: uppercase;
}

.issue-diff-content {
  min-width: 0;
  flex: 1;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.65;
  white-space: break-spaces;
}

.cat-selected-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.45;
  color: #64748b;
}

.cat-selected-source {
  color: #1d4ed8;
  font-weight: 700;
}

.issue-diff-original {
  color: #475569;
}

.issue-diff-suggested {
  color: #0f172a;
  font-weight: 400;
}

.issue-diff-content :deep(.diff-highlight) {
  display: inline;
  padding: 0 2px;
  border-radius: 4px;
}

.issue-diff-content :deep(.diff-highlight-suggested) {
  background: #fecaca;
  color: #991b1b;
}

.issue-diff-content :deep(.diff-highlight-original) {
  background: #bbf7d0;
  color: #166534;
}

.issue-diff-content :deep(.diff-space) {
  display: inline-block;
  min-width: 0.72em;
  text-align: center;
  color: inherit;
  font-size: 0.9em;
  vertical-align: baseline;
}

.issue-basis {
  color: #64748b;
}

.issue-match-card {
  border: 1px solid #e2e8f0;
  background: linear-gradient(180deg, #f8fbff, #f8fafc);
  border-radius: 12px;
  padding: 12px;
}

.issue-match-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.issue-match-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.issue-ai-title {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
}

.issue-ai-score {
  font-size: 12px;
  font-weight: 700;
  color: #1d4ed8;
}

.issue-candidate-list {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.issue-candidate-list-inline {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}

.issue-ai-card {
  margin-top: 12px;
  border: 1px solid #fecaca;
  border-radius: 12px;
  background: linear-gradient(135deg, #fff1f2, #fff7ed);
  padding: 12px;
}

.issue-ai-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.issue-ai-card-reason {
  font-size: 13px;
  line-height: 1.7;
  color: #7f1d1d;
}

.issue-candidate-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
}

.issue-candidate-count {
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
}

.issue-candidate-select {
  width: 100%;
}

.issue-candidate-option {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  padding: 4px 0;
}

.issue-candidate-option-main {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.issue-candidate-option-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.issue-candidate-option-text {
  min-width: 0;
  flex: 1;
  color: #334155;
  font-weight: 500;
  word-break: break-word;
  white-space: break-spaces;
  line-height: 1.6;
}

.issue-candidate-ai-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 22px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.issue-candidate-ai-badge.is-recommended {
  background: #dcfce7;
  color: #166534;
}

.issue-candidate-ai-badge.is-neutral {
  background: #fef3c7;
  color: #92400e;
}

.issue-candidate-option-meta {
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
  white-space: normal;
}

.issue-candidate-option-ai {
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
  white-space: normal;
}

.issue-candidate-option-percent {
  flex: 0 0 52px;
  min-width: 52px;
  color: #2563eb;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
  align-self: flex-start;
}

.issue-diff-content :deep(.diff-add) {
  background: #fecaca;
  color: #991b1b;
  padding: 1px 4px;
  border-radius: 4px;
}

.issue-diff-content :deep(.diff-remove) {
  background: #bbf7d0;
  color: #166534;
  padding: 1px 4px;
  border-radius: 4px;
}

.issue-candidate-empty {
  border: 1px dashed #cbd5e1;
  background: #f8fafc;
  border-radius: 8px;
  padding: 10px 12px;
  color: #64748b;
  font-size: 12px;
}

.custom-edit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.doc-issue-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 2px;
}

.doc-review-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 2px;
}

.doc-change-table-scroll {
  height: 400px;
  min-height: 400px;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.doc-change-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}

.doc-change-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #e5e7eb;
  font-weight: 700;
  color: #111827;
  padding: 12px 10px;
  border-bottom: 1px solid #d1d5db;
  text-align: left;
  font-size: 13px;
}

.doc-change-table tbody td {
  vertical-align: top;
  padding: 12px 10px;
  border-bottom: 1px solid #eef2f7;
  color: #374151;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}

.doc-change-table tbody tr:nth-child(even) {
  background: #fafafa;
}

.doc-change-table .col-index {
  width: 70px;
}

.doc-change-table .col-type {
  width: 110px;
}

.doc-change-table .col-accepted {
  width: 180px;
}

.doc-change-table .col-accepted :deep(.el-checkbox) {
  align-items: flex-start;
  margin-right: 12px;
}

.doc-change-empty {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
  color: #94a3b8;
  font-size: 13px;
  background: #fafbfc;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f3f4f6;
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.button-loading-icon {
  margin-right: 4px;
}

.result-header-inline {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ── 文件选择行 ── */
.file-select-row {
  display: flex;
  gap: 16px;
}

.file-select-col {
  flex: 1;
  min-width: 0;
}

/* ── 左右分栏 ── */
.content-row {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.content-left {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.content-left .panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.text-input-shell {
  flex: 1;
  display: flex;
  min-height: 0;
}

.content-left .panel :deep(.el-textarea) {
  display: flex;
  flex: 1;
  width: 100%;
}

.content-left .panel :deep(.el-textarea__inner) {
  height: 100%;
  resize: vertical;
}

.content-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.content-right .panel {
  display: flex;
  flex-direction: column;
}

/* ── 结果面板 ── */
.result-panel {
  margin-bottom: 0;
  overflow: visible;
}

.content-right .result-panel {
  min-height: 0;
}

.result-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.result-panel .result-grid-vertical {
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.result-placeholder {
  border-style: dashed;
  border-color: #e5e7eb;
  background: #fafbfc;
  display: flex;
  flex-direction: column;
}

.placeholder-text {
  text-align: center;
  padding: 36px 20px;
  color: #94a3b8;
  font-size: 13px;
}

.result-grid-vertical {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.result-col-v {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: visible;
  display: flex;
  flex-direction: column;
}

.col-content-compact {
  padding: 10px 12px;
  line-height: 1.6;
  color: #374151;
  font-size: 14px;
  white-space: pre-wrap;
}

.text-single-candidate-card {
  margin-top: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid #fb7185;
  box-shadow: inset 0 0 0 1px rgba(251, 113, 133, 0.12);
  background: linear-gradient(180deg, #fff7ed, #fff1f2 45%, #fff7ed);
  border-radius: 10px;
  padding: 14px;
}

.text-single-candidate-body {
  font-size: 13px;
  line-height: 1.75;
  color: #7f1d1d;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.68);
  border: 1px solid rgba(253, 164, 175, 0.4);
}

.text-single-candidate-body :deep(.result-text-block) {
  margin: 0;
}

.text-single-candidate-body :deep(.diff-add) {
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff7ed;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  box-shadow: 0 0 0 1px rgba(190, 24, 93, 0.16);
}

.text-single-candidate-body :deep(.diff-remove) {
  background: #fde68a;
  color: #92400e;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
}

.text-cat-panel {
  margin-top: 8px;
}

.text-cat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.text-cat-header > span:first-child {
  font-size: 13px;
}

.text-cat-count {
  font-size: 12px;
  color: #64748b;
}

.text-cat-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.text-cat-item-row {
  padding: 8px 10px;
  border-left: 4px solid #94a3b8;
  border-radius: 8px;
  background: #f8fafc;
}

.text-cat-item-row .cat-item-body {
  margin-top: 0;
}

.col-content-compact :deep(.diff-highlight) {
  display: inline;
  color: #dc2626;
  background: #fecaca;
  font-weight: 600;
  border-radius: 3px;
  padding: 0 2px;
}

.col-content-compact :deep(.diff-highlight-suggested) {
  color: #991b1b;
  background: #fecaca;
}

.col-content-compact :deep(.diff-highlight-original) {
  color: #166534;
  background: #bbf7d0;
}

.col-content-compact :deep(.diff-space) {
  display: inline-block;
  min-width: 0.72em;
  text-align: center;
  color: inherit;
  font-size: 0.9em;
  vertical-align: baseline;
}

.doc-change-table td :deep(.diff-highlight) {
  color: #dc2626;
  background: #fecaca;
  font-weight: 600;
  border-radius: 3px;
}

.title-progress-inline {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: #3b82f6;
  font-weight: 600;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 20px;
  padding: 3px 14px;
}

/* ── 进度条（准确率区块后面） ── */
.polish-progress-float {
  display: inline-flex;
  align-items: center;
  gap: 0;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  overflow: hidden;
  font-size: 13px;
  min-width: 280px;
  padding: 4px 16px;
}

.polish-progress-float.done {
  opacity: 0.5;
}

.progress-float-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #374151;
  font-weight: 600;
  white-space: nowrap;
}

.progress-float-text {
  white-space: nowrap;
}

.progress-float-eta {
  color: #64748b;
  font-weight: 500;
  white-space: nowrap;
}

.progress-float-body {
  margin-left: 14px;
  min-width: 140px;
  flex: 1;
}

.feedback-panel {
  margin-top: 16px;
}

.feedback-rating-row,
.feedback-type-row {
  margin-bottom: 14px;
}

.feedback-rating-group {
  display: flex;
  flex-wrap: wrap;
}

.feedback-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.term-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.term-arrow {
  color: #94a3b8;
  font-weight: 700;
  flex: 0 0 auto;
  line-height: 1;
}

.term-row .el-input {
  flex: 1 1 0;
}

.term-row .el-input :deep(.el-input__wrapper) {
  min-height: 36px;
  height: 36px;
  padding: 0 12px;
}

.term-row .el-button {
  flex: 0 0 auto;
  padding: 0 6px;
  height: 36px;
}

.feedback-bottom {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
  padding-top: 12px;
  border-top: 1px solid #f3f4f6;
}

/* ── 表单 ── */
.form-item { margin-bottom: 14px; }

.form-label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #374151;
  font-size: 13px;
}

.feedback-hint {
  margin-top: 6px;
  color: #6b7280;
  font-size: 12px;
}

.feedback-rating-group {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
}

.feedback-rating-inline {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.feedback-rating-btn {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s;
  outline: none;
}

.feedback-rating-btn:hover {
  background: rgba(245, 158, 11, 0.1);
}

.feedback-rating-btn.active {
  background: rgba(245, 158, 11, 0.14);
}

.rating-star {
  font-size: 22px;
  color: #d1d5db;
  line-height: 1;
}

.feedback-rating-btn.active .rating-star {
  color: #f59e0b;
}

.feedback-rating-text {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
  line-height: 1.4;
  flex: 1 1 140px;
  min-width: 0;
}

.input-with-button {
  display: flex;
  gap: 8px;
  align-items: center;
}

.input-with-button .el-input,
.input-with-button .el-select {
  flex: 1;
  min-width: 0;
}

.polish-container :deep(.el-input__inner),
.polish-container :deep(.el-textarea__inner),
.polish-container :deep(.el-select__selected-item),
.polish-container :deep(.el-select__placeholder),
.polish-container :deep(.el-select-dropdown__item) {
  font-size: 14px;
}

.full-width {
  width: 100%;
}

.button-group {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

/* ── 旧样式保留 ── */
.col-title {
  padding: 8px 14px;
  background: #fff;
  font-weight: 500;
  font-size: 13px;
  color: #374151;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}

.dot-blue { background: #3b82f6; }
.dot-green { background: #10b981; }

.file-picker-content {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px;
}

.picker-empty {
  padding: 24px 12px;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
}

.picker-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.picker-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #111827;
  cursor: pointer;
  text-align: left;
}

.picker-row:hover {
  background: #f8fafc;
}

.picker-row.is-folder {
  font-weight: 600;
  color: #334155;
}

.picker-row.is-file {
  color: #475569;
}

.picker-row.is-selected {
  background: #ecfdf5;
  color: #065f46;
}

.picker-name {
  min-width: 0;
  word-break: break-all;
}

.tree-node-content {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.node-icon {
  font-size: 14px;
}

.selected-info {
  margin-top: 10px;
  color: #059669;
  font-size: 13px;
}

.progress-card {
  margin-top: 16px;
  padding: 14px 18px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.progress-dialog-body {
  padding: 6px 2px 2px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

@media (max-width: 960px) {
  .doc-layout,
  .content-row,
  .file-select-row,
  .feedback-row {
    flex-direction: column;
  }

  .doc-result-preview {
    grid-template-columns: 1fr;
  }

  .doc-result-panel,
  .doc-review-panel,
  .doc-issue-list,
  .doc-result-table-wrap,
  .doc-change-table-scroll {
    max-height: none;
    height: auto;
    min-height: 0;
  }

  .feedback-bottom {
    align-items: flex-start;
    gap: 12px;
    flex-direction: column;
  }

  .feedback-rating-btn {
    flex: 0 0 calc(33.333% - 8px);
  }

  .cat-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .cat-apply-banner,
  .cat-item-header,
  .cat-compare-grid {
    flex-direction: column;
    align-items: flex-start;
  }

  .cat-compare-grid {
    display: flex;
  }
}

.progress-msg {
  flex: 1;
  font-size: 13px;
  color: #374151;
}

.progress-pct {
  font-size: 13px;
  font-weight: 600;
  color: #2563eb;
}

@media (max-width: 768px) {
  .polish-container { max-width: 100%; }
  .content-row { flex-direction: column; }
  .cat-summary-grid { grid-template-columns: 1fr; }
  .content-left,
  .content-right,
  .content-left .panel,
  .content-right .panel,
  .content-right .result-panel {
    min-height: 0;
  }
  .content-left .panel :deep(.el-textarea__inner),
  .col-content-compact {
    min-height: 0;
  }
  .term-row {
    flex-direction: column;
    align-items: stretch;
  }
  .feedback-rating-inline {
    align-items: flex-start;
    gap: 8px 12px;
  }
  .feedback-rating-group {
    flex: 0 0 auto;
  }
  .feedback-rating-text {
    flex: 1 1 100%;
  }
}
</style>
