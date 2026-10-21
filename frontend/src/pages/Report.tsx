import { useEffect, useState } from 'react'
import { api, fmtDateTime, KIND_LABEL, type Insights } from '../api'
import { IconPrint } from '../components/icons'
import { BrandMark, TopBar } from '../components/Layout'

function stats(xs: number[]) {
  if (!xs.length) return null
  const avg = xs.reduce((a, b) => a + b, 0) / xs.length
  return { avg: Math.round(avg * 10) / 10, min: Math.min(...xs), max: Math.max(...xs) }
}

export function Report({ connected }: { connected: boolean }) {
  const [data, setData] = useState<Insights | null>(null)
  const [days, setDays] = useState(7)
  useEffect(() => {
    api
      .insights(days)
      .then(setData)
      .catch(() => undefined)
  }, [days])

  if (!data)
    return (
      <>
        <TopBar connected={connected} />
        <main className="report">Loading report…</main>
      </>
    )
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

  return (
    <>
      <TopBar connected={connected}>
        <div className="row no-print">
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
          <button className="btn small primary" onClick={() => window.print()}>
            <IconPrint size={16} /> Print / Save PDF
          </button>
        </div>
      </TopBar>
      <main className="report" data-testid="report">
        <div className="row">
          <BrandMark />
          <div>
            <h1>Home monitoring summary</h1>
            <div className="muted">
              {data.profile.user_name || 'Name not set'} · {from} – {to} · generated{' '}
              {fmtDateTime(data.generated_t)}
            </div>
          </div>
        </div>
        {simulated && (
          <p className="chip info" style={{ marginTop: 12 }}>
            Contains SIMULATED demo data — not real patient readings
          </p>
        )}

        <section>
          <h2>Details (as entered in the app)</h2>
          <dl className="kv">
            <dt>Conditions</dt>
            <dd>{data.profile.conditions || 'Not entered'}</dd>
            <dt>Allergies</dt>
            <dd>{data.profile.allergies || 'Not entered'}</dd>
            <dt>Caregiver</dt>
            <dd>
              {[data.profile.caregiver_name, data.profile.caregiver_phone].filter(Boolean).join(' · ') ||
                'Not entered'}
            </dd>
          </dl>
        </section>

        <section>
          <h2>At a glance</h2>
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
        </section>

        <section>
          <h2>Vital signs (home device)</h2>
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
        </section>

        <section>
          <h2>Medicines</h2>
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
        </section>

        <section>
          <h2>Symptoms reported</h2>
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
        </section>

        <section>
          <h2>Alerts and events</h2>
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
        </section>

        <section>
          <h2>Questions to discuss with the doctor</h2>
          <ul>
            {data.adherence.missed > 0 && (
              <li>{data.adherence.missed} missed doses — is the schedule easy to follow?</li>
            )}
            {(vit.sys?.max ?? 0) >= 140 && <li>Home systolic BP reached {vit.sys?.max} mmHg.</li>}
            {(vit.spo2?.min ?? 100) < 94 && <li>Lowest home SpO2 was {vit.spo2?.min}%.</li>}
            {data.incidents.some((i) => i.kind === 'possible_fall') && (
              <li>A possible fall was detected — consider a falls-risk review.</li>
            )}
            {(stats(pains)?.max ?? 0) >= 6 && <li>Pain reached {stats(pains)?.max}/10.</li>}
            <li>Any medicines that could cause dizziness or drowsiness?</li>
          </ul>
        </section>

        <p className="tiny muted" style={{ marginTop: 28 }}>
          Generated by Kawan, a prototype home safety companion. This is a summary of self-reported and
          home-device data to support a conversation with a healthcare professional. It is not a diagnosis and
          has not been clinically validated.
        </p>
      </main>
    </>
  )
}
