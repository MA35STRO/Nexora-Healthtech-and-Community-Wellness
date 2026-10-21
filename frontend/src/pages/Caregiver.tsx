import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ago,
  api,
  fmtDateTime,
  fmtTime,
  KIND_LABEL,
  type Incident,
  type Insights,
  type Snapshot,
} from '../api'
import { ActivityHeatmap, AdherenceChart, VitalsChart, WellnessChart } from '../components/Charts'
import { IconBell, IconPrint } from '../components/icons'
import { TopBar } from '../components/Layout'

const STATE_TEXT: Record<string, [string, string]> = {
  monitoring: ['All clear', 'Monitoring normally — no open alerts'],
  check_in: ['Checking in with them', 'Kawan asked if they are okay and is waiting for a reply'],
  attention: ['Needs a look', 'Something was noticed; they responded or it is low risk'],
  escalated: [
    'ALERT — please check on them now',
    'They asked for help, reported warning signs, or did not respond',
  ],
}
const EVENT_COLOR: Record<string, string> = {
  escalated: 'var(--danger)',
  possible_fall: 'var(--warn)',
  inactivity: 'var(--warn)',
  vitals_alert: 'var(--warn)',
  red_flag_symptom: 'var(--danger)',
  missed_medication: 'var(--warn)',
  user_ok: 'var(--ok)',
  med_taken: 'var(--ok)',
  resolved: 'var(--ok)',
  acknowledged: 'var(--info)',
  checkin_sent: 'var(--brand)',
  demo_started: 'var(--info)',
}

function beep() {
  try {
    const ctx = new AudioContext()
    ;[0, 0.25, 0.5].forEach((d) => {
      const o = ctx.createOscillator()
      const g = ctx.createGain()
      o.frequency.value = 880
      g.gain.setValueAtTime(0.2, ctx.currentTime + d)
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + d + 0.2)
      o.connect(g).connect(ctx.destination)
      o.start(ctx.currentTime + d)
      o.stop(ctx.currentTime + d + 0.2)
    })
  } catch {
    /* audio blocked until the caregiver interacts with the page */
  }
}

function useEscalationAlerts(snap: Snapshot | null) {
  const seen = useRef<Set<number> | null>(null)
  useEffect(() => {
    if (!snap) return
    const escalated = snap.incidents.filter((i) => i.escalated && i.status !== 'resolved')
    if (seen.current === null) {
      seen.current = new Set(escalated.map((i) => i.id))
      return
    }
    for (const i of escalated) {
      if (seen.current.has(i.id)) continue
      seen.current.add(i.id)
      beep()
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(`Kawan alert: ${KIND_LABEL[i.kind] ?? i.kind}`, {
          body: i.escalation_reason ?? i.reasons[0],
          tag: `inc-${i.id}`,
        })
      }
    }
    document.title = escalated.length ? `🚨 ALERT — Kawan` : 'Kawan — Caregiver'
  }, [snap])
}

export function Caregiver({ snap, connected }: { snap: Snapshot | null; connected: boolean }) {
  const [insights, setInsights] = useState<Insights | null>(null)
  const [perm, setPerm] = useState(typeof Notification !== 'undefined' ? Notification.permission : 'denied')
  useEscalationAlerts(snap)
  const loaded = snap !== null
  useEffect(() => {
    // "/caregiver#setup" → jump to the settings card
    if (loaded && location.hash) document.querySelector(location.hash)?.scrollIntoView({ behavior: 'smooth' })
  }, [loaded])

  const refresh = useCallback(
    () =>
      api
        .insights()
        .then(setInsights)
        .catch(() => undefined),
    [],
  )
  const incidentKey = snap?.incidents.map((i) => `${i.id}${i.status}${i.user_response}`).join() ?? ''
  const medKey = snap?.meds.today.map((d) => d.status).join() ?? ''
  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 15000)
    return () => clearInterval(id)
  }, [refresh, incidentKey, medKey])

  if (!snap)
    return (
      <>
        <TopBar connected={connected} />
        <main className="page">Connecting…</main>
      </>
    )
  const [title, sub] = STATE_TEXT[snap.state]
  const active = snap.active_incident
  const now = snap.server_time

  return (
    <>
      <TopBar connected={connected}>
        <div className="row">
          {perm !== 'granted' && 'Notification' in window && (
            <button className="btn small" onClick={() => Notification.requestPermission().then(setPerm)}>
              <IconBell size={16} /> Enable alerts
            </button>
          )}
          <Link className="btn small" to="/report">
            <IconPrint size={16} /> Doctor report
          </Link>
        </div>
      </TopBar>
      <main className="page grid caregiver">
        <section className={`banner span-12 ${snap.state}`} data-testid="status-banner">
          <div style={{ flex: 1, minWidth: 220 }}>
            <div className="sub small">
              {snap.profile.user_name || 'Person at home (name not set)'} · caregiver:{' '}
              {snap.profile.caregiver_name || 'not set'}
            </div>
            <h1>{title}</h1>
            <div className="sub">{sub}</div>
          </div>
          <div className="row">
            <span className="chip">
              {snap.live
                ? `${snap.live.person ? snap.live.posture : 'not in view'} · ${snap.live.source}`
                : 'no live feed'}
            </span>
            <span className={`chip ${snap.camera.browser_fps > 0 ? 'ok' : 'warn'}`}>
              camera {snap.camera.browser_fps > 0 ? `live ${snap.camera.browser_fps} fps` : 'offline'}
            </span>
            {snap.routine.still_s > 60 && (
              <span className="chip">still {Math.round(snap.routine.still_s / 60)} min</span>
            )}
            {snap.notify.telegram && <span className="chip info">Telegram alerts on</span>}
          </div>
        </section>

        <section className="card span-7">
          <div className="card-head">
            <h2>Active alert</h2>
          </div>
          {active ? (
            <IncidentCard inc={active} now={now} />
          ) : (
            <p className="muted">No open alerts. Kawan is monitoring.</p>
          )}
        </section>

        <section className="card span-5">
          <div className="card-head">
            <h2>Live timeline</h2>
          </div>
          <ul className="timeline">
            {snap.events.map((e) => (
              <li key={e.id}>
                <span className="when">{fmtTime(e.t)}</span>
                <span className="bullet" style={{ background: EVENT_COLOR[e.kind] }} />
                <span>
                  {e.message}
                  {e.source === 'demo' && (
                    <span className="chip info tiny" style={{ marginLeft: 6 }}>
                      SIM
                    </span>
                  )}
                </span>
              </li>
            ))}
            {!snap.events.length && <li className="muted">Nothing yet.</li>}
          </ul>
        </section>

        <section className="card span-8">
          <div className="card-head">
            <h2>Vital signs (live)</h2>
            {snap.vitals.simulated && <span className="chip info">SIMULATED device</span>}
            <div className="spacer" />
            {snap.vitals.latest && (
              <span className="small muted">
                HR {snap.vitals.latest.hr} · SpO2 {snap.vitals.latest.spo2}% · BP {snap.vitals.latest.sys}/
                {snap.vitals.latest.dia} · {snap.vitals.latest.temp}°C
              </span>
            )}
          </div>
          {snap.vitals.history.length ? (
            <VitalsChart history={snap.vitals.history} />
          ) : (
            <p className="muted">
              No readings yet. They appear here when readings are entered on the Companion page (“My
              readings”) or sent by a device to <code>/api/vitals</code>.
            </p>
          )}
        </section>

        <section className="card span-4">
          <div className="card-head">
            <h2>Medication adherence</h2>
            <div className="spacer" />
            {insights?.adherence.percent != null && (
              <span className={`chip ${insights.adherence.percent >= 80 ? 'ok' : 'warn'}`}>
                {insights.adherence.percent}% · 7 days
              </span>
            )}
          </div>
          {insights &&
            (insights.adherence.taken + insights.adherence.missed > 0 ? (
              <AdherenceChart data={insights.adherence} />
            ) : (
              <p className="muted">
                No doses recorded yet. Add medicines below; taken and missed doses will be tracked here.
              </p>
            ))}
          <div className="small">
            {snap.meds.today.map((d) => (
              <div key={d.id} className="row" style={{ justifyContent: 'space-between' }}>
                <span>
                  {fmtTime(d.due_t)} {d.name}
                </span>
                <span
                  className={`chip ${d.status === 'taken' ? 'ok' : d.status === 'missed' ? 'danger' : d.status === 'due' ? 'warn' : ''}`}
                >
                  {d.status}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="card span-6">
          <div className="card-head">
            <h2>Activity pattern (active minutes / hour)</h2>
          </div>
          {insights && <ActivityHeatmap data={insights.activity} />}
          <p className="tiny muted">
            {insights?.activity.some((d) => d.simulated) ? '* simulated demo history. ' : ''}
            Built from the camera while the Companion page is open. Kawan learns typical still periods per
            hour to spot unusual inactivity.
          </p>
        </section>

        <section className="card span-6">
          <div className="card-head">
            <h2>Daily check-ins</h2>
          </div>
          {insights &&
            (insights.wellness.length ? (
              <WellnessChart data={insights.wellness} />
            ) : (
              <p className="muted">
                No daily check-ins yet. They are done from the Companion page (“Daily check-in”).
              </p>
            ))}
        </section>

        <section className="card span-7">
          <div className="card-head">
            <h2>Alert history</h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>What</th>
                  <th>Severity</th>
                  <th>Response</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {snap.incidents.map((i) => (
                  <tr key={i.id}>
                    <td>{fmtDateTime(i.created_t)}</td>
                    <td>
                      {KIND_LABEL[i.kind] ?? i.kind}
                      {i.source === 'demo' && ' (sim)'}
                    </td>
                    <td>
                      <span
                        className={`chip ${i.severity === 'critical' ? 'danger' : i.severity === 'medium' ? 'warn' : ''}`}
                      >
                        {i.severity}
                      </span>
                    </td>
                    <td>{i.user_response.replace('_', ' ')}</td>
                    <td>{i.status}</td>
                  </tr>
                ))}
                {!snap.incidents.length && (
                  <tr>
                    <td colSpan={5} className="muted">
                      No alerts yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card span-5">
          <MedsEditor snap={snap} />
        </section>

        <section className="card span-12" id="setup">
          <ProfileEditor snap={snap} />
        </section>

        <section className="card span-12 no-print">
          <DemoPanel snap={snap} />
        </section>
      </main>
      <footer className="disclaimer">
        Prototype for UTP CodeFest 2026. Not a medical device; alerts are safety prompts, not diagnoses.
        Emergencies: 999.
      </footer>
    </>
  )
}

function IncidentCard({ inc, now }: { inc: Incident; now: number }) {
  const [note, setNote] = useState('')
  return (
    <div data-testid="active-incident">
      <div className="row" style={{ marginBottom: 6 }}>
        <span
          className={`chip ${inc.severity === 'critical' ? 'danger' : inc.severity === 'medium' ? 'warn' : 'info'}`}
        >
          {inc.severity.toUpperCase()}
        </span>
        <b style={{ fontSize: '1.15rem' }}>{KIND_LABEL[inc.kind] ?? inc.kind}</b>
        {inc.source === 'demo' && <span className="chip info">SIMULATED</span>}
        <span className="muted small">
          #{inc.id} · {ago(inc.created_t, now)}
        </span>
      </div>
      {inc.escalation_reason && (
        <p style={{ margin: '6px 0', fontWeight: 800, color: 'var(--danger)' }}>{inc.escalation_reason}</p>
      )}
      <div className="small muted" style={{ fontWeight: 800 }}>
        Why Kawan flagged this
      </div>
      <ul className="reasons">
        {inc.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <dl className="kv">
        <dt>Their response</dt>
        <dd>{inc.user_response.replace('_', ' ')}</dd>
        <dt>Status</dt>
        <dd>{inc.status}</dd>
        <dt>Uncertainty</dt>
        <dd className="small">{inc.uncertainty}</dd>
        {inc.notes.length > 0 && (
          <>
            <dt>Notes</dt>
            <dd className="small">{inc.notes.join(' · ')}</dd>
          </>
        )}
      </dl>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn" disabled={inc.status !== 'open'} onClick={() => api.ack(inc.id)}>
          Acknowledge — I'm on it
        </button>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Resolution note (optional)"
          style={{
            flex: 1,
            minWidth: 160,
            padding: '9px 12px',
            borderRadius: 10,
            border: '1px solid var(--line)',
            background: 'var(--bg)',
          }}
        />
        <button className="btn primary" onClick={() => api.resolve(inc.id, note)}>
          Resolve
        </button>
      </div>
    </div>
  )
}

function MedsEditor({ snap }: { snap: Snapshot }) {
  const [name, setName] = useState('')
  const [dose, setDose] = useState('')
  const [time, setTime] = useState('08:00')
  const [instructions, setInstructions] = useState('')
  const [purpose, setPurpose] = useState('')
  const add = async () => {
    if (!name.trim()) return
    const times = time
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
    await api.addMed({
      name,
      dose,
      times,
      instructions,
      purpose,
      color: COLORS[snap.meds.schedule.length % COLORS.length],
    })
    setPurpose('')
    setName('')
    setDose('')
    setInstructions('')
  }
  return (
    <>
      <div className="card-head">
        <h2>Medication schedule</h2>
      </div>
      {snap.meds.schedule.map((m) => (
        <div className="dose" key={m.id}>
          <div className="pill" style={{ background: m.color }}>
            {m.name.slice(0, 2)}
          </div>
          <div className="info">
            <b>
              {m.name} <span className="muted small">{m.dose}</span>
            </b>
            <span className="small muted">
              {m.times.join(', ')} · {m.purpose || m.instructions}
            </span>
          </div>
          <button
            className="btn small ghost"
            onClick={() => api.removeMed(m.id)}
            aria-label={`Remove ${m.name}`}
          >
            Remove
          </button>
        </div>
      ))}
      <div className="row" style={{ marginTop: 10 }}>
        <input
          aria-label="Medicine name"
          placeholder="Medicine"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={inputStyle}
        />
        <input
          aria-label="Dose"
          placeholder="Dose"
          value={dose}
          onChange={(e) => setDose(e.target.value)}
          style={{ ...inputStyle, width: 90 }}
        />
        <input
          aria-label="Time"
          placeholder="08:00, 20:00"
          value={time}
          onChange={(e) => setTime(e.target.value)}
          style={{ ...inputStyle, flex: 'none', width: 120 }}
          title="One or more times, separated by commas (24-hour)"
        />
        <input
          aria-label="Instructions"
          placeholder="Instructions (e.g. with food)"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          style={inputStyle}
        />
        <input
          aria-label="Purpose"
          placeholder="What it's for (from doctor)"
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
          style={inputStyle}
        />
        <button className="btn primary small" onClick={add}>
          Add
        </button>
      </div>
    </>
  )
}
const COLORS = ['#5b8def', '#f2a541', '#47b39d', '#9b6ce8', '#e8655f', '#3aa0b8']

function ProfileEditor({ snap }: { snap: Snapshot }) {
  const [p, setP] = useState(snap.profile)
  const [saved, setSaved] = useState(false)
  useEffect(() => setP(snap.profile), [snap.profile.user_name, snap.profile.caregiver_name]) // eslint-disable-line react-hooks/exhaustive-deps
  const field = (k: keyof typeof p, label: string, placeholder: string, wide = false) => (
    <label
      className="small"
      style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: wide ? '2 1 280px' : '1 1 180px' }}
    >
      <b>{label}</b>
      <input
        aria-label={label}
        placeholder={placeholder}
        value={p[k]}
        style={{ ...inputStyle, flex: 'none' }}
        onChange={(e) => {
          setP({ ...p, [k]: e.target.value })
          setSaved(false)
        }}
      />
    </label>
  )
  return (
    <>
      <div className="card-head">
        <h2>Profile & settings</h2>
        <span className="small muted">
          Kawan only uses what you enter here; it never guesses personal details.
        </span>
      </div>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        {field('user_name', 'Name of person at home', 'e.g. Aminah')}
        {field('caregiver_name', 'Caregiver name', 'e.g. Farid (son)')}
        {field('caregiver_phone', 'Caregiver phone', 'shown in the report')}
        {field('conditions', 'Health conditions', 'e.g. type 2 diabetes, hypertension', true)}
        {field('allergies', 'Allergies', 'e.g. penicillin', true)}
        <button
          className="btn primary"
          onClick={async () => {
            await api.saveProfile(p)
            setSaved(true)
          }}
        >
          Save
        </button>
        {saved && <span className="chip ok">Saved</span>}
      </div>
    </>
  )
}

const inputStyle = {
  flex: 1,
  minWidth: 100,
  padding: '8px 10px',
  borderRadius: 10,
  border: '1px solid var(--line)',
  background: 'var(--bg)',
}

function DemoPanel({ snap }: { snap: Snapshot }) {
  const [v, setV] = useState({ hr: '', spo2: '', sys: '', dia: '' })
  const post = () => {
    const body = Object.fromEntries(
      Object.entries(v)
        .filter(([, x]) => x !== '')
        .map(([k, x]) => [k, Number(x)]),
    )
    if (Object.keys(body).length)
      api.vitals({ ...body, source: 'manual' }).catch(() => alert('Reading out of range'))
  }
  return (
    <>
      <div className="card-head">
        <h2>Demo & simulation panel</h2>
        <span className="chip info">Runs through the REAL detection pipeline</span>
        <div className="spacer" />
        {snap.demo.running && (
          <button className="btn small" onClick={() => api.demoStop()}>
            Stop demo
          </button>
        )}
        <button
          className="btn small ghost"
          onClick={() => confirm('Clear all events, alerts and history?') && api.reset()}
        >
          Reset all data
        </button>
      </div>
      <div className="demo-grid">
        {Object.entries(snap.demo.scenarios).map(([k, label]) => (
          <button
            key={k}
            className={`btn ${snap.demo.running === k ? 'primary' : ''}`}
            onClick={() => api.demo(k)}
            data-testid={`demo-${k}`}
          >
            ▶ {label}
          </button>
        ))}
      </div>
      <div className="row" style={{ marginTop: 14 }}>
        <span className="small muted" style={{ fontWeight: 800 }}>
          Post a device reading:
        </span>
        {(['hr', 'spo2', 'sys', 'dia'] as const).map((k) => (
          <input
            key={k}
            aria-label={k}
            placeholder={k.toUpperCase()}
            value={v[k]}
            onChange={(e) => setV({ ...v, [k]: e.target.value })}
            inputMode="numeric"
            style={{ ...inputStyle, flex: 'none', width: 80 }}
          />
        ))}
        <button className="btn small" onClick={post}>
          Send to /api/vitals
        </button>
      </div>
    </>
  )
}
