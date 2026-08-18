import { createRouter, createWebHistory } from 'vue-router'

const Login = () => import('@/views/Login.vue')
const Home = () => import('@/views/Home.vue')
const Review = () => import('@/views/Review.vue')
const ReviewDashboard = () => import('@/views/ReviewDashboard.vue')
const Polish = () => import('@/views/Polish.vue')
const PolishHistory = () => import('@/views/PolishHistory.vue')
const QA = () => import('@/views/QA.vue')
const QAManual = () => import('@/views/QADoc.vue')
const QADashboard = () => import('@/views/QADashboard.vue')
const QAHistory = () => import('@/views/QAHistory.vue')
const Generate = () => import('@/views/Generate.vue')
const DocGenerator = () => import('@/views/DocGenerator.vue')
const Compare = () => import('@/views/Compare.vue')
const CompareParams = () => import('@/views/CompareParams.vue')
const Competitor = () => import('@/views/Competitor.vue')
const Convert = () => import('@/views/Convert.vue')
const Terms = () => import('@/views/Terms.vue')
const Users = () => import('@/views/Users.vue')
const Translate = () => import('@/views/Translate.vue')
const TranslateDoc = () => import('@/views/TranslateDoc.vue')
const TranslateStats = () => import('@/views/TranslateStats.vue')
const Knowledge = () => import('@/views/Knowledge.vue')
const PolishPreview = () => import('@/views/PolishPreview.vue')
const RulesManage = () => import('@/views/RulesManage.vue')
const SpellCheck = () => import('@/views/SpellCheck.vue')
const SpellCheckHistory = () => import('@/views/SpellCheckHistory.vue')
const WhiteList = () => import('@/views/WhiteList.vue')
const Feedback = () => import('@/views/Feedback.vue')

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { public: true }
  },
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/review/dashboard',
    name: 'ReviewDashboard',
    component: ReviewDashboard
  },
  {
    path: '/review',
    name: 'Review',
    component: Review
  },
  {
    path: '/review/tasks',
    name: 'ReviewTasks',
    component: Review
  },
  {
    path: '/review/rules',
    name: 'ReviewRules',
    component: Review
  },
  {
    path: '/review/basis',
    redirect: '/review'
  },
  {
    path: '/review/spell-check',
    name: 'SpellCheck',
    component: SpellCheck
  },
  {
    path: '/review/spell-check/history',
    name: 'SpellCheckHistory',
    component: SpellCheckHistory
  },
  {
    path: '/review/spell-check/whitelist',
    name: 'WhiteList',
    component: WhiteList
  },
  {
    path: '/polish',
    name: 'Polish',
    component: Polish
  },
  {
    path: '/polish/document',
    name: 'PolishDocument',
    component: Polish
  },
  {
    path: '/polish/history',
    name: 'PolishHistory',
    component: PolishHistory
  },
  {
    path: '/polish/preview/:id',
    name: 'PolishPreview',
    component: PolishPreview
  },
  {
    path: '/tools/doc-polish',
    redirect: '/polish/document'
  },
  {
    path: '/tools/doc-generator',
    name: 'DocGenerator',
    component: DocGenerator
  },
  {
    path: '/tools/polish-rules',
    name: 'RulesManage',
    component: RulesManage
  },
  {
    path: '/qa',
    name: 'QA',
    component: QA
  },
  {
    path: '/qa/manual',
    name: 'QAManual',
    component: QAManual
  },
  {
    path: '/qa/docs',
    redirect: '/qa/manual'
  },
  {
    path: '/qa/dashboard',
    name: 'QADashboard',
    component: QADashboard
  },
  {
    path: '/qa/history',
    redirect: '/qa/history/general'
  },
  {
    path: '/qa/history/general',
    name: 'QAHistoryGeneral',
    component: QAHistory
  },
  {
    path: '/qa/history/doc',
    name: 'QAHistoryDoc',
    component: QAHistory
  },
  {
    path: '/generate',
    name: 'Generate',
    redirect: '/generate/image-descriptions'
  },
  {
    path: '/generate/image-descriptions',
    name: 'GenerateImageDescriptions',
    component: Generate
  },
  {
    path: '/generate/manual-draft',
    name: 'GenerateManualDraft',
    component: Generate
  },
  {
    path: '/generate/paragraph',
    name: 'GenerateParagraph',
    component: Generate
  },
  {
    path: '/generate/templates',
    name: 'GenerateTemplates',
    component: Generate
  },
  {
    path: '/compare',
    name: 'Compare',
    component: Compare
  },
  {
    path: '/compare/tasks',
    name: 'CompareTasks',
    component: Compare
  },
  {
    path: '/compare/params',
    name: 'CompareParams',
    component: CompareParams
  },
  {
    path: '/competitor',
    name: 'Competitor',
    component: Competitor
  },
  {
    path: '/competitor/tasks',
    name: 'CompetitorTasks',
    component: Competitor
  },
  {
    path: '/convert',
    name: 'Convert',
    component: Convert
  },
  {
    path: '/convert/history',
    name: 'ConvertHistory',
    component: Convert
  },
  {
    path: '/terms',
    name: 'Terms',
    component: Terms
  },
  {
    path: '/users',
    name: 'Users',
    component: Users
  },
  {
    path: '/translate',
    name: 'Translate',
    component: Translate
  },
  {
    path: '/translate/docs',
    name: 'TranslateDocs',
    component: TranslateDoc
  },
  {
    path: '/translate/stats',
    name: 'TranslateStats',
    component: TranslateStats
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: Knowledge
  },
  {
    path: '/knowledge/:id',
    name: 'KnowledgeFolder',
    component: Knowledge
  },
  {
    path: '/feedback',
    name: 'Feedback',
    component: Feedback
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.public) {
    next()
    return
  }
  if (!token) {
    next('/login')
    return
  }
  next()
})

export default router
