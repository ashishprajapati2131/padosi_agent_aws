import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios"

import type {
  AdminStats,
  BulkResponse,
  ExportRow,
  HistoryResponse,
  Place,
  ResultQuery,
  SavedResponse,
  SearchInput,
  SearchResponse,
  SettingsInfo,
  TokenResponse,
  UsageReport,
  User,
} from "./types"

const ACCESS = "gpc_access"
const REFRESH = "gpc_refresh"

let accessMemory = localStorage.getItem(ACCESS) || ""
let refreshMemory = localStorage.getItem(REFRESH) || ""

export function getAccessToken() {
  return accessMemory
}

export function setTokens(access: string, refresh: string) {
  accessMemory = access
  refreshMemory = refresh
  localStorage.setItem(ACCESS, access)
  localStorage.setItem(REFRESH, refresh)
}

export function clearTokens() {
  accessMemory = ""
  refreshMemory = ""
  localStorage.removeItem(ACCESS)
  localStorage.removeItem(REFRESH)
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
})

api.interceptors.request.use((config) => {
  if (accessMemory) {
    config.headers.Authorization = `Bearer ${accessMemory}`
  }
  return config
})

let refreshing: Promise<string | null> | null = null

async function refreshAccess(): Promise<string | null> {
  if (!refreshMemory) return null
  const response = await axios.post<TokenResponse>(`${import.meta.env.VITE_API_URL || ""}/api/auth/refresh`, {
    refresh_token: refreshMemory,
  })
  setTokens(response.data.access_token, response.data.refresh_token)
  return response.data.access_token
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    if (error.response?.status !== 401 || !original || original._retry || original.url?.includes("/api/auth/")) {
      return Promise.reject(error)
    }
    original._retry = true
    try {
      refreshing = refreshing || refreshAccess()
      const token = await refreshing
      refreshing = null
      if (!token) {
        clearTokens()
        return Promise.reject(error)
      }
      original.headers.Authorization = `Bearer ${token}`
      return api(original)
    } catch (refreshError) {
      refreshing = null
      clearTokens()
      return Promise.reject(refreshError)
    }
  },
)

export async function readError(error: unknown): Promise<string> {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    if (data instanceof Blob) {
      try {
        const parsed = JSON.parse(await data.text()) as { detail?: string }
        if (typeof parsed.detail === "string") return parsed.detail
      } catch {
        return "Something went wrong. Please try again."
      }
    }
    if (data && typeof data === "object" && "detail" in data && typeof data.detail === "string") {
      return data.detail
    }
  }
  return "Something went wrong. Please try again."
}

export async function register(email: string, password: string) {
  const { data } = await api.post<TokenResponse>("/api/auth/register", { email, password })
  setTokens(data.access_token, data.refresh_token)
  return data.user
}

export async function login(email: string, password: string) {
  const { data } = await api.post<TokenResponse>("/api/auth/login", { email, password })
  setTokens(data.access_token, data.refresh_token)
  return data.user
}

export async function fetchMe() {
  const { data } = await api.get<User>("/api/auth/me")
  return data
}

export async function fetchSettings() {
  const { data } = await api.get<SettingsInfo>("/api/settings")
  return data
}

export async function createSearch(body: SearchInput) {
  const { data } = await api.post<SearchResponse>("/api/search", body, { timeout: 120000 })
  return data
}

export async function fetchSearch(id: number, query: ResultQuery) {
  const { data } = await api.get<SearchResponse>(`/api/search/${id}`, { params: query })
  return data
}

export async function rerunSearch(id: number) {
  const { data } = await api.post<SearchResponse>(`/api/search/${id}/rerun`, {}, { timeout: 120000 })
  return data
}

export async function fetchHistory(page = 1) {
  const { data } = await api.get<HistoryResponse>("/api/history", { params: { page, page_size: 20 } })
  return data
}

export async function deleteHistory(id: number) {
  await api.delete(`/api/history/${id}`)
}

export async function fetchPlace(id: number) {
  const { data } = await api.get<Place>(`/api/places/${id}`)
  return data
}

export async function fetchSaved(page = 1) {
  const { data } = await api.get<SavedResponse>("/api/saved-places", { params: { page, page_size: 20 } })
  return data
}

export async function savePlaces(placeIds: number[]) {
  const { data } = await api.post<{ saved_ids: number[] }>("/api/saved-places", { place_ids: placeIds })
  return data
}

export async function deleteSaved(id: number) {
  await api.delete(`/api/saved-places/${id}`)
}

export async function fetchExports(page = 1) {
  const { data } = await api.get<{ results: ExportRow[]; total: number }>("/api/exports", {
    params: { page, page_size: 20 },
  })
  return data
}

async function saveBlob(responseData: Blob, headers: Record<string, string>, fallback: string) {
  const type = headers["content-type"] || ""
  if (type.includes("application/json")) {
    const parsed = JSON.parse(await responseData.text()) as { detail?: string }
    throw new Error(parsed.detail || "Export failed.")
  }
  const match = /filename="([^"]+)"/.exec(headers["content-disposition"] || "")
  const filename = match?.[1] || fallback
  const url = URL.createObjectURL(responseData)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function exportPlaces(body: { search_id?: number; saved?: boolean; format: "csv" | "xlsx"; place_ids?: number[] }) {
  const response = await api.post<Blob>("/api/exports", body, { responseType: "blob" })
  await saveBlob(response.data, response.headers as Record<string, string>, `places.${body.format}`)
}

export async function downloadExport(id: number, format: string) {
  const response = await api.get<Blob>(`/api/exports/${id}`, { responseType: "blob" })
  await saveBlob(response.data, response.headers as Record<string, string>, `places.${format}`)
}

export async function previewBulk(csvText: string) {
  const { data } = await api.post<BulkResponse>("/api/bulk-search", { csv_text: csvText, confirm: false })
  return data
}

export async function confirmBulk(csvText: string) {
  const { data } = await api.post<BulkResponse>("/api/bulk-search", { csv_text: csvText, confirm: true }, { timeout: 300000 })
  return data
}

export async function fetchAdminStats() {
  const { data } = await api.get<AdminStats>("/api/admin/stats")
  return data
}

export async function fetchUsage() {
  const { data } = await api.get<UsageReport>("/api/admin/api-usage")
  return data
}

export async function runRetentionCleanup() {
  const { data } = await api.post<{
    deleted_searches: number
    deleted_results: number
    deleted_orphan_places: number
    retention_days: number
  }>("/api/admin/retention/cleanup")
  return data
}

export function browserMapKey() {
  return (import.meta.env.VITE_GOOGLE_MAPS_BROWSER_KEY || "").trim()
}
