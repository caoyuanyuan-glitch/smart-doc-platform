<template>
  <div class="redirect-panel">正在打开文档润色...</div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

onMounted(() => {
  router.replace('/polish/document')
})
</script>

<style scoped>
.redirect-panel {
  padding: 24px;
  color: #606266;
}
</style>
