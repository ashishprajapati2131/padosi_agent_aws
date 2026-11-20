import { Navigate, Route, Routes } from "react-router-dom"

import { useAuth } from "./auth/AuthContext"
import { Layout } from "./components/Layout"
import { SkeletonRows } from "./components/ui"
import { AdminPage } from "./pages/AdminPage"
import { AdminUsagePage } from "./pages/AdminUsagePage"
import { DashboardPage } from "./pages/DashboardPage"
import { ExportsPage } from "./pages/ExportsPage"
import { HistoryPage } from "./pages/HistoryPage"
import { LoginPage } from "./pages/LoginPage"
import { RegisterPage } from "./pages/RegisterPage"
import { ResultsPage } from "./pages/ResultsPage"
import { SavedPage } from "./pages/SavedPage"
import { SearchPage } from "./pages/SearchPage"
import { SettingsPage } from "./pages/SettingsPage"

function Gate({ children, admin = false }: { children: React.ReactNode; admin?: boolean }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <SkeletonRows />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  if (admin && user.role !== "admin") return <Navigate to="/dashboard" replace />
  return <Layout>{children}</Layout>
}

function Guest({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (user) return <Navigate to="/dashboard" replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Guest><LoginPage /></Guest>} />
      <Route path="/register" element={<Guest><RegisterPage /></Guest>} />
      <Route path="/dashboard" element={<Gate><DashboardPage /></Gate>} />
      <Route path="/search" element={<Gate><SearchPage /></Gate>} />
      <Route path="/results/:searchId" element={<Gate><ResultsPage /></Gate>} />
      <Route path="/search-history" element={<Gate><HistoryPage /></Gate>} />
      <Route path="/saved-places" element={<Gate><SavedPage /></Gate>} />
      <Route path="/exports" element={<Gate><ExportsPage /></Gate>} />
      <Route path="/settings" element={<Gate><SettingsPage /></Gate>} />
      <Route path="/admin" element={<Gate admin><AdminPage /></Gate>} />
      <Route path="/admin/api-usage" element={<Gate admin><AdminUsagePage /></Gate>} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
