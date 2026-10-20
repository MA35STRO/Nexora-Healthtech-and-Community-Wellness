import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Insights, Vitals } from '../api'

const AXIS = { stroke: 'var(--ink-3)', fontSize: 11 }
const tip = { contentStyle: { background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 10, color: 'var(--ink)' } }
const hhmmss = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const day = (d: string) => new Date(d + 'T00:00').toLocaleDateString([], { weekday: 'short' })

export function VitalsChart({ history }: { history: Vitals[] }) {
  const data = history.map((r) => ({ ...r, time: hhmmss(r.t) }))
  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />
          <XAxis dataKey="time" tick={AXIS} minTickGap={40} />
          <YAxis yAxisId="hr" domain={[40, 160]} tick={AXIS} />
          <YAxis yAxisId="o2" orientation="right" domain={[80, 100]} tick={AXIS} />
          <Tooltip {...tip} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine yAxisId="o2" y={92} stroke="var(--danger)" strokeDasharray="4 4" />
          <Line yAxisId="hr" type="monotone" dataKey="hr" name="Heart rate (bpm)" stroke="#e8655f" dot={false} strokeWidth={2} isAnimationActive={false} />
          <Line yAxisId="o2" type="monotone" dataKey="spo2" name="SpO2 (%)" stroke="#3a8ee8" dot={false} strokeWidth={2} isAnimationActive={false} />
          <Line yAxisId="hr" type="monotone" dataKey="sys" name="Systolic (mmHg)" stroke="#9b6ce8" dot={false} strokeWidth={1.5} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function AdherenceChart({ data }: { data: Insights['adherence'] }) {
  const rows = data.days.map((d) => ({ ...d, day: day(d.date) }))
  return (
    <div style={{ height: 200 }}>
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="day" tick={AXIS} />
          <YAxis allowDecimals={false} tick={AXIS} />
          <Tooltip {...tip} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="taken" name="Taken" stackId="a" fill="#2f9a5b" radius={[0, 0, 4, 4]} />
          <Bar dataKey="missed" name="Missed" stackId="a" fill="#d23f3f" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function WellnessChart({ data }: { data: Insights['wellness'] }) {
  const rows = data.map((w) => ({ ...w, day: new Date(w.t * 1000).toLocaleDateString([], { weekday: 'short', day: 'numeric' }) }))
  return (
    <div style={{ height: 200 }}>
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />
          <XAxis dataKey="day" tick={AXIS} />
          <YAxis domain={[0, 10]} tick={AXIS} />
          <Tooltip {...tip} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="mood" name="Mood (1–5)" stroke="#138a80" strokeWidth={2} />
          <Line type="monotone" dataKey="pain" name="Pain (0–10)" stroke="#d23f3f" strokeWidth={2} />
          <Line type="monotone" dataKey="sleep_h" name="Sleep (h)" stroke="#3a6fd8" strokeWidth={2} strokeDasharray="4 3" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ActivityHeatmap({ data }: { data: Insights['activity'] }) {
  const max = Math.max(10, ...data.flatMap((d) => d.active_min))
  return (
    <div className="heat" role="img" aria-label="Active minutes per hour over the last week">
      <div />
      {Array.from({ length: 24 }, (_, h) => (
        <div key={h} className="lbl" style={{ justifyContent: 'center' }}>{h % 3 === 0 ? h : ''}</div>
      ))}
      {data.map((d) => (
        <Row key={d.date} label={`${day(d.date)}${d.simulated ? '*' : ''}`} values={d.active_min} max={max} />
      ))}
    </div>
  )
}

function Row({ label, values, max }: { label: string; values: number[]; max: number }) {
  return (
    <>
      <div className="lbl">{label}</div>
      {values.map((v, h) => (
        <div
          key={h}
          className="cell"
          title={`${h}:00 — ${v} active min`}
          style={v > 0 ? { background: `color-mix(in srgb, var(--brand) ${Math.round(15 + (85 * v) / max)}%, var(--bg-2))` } : undefined}
        />
      ))}
    </>
  )
}
