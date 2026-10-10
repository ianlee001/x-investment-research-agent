export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export const headers = () => {
  const token = sessionStorage.getItem('app_token')
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }
}

export async function api<T = any>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...options, headers: { ...headers(), ...options?.headers } })
  const data = await response.json()
  if (!response.ok) {
    const detail = data.detail
    throw new ApiError(response.status, typeof detail === 'string' ? detail : detail?.reason || '请求失败，请稍后重试')
  }
  return data
}

export const post = <T = any>(path: string, body: unknown = {}) => api<T>(path, { method: 'POST', body: JSON.stringify(body) })
export const remove = (path: string) => api(path, { method: 'DELETE' })
export const requestKey = () => crypto.randomUUID()
export const isActive = (status: string) => ['queued', 'running', 'awaiting_approval'].includes(status)
export const formatDate = (value?: string | null) => value ? new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '尚未更新'
export const number = (value?: number | null, digits = 2) => value == null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value)

export type Run = { id: string; thread_id: string; kind: string; question: string; title?: string; status: string; stage: string; ticker?: string; error?: string; created_at: string; completed_at?: string; result?: any; coverage?: any; usage: Record<string, number>; approvals?: any[]; events?: any[]; sources?: any[] }
