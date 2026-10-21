import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 40 40" aria-hidden>
      <path d="M20 6c11 0 15 7 15 16s-7 14-15 14S5 31 5 22 9 6 20 6z" fill="#1f9e93" />
      <rect x="11" y="15" width="18" height="13" rx="6.5" fill="#0d2b2d" />
      <ellipse cx="16.5" cy="21.5" rx="1.8" ry="2.2" fill="#7fe3d0" />
      <ellipse cx="23.5" cy="21.5" rx="1.8" ry="2.2" fill="#7fe3d0" />
      <path
        d="M20 5.5c-1-1.6-3.4-1-2.7.9.5 1.2 2.7 2.4 2.7 2.4s2.2-1.2 2.7-2.4c.7-1.9-1.7-2.5-2.7-.9z"
        fill="#ff8fa3"
      />
    </svg>
  )
}

export function TopBar({ children, connected }: { children?: ReactNode; connected: boolean }) {
  return (
    <>
      {!connected && <div className="offline-bar">Reconnecting to the Kawan hub…</div>}
      <header className="topbar">
        <NavLink to="/" className="brand">
          <BrandMark />
          <span>
            <b>Kawan</b>
            <small>AI Guardian for Independent Living</small>
          </span>
        </NavLink>
        <nav className="nav">
          <NavLink to="/" end>
            Companion
          </NavLink>
          <NavLink to="/caregiver">Caregiver</NavLink>
          <NavLink to="/report">Report</NavLink>
          <NavLink to="/guide">How to use</NavLink>
        </nav>
        <div className="spacer" />
        {children}
      </header>
    </>
  )
}
