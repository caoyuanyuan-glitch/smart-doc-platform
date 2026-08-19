const MODEL_LABELS = {
  qwen: 'Qwen',
  kimi: 'Kimi (Moonshot)',
  deepseek: 'DeepSeek Chat',
  arkclaw: 'ArkClaw Chat',
  mcai: 'MCAI Proxy',
  proxy: 'Proxy'
}

const MODEL_ORDER = ['qwen', 'kimi', 'deepseek', 'arkclaw', 'mcai', 'proxy']

export const TRANSLATION_SOURCE_LANGUAGE_OPTIONS = [
  { label: '自动', value: 'auto' },
  { label: '中文', value: 'zh' },
  { label: '英文', value: 'en' },
  { label: '日文', value: 'ja' },
  { label: '韩文', value: 'ko' },
  { label: '法文', value: 'fr' },
  { label: '德文', value: 'de' },
  { label: '西班牙文', value: 'es' },
  { label: '俄文', value: 'ru' }
]

export const TRANSLATION_TARGET_LANGUAGE_OPTIONS = TRANSLATION_SOURCE_LANGUAGE_OPTIONS.filter(
  (option) => option.value !== 'auto'
)

export const FALLBACK_TRANSLATION_MODELS = MODEL_ORDER.map((name) => ({
  value: name,
  label: MODEL_LABELS[name] || name,
  available: true
}))

function normalizeProviderEntry(name, availableSet) {
  const value = String(name || '').trim().toLowerCase()
  if (!value) return null
  return {
    value,
    label: MODEL_LABELS[value] || value,
    available: availableSet ? availableSet.has(value) : true
  }
}

export function buildAvailableTranslationModels(providerStatus) {
  const hasAvailability = Array.isArray(providerStatus?.available)
  const availableProviders = hasAvailability ? providerStatus.available : []
  const priority = Array.isArray(providerStatus?.priority) ? providerStatus.priority : MODEL_ORDER
  const availableSet = new Set(availableProviders.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean))

  const ordered = []
  for (const name of priority) {
    const model = normalizeProviderEntry(name, hasAvailability ? availableSet : null)
    if (model) {
      ordered.push(model)
    }
  }

  for (const fallback of FALLBACK_TRANSLATION_MODELS) {
    if (!ordered.some((item) => item.value === fallback.value)) {
      ordered.push({ ...fallback, available: hasAvailability ? availableSet.has(fallback.value) : fallback.available })
    }
  }

  return ordered.filter((item) => item.available)
}

export function getTranslationModelLabel(model) {
  const value = String(model || '').trim().toLowerCase()
  return MODEL_LABELS[value] || value || '默认模型'
}

export function getTranslationProviderHint(providerStatus, currentModel, loading = false) {
  if (loading) {
    return '正在检测可用模型...'
  }

  const healthyProviders = Array.isArray(providerStatus?.available) ? providerStatus.available : []
  if (healthyProviders.length > 0) {
    return `当前使用 ${getTranslationModelLabel(currentModel)}`
  }

  const healthProviders = providerStatus?.health?.providers || {}
  const failedProvider = MODEL_ORDER
    .map((name) => ({ name, info: healthProviders[name] }))
    .find((item) => item.info && item.info.status === 'error')

  if (failedProvider) {
    const rawError = String(failedProvider.info.error || '').trim()
    const shortError = rawError ? rawError.slice(0, 90) : '调用失败'
    return `${getTranslationModelLabel(failedProvider.name)} 异常: ${shortError}`
  }

  return '未检测到可用 AI 模型'
}
