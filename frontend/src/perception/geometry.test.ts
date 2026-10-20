import { describe, expect, it } from 'vitest'
import { motionScore, pack, shouldProcess } from './geometry'
import { isCheckinAnswer, matchWake } from '../voice/wake'

describe('pack', () => {
  it('rounds and defaults visibility', () => {
    expect(pack([{ x: 0.123456, y: 0.98765, visibility: 0.5 }, { x: 1, y: 0 }])).toEqual([
      [0.1235, 0.9877, 0.5],
      [1, 0, 1],
    ])
  })
})

describe('motionScore', () => {
  const a = pack([{ x: 0.1, y: 0.1, visibility: 1 }, { x: 0.5, y: 0.5, visibility: 1 }])
  it('is null for the first frame', () => expect(motionScore(null, a)).toBeNull())
  it('averages displacement of visible points', () => {
    const b = pack([{ x: 0.13, y: 0.14, visibility: 1 }, { x: 0.5, y: 0.5, visibility: 1 }])
    expect(motionScore(a, b)).toBeCloseTo(0.025, 6)
  })
  it('ignores low-visibility (guessed) points', () => {
    const b = pack([{ x: 0.9, y: 0.9, visibility: 0.1 }, { x: 0.5, y: 0.5, visibility: 1 }])
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

describe('matchWake', () => {
  it.each([
    ['Hey Kawan, what is metformin?', 'what is metformin?'],
    ['hai kawan saya sakit', 'saya sakit'],
    ['kawan', ''],
    ['OK Cowan remind me later', 'remind me later'],
  ])('%s', (said, cmd) => {
    expect(matchWake(said)).toEqual({ woke: true, command: cmd })
  })
  it('does not wake on other speech', () => {
    expect(matchWake('my friend kawan is here').woke).toBe(false)
    expect(matchWake('hello there').woke).toBe(false)
  })
})

describe('isCheckinAnswer', () => {
  it('accepts short okay / help replies', () => {
    expect(isCheckinAnswer("I'm okay")).toBe(true)
    expect(isCheckinAnswer('tolong')).toBe(true)
    expect(isCheckinAnswer('the weather is nice')).toBe(false)
  })
})
