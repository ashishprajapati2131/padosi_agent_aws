import { useQuery } from "@tanstack/react-query"

import { fetchSettings } from "../api/client"
import { Card, Disclaimer, ErrorState, SkeletonRows } from "../components/ui"

export function SettingsPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: fetchSettings })

  return (
    <div className="space-y-5">
      <h1 className="font-display text-3xl font-semibold">Settings</h1>
      <p className="max-w-2xl text-sm text-stone-600">
        These values come from the server. Field mode, retention, and result caps are read-only here. Change them in the server environment, then restart the API.
      </p>
      <Disclaimer />
      {settings.isLoading ? <SkeletonRows /> : null}
      {settings.isError ? <ErrorState message="Settings could not be loaded." onRetry={() => void settings.refetch()} /> : null}
      {settings.data ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <p className="text-sm text-stone-500">Field mode</p>
            <p className="mt-1 font-display text-2xl font-semibold capitalize">{settings.data.field_mode}</p>
            <p className="mt-2 text-sm text-stone-600">Search lists use this mask. Opening a place may request the detailed mask.</p>
          </Card>
          <Card>
            <p className="text-sm text-stone-500">Search retention</p>
            <p className="mt-1 font-display text-2xl font-semibold">{settings.data.search_retention_days} days</p>
            <p className="mt-2 text-sm text-stone-600">An admin can run cleanup. Production should schedule that call. Retention must follow current Google terms.</p>
          </Card>
          <Card>
            <p className="text-sm text-stone-500">Maximum results per search</p>
            <p className="mt-1 font-display text-2xl font-semibold">{settings.data.max_results_per_search}</p>
            <p className="mt-2 text-sm text-stone-600">The server will not return more than this, even if a request asks for more.</p>
          </Card>
          <Card>
            <p className="text-sm text-stone-500">Search rate limit</p>
            <p className="mt-1 font-display text-2xl font-semibold">{settings.data.max_searches_per_minute}/min</p>
            <p className="mt-2 text-sm text-stone-600">Bulk rows: {settings.data.bulk_max_rows}. Concurrency: {settings.data.bulk_concurrency}. Environment: {settings.data.environment}.</p>
          </Card>
        </div>
      ) : null}
    </div>
  )
}
