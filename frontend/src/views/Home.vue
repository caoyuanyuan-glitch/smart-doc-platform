<template>
  <div class="home-container">
    <div class="welcome-banner">
      <div class="banner-content">
        <h1 class="welcome-title">欢迎使用智能技术文档平台</h1>
        <p class="welcome-subtitle">AI 驱动的文档审核、润色、问答、生成、对比与格式转换一站式解决方案</p>
      </div>
    </div>

    <h2 class="section-title">应用功能</h2>
    <div class="features-grid">
      <div class="feature-card card-polish" @click="$router.push('/polish')">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 19l7-7 3 3-7 7-3 3z"></path>
            <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"></path>
            <path d="M2 2l7.586 7.586"></path>
            <circle cx="11" cy="11" r="2"></circle>
          </svg>
        </div>
        <h3 class="feature-title">智能润色</h3>
        <p class="feature-desc">优化文档表达和句式，并排对比原文与润色结果，提升专业性</p>
        <div class="feature-enter">进入 <el-icon><ArrowRight /></el-icon></div>
      </div>

      <div class="feature-card card-generate" @click="$router.push('/generate')">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="12" y1="18" x2="12" y2="12"></line>
            <line x1="9" y1="15" x2="15" y2="15"></line>
          </svg>
        </div>
        <h3 class="feature-title">内容生成</h3>
        <p class="feature-desc">基于参数和模板生成标准化文档，支持中英文内容生成</p>
        <div class="feature-enter">进入 <el-icon><ArrowRight /></el-icon></div>
      </div>

      <div class="feature-card card-compare" @click="$router.push('/compare')">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10"></line>
            <line x1="12" y1="20" x2="12" y2="4"></line>
            <line x1="6" y1="20" x2="6" y2="14"></line>
            <line x1="3" y1="4" x2="21" y2="4"></line>
          </svg>
        </div>
        <h3 class="feature-title">文档对比</h3>
        <p class="feature-desc">智能对比两个版本文档的差异，生成详细对比报告</p>
        <div class="feature-enter">进入 <el-icon><ArrowRight /></el-icon></div>
      </div>

      <div class="feature-card card-convert" @click="$router.push('/convert')">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="17 1 21 5 17 9"></polyline>
          <path d="M3 11V9a4 4 0 0 1 4-4h14"></path>
          <polyline points="7 23 3 19 7 15"></polyline>
          <path d="M21 13v2a4 4 0 0 1-4 4H3"></path>
          </svg>
        </div>
        <h3 class="feature-title">格式转换</h3>
        <p class="feature-desc">Word/Markdown 转 DITA 结构化文档，保持格式和内容完整性</p>
        <div class="feature-enter">进入 <el-icon><ArrowRight /></el-icon></div>
      </div>

      <div class="feature-card card-review" @click="$router.push('/review')">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <path d="M9 15l2 2 4-4"></path>
          </svg>
        </div>
        <h3 class="feature-title">文档审核</h3>
        <p class="feature-desc">智能识别文档问题，规则+AI双重审核，支持问题跟踪和报告导出</p>
        <div class="feature-enter">进入 <el-icon><ArrowRight /></el-icon></div>
      </div>

      <div class="feature-card card-qa" @click="$router.push('/qa')">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
        </div>
        <h3 class="feature-title">智能问答</h3>
        <p class="feature-desc">基于知识库的对话式问答，支持多轮对话，快速定位关键信息</p>
        <div class="feature-enter">进入 <el-icon><ArrowRight /></el-icon></div>
      </div>

      <div class="feature-card card-knowledge" @click="$router.push('/knowledge')">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
            <path d="M12 8l-4 4 4 4"></path>
            <path d="M16 12l-4 4 4 4"></path>
          </svg>
        </div>
        <h3 class="feature-title">知识库管理</h3>
        <p class="feature-desc">上传、下载、删除文档文件，支持多模块调用，管理员权限控制</p>
        <div class="feature-enter">进入 <el-icon><ArrowRight /></el-icon></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'
</script>

<style>
.home-container {
  padding: 0;
  max-width: 1400px;
  margin: 0 auto;
}

.welcome-banner {
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 50%, #93c5fd 100%);
  border-radius: 16px;
  padding: 48px 40px;
  margin-bottom: 32px;
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.12);
}

.banner-content {
  max-width: 800px;
  margin: 0 auto;
  text-align: center;
}

.welcome-title {
  font-size: 32px;
  font-weight: 700;
  color: #1e40af;
  margin-bottom: 12px;
  letter-spacing: 0.5px;
}

.welcome-subtitle {
  font-size: 16px;
  color: #1e3a8a;
  line-height: 1.6;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 20px;
  padding-left: 12px;
  border-left: 4px solid #3b82f6;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin: 0 auto 24px;
}

.feature-card {
  background: #fff;
  border-radius: 14px;
  padding: 28px 24px;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  border: 1px solid #e5edf7;
  position: relative;
  overflow: hidden;
}

.feature-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 12px 32px rgba(59, 130, 246, 0.15);
  border-color: #bfdbfe;
}

.feature-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  border-radius: 14px 14px 0 0;
  opacity: 0;
  transition: opacity 0.3s;
}

.feature-card:hover::before {
  opacity: 1;
}

.feature-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #1e40af;
  margin-bottom: 18px;
}

.card-review .feature-icon, .card-review::before { background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); }
.card-polish .feature-icon, .card-polish::before { background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); }
.card-qa .feature-icon, .card-qa::before { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); }
.card-generate .feature-icon, .card-generate::before { background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%); }
.card-compare .feature-icon, .card-compare::before { background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%); }
.card-convert .feature-icon, .card-convert::before { background: linear-gradient(135deg, #cffafe 0%, #a5f3fc 100%); }
.card-knowledge .feature-icon, .card-knowledge::before { background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%); }

.feature-title {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 10px;
}

.feature-desc {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.7;
  margin-bottom: 18px;
  min-height: 68px;
}

.feature-enter {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #3b82f6;
  font-weight: 500;
}

.card-review .feature-enter { color: #2563eb; }
.card-polish .feature-enter { color: #059669; }
.card-qa .feature-enter { color: #d97706; }
.card-generate .feature-enter { color: #dc2626; }
.card-compare .feature-enter { color: #7c3aed; }
.card-convert .feature-enter { color: #0891b2; }
.card-knowledge .feature-enter { color: #6366f1; }

@media (max-width: 1024px) {
  .features-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .features-grid {
    grid-template-columns: 1fr;
  }

  .welcome-banner {
    padding: 28px 24px;
  }

  .welcome-title {
    font-size: 24px;
  }
}
</style>
