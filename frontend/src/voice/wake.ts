// Wake-phrase matching for hands-free use: "Hey Kawan, what is metformin?" → "what is metformin?"
// Speech recognisers often mishear an unfamiliar name, so a few close spellings are accepted.

const NAME = '(?:kawan|cowan|kawen|ka wan|kow an|kau an|kauan)'
const WAKE = new RegExp(`^\\s*(?:(?:hey|hei|hai|hi|ok|okay|helo|hello)\\s+)?${NAME}\\b[\\s,.!?]*`, 'i')

export interface WakeMatch {
  woke: boolean
  command: string
}

export function matchWake(transcript: string): WakeMatch {
  const t = transcript.trim()
  const m = t.match(WAKE)
  if (!m) return { woke: false, command: '' }
  return { woke: true, command: t.slice(m[0].length).trim() }
}

/** Replies we accept without a wake word while Kawan is actively asking "Are you okay?". */
export function isCheckinAnswer(transcript: string): boolean {
  return /\b(ok|okay|fine|alright|help|tolong|baik|sakit|hurt|pain|can'?t|tak)\b/i.test(transcript)
}
