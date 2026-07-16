const RESOURCE_FOLDER_NAMES = ['资源库', '资源', 'resource library', 'resource', 'resources']
const MEMORY_FOLDER_NAMES = ['记忆库', 'memory library', 'memory', 'translation memory']

function normalizeName(name) {
  return String(name || '').trim().toLowerCase()
}

function resolveFileType(file) {
  const explicitType = String(file?.file_type || file?.fileType || file?.type || file?.extension || '').trim().toLowerCase()
  if (explicitType) {
    return explicitType.replace(/^\./, '')
  }

  const filename = String(file?.filename || file?.name || '').trim().toLowerCase()
  const lastDotIndex = filename.lastIndexOf('.')
  if (lastDotIndex === -1) {
    return ''
  }
  return filename.slice(lastDotIndex + 1)
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
    fileType: resolveFileType(file),
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
