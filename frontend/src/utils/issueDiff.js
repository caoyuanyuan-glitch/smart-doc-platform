export function escapeIssueHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function issueSuggestionDiffHtml(issue) {
  const original = String(issue?.original_text || '')
  const suggestion = String(issue?.suggestion || '')
  if (!original || !suggestion) return ''
  const maxLen = 4000
  const left = original.slice(0, maxLen)
  const right = suggestion.slice(0, maxLen)
  if (left === right) return ''
  let start = 0
  const minLen = Math.min(left.length, right.length)
  while (start < minLen && left[start] === right[start]) start += 1
  let endLeft = left.length
  let endRight = right.length
  while (endLeft > start && endRight > start && left[endLeft - 1] === right[endRight - 1]) {
    endLeft -= 1
    endRight -= 1
  }
  const prefix = escapeIssueHtml(left.slice(0, start))
  const deleted = escapeIssueHtml(left.slice(start, endLeft))
  const inserted = escapeIssueHtml(right.slice(start, endRight))
  const suffix = escapeIssueHtml(left.slice(endLeft))
  return `${prefix}<span class="diff-delete">${deleted}</span><span class="diff-insert">${inserted}</span>${suffix}`
}
