import { FormEvent, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { readError } from "../api/client"
import { useAuth } from "../auth/AuthContext"
import { Button, Field, inputClass } from "../components/ui"

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (password.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }
    setBusy(true)
    setError("")
    try {
      await register(email.trim(), password)
      navigate("/dashboard")
    } catch (err) {
      setError(await readError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-12">
      <form className="w-full max-w-md space-y-4" onSubmit={onSubmit}>
        <p className="font-display text-sm font-semibold text-pine-700">Google Places Data Collector</p>
        <h1 className="font-display text-3xl font-semibold">Create an account</h1>
        <p className="text-sm text-stone-600">Search places matching your query after you sign in.</p>
        {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p> : null}
        <Field label="Email">
          <input className={inputClass} autoComplete="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </Field>
        <Field label="Password">
          <input className={inputClass} autoComplete="new-password" minLength={8} type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </Field>
        <Button className="w-full" disabled={busy} type="submit">
          {busy ? "Creating account..." : "Create account"}
        </Button>
        <p className="text-sm text-stone-600">
          Already registered? <Link className="font-semibold text-pine-700" to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  )
}
