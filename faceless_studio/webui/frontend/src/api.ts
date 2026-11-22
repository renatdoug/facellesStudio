import type { Channel, Job, Meta, Script, ScriptState } from './types'

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!res.ok) {
    let detail = `Erro ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch { /* corpo não é JSON */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const enc = encodeURIComponent
const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  meta: () => call<Meta>('/api/meta'),
  channels: () => call<Channel[]>('/api/channels'),
  createChannel: (name: string) => call<Channel>('/api/channels', post({ name })),
  createScript: (channel: string, name: string) =>
    call<{ script: string }>(`/api/channels/${enc(channel)}/scripts`, post({ name })),
  state: (channel: string, script: string) =>
    call<ScriptState>(`/api/channels/${enc(channel)}/scripts/${enc(script)}`),
  save: (channel: string, script: string, data: Script) =>
    call<{ saved: boolean }>(`/api/channels/${enc(channel)}/scripts/${enc(script)}`,
      { method: 'PUT', body: JSON.stringify(data) }),
  setKey: (channel: string, key: string, value: string) =>
    call<{ keys: Record<string, string | null> }>(`/api/channels/${enc(channel)}/env`, post({ key, value })),
  startJob: (req: {
    channel: string; script: string; mode: string; provider?: string | null
    regen?: string; strict: boolean; no_voice: boolean
  }) => call<{ id: number }>('/api/jobs', post(req)),
  job: (since: number) => call<Job | null>(`/api/jobs/current?since=${since}`),
  cancel: () => call<{ cancelled: boolean }>('/api/jobs/cancel', post({})),
}
