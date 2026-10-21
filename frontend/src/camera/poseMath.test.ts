import { describe, expect, it } from 'vitest'
import { motionScore, pack, shouldProcess } from './poseMath'

describe('pack', () => {
  it('rounds and defaults visibility', () => {
    expect(
      pack([
        { x: 0.123456, y: 0.98765, visibility: 0.5 },
        { x: 1, y: 0 },
      ]),
    ).toEqual([
      [0.1235, 0.9877, 0.5],
      [1, 0, 1],
    ])
  })
})

describe('motionScore', () => {
  const a = pack([
    { x: 0.1, y: 0.1, visibility: 1 },
    { x: 0.5, y: 0.5, visibility: 1 },
  ])
  it('is null for the first frame', () => expect(motionScore(null, a)).toBeNull())
  it('averages displacement of visible points', () => {
    const b = pack([
      { x: 0.13, y: 0.14, visibility: 1 },
      { x: 0.5, y: 0.5, visibility: 1 },
    ])
    expect(motionScore(a, b)).toBeCloseTo(0.025, 6)
  })
  it('ignores low-visibility (guessed) points', () => {
    const b = pack([
      { x: 0.9, y: 0.9, visibility: 0.1 },
      { x: 0.5, y: 0.5, visibility: 1 },
    ])
    expect(motionScore(a, b)).toBe(0)
  })
  it('is null when nothing is visible in both', () => {
    const hidden = pack([{ x: 0, y: 0, visibility: 0 }])
    expect(motionScore(hidden, hidden)).toBeNull()
  })
})

describe('shouldProcess', () => {
  it('throttles to the target fps', () => {
    expect(shouldProcess(1000, 990, 15)).toBe(false)
    expect(shouldProcess(1067, 1000, 15)).toBe(true)
  })
})
