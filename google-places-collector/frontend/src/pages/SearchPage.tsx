import { FormEvent, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { confirmBulk, createSearch, previewBulk, readError } from "../api/client"
import type { BulkResponse, SearchInput } from "../api/types"
import { Button, Card, Disclaimer, Field, Modal, inputClass, useToast } from "../components/ui"

const HINTS = ["Hotel", "School", "College", "Petrol Pump", "Restaurant", "Hospital", "Office", "Gym", "Pharmacy", "Cafe"]
const PHASES = ["Resolving location...", "Searching Google Places...", "Processing results..."] as const

export function SearchPage() {
  const navigate = useNavigate()
  const { push } = useToast()
  const [category, setCategory] = useState("")
  const [location, setLocation] = useState("")
  const [radius, setRadius] = useState(5)
  const [keyword, setKeyword] = useState("")
  const [maxResults, setMaxResults] = useState(20)
  const [language, setLanguage] = useState("en")
  const [mode, setMode] = useState<"text" | "nearby">("text")
  const [minRating, setMinRating] = useState("")
  const [minReviews, setMinReviews] = useState("")
  const [hasWebsite, setHasWebsite] = useState(false)
  const [hasPhone, setHasPhone] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [phase, setPhase] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [csv, setCsv] = useState("")
  const [preview, setPreview] = useState<BulkResponse | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)

  function payload(): SearchInput {
    return {
      category: category.trim(),
      location: location.trim(),
      radius_km: radius,
      keyword: keyword.trim() || undefined,
      max_results: maxResults,
      language: language.trim() || "en",
      search_mode: mode,
      min_rating: minRating === "" ? undefined : Number(minRating),
      min_reviews: minReviews === "" ? undefined : Number(minReviews),
      has_website: hasWebsite,
      has_phone: hasPhone,
      has_both: hasWebsite && hasPhone,
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setPhase(PHASES[0])
    const timers = [
      window.setTimeout(() => setPhase(PHASES[1]), 700),
      window.setTimeout(() => setPhase(PHASES[2]), 1600),
    ]
    try {
      const data = await createSearch(payload())
      timers.forEach((timer) => window.clearTimeout(timer))
      setPhase(`Found ${data.search.result_count} places`)
      window.setTimeout(() => navigate(`/results/${data.search.id}`), 500)
    } catch (error) {
      timers.forEach((timer) => window.clearTimeout(timer))
      setPhase(null)
      push(await readError(error), "err")
    } finally {
      setBusy(false)
    }
  }

  async function onPreview() {
    setBulkBusy(true)
    try {
      setPreview(await previewBulk(csv))
    } catch (error) {
      push(await readError(error), "err")
    } finally {
      setBulkBusy(false)
    }
  }

  async function onConfirm() {
    setBulkBusy(true)
    try {
      const result = await confirmBulk(csv)
      setPreview(null)
      push(result.message, result.stopped ? "err" : "ok")
      const first = result.results.find((row) => row.search_id)
      if (first?.search_id) navigate(`/results/${first.search_id}`)
    } catch (error) {
      push(await readError(error), "err")
    } finally {
      setBulkBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold">Search</h1>
        <p className="mt-2 text-stone-600">Search places matching your query. The count you see is for this search only.</p>
      </div>
      <Disclaimer />
      <Card>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Category">
              <input className={inputClass} list="category-hints" value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Any category" required />
              <datalist id="category-hints">
                {HINTS.map((hint) => <option key={hint} value={hint} />)}
              </datalist>
            </Field>
            <Field label="Location">
              <input className={inputClass} value={location} onChange={(event) => setLocation(event.target.value)} placeholder="City, area, pincode, or address" required />
            </Field>
            <Field label="Radius (km)">
              <input className={inputClass} max={50} min={0.1} step={0.1} type="number" value={radius} onChange={(event) => setRadius(Number(event.target.value))} />
            </Field>
            <Field label="Keyword (optional)">
              <input className={inputClass} value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="Extra words for the text query" />
            </Field>
            <Field label="Maximum results">
              <input className={inputClass} max={100} min={1} type="number" value={maxResults} onChange={(event) => setMaxResults(Number(event.target.value))} />
            </Field>
          </div>
          <button className="text-sm font-semibold text-pine-700" onClick={() => setAdvanced((value) => !value)} type="button">
            {advanced ? "Hide advanced filters" : "Advanced filters"}
          </button>
          {advanced ? (
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Minimum rating">
                <input className={inputClass} max={5} min={0} step={0.1} type="number" value={minRating} onChange={(event) => setMinRating(event.target.value)} />
              </Field>
              <Field label="Minimum reviews">
                <input className={inputClass} min={0} type="number" value={minReviews} onChange={(event) => setMinReviews(event.target.value)} />
              </Field>
              <Field label="Language">
                <input className={inputClass} value={language} onChange={(event) => setLanguage(event.target.value)} />
              </Field>
              <Field label="Search mode">
                <select className={inputClass} value={mode} onChange={(event) => setMode(event.target.value as "text" | "nearby")}>
                  <option value="text">Text</option>
                  <option value="nearby">Nearby</option>
                </select>
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <input checked={hasWebsite} onChange={(event) => setHasWebsite(event.target.checked)} type="checkbox" />
                Has website
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input checked={hasPhone} onChange={(event) => setHasPhone(event.target.checked)} type="checkbox" />
                Has phone
              </label>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={busy} type="submit">Search Places</Button>
            {phase ? <p className="text-sm font-medium text-pine-800">{phase}</p> : null}
          </div>
          <p className="text-xs text-stone-500">Nearby search uses the resolved point and radius. Text search uses category, optional keyword, and location. The server caps the result count.</p>
        </form>
      </Card>
      <Card>
        <h2 className="font-display text-lg font-semibold">Bulk search</h2>
        <p className="mt-1 text-sm text-stone-600">CSV columns: category, location, radius. You will confirm the count before any search runs.</p>
        <textarea
          className={`${inputClass} mt-3 min-h-32 font-mono`}
          placeholder={"category,location,radius\nHotel,Ahmedabad,5"}
          value={csv}
          onChange={(event) => setCsv(event.target.value)}
        />
        <Button className="mt-3" disabled={bulkBusy || !csv.trim()} onClick={() => void onPreview()} type="button" variant="ghost">
          Preview bulk search
        </Button>
      </Card>
      {preview ? (
        <Modal title="Confirm bulk search" onClose={() => setPreview(null)}>
          <p className="text-sm leading-6">{preview.message}</p>
          <p className="mt-2 text-sm text-stone-600">You are about to perform {preview.search_count} searches.</p>
          <ul className="mt-3 max-h-48 space-y-1 overflow-auto text-sm">
            {preview.results.map((row) => (
              <li key={row.row}>{row.row}. {row.category} — {row.location}</li>
            ))}
          </ul>
          <div className="mt-4 flex justify-end gap-2">
            <Button onClick={() => setPreview(null)} type="button" variant="ghost">Cancel</Button>
            <Button disabled={bulkBusy} onClick={() => void onConfirm()} type="button">Continue</Button>
          </div>
        </Modal>
      ) : null}
      <p className="text-sm text-stone-500">
        Previous searches are on the <Link className="font-semibold text-pine-700" to="/search-history">history</Link> page.
      </p>
    </div>
  )
}
