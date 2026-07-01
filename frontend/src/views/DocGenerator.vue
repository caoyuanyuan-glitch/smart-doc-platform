<template>
  <div class="doc-generator-page">
    <div class="page-head">
      <div>
        <h2>说明书初稿</h2>
        <p>基于产品资料和模板生成说明书初稿，当前使用 Mock 数据完成完整交互流程。</p>
      </div>
      <el-tag type="info">自动保存：{{ lastSavedText }}</el-tag>
    </div>

    <div class="stepper-card">
      <div class="custom-steps">
        <div v-for="(step, index) in steps" :key="step" class="custom-step" :class="stepClass(index)">
          <span class="step-index">{{ index < currentStep ? '✓' : index + 1 }}</span>
          <span>{{ step }}</span>
        </div>
      </div>
    </div>

    <section v-if="currentStep === 0" class="step-layout">
      <div class="panel form-panel">
        <div class="panel-title with-actions">
          <span>{{ activeTemplate ? '模板章节表单' : '产品资料表单' }}</span>
          <div v-if="activeTemplate" class="active-template-actions">
            <el-tag type="success">当前模板：{{ activeTemplate.name }}</el-tag>
            <el-button size="small" @click="changeTemplate">更换模板</el-button>
          </div>
        </div>
        <el-form v-if="activeTemplate" label-position="top" class="generator-form dynamic-form">
          <div class="form-grid meta-grid">
            <el-form-item :class="dynamicErrorClass('metaProductName')"><template #label><span class="required-label">产品名称</span></template><el-input v-model="templateForm.meta.productName" placeholder="请输入产品名称" /></el-form-item>
            <el-form-item :class="dynamicErrorClass('metaProductModel')"><template #label><span class="required-label">产品型号</span></template><el-input v-model="templateForm.meta.productModel" placeholder="请输入产品型号" /></el-form-item>
            <el-form-item :class="dynamicErrorClass('metaVersion')"><template #label><span class="required-label">说明书版本</span></template><el-input v-model="templateForm.meta.version" placeholder="例如：V1.0" /></el-form-item>
            <el-form-item :class="dynamicErrorClass('metaManufacturer')"><template #label><span class="required-label">制造商</span></template><el-input v-model="templateForm.meta.manufacturer" placeholder="请输入制造商" /></el-form-item>
          </div>
          <el-collapse v-model="dynamicOpenPanels" class="chapter-collapse">
            <el-collapse-item v-for="chapter in activeTemplate.sections" :key="chapter.id" :name="chapter.id">
              <template #title><span class="collapse-title">{{ chapter.title }}</span></template>
              <div v-if="chapter.children?.length" class="chapter-fields">
                <div v-for="field in chapter.children" :key="field.id" class="dynamic-field">
                  <component :is="'div'">
                    <el-form-item v-if="fieldComponent(field) === 'textarea'" :class="dynamicErrorClass(field.id)">
                      <template #label><span class="required-label">{{ field.cleaned_title }}</span></template>
                      <el-input v-model="templateForm.fields[field.id]" type="textarea" :rows="4" :placeholder="`请填写${field.cleaned_title}...`" />
                      <div v-if="dynamicErrors[field.id]" class="error-text">{{ dynamicErrors[field.id] }}</div>
                    </el-form-item>
                    <div v-else-if="fieldComponent(field) === 'warning_list'" class="entry-card">
                      <div class="entry-head"><strong>{{ field.title }}</strong><el-button size="small" @click="addDynamicWarning(field.id)">添加警告</el-button></div>
                      <div v-for="(item, index) in templateForm.fields[field.id]" :key="`${field.id}-${index}`" class="form-grid compact">
                        <el-form-item label="级别"><el-select v-model="item.level" class="full-width"><el-option label="危险" value="危险" /><el-option label="警告" value="警告" /><el-option label="注意" value="注意" /></el-select></el-form-item>
                        <el-form-item><template #label><span class="required-label">内容</span></template><el-input v-model="item.content" type="textarea" :rows="2" placeholder="请填写警告内容" /></el-form-item>
                      </div>
                    </div>
                    <div v-else-if="fieldComponent(field) === 'power_specs'" class="entry-card">
                      <div class="entry-head"><strong>{{ field.title }}</strong></div>
                      <div class="form-grid compact">
                        <el-form-item label="电源电压"><el-select v-model="templateForm.fields[field.id].voltage" class="full-width"><el-option label="AC 110V" value="AC 110V" /><el-option label="AC 220V" value="AC 220V" /><el-option label="DC 24V" value="DC 24V" /></el-select></el-form-item>
                        <el-form-item label="频率"><el-select v-model="templateForm.fields[field.id].frequency" class="full-width"><el-option label="50 Hz" value="50 Hz" /><el-option label="60 Hz" value="60 Hz" /></el-select></el-form-item>
                        <el-form-item><template #label><span class="required-label">功率</span></template><el-input v-model="templateForm.fields[field.id].power" placeholder="≤ 500"><template #append>W</template></el-input></el-form-item>
                      </div>
                    </div>
                    <div v-else-if="fieldComponent(field) === 'env_specs'" class="entry-card">
                      <div class="entry-head"><strong>{{ field.title }}</strong></div>
                      <div class="form-grid compact">
                        <el-form-item label="温度范围"><div class="range-row"><el-input v-model="templateForm.fields[field.id].tempMin" placeholder="15" /><span>~</span><el-input v-model="templateForm.fields[field.id].tempMax" placeholder="30 ℃" /></div></el-form-item>
                        <el-form-item label="湿度范围"><div class="range-row"><el-input v-model="templateForm.fields[field.id].humidityMin" placeholder="20" /><span>~</span><el-input v-model="templateForm.fields[field.id].humidityMax" placeholder="80% RH" /></div></el-form-item>
                      </div>
                    </div>
                    <div v-else-if="fieldComponent(field) === 'dynamic_steps'" class="entry-card">
                      <div class="entry-head"><strong>{{ field.title }}</strong><el-button size="small" @click="addDynamicStep(field.id)">添加步骤</el-button></div>
                      <div v-for="(item, index) in templateForm.fields[field.id]" :key="`${field.id}-${index}`" class="entry-card inner-card">
                        <el-form-item><template #label><span class="required-label">操作内容 #{{ index + 1 }}</span></template><el-input v-model="item.action" type="textarea" :rows="2" placeholder="请填写操作步骤" /></el-form-item>
                        <el-form-item label="注意事项"><el-input v-model="item.caution" placeholder="可选" /></el-form-item>
                      </div>
                    </div>
                    <el-form-item v-else :class="dynamicErrorClass(field.id)">
                      <template #label><span class="required-label">{{ field.cleaned_title }}</span></template>
                      <el-input v-model="templateForm.fields[field.id]" :placeholder="dynamicPlaceholder(field)" />
                      <div v-if="dynamicErrors[field.id]" class="error-text">{{ dynamicErrors[field.id] }}</div>
                    </el-form-item>
                  </component>
                </div>
              </div>
              <el-empty v-else description="该章节暂无二级字段，可在后续生成预览中补充" />
            </el-collapse-item>
          </el-collapse>
          <div class="required-tip">* 为必填项</div>
        </el-form>
        <el-form v-else label-position="top" class="generator-form">
          <div class="form-grid">
            <el-form-item :class="errorClass('productName')">
              <template #label><span class="required-label">产品名称</span></template>
              <el-input v-model="productForm.productName" placeholder="例如：全自动核酸提取仪" />
              <div v-if="errors.productName" class="error-text">{{ errors.productName }}</div>
            </el-form-item>
            <el-form-item :class="errorClass('model')">
              <template #label><span class="required-label">产品型号</span></template>
              <el-input v-model="productForm.model" placeholder="例如：NEX-9600" />
              <div v-if="errors.model" class="error-text">{{ errors.model }}</div>
            </el-form-item>
            <el-form-item :class="errorClass('manufacturer')">
              <template #label><span class="required-label">制造商</span></template>
              <el-input v-model="productForm.manufacturer" placeholder="例如：某某医疗科技有限公司" />
              <div v-if="errors.manufacturer" class="error-text">{{ errors.manufacturer }}</div>
            </el-form-item>
            <el-form-item :class="errorClass('version')">
              <template #label><span class="required-label">版本</span></template>
              <el-input v-model="productForm.version" placeholder="例如：V1.0" />
              <div v-if="errors.version" class="error-text">{{ errors.version }}</div>
            </el-form-item>
            <el-form-item :class="errorClass('audience')">
              <template #label><span class="required-label">目标用户</span></template>
              <el-input v-model="productForm.audience" placeholder="例如：实验室操作人员" />
              <div v-if="errors.audience" class="error-text">{{ errors.audience }}</div>
            </el-form-item>
            <el-form-item label="使用场景">
              <el-select v-model="productForm.scene" class="full-width">
                <el-option label="临床检验" value="临床检验" />
                <el-option label="科研实验" value="科研实验" />
                <el-option label="现场检测" value="现场检测" />
              </el-select>
            </el-form-item>
          </div>

          <el-form-item label="功能模块（勾选则在说明书中生成对应章节）">
            <el-checkbox-group v-model="productForm.modules" class="module-grid">
              <el-checkbox label="uv">紫外模块</el-checkbox>
              <el-checkbox label="heating">加热模块</el-checkbox>
              <el-checkbox label="cooling">制冷模块</el-checkbox>
              <el-checkbox label="magnetic">磁珠模块</el-checkbox>
              <el-checkbox label="pipetting">移液模块</el-checkbox>
            </el-checkbox-group>
          </el-form-item>

          <el-form-item label="产品概述">
            <el-input v-model="productForm.description" type="textarea" :rows="3" placeholder="说明产品用途、核心能力和主要使用边界" />
          </el-form-item>

          <el-collapse v-model="openPanels" class="spec-collapse">
            <el-collapse-item name="specs">
              <template #title><span class="collapse-title">技术规格</span></template>
              <div class="spec-grid">
                <el-form-item :class="errorClass('powerVoltage')">
                  <template #label><span class="required-label">电源电压</span></template>
                  <el-select v-model="productForm.specs.powerVoltage" class="full-width">
                    <el-option label="AC 110 V" value="AC 110 V" />
                    <el-option label="AC 220 V" value="AC 220 V" />
                    <el-option label="DC 24 V" value="DC 24 V" />
                  </el-select>
                  <div v-if="errors.powerVoltage" class="error-text">{{ errors.powerVoltage }}</div>
                </el-form-item>
                <el-form-item label="频率">
                  <el-select v-model="productForm.specs.frequency" class="full-width">
                    <el-option label="50 Hz" value="50 Hz" />
                    <el-option label="60 Hz" value="60 Hz" />
                  </el-select>
                </el-form-item>
                <el-form-item :class="errorClass('power')">
                  <template #label><span class="required-label">功率</span></template>
                  <el-input v-model="productForm.specs.power" placeholder="≤ 500"><template #append>W</template></el-input>
                  <div v-if="errors.power" class="error-text">{{ errors.power }}</div>
                </el-form-item>
                <el-form-item :class="errorClass('dimensions')">
                  <template #label><span class="required-label">尺寸</span></template>
                  <div class="dimension-row">
                    <el-input v-model="productForm.specs.width" placeholder="600" />
                    <span>×</span>
                    <el-input v-model="productForm.specs.depth" placeholder="450" />
                    <span>×</span>
                    <el-input v-model="productForm.specs.height" placeholder="520" />
                    <span>mm</span>
                  </div>
                  <div v-if="errors.dimensions" class="error-text">{{ errors.dimensions }}</div>
                </el-form-item>
                <el-form-item label="重量">
                  <el-input v-model="productForm.specs.weight" placeholder="约 45"><template #append>kg</template></el-input>
                </el-form-item>
                <el-form-item label="温度范围">
                  <div class="range-row"><el-input v-model="productForm.specs.tempMin" placeholder="15 ℃" /><span>~</span><el-input v-model="productForm.specs.tempMax" placeholder="30 ℃" /></div>
                </el-form-item>
                <el-form-item label="湿度范围">
                  <div class="range-row"><el-input v-model="productForm.specs.humidityMin" placeholder="20%" /><span>~</span><el-input v-model="productForm.specs.humidityMax" placeholder="80% RH" /></div>
                </el-form-item>
              </div>
            </el-collapse-item>
          </el-collapse>

          <div class="card-list-section">
            <div class="section-title">操作步骤</div>
            <div v-for="(item, index) in productForm.operation_steps" :key="`step-${index}`" class="entry-card">
              <div class="entry-head"><strong>操作步骤 #{{ index + 1 }}</strong><el-button text type="danger" :disabled="productForm.operation_steps.length <= 1" @click="removeItem('operation_steps', index)">删除</el-button></div>
              <el-form-item><template #label><span class="required-label">操作内容</span></template><el-input v-model="item.action" placeholder="例如：连接电源并打开主机开关" /></el-form-item>
              <el-form-item label="注意事项"><el-input v-model="item.caution" placeholder="例如：确认电源接地可靠" /></el-form-item>
            </div>
            <el-button @click="addOperationStep">添加步骤</el-button>
          </div>

          <div class="card-list-section">
            <div class="section-title">安全警告</div>
            <div v-for="(item, index) in productForm.safety_warnings" :key="`warning-${index}`" class="entry-card">
              <div class="entry-head"><strong>安全警告 #{{ index + 1 }}</strong><el-button text type="danger" :disabled="productForm.safety_warnings.length <= 1" @click="removeItem('safety_warnings', index)">删除</el-button></div>
              <div class="form-grid compact">
                <el-form-item><template #label><span class="required-label">级别</span></template><el-select v-model="item.level" class="full-width"><el-option label="危险" value="危险" /><el-option label="警告" value="警告" /><el-option label="注意" value="注意" /></el-select></el-form-item>
                <el-form-item><template #label><span class="required-label">内容</span></template><el-input v-model="item.content" placeholder="例如：设备运行过程中请勿打开防护盖" /></el-form-item>
              </div>
            </div>
            <el-button @click="addSafetyWarning">添加警告</el-button>
          </div>

          <div class="card-list-section">
            <div class="section-title">维护项</div>
            <div v-for="(item, index) in productForm.maintenance_items" :key="`maintenance-${index}`" class="entry-card">
              <div class="entry-head"><strong>维护项 #{{ index + 1 }}</strong><el-button text type="danger" :disabled="productForm.maintenance_items.length <= 1" @click="removeItem('maintenance_items', index)">删除</el-button></div>
              <div class="form-grid compact">
                <el-form-item><template #label><span class="required-label">项目名称</span></template><el-input v-model="item.name" placeholder="例如：样本槽清洁" /></el-form-item>
                <el-form-item><template #label><span class="required-label">维护周期</span></template><el-input v-model="item.period" placeholder="例如：每次实验后" /></el-form-item>
              </div>
              <el-form-item><template #label><span class="required-label">操作内容</span></template><el-input v-model="item.action" placeholder="例如：使用无尘布擦拭样本槽" /></el-form-item>
            </div>
            <el-button @click="addMaintenanceItem">添加维护项</el-button>
          </div>

          <div class="required-tip">* 为必填项</div>
        </el-form>
      </div>
      <aside class="panel hint-panel">
        <div class="panel-title">填写提示</div>
        <p>请填写左侧产品信息，完成后点击下一步。</p>
        <p>技术规格、操作步骤、安全警告和维护项会用于后续模板替换与初稿生成。</p>
      </aside>
      <div class="step-actions"><el-button type="primary" @click="goTemplateStep">{{ activeTemplate ? '下一步：生成预览' : '下一步：选择模板' }}</el-button></div>
    </section>

    <section v-if="currentStep === 1" class="panel">
      <div class="panel-title">模板选择</div>
      <div class="extract-card">
        <div>
          <h3>上传现有说明书提取框架</h3>
          <p>支持 .docx / .pdf，上传后 Mock 分析章节层级、通用框架映射和缺失共性章节。</p>
        </div>
        <el-upload drag action="#" accept=".docx,.pdf" :auto-upload="false" :show-file-list="false" :on-change="handleFrameworkUpload">
          <div class="upload-title">点击上传或拖拽文件</div>
          <div class="upload-tip">上传后自动生成章节树，并可保存到我的模板</div>
        </el-upload>
      </div>

      <div class="sub-panel-title">官方模板</div>
      <div class="template-grid">
        <label v-for="tpl in templates" :key="tpl.id" class="template-card" :class="{ active: selectedTemplateId === tpl.id }">
          <el-radio v-model="selectedTemplateId" :label="tpl.id" :value="tpl.id">
            <strong>{{ tpl.name }}</strong>
          </el-radio>
          <p>{{ tpl.desc }}</p>
          <el-button size="small" type="primary" plain @click.stop="openTemplatePreview(tpl)">预览</el-button>
        </label>
      </div>

      <div class="sub-panel-title with-actions"><span>我的模板</span><el-tag type="info">{{ myTemplates.length }} 个</el-tag></div>
      <el-empty v-if="!myTemplates.length" description="上传说明书并保存后，会出现在这里" />
      <div v-else class="template-grid my-template-grid">
        <label v-for="tpl in myTemplates" :key="tpl.id" class="template-card" :class="{ active: selectedTemplateId === tpl.id }">
          <el-radio v-model="selectedTemplateId" :label="tpl.id" :value="tpl.id">
            <strong>{{ tpl.name }}</strong>
          </el-radio>
          <p>来源：{{ tpl.source }}</p>
          <p>章节：一级 {{ tpl.sectionCount.level1 }}，二级 {{ tpl.sectionCount.level2 }}，三级 {{ tpl.sectionCount.level3 }}</p>
          <div class="template-actions">
            <el-button size="small" type="primary" plain @click.stop="openTemplatePreview(tpl)">预览</el-button>
            <el-button size="small" type="danger" plain @click.stop="deleteMyTemplate(tpl.id)">删除</el-button>
          </div>
        </label>
      </div>

      <div class="template-inline-preview">
        <h3>{{ activeTemplateName }}预览</h3>
        <el-alert v-if="activeFrameworkTree.length" title="已应用上传说明书的章节结构，生成预览会按下方章节树输出。" type="success" :closable="false" show-icon class="applied-alert" />
        <el-tree v-if="activeFrameworkTree.length" :data="activeFrameworkTree" node-key="id" default-expand-all />
        <el-timeline v-else>
          <el-timeline-item v-for="section in renderedTemplateSections" :key="section" :timestamp="section" />
        </el-timeline>
      </div>
      <div class="step-actions"><el-button @click="currentStep = 0">返回</el-button><el-button type="primary" @click="generateDraft">下一步：生成预览</el-button></div>
    </section>

    <section v-if="currentStep === 2" class="panel">
      <div class="panel-title with-actions"><span>生成预览</span><el-tag :type="unresolvedPlaceholders.length ? 'warning' : 'success'">{{ unresolvedPlaceholders.length ? `${unresolvedPlaceholders.length} 个占位符待补充` : '占位符已完成替换' }}</el-tag></div>
      <el-table :data="placeholderRows" border class="placeholder-table">
        <el-table-column prop="label" label="占位符" width="180" />
        <el-table-column prop="value" label="替换内容" min-width="220"><template #default="scope"><span :class="{ muted: !scope.row.value }">{{ scope.row.value || '待补充' }}</span></template></el-table-column>
        <el-table-column label="状态" width="120"><template #default="scope"><el-tag :type="scope.row.value ? 'success' : 'warning'" size="small">{{ scope.row.value ? '已替换' : '缺失' }}</el-tag></template></el-table-column>
      </el-table>
      <div class="preview-box"><h3>{{ previewTitle }}</h3><pre>{{ previewContent }}</pre></div>
      <div class="step-actions"><el-button @click="currentStep = 1">返回</el-button><el-button type="primary" @click="currentStep = 3">下一步：确认导出</el-button></div>
    </section>

    <section v-if="currentStep === 3" class="panel">
      <div class="panel-title with-actions"><span>确认导出</span><div class="confirm-stats"><el-tag type="success">已接受 {{ acceptedBlocks.length }}</el-tag><el-tag type="danger">已拒绝 {{ rejectedBlocks.length }}</el-tag><el-tag type="info">待确认 {{ pendingBlocks.length }}</el-tag></div></div>
      <div class="ai-block-list">
        <article v-for="block in aiBlocks" :key="block.id" class="ai-block" :class="`status-${block.status}`">
          <div class="ai-block-head"><div><span class="block-type">{{ block.section }}</span><strong>{{ block.title }}</strong></div><el-tag :type="blockStatusType(block.status)" size="small">{{ blockStatusText(block.status) }}</el-tag></div>
          <p>{{ block.content }}</p>
          <div class="block-actions"><el-button size="small" type="success" :disabled="block.status === 'accepted'" @click="setBlockStatus(block.id, 'accepted')">接受</el-button><el-button size="small" type="danger" :disabled="block.status === 'rejected'" @click="setBlockStatus(block.id, 'rejected')">拒绝</el-button><el-button size="small" @click="regenerateBlock(block.id)">重新生成</el-button></div>
        </article>
      </div>
      <div class="step-actions bottom-actions"><el-button @click="currentStep = 2">返回</el-button><el-button type="primary" :disabled="!draftReady" @click="exportDocx">导出 docx</el-button><el-button type="success" :disabled="!draftReady" @click="goToPolish">去润色</el-button></div>
    </section>

    <el-dialog v-model="templatePreviewVisible" title="模板预览" width="720px">
      <div v-if="previewTemplate" class="template-preview">
        <h3>{{ previewTemplate.name }}</h3>
        <p>{{ previewTemplate.desc }}</p>
        <el-timeline><el-timeline-item v-for="section in previewTemplate.sections" :key="section" :timestamp="section" /></el-timeline>
        <pre>{{ previewTemplate.sample }}</pre>
      </div>
    </el-dialog>

    <el-dialog v-model="frameworkDialogVisible" title="提取的说明书框架" width="860px">
      <div v-if="extractedFramework" class="framework-preview">
        <div class="framework-summary">
          <el-tag type="success">{{ extractedFramework.source.name }}</el-tag>
          <el-tag type="info">{{ extractedFramework.source.pages }} 页</el-tag>
          <el-tag v-for="type in extractedFramework.types" :key="type" type="warning">{{ type }}</el-tag>
        </div>
        <div class="framework-columns">
          <div>
            <h3>章节树</h3>
            <el-tree :data="extractedFramework.tree" node-key="id" default-expand-all />
          </div>
          <div>
            <h3>映射到通用框架</h3>
            <el-table :data="extractedFramework.mapped" border size="small">
              <el-table-column prop="extracted" label="提取章节" />
              <el-table-column prop="generic" label="通用章节" />
              <el-table-column label="置信度" width="100"><template #default="scope">{{ Math.round(scope.row.confidence * 100) }}%</template></el-table-column>
            </el-table>
            <div class="missing-box">
              <strong>建议补充章节：</strong>
              <el-tag v-for="section in extractedFramework.missing" :key="section" type="danger" effect="plain">{{ section }}</el-tag>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-input v-model="frameworkTemplateName" placeholder="模板名称" class="framework-name-input" />
        <el-button @click="frameworkDialogVisible = false">取消</el-button>
        <el-button @click="saveExtractedFramework">保存到我的模板</el-button>
        <el-button type="primary" @click="applyExtractedTemplate">应用此模板</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const STORAGE_KEY = 'doc_generator_draft_v2'

const steps = ['产品资料', '模板选择', '生成预览', '确认导出']
const currentStep = ref(0)
const openPanels = ref(['specs'])
const selectedTemplateId = ref('instrument')
const draftReady = ref(false)
const templatePreviewVisible = ref(false)
const frameworkDialogVisible = ref(false)
const previewTemplate = ref(null)
const extractedFramework = ref(null)
const appliedFramework = ref(null)
const activeTemplate = ref(null)
const frameworkTemplateName = ref('')
const myTemplates = ref([])
const aiBlocks = ref([])
const errors = reactive({})
const dynamicErrors = reactive({})
const lastSavedText = ref('尚未保存')
const dynamicOpenPanels = ref([])
let saveTimer = null

const templates = [
  { id: 'instrument', name: '通用仪器', desc: '适合设备类产品，包含产品概述、技术规格、安全信息、操作步骤、维护保养和技术支持。', sections: ['封面信息', '安全警告', '产品概述', '技术规格', '安装准备', '操作步骤', '维护保养', '技术支持'], sample: '产品名称：{{product_name}}\n产品型号：{{product_model}}\n技术规格：{{specs.power_voltage}} / {{specs.power_frequency}}\n操作步骤：{{operation_steps}}\n维护保养：{{maintenance_items}}' },
  { id: 'kit', name: '试剂盒', desc: '适合试剂盒说明书，强调产品组成、储存运输、实验步骤和注意事项。', sections: ['封面信息', '安全警告', '产品概述', '适用范围', '产品组成', '储存运输', '操作步骤', '技术支持'], sample: '产品用途：{{product_description}}\n适用范围：{{applicable_scope}}\n组成清单：{{components}}\n安全警告：{{safety_warnings}}' },
  { id: 'software', name: '软件系统', desc: '适合平台和软件产品，包含运行环境、功能入口、操作说明和技术支持。', sections: ['封面信息', '产品概述', '适用范围', '运行环境', '操作步骤', '故障处理', '技术支持'], sample: '系统简介：{{product_name}} 面向 {{target_user}}。\n功能说明：{{operation_steps}}\n技术支持：{{support_phone}}' }
]

const defaultForm = () => ({
  productName: '全自动核酸提取仪', model: 'NEX-9600', manufacturer: '某某医疗科技有限公司', version: 'V1.0', audience: '实验室操作人员', scene: '临床检验', description: '用于样本核酸自动化提取，支持批量样本处理和流程状态提示。', modules: ['uv', 'heating', 'magnetic'],
  specs: { powerVoltage: 'AC 220 V', frequency: '50 Hz', power: '≤ 500', width: '600', depth: '450', height: '520', weight: '约 45', tempMin: '15 ℃', tempMax: '30 ℃', humidityMin: '20%', humidityMax: '80% RH' },
  operation_steps: [{ action: '连接电源并打开主机开关', caution: '确认电源接地可靠' }, { action: '将样本放入样本槽中，关闭槽盖', caution: '确认样本管已固定' }, { action: '在控制软件中选择实验流程并启动运行', caution: '' }],
  safety_warnings: [{ level: '警告', content: '设备运行过程中请勿打开防护盖' }, { level: '注意', content: '样本管未固定时请勿启动流程' }],
  maintenance_items: [{ name: '样本槽清洁', period: '每次实验后', action: '使用无尘布擦拭样本槽' }, { name: '运动部件检查', period: '每月', action: '检查导轨和传动结构是否异常' }]
})

const productForm = reactive(defaultForm())
const templateForm = reactive({
  meta: { productName: '全自动核酸提取仪', productModel: 'NEX-9600', version: 'V1.0', manufacturer: '某某医疗科技有限公司' },
  fields: {}
})
const allTemplates = computed(() => [...templates, ...myTemplates.value])
const selectedTemplate = computed(() => allTemplates.value.find((item) => item.id === selectedTemplateId.value) || templates[0])
const activeFrameworkTree = computed(() => activeTemplate.value?.sections || appliedFramework.value?.tree || (selectedTemplate.value.isCustom ? selectedTemplate.value.tree || [] : []))
const activeTemplateName = computed(() => activeTemplate.value?.name || appliedFramework.value?.name || selectedTemplate.value.name)
const previewTitle = computed(() => `${productForm.productName || '未命名产品'} ${selectedTemplate.value.name}说明书初稿`)
const acceptedBlocks = computed(() => aiBlocks.value.filter((item) => item.status === 'accepted'))
const rejectedBlocks = computed(() => aiBlocks.value.filter((item) => item.status === 'rejected'))
const pendingBlocks = computed(() => aiBlocks.value.filter((item) => item.status === 'pending'))
const renderedTemplateSections = computed(() => [...selectedTemplate.value.sections, ...moduleSections.value])
const moduleSections = computed(() => {
  const map = { uv: '紫外安全', heating: '高温警告', cooling: '低温注意事项', magnetic: '磁珠使用', pipetting: '移液操作' }
  return productForm.modules.map((key) => map[key]).filter(Boolean)
})
const placeholderRows = computed(() => [
  { label: '{{product_name}}', value: productForm.productName }, { label: '{{product_model}}', value: productForm.model }, { label: '{{manufacturer}}', value: productForm.manufacturer }, { label: '{{version}}', value: productForm.version }, { label: '{{release_date}}', value: releaseDate.value }, { label: '{{product_description}}', value: productForm.description }, { label: '{{applicable_scope}}', value: `${productForm.scene}，目标用户为${productForm.audience}` }, { label: '{{specs.power_voltage}}', value: productForm.specs.powerVoltage }, { label: '{{specs.power_frequency}}', value: productForm.specs.frequency }, { label: '{{specs.power_consumption}}', value: productForm.specs.power }, { label: '{{operation_steps}}', value: operationTexts.value.join('；') }, { label: '{{safety_warnings}}', value: warningTexts.value.join('；') }, { label: '{{maintenance_items}}', value: maintenanceTexts.value.join('；') }
])
const unresolvedPlaceholders = computed(() => placeholderRows.value.filter((item) => !item.value))
const operationTexts = computed(() => productForm.operation_steps.map((item) => item.action).filter(Boolean))
const warningTexts = computed(() => productForm.safety_warnings.map((item) => item.content).filter(Boolean))
const maintenanceTexts = computed(() => productForm.maintenance_items.map((item) => [item.name, item.period, item.action].filter(Boolean).join('：')).filter(Boolean))
const specsText = computed(() => `${productForm.specs.powerVoltage}，${productForm.specs.frequency}，功率 ${productForm.specs.power} W，尺寸 ${productForm.specs.width} × ${productForm.specs.depth} × ${productForm.specs.height} mm`)
const releaseDate = computed(() => new Date().toISOString().slice(0, 10))
const previewContent = computed(() => activeTemplate.value ? buildDynamicTemplatePreview() : (activeFrameworkTree.value.length ? buildCustomTemplatePreview() : buildGenericTemplatePreview()))

function stepClass(index) { return { active: index === currentStep.value, done: index < currentStep.value, disabled: index > currentStep.value } }
function errorClass(key) { return errors[key] ? 'is-error' : '' }
function clearErrors() { Object.keys(errors).forEach((key) => delete errors[key]) }
function validateStep1() {
  clearErrors()
  if (!productForm.productName.trim()) errors.productName = '请填写产品名称'
  if (!productForm.model.trim()) errors.model = '请填写产品型号'
  if (!productForm.manufacturer.trim()) errors.manufacturer = '请填写制造商'
  if (!productForm.version.trim()) errors.version = '请填写版本'
  if (!productForm.audience.trim()) errors.audience = '请填写目标用户'
  if (!productForm.specs.powerVoltage) errors.powerVoltage = '请选择电源电压'
  if (!productForm.specs.power.trim()) errors.power = '请填写功率'
  if (!productForm.specs.width.trim() || !productForm.specs.depth.trim() || !productForm.specs.height.trim()) errors.dimensions = '请填写完整尺寸'
  const firstError = Object.keys(errors)[0]
  if (firstError) {
    window.setTimeout(() => document.querySelector('.is-error')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0)
    ElMessage.warning(errors[firstError])
    return false
  }
  return true
}
function goTemplateStep() {
  if (activeTemplate.value) {
    if (validateDynamicForm()) generateDraft()
    return
  }
  if (validateStep1()) currentStep.value = 1
}
function changeTemplate() {
  activeTemplate.value = null
  appliedFramework.value = null
  currentStep.value = 1
}
function addOperationStep() { productForm.operation_steps.push({ action: '', caution: '' }) }
function addSafetyWarning() { productForm.safety_warnings.push({ level: '注意', content: '' }) }
function addMaintenanceItem() { productForm.maintenance_items.push({ name: '', period: '', action: '' }) }
function removeItem(field, index) { if (productForm[field].length > 1) productForm[field].splice(index, 1) }
function openTemplatePreview(template) { previewTemplate.value = template; templatePreviewVisible.value = true }
function handleFrameworkUpload(uploadFile) {
  const fileName = uploadFile?.name || uploadFile?.raw?.name || ''
  const isSupported = /\.(docx|pdf)$/i.test(fileName)
  if (!isSupported) {
    ElMessage.warning('请上传 .docx 或 .pdf 文件')
    return false
  }
  const baseName = fileName.replace(/\.(docx|pdf)$/i, '')
  extractedFramework.value = buildMockFramework(baseName)
  frameworkTemplateName.value = `${baseName}框架`
  frameworkDialogVisible.value = true
  ElMessage.success('章节框架已提取')
  return false
}
function buildMockFramework(sourceName) {
  return {
    source: { name: sourceName, pages: 32 },
    types: ['安全警告', '产品概述', '操作步骤', '技术规格'],
    tree: [
      { id: 'ch1', label: '一、产品描述', children: [{ id: 'ch1-1', label: '1.1 产品用途' }, { id: 'ch1-2', label: '1.2 适用范围' }] },
      { id: 'ch2', label: '二、安全信息', children: [{ id: 'ch2-1', label: '2.1 生物安全' }, { id: 'ch2-2', label: '2.2 电气安全' }] },
      { id: 'ch3', label: '三、技术规格', children: [{ id: 'ch3-1', label: '3.1 电源参数' }, { id: 'ch3-2', label: '3.2 环境要求' }] },
      { id: 'ch4', label: '四、操作步骤', children: [{ id: 'ch4-1', label: '4.1 实验准备' }, { id: 'ch4-2', label: '4.2 运行流程' }] },
      { id: 'ch5', label: '五、技术支持' }
    ],
    mapped: [
      { extracted: '产品描述', generic: '第2章-产品概述', confidence: 0.95 },
      { extracted: '安全信息', generic: '第1章-安全警告', confidence: 0.92 },
      { extracted: '技术规格', generic: '第3章-技术规格', confidence: 0.97 },
      { extracted: '操作步骤', generic: '第4章-操作步骤', confidence: 0.98 },
      { extracted: '技术支持', generic: '第7章-技术支持', confidence: 0.9 }
    ],
    missing: ['维护保养', '故障处理'],
    sections: ['产品描述', '安全信息', '技术规格', '操作步骤', '技术支持', '维护保养']
  }
}
function saveExtractedFramework() {
  if (!extractedFramework.value) return
  const templateName = frameworkTemplateName.value.trim()
  if (!templateName) {
    ElMessage.warning('请填写模板名称')
    return
  }
  const template = createCustomTemplate(templateName, extractedFramework.value)
  myTemplates.value.unshift(template)
  selectedTemplateId.value = template.id
  frameworkDialogVisible.value = false
  saveDraft()
  ElMessage.success('已保存到我的模板')
}
function applyExtractedTemplate() {
  if (!extractedFramework.value) return
  const templateName = frameworkTemplateName.value.trim()
  if (!templateName) {
    ElMessage.warning('请填写模板名称')
    return
  }
  const template = applyExtractedFramework(templateName)
  frameworkDialogVisible.value = false
  currentStep.value = 0
  saveDraft()
  ElMessage.success('已应用模板，Step 1 已按章节结构渲染')
}
function applyExtractedFramework(templateName) {
  const template = createCustomTemplate(templateName, extractedFramework.value)
  appliedFramework.value = template
  activeTemplate.value = { id: template.id, name: template.name, source: 'upload', sections: normalizeSectionNodes(template.tree) }
  initializeTemplateForm(activeTemplate.value)
  selectedTemplateId.value = template.id
  return template
}
function createCustomTemplate(templateName, framework) {
  const flattenedSections = flattenFrameworkTree(framework.tree)
  return {
    id: `custom-${Date.now()}`,
    name: templateName,
    desc: '从用户上传说明书提取的自定义框架，生成时直接沿用原始章节结构。',
    source: framework.source.name,
    sectionCount: countFrameworkLevels(framework.tree),
    isCustom: true,
    tree: framework.tree,
    sections: flattenedSections.map((item) => item.label),
    sample: flattenedSections.map((section) => `${'  '.repeat(section.level - 1)}${section.label}：{{${normalizeSectionKey(section.label)}}}`).join('\n')
  }
}
async function deleteMyTemplate(id) {
  try {
    await ElMessageBox.confirm('确认删除该自定义模板？', '删除模板', { type: 'warning' })
    const index = myTemplates.value.findIndex((item) => item.id === id)
    if (index >= 0) myTemplates.value.splice(index, 1)
    if (selectedTemplateId.value === id) selectedTemplateId.value = 'instrument'
    ElMessage.success('模板已删除')
  } catch (e) {
    // User cancelled.
  }
}
function flattenFrameworkTree(nodes, level = 1) {
  return nodes.flatMap((node) => [{ label: node.label, level }, ...flattenFrameworkTree(node.children || [], level + 1)])
}
function countFrameworkLevels(nodes) {
  return flattenFrameworkTree(nodes).reduce((acc, item) => {
    if (item.level === 1) acc.level1 += 1
    if (item.level === 2) acc.level2 += 1
    if (item.level >= 3) acc.level3 += 1
    return acc
  }, { level1: 0, level2: 0, level3: 0 })
}
function normalizeSectionKey(label) {
  return label.replace(/^\s*[一二三四五六七八九十]+[、.．]\s*/, '').replace(/^\s*\d+(\.\d+)*\s*/, '').trim()
}
function normalizeSectionNodes(nodes = [], level = 1) {
  return nodes.map((node, index) => {
    const title = node.title || node.label || `章节 ${index + 1}`
    return {
      id: node.id || `sec-${level}-${index}`,
      level,
      title,
      label: title,
      cleaned_title: node.cleaned_title || normalizeSectionKey(title),
      children: normalizeSectionNodes(node.children || [], level + 1)
    }
  })
}
function initializeTemplateForm(template) {
  templateForm.meta.productName = productForm.productName
  templateForm.meta.productModel = productForm.model
  templateForm.meta.version = productForm.version
  templateForm.meta.manufacturer = productForm.manufacturer
  Object.keys(templateForm.fields).forEach((key) => delete templateForm.fields[key])
  dynamicOpenPanels.value = template.sections.map((chapter) => chapter.id)
  template.sections.forEach((chapter) => {
    chapter.children.forEach((field) => {
      templateForm.fields[field.id] = defaultFieldValue(field)
    })
  })
}
function fieldComponent(field) {
  const title = field.cleaned_title || ''
  if (['安全', '警告', '危险', '防护'].some((key) => title.includes(key))) return 'warning_list'
  if (['电源', '电压', '功率'].some((key) => title.includes(key))) return 'power_specs'
  if (['环境', '温度', '湿度'].some((key) => title.includes(key))) return 'env_specs'
  if (['步骤', '操作', '流程', '运行', '实验'].some((key) => title.includes(key))) return 'dynamic_steps'
  if (['用途', '描述', '介绍', '概述', '说明', '范围'].some((key) => title.includes(key))) return 'textarea'
  return 'input'
}
function defaultFieldValue(field) {
  const component = fieldComponent(field)
  if (component === 'warning_list') return [{ level: '警告', content: '' }]
  if (component === 'power_specs') return { voltage: 'AC 220V', frequency: '50 Hz', power: '' }
  if (component === 'env_specs') return { tempMin: '', tempMax: '', humidityMin: '', humidityMax: '' }
  if (component === 'dynamic_steps') return [{ action: '', caution: '' }]
  return ''
}
function dynamicPlaceholder(field) {
  const title = field.cleaned_title || '内容'
  if (title.includes('电话') || title.includes('热线') || title.includes('联系')) return '400-xxx-xxxx'
  if (title.includes('网站') || title.includes('网址') || title.includes('官网')) return 'www.xxx.com'
  if (title.includes('邮箱') || title.includes('Email') || title.includes('邮件')) return 'support@xxx.com'
  return `请填写${title}`
}
function dynamicErrorClass(fieldId) { return dynamicErrors[fieldId] ? 'is-error' : '' }
function addDynamicWarning(fieldId) { templateForm.fields[fieldId].push({ level: '警告', content: '' }) }
function addDynamicStep(fieldId) { templateForm.fields[fieldId].push({ action: '', caution: '' }) }
function validateDynamicForm() {
  Object.keys(dynamicErrors).forEach((key) => delete dynamicErrors[key])
  if (!templateForm.meta.productName.trim()) dynamicErrors.metaProductName = '请填写产品名称'
  if (!templateForm.meta.productModel.trim()) dynamicErrors.metaProductModel = '请填写产品型号'
  if (!templateForm.meta.version.trim()) dynamicErrors.metaVersion = '请填写说明书版本'
  if (!templateForm.meta.manufacturer.trim()) dynamicErrors.metaManufacturer = '请填写制造商'
  activeTemplate.value.sections.forEach((chapter) => {
    chapter.children.forEach((field) => {
      const value = templateForm.fields[field.id]
      const component = fieldComponent(field)
      if (component === 'warning_list' && !value.some((item) => item.content?.trim())) dynamicErrors[field.id] = `请填写${field.cleaned_title}`
      if (component === 'dynamic_steps' && !value.some((item) => item.action?.trim())) dynamicErrors[field.id] = `请填写${field.cleaned_title}`
      if (component === 'textarea' && !String(value || '').trim()) dynamicErrors[field.id] = `请填写${field.cleaned_title}`
      if (component === 'input' && !String(value || '').trim()) dynamicErrors[field.id] = `请填写${field.cleaned_title}`
    })
  })
  const firstError = Object.keys(dynamicErrors)[0]
  if (firstError) {
    window.setTimeout(() => document.querySelector('.is-error')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0)
    ElMessage.warning(dynamicErrors[firstError])
    return false
  }
  return true
}
function sectionsToTree(sections = []) {
  return sections.map((label, index) => ({ id: `legacy-${index}`, label }))
}
function buildGenericTemplatePreview() {
  return [
    `# ${productForm.productName} 使用说明书`, '', `说明书版本：${productForm.version}`, `发布日期：${releaseDate.value}`, `制造商：${productForm.manufacturer}`, '', '## 1. 安全警告', ...productForm.safety_warnings.filter((item) => item.content).map((item) => `- ${item.level}：${item.content}`), '', '## 2. 产品概述', `产品名称：${productForm.productName}`, `产品型号：${productForm.model}`, `产品描述：${productForm.description}`, `适用范围：${productForm.scene}，目标用户为${productForm.audience}`, '', '## 3. 技术规格', `电源电压：${productForm.specs.powerVoltage}`, `电源频率：${productForm.specs.frequency}`, `功率：${productForm.specs.power} W`, `尺寸：${productForm.specs.width} × ${productForm.specs.depth} × ${productForm.specs.height} mm`, `重量：${productForm.specs.weight} kg`, `温度范围：${productForm.specs.tempMin} ~ ${productForm.specs.tempMax}`, `湿度范围：${productForm.specs.humidityMin} ~ ${productForm.specs.humidityMax}`, '', '## 4. 操作步骤', ...productForm.operation_steps.filter((item) => item.action).map((item, index) => `${index + 1}. ${item.action}${item.caution ? `（注意：${item.caution}）` : ''}`), '', '## 5. 维护保养', ...productForm.maintenance_items.filter((item) => item.name || item.action).map((item) => `- ${item.name}：${item.period}，${item.action}`), '', '## 6. 模块说明', ...moduleSections.value.map((section) => `- ${section}：根据已勾选功能模块生成对应说明。`), '', '## 7. 技术支持', '技术支持热线：待补充', '官方网站：待补充', '', '## 8. AI 生成区块', ...(acceptedBlocks.value.length ? acceptedBlocks.value : pendingBlocks.value).map((block) => `${block.section}：${block.content}`)
  ].join('\n')
}
function buildCustomTemplatePreview() {
  const activeTemplate = appliedFramework.value || selectedTemplate.value
  const tree = activeFrameworkTree.value.length ? activeFrameworkTree.value : sectionsToTree(activeTemplate.sections)
  const lines = [`# ${productForm.productName} 使用说明书`, '', `模板来源：${activeTemplate.source}`, `说明书版本：${productForm.version}`, `发布日期：${releaseDate.value}`, '']
  appendCustomSections(lines, tree)
  lines.push('', '## AI 生成区块', ...(acceptedBlocks.value.length ? acceptedBlocks.value : pendingBlocks.value).map((block) => `${block.section}：${block.content}`))
  return lines.join('\n')
}
function buildDynamicTemplatePreview() {
  const submitData = buildTemplateSubmitData()
  const lines = [`# ${submitData.meta.productName} 产品说明书`, '', `产品型号：${submitData.meta.productModel}`, `说明书版本：${submitData.meta.version}`, `制造商：${submitData.meta.manufacturer}`, '']
  submitData.chapters.forEach((chapter) => {
    lines.push(`## ${chapter.chapterTitle}`, '')
    chapter.fields.forEach((field) => appendFieldMarkdown(lines, field))
    lines.push('')
  })
  lines.push('## AI 生成区块', ...(acceptedBlocks.value.length ? acceptedBlocks.value : pendingBlocks.value).map((block) => `${block.section}：${block.content}`))
  return lines.join('\n')
}
function buildTemplateSubmitData() {
  return {
    templateId: activeTemplate.value.id,
    templateName: activeTemplate.value.name,
    meta: { ...templateForm.meta },
    chapters: activeTemplate.value.sections.map((chapter) => ({
      chapterId: chapter.id,
      chapterTitle: chapter.title,
      fields: chapter.children.map((field) => ({ fieldId: field.id, label: field.cleaned_title, value: templateForm.fields[field.id] }))
    }))
  }
}
function appendFieldMarkdown(lines, field) {
  const value = field.value
  lines.push(`### ${field.label}`)
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      if ('content' in item) lines.push(`${index + 1}. ${item.level}：${item.content || '待补充'}`)
      if ('action' in item) {
        lines.push(`${index + 1}. ${item.action || '待补充'}`)
        if (item.caution) lines.push(`   注意：${item.caution}`)
      }
    })
  } else if (value && typeof value === 'object') {
    Object.entries(value).forEach(([key, itemValue]) => lines.push(`- ${fieldValueLabel(key)}：${itemValue || '待补充'}`))
  } else {
    lines.push(value || '待补充')
  }
  lines.push('')
}
function fieldValueLabel(key) {
  return { voltage: '电源电压', frequency: '频率', power: '功率', tempMin: '最低温度', tempMax: '最高温度', humidityMin: '最低湿度', humidityMax: '最高湿度' }[key] || key
}
function appendCustomSections(lines, nodes) {
  nodes.forEach((node) => {
    const title = node.label
    lines.push(`${'#'.repeat(Math.min((node.id.match(/-/g)?.length || 0) + 2, 4))} ${title}`)
    lines.push(...customSectionContent(title), '')
    appendCustomSections(lines, node.children || [])
  })
}
function customSectionContent(title) {
  const cleanedTitle = normalizeSectionKey(title)
  if (/产品|描述|概述|用途/.test(cleanedTitle)) return [`产品名称：${productForm.productName}`, `产品型号：${productForm.model}`, `产品描述：${productForm.description}`]
  if (/适用|范围/.test(cleanedTitle)) return [`适用范围：${productForm.scene}`, `目标用户：${productForm.audience}`]
  if (/安全|警告|危险|防护/.test(cleanedTitle)) return productForm.safety_warnings.filter((item) => item.content).map((item) => `- ${item.level}：${item.content}`)
  if (/规格|参数|技术|环境|电源/.test(cleanedTitle)) return [specsText.value, `重量：${productForm.specs.weight} kg`, `温度范围：${productForm.specs.tempMin} ~ ${productForm.specs.tempMax}`, `湿度范围：${productForm.specs.humidityMin} ~ ${productForm.specs.humidityMax}`]
  if (/操作|步骤|流程|运行|实验/.test(cleanedTitle)) return productForm.operation_steps.filter((item) => item.action).map((item, index) => `${index + 1}. ${item.action}${item.caution ? `（注意：${item.caution}）` : ''}`)
  if (/维护|保养|清洁|校准/.test(cleanedTitle)) return productForm.maintenance_items.filter((item) => item.name || item.action).map((item) => `- ${item.name}：${item.period}，${item.action}`)
  if (/支持|服务|联系|售后/.test(cleanedTitle)) return ['技术支持热线：待补充', '官方网站：待补充']
  return ['待根据产品资料生成。']
}
function generateDraft() { if (!activeTemplate.value && selectedTemplate.value.isCustom) appliedFramework.value = selectedTemplate.value; aiBlocks.value = buildMockBlocks(); draftReady.value = true; currentStep.value = 2; ElMessage.success(activeTemplate.value ? '已按动态章节表单生成预览' : (activeFrameworkTree.value.length ? '已按上传章节结构生成预览' : '说明书初稿预览已生成')) }
function buildMockBlocks() { return [{ id: 'overview-ai', section: '产品概述', title: '应用边界补充', content: `${productForm.productName}适用于${productForm.scene}场景，可辅助${productForm.audience}完成标准化样本处理。`, status: 'pending' }, { id: 'safety-ai', section: '安全信息', title: '风险提示补充', content: '启动流程前应确认样本管已固定，防护盖处于闭合状态，并确保设备周围无遮挡物。', status: 'pending' }, { id: 'maintenance-ai', section: '维护保养', title: '维护周期建议', content: '建议建立维护记录表，记录清洁时间、检查项目和异常处理结果，便于后续追溯。', status: 'pending' }] }
function setBlockStatus(id, status) { const block = aiBlocks.value.find((item) => item.id === id); if (block) block.status = status }
function regenerateBlock(id) { const block = aiBlocks.value.find((item) => item.id === id); if (!block) return; const suffix = new Date().toLocaleTimeString('zh-CN', { hour12: false }); block.content = `${block.content.replace(/（Mock 重新生成.*）$/, '')}（Mock 重新生成 ${suffix}）`; block.status = 'pending'; ElMessage.success('区块已重新生成') }
function blockStatusText(status) { return { accepted: '已接受', rejected: '已拒绝', pending: '待确认' }[status] || '待确认' }
function blockStatusType(status) { return { accepted: 'success', rejected: 'danger', pending: 'info' }[status] || 'info' }
function exportDocx() { const html = `<html><head><meta charset="utf-8"></head><body><pre>${escapeHtml(previewContent.value)}</pre></body></html>`; const blob = new Blob([html], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document;charset=utf-8' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `${productForm.productName || '说明书初稿'}.docx`; link.click(); URL.revokeObjectURL(url); ElMessage.success('docx 导出已开始') }
function goToPolish() { sessionStorage.setItem('pendingPolishText', previewContent.value); router.push('/polish') }
function escapeHtml(value) { return String(value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
function saveDraft() { localStorage.setItem(STORAGE_KEY, JSON.stringify({ productForm, selectedTemplateId: selectedTemplateId.value, myTemplates: myTemplates.value, appliedFramework: appliedFramework.value, activeTemplate: activeTemplate.value, templateForm })); lastSavedText.value = new Date().toLocaleTimeString('zh-CN', { hour12: false }) }
function loadDraft() { const raw = localStorage.getItem(STORAGE_KEY); if (!raw) return; try { const saved = JSON.parse(raw); Object.assign(productForm, saved.productForm || {}); myTemplates.value = normalizeSavedTemplates(saved.myTemplates); selectedTemplateId.value = saved.selectedTemplateId || 'instrument'; appliedFramework.value = saved.appliedFramework?.tree?.length ? saved.appliedFramework : null; activeTemplate.value = saved.activeTemplate?.sections?.length ? saved.activeTemplate : null; Object.assign(templateForm.meta, saved.templateForm?.meta || {}); Object.assign(templateForm.fields, saved.templateForm?.fields || {}); if (activeTemplate.value) dynamicOpenPanels.value = activeTemplate.value.sections.map((chapter) => chapter.id); lastSavedText.value = '已恢复草稿' } catch (e) { localStorage.removeItem(STORAGE_KEY) } }
function normalizeSavedTemplates(templatesValue) {
  if (!Array.isArray(templatesValue)) return []
  return templatesValue.map((template) => {
    if (!template.source) return template
    const tree = template.tree?.length ? template.tree : sectionsToTree(template.sections)
    return {
      ...template,
      isCustom: true,
      tree,
      sections: flattenFrameworkTree(tree).map((item) => item.label),
      sectionCount: template.sectionCount || countFrameworkLevels(tree)
    }
  })
}

watch(productForm, () => { draftReady.value = false }, { deep: true })
watch(templateForm, () => { draftReady.value = false }, { deep: true })
onMounted(() => { loadDraft(); saveTimer = window.setInterval(saveDraft, 30000) })
onBeforeUnmount(() => { if (saveTimer) window.clearInterval(saveTimer); saveDraft() })
</script>

<style scoped>
.doc-generator-page { padding-bottom: 40px; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
.page-head h2 { margin: 0 0 6px; font-size: 24px; color: #111827; }
.page-head p, .hint-panel p, .template-card p { margin: 0; color: #64748b; line-height: 1.6; }
.stepper-card, .panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; margin-bottom: 18px; }
.custom-steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.custom-step { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 10px; border-radius: 999px; background: #f1f5f9; color: #64748b; font-weight: 700; }
.custom-step.active { background: #2563eb; color: #fff; }
.custom-step.done { background: #dcfce7; color: #15803d; }
.step-index { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 999px; background: rgba(255,255,255,.32); }
.step-layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 18px; }
.step-layout .step-actions { grid-column: 1 / -1; }
.panel-title { font-size: 16px; font-weight: 700; color: #111827; margin-bottom: 16px; }
.panel-title.with-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.active-template-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sub-panel-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 18px 0 10px; font-weight: 700; color: #111827; }
.form-grid, .spec-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.form-grid.compact { gap: 10px; }
.full-width { width: 100%; }
.required-label::before { content: '*'; color: #ef4444; margin-right: 4px; }
.required-tip, .error-text { color: #ef4444; font-size: 13px; margin-top: 6px; }
.is-error :deep(.el-input__wrapper), .is-error :deep(.el-select__wrapper) { box-shadow: 0 0 0 1px #ef4444 inset; }
.module-grid { display: grid; grid-template-columns: repeat(5, minmax(90px, 1fr)); gap: 8px; }
.spec-collapse { margin-bottom: 18px; }
.chapter-collapse { margin-top: 16px; }
.chapter-fields { display: grid; gap: 12px; }
.inner-card { background: #fff; }
.collapse-title, .section-title { font-weight: 700; color: #111827; }
.dimension-row, .range-row { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr auto; gap: 8px; align-items: center; width: 100%; }
.range-row { grid-template-columns: 1fr auto 1fr; }
.card-list-section { margin-top: 18px; }
.entry-card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; margin: 10px 0; background: #f8fafc; }
.entry-head, .step-actions, .confirm-stats, .block-actions, .ai-block-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.step-actions { justify-content: flex-end; margin-top: 18px; }
.extract-card { display: grid; grid-template-columns: minmax(240px, 360px) 1fr; gap: 16px; align-items: center; padding: 16px; border: 1px dashed #93c5fd; border-radius: 10px; background: #eff6ff; }
.extract-card h3 { margin: 0 0 8px; color: #111827; }
.extract-card p, .upload-tip { margin: 0; color: #64748b; line-height: 1.6; }
.upload-title { color: #2563eb; font-weight: 700; margin-bottom: 6px; }
.template-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.template-card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; cursor: pointer; display: grid; gap: 8px; }
.template-card.active { border-color: #2563eb; background: #eff6ff; }
.template-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.template-inline-preview, .preview-box, .template-preview pre { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; margin-top: 16px; }
.applied-alert { margin-bottom: 12px; }
.framework-summary, .missing-box { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; align-items: center; }
.framework-columns { display: grid; grid-template-columns: 280px 1fr; gap: 16px; }
.framework-columns h3 { margin: 0 0 10px; color: #111827; }
.framework-name-input { width: 260px; margin-right: auto; }
.placeholder-table { margin-bottom: 16px; }
.muted { color: #f59e0b; }
.preview-box pre, .template-preview pre { white-space: pre-wrap; word-break: break-word; margin: 0; line-height: 1.8; font-family: inherit; color: #374151; }
.ai-block-list { display: grid; gap: 12px; }
.ai-block { border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; }
.ai-block.status-accepted { border-color: #bbf7d0; background: #f0fdf4; }
.ai-block.status-rejected { border-color: #fecaca; background: #fef2f2; }
.block-type { color: #2563eb; margin-right: 8px; }
@media (max-width: 1100px) { .step-layout, .template-grid, .extract-card, .framework-columns { grid-template-columns: 1fr; } .module-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 720px) { .page-head, .panel-title.with-actions { flex-direction: column; } .custom-steps, .form-grid, .spec-grid, .dimension-row { grid-template-columns: 1fr; } }
</style>
