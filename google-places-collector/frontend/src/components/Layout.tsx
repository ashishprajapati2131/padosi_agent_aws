import {
  Bookmark,
  Download,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Settings,
  Shield,
  X,
} from "lucide-react"
import { useState } from "react"
import { NavLink, useNavigate } from "react-router-dom"

import { useAuth } from "../auth/AuthContext"

const links = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/search", label: "Search", icon: Search },
  { to: "/search-history", label: "History", icon: History },
  { to: "/saved-places", label: "Saved places", icon: Bookmark },
  { to: "/exports", label: "Exports", icon: Download },
  { to: "/settings", label: "Settings", icon: Settings },
]

export function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  function signOut() {
    logout()
    navigate("/login")
  }

  const items = user?.role === "admin"
    ? [...links, { to: "/admin", label: "Admin", icon: Shield }]
    : links

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      {open ? <button aria-label="Close menu" className="fixed inset-0 z-30 bg-stone-950/30 lg:hidden" onClick={() => setOpen(false)} type="button" /> : null}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-line bg-card transition lg:static lg:w-auto lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-start justify-between px-5 py-5">
          <div>
            <p className="font-display text-base font-semibold leading-5 text-ink">Google Places Data Collector</p>
            <p className="mt-1 text-xs text-stone-500">Search places matching your query.</p>
          </div>
          <button className="lg:hidden" onClick={() => setOpen(false)} type="button" aria-label="Close sidebar">
            <X size={18} />
          </button>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-pine-700 text-white" : "text-stone-700 hover:bg-stone-100"}`
              }
            >
              <item.icon size={16} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-line px-4 py-4 text-sm">
          <p className="truncate font-medium">{user?.email}</p>
          <p className="text-xs capitalize text-stone-500">{user?.role}</p>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-paper/90 px-4 py-3 backdrop-blur">
          <button className="rounded-lg border border-line bg-white p-2 lg:hidden" onClick={() => setOpen(true)} type="button" aria-label="Open menu">
            <Menu size={18} />
          </button>
          <p className="hidden font-display text-sm font-semibold lg:block">Google Places Data Collector</p>
          <button className="ml-auto inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold" onClick={signOut} type="button">
            <LogOut size={16} />
            Log out
          </button>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </div>
    </div>
  )
}
