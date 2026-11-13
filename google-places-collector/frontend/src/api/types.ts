export type User = {
  id: number
  email: string
  role: string
  is_active: boolean
  created_at: string
}

export type TokenResponse = {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export type Place = {
  id: number
  google_place_id: string | null
  name: string | null
  address: string | null
  latitude: number | null
  longitude: number | null
  rating: number | null
  review_count: number | null
  phone: string | null
  website: string | null
  business_status: string | null
  maps_uri: string | null
  types: string[]
  opening_hours: string[] | null
  open_now: boolean | null
  distance_meters: number | null
  position: number | null
  detail_source?: string
  detail_warning?: string | null
}

export type SearchRecord = {
  id: number
  query: string
  category: string
  location_text: string
  formatted_address: string | null
  latitude: number | null
  longitude: number | null
  radius_meters: number | null
  keyword: string | null
  language: string
  search_mode: string
  field_mode: string
  result_count: number
  status: string
  error_message: string | null
  created_at: string
  available_fields: string[]
}

export type SearchResponse = {
  search: SearchRecord
  results: Place[]
  page: number
  page_size: number
  total: number
  message: string | null
  cap_note?: string
  max_results_applied?: number
}

export type HistoryResponse = {
  results: SearchRecord[]
  page: number
  page_size: number
  total: number
}

export type SavedItem = {
  id: number
  place_id: number
  created_at: string
  place: Place
}

export type SavedResponse = {
  results: SavedItem[]
  page: number
  page_size: number
  total: number
}

export type ExportRow = {
  id: number
  search_id: number | null
  format: string
  field_mode: string
  row_count: number
  created_at: string
}

export type SettingsInfo = {
  field_mode: string
  search_retention_days: number
  max_results_per_search: number
  max_searches_per_minute: number
  bulk_max_rows: number
  bulk_concurrency: number
  environment: string
}

export type NamedCount = { name: string; count: number }
export type DayCount = { date: string; count: number }

export type AdminStats = {
  total_users: number
  total_searches: number
  searches_today: number
  api_requests: number
  api_errors: number
  estimated_google_requests: number
  top_categories: NamedCount[]
  top_locations: NamedCount[]
  recent_searches: Array<{
    id: number
    user_id: number
    query: string
    category: string
    location_text: string
    result_count: number
    status: string
    created_at: string
  }>
  failed_requests: Array<{
    id: number
    endpoint: string
    google_operation: string
    error_type: string | null
    status_code: number | null
    created_at: string
  }>
}

export type UsageReport = {
  daily_searches: DayCount[]
  daily_errors: DayCount[]
  categories: NamedCount[]
  locations: NamedCount[]
}

export type SearchInput = {
  category: string
  location: string
  radius_km: number
  keyword?: string
  max_results: number
  language: string
  search_mode: "text" | "nearby"
  min_rating?: number
  min_reviews?: number
  has_website: boolean
  has_phone: boolean
  has_both: boolean
}

export type ResultQuery = {
  page?: number
  page_size?: number
  sort?: string
  min_rating?: number
  min_reviews?: number
  business_status?: string
  type_contains?: string
  q?: string
  has_website?: boolean
  has_phone?: boolean
  has_both?: boolean
  max_distance_km?: number
}

export type BulkResult = {
  row: number
  category?: string
  location?: string
  search_id?: number | null
  result_count?: number
  status?: string
  error?: string | null
  radius_km?: number | null
}

export type BulkResponse = {
  confirm_required: boolean
  search_count: number
  message: string
  stopped: boolean
  stop_reason: string | null
  failed_row: number | null
  results: BulkResult[]
}
