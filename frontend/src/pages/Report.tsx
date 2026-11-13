import { useEffect, useState, type ReactNode } from 'react'
import { api, fmtDateTime, KIND_LABEL, type Insights, type Profile, type ReportEdits } from '../api'
import { IconPrint } from '../components/icons'
import { BrandMark, TopBar } from '../components/Layout'

function stats(xs: number[]) {
  if (!xs.length) return null
  const avg = xs.reduce((a, b) => a + b, 0) / xs.length
  return { avg: Math.round(avg * 10) / 10, min: Math.min(...xs), max: Math.max(...xs) }
}

type SectionKey = 'details' | 'glance' | 'vitals' | 'meds' | 'symptoms' | 'alerts' | 'questions' | 'notes'
const EMPTY: ReportEdits = { notes: '', questions: [], hidden_sections: [], hidden_questions: [] }
const field = {
  padding: '7px 10px',
  borderRadius: 10,
  border: '1px solid var(--line)',
  background: 'var(--bg)',
  width: '100%',
}

/** A report section: hidden ones disappear from the report, but stay (dimmed) while editing. */
function Section(props: {
  k: SectionKey
  title: string
  editing: boolean
  included: boolean
  onToggle: () => void
  children: ReactNode
}) {
  const { k, title, editing, included, onToggle, children } = props
  if (!editing && !included) return null
  return (
    <section className={editing && !included ? 'report-hidden' : undefined} data-testid={`section-${k}`}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2>{title}</h2>
        {editing && (
          <label className="small no-print" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={included} onChange={onToggle} />
            Include in report
          </label>
        )}
      </div>
      {children}
    </section>
  )
}

export function Report({ connected }: { connected: boolean }) {
  const [data, setData] = useState<Insights | null>(null)
  const [days, setDays] = useState(7)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<ReportEdits>(EMPTY)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [newQ, setNewQ] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    api
      .insights(days)
      .then(setData)
      .catch(() => undefined)
  useEffect(() => {
    load()
  }, [days]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!data)
    return (
      <>
        <TopBar connected={connected} />
        <main className="report">Loading report…</main>
      </>
    )

  const edits = editing ? draft : (data.report ?? EMPTY)
  const shown = (k: SectionKey) => !edits.hidden_sections.includes(k)
  const startEditing = () => {
    setDraft(data.report ?? EMPTY)
    setProfile(data.profile)
    setNewQ('')
    setError(null)
    setEditing(true)
  }
  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const extra = newQ.trim() ? [...draft.questions, newQ.trim()] : draft.questions
      await api.saveReport({ ...draft, questions: extra })
      if (profile) await api.saveProfile(profile)
      await load()
      setEditing(false)
    } catch {
      setError('Could not save. Is the Kawan hub running?')
    } finally {
      setSaving(false)
    }
  }
  const toggle = (list: 'hidden_sections' | 'hidden_questions', key: string) =>
    setDraft((d) => ({
      ...d,
      [list]: d[list].includes(key) ? d[list].filter((x) => x !== key) : [...d[list], key],
    }))

  const sec = (k: SectionKey) => ({
    k,
    editing,
    included: shown(k),
    onToggle: () => toggle('hidden_sections', k),
  })

  const pick = (k: 'hr' | 'spo2' | 'sys' | 'dia' | 'temp') =>
    data.vitals.map((v) => v[k]).filter((x): x is number => typeof x === 'number')
  const vit = {
    hr: stats(pick('hr')),
    spo2: stats(pick('spo2')),
    sys: stats(pick('sys')),
    dia: stats(pick('dia')),
    temp: stats(pick('temp')),
  }
  const simulated =
    data.vitals.some((v) => v.simulated) ||
    data.wellness.some((w) => w.simulated) ||
    data.adherence.days.some((d) => d.simulated)
  const moods = data.wellness.map((w) => w.mood).filter((x): x is number => x != null)
  const pains = data.wellness.map((w) => w.pain).filter((x): x is number => x != null)
  const symptomCounts: Record<string, number> = {}
  data.wellness.forEach((w) => w.symptoms.forEach((s) => (symptomCounts[s] = (symptomCounts[s] ?? 0) + 1)))
  const from = new Date((data.generated_t - days * 86400) * 1000).toLocaleDateString()
  const to = new Date(data.generated_t * 1000).toLocaleDateString()
  const p = editing && profile ? profile : data.profile

  // suggested questions come from the data; the caregiver can remove any of them
  const auto: [string, string | false][] = [
    [
      'missed',
      data.adherence.missed > 0 && `${data.adherence.missed} missed doses — is the schedule easy to follow?`,
    ],
    ['bp', (vit.sys?.max ?? 0) >= 140 && `Home systolic BP reached ${vit.sys?.max} mmHg.`],
    ['spo2', (vit.spo2?.min ?? 100) < 94 && `Lowest home SpO2 was ${vit.spo2?.min}%.`],
    [
      'fall',
      data.incidents.some((i) => i.kind === 'possible_fall') &&
        'A possible fall was detected — consider a falls-risk review.',
    ],
    ['pain', (stats(pains)?.max ?? 0) >= 6 && `Pain reached ${stats(pains)?.max}/10.`],
    ['dizzy', 'Any medicines that could cause dizziness or drowsiness?'],
  ]
  const autoShown = auto.filter(([, text]) => text) as [string, string][]
  const anyQuestion =
    autoShown.some(([k]) => !edits.hidden_questions.includes(k)) || edits.questions.length > 0

  return (
    <>
      <TopBar connected={connected}>
        <div className="row no-print">
          {!editing && (
            <select
              value={days}
              onChange={(e) => setDays(+e.target.value)}
              aria-label="Report period"
              style={{
                padding: '6px 10px',
                borderRadius: 10,
                border: '1px solid var(--line)',
                background: 'var(--card)',
              }}
            >
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
            </select>
          )}
          {editing ? (
            <>
              <button className="btn small" onClick={() => setEditing(false)} disabled={saving}>
                Cancel
              </button>
              <button className="btn small primary" onClick={save} disabled={saving}>
                {saving ? 'Saving…' : 'Save changes'}
              </button>
            </>
          ) : (
            <>
              <button className="btn small" onClick={startEditing}>
                ✏️ Edit report
              </button>
              <button className="btn small primary" onClick={() => window.print()}>
                <IconPrint size={16} /> Print / Save PDF
              </button>
            </>
          )}
        </div>
      </TopBar>
      <main className="report" data-testid="report">
        {editing && (
          <p className="chip info no-print" style={{ whiteSpace: 'normal' }}>
            Editing: change the details, add notes and questions for the doctor, or untick a section to leave
            it out. Readings, doses and alerts come from the app and can't be changed here.
          </p>
        )}
        {error && (
          <p className="chip danger no-print" style={{ whiteSpace: 'normal' }}>
            {error}
          </p>
        )}
        <div className="row">
          <BrandMark />
          <div>
            <h1>Home monitoring summary</h1>
            <div className="muted">
              {p.user_name || 'Name not set'} · {from} – {to} · generated {fmtDateTime(data.generated_t)}
            </div>
          </div>
        </div>
        {simulated && (
          <p className="chip info" style={{ marginTop: 12 }}>
            Contains SIMULATED demo data — not real patient readings
          </p>
        )}

        <Section {...sec('details')} title="Details (as entered in the app)">
          {editing && profile ? (
            <div className="report-edit-grid">
              {(
                [
                  ['user_name', 'Name'],
                  ['conditions', 'Conditions'],
                  ['allergies', 'Allergies'],
                  ['caregiver_name', 'Caregiver'],
                  ['caregiver_phone', 'Caregiver phone'],
                ] as const
              ).map(([k, label]) => (
                <label key={k} className="small">
                  <b>{label}</b>
                  <input
                    aria-label={label}
                    value={profile[k]}
                    onChange={(e) => setProfile({ ...profile, [k]: e.target.value })}
                    style={field}
                  />
                </label>
              ))}
              <span className="tiny muted">These are also saved to the profile on the Caregiver page.</span>
            </div>
          ) : (
            <dl className="kv">
              <dt>Conditions</dt>
              <dd>{p.conditions || 'Not entered'}</dd>
              <dt>Allergies</dt>
              <dd>{p.allergies || 'Not entered'}</dd>
              <dt>Caregiver</dt>
              <dd>{[p.caregiver_name, p.caregiver_phone].filter(Boolean).join(' · ') || 'Not entered'}</dd>
            </dl>
          )}
        </Section>

        <Section {...sec('glance')} title="At a glance">
          <div className="stats">
            <div className="stat">
              <span className="muted small">Medication adherence</span>
              <b>{data.adherence.percent ?? '–'}%</b>
              <span className="small">
                {data.adherence.taken} taken · {data.adherence.missed} missed
              </span>
            </div>
            <div className="stat">
              <span className="muted small">Alerts</span>
              <b>{data.incidents.length}</b>
              <span className="small">{data.incidents.filter((i) => i.escalated).length} escalated</span>
            </div>
            <div className="stat">
              <span className="muted small">Avg mood (1–5)</span>
              <b>{stats(moods)?.avg ?? '–'}</b>
              <span className="small">{data.wellness.length} check-ins</span>
            </div>
            <div className="stat">
              <span className="muted small">Avg pain (0–10)</span>
              <b>{stats(pains)?.avg ?? '–'}</b>
              <span className="small">max {stats(pains)?.max ?? '–'}</span>
            </div>
          </div>
        </Section>

        <Section {...sec('vitals')} title="Vital signs (home device)">
          <table>
            <thead>
              <tr>
                <th>Measure</th>
                <th>Average</th>
                <th>Lowest</th>
                <th>Highest</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ['Heart rate (bpm)', vit.hr],
                  ['SpO2 (%)', vit.spo2],
                  ['Systolic BP (mmHg)', vit.sys],
                  ['Diastolic BP (mmHg)', vit.dia],
                  ['Temperature (°C)', vit.temp],
                ] as const
              ).map(([label, s]) => (
                <tr key={label}>
                  <td>{label}</td>
                  <td>{s?.avg ?? '–'}</td>
                  <td>{s?.min ?? '–'}</td>
                  <td>{s?.max ?? '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section {...sec('meds')} title="Medicines">
          <table>
            <thead>
              <tr>
                <th>Medicine</th>
                <th>Dose</th>
                <th>Times</th>
                <th>Purpose / instructions</th>
              </tr>
            </thead>
            <tbody>
              {data.meds.map((m) => (
                <tr key={m.id}>
                  <td>{m.name}</td>
                  <td>{m.dose}</td>
                  <td>{m.times.join(', ')}</td>
                  <td>{[m.purpose, m.instructions].filter(Boolean).join(' — ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>Day</th>
                {data.adherence.days.map((d) => (
                  <th key={d.date}>
                    {new Date(d.date + 'T00:00').toLocaleDateString([], { weekday: 'short', day: 'numeric' })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Taken</td>
                {data.adherence.days.map((d) => (
                  <td key={d.date}>{d.taken}</td>
                ))}
              </tr>
              <tr>
                <td>Missed</td>
                {data.adherence.days.map((d) => (
                  <td
                    key={d.date}
                    style={{
                      color: d.missed ? 'var(--danger)' : undefined,
                      fontWeight: d.missed ? 800 : undefined,
                    }}
                  >
                    {d.missed}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </Section>

        <Section {...sec('symptoms')} title="Symptoms reported">
          {Object.keys(symptomCounts).length ? (
            <p>
              {Object.entries(symptomCounts)
                .map(([s, n]) => `${s.replace('_', ' ')} (${n}×)`)
                .join(', ')}
            </p>
          ) : (
            <p className="muted">None reported.</p>
          )}
          {data.wellness
            .filter((w) => w.note)
            .map((w) => (
              <p key={w.t} className="small">
                “{w.note}” — {fmtDateTime(w.t)}
              </p>
            ))}
        </Section>

        <Section {...sec('alerts')} title="Alerts and events">
          {data.incidents.length ? (
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Type</th>
                  <th>Severity</th>
                  <th>Response</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {data.incidents.map((i) => (
                  <tr key={i.id}>
                    <td>{fmtDateTime(i.created_t)}</td>
                    <td>
                      {KIND_LABEL[i.kind] ?? i.kind}
                      {i.source === 'demo' && ' (sim)'}
                    </td>
                    <td>{i.severity}</td>
                    <td>{i.user_response.replace('_', ' ')}</td>
                    <td className="small">{i.reasons.join('; ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No alerts in this period.</p>
          )}
        </Section>

        <Section {...sec('questions')} title="Questions to discuss with the doctor">
          <ul className={editing ? 'report-questions editing' : 'report-questions'}>
            {autoShown.map(([k, text]) => {
              const hidden = edits.hidden_questions.includes(k)
              if (hidden && !editing) return null
              return (
                <li key={k} className={hidden ? 'report-hidden' : undefined}>
                  {text}
                  {editing && (
                    <button
                      className="btn small ghost no-print"
                      onClick={() => toggle('hidden_questions', k)}
                    >
                      {hidden ? 'Put back' : 'Remove'}
                    </button>
                  )}
                </li>
              )
            })}
            {edits.questions.map((q, n) => (
              <li key={`own-${n}`}>
                {editing ? (
                  <input
                    aria-label={`Your question ${n + 1}`}
                    value={q}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        questions: d.questions.map((x, j) => (j === n ? e.target.value : x)),
                      }))
                    }
                    style={{ ...field, width: 'auto', flex: 1 }}
                  />
                ) : (
                  q
                )}
                {editing && (
                  <button
                    className="btn small ghost no-print"
                    onClick={() =>
                      setDraft((d) => ({ ...d, questions: d.questions.filter((_, j) => j !== n) }))
                    }
                  >
                    Remove
                  </button>
                )}
              </li>
            ))}
            {!editing && !anyQuestion && <li className="muted">No questions added.</li>}
          </ul>
          {editing && (
            <form
              className="row no-print"
              onSubmit={(e) => {
                e.preventDefault()
                if (!newQ.trim()) return
                setDraft((d) => ({ ...d, questions: [...d.questions, newQ.trim()] }))
                setNewQ('')
              }}
            >
              <input
                aria-label="Add a question"
                placeholder="Add your own question, e.g. Can she take paracetamol with her medicines?"
                value={newQ}
                onChange={(e) => setNewQ(e.target.value)}
                style={{ ...field, width: 'auto', flex: 1 }}
              />
              <button className="btn small">Add</button>
            </form>
          )}
        </Section>

        {(editing || edits.notes) && (
          <Section {...sec('notes')} title="Notes from the caregiver">
            {editing ? (
              <textarea
                aria-label="Notes for the doctor"
                placeholder="Anything the doctor should know, e.g. changes you've noticed, side effects, how they've been sleeping."
                value={draft.notes}
                onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
                rows={5}
                maxLength={2000}
                style={{ ...field, resize: 'vertical' }}
              />
            ) : (
              <p style={{ whiteSpace: 'pre-wrap' }}>{edits.notes}</p>
            )}
          </Section>
        )}

        <p className="tiny muted" style={{ marginTop: 28 }}>
          Generated by Kawan, a prototype home safety companion. This is a summary of self-reported and
          home-device data to support a conversation with a healthcare professional. It is not a diagnosis and
          has not been clinically validated.
          {(edits.notes || edits.questions.length > 0) &&
            ' Notes and added questions were written by the caregiver.'}
        </p>
      </main>
    </>
  )
}
