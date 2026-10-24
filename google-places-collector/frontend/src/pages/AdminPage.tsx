import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"

import { fetchAdminStats, readError, runRetentionCleanup } from "../api/client"
import { Card, ErrorState, SkeletonRows, useToast } from "../components/ui"
import { when } from "../lib/display"

export function AdminPage() {
  const { push } = useToast()
  const stats = useQuery({ queryKey: ["admin-stats"], queryFn: fetchAdminStats })

  async function cleanup() {
    try {
      const result = await runRetentionCleanup()
      push(`Removed ${result.deleted_searches} searches older than ${result.retention_days} days.`)
      await stats.refetch()
    } catch (error) {
      push(await readError(error), "err")
    }
  }

  const data = stats.data
  const cards = data
    ? [
        ["Users", data.total_users],
        ["Searches", data.total_searches],
        ["Searches today", data.searches_today],
        ["API requests", data.api_requests],
        ["API errors", data.api_errors],
        ["Outbound Google requests", data.estimated_google_requests],
      ]
    : []

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-semibold">Admin</h1>
          <p className="mt-1 text-sm text-stone-600">Outbound Google requests are a count of API calls, not a dollar amount.</p>
        </div>
        <div className="flex gap-2">
          <Link className="rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold" to="/admin/api-usage">API usage</Link>
          <button className="rounded-lg bg-pine-700 px-3 py-2 text-sm font-semibold text-white" onClick={() => void cleanup()} type="button">Run retention cleanup</button>
        </div>
      </div>
      {stats.isLoading ? <SkeletonRows /> : null}
      {stats.isError ? <ErrorState message="Admin stats could not be loaded." onRetry={() => void stats.refetch()} /> : null}
      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {cards.map(([label, value]) => (
              <Card key={String(label)}>
                <p className="text-sm text-stone-500">{label}</p>
                <p className="mt-1 font-display text-3xl font-semibold">{value}</p>
              </Card>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <h2 className="font-display text-lg font-semibold">Top categories</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {data.top_categories.length === 0 ? <li className="text-stone-500">No searches yet.</li> : null}
                {data.top_categories.map((item) => <li key={item.name} className="flex justify-between"><span>{item.name}</span><span>{item.count}</span></li>)}
              </ul>
            </Card>
            <Card>
              <h2 className="font-display text-lg font-semibold">Top locations</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {data.top_locations.length === 0 ? <li className="text-stone-500">No searches yet.</li> : null}
                {data.top_locations.map((item) => <li key={item.name} className="flex justify-between"><span>{item.name}</span><span>{item.count}</span></li>)}
              </ul>
            </Card>
          </div>
          <Card>
            <h2 className="font-display text-lg font-semibold">Recent searches</h2>
            <ul className="mt-3 divide-y divide-line text-sm">
              {data.recent_searches.length === 0 ? <li className="py-2 text-stone-500">No searches yet.</li> : null}
              {data.recent_searches.map((item) => (
                <li key={item.id} className="flex flex-wrap justify-between gap-2 py-2">
                  <span>{item.category} · {item.location_text}</span>
                  <span className="text-stone-500">{item.result_count} results · {item.status} · {when(item.created_at)}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <h2 className="font-display text-lg font-semibold">Failed requests</h2>
            <ul className="mt-3 divide-y divide-line text-sm">
              {data.failed_requests.length === 0 ? <li className="py-2 text-stone-500">No failed requests.</li> : null}
              {data.failed_requests.map((item) => (
                <li key={item.id} className="flex flex-wrap justify-between gap-2 py-2">
                  <span>{item.google_operation || item.endpoint}</span>
                  <span className="text-stone-500">{item.error_type || "error"} · {item.status_code ?? "—"} · {when(item.created_at)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      ) : null}
    </div>
  )
}
