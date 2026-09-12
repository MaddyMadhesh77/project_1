import { Route, Routes } from 'react-router-dom'
import AdminLayout from './pages/AdminLayout'
import Analytics from './pages/Analytics'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import Graph from './pages/Graph'
import IntegrityCheck from './pages/IntegrityCheck'
import Logs from './pages/Logs'
import MemoryDetail from './pages/MemoryDetail'
import Memories from './pages/Memories'
import Rollback from './pages/Rollback'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Chat />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="memories" element={<Memories />} />
        <Route path="memories/:memoryId" element={<MemoryDetail />} />
        <Route path="memories/:memoryId/graph" element={<Graph />} />
        <Route path="integrity" element={<IntegrityCheck />} />
        <Route path="rollback" element={<Rollback />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="logs" element={<Logs />} />
      </Route>
    </Routes>
  )
}
