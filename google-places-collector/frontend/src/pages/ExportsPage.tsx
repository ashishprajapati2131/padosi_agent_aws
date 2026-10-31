import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { downloadExport, fetchExports, readError } from "../api/client"
import { Pager } from "../components/Pager"
import { Card, EmptyState, ErrorState, SkeletonRows, useToast } from "../components/ui"
import { when } from "../lib/display"

export function ExportsPage() {
  const [page, setPage] = useState(1)
  const { push } = useToast()
  const exportsQuery = useQuery({ queryKey: ["exports", page], queryFn: () => fetchExports(page) })

  async function download(id: number, format: string) {
    try {
      await downloadExport(id, format)
    } catch (error) {
      push(await readError(error), "err")
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="font-display text-3xl font-semibold">Exports</h1>
      <p className="text-sm text-stone-600">Files include only the export allowlist. A field turned off in configuration is absent from the file.</p>
      {exportsQuery.isLoading ? <SkeletonRows /> : null}
      {exportsQuery.isError ? <ErrorState message="Exports could not be loaded." onRetry={() => void exportsQuery.refetch()} /> : null}
      {exportsQuery.data && exportsQuery.data.results.length === 0 ? (
        <EmptyState title="No exports yet" body="Export CSV or XLSX from a results page or from saved places." />
      ) : null}
      {exportsQuery.data && exportsQuery.data.results.length > 0 ? (
        <Card>
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="py-2">When</th>
                <th className="py-2">Format</th>
                <th className="py-2">Rows</th>
                <th className="py-2">Search</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {exportsQuery.data.results.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className="py-3">{when(row.created_at)}</td>
                  <td className="py-3 uppercase">{row.format}</td>
                  <td className="py-3">{row.row_count}</td>
                  <td className="py-3">{row.search_id ?? "Saved places"}</td>
                  <td className="py-3">
                    <button className="font-semibold text-pine-700" onClick={() => void download(row.id, row.format)} type="button">Download</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4">
            <Pager page={page} pageSize={20} total={exportsQuery.data.total} onPage={setPage} />
          </div>
        </Card>
      ) : null}
    </div>
  )
}
