import { describe, expect, it } from 'vitest'
import { isCheckinAnswer, matchWake } from './wake'

describe('matchWake', () => {
  it.each([
    ['Hey Kawan, what is metformin?', 'what is metformin?'],
    ['hai kawan saya sakit', 'saya sakit'],
    ['kawan', ''],
    ['OK Cowan remind me later', 'remind me later'],
    ['hey Karwan what is diabetes', 'what is diabetes'],
    ['hey Kevin help', 'help'],
    ['Hey Kawaan.', ''],
    ['hi Kowan what time is my medicine', 'what time is my medicine'],
    ['hey car one tell me a joke', 'tell me a joke'],
    ['hey ka wan', ''],
    ['Hey Gawan', ''],
  ])('%s', (said, cmd) => {
    expect(matchWake(said)).toEqual({ woke: true, command: cmd })
  })
  it('does not wake on other speech', () => {
    expect(matchWake('my friend kawan is here').woke).toBe(false)
    expect(matchWake('hello there').woke).toBe(false)
    expect(matchWake('hey what is the weather').woke).toBe(false)
    expect(matchWake('can you hear me').woke).toBe(false)
    expect(matchWake('kevin is coming over').woke).toBe(false) // near-matches need a greeting
    expect(matchWake('').woke).toBe(false)
  })
})

describe('isCheckinAnswer', () => {
  it('accepts short okay / help replies', () => {
    expect(isCheckinAnswer("I'm okay")).toBe(true)
    expect(isCheckinAnswer('tolong')).toBe(true)
    expect(isCheckinAnswer('the weather is nice')).toBe(false)
  })
})
