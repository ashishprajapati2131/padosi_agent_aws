import { useEffect, useRef, useState } from "react"

import { browserMapKey } from "../api/client"
import type { Place } from "../api/types"
import { placeTitle, text } from "../lib/display"

type GMap = {
  fitBounds: (bounds: object) => void
  panTo: (position: { lat: number; lng: number }) => void
  setZoom: (zoom: number) => void
}

type GMarker = { setMap: (map: GMap | null) => void }

type GInfo = {
  setContent: (html: string) => void
  open: (map: GMap, marker: GMarker) => void
}

type MapsNamespace = {
  Map: new (element: HTMLElement, options: object) => GMap
  Marker: new (options: object) => GMarker
  InfoWindow: new () => GInfo
  LatLngBounds: new () => { extend: (position: { lat: number; lng: number }) => void }
  event: { addListener: (target: object, name: string, handler: () => void) => void }
}

declare global {
  interface Window {
    google?: { maps: MapsNamespace }
  }
}

function loadMaps(key: string): Promise<void> {
  if (window.google?.maps) return Promise.resolve()
  const existing = document.querySelector<HTMLScriptElement>("script[data-gpc-maps]")
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve(), { once: true })
      existing.addEventListener("error", () => reject(new Error("map")), { once: true })
    })
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script")
    script.dataset.gpcMaps = "1"
    script.async = true
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error("map"))
    document.head.appendChild(script)
  })
}

function escapeHtml(value: string) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;")
}

export function ResultsMap({
  places,
  selectedId,
  origin,
  onSelect,
}: {
  places: Place[]
  selectedId: number | null
  origin: { latitude: number | null; longitude: number | null }
  onSelect: (id: number) => void
}) {
  const key = browserMapKey()
  const node = useRef<HTMLDivElement>(null)
  const mapRef = useRef<GMap | null>(null)
  const markers = useRef<Map<number, GMarker>>(new Map())
  const info = useRef<GInfo | null>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!key || !node.current) return
    let cancelled = false
    void loadMaps(key)
      .then(() => {
        if (cancelled || !node.current || !window.google) return
        const maps = window.google.maps
        const center =
          origin.latitude != null && origin.longitude != null
            ? { lat: origin.latitude, lng: origin.longitude }
            : { lat: 23.0225, lng: 72.5714 }
        mapRef.current = new maps.Map(node.current, {
          center,
          zoom: 12,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
        })
        info.current = new maps.InfoWindow()
        setReady(true)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [key, origin.latitude, origin.longitude])

  useEffect(() => {
    const map = mapRef.current
    const maps = window.google?.maps
    if (!ready || !map || !maps) return
    markers.current.forEach((marker) => marker.setMap(null))
    markers.current.clear()
    const bounds = new maps.LatLngBounds()
    let plotted = 0
    for (const place of places) {
      if (place.latitude == null || place.longitude == null) continue
      const position = { lat: place.latitude, lng: place.longitude }
      const marker = new maps.Marker({ map, position, title: placeTitle(place) })
      maps.event.addListener(marker, "click", () => onSelect(place.id))
      markers.current.set(place.id, marker)
      bounds.extend(position)
      plotted += 1
    }
    if (plotted > 1) map.fitBounds(bounds)
  }, [places, ready, onSelect])

  useEffect(() => {
    const map = mapRef.current
    const marker = selectedId == null ? undefined : markers.current.get(selectedId)
    const place = places.find((item) => item.id === selectedId)
    if (!map || !marker || !place || !info.current) return
    info.current.setContent(
      `<div style="font:14px Source Sans 3,sans-serif;max-width:220px"><strong>${escapeHtml(placeTitle(place))}</strong><div>${escapeHtml(text(place.address))}</div></div>`,
    )
    info.current.open(map, marker)
    if (place.latitude != null && place.longitude != null) {
      map.panTo({ lat: place.latitude, lng: place.longitude })
    }
  }, [selectedId, places])

  if (!key) {
    return (
      <div className="flex min-h-60 items-center justify-center rounded-2xl border border-dashed border-line bg-white p-6 text-center text-sm text-stone-600">
        A browser key is not configured.
      </div>
    )
  }
  if (failed) {
    return (
      <div className="flex min-h-60 items-center justify-center rounded-2xl border border-dashed border-line bg-white p-6 text-center text-sm text-stone-600">
        The map could not be loaded. The results table is still available.
      </div>
    )
  }
  return <div ref={node} className="min-h-[420px] overflow-hidden rounded-2xl border border-line bg-white" />
}
