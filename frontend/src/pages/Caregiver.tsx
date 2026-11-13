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
import { caregiverAlarm, unlockAudio, useAlarm } from '../alarm'
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

/** Desktop notification once per new escalated alert (the looping sound is handled by useAlarm). */
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
  const [silenced, setSilenced] = useState<Set<number>>(() => new Set())
  const ringing = caregiverAlarm(snap?.incidents ?? [], silenced)
  const { blocked: soundBlocked } = useAlarm(ringing)
  const silence = () =>
    setSilenced(
      new Set([...silenced, ...(snap?.incidents ?? []).filter((i) => i.escalated).map((i) => i.id)]),
    )
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
          {ringing && (
            <button
              className="btn small danger"
              onClick={soundBlocked ? unlockAudio : silence}
              data-testid="alarm-button"
            >
              {soundBlocked ? '🔊 Tap to sound the alarm' : '🔕 Silence alarm'}
            </button>
          )}
          {perm !== 'granted' && 'Notification' in window && (
            <button
              className="btn small"
              onClick={() => {
                unlockAudio()
                Notification.requestPermission().then(setPerm)
              }}
            >
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
            {snap.notify.telegram && (
              <span className="chip info">
                Telegram alerts on · {snap.notify.telegram_recipients}{' '}
                {snap.notify.telegram_recipients === 1 ? 'caregiver' : 'caregivers'}
              </span>
            )}
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

        <section className="card span-12" id="telegram">
          <TelegramConnection snap={snap} />
        </section>

        <section className="card span-12" id="ai">
          <AIConnection snap={snap} />
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

function AIConnection({ snap }: { snap: Snapshot }) {
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const connect = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const r = await api.connectAI(key)
      setMsg({ ok: r.ok, text: r.message })
      if (r.ok) setKey('')
    } catch {
      setMsg({ ok: false, text: 'Could not reach the Kawan hub.' })
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <div className="card-head">
        <h2>AI connection (optional)</h2>
        <span className={`chip ${snap.ai.online ? 'ok' : ''}`}>
          {snap.ai.provider === 'local'
            ? `Local AI · ${snap.ai.model}`
            : snap.ai.online
              ? `Claude · ${snap.ai.model}`
              : `Offline library · ${snap.ai.topics} topics`}
        </span>
      </div>
      <p className="small" style={{ marginTop: 0 }}>
        Kawan always works offline using its built-in health library ({snap.ai.topics} topics, each with a
        source). Connecting an AI lets Kawan answer a much wider range of questions in natural English or
        Bahasa Melayu, still grounded in that library and still never deciding emergencies. Pick one:
      </p>
      <LocalAI snap={snap} />
      <h3 style={{ margin: '16px 0 6px', fontSize: '1rem' }}>Claude AI (paid API, needs internet)</h3>
      {snap.ai.provider === 'local' && (
        <p className="small muted" style={{ marginTop: 0 }}>
          The local model is in use. A saved Claude key is used only if you disconnect the local model.
        </p>
      )}
      {snap.ai.key_source === 'env' ? (
        <p className="small muted">
          Connected using the key in <code>backend/.env</code>. Edit that file to change it.
        </p>
      ) : snap.ai.key_source === 'app' ? (
        <div className="row">
          <span className="small">Your key is saved on this computer only and is never shown again.</span>
          <button className="btn small" onClick={() => api.disconnectAI()}>
            Disconnect
          </button>
        </div>
      ) : (
        <>
          <ol className="small" style={{ margin: '0 0 10px', paddingLeft: 20 }}>
            <li>
              Go to{' '}
              <a href="https://console.anthropic.com" target="_blank" rel="noreferrer">
                console.anthropic.com
              </a>{' '}
              and sign up.
            </li>
            <li>
              Open <b>Billing</b> and add a small amount of credit (each answer costs roughly a few US cents
              or less).
            </li>
            <li>
              Open <b>API keys</b> → <b>Create key</b>, then copy it (it starts with <code>sk-ant-</code>).
            </li>
            <li>Paste it below and press Connect. Kawan tests it before saving it.</li>
          </ol>
          <div className="row">
            <input
              aria-label="Claude API key"
              type="password"
              placeholder="sk-ant-..."
              value={key}
              onChange={(e) => setKey(e.target.value)}
              style={{ ...inputStyle, minWidth: 260 }}
              autoComplete="off"
            />
            <button className="btn primary" disabled={busy || !key.trim()} onClick={connect}>
              {busy ? 'Testing…' : 'Connect'}
            </button>
          </div>
          <p className="tiny muted" style={{ marginBottom: 0 }}>
            The key is stored only in this computer's Kawan database. Don't share the caregiver page publicly
            while a key is connected.
          </p>
        </>
      )}
      {msg && (
        <p className={`chip ${msg.ok ? 'ok' : 'danger'}`} style={{ whiteSpace: 'normal', marginTop: 10 }}>
          {msg.text}
        </p>
      )}
    </>
  )
}

function LocalAI({ snap }: { snap: Snapshot }) {
  const [info, setInfo] = useState<{ running: boolean; models: string[] } | null>(null)
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const active = snap.ai.provider === 'local'
  const refresh = useCallback(
    () =>
      api
        .localModels()
        .then((r) => {
          setInfo(r)
          setModel((m) => m || r.models.find((x) => x.startsWith('gemma3')) || r.models[0] || '')
        })
        .catch(() => setInfo({ running: false, models: [] })),
    [],
  )
  useEffect(() => {
    refresh()
  }, [refresh])
  const connect = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const r = await api.connectLocal(model)
      setMsg({ ok: r.ok, text: r.message })
    } catch {
      setMsg({ ok: false, text: 'Could not reach the Kawan hub.' })
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <h3 style={{ margin: '6px 0', fontSize: '1rem' }}>Local AI (free, private, works offline)</h3>
      <p className="small" style={{ marginTop: 0 }}>
        Runs a model on this computer with{' '}
        <a href="https://ollama.com" target="_blank" rel="noreferrer">
          Ollama
        </a>
        : no API key, no bill, and questions and photos never leave this computer. Answers are slower (a few
        seconds to half a minute) and simpler than Claude's, especially in Bahasa Melayu. For pill check, use
        a model that can read images, such as <code>gemma3:4b</code>.
      </p>
      {snap.ai.local_source === 'env' ? (
        <p className="small muted">
          Using <b>{snap.ai.model}</b> from <code>backend/.env</code> (OLLAMA_MODEL). Edit that file to change
          it.
        </p>
      ) : active ? (
        <div className="row">
          <span className="small">
            Using <b>{snap.ai.model}</b> on this computer.
          </span>
          <button className="btn small" onClick={() => api.disconnectLocal()}>
            Disconnect
          </button>
        </div>
      ) : info && !info.running ? (
        <div className="row">
          <span className="small">
            Ollama isn't running. Install it, open it, then run <code>ollama pull gemma3:4b</code>.
          </span>
          <button className="btn small" onClick={refresh}>
            Check again
          </button>
        </div>
      ) : info && !info.models.length ? (
        <div className="row">
          <span className="small">
            Ollama is running but has no models. In a terminal, run <code>ollama pull gemma3:4b</code>.
          </span>
          <button className="btn small" onClick={refresh}>
            Check again
          </button>
        </div>
      ) : info ? (
        <div className="row">
          <select
            aria-label="Local model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={{ ...inputStyle, flex: 'none', minWidth: 180 }}
          >
            {info.models.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
          <button className="btn primary" disabled={busy || !model} onClick={connect}>
            {busy ? 'Loading the model…' : 'Use this model'}
          </button>
        </div>
      ) : (
        <p className="small muted">Looking for Ollama…</p>
      )}
      {msg && (
        <p className={`chip ${msg.ok ? 'ok' : 'danger'}`} style={{ whiteSpace: 'normal', marginTop: 10 }}>
          {msg.text}
        </p>
      )}
    </>
  )
}

function TelegramConnection({ snap }: { snap: Snapshot }) {
  const n = snap.notify
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const run = async (fn: () => Promise<{ ok: boolean; message: string }>, after?: () => void) => {
    setBusy(true)
    setMsg(null)
    try {
      const r = await fn()
      setMsg({ ok: r.ok, text: r.message })
      if (r.ok) after?.()
    } catch {
      setMsg({ ok: false, text: 'Could not reach the Kawan hub.' })
    } finally {
      setBusy(false)
    }
  }
  const connected = n.token_source !== null
  return (
    <>
      <div className="card-head">
        <h2>Telegram alerts (optional)</h2>
        <span className={`chip ${n.telegram ? 'ok' : connected ? 'warn' : ''}`}>
          {n.telegram
            ? `On · ${n.telegram_recipients} ${n.telegram_recipients === 1 ? 'caregiver' : 'caregivers'}`
            : connected
              ? 'Bot connected · no caregiver linked yet'
              : 'Off'}
        </span>
        {connected && (
          <span className={`chip ${n.listening ? 'ok' : 'warn'}`}>
            {n.listening ? 'listening for replies' : 'not listening'}
          </span>
        )}
      </div>
      <p className="small" style={{ marginTop: 0 }}>
        Sends urgent alerts to caregivers' phones, even when the dashboard is closed. Each alert has an{' '}
        <b>“I'm on it”</b> button: tapping it acknowledges the alert here and tells the person at home that
        help has seen it. Caregivers can also send <code>/status</code> any time. Needs internet; no public
        URL or tunnel.
      </p>
      {!connected ? (
        <>
          <ol className="small" style={{ margin: '0 0 10px', paddingLeft: 20 }}>
            <li>
              In Telegram, open{' '}
              <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">
                @BotFather
              </a>{' '}
              and send <code>/newbot</code>. Pick any name (e.g. “Kawan Alerts”).
            </li>
            <li>
              BotFather replies with a token like <code>123456789:AA…</code>. Copy it.
            </li>
            <li>Paste it below and press Connect. Kawan tests it before saving it.</li>
          </ol>
          <div className="row">
            <input
              aria-label="Telegram bot token"
              type="password"
              placeholder="123456789:AA..."
              value={token}
              onChange={(e) => setToken(e.target.value)}
              style={{ ...inputStyle, minWidth: 260 }}
              autoComplete="off"
            />
            <button
              className="btn primary"
              disabled={busy || !token.trim()}
              onClick={() =>
                run(
                  () => api.connectTelegram(token),
                  () => setToken(''),
                )
              }
            >
              {busy ? 'Testing…' : 'Connect'}
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="small" style={{ marginBottom: 8 }}>
            Bot: <b>{n.bot ? `@${n.bot}` : '…'}</b>
            {n.token_source === 'env' && <span className="muted"> (token from backend/.env)</span>}
          </div>
          {n.link && (
            <div className="small" style={{ marginBottom: 10 }}>
              <b>Add a caregiver:</b> open this private link on their phone and tap <b>Start</b>. Each link
              works once, so a new one appears after someone joins.
              <div className="row" style={{ marginTop: 6 }}>
                <a className="btn small primary" href={n.link} target="_blank" rel="noreferrer">
                  Open in Telegram
                </a>
                <code style={{ wordBreak: 'break-all' }}>{n.link}</code>
                <button className="btn small ghost" onClick={() => navigator.clipboard?.writeText(n.link!)}>
                  Copy
                </button>
              </div>
            </div>
          )}
          <div className="small" style={{ fontWeight: 800 }}>
            Linked caregivers
          </div>
          {n.chats.length ? (
            n.chats.map((c) => (
              <div key={c.id} className="row" style={{ justifyContent: 'space-between', maxWidth: 520 }}>
                <span className="small">{c.name}</span>
                {!c.env && (
                  <button className="btn small ghost" onClick={() => api.removeTelegramChat(c.id)}>
                    Remove
                  </button>
                )}
              </div>
            ))
          ) : (
            <p className="small muted" style={{ margin: '4px 0' }}>
              Nobody yet. Open the link above on a caregiver's phone.
            </p>
          )}
          <div className="row" style={{ marginTop: 10 }}>
            <button
              className="btn small"
              disabled={busy || !n.chats.length}
              onClick={() => run(() => api.testTelegram())}
            >
              Send test message
            </button>
            {n.token_source === 'app' && (
              <button
                className="btn small ghost"
                onClick={() =>
                  confirm('Disconnect the Telegram bot? Caregivers will stop getting alerts.') &&
                  api.disconnectTelegram()
                }
              >
                Disconnect bot
              </button>
            )}
          </div>
          {n.error && (
            <p className="chip warn" style={{ whiteSpace: 'normal', marginTop: 10 }}>
              {n.error}
            </p>
          )}
        </>
      )}
      {msg && (
        <p className={`chip ${msg.ok ? 'ok' : 'danger'}`} style={{ whiteSpace: 'normal', marginTop: 10 }}>
          {msg.text}
        </p>
      )}
    </>
  )
}

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
