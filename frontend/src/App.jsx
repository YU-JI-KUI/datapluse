import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import Layout from '@/components/Layout'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import DataManagement from '@/pages/DataManagement'
import PreAnnotation from '@/pages/PreAnnotation'
import Annotation from '@/pages/Annotation'
import ConflictDetection from '@/pages/ConflictDetection'
import ConfigCenter from '@/pages/ConfigCenter'
import Export from '@/pages/Export'
import Users from '@/pages/Users'

function RequireAuth({ children }) {
  const token = localStorage.getItem('token')
  return token ? children : <Navigate to="/login" replace />
}

function RequireAdmin({ children }) {
  const roles = JSON.parse(localStorage.getItem('roles') || '[]')
  return roles.includes('admin') ? children : <Navigate to="/dashboard" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" richColors />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard"      element={<Dashboard />} />
          <Route path="data"           element={<DataManagement />} />
          <Route path="pre-annotation" element={<PreAnnotation />} />
          <Route path="annotation"     element={<Annotation />} />
          <Route path="conflicts"      element={<ConflictDetection />} />
          <Route path="config"         element={<ConfigCenter />} />
          <Route path="export"         element={<Export />} />
          <Route path="users"          element={<RequireAdmin><Users /></RequireAdmin>} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
