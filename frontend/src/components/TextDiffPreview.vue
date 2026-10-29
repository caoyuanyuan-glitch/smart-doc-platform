<template>
  <div class="bc-root">
    <div class="bc-toolbar">
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button label="all">全部</el-radio-button>
        <el-radio-button label="diff">差别</el-radio-button>
      </el-radio-group>
      <el-button size="small" :disabled="!diffCount" @click="goPrev">上一段</el-button>
      <el-button size="small" :disabled="!diffCount" @click="goNext">下一段</el-button>
      <span class="bc-toolbar-info">{{ toolbarText }}</span>
    </div>
    <div class="bc-headers">
      <div class="bc-ov-pad" />
      <div class="bc-h">{{ fileAName }}</div>
      <div class="bc-split-h" />
      <div class="bc-h">{{ fileBName }}</div>
    </div>
    <div class="bc-main">
      <div class="bc-overview" @click="onOverviewClick">
        <div
          v-for="(sec, idx) in diffSections"
          :key="'ov-' + sec.start"
          class="bc-ov-mark"
          :class="{ current: idx === currentSection }"
          :style="overviewStyle(sec)"
        />
      </div>
      <div ref="paneARef" class="bc-pane" @scroll="onScrollA">
        <template v-for="item in visibleItems" :key="'a-' + item.key">
          <div v-if="item.type === 'skip'" class="bc-skip" @click="expandAll(item.rowIndex)">{{ item.count }} 行相同</div>
          <div
            v-else
            class="bc-line"
            :class="lineClass(item, 'a')"
            :data-row="item.rowIndex"
          >
            <div class="bc-mark" :class="markClass(item.rowIndex)">
              <span v-if="isSectionStart(item.rowIndex)" class="bc-arrow" />
            </div>
            <div class="bc-no">{{ item.row.a_no || '' }}</div>
            <div class="bc-txt">
              <span
                v-for="(sp, si) in (item.row.a_spans || [])"
                :key="'as' + si"
                :class="'sp-' + sp.k"
              >{{ sp.t }}</span>
            </div>
          </div>
        </template>
      </div>
      <div class="bc-split" />
      <div ref="paneBRef" class="bc-pane" @scroll="onScrollB">
        <template v-for="item in visibleItems" :key="'b-' + item.key">
          <div v-if="item.type === 'skip'" class="bc-skip" @click="expandAll(item.rowIndex)">{{ item.count }} 行相同</div>
          <div
            v-else
            class="bc-line"
            :class="lineClass(item, 'b')"
            :data-row="item.rowIndex"
          >
            <div class="bc-mark" :class="markClass(item.rowIndex)">
              <span v-if="isSectionStart(item.rowIndex)" class="bc-arrow" />
            </div>
            <div class="bc-no">{{ item.row.b_no || '' }}</div>
            <div class="bc-txt">
              <span
                v-for="(sp, si) in (item.row.b_spans || [])"
                :key="'bs' + si"
                :class="'sp-' + sp.k"
              >{{ sp.t }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>
    <div class="bc-status">{{ statusText }}</div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  fileAName: { type: String, default: '' },
  fileBName: { type: String, default: '' },
  rows: { type: Array, default: () => [] },
  diffSections: { type: Array, default: () => [] },
  diffCount: { type: Number, default: 0 },
})

const viewMode = ref('all')
const currentSection = ref(0)
const paneARef = ref(null)
const paneBRef = ref(null)
let syncing = false

const toolbarText = computed(() => {
  if (!props.diffCount) return '文件相同'
  const n = currentSection.value + 1
  return `${props.diffCount} 个差异部分    第 ${n} 个`
})

const statusText = computed(() => {
  if (!props.diffCount) return '文件相同'
  return `${props.diffCount} 个差异部分`
})

const visibleItems = computed(() => {
  const rows = props.rows || []
  if (viewMode.value === 'all') {
    return rows.map((row, i) => ({ type: 'row', row, rowIndex: i, key: 'r' + i }))
  }
  const items = []
  let i = 0
  while (i < rows.length) {
    if (rows[i].op === 'equal') {
      let j = i
      while (j < rows.length && rows[j].op === 'equal') j += 1
      items.push({ type: 'skip', count: j - i, rowIndex: i, key: 's' + i })
      i = j
      continue
    }
    items.push({ type: 'row', row: rows[i], rowIndex: i, key: 'r' + i })
    i += 1
  }
  return items
})

function isCurrent(rowIndex) {
  const sec = props.diffSections[currentSection.value]
  if (!sec) return false
  return rowIndex >= sec.start && rowIndex <= sec.end
}

function isSectionStart(rowIndex) {
  return (props.diffSections || []).some((sec) => sec.start === rowIndex)
}

function markClass(rowIndex) {
  const sec = (props.diffSections || []).find((s) => rowIndex >= s.start && rowIndex <= s.end)
  if (!sec) return {}
  return {
    hunk: true,
    start: sec.start === rowIndex,
    current: isCurrent(rowIndex),
  }
}

function lineClass(item, side) {
  const op = item.row.op || 'equal'
  const gap = side === 'a' ? !item.row.a_no : !item.row.b_no
  return {
    ['op-' + op]: true,
    gap,
    current: isCurrent(item.rowIndex),
  }
}

function overviewStyle(sec) {
  const total = Math.max(props.rows.length, 1)
  const top = (sec.start / total) * 100
  const height = Math.max(((sec.end - sec.start + 1) / total) * 100, 0.8)
  return { top: top + '%', height: height + '%' }
}

function scrollToRow(rowIndex) {
  nextTick(() => {
    const el = paneARef.value?.querySelector(`[data-row="${rowIndex}"]`)
    if (!el || !paneARef.value) return
    const top = el.offsetTop - paneARef.value.clientHeight / 3
    syncing = true
    paneARef.value.scrollTop = top
    if (paneBRef.value) paneBRef.value.scrollTop = top
    syncing = false
  })
}

function scrollToCurrent() {
  const sec = props.diffSections[currentSection.value]
  if (sec) scrollToRow(sec.start)
}

function goNext() {
  if (!props.diffSections.length) return
  currentSection.value = (currentSection.value + 1) % props.diffSections.length
  scrollToCurrent()
}

function goPrev() {
  if (!props.diffSections.length) return
  currentSection.value = (currentSection.value - 1 + props.diffSections.length) % props.diffSections.length
  scrollToCurrent()
}

function expandAll(rowIndex) {
  viewMode.value = 'all'
  scrollToRow(rowIndex)
}

function onScrollA(e) {
  if (syncing) return
  syncing = true
  if (paneBRef.value) paneBRef.value.scrollTop = e.target.scrollTop
  syncing = false
}

function onScrollB(e) {
  if (syncing) return
  syncing = true
  if (paneARef.value) paneARef.value.scrollTop = e.target.scrollTop
  syncing = false
}

function onOverviewClick(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const y = (e.clientY - rect.top) / Math.max(rect.height, 1)
  const idx = Math.min(props.rows.length - 1, Math.max(0, Math.floor(y * props.rows.length)))
  let best = 0
  let bestDist = Infinity
  props.diffSections.forEach((sec, i) => {
    const mid = (sec.start + sec.end) / 2
    const dist = Math.abs(mid - idx)
    if (dist < bestDist) {
      bestDist = dist
      best = i
    }
  })
  if (props.diffSections.length) currentSection.value = best
  scrollToRow(idx)
}

watch(
  () => props.rows,
  () => {
    currentSection.value = props.diffSections.length ? 0 : 0
    viewMode.value = 'all'
    scrollToCurrent()
  },
)
</script>

<style scoped>
.bc-root {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  color: #111;
  font-family: Consolas, "Courier New", ui-monospace, monospace;
}
.bc-toolbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #f3f4f6;
  border-bottom: 1px solid #d1d5db;
}
.bc-toolbar-info {
  margin-left: auto;
  font-size: 12px;
  color: #374151;
  font-family: system-ui, sans-serif;
}
.bc-headers {
  flex: 0 0 auto;
  display: flex;
  border-bottom: 1px solid #c0c0c0;
  font-family: system-ui, sans-serif;
}
.bc-ov-pad {
  width: 16px;
  flex-shrink: 0;
  background: #ececec;
  border-right: 1px solid #c0c0c0;
}
.bc-h {
  flex: 1;
  min-width: 0;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 500;
  color: #222;
  background: #f3f3f3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bc-split-h {
  width: 6px;
  flex-shrink: 0;
  background: #d9d9d9;
  border-left: 1px solid #c0c0c0;
  border-right: 1px solid #c0c0c0;
}
.bc-main {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}
.bc-overview {
  width: 16px;
  flex-shrink: 0;
  position: relative;
  background: #f0f0f0;
  border-right: 1px solid #c0c0c0;
  cursor: pointer;
}
.bc-ov-mark {
  position: absolute;
  left: 2px;
  right: 2px;
  background: #f5b0b0;
  border-radius: 1px;
}
.bc-ov-mark.current {
  background: #cc4444;
}
.bc-pane {
  flex: 1 1 auto;
  min-width: 0;
  overflow: auto;
  background: #fff;
}
.bc-split {
  width: 6px;
  flex-shrink: 0;
  background: #d9d9d9;
  border-left: 1px solid #c0c0c0;
  border-right: 1px solid #c0c0c0;
}
.bc-line {
  display: flex;
  height: 18px;
  flex-shrink: 0;
  line-height: 18px;
  font-size: 12px;
  width: max-content;
  min-width: 100%;
}
.bc-mark {
  width: 16px;
  flex-shrink: 0;
  position: relative;
  background: #f7f7f7;
  border-right: 1px solid #e5e7eb;
}
.bc-mark.hunk::before {
  content: "";
  position: absolute;
  left: 7px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #c8c8c8;
}
.bc-mark.start.hunk::before {
  top: 10px;
}
.bc-mark.current.hunk::before {
  background: #e6b800;
}
.bc-arrow {
  position: absolute;
  left: 4px;
  top: 4px;
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 8px solid #e6b800;
}
.bc-mark.current .bc-arrow {
  border-left-color: #c99200;
}
.bc-no {
  width: 40px;
  flex-shrink: 0;
  padding: 0 6px;
  text-align: right;
  color: #6b7280;
  background: #fafafa;
  border-right: 1px solid #ececec;
  user-select: none;
}
.bc-txt {
  padding: 0 8px;
  white-space: pre;
  flex: 1;
}
.bc-line.gap .bc-txt {
  background-image: repeating-linear-gradient(
    -45deg,
    #ffffff,
    #ffffff 4px,
    #d4d4d4 4px,
    #d4d4d4 5px
  );
}
.bc-line.op-replace:not(.gap) .bc-txt,
.bc-line.op-delete:not(.gap) .bc-txt,
.bc-line.op-insert:not(.gap) .bc-txt {
  background: #ffd6d6;
}
.bc-line.current:not(.gap) .bc-txt {
  background: #ffc9c9;
}
.sp-del,
.sp-ins,
.sp-chg {
  color: #9f1239;
  font-weight: 700;
}
.bc-skip {
  height: 22px;
  line-height: 22px;
  flex-shrink: 0;
  text-align: center;
  font-size: 11px;
  color: #6b7280;
  background: #ececec;
  cursor: pointer;
  font-family: system-ui, sans-serif;
  border-bottom: 1px solid #d4d4d4;
}
.bc-status {
  flex: 0 0 auto;
  padding: 4px 10px;
  font-size: 12px;
  color: #4b5563;
  background: #f3f4f6;
  border-top: 1px solid #d1d5db;
  font-family: system-ui, sans-serif;
}
</style>
