import { createContext, useContext, useMemo, useState } from "react"

import { DISCLAIMER } from "../lib/display"

type Toast = { id: number; tone: "ok" | "err"; text: string }

const ToastContext = createContext<{
  push: (text: string, tone?: "ok" | "err") => void
} | null>(null)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const value = useMemo(
    () => ({
      push: (text: string, tone: "ok" | "err" = "ok") => {
        const id = Date.now() + Math.random()
        setToasts((current) => [...current, { id, tone, text }])
        window.setTimeout(() => {
          setToasts((current) => current.filter((item) => item.id !== id))
        }, 4200)
      },
    }),
    [],
  )
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-[min(100%-2rem,22rem)] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`rounded-xl border px-4 py-3 text-sm shadow-card ${
              toast.tone === "err" ? "border-red-200 bg-red-50 text-red-900" : "border-pine-100 bg-white text-ink"
            }`}
          >
            {toast.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const value = useContext(ToastContext)
  if (!value) throw new Error("ToastProvider is missing")
  return value
}

export function Disclaimer() {
  return (
    <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950">
      {DISCLAIMER}
    </p>
  )
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block font-medium text-stone-700">{label}</span>
      {children}
    </label>
  )
}

export const inputClass =
  "w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink outline-none transition placeholder:text-stone-400 focus:border-pine-600"

export function Button({
  children,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const styles = {
    primary: "bg-pine-700 text-white hover:bg-pine-800 disabled:bg-stone-300",
    ghost: "border border-line bg-white text-ink hover:bg-stone-50",
    danger: "bg-red-700 text-white hover:bg-red-800",
  }[variant]
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed ${styles} ${props.className || ""}`}
    >
      {children}
    </button>
  )
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-line bg-card p-5 shadow-card ${className}`}>{children}</section>
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-line bg-white px-6 py-12 text-center">
      <h3 className="font-display text-lg font-semibold text-ink">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-stone-600">{body}</p>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-900">
      <p>{message}</p>
      {onRetry ? (
        <button className="mt-3 font-semibold underline" onClick={onRetry} type="button">
          Try again
        </button>
      ) : null}
    </div>
  )
}

export function SkeletonRows() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="h-12 animate-pulse rounded-lg bg-stone-200/70" />
      ))}
    </div>
  )
}

export function Modal({
  title,
  children,
  onClose,
}: {
  title: string
  children: React.ReactNode
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-stone-950/40 p-4 sm:items-center">
      <div className="w-full max-w-lg rounded-2xl bg-card p-5 shadow-card">
        <div className="mb-3 flex items-start justify-between gap-4">
          <h3 className="font-display text-lg font-semibold">{title}</h3>
          <button className="text-sm text-stone-500" onClick={onClose} type="button">
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
