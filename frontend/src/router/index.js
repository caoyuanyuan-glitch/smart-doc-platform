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
import Terms from '@/views/Terms.vue'
import Users from '@/views/Users.vue'
import Knowledge from '@/views/Knowledge.vue'

import PolishPreview from '@/views/PolishPreview.vue'

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
    path: '/review/reports',
    name: 'ReviewReports',
    component: Review
  },
  {
    path: '/review/basis',
    name: 'ReviewBasis',
    component: Review
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