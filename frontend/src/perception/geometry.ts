// Pure helpers for the browser perception loop (unit-tested in geometry.test.ts).

export interface Landmark {
  x: number
  y: number
  visibility?: number
}

export type Packed = [number, number, number][]

export const VISIBLE = 0.5

/** Compact landmarks for the wire: [[x, y, visibility], ...] rounded to 4 dp. No pixels are ever sent. */
export function pack(lms: Landmark[]): Packed {
  const r = (n: number) => Math.round(n * 1e4) / 1e4
  return lms.map((l) => [r(l.x), r(l.y), r(l.visibility ?? 1)])
}

/** Mean movement of confidently-seen landmarks between two frames (same formula as the Python server). */
export function motionScore(prev: Packed | null, cur: Packed): number | null {
  if (!prev) return null
  let sum = 0
  let n = 0
  for (let i = 0; i < Math.min(prev.length, cur.length); i++) {
    const [px, py, pv] = prev[i]
    const [cx, cy, cv] = cur[i]
    if (pv >= VISIBLE && cv >= VISIBLE) {
      sum += Math.hypot(cx - px, cy - py)
      n++
    }
  }
  return n ? sum / n : null
}

/** Body skeleton edges drawn on the overlay (MediaPipe pose indices). */
export const SKELETON: [number, number][] = [
  [11, 12], [11, 23], [12, 24], [23, 24], [23, 25], [24, 26], [25, 27], [26, 28],
  [11, 13], [13, 15], [12, 14], [14, 16], [0, 11], [0, 12],
]

/** Frame throttle: true when enough time has passed since the last processed frame. */
export function shouldProcess(now: number, last: number, fps: number): boolean {
  return now - last >= 1000 / fps - 1
}
