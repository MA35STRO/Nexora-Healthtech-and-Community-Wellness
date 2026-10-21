import { useState } from 'react'
import { Link } from 'react-router-dom'
import { TopBar } from '../components/Layout'
import type { Lang } from '../i18n'

type Block = { id: string; title: string; body: React.ReactNode }

function content(lang: Lang): { intro: string; blocks: Block[] } {
  if (lang === 'ms') {
    return {
      intro: 'Kawan ialah peneman kesihatan di rumah. Ia memerhati jika anda jatuh atau lama tidak bergerak, mengingatkan ubat, menerangkan topik kesihatan dan memaklumkan penjaga anda jika ada yang tidak kena. Kawan bukan doktor dan tidak membuat diagnosis.',
      blocks: [
        { id: 'start', title: '1. Mula dalam 3 minit (penjaga)', body: (
          <ol>
            <li>Buka halaman <Link to="/caregiver#setup">Penjaga</Link> → kad <b>Profil & tetapan</b>. Masukkan nama pengguna, nama penjaga, penyakit dan alahan. Kawan hanya menggunakan maklumat yang anda masukkan.</li>
            <li>Dalam kad <b>Jadual ubat</b>, tambah setiap ubat: nama, dos dan masa, tepat seperti pada label preskripsi.</li>
            <li>Tekan <b>Hidupkan amaran</b> di bahagian atas supaya pelayar boleh berbunyi dan memaparkan notifikasi.</li>
            <li>Letakkan komputer riba atau tablet supaya kamera nampak bilik, sebaiknya seluruh badan. Biarkan halaman <Link to="/">Peneman</Link> terbuka.</li>
          </ol>) },
        { id: 'daily', title: '2. Penggunaan harian (pengguna)', body: (
          <ul>
            <li><b>Tekan "Hidupkan suara"</b> sekali. Kawan akan bercakap dan mendengar <b>"Hai Kawan, …"</b>. Contoh: <i>"Hai Kawan, apa itu metformin?"</i></li>
            <li><b>Butang besar:</b> <b>Saya okay</b>, <b>Tolong</b> (memaklumkan penjaga segera), <b>Saya sudah makan ubat</b>, dan <b>Cakap</b>.</li>
            <li><b>Bacaan saya:</b> masukkan bacaan daripada mesin tekanan darah, oksimeter atau termometer anda. Kawan tidak mereka bacaan.</li>
            <li><b>Semakan harian:</b> sekali sehari, nyatakan perasaan, kesakitan, tidur dan simptom. Anda akan mendapat panduan (bukan diagnosis).</li>
          </ul>) },
        { id: 'alerts', title: '3. Apa berlaku apabila Kawan risau', body: (
          <ol>
            <li>Jika Kawan nampak kemungkinan jatuh, anda lama tidak bergerak, atau bacaan luar biasa, ia <b>bertanya dahulu</b>: "Anda okay?"</li>
            <li>Jawab dengan suara, butang atau taip. <b>"Saya okay"</b> → penjaga dimaklumkan dengan tahap rendah.</li>
            <li><b>"Tolong"</b>, atau <b>tiada jawapan dalam 20 saat</b> → amaran merah dihantar kepada penjaga, beserta sebabnya.</li>
            <li>Simptom bahaya seperti sakit dada, sesak nafas atau tanda strok → Kawan menyuruh anda <b>hubungi 999</b> dan terus memaklumkan penjaga.</li>
          </ol>) },
        { id: 'caregiver', title: '4. Untuk penjaga', body: (
          <ul>
            <li>Halaman <Link to="/caregiver">Penjaga</Link> menunjukkan status langsung, sebab setiap amaran, garis masa dan carta.</li>
            <li>Tekan <b>Akui</b> apabila anda menguruskan amaran, dan <b>Selesai</b> dengan nota selepas itu.</li>
            <li><Link to="/report">Laporan</Link> mengumpulkan pematuhan ubat, bacaan, simptom dan amaran untuk dibawa ke temujanji doktor (Cetak → PDF).</li>
            <li>Untuk amaran ke telefon walaupun aplikasi ditutup, sediakan bot Telegram (lihat README).</li>
          </ul>) },
        { id: 'ai', title: '5. Bertanya soalan kesihatan', body: (
          <ul>
            <li>Jawapan datang daripada perpustakaan kesihatan yang disemak, dengan <b>sumber dinyatakan</b> di bawah setiap jawapan (contohnya garis panduan KKM, WHO, NHS).</li>
            <li>Dengan kunci API Claude, jawapan lebih fleksibel tetapi tetap berpandukan perpustakaan itu. Kawan tidak mereka dos, nombor atau fakta tentang anda, dan akan berkata "saya tidak pasti" jika tidak tahu.</li>
            <li>Kawan tidak boleh menukar ubat atau dos anda. Tanya doktor atau ahli farmasi.</li>
          </ul>) },
        { id: 'privacy', title: '6. Privasi', body: (
          <ul>
            <li>Video kamera <b>tidak pernah keluar</b> dari peranti dan tidak dirakam. Hanya 33 titik postur badan dianalisis.</li>
            <li><b>Mod privasi</b> menyembunyikan video dan hanya menunjukkan rangka.</li>
            <li>Satu gambar dihantar hanya apabila anda menekan <b>Semak ubat saya</b>.</li>
          </ul>) },
        { id: 'trouble', title: '7. Masalah biasa', body: (
          <ul>
            <li><b>Kamera tidak hidup:</b> klik ikon 🔒 di bar alamat → benarkan Kamera, kemudian muat semula. Guna Chrome atau Edge.</li>
            <li><b>"Hai Kawan" tidak didengar:</b> pastikan suara hidup dan mikrofon dibenarkan; lihat teks "dengar:" di bawah gelembung. Pengecaman suara memerlukan internet. Atau tekan <b>Cakap</b>.</li>
            <li><b>Pengesanan jatuh:</b> berfungsi terbaik apabila seluruh badan kelihatan dan bilik terang. Biarkan tab kekal terbuka dan kelihatan.</li>
            <li><b>Di telefon:</b> perlukan pautan https (jalankan <kbd>tunnel.ps1</kbd> di komputer).</li>
          </ul>) },
        { id: 'demo', title: '8. Mod demo (untuk pembentangan)', body: (
          <p>Di bahagian bawah halaman Penjaga, <b>Panel demo</b> menjalankan senario simulasi (jatuh, ubat terlepas, oksigen turun…) melalui sistem pengesanan sebenar. Semua data demo dilabel <b>SIMULASI</b> dan tidak dikira dalam laporan sebenar.</p>) },
      ],
    }
  }
  return {
    intro: 'Kawan is a home health companion. It watches for falls and long periods without movement, reminds you about medicines, explains health topics, and alerts your caregiver if something seems wrong. Kawan is not a doctor and does not diagnose.',
    blocks: [
      { id: 'start', title: '1. Set up in 3 minutes (caregiver)', body: (
        <ol>
          <li>Open the <Link to="/caregiver#setup">Caregiver</Link> page and find the <b>Profile & settings</b> card. Enter the person's name, the caregiver's name, their conditions and allergies. Kawan only uses information you enter.</li>
          <li>In <b>Medication schedule</b>, add each medicine with its name, dose and time, exactly as on the prescription label.</li>
          <li>Click <b>Enable alerts</b> at the top so the browser can beep and show notifications.</li>
          <li>Place the laptop or tablet so the camera sees the room, ideally the whole body. Keep the <Link to="/">Companion</Link> page open.</li>
        </ol>) },
      { id: 'daily', title: '2. Everyday use (the person at home)', body: (
        <ul>
          <li><b>Tap "Turn on voice"</b> once. Kawan will talk and listen for <b>"Hey Kawan, …"</b>, for example <i>"Hey Kawan, what is metformin for?"</i></li>
          <li><b>Big buttons:</b> <b>I'm okay</b>, <b>Help</b> (alerts your caregiver immediately), <b>I took my medicine</b>, and <b>Talk</b>.</li>
          <li><b>My readings:</b> enter readings from your own blood pressure monitor, oximeter or thermometer. Kawan never makes readings up.</li>
          <li><b>Daily check-in:</b> once a day, share your mood, pain, sleep and symptoms. You get guidance on what kind of help to seek, never a diagnosis.</li>
        </ul>) },
      { id: 'alerts', title: '3. What happens when Kawan is worried', body: (
        <ol>
          <li>If Kawan sees a possible fall, a long time without movement, or an unusual reading, it <b>asks first</b>: "Are you okay?"</li>
          <li>Answer by voice, button or typing. <b>"I'm okay"</b> → your caregiver gets a low-priority note.</li>
          <li><b>"Help"</b>, or <b>no answer within 20 seconds</b> → a red alert goes to your caregiver, with the reasons.</li>
          <li>Danger symptoms such as chest pain, trouble breathing or stroke signs → Kawan tells you to <b>call 999</b> and alerts your caregiver straight away.</li>
        </ol>) },
      { id: 'caregiver', title: '4. For caregivers', body: (
        <ul>
          <li>The <Link to="/caregiver">Caregiver</Link> page shows live status, why each alert fired, a timeline and charts.</li>
          <li>Press <b>Acknowledge</b> when you're handling an alert, then <b>Resolve</b> with a note afterwards.</li>
          <li>The <Link to="/report">Report</Link> gathers medicine adherence, readings, symptoms and alerts to take to a doctor's appointment (Print → Save as PDF).</li>
          <li>For alerts on your phone even when the app is closed, set up a Telegram bot (see the README).</li>
        </ul>) },
      { id: 'ai', title: '5. Asking health questions', body: (
        <ul>
          <li>Answers come from a reviewed health library, with the <b>source shown under each answer</b> (for example Malaysian MOH guidelines, WHO or NHS).</li>
          <li>With a Claude API key, answers are more flexible but still grounded in that library. Kawan won't invent doses, numbers or facts about you, and says "I'm not sure" when it doesn't know.</li>
          <li>Kawan can't change your medicines or doses. Ask your doctor or pharmacist.</li>
        </ul>) },
      { id: 'privacy', title: '6. Privacy', body: (
        <ul>
          <li>Camera video <b>never leaves the device</b> and is never recorded. Only 33 body-position points are analysed.</li>
          <li><b>Privacy mode</b> hides the video and shows only a stick figure.</li>
          <li>A single photo is sent only when you tap <b>Check my medicine</b>.</li>
        </ul>) },
      { id: 'trouble', title: '7. Troubleshooting', body: (
        <ul>
          <li><b>Camera won't start:</b> click the 🔒 icon in the address bar, allow Camera, and reload. Use Chrome or Edge.</li>
          <li><b>"Hey Kawan" isn't heard:</b> make sure voice is on and the microphone is allowed, and look at the "heard:" text under the speech bubble. Speech recognition needs internet. Or press <b>Talk</b>.</li>
          <li><b>Fall detection:</b> works best with the whole body in view and a well-lit room. Keep the tab open and visible.</li>
          <li><b>On a phone:</b> needs an https link (run <kbd>tunnel.ps1</kbd> on the computer).</li>
        </ul>) },
      { id: 'demo', title: '8. Demo mode (for presentations)', body: (
        <p>At the bottom of the Caregiver page, the <b>Demo panel</b> runs simulated scenarios (a fall, a missed dose, an oxygen drop…) through the real detection system. All demo data is labelled <b>SIMULATED</b> and is never counted in real reports.</p>) },
    ],
  }
}

export function Guide({ connected }: { connected: boolean }) {
  const [lang, setLang] = useState<Lang>('en')
  const c = content(lang)
  return (
    <>
      <TopBar connected={connected}>
        <button className="btn small" onClick={() => setLang(lang === 'en' ? 'ms' : 'en')}>{lang === 'en' ? 'BM' : 'EN'}</button>
      </TopBar>
      <main className="guide" data-testid="guide">
        <h1>{lang === 'ms' ? 'Cara menggunakan Kawan' : 'How to use Kawan'}</h1>
        <p className="muted">{c.intro}</p>
        <div className="callout danger"><b>{lang === 'ms' ? 'Kecemasan? Hubungi 999.' : 'Emergency? Call 999.'}</b> {lang === 'ms' ? 'Kawan ialah prototaip, bukan peranti perubatan.' : 'Kawan is a prototype, not a medical device.'}</div>
        <nav className="toc">
          {c.blocks.map((b) => <a key={b.id} className="chip" href={`#${b.id}`}>{b.title.replace(/^\d+\.\s*/, '')}</a>)}
        </nav>
        {c.blocks.map((b) => (
          <section key={b.id} id={b.id} className="card">
            <h2>{b.title}</h2>
            {b.body}
          </section>
        ))}
      </main>
    </>
  )
}
