import type { Place } from "../api/types"

export const MISSING = "Data not available"
export const DISCLAIMER =
  "Google Places data is provided through Google Maps Platform. Availability, fields, usage limits, and storage/export permissions are subject to Google's current terms and API policies."

export function text(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return MISSING
  return String(value)
}

export function categoryLabel(types: string[] | null | undefined): string {
  const first = types?.find((item) => item && item !== "point_of_interest")
  if (!first) return MISSING
  return first
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

export function statusLabel(value: string | null): string {
  if (!value) return MISSING
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

export function ratingLabel(value: number | null): string {
  if (value === null || value === undefined) return MISSING
  return value.toFixed(1)
}

export function distanceLabel(meters: number | null): string {
  if (meters === null || meters === undefined) return MISSING
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`
  return `${Math.round(meters)} m`
}

export function coordLabel(value: number | null): string {
  if (value === null || value === undefined) return MISSING
  return value.toFixed(6)
}

export function when(value: string | null | undefined): string {
  if (!value) return MISSING
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export function safeHttpUrl(value: string | null): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    if (url.protocol === "https:" || url.protocol === "http:") return value
  } catch {
    return null
  }
  return null
}

export function hasField(fields: string[] | undefined, field: string) {
  return !fields || fields.includes(field)
}

export function placeTitle(place: Pick<Place, "name">) {
  return place.name || MISSING
}
