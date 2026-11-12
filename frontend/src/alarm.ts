// Looping alarm sounds, made with the Web Audio API (no sound files).
//
//  chime   person's screen, while Kawan is checking in ("are you okay?") — soft, every 4 s
//  siren   person's screen, once an alert is escalated — loud, so neighbours or anyone nearby hear it
//  alarm   caregiver dashboard, until someone acknowledges the alert
//
// Browsers only allow sound after the user has tapped or typed on the page once, so the first tap
// anywhere unlocks audio. If a sound is due before that, useAlarm reports `blocked` so the page can
// show a "tap to turn on sound" button.
import { useEffect, useState } from 'react'
import type { Incident, Snapshot } from './api'

export type AlarmKind = 'chime' | 'siren' | 'alarm'

let ctx: AudioContext | null = null
function audio(): AudioContext | null {
  try {
    ctx ??= new AudioContext()
  } catch {
    return null
  }
  return ctx
}

export function unlockAudio() {
  const c = audio()
  if (c && c.state === 'suspended') c.resume().catch(() => undefined)
}
if (typeof window !== 'undefined' && typeof AudioContext !== 'undefined') {
  for (const ev of ['pointerdown', 'keydown'] as const)
    window.addEventListener(ev, unlockAudio, { passive: true })
}

function tone(c: AudioContext, at: number, freq: number, dur: number, gain: number, type: OscillatorType) {
  const o = c.createOscillator()
  const g = c.createGain()
  o.type = type
  o.frequency.value = freq
  g.gain.setValueAtTime(0.0001, at)
  g.gain.exponentialRampToValueAtTime(gain, at + 0.02)
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur)
  o.connect(g).connect(c.destination)
  o.start(at)
  o.stop(at + dur + 0.05)
}

/** One "ring" of each sound, and how often it repeats (seconds). */
export const PATTERNS: Record<AlarmKind, { every: number; play: (c: AudioContext, t: number) => void }> = {
  chime: {
    every: 4,
    play: (c, t) => {
      tone(c, t, 660, 0.25, 0.18, 'sine')
      tone(c, t + 0.25, 880, 0.4, 0.18, 'sine')
    },
  },
  siren: {
    every: 1.6,
    play: (c, t) => {
      // rising and falling wail, like an emergency vehicle
      const o = c.createOscillator()
      const g = c.createGain()
      o.type = 'square'
      o.frequency.setValueAtTime(650, t)
      o.frequency.linearRampToValueAtTime(1300, t + 0.75)
      o.frequency.linearRampToValueAtTime(650, t + 1.5)
      g.gain.setValueAtTime(0.0001, t)
      g.gain.exponentialRampToValueAtTime(0.22, t + 0.05)
      g.gain.setValueAtTime(0.22, t + 1.45)
      g.gain.exponentialRampToValueAtTime(0.0001, t + 1.55)
      o.connect(g).connect(c.destination)
      o.start(t)
      o.stop(t + 1.6)
    },
  },
  alarm: {
    every: 2,
    play: (c, t) => [0, 0.25, 0.5].forEach((d) => tone(c, t + d, 880, 0.2, 0.25, 'square')),
  },
}

/** Plays `kind` on a loop until it becomes null (or `paused`, e.g. while Kawan is speaking). */
export function useAlarm(kind: AlarmKind | null, paused = false): { blocked: boolean } {
  const [blocked, setBlocked] = useState(false)
  useEffect(() => {
    if (!kind || paused) return
    const c = audio()
    if (!c) return
    const p = PATTERNS[kind]
    let stopped = false
    const ring = () => {
      if (stopped) return
      if (c.state !== 'running') {
        setBlocked(true)
        c.resume()
          .then(() => !stopped && setBlocked(false))
          .catch(() => undefined)
        return
      }
      setBlocked(false)
      p.play(c, c.currentTime + 0.02)
    }
    ring()
    const id = setInterval(ring, p.every * 1000)
    return () => {
      stopped = true
      clearInterval(id)
      setBlocked(false)
    }
  }, [kind, paused])
  return { blocked }
}

/** Person's screen: chime while being checked on, siren once escalated (until silenced or resolved). */
export function companionAlarm(
  snap: Pick<Snapshot, 'state' | 'active_incident'> | null,
  silencedId: number | null,
): AlarmKind | null {
  if (!snap) return null
  const a = snap.active_incident
  if (snap.state === 'escalated' && a && a.id !== silencedId) return 'siren'
  if (snap.state === 'check_in') return 'chime'
  return null
}

/** Caregiver dashboard: ring while any escalated alert is still open (not yet acknowledged). */
export function caregiverAlarm(
  incidents: Pick<Incident, 'id' | 'escalated' | 'status'>[],
  silenced: ReadonlySet<number>,
): AlarmKind | null {
  return incidents.some((i) => i.escalated && i.status === 'open' && !silenced.has(i.id)) ? 'alarm' : null
}
