import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { fetchHistory } from "../api/client"
import { useAuth } from "../auth/AuthContext"
import { Card, Disclaimer, EmptyState, ErrorState, SkeletonRows } from "../components/ui"
import { when } from "../lib/display"

export function DashboardPage() {
  const { user } = useAuth()
  const history = useQuery({ queryKey: ["history", 1], queryFn: () => fetchHistory(1) })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold">Dashboard</h1>
        <p className="mt-2 max-w-2xl text-stone-600">
          Search places matching your query. Enter any category and location. Results are the matches returned for that query.
        </p>
      </div>
      <Disclaimer />
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <p className="text-sm text-stone-500">Signed in</p>
          <p className="mt-2 truncate font-display text-lg font-semibold">{user?.email}</p>
          <p className="text-sm capitalize text-stone-500">{user?.role}</p>
        </Card>
        <Card>
          <p className="text-sm text-stone-500">Searches</p>
          <p className="mt-2 font-display text-3xl font-semibold">{history.data?.total ?? "—"}</p>
          <Link className="mt-2 inline-block text-sm font-semibold text-pine-700" to="/search-history">View history</Link>
        </Card>
        <Card>
          <p className="text-sm text-stone-500">New search</p>
          <p className="mt-2 text-sm text-stone-600">Hotel, school, petrol pump, gym — type the category. Nothing is hard-coded.</p>
          <Link className="mt-3 inline-flex rounded-lg bg-pine-700 px-3 py-2 text-sm font-semibold text-white" to="/search">Search Places</Link>
        </Card>
      </div>
      <Card>
        <h2 className="font-display text-lg font-semibold">Recent searches</h2>
        {history.isLoading ? <div className="mt-4"><SkeletonRows /></div> : null}
        {history.isError ? <div className="mt-4"><ErrorState message="History could not be loaded." onRetry={() => void history.refetch()} /></div> : null}
        {history.data && history.data.results.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="No searches yet" body="Run a search to see matches here. A result count is the size of that search, not every business in a city." />
          </div>
        ) : null}
        {history.data && history.data.results.length > 0 ? (
          <ul className="mt-4 divide-y divide-line">
            {history.data.results.slice(0, 6).map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                <div>
                  <p className="font-semibold">{item.category} · {item.location_text}</p>
                  <p className="text-stone-500">{when(item.created_at)} · {item.result_count} results · {item.status}</p>
                </div>
                <Link className="font-semibold text-pine-700" to={`/results/${item.id}`}>View</Link>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
    </div>
  )
}
