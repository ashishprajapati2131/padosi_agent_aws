import { useQuery } from "@tanstack/react-query"
import { useCallback, useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"

import { exportPlaces, fetchSearch, readError, savePlaces } from "../api/client"
import type { Place, ResultQuery } from "../api/types"
import { Pager } from "../components/Pager"
import { PlaceDrawer } from "../components/PlaceDrawer"
import { ResultsMap } from "../components/ResultsMap"
import { Button, Card, Disclaimer, EmptyState, ErrorState, SkeletonRows, inputClass, useToast } from "../components/ui"
import { MISSING, categoryLabel, coordLabel, distanceLabel, hasField, ratingLabel, safeHttpUrl, statusLabel, text } from "../lib/display"

const SORTS = [
  { value: "position_asc", label: "Result order" },
  { value: "rating_desc", label: "Rating high to low" },
  { value: "rating_asc", label: "Rating low to high" },
  { value: "reviews_desc", label: "Review count" },
  { value: "name_asc", label: "Name A–Z" },
  { value: "name_desc", label: "Name Z–A" },
  { value: "distance_asc", label: "Distance" },
]

const COLUMNS = [
  { key: "name", label: "Business name" },
  { key: "types", label: "Category" },
  { key: "address", label: "Address" },
  { key: "phone", label: "Phone" },
  { key: "website", label: "Website" },
  { key: "rating", label: "Rating" },
  { key: "review_count", label: "Review count" },
  { key: "maps_uri", label: "Maps link" },
  { key: "latitude", label: "Latitude" },
  { key: "longitude", label: "Longitude" },
  { key: "business_status", label: "Status" },
  { key: "distance", label: "Distance" },
]

function cell(place: Place, key: string) {
  if (key === "name") return text(place.name)
  if (key === "types") return categoryLabel(place.types)
  if (key === "address") return text(place.address)
  if (key === "phone") return text(place.phone)
  if (key === "rating") return ratingLabel(place.rating)
  if (key === "review_count") return text(place.review_count)
  if (key === "latitude") return coordLabel(place.latitude)
  if (key === "longitude") return coordLabel(place.longitude)
  if (key === "business_status") return statusLabel(place.business_status)
  if (key === "distance") return distanceLabel(place.distance_meters)
  if (key === "website") {
    const href = safeHttpUrl(place.website)
    return href ? <a className="text-pine-700 underline" href={href} rel="noreferrer" target="_blank">Website</a> : MISSING
  }
  if (key === "maps_uri") {
    const href = safeHttpUrl(place.maps_uri)
    return href ? <a className="text-pine-700 underline" href={href} rel="noreferrer" target="_blank">Maps</a> : MISSING
  }
  return MISSING
}

export function ResultsPage() {
  const params = useParams()
  const searchId = Number(params.searchId)
  const { push } = useToast()
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState("position_asc")
  const [q, setQ] = useState("")
  const [minRating, setMinRating] = useState("")
  const [minReviews, setMinReviews] = useState("")
  const [status, setStatus] = useState("")
  const [typeContains, setTypeContains] = useState("")
  const [hasWebsite, setHasWebsite] = useState(false)
  const [hasPhone, setHasPhone] = useState(false)
  const [hidden, setHidden] = useState<string[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [openId, setOpenId] = useState<number | null>(null)
  const [highlight, setHighlight] = useState<number | null>(null)

  const queryParams: ResultQuery = useMemo(
    () => ({
      page,
      page_size: 20,
      sort,
      q: q.trim() || undefined,
      min_rating: minRating === "" ? undefined : Number(minRating),
      min_reviews: minReviews === "" ? undefined : Number(minReviews),
      business_status: status || undefined,
      type_contains: typeContains.trim() || undefined,
      has_website: hasWebsite,
      has_phone: hasPhone,
      has_both: hasWebsite && hasPhone,
    }),
    [page, sort, q, minRating, minReviews, status, typeContains, hasWebsite, hasPhone],
  )

  const search = useQuery({
    queryKey: ["search", searchId, queryParams],
    queryFn: () => fetchSearch(searchId, queryParams),
    enabled: Number.isFinite(searchId),
  })

  const fields = search.data?.search.available_fields
  const columns = COLUMNS.filter((column) => hasField(fields, column.key) && !hidden.includes(column.key))
  const pageIds = search.data?.results.map((place) => place.id) ?? []
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selected.includes(id))

  const origin = useMemo(
    () => ({
      latitude: search.data?.search.latitude ?? null,
      longitude: search.data?.search.longitude ?? null,
    }),
    [search.data?.search.latitude, search.data?.search.longitude],
  )

  const onSelect = useCallback((id: number) => {
    setHighlight(id)
    setOpenId(id)
  }, [])

  function toggle(id: number) {
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]))
  }

  function toggleAll() {
    setSelected((current) => (allSelected ? current.filter((id) => !pageIds.includes(id)) : Array.from(new Set([...current, ...pageIds]))))
  }

  async function saveSelected() {
    if (!selected.length) return
    try {
      await savePlaces(selected)
      push(`Saved ${selected.length} places.`)
    } catch (error) {
      push(await readError(error), "err")
    }
  }

  async function exportSelected(format: "csv" | "xlsx") {
    try {
      await exportPlaces({ search_id: searchId, format, place_ids: selected.length ? selected : undefined })
      push("Export downloaded.")
    } catch (error) {
      push(await readError(error), "err")
    }
  }

  if (!Number.isFinite(searchId)) return <ErrorState message="This search link is not valid." />

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-semibold">Results</h1>
          <p className="mt-1 text-sm text-stone-600">
            {search.data ? `${search.data.search.category} · ${search.data.search.location_text}` : "Loading search"}
          </p>
        </div>
        <Link className="text-sm font-semibold text-pine-700" to="/search">New search</Link>
      </div>
      <Disclaimer />
      {search.data?.search.error_message ? <ErrorState message={search.data.search.error_message} /> : null}
      {search.data?.cap_note ? <p className="text-sm text-stone-600">{search.data.cap_note}</p> : null}
      <Card>
        <div className="grid gap-3 md:grid-cols-4">
          <input className={inputClass} placeholder="Search within results" value={q} onChange={(event) => { setPage(1); setQ(event.target.value) }} />
          <select className={inputClass} value={sort} onChange={(event) => { setPage(1); setSort(event.target.value) }}>
            {SORTS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <input className={inputClass} placeholder="Minimum rating" type="number" min={0} max={5} step={0.1} value={minRating} onChange={(event) => { setPage(1); setMinRating(event.target.value) }} />
          <input className={inputClass} placeholder="Minimum reviews" type="number" min={0} value={minReviews} onChange={(event) => { setPage(1); setMinReviews(event.target.value) }} />
          <input className={inputClass} placeholder="Type contains" value={typeContains} onChange={(event) => { setPage(1); setTypeContains(event.target.value) }} />
          <select className={inputClass} value={status} onChange={(event) => { setPage(1); setStatus(event.target.value) }}>
            <option value="">Any status</option>
            <option value="OPERATIONAL">Operational</option>
            <option value="CLOSED_TEMPORARILY">Closed temporarily</option>
            <option value="CLOSED_PERMANENTLY">Closed permanently</option>
          </select>
          <label className="flex items-center gap-2 text-sm"><input checked={hasWebsite} type="checkbox" onChange={(event) => { setPage(1); setHasWebsite(event.target.checked) }} /> Has website</label>
          <label className="flex items-center gap-2 text-sm"><input checked={hasPhone} type="checkbox" onChange={(event) => { setPage(1); setHasPhone(event.target.checked) }} /> Has phone</label>
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-stone-600">
          {COLUMNS.filter((column) => hasField(fields, column.key)).map((column) => (
            <label key={column.key} className="inline-flex items-center gap-1">
              <input
                checked={!hidden.includes(column.key)}
                type="checkbox"
                onChange={() => setHidden((current) => current.includes(column.key) ? current.filter((item) => item !== column.key) : [...current, column.key])}
              />
              {column.label}
            </label>
          ))}
        </div>
      </Card>
      <div className="flex flex-wrap items-center gap-2">
        <p className="mr-auto text-sm font-semibold">{search.data ? `Showing ${search.data.total} results` : "Loading results"}</p>
        <Button disabled={!selected.length} onClick={() => void saveSelected()} type="button" variant="ghost">Save selected</Button>
        <Button onClick={() => void exportSelected("csv")} type="button" variant="ghost">Export CSV</Button>
        <Button onClick={() => void exportSelected("xlsx")} type="button" variant="ghost">Export XLSX</Button>
      </div>
      <p className="text-xs text-stone-500">Showing the matches stored for this search. This is not every business in the city or on Google Maps. Sort order is an app setting, not an official ranking.</p>
      {search.isLoading ? <SkeletonRows /> : null}
      {search.isError ? <ErrorState message="Results could not be loaded." onRetry={() => void search.refetch()} /> : null}
      {search.data && search.data.total === 0 ? (
        <EmptyState
          title="No places found for this search."
          body="Try a broader location, a larger radius, a different keyword, or another category."
        />
      ) : null}
      {search.data && search.data.results.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="overflow-x-auto rounded-2xl border border-line bg-card">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="px-3 py-3">
                    <input checked={allSelected} onChange={toggleAll} type="checkbox" aria-label="Select all" />
                  </th>
                  {columns.map((column) => <th key={column.key} className="px-3 py-3 font-semibold">{column.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {search.data.results.map((place) => (
                  <tr key={place.id} className={`border-t border-line ${highlight === place.id ? "bg-pine-50" : ""}`}>
                    <td className="px-3 py-3">
                      <input checked={selected.includes(place.id)} onChange={() => toggle(place.id)} type="checkbox" aria-label={`Select ${text(place.name)}`} />
                    </td>
                    {columns.map((column) => (
                      <td key={column.key} className="max-w-xs px-3 py-3 align-top">
                        {column.key === "name" ? (
                          <button className="text-left font-semibold text-pine-800" onClick={() => onSelect(place.id)} type="button">
                            {cell(place, column.key)}
                          </button>
                        ) : (
                          cell(place, column.key)
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ResultsMap origin={origin} places={search.data.results} selectedId={highlight} onSelect={onSelect} />
        </div>
      ) : null}
      {search.data && search.data.total > 0 ? (
        <Pager page={search.data.page} pageSize={search.data.page_size} total={search.data.total} onPage={setPage} />
      ) : null}
      <PlaceDrawer placeId={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}
