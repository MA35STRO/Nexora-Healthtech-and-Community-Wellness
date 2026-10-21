export type Lang = 'en' | 'ms'

const S = {
  tagline: { en: 'Your home health companion', ms: 'Peneman kesihatan di rumah' },
  monitoring: { en: 'All good — I’m keeping you company', ms: 'Semua baik — saya menemani anda' },
  check_in: { en: 'Checking on you…', ms: 'Sedang memeriksa anda…' },
  attention: { en: 'Your caregiver has been informed', ms: 'Penjaga anda telah dimaklumkan' },
  escalated: { en: 'Help is being requested', ms: 'Bantuan sedang diminta' },
  imOkay: { en: "I'm okay", ms: 'Saya okay' },
  help: { en: 'Help', ms: 'Tolong' },
  tookMed: { en: 'I took my medicine', ms: 'Saya sudah makan ubat' },
  talk: { en: 'Talk', ms: 'Cakap' },
  listening: { en: 'Listening…', ms: 'Mendengar…' },
  typeHere: {
    en: 'Ask me anything, e.g. "What is metformin for?"',
    ms: 'Tanya apa sahaja, cth. "Apa itu darah tinggi?"',
  },
  send: { en: 'Send', ms: 'Hantar' },
  medsToday: { en: 'Today’s medicines', ms: 'Ubat hari ini' },
  checkMed: { en: 'Check my medicine', ms: 'Semak ubat saya' },
  checkMedHint: { en: 'Hold the box or label up to the camera', ms: 'Tunjukkan kotak atau label ke kamera' },
  vitals: { en: 'My readings', ms: 'Bacaan saya' },
  simulated: { en: 'SIMULATED', ms: 'SIMULASI' },
  dailyCheckin: { en: 'Daily check-in', ms: 'Semakan harian' },
  camera: { en: 'Guardian camera', ms: 'Kamera penjaga' },
  privacy: { en: 'Privacy mode', ms: 'Mod privasi' },
  privacyNote: {
    en: 'Video stays on this device. Only body-pose points are analysed.',
    ms: 'Video kekal pada peranti ini. Hanya titik postur badan dianalisis.',
  },
  voiceOn: { en: 'Voice on', ms: 'Suara hidup' },
  voiceOff: { en: 'Turn on voice', ms: 'Hidupkan suara' },
  handsFree: { en: '“Hey Kawan” listening', ms: 'Dengar “Hai Kawan”' },
  disclaimer: {
    en: 'Kawan is a prototype safety companion, not a medical device and not a doctor. In an emergency call 999.',
    ms: 'Kawan ialah prototaip peneman keselamatan, bukan peranti perubatan dan bukan doktor. Kecemasan, hubungi 999.',
  },
  replyIn: { en: 'Please reply within', ms: 'Sila balas dalam' },
  noMeds: { en: 'No medicines scheduled today', ms: 'Tiada ubat dijadualkan hari ini' },
  mood: { en: 'How is your mood?', ms: 'Bagaimana perasaan anda?' },
  pain: { en: 'Any pain? (0 = none, 10 = worst)', ms: 'Ada sakit? (0 = tiada, 10 = paling teruk)' },
  sleep: { en: 'Hours of sleep last night', ms: 'Jam tidur malam tadi' },
  symptoms: { en: 'Anything you’re feeling today?', ms: 'Apa yang anda rasa hari ini?' },
  note: { en: 'Anything else? (optional)', ms: 'Lain-lain? (pilihan)' },
  submit: { en: 'Submit check-in', ms: 'Hantar semakan' },
  close: { en: 'Close', ms: 'Tutup' },
} as const

export type Key = keyof typeof S

export function t(key: Key, lang: Lang): string {
  return S[key][lang]
}

export const STATUS_LABEL: Record<string, string> = {
  upcoming: 'Upcoming',
  due: 'Due now',
  snoozed: 'Snoozed',
  taken: 'Taken',
  missed: 'Missed',
}
