import { describe, expect, it } from 'vitest'
import { caregiverAlarm, companionAlarm } from './alarm'

const inc = (id: number, escalated: boolean, status: 'open' | 'acknowledged' | 'resolved') =>
  ({ id, escalated, status }) as const
const snap = (state: 'monitoring' | 'check_in' | 'attention' | 'escalated', id: number | null = 1) =>
  ({ state, active_incident: id === null ? null : { id } }) as never

describe('companion alarm (person at home)', () => {
  it('is quiet when all is well', () => {
    expect(companionAlarm(null, null)).toBeNull()
    expect(companionAlarm(snap('monitoring', null), null)).toBeNull()
    expect(companionAlarm(snap('attention'), null)).toBeNull()
  })
  it('chimes while checking in and sirens once escalated', () => {
    expect(companionAlarm(snap('check_in'), null)).toBe('chime')
    expect(companionAlarm(snap('escalated'), null)).toBe('siren')
  })
  it('silencing stops the siren for that alert only', () => {
    expect(companionAlarm(snap('escalated', 1), 1)).toBeNull()
    expect(companionAlarm(snap('escalated', 2), 1)).toBe('siren') // a new alert rings again
  })
})

describe('caregiver alarm', () => {
  it('rings until an escalated alert is acknowledged', () => {
    expect(caregiverAlarm([inc(1, true, 'open')], new Set())).toBe('alarm')
    expect(caregiverAlarm([inc(1, true, 'acknowledged')], new Set())).toBeNull()
    expect(caregiverAlarm([inc(1, true, 'resolved')], new Set())).toBeNull()
  })
  it('ignores alerts that were not escalated, and silenced ones', () => {
    expect(caregiverAlarm([inc(1, false, 'open')], new Set())).toBeNull()
    expect(caregiverAlarm([inc(1, true, 'open')], new Set([1]))).toBeNull()
    expect(caregiverAlarm([inc(1, true, 'open'), inc(2, true, 'open')], new Set([1]))).toBe('alarm')
  })
})
