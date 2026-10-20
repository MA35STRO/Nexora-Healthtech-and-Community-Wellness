import { useEffect, useState } from 'react'
import { api, type Triage } from '../api'
import { t, type Lang } from '../i18n'

const MOODS = ['😣', '🙁', '😐', '🙂', '😄']
const LEVEL_TITLE: Record<Triage['level'], { en: string; ms: string }> = {
  emergency: { en: 'Emergency — call 999', ms: 'Kecemasan — hubungi 999' },
  urgent: { en: 'See a doctor today', ms: 'Jumpa doktor hari ini' },
  routine: { en: 'Keep an eye on it', ms: 'Pantau keadaan' },
  self_care: { en: 'Looking good today', ms: 'Keadaan baik hari ini' },
}

export function WellnessModal({ lang, onClose, onDone }: { lang: Lang; onClose: () => void; onDone: (r: Triage) => void }) {
  const [options, setOptions] = useState<{ id: string; en: string; ms: string; red_flag: boolean }[]>([])
  const [mood, setMood] = useState<number | null>(null)
  const [pain, setPain] = useState(0)
  const [sleep, setSleep] = useState(7)
  const [symptoms, setSymptoms] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [result, setResult] = useState<Triage | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.wellnessOptions().then((o) => setOptions(o.symptoms)).catch(() => undefined)
  }, [])

  const toggle = (id: string) => setSymptoms((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  const submit = async () => {
    setBusy(true)
    try {
      const r = await api.wellness({ mood, pain, sleep_h: sleep, symptoms, note, lang })
      setResult(r)
      onDone(r)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-bg" role="dialog" aria-modal="true" aria-label={t('dailyCheckin', lang)} onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="card-head">
          <h2>{t('dailyCheckin', lang)}</h2>
          <div className="spacer" />
          <button className="btn ghost small" onClick={onClose}>{t('close', lang)}</button>
        </div>

        {result ? (
          <div>
            <div className={`triage ${result.level}`}>
              <h2>{LEVEL_TITLE[result.level][lang]}</h2>
              {result.advice.map((a) => <p key={a} style={{ margin: '6px 0' }}>{a}</p>)}
            </div>
            {result.reasons.length > 0 && (
              <ul className="reasons small">{result.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            )}
            <p className="tiny muted">{result.disclaimer}</p>
            <button className="btn primary" onClick={onClose}>{t('close', lang)}</button>
          </div>
        ) : (
          <>
            <div className="field">
              <label>{t('mood', lang)}</label>
              <div className="moods">
                {MOODS.map((m, i) => (
                  <button key={m} className={mood === i + 1 ? 'sel' : ''} onClick={() => setMood(i + 1)} aria-label={`mood ${i + 1} of 5`}>
                    {m}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <label htmlFor="pain">{t('pain', lang)}: <b>{pain}</b></label>
              <input id="pain" type="range" min={0} max={10} value={pain} onChange={(e) => setPain(+e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="sleep">{t('sleep', lang)}: <b>{sleep}</b></label>
              <input id="sleep" type="range" min={0} max={12} step={0.5} value={sleep} onChange={(e) => setSleep(+e.target.value)} />
            </div>
            <div className="field">
              <label>{t('symptoms', lang)}</label>
              <div className="chips">
                {options.map((o) => (
                  <button key={o.id} className={`${symptoms.includes(o.id) ? 'sel' : ''} ${o.red_flag ? 'red' : ''}`} onClick={() => toggle(o.id)}>
                    {o[lang]}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <label htmlFor="note">{t('note', lang)}</label>
              <textarea id="note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <button className="btn primary" disabled={busy} onClick={submit}>{t('submit', lang)}</button>
          </>
        )}
      </div>
    </div>
  )
}
