import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { deleteHistory, fetchHistory, readError, rerunSearch } from "../api/client"
import { Pager } from "../components/Pager"
import { Button, Card, EmptyState, ErrorState, SkeletonRows, useToast } from "../components/ui"
import { when } from "../lib/display"

export function HistoryPage() {
  const [page, setPage] = useState(1)
  const { push } = useToast()
  const navigate = useNavigate()
  const client = useQueryClient()
  const history = useQuery({ queryKey: ["history", page], queryFn: () => fetchHistory(page) })
  const remove = useMutation({
    mutationFn: deleteHistory,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["history"] })
      push("Search deleted.")
    },
    onError: async (error) => push(await readError(error), "err"),
  })

  async function repeat(id: number) {
    try {
      const data = await rerunSearch(id)
      push(`Found ${data.search.result_count} places`)
      navigate(`/results/${data.search.id}`)
    } catch (error) {
      push(await readError(error), "err")
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="font-display text-3xl font-semibold">Search history</h1>
      <p className="text-sm text-stone-600">Each row is one saved search. Repeat runs the same category and location again.</p>
      {history.isLoading ? <SkeletonRows /> : null}
      {history.isError ? <ErrorState message="History could not be loaded." onRetry={() => void history.refetch()} /> : null}
      {history.data && history.data.results.length === 0 ? (
        <EmptyState title="No searches yet" body="Searches you run appear here with their result count and date." />
      ) : null}
      {history.data && history.data.results.length > 0 ? (
        <Card>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-stone-500">
                <tr>
                  <th className="py-2 pr-3">Query</th>
                  <th className="py-2 pr-3">Location</th>
                  <th className="py-2 pr-3">Category</th>
                  <th className="py-2 pr-3">Results</th>
                  <th className="py-2 pr-3">Date</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {history.data.results.map((item) => (
                  <tr key={item.id} className="border-t border-line">
                    <td className="py-3 pr-3">{item.query}</td>
                    <td className="py-3 pr-3">{item.location_text}</td>
                    <td className="py-3 pr-3">{item.category}</td>
                    <td className="py-3 pr-3">{item.result_count}</td>
                    <td className="py-3 pr-3">{when(item.created_at)}</td>
                    <td className="py-3">
                      <div className="flex flex-wrap gap-2">
                        <Link className="font-semibold text-pine-700" to={`/results/${item.id}`}>View</Link>
                        <button className="font-semibold text-pine-700" onClick={() => void repeat(item.id)} type="button">Repeat</button>
                        <button className="font-semibold text-red-700" onClick={() => remove.mutate(item.id)} type="button">Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4">
            <Pager page={history.data.page} pageSize={history.data.page_size} total={history.data.total} onPage={setPage} />
          </div>
        </Card>
      ) : null}
      <Button onClick={() => navigate("/search")} type="button">Search Places</Button>
    </div>
  )
}
