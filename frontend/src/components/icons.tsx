// Small inline icons (stroke style) so the app needs no icon font and works offline.
type P = { size?: number }
const base = (size = 22) => ({
  width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
  strokeWidth: 2.2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true,
})

export const IconCheck = ({ size }: P) => <svg {...base(size)}><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
export const IconAlert = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 3l9.5 17h-19z" /><path d="M12 10v4" /><path d="M12 17.5v.01" /></svg>
)
export const IconPill = ({ size }: P) => (
  <svg {...base(size)}><rect x="3" y="8.5" width="18" height="7" rx="3.5" transform="rotate(-35 12 12)" /><path d="M9.5 8.3l5 7.4" /></svg>
)
export const IconMic = ({ size }: P) => (
  <svg {...base(size)}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0" /><path d="M12 18v3" /></svg>
)
export const IconSend = ({ size }: P) => <svg {...base(size)}><path d="M4 12l16-8-6 16-3-7z" /></svg>
export const IconSpeaker = ({ size }: P) => (
  <svg {...base(size)}><path d="M4 9h4l5-4v14l-5-4H4z" /><path d="M16.5 8.5a5 5 0 0 1 0 7" /><path d="M19 6a8.5 8.5 0 0 1 0 12" /></svg>
)
export const IconHeart = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 20s-7-4.4-9-9a4.8 4.8 0 0 1 9-3 4.8 4.8 0 0 1 9 3c-2 4.6-9 9-9 9z" /></svg>
)
export const IconCamera = ({ size }: P) => (
  <svg {...base(size)}><path d="M4 8h3l2-2.5h6L17 8h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg>
)
export const IconClipboard = ({ size }: P) => (
  <svg {...base(size)}><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4h6v3H9z" /><path d="M9 12h6M9 16h4" /></svg>
)
export const IconPrint = ({ size }: P) => (
  <svg {...base(size)}><path d="M7 9V3h10v6" /><rect x="3" y="9" width="18" height="8" rx="2" /><path d="M7 14h10v7H7z" /></svg>
)
export const IconBell = ({ size }: P) => (
  <svg {...base(size)}><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>
)
