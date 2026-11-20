import { useQuery } from "@tanstack/react-query"
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { fetchUsage } from "../api/client"
import { Card, ErrorState, SkeletonRows } from "../components/ui"

export function AdminUsagePage() {
  const usage = useQuery({ queryKey: ["admin-usage"], queryFn: fetchUsage })

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-3xl font-semibold">API usage</h1>
        <p className="mt-1 text-sm text-stone-600">Charts count searches and outbound Google requests. They are not a price quote.</p>
      </div>
      {usage.isLoading ? <SkeletonRows /> : null}
      {usage.isError ? <ErrorState message="Usage data could not be loaded." onRetry={() => void usage.refetch()} /> : null}
      {usage.data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">Daily searches</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={usage.data.daily_searches}>
                  <CartesianGrid stroke="#e4dccd" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Line dataKey="count" stroke="#0c574e" strokeWidth={2} dot={false} name="Searches" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">API errors</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={usage.data.daily_errors}>
                  <CartesianGrid stroke="#e4dccd" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Line dataKey="count" stroke="#9a3412" strokeWidth={2} dot={false} name="Errors" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">Categories</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={usage.data.categories}>
                  <CartesianGrid stroke="#e4dccd" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#0f6e62" name="Searches" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 font-display text-lg font-semibold">Locations</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={usage.data.locations}>
                  <CartesianGrid stroke="#e4dccd" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#0c574e" name="Searches" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  )
}
