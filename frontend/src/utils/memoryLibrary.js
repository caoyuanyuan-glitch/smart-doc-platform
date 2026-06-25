const RESOURCE_FOLDER_NAMES = ['资源库', '资源', 'resource library', 'resource', 'resources']
const MEMORY_FOLDER_NAMES = ['记忆库', 'memory library', 'memory', 'translation memory']

function normalizeName(name) {
  return String(name || '').trim().toLowerCase()
}

function isResourceFolder(name) {
  return RESOURCE_FOLDER_NAMES.includes(normalizeName(name))
}

function isMemoryFolder(name) {
  return MEMORY_FOLDER_NAMES.includes(normalizeName(name))
}

function collectFilesFromFolder(node, path = []) {
  const currentPath = [...path, node.name]
  const files = (node.files || []).map(file => ({
    id: file.id,
    name: file.name,
    filename: file.filename,
    fileType: String(file.file_type || file.fileType || '').toLowerCase(),
    label: [...currentPath, file.name].join(' / '),
    path: currentPath.join(' / ')
  }))

  return [...files, ...(node.children || []).flatMap(child => collectFilesFromFolder(child, currentPath))]
}

export function extractMemoryLibraryFiles(treeData = []) {
  const matchedFiles = []

  function walk(nodes, hasResourceAncestor = false) {
    for (const node of nodes) {
      const hasResource = hasResourceAncestor || isResourceFolder(node.name)
      if (hasResource && isMemoryFolder(node.name)) {
        matchedFiles.push(...collectFilesFromFolder(node))
        continue
      }
      walk(node.children || [], hasResource)
    }
  }

  walk(treeData)
  return matchedFiles.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
}
