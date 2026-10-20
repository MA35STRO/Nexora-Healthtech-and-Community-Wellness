// "Kawan" — an original companion mascot: a soft teal lantern with a face screen and a heart-beat antenna.
export type Mood = 'calm' | 'happy' | 'listening' | 'speaking' | 'concerned' | 'alert'

const EYES: Record<Mood, { ry: number; tilt: number }> = {
  calm: { ry: 9, tilt: 0 },
  happy: { ry: 4, tilt: 0 },
  listening: { ry: 11, tilt: 0 },
  speaking: { ry: 9, tilt: 0 },
  concerned: { ry: 8, tilt: 12 },
  alert: { ry: 11, tilt: 18 },
}

export function Mascot({ mood, size = 220 }: { mood: Mood; size?: number }) {
  const e = EYES[mood]
  const glow = mood === 'alert' ? '#ff5d5d' : mood === 'concerned' ? '#ffb347' : '#7fe3d0'
  return (
    <div className={`mascot mascot-${mood}`} style={{ width: size, height: size }} aria-label={`Kawan is ${mood}`} role="img">
      <svg viewBox="0 0 200 200" width={size} height={size}>
        <defs>
          <radialGradient id="kw-body" cx="40%" cy="30%" r="75%">
            <stop offset="0%" stopColor="#5fd4c0" />
            <stop offset="60%" stopColor="#1f9e93" />
            <stop offset="100%" stopColor="#13756f" />
          </radialGradient>
          <filter id="kw-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {(mood === 'listening' || mood === 'alert') && (
          <g className="kw-rings" fill="none" stroke={glow} strokeWidth="2">
            <circle cx="100" cy="112" r="80" opacity="0.5" />
            <circle cx="100" cy="112" r="92" opacity="0.25" />
          </g>
        )}

        <g className="kw-float">
          {/* antenna with heart */}
          <line x1="100" y1="38" x2="100" y2="22" stroke="#13756f" strokeWidth="4" strokeLinecap="round" />
          <path className="kw-heart" d="M100 20 c-4 -7 -14 -4 -11 4 c2 5 11 10 11 10 c0 0 9 -5 11 -10 c3 -8 -7 -11 -11 -4z" fill={glow} filter="url(#kw-glow)" />

          {/* lantern body */}
          <path d="M100 38 C150 38 172 72 172 116 C172 158 140 182 100 182 C60 182 28 158 28 116 C28 72 50 38 100 38Z" fill="url(#kw-body)" />
          <path d="M58 60 C70 48 86 44 100 44" stroke="#bff3ea" strokeWidth="5" strokeLinecap="round" fill="none" opacity="0.6" />
          {/* little arms */}
          <ellipse cx="28" cy="128" rx="9" ry="16" fill="#1f9e93" transform="rotate(18 28 128)" />
          <ellipse cx="172" cy="128" rx="9" ry="16" fill="#1f9e93" transform={mood === 'happy' ? 'rotate(-60 172 128)' : 'rotate(-18 172 128)'} />

          {/* face screen */}
          <rect x="52" y="78" width="96" height="66" rx="30" fill="#0d2b2d" />
          <g filter="url(#kw-glow)" fill={glow}>
            <g className="kw-eye" transform={`rotate(${e.tilt} 80 108)`}>
              <ellipse cx="80" cy="108" rx="8" ry={e.ry} />
            </g>
            <g className="kw-eye" transform={`rotate(${-e.tilt} 120 108)`}>
              <ellipse cx="120" cy="108" rx="8" ry={e.ry} />
            </g>
          </g>
          {mood === 'speaking' ? (
            <ellipse className="kw-mouth-talk" cx="100" cy="130" rx="9" ry="5" fill={glow} />
          ) : mood === 'concerned' || mood === 'alert' ? (
            <path d="M88 133 Q100 126 112 133" stroke={glow} strokeWidth="3.5" strokeLinecap="round" fill="none" />
          ) : (
            <path d="M88 127 Q100 137 112 127" stroke={glow} strokeWidth="3.5" strokeLinecap="round" fill="none" />
          )}
          {/* cheeks */}
          <circle cx="62" cy="134" r="6" fill="#ff9fb1" opacity="0.45" />
          <circle cx="138" cy="134" r="6" fill="#ff9fb1" opacity="0.45" />
        </g>
      </svg>
    </div>
  )
}
