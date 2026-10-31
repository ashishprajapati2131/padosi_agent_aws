import { useQuery } from "@tanstack/react-query"

import { fetchPlace } from "../api/client"
import { MISSING, coordLabel, ratingLabel, safeHttpUrl, statusLabel, text } from "../lib/display"
import { ErrorState, SkeletonRows } from "./ui"

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-line py-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</p>
      <div className="mt-1 text-sm text-ink">{children}</div>
    </div>
  )
}

export function PlaceDrawer({ placeId, onClose }: { placeId: number | null; onClose: () => void }) {
  const query = useQuery({
    queryKey: ["place", placeId],
    queryFn: () => fetchPlace(placeId as number),
    enabled: placeId != null,
  })

  if (placeId == null) return null
  const place = query.data
  const website = safeHttpUrl(place?.website || null)
  const maps = safeHttpUrl(place?.maps_uri || null)

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-stone-950/30" onClick={onClose} role="presentation">
      <aside
        className="h-full w-full max-w-md overflow-y-auto bg-card p-6 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="font-display text-xl font-semibold">{place ? text(place.name) : "Place details"}</h2>
          <button className="text-sm font-semibold text-stone-500" onClick={onClose} type="button">
            Close
          </button>
        </div>
        {query.isLoading ? <SkeletonRows /> : null}
        {query.isError ? <ErrorState message="Place details could not be loaded." onRetry={() => void query.refetch()} /> : null}
        {place?.detail_warning ? (
          <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">{place.detail_warning}</p>
        ) : null}
        {place ? (
          <div>
            <Row label="Address">{text(place.address)}</Row>
            <Row label="Phone">{text(place.phone)}</Row>
            <Row label="Website">
              {website ? (
                <a className="break-all text-pine-700 underline" href={website} rel="noreferrer" target="_blank">
                  {website}
                </a>
              ) : (
                MISSING
              )}
            </Row>
            <Row label="Rating">{ratingLabel(place.rating)}</Row>
            <Row label="Review count">{text(place.review_count)}</Row>
            <Row label="Business status">{statusLabel(place.business_status)}</Row>
            <Row label="Location">
              {place.latitude == null || place.longitude == null
                ? MISSING
                : `${coordLabel(place.latitude)}, ${coordLabel(place.longitude)}`}
            </Row>
            <Row label="Place ID">{text(place.google_place_id)}</Row>
            <Row label="Types">
              {place.types.length
                ? place.types.map((item) => item.replaceAll("_", " ")).join(", ")
                : MISSING}
            </Row>
            <Row label="Maps link">
              {maps ? (
                <a className="break-all text-pine-700 underline" href={maps} rel="noreferrer" target="_blank">
                  Open in Google Maps
                </a>
              ) : (
                MISSING
              )}
            </Row>
            <Row label="Opening hours">
              {place.opening_hours && place.opening_hours.length ? (
                <ul className="space-y-1">
                  {place.opening_hours.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              ) : (
                MISSING
              )}
            </Row>
          </div>
        ) : null}
      </aside>
    </div>
  )
}
