import { createRouter, createWebHistory } from 'vue-router'
import Login from '@/views/Login.vue'
import Home from '@/views/Home.vue'
import Review from '@/views/Review.vue'
import Polish from '@/views/Polish.vue'
import PolishHistory from '@/views/PolishHistory.vue'
import QA from '@/views/QA.vue'
import QAManual from '@/views/QADoc.vue'
import QADashboard from '@/views/QADashboard.vue'
import QAHistory from '@/views/QAHistory.vue'
import Generate from '@/views/Generate.vue'
import Compare from '@/views/Compare.vue'
import CompareParams from '@/views/CompareParams.vue'
import Convert from '@/views/Convert.vue'
import Terms from '@/views/Terms.vue'
import Users from '@/views/Users.vue'
import Translate from '@/views/Translate.vue'
import TranslateDoc from '@/views/TranslateDoc.vue'
import TranslateStats from '@/views/TranslateStats.vue'
import Knowledge from '@/views/Knowledge.vue'
import PolishPreview from '@/views/PolishPreview.vue'
import SpellCheck from '@/views/SpellCheck.vue'
import SpellCheckHistory from '@/views/SpellCheckHistory.vue'
import WhiteList from '@/views/WhiteList.vue'
import Feedback from '@/views/Feedback.vue'

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
