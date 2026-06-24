<template>
  <ul class="tree-list">
    <li v-for="node in nodes" :key="node.id" class="tree-node">
      <div
        class="tree-row"
        :class="{ active: currentFolderId === node.id }"
        @click="$emit('select', node)"
      >
        <span
          v-if="node.children && node.children.length > 0"
          class="expand-arrow"
          :class="{ expanded: expandedIds.has(node.id) }"
          @click.stop="$emit('toggle', node.id)"
        >▶</span>
        <span v-else class="expand-placeholder"></span>

        <span class="tree-icon">📁</span>
        <span class="tree-label">{{ node.name }}</span>

        <span class="tree-actions">
          <span class="tree-action" :class="{ active: isActionActive(node.id, 'create-sub') }" @click.stop="$emit('create-sub', node.id)" title="新建子文件夹">
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M8 3.25v9.5M3.25 8h9.5" />
            </svg>
          </span>
          <span class="tree-action" :class="{ active: isActionActive(node.id, 'move') }" @click.stop="$emit('move', node)" title="移动">
            <svg viewBox="0 0 1024 1024" aria-hidden="true">
              <path fill="currentColor" d="M896 301.653333L618.24 64a77.226667 77.226667 0 0 0-14.933333-11.52L597.333333 50.346667h-2.986666A72.533333 72.533333 0 0 0 567.466667 42.666667H178.773333A72.106667 72.106667 0 0 0 106.666667 114.773333v794.453334A72.106667 72.106667 0 0 0 178.773333 981.333333h298.666667a35.84 35.84 0 0 0 0-71.68h-298.666667V114.773333h354.56v197.12A72.106667 72.106667 0 0 0 605.44 384h240.213333v164.693333a35.84 35.84 0 0 0 71.68 0v-196.266666a72.106667 72.106667 0 0 0-21.333333-50.773334z m-290.986667 10.24V153.173333l199.68 158.72z" />
              <path fill="currentColor" d="M906.666667 760.32l-98.986667-98.986667a35.84 35.84 0 0 0-50.773333 50.773334l37.973333 37.973333h-384v-85.333333a35.84 35.84 0 0 0-71.68 0v122.026666a35.84 35.84 0 0 0 35.84 35.84h420.266667l-37.973334 37.973334a35.84 35.84 0 0 0 50.773334 50.773333L906.666667 810.666667a35.84 35.84 0 0 0 0-50.346667z" />
            </svg>
          </span>
          <span class="tree-action" :class="{ active: isActionActive(node.id, 'rename') }" @click.stop="$emit('rename', node)" title="重命名">
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="m11.8 2.7 1.5 1.5M4 12l2.2-.4 6.3-6.3a1.1 1.1 0 0 0 0-1.6l-.3-.3a1.1 1.1 0 0 0-1.6 0L4.3 9.7 4 12Z" />
            </svg>
          </span>
          <span class="tree-action delete" :class="{ active: isActionActive(node.id, 'delete') }" @click.stop="$emit('delete', node)" title="删除">
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.75 4.5h8.5M6.25 2.75h3.5M5.25 4.5v7.25m5.5-7.25v7.25M4.75 4.5l.4 8c.03.5.44.9.94.9h3.82c.5 0 .91-.4.94-.9l.4-8" />
            </svg>
          </span>
        </span>
      </div>

      <ul v-if="node.children && node.children.length > 0 && expandedIds.has(node.id)" class="tree-children">
        <recursive-tree
          :nodes="node.children"
          :current-folder-id="currentFolderId"
          :expanded-ids="expandedIds"
          :active-action="activeAction"
          @toggle="$emit('toggle', $event)"
          @select="$emit('select', $event)"
          @create-sub="$emit('create-sub', $event)"
          @move="$emit('move', $event)"
          @rename="$emit('rename', $event)"
          @delete="$emit('delete', $event)"
        />
      </ul>
    </li>
  </ul>
</template>

<script setup>
const props = defineProps({
  nodes: { type: Array, required: true },
  currentFolderId: { type: Number, default: null },
  expandedIds: { type: Set, required: true },
  activeAction: {
    type: Object,
    default: () => ({ folderId: null, type: '' })
  }
})

function isActionActive(folderId, type) {
  return props.activeAction?.folderId === folderId && props.activeAction?.type === type
}

defineEmits(['toggle', 'select', 'create-sub', 'move', 'rename', 'delete'])
</script>

<style scoped>
.tree-list {
  list-style: none;
  padding-left: 8px;
  margin: 0;
}

.tree-node {
  list-style: none;
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  margin: 1px 0;
  font-size: 15px;
  transition: background 0.15s;
}

.tree-row:hover {
  background: #dbeafe;
}

.tree-row.active {
  background: #4f8ff7;
  color: #fff;
}

.tree-row.active {
  background: #4f8ff7;
  color: #fff;
}

.tree-row.active .expand-arrow {
  color: #fff;
}

.tree-row.active .tree-icon {
  filter: brightness(0) invert(1);
}

.tree-row.active .tree-actions {
  display: flex;
  gap: 2px;
}

.tree-row.active .tree-action {
  color: rgba(255, 255, 255, 0.88);
  border-color: rgba(255, 255, 255, 0.18);
  background: transparent;
  opacity: 0.92;
}

.tree-row.active .tree-action:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.34);
}

.tree-row.active .tree-action.active {
  color: #2563eb;
  background: #fff;
  border-color: rgba(255, 255, 255, 1);
  border-width: 3px;
  width: 28px;
  height: 28px;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.72), 0 0 0 5px rgba(37, 99, 235, 0.28);
  opacity: 1;
}

.expand-arrow {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.2s;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.expand-placeholder {
  width: 18px;
  flex-shrink: 0;
}

.tree-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.tree-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-actions {
  display: none;
  gap: 2px;
  flex-shrink: 0;
}

.tree-row:hover .tree-actions {
  display: flex;
}

.tree-action {
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.15s, background 0.15s, border-color 0.15s, color 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: 1px solid transparent;
  box-sizing: border-box;
  color: #64748b;
}

.tree-action:hover {
  opacity: 1;
  background: rgba(37, 99, 235, 0.1);
  color: #2563eb;
}

.tree-action svg {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  stroke-width: 1.5;
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}


.tree-children {
  list-style: none;
  padding-left: 12px;
  margin: 0;
}
</style>
