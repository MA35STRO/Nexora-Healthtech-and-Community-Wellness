import { useEffect, useRef, useState } from 'react'

export type EngineState = 'monitoring' | 'check_in' | 'attention' | 'escalated'

export interface Incident {
  id: number
  kind: string
  created_t: number
  severity: 'low' | 'medium' | 'critical'
  status: 'open' | 'acknowledged' | 'resolved'
  user_response: string
  reasons: string[]
  uncertainty: string
  source: string
  checkin_deadline: number | null
  escalated: boolean
  escalation_reason: string | null
  updated_t: number
  notes: string[]
}

export interface TimelineEvent {
  id: number
  t: number
  kind: string
  message: string
  source: string
  incident_id: number | null
}

export interface ChatMsg {
  id: number
  t: number
  from: 'user' | 'assistant'
  text: string
  kind: 'chat' | 'checkin' | 'reminder' | 'alert'
  source: string | null
  refs?: { title: string; source: string }[]
}

export interface Profile {
  user_name: string
  caregiver_name: string
  caregiver_phone: string
  conditions: string
  allergies: string
}

export interface DoseView {
  id: string
  med_id: string
  name: string
  dose: string
  color: string
  instructions: string
  due_t: number
  status: 'upcoming' | 'due' | 'snoozed' | 'taken' | 'missed'
  taken_t: number | null
  demo: boolean
}

export interface Med {
  id: string
  name: string
  dose: string
  times: string[]
  instructions: string
  purpose: string
  color: string
}

export interface Vitals {
  t: number
  source: string
  hr?: number
  spo2?: number
  sys?: number
  dia?: number
  temp?: number
}

export interface Snapshot {
  version: number
  server_time: number
  state: EngineState
  active_incident: Incident | null
  incidents: Incident[]
  events: TimelineEvent[]
  chat: ChatMsg[]
  pending_prompt: string | null
  checkin_deadline: number | null
  lang: 'en' | 'ms'
  camera: { browser_connected: boolean; browser_fps: number }
  demo: { running: string | null; scenarios: Record<string, string> }
  live: {
    person: boolean
    posture: string
    torso_angle: number
    source: string
    motion: number | null
  } | null
  routine: { still_s: number; threshold_s: number }
  meds: { today: DoseView[]; next: DoseView | null; schedule: Med[] }
  vitals: { latest: Vitals | null; history: Vitals[]; simulated: boolean; mode: string }
  ai: { online: boolean; model: string | null }
  notify: { telegram: boolean }
  profile: Profile
  config: { checkin_timeout_s: number }
}

export interface Insights {
  generated_t: number
  profile: Profile
  adherence: {
    days: { date: string; taken: number; missed: number; simulated: boolean }[]
    taken: number
    missed: number
    percent: number | null
  }
  activity: { date: string; simulated: boolean; active_min: number[]; present_min: number[] }[]
  wellness: {
    t: number
    mood: number | null
    pain: number | null
    sleep_h: number | null
    symptoms: string[]
    note: string
    level: string
    simulated: boolean
  }[]
  vitals: (Vitals & { simulated: boolean })[]
  incidents: Incident[]
  incident_counts: Record<string, number>
  meds: Med[]
  events: TimelineEvent[]
}

export interface Triage {
  level: 'emergency' | 'urgent' | 'routine' | 'self_care'
  reasons: string[]
  advice: string[]
  red_flags: string[]
  disclaimer: string
}

export interface ChatReply {
  reply: string
  route: string
  source: string
  action: string | null
  refs: { title: string; source: string }[]
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${method} ${url} → ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  state: () => req<Snapshot>('GET', '/api/state'),
  insights: (days = 7) => req<Insights>('GET', `/api/insights?days=${days}`),
  chat: (text: string) => req<ChatReply>('POST', '/api/chat', { text }),
  ack: (id: number) => req('POST', `/api/incidents/${id}/ack`),
  resolve: (id: number, note: string) => req('POST', `/api/incidents/${id}/resolve`, { note }),
  takeMed: (med_id?: string) => req<{ reply: string }>('POST', '/api/meds/take', { med_id }),
  snoozeMed: () => req<ChatReply>('POST', '/api/meds/snooze'),
  addMed: (m: Omit<Med, 'id'>) => req('POST', '/api/meds', m),
  removeMed: (id: string) => req('DELETE', `/api/meds/${id}`),
  wellnessOptions: () =>
    req<{
      symptoms: { id: string; en: string; ms: string; red_flag: boolean }[]
      hotlines: Record<string, string>
    }>('GET', '/api/wellness/options'),
  wellness: (body: {
    mood: number | null
    pain: number | null
    sleep_h: number | null
    symptoms: string[]
    note: string
    lang: string
  }) => req<Triage>('POST', '/api/wellness', body),
  pillCheck: (image: string) =>
    req<{
      medicine: string | null
      matches: string | null
      confidence: string
      note: string
      source: string
    }>('POST', '/api/pillcheck', { image }),
  vitals: (v: Partial<Vitals>) => req<{ ok: boolean; alert: boolean }>('POST', '/api/vitals', v),
  profile: () => req<Profile>('GET', '/api/profile'),
  saveProfile: (p: Partial<Profile>) => req<Profile>('POST', '/api/profile', p),
  demo: (name: string) => req('POST', `/api/demo/${name}`),
  demoStop: () => req('POST', '/api/demo/stop'),
  reset: () => req('POST', '/api/reset'),
}

export function wsUrl(path: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}

/** Live snapshot over WebSocket, auto-reconnecting. `connected` is false while the backend is unreachable. */
export function useSnapshot(): { snap: Snapshot | null; connected: boolean } {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [connected, setConnected] = useState(false)
  const retry = useRef(0)

  useEffect(() => {
    let ws: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let closed = false
    const open = () => {
      ws = new WebSocket(wsUrl('/ws'))
      ws.onopen = () => {
        retry.current = 0
        setConnected(true)
      }
      ws.onmessage = (e) => setSnap(JSON.parse(e.data) as Snapshot)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) timer = setTimeout(open, Math.min(5000, 500 * 2 ** retry.current++))
      }
      ws.onerror = () => ws?.close()
    }
    open()
    return () => {
      closed = true
      clearTimeout(timer)
      ws?.close()
    }
  }, [])
  return { snap, connected }
}

export function fmtTime(t: number): string {
  return new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function fmtDateTime(t: number): string {
  return new Date(t * 1000).toLocaleString([], {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ago(t: number, now: number): string {
  const s = Math.max(0, Math.round(now - t))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

export const KIND_LABEL: Record<string, string> = {
  possible_fall: 'Possible fall',
  inactivity: 'Unusual inactivity',
  vitals_alert: 'Vital signs alert',
  missed_medication: 'Missed medication',
  red_flag_symptom: 'Emergency warning signs',
  help_request: 'Help requested',
}
