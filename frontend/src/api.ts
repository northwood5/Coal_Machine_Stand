// 后端 API 封装与类型定义

export interface Project {
  id: number
  name: string
  description: string
}

export interface Design {
  id: number
  project_id: number
  name: string
}

export interface DesignDetail extends Design {
  model: Record<string, any>
}

export interface FieldSpec {
  path: string
  label: string
  unit: string
  required: boolean
}

export interface ModuleInfo {
  id: string
  name: string
  order: number
  implemented: boolean
  input_fields: FieldSpec[]
  missing_inputs: string[] | null
  dirty: boolean | null
}

export interface ModuleRunResult {
  module: string
  passed: boolean | null
  results: Record<string, any>
  margins: Record<string, number>
  suggestions: string[]
  standard_refs: string[]
  snapshot_id: number
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail ?? `HTTP ${resp.status}`)
  }
  return resp.status === 204 ? (undefined as T) : resp.json()
}

export interface LLMSettings {
  provider: string
  model: string
  base_url: string
  api_key_masked: string
  configured: boolean
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  tool_calls?: string[]
}

export interface AgentEvent {
  type: 'text' | 'tool_call' | 'tool_result' | 'done' | 'error'
  content?: string
  name?: string
  arguments?: Record<string, any>
  result?: string
  message?: string
}

export const api = {
  listProjects: () => request<Project[]>('/api/projects'),
  createProject: (name: string) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  listDesigns: (projectId: number) => request<Design[]>(`/api/projects/${projectId}/designs`),
  createDesign: (projectId: number, name: string) =>
    request<DesignDetail>(`/api/projects/${projectId}/designs`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  getDesign: (designId: number) => request<DesignDetail>(`/api/designs/${designId}`),
  updateParams: (designId: number, section: string, values: Record<string, any>) =>
    request<DesignDetail>(`/api/designs/${designId}/params`, {
      method: 'PATCH',
      body: JSON.stringify({ section, values }),
    }),
  listModules: (designId: number) => request<ModuleInfo[]>(`/api/designs/${designId}/modules`),
  runModule: (designId: number, moduleId: string) =>
    request<ModuleRunResult>(`/api/designs/${designId}/modules/${moduleId}/run`, { method: 'POST' }),
  getLLMSettings: () => request<LLMSettings>('/api/settings/llm'),
  saveLLMSettings: (s: { provider: string; model: string; base_url: string; api_key: string }) =>
    request<LLMSettings>('/api/settings/llm', { method: 'PUT', body: JSON.stringify(s) }),
  getAgentHistory: (designId: number) =>
    request<ChatMessage[]>(`/api/designs/${designId}/agent/history`),
  clearAgentHistory: (designId: number) =>
    request<void>(`/api/designs/${designId}/agent/history`, { method: 'DELETE' }),
  reportUrl: (designId: number) => `/api/designs/${designId}/report?format=html`,
}

export function agentWebSocket(designId: number): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${location.host}/api/designs/${designId}/agent/ws`)
}
