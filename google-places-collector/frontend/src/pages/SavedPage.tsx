import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { deleteSaved, exportPlaces, fetchSaved, readError } from "../api/client"
import { Pager } from "../components/Pager"
import { PlaceDrawer } from "../components/PlaceDrawer"
import { Button, Card, EmptyState, ErrorState, SkeletonRows, useToast } from "../components/ui"
import { categoryLabel, text, when } from "../lib/display"

export function SavedPage() {
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<number | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  const { push } = useToast()
  const client = useQueryClient()
  const saved = useQuery({ queryKey: ["saved", page], queryFn: () => fetchSaved(page) })
  const remove = useMutation({
    mutationFn: deleteSaved,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["saved"] })
      push("Removed from saved places.")
    },
    onError: async (error) => push(await readError(error), "err"),
  })

  async function download(format: "csv" | "xlsx") {
    try {
      await exportPlaces({ saved: true, format, place_ids: selected.length ? selected : undefined })
      push("Export downloaded.")
    } catch (error) {
      push(await readError(error), "err")
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-3xl font-semibold">Saved places</h1>
        <div className="flex gap-2">
          <Button onClick={() => void download("csv")} type="button" variant="ghost">Export CSV</Button>
          <Button onClick={() => void download("xlsx")} type="button" variant="ghost">Export XLSX</Button>
        </div>
      </div>
      {saved.isLoading ? <SkeletonRows /> : null}
      {saved.isError ? <ErrorState message="Saved places could not be loaded." onRetry={() => void saved.refetch()} /> : null}
      {saved.data && saved.data.results.length === 0 ? (
        <EmptyState title="Nothing saved" body="Select rows on a results page and choose Save selected." />
      ) : null}
      {saved.data && saved.data.results.length > 0 ? (
        <Card>
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="py-2">Select</th>
                <th className="py-2">Name</th>
                <th className="py-2">Category</th>
                <th className="py-2">Address</th>
                <th className="py-2">Saved</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {saved.data.results.map((item) => (
                <tr key={item.id} className="border-t border-line">
                  <td className="py-3">
                    <input
                      checked={selected.includes(item.place_id)}
                      type="checkbox"
                      onChange={() => setSelected((current) => current.includes(item.place_id) ? current.filter((id) => id !== item.place_id) : [...current, item.place_id])}
                      aria-label={`Select ${text(item.place.name)}`}
                    />
                  </td>
                  <td className="py-3">
                    <button className="font-semibold text-pine-800" onClick={() => setOpenId(item.place_id)} type="button">{text(item.place.name)}</button>
                  </td>
                  <td className="py-3">{categoryLabel(item.place.types)}</td>
                  <td className="py-3">{text(item.place.address)}</td>
                  <td className="py-3">{when(item.created_at)}</td>
                  <td className="py-3">
                    <button className="font-semibold text-red-700" onClick={() => remove.mutate(item.id)} type="button">Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4">
            <Pager page={saved.data.page} pageSize={saved.data.page_size} total={saved.data.total} onPage={setPage} />
          </div>
        </Card>
      ) : null}
      <PlaceDrawer placeId={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}
