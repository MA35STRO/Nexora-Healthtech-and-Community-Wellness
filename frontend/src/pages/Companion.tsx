import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtTime, type Snapshot } from '../api'
import { IconAlert, IconCamera, IconCheck, IconClipboard, IconMic, IconPill, IconSend, IconSpeaker } from '../components/icons'
import { TopBar } from '../components/Layout'
import { Mascot, type Mood } from '../components/Mascot'
import { VitalsEntry } from '../components/VitalsEntry'
import { WellnessModal } from '../components/WellnessModal'
import { STATUS_LABEL, t, type Lang } from '../i18n'
import { useCamera } from '../perception/useCamera'
import { canListen, canSpeak, useVoice } from '../voice/useVoice'

function load(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    return v === null ? fallback : v === '1'
  } catch {
    return fallback
  }
}
function save(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
}

export function Companion({ snap, connected }: { snap: Snapshot | null; connected: boolean }) {
  const [lang, setLang] = useState<Lang>('en')
  const [privacy, setPrivacy] = useState(() => load('kw-privacy', false))
  const [voiceOn, setVoiceOn] = useState(false)   // needs a tap each visit (browser autoplay rules)
  const [handsFree, setHandsFree] = useState(() => load('kw-handsfree', false))
  const [text, setText] = useState('')
  const [wellnessOpen, setWellnessOpen] = useState(false)
  const [pillMsg, setPillMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(Date.now() / 1000)
  const cam = useCamera(privacy)
  const chatRef = useRef<HTMLDivElement>(null)
  const spoken = useRef<number | null>(null)
  const offset = useRef(0)

  useEffect(() => save('kw-privacy', privacy), [privacy])
  useEffect(() => save('kw-handsfree', handsFree), [handsFree])
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 500)
    return () => clearInterval(id)
  }, [])
  useEffect(() => {
    if (snap) offset.current = snap.server_time - Date.now() / 1000
  }, [snap])
  useEffect(() => {
    if (snap?.lang) setLang(snap.lang)
  }, [snap?.lang])

  const awaiting = snap?.state === 'check_in'
  const send = async (msg: string) => {
    const m = msg.trim()
    if (!m) return
    setText('')
    setBusy(true)
    try {
      const r = await api.chat(m)
      if (r.action === 'open_wellness') setWellnessOpen(true)
    } finally {
      setBusy(false)
    }
  }
  const voice = useVoice({ lang, enabled: voiceOn, handsFree, awaitingAnswer: awaiting, onCommand: send })

  // speak each new assistant message once
  const lastAssistant = useMemo(() => [...(snap?.chat ?? [])].reverse().find((m) => m.from === 'assistant'), [snap?.chat])
  useEffect(() => {
    if (!snap) return
    const newest = snap.chat.length ? snap.chat[snap.chat.length - 1].id : 0
    if (spoken.current === null) {
      spoken.current = newest   // don't read out history on page load
      return
    }
    for (const m of snap.chat) {
      if (m.id > spoken.current && m.from === 'assistant') voice.speak(m.text)
    }
    spoken.current = Math.max(spoken.current, newest)
  }, [snap, voice])

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' })
  }, [snap?.chat.length])

  const state = snap?.state ?? 'monitoring'
  const recentTaken = snap?.meds.today.some((d) => d.taken_t && now + offset.current - d.taken_t < 15)
  const mood: Mood =
    state === 'escalated' ? 'alert'
      : voice.speaking ? 'speaking'
        : state === 'check_in' ? 'concerned'
          : voice.listening && (handsFree || awaiting) ? 'listening'
            : recentTaken ? 'happy' : 'calm'

  const deadline = snap?.checkin_deadline
  const remaining = deadline ? Math.max(0, deadline - (now + offset.current)) : 0
  const total = snap?.config.checkin_timeout_s ?? 20
  const bubbleKind = state === 'escalated' ? 'alert' : state === 'check_in' ? 'checkin' : lastAssistant?.kind === 'reminder' ? 'reminder' : ''
  const name = snap?.profile.user_name ? ` ${snap.profile.user_name}` : ''
  const bubbleText = state === 'check_in' && snap?.pending_prompt ? snap.pending_prompt : lastAssistant?.text ??
    (lang === 'ms' ? `Hai${name}! Saya Kawan. Saya ada di sini.` : `Hi${name}! I'm Kawan. I'm right here with you.`)
  const needsSetup = snap && !snap.profile.user_name && snap.meds.schedule.length === 0

  const pillCheck = async () => {
    const img = cam.captureFrame()
    if (!img) return setPillMsg('Camera is not ready yet.')
    setPillMsg(lang === 'ms' ? 'Sedang membaca label…' : 'Reading the label…')
    try {
      const r = await api.pillCheck(img)
      setPillMsg(r.medicine ? `${r.medicine}${r.matches ? ` ✓ ${r.matches}` : ''} — ${r.note}` : r.note)
    } catch {
      setPillMsg('Pill check failed.')
    }
  }

  const v = snap?.vitals.latest
  // most recent value of each measure (a BP-only reading shouldn't blank out the last oxygen reading)
  const last: Partial<Record<'hr' | 'spo2' | 'sys' | 'dia' | 'temp', number>> = {}
  for (const r of snap?.vitals.history ?? []) {
    for (const k of ['hr', 'spo2', 'sys', 'dia', 'temp'] as const) if (r[k] != null) last[k] = r[k]
  }
  const live = snap?.live
  const camLabel = cam.status === 'live'
    ? cam.server?.person ? `${cam.server.posture} · ${cam.server.torso_angle}°` : 'no person in view'
    : cam.status.replace('-', ' ')

  return (
    <>
      <TopBar connected={connected}>
        <div className="row">
          <button className="btn small" onClick={() => setLang(lang === 'en' ? 'ms' : 'en')} aria-label="Switch language">
            {lang === 'en' ? 'BM' : 'EN'}
          </button>
          {canSpeak && (
            <button className={`btn small ${voiceOn ? 'primary' : ''}`} onClick={() => {
              setVoiceOn(!voiceOn)
              if (!voiceOn && canListen) setHandsFree(true)   // voice on = Kawan talks AND listens for "Hey Kawan"
              if (!voiceOn && lastAssistant) setTimeout(() => voice.speak(lastAssistant.text), 50)
            }}>
              <IconSpeaker size={16} /> {voiceOn ? t('voiceOn', lang) : t('voiceOff', lang)}
            </button>
          )}
        </div>
      </TopBar>

      <main className="page grid companion">
        {needsSetup && (
          <section className="card welcome" style={{ gridColumn: '1 / -1' }} data-testid="welcome">
            <b>{lang === 'ms' ? 'Selamat datang ke Kawan! 👋' : 'Welcome to Kawan! 👋'}</b>{' '}
            {lang === 'ms'
              ? 'Tetapkan nama anda, penjaga dan ubat-ubatan di halaman Penjaga, atau baca panduan ringkas dahulu.'
              : 'Set up your name, caregiver and medicines on the Caregiver page, or read the short guide first.'}
            <div className="row" style={{ marginTop: 10 }}>
              <Link className="btn small primary" to="/guide">{lang === 'ms' ? 'Cara guna' : 'How to use'}</Link>
              <Link className="btn small" to="/caregiver#setup">{lang === 'ms' ? 'Tetapan' : 'Set up now'}</Link>
            </div>
          </section>
        )}
        <div className="stack">
          <section className="card">
            <div className="hero">
              <Mascot mood={mood} size={200} />
              <div>
                <div className="status-line">
                  <span className={`chip ${state === 'monitoring' ? 'ok' : state === 'escalated' ? 'danger' : 'warn'}`}>
                    <span className="dot pulse" /> {t(state, lang)}
                  </span>
                  {snap?.demo.running && <span className="chip info">SIMULATION</span>}
                  {voice.listening && (handsFree || awaiting) && <span className="chip brand"><IconMic size={14} /> {t('listening', lang)}</span>}
                </div>
                <div className={`bubble ${bubbleKind}`} aria-live="polite">{bubbleText}</div>
                {deadline && remaining > 0 && (
                  <>
                    <div className="countdown"><div style={{ width: `${(remaining / total) * 100}%` }} /></div>
                    <div className="small muted" style={{ marginTop: 4 }}>
                      {t('replyIn', lang)} {Math.ceil(remaining)}s
                    </div>
                  </>
                )}
                {voiceOn && (
                  <div className="small" style={{ marginTop: 8 }} data-testid="mic-status">
                    {voice.error ? (
                      <span style={{ color: 'var(--danger)', fontWeight: 700 }}>🎙 {voice.error}</span>
                    ) : !canListen ? (
                      <span className="muted">🎙 This browser can't listen — use Chrome or Edge, or the buttons below.</span>
                    ) : voice.listening ? (
                      <span className="muted">
                        🎙 {lang === 'ms' ? 'Sebut' : 'Say'} <b>“Hey Kawan, …”</b>
                        {voice.heard && <> · {lang === 'ms' ? 'dengar' : 'heard'}: “{voice.heard}”</>}
                      </span>
                    ) : voice.speaking ? null : (
                      <span className="muted">🎙 {handsFree ? (lang === 'ms' ? 'Memulakan mikrofon…' : 'Starting microphone…') : (lang === 'ms' ? 'Tekan Cakap untuk bercakap' : 'Tap Talk to speak')}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="big-actions" aria-label="Quick actions">
            <button className="big-btn ok" onClick={() => send(lang === 'ms' ? 'Saya okay' : "I'm okay")}><IconCheck /> {t('imOkay', lang)}</button>
            <button className="big-btn help" onClick={() => send(lang === 'ms' ? 'Tolong' : 'Help')}><IconAlert /> {t('help', lang)}</button>
            <button className="big-btn med" onClick={() => api.takeMed()}><IconPill /> {t('tookMed', lang)}</button>
            {canListen ? (
              <button className={`big-btn talk ${voice.listening ? 'on' : ''}`} onClick={() => {
                if (!voiceOn) setVoiceOn(true)
                voice.pushToTalk()
              }}>
                <IconMic /> {voice.listening ? t('listening', lang) : t('talk', lang)}
              </button>
            ) : (
              <button className="big-btn talk" onClick={() => setWellnessOpen(true)}><IconClipboard /> {t('dailyCheckin', lang)}</button>
            )}
          </section>

          <section className="card">
            <div className="card-head">
              <h2>Kawan</h2>
              <span className={`chip ${snap?.ai.online ? 'brand' : ''}`} title={snap?.ai.model ?? 'offline knowledge base'}>
                {snap?.ai.online ? 'Claude AI' : 'Offline knowledge'}
              </span>
              <div className="spacer" />
              {canListen && (
                <label className="toggle small">
                  <input type="checkbox" checked={handsFree} onChange={(e) => {
                    setHandsFree(e.target.checked)
                    if (e.target.checked) setVoiceOn(true)
                  }} />
                  {t('handsFree', lang)}
                </label>
              )}
            </div>
            <div className="chat" ref={chatRef}>
              {(snap?.chat ?? []).map((m) => (
                <div key={m.id} className={`msg ${m.from} ${m.kind}`}>
                  {m.text}
                  {m.refs && m.refs.length > 0 && (
                    <div className="refs">📖 {lang === 'ms' ? 'Sumber' : 'Source'}: {m.refs.map((r) => r.source).join(' · ')}</div>
                  )}
                  <div className="meta">{fmtTime(m.t)}{m.source === 'claude' ? ' · Claude AI' : m.source === 'offline' ? ' · offline library' : ''}</div>
                </div>
              ))}
            </div>
            <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text) }}>
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder={t('typeHere', lang)} aria-label="Message Kawan" />
              <button className="btn primary" disabled={busy || !text.trim()} aria-label={t('send', lang)}><IconSend size={18} /></button>
            </form>
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <div className="card-head">
              <IconCamera size={18} />
              <h2>{t('camera', lang)}</h2>
              <div className="spacer" />
              <label className="toggle">
                <input type="checkbox" checked={privacy} onChange={(e) => setPrivacy(e.target.checked)} />
                {t('privacy', lang)}
              </label>
            </div>
            <div className="cam" data-testid="camera">
              <video ref={cam.videoRef} muted playsInline className={privacy ? 'hidden' : ''} />
              <canvas ref={cam.canvasRef} />
              <div className="cam-overlay">
                <span className={`chip ${cam.status === 'live' ? 'ok' : cam.status === 'denied' || cam.status === 'error' ? 'danger' : 'warn'}`} data-testid="cam-status">
                  <span className={`dot ${cam.status === 'live' ? 'pulse' : ''}`} /> {cam.status === 'live' ? 'LIVE' : cam.status.toUpperCase().replace('-', ' ')}
                </span>
                <span className="chip">{camLabel}</span>
                {cam.status === 'live' && <span className="chip">{cam.fps} fps</span>}
              </div>
              {cam.status !== 'live' && cam.error && <div className="cam-msg">{cam.error}</div>}
              {(cam.status === 'starting' || cam.status === 'loading-model') && !cam.error && (
                <div className="cam-msg">{cam.status === 'starting' ? 'Opening your camera…' : 'Loading the on-device pose model…'}</div>
              )}
            </div>
            <p className="tiny muted" style={{ margin: '8px 0 0' }}>🔒 {t('privacyNote', lang)}</p>
            {live?.source === 'demo' && <p className="tiny" style={{ margin: '4px 0 0' }}>Demo running: camera input paused.</p>}
          </section>

          <section className="card">
            <div className="card-head">
              <IconPill size={18} />
              <h2>{t('medsToday', lang)}</h2>
              <div className="spacer" />
              <button className="btn small" onClick={pillCheck} disabled={cam.status !== 'live'} title={t('checkMedHint', lang)}>
                <IconCamera size={16} /> {t('checkMed', lang)}
              </button>
            </div>
            {pillMsg && <p className="small" style={{ marginTop: 0 }}>{pillMsg}</p>}
            {snap?.meds.today.length ? snap.meds.today.map((d) => (
              <div className="dose" key={d.id}>
                <div className="pill" style={{ background: d.color }}>{d.name.slice(0, 2)}</div>
                <div className="info">
                  <b>{d.name} <span className="muted small">{d.dose}</span></b>
                  <span className="small muted">{fmtTime(d.due_t)} · {d.instructions}</span>
                </div>
                <span className={`chip ${d.status === 'taken' ? 'ok' : d.status === 'missed' ? 'danger' : d.status === 'due' ? 'warn' : ''}`}>
                  {STATUS_LABEL[d.status]}
                </span>
                {(d.status === 'due' || d.status === 'snoozed') && (
                  <button className="btn small primary" onClick={() => api.takeMed(d.med_id)}>Take</button>
                )}
              </div>
            )) : (
              <p className="muted">
                {t('noMeds', lang)}
                {snap?.meds.next && <><br />{lang === 'ms' ? 'Seterusnya' : 'Next'}: <b>{snap.meds.next.name} {snap.meds.next.dose}</b> · {new Date(snap.meds.next.due_t * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })}</>}
              </p>
            )}
          </section>

          <section className="card">
            <div className="card-head">
              <h2>{t('vitals', lang)}</h2>
              {v?.source === 'simulated' && <span className="chip info">{t('simulated', lang)}</span>}
              <div className="spacer" />
              <button className="btn small" onClick={() => setWellnessOpen(true)}><IconClipboard size={16} /> {t('dailyCheckin', lang)}</button>
            </div>
            {v ? (
              <>
                <div className="vitals">
                  <div className={`vital ${last.hr && (last.hr > 120 || last.hr < 45) ? 'bad' : ''}`}><div className="u">HEART</div><div className="v">{last.hr ?? '–'}</div><div className="u">bpm</div></div>
                  <div className={`vital ${last.spo2 && last.spo2 < 92 ? 'bad' : ''}`}><div className="u">OXYGEN</div><div className="v">{last.spo2 ?? '–'}</div><div className="u">% SpO2</div></div>
                  <div className={`vital ${last.sys && last.sys >= 180 ? 'bad' : ''}`}><div className="u">BLOOD PRESSURE</div><div className="v">{last.sys ? `${last.sys}/${last.dia}` : '–'}</div><div className="u">mmHg</div></div>
                  <div className={`vital ${last.temp && last.temp >= 38.5 ? 'bad' : ''}`}><div className="u">TEMP</div><div className="v">{last.temp ?? '–'}</div><div className="u">°C</div></div>
                </div>
                <p className="tiny muted" style={{ margin: '6px 0 0' }}>
                  {lang === 'ms' ? 'Bacaan terakhir' : 'Last reading'}: {fmtTime(v.t)} · {v.source === 'simulated' ? t('simulated', lang) : v.source === 'manual' ? (lang === 'ms' ? 'dimasukkan sendiri' : 'entered by you') : v.source}
                </p>
              </>
            ) : (
              <p className="muted small" style={{ marginTop: 0 }}>
                {lang === 'ms' ? 'Tiada bacaan lagi. Masukkan bacaan daripada mesin tekanan darah, oksimeter atau termometer anda.'
                  : 'No readings yet. Enter a reading from your blood pressure monitor, oximeter or thermometer.'}
              </p>
            )}
            <details style={{ marginTop: 10 }} open={!v}>
              <summary className="small" style={{ cursor: 'pointer', fontWeight: 800 }}>{lang === 'ms' ? '+ Tambah bacaan' : '+ Add a reading'}</summary>
              <VitalsEntry lang={lang} />
            </details>
          </section>
        </div>
      </main>
      <footer className="disclaimer">{t('disclaimer', lang)}</footer>
      {wellnessOpen && <WellnessModal lang={lang} onClose={() => setWellnessOpen(false)} onDone={() => undefined} />}
    </>
  )
}
