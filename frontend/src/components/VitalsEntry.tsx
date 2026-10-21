import { useState } from 'react'
import { api } from '../api'
import type { Lang } from '../i18n'

const FIELDS = [
  { k: 'sys', en: 'BP top (systolic)', ms: 'BP atas (sistolik)', min: 50, max: 260, step: 1 },
  { k: 'dia', en: 'BP bottom (diastolic)', ms: 'BP bawah (diastolik)', min: 30, max: 160, step: 1 },
  { k: 'hr', en: 'Heart rate', ms: 'Kadar jantung', min: 20, max: 250, step: 1 },
  { k: 'spo2', en: 'Oxygen SpO2 %', ms: 'Oksigen SpO2 %', min: 50, max: 100, step: 1 },
  { k: 'temp', en: 'Temperature °C', ms: 'Suhu °C', min: 30, max: 45, step: 0.1 },
] as const

/** Enter a REAL reading from a home device (BP monitor, oximeter, thermometer). Nothing is made up. */
export function VitalsEntry({ lang, onDone }: { lang: Lang; onDone?: () => void }) {
  const [v, setV] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)

  const save = async () => {
    const body: Record<string, number> = {}
    for (const f of FIELDS) {
      const raw = v[f.k]?.trim()
      if (!raw) continue
      const n = Number(raw)
      if (!Number.isFinite(n) || n < f.min || n > f.max) {
        setMsg(
          lang === 'ms'
            ? `${f.ms}: nilai mesti antara ${f.min} dan ${f.max}`
            : `${f.en}: must be between ${f.min} and ${f.max}`,
        )
        return
      }
      body[f.k] = n
    }
    if (!Object.keys(body).length)
      return setMsg(
        lang === 'ms' ? 'Masukkan sekurang-kurangnya satu bacaan.' : 'Enter at least one reading.',
      )
    if ((body.sys == null) !== (body.dia == null))
      return setMsg(lang === 'ms' ? 'Masukkan kedua-dua nombor BP.' : 'Enter both blood pressure numbers.')
    try {
      const r = await api.vitals({ ...body, source: 'manual' })
      setV({})
      setMsg(
        r.alert
          ? lang === 'ms'
            ? 'Disimpan. Bacaan ini luar biasa — Kawan akan bertanya khabar.'
            : 'Saved. This reading is unusual — Kawan will check on you.'
          : lang === 'ms'
            ? 'Bacaan disimpan.'
            : 'Reading saved.',
      )
      onDone?.()
    } catch {
      setMsg(lang === 'ms' ? 'Tidak dapat menyimpan.' : 'Could not save the reading.')
    }
  }

  return (
    <form
      className="vitals-entry"
      onSubmit={(e) => {
        e.preventDefault()
        save()
      }}
    >
      <div className="vitals-entry-grid">
        {FIELDS.map((f) => (
          <label key={f.k} className="small">
            <span className="muted">{f[lang]}</span>
            <input
              inputMode="decimal"
              value={v[f.k] ?? ''}
              onChange={(e) => setV({ ...v, [f.k]: e.target.value })}
              aria-label={f.en}
              placeholder="–"
            />
          </label>
        ))}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn small primary">{lang === 'ms' ? 'Simpan bacaan' : 'Save reading'}</button>
        {msg && <span className="small">{msg}</span>}
      </div>
    </form>
  )
}
