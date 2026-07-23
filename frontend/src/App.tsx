import { Route, Routes } from 'react-router-dom'
import AdminLayout from './pages/AdminLayout'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import MemoryDetail from './pages/MemoryDetail'
import Memories from './pages/Memories'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Chat />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="memories" element={<Memories />} />
        <Route path="memories/:memoryId" element={<MemoryDetail />} />
      </Route>
    </Routes>
  )
}
