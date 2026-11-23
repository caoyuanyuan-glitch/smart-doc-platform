<template>
  <ul class="tree-list">
    <li v-for="node in nodes" :key="node.id" class="tree-node">
      <div
        class="tree-row"
        :class="{ active: currentFolderId === node.id, 'has-menu': contextFolderId === node.id }"
        @click="$emit('select', node)"
        @contextmenu="onRowContextMenu(node, $event)"
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
      </div>

      <ul v-if="node.children && node.children.length > 0 && expandedIds.has(node.id)" class="tree-children">
        <recursive-tree
          :nodes="node.children"
          :current-folder-id="currentFolderId"
          :expanded-ids="expandedIds"
          :context-folder-id="contextFolderId"
          :enable-context-menu="enableContextMenu"
          @toggle="$emit('toggle', $event)"
          @select="$emit('select', $event)"
          @contextmenu="$emit('contextmenu', $event)"
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
  contextFolderId: { type: Number, default: null },
  enableContextMenu: { type: Boolean, default: true }
})

const emit = defineEmits(['toggle', 'select', 'contextmenu'])

function onRowContextMenu(node, event) {
  if (!props.enableContextMenu) return
  event.preventDefault()
  event.stopPropagation()
  emit('contextmenu', { node, event })
}
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

.tree-row.active .expand-arrow {
  color: #fff;
}

.tree-row.active .tree-icon {
  filter: brightness(0) invert(1);
}

.tree-row.has-menu {
  background: #dbeafe;
}

.tree-row.active.has-menu {
  background: #4f8ff7;
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


.tree-children {
  list-style: none;
  padding-left: 12px;
  margin: 0;
}
</style>
