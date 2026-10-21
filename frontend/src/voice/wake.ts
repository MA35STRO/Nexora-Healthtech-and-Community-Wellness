// Wake-phrase matching for hands-free use: "Hey Kawan, what is metformin?" → "what is metformin?"
// "Kawan" is not an English word, so recognisers transcribe it many ways ("Cowan", "Karwan", "Kevin",
// "car one"...). We compare a rough sound-key of the first word(s) with "kawan" instead of exact spellings.

const GREETINGS = new Set([
  'hey',
  'hei',
  'hai',
  'hi',
  'hay',
  'ok',
  'okay',
  'hello',
  'helo',
  'hallo',
  'a',
  'eh',
])
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
  let i = 0
  const greeted = words.length > 0 && GREETINGS.has(clean(words[0]))
  if (greeted) i = 1
  // the name may come out as one word ("cowan") or two ("ka wan", "car one")
  for (const n of [1, 2]) {
    if (i + n > words.length) break
    const key = soundKey(words.slice(i, i + n).join(''))
    const dist = distance(key, TARGET)
    // exact sound-match is enough on its own; a near-match needs "hey/hi/ok" in front
    if (dist === 0 || (greeted && dist <= (key.length >= 4 ? 2 : 1))) {
      return {
        woke: true,
        command: words
          .slice(i + n)
          .join(' ')
          .replace(/^[\s,.!?]+/, '')
          .trim(),
      }
    }
  }
  return { woke: false, command: '' }
}

/** Replies we accept without a wake word while Kawan is actively asking "Are you okay?". */
export function isCheckinAnswer(transcript: string): boolean {
  return /\b(ok|okay|fine|alright|help|tolong|baik|sakit|hurt|pain|can'?t|tak)\b/i.test(transcript)
}
