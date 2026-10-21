import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { useSnapshot } from './api'
import { Caregiver } from './pages/Caregiver'
import { Companion } from './pages/Companion'
import { Guide } from './pages/Guide'
import { Report } from './pages/Report'

export default function App() {
  const { snap, connected } = useSnapshot()
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Companion snap={snap} connected={connected} />} />
        <Route path="/caregiver" element={<Caregiver snap={snap} connected={connected} />} />
        <Route path="/report" element={<Report connected={connected} />} />
        <Route path="/guide" element={<Guide connected={connected} />} />
        <Route path="*" element={<Companion snap={snap} connected={connected} />} />
      </Routes>
    </BrowserRouter>
  )
}
