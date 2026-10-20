// Voice: speaks Kawan's messages (speechSynthesis) and listens (Web Speech API, Chrome/Edge).
// Hands-free: "Hey Kawan, …" wakes it. During a check-in it accepts "I'm okay" / "Help" without the wake word.
import { useCallback, useEffect, useRef, useState } from 'react'
import { isCheckinAnswer, matchWake } from './wake'

type Lang = 'en' | 'ms'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Recognition = any

const RecognitionCtor: (new () => Recognition) | undefined =
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition

export const canListen = Boolean(RecognitionCtor)
export const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window

const BCP47: Record<Lang, string> = { en: 'en-US', ms: 'ms-MY' }

function pickVoice(lang: Lang): SpeechSynthesisVoice | undefined {
  const voices = speechSynthesis.getVoices()
  const want = lang === 'ms' ? ['ms-MY', 'ms', 'id-ID', 'id'] : ['en-GB', 'en-US', 'en']
  for (const w of want) {
    const v = voices.find((x) => x.lang.toLowerCase().startsWith(w.toLowerCase()))
    if (v) return v
  }
  return undefined
}

interface Options {
  lang: Lang
  enabled: boolean          // user turned voice on (needed: browsers require a tap before audio)
  handsFree: boolean        // always listening for the wake phrase
  awaitingAnswer: boolean   // a check-in is pending
  onCommand: (text: string) => void
}

export function useVoice({ lang, enabled, handsFree, awaitingAnswer, onCommand }: Options) {
  const [speaking, setSpeaking] = useState(false)
  const [listening, setListening] = useState(false)
  const [heard, setHeard] = useState('')
  const rec = useRef<Recognition | null>(null)
  const want = useRef({ continuous: false, oneShot: false, armedUntil: 0 })
  const opts = useRef({ awaitingAnswer, onCommand })
  opts.current = { awaitingAnswer, onCommand }
  const speakingRef = useRef(false)

  const startRec = useCallback(() => {
    if (!RecognitionCtor || speakingRef.current) return
    try {
      rec.current?.start()
    } catch {
      /* already started */
    }
  }, [])

  useEffect(() => {
    if (!RecognitionCtor) return
    const r: Recognition = new RecognitionCtor()
    r.lang = BCP47[lang]
    r.continuous = true
    r.interimResults = false
    r.onstart = () => setListening(true)
    r.onend = () => {
      setListening(false)
      if (want.current.continuous && !speakingRef.current) setTimeout(startRec, 300)
    }
    r.onerror = () => setListening(false)
    r.onresult = (e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>; resultIndex: number }) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (!e.results[i].isFinal) continue
        const said = e.results[i][0].transcript.trim()
        if (!said) continue
        setHeard(said)
        const w = want.current
        const wake = matchWake(said)
        if (w.oneShot) {
          w.oneShot = false
          opts.current.onCommand(wake.woke ? wake.command || said : said)
          if (!w.continuous) r.stop()
        } else if (wake.woke) {
          if (wake.command) opts.current.onCommand(wake.command)
          else w.armedUntil = Date.now() + 8000   // "Hey Kawan" … (pause) … "what is metformin?"
        } else if (Date.now() < w.armedUntil) {
          w.armedUntil = 0
          opts.current.onCommand(said)
        } else if (opts.current.awaitingAnswer && isCheckinAnswer(said)) {
          opts.current.onCommand(said)
        }
      }
    }
    rec.current = r
    return () => {
      r.onend = null
      r.abort()
      rec.current = null
    }
  }, [lang, startRec])

  // continuous listening when hands-free is on, or while a check-in waits for an answer
  useEffect(() => {
    const on = enabled && (handsFree || awaitingAnswer)
    want.current.continuous = on
    if (on) startRec()
    else if (!want.current.oneShot) rec.current?.stop()
  }, [enabled, handsFree, awaitingAnswer, startRec, lang])

  const speak = useCallback(
    (text: string) => {
      if (!canSpeak || !enabled) return
      speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(text.replace(/"/g, ''))
      u.lang = BCP47[lang]
      const v = pickVoice(lang)
      if (v) u.voice = v
      u.rate = 0.95
      u.pitch = 1.05
      u.onstart = () => {
        speakingRef.current = true
        setSpeaking(true)
        rec.current?.stop()   // don't transcribe ourselves
      }
      const done = () => {
        speakingRef.current = false
        setSpeaking(false)
        if (want.current.continuous || want.current.oneShot) setTimeout(startRec, 250)
      }
      u.onend = done
      u.onerror = done
      speechSynthesis.speak(u)
    },
    [enabled, lang, startRec],
  )

  const pushToTalk = useCallback(() => {
    want.current.oneShot = true
    speechSynthesis?.cancel()
    speakingRef.current = false
    startRec()
  }, [startRec])

  return { speak, speaking, listening, heard, pushToTalk }
}
