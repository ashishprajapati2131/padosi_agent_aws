import { FormEvent, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { readError } from "../api/client"
import { useAuth } from "../auth/AuthContext"
import { Button, Field, inputClass } from "../components/ui"

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError("")
    try {
      await login(email.trim(), password)
      navigate("/dashboard")
    } catch (err) {
      setError(await readError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="hidden bg-pine-800 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <p className="font-display text-2xl font-semibold">Google Places Data Collector</p>
        <p className="max-w-md text-lg leading-8 text-pine-100">Search places matching your query. Category and location stay free text, so the same flow covers any business type you enter.</p>
      </section>
      <section className="flex items-center justify-center px-6 py-12">
        <form className="w-full max-w-md space-y-4" onSubmit={onSubmit}>
          <h1 className="font-display text-3xl font-semibold">Sign in</h1>
          <p className="text-sm text-stone-600">Use the account you registered for this collector.</p>
          {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p> : null}
          <Field label="Email">
            <input className={inputClass} autoComplete="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </Field>
          <Field label="Password">
            <input className={inputClass} autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </Field>
          <Button className="w-full" disabled={busy} type="submit">
            {busy ? "Signing in..." : "Sign in"}
          </Button>
          <p className="text-sm text-stone-600">
            No account yet? <Link className="font-semibold text-pine-700" to="/register">Create one</Link>
          </p>
        </form>
      </section>
    </div>
  )
}
