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
          <span class="tree-action" @click.stop="$emit('create-sub', node.id)" title="新建子文件夹">➕</span>
          <span class="tree-action" @click.stop="$emit('rename', node)" title="重命名">✏️</span>
          <span class="tree-action delete" @click.stop="$emit('delete', node)" title="删除">🗑️</span>
        </span>
      </div>

      <ul v-if="node.children && node.children.length > 0 && expandedIds.has(node.id)" class="tree-children">
        <recursive-tree
          :nodes="node.children"
          :current-folder-id="currentFolderId"
          :expanded-ids="expandedIds"
          @toggle="$emit('toggle', $event)"
          @select="$emit('select', $event)"
          @create-sub="$emit('create-sub', $event)"
          @rename="$emit('rename', $event)"
          @delete="$emit('delete', $event)"
        />
      </ul>
    </li>
  </ul>
</template>

<script setup>
defineProps({
  nodes: { type: Array, required: true },
  currentFolderId: { type: Number, default: null },
  expandedIds: { type: Set, required: true }
})

defineEmits(['toggle', 'select', 'create-sub', 'rename', 'delete'])
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
  background: #2563eb;
  color: #fff;
}

.tree-row.active {
  background: #2563eb;
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
  color: #fff;
  opacity: 0.8;
}

.tree-row.active .tree-action:hover {
  opacity: 1;
}

.expand-arrow {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #64748b;
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.2s;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.expand-placeholder {
  width: 16px;
  flex-shrink: 0;
}

.tree-icon {
  font-size: 14px;
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
  font-size: 14px;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.15s;
  display: flex;
  align-items: center;
}

.tree-action:hover {
  opacity: 1;
}

.tree-children {
  list-style: none;
  padding-left: 12px;
  margin: 0;
}
</style>
