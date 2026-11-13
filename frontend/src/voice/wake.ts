// Wake-word matching for hands-free use. The wake word is "Hey":
//   "Hey, what is metformin?"        → "what is metformin?"
//   "Hey Kawan, what is metformin?"  → "what is metformin?"   (the name is optional and removed)
//   "Kawan, what is metformin?"      → "what is metformin?"   (still works on its own)
// "Kawan" is not an English word, so recognisers transcribe it many ways ("Cowan", "Karwan", "Kevin",
// "car one"...). We compare a rough sound-key of the word(s) after "hey" with "kawan" to strip it.

// how speech recognisers write "hey" (and the Malay "hai")
const WAKE_WORDS = new Set(['hey', 'hei', 'hay', 'hai', 'heyy', 'heey'])
const TARGET = soundKey('kawan')

export interface WakeMatch {
  woke: boolean
  command: string
}

/** Rough phonetic key: c/q/g → k, every vowel → a, collapse repeats, drop h/r after a vowel. */
export function soundKey(word: string): string {
  return word
    .toLowerCase()
    .replace(/[^a-z]/g, '')
    .replace(/[cqg]/g, 'k')
    .replace(/[aeiouy]+/g, 'a')
    .replace(/a[hr]/g, 'a')
    .replace(/(.)\1+/g, '$1')
}

function distance(a: string, b: string): number {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)])
  for (let j = 1; j <= b.length; j++) d[0][j] = j
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
  return d[a.length][b.length]
}

export function matchWake(transcript: string): WakeMatch {
  const words = transcript.trim().split(/\s+/).filter(Boolean)
  const clean = (w: string) => w.toLowerCase().replace(/[^a-z']/g, '')
  const rest = (from: number) =>
    words
      .slice(from)
      .join(' ')
      .replace(/^[\s,.!?]+/, '')
      .trim()
  const heyFirst = words.length > 0 && WAKE_WORDS.has(clean(words[0]))
  const i = heyFirst ? 1 : 0
  // after "hey", drop the name if it's there: one word ("cowan") or two ("ka wan", "car one")
  for (const n of [1, 2]) {
    if (i + n > words.length) break
    const key = soundKey(words.slice(i, i + n).join(''))
    const dist = distance(key, TARGET)
    // "Kawan" alone needs an exact sound-match; after "hey" a near-match is dropped too
    if (dist === 0 || (heyFirst && dist <= (key.length >= 4 ? 2 : 1)))
      return { woke: true, command: rest(i + n) }
  }
  return heyFirst ? { woke: true, command: rest(1) } : { woke: false, command: '' }
}

/** Replies we accept without a wake word while Kawan is actively asking "Are you okay?". */
export function isCheckinAnswer(transcript: string): boolean {
  return /\b(ok|okay|fine|alright|help|tolong|baik|sakit|hurt|pain|can'?t|tak)\b/i.test(transcript)
}
