import { describe, expect, it } from 'vitest'
import { isCheckinAnswer, matchWake } from './wake'

describe('matchWake', () => {
  it.each([
    ['Hey Kawan, what is metformin?', 'what is metformin?'],
    ['hai kawan saya sakit', 'saya sakit'],
    ['kawan', ''],
    ['hey Karwan what is diabetes', 'what is diabetes'],
    ['hey Kevin help', 'help'],
    ['Hey Kawaan.', ''],
    ['hey Kowan what time is my medicine', 'what time is my medicine'],
    ['hey car one tell me a joke', 'tell me a joke'],
    ['hey ka wan', ''],
    ['Hey Gawan', ''],
    // "Hey" on its own is the wake word
    ['Hey, what is metformin?', 'what is metformin?'],
    ['hey what is the weather', 'what is the weather'],
    ['Hey', ''],
    ['hai saya sakit', 'saya sakit'],
    ['Hei, bila ubat saya?', 'bila ubat saya?'],
    ['hay remind me later', 'remind me later'],
  ])('%s', (said, cmd) => {
    expect(matchWake(said)).toEqual({ woke: true, command: cmd })
  })
  it('does not wake on other speech', () => {
    expect(matchWake('my friend kawan is here').woke).toBe(false)
    expect(matchWake('hello there').woke).toBe(false)
    expect(matchWake('can you hear me').woke).toBe(false)
    expect(matchWake('they said hey to me').woke).toBe(false) // "hey" must come first
    expect(matchWake('kevin is coming over').woke).toBe(false) // near-matches need "hey" first
    expect(matchWake('hi there').woke).toBe(false) // only "hey" wakes Kawan
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
