import { createRouter, createWebHistory } from 'vue-router'
import Login from '@/views/Login.vue'
import Home from '@/views/Home.vue'
import Review from '@/views/Review.vue'
import Polish from '@/views/Polish.vue'
import PolishHistory from '@/views/PolishHistory.vue'
import QA from '@/views/QA.vue'
import Generate from '@/views/Generate.vue'
import Compare from '@/views/Compare.vue'
import Convert from '@/views/Convert.vue'
import ConvertRules from '@/views/ConvertRules.vue'
import Terms from '@/views/Terms.vue'
import Users from '@/views/Users.vue'
import Translate from '@/views/Translate.vue'
import TranslateDoc from '@/views/TranslateDoc.vue'
import Knowledge from '@/views/Knowledge.vue'
import PolishPreview from '@/views/PolishPreview.vue'
import SpellCheck from '@/views/SpellCheck.vue'
import SpellCheckHistory from '@/views/SpellCheckHistory.vue'
import WhiteList from '@/views/WhiteList.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login
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
    name: 'ReviewBasis',
    component: Review
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
    path: '/qa/library',
    name: 'QALibrary',
    component: QA
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
    path: '/compare/config',
    name: 'CompareConfig',
    component: Compare
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
    path: '/convert/rules',
    name: 'ConvertRules',
    component: ConvertRules
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
    path: '/knowledge',
    name: 'Knowledge',
    component: Knowledge
  },
  {
    path: '/knowledge/:id',
    name: 'KnowledgeFolder',
    component: Knowledge
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
