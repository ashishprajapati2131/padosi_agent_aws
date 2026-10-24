import { Button } from "./ui"

export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (page: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="flex items-center justify-between gap-3 text-sm text-stone-600">
      <span>
        Page {page} of {pages}
      </span>
      <div className="flex gap-2">
        <Button disabled={page <= 1} onClick={() => onPage(page - 1)} type="button" variant="ghost">
          Previous
        </Button>
        <Button disabled={page >= pages} onClick={() => onPage(page + 1)} type="button" variant="ghost">
          Next
        </Button>
      </div>
    </div>
  )
}
