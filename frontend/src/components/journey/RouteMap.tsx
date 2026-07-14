"use client";

import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import type { ItineraryOption, LegOption, TransportMode } from "@/models/journey";

// Per-mode colour for markers and the connecting line, aligned with the app's
// slate/teal palette.
const MODE_COLOR: Record<string, string> = {
  cab: "#0f172a",
  auto: "#b45309",
  flight: "#0d9488",
  train: "#7c3aed",
  bus: "#2563eb",
  metro: "#db2777",
};

const ROAD_MODES = new Set<TransportMode>(["cab", "auto", "bus", "metro"]);

type LatLng = { lat: number; lng: number };
type RoutePoint = LatLng & { label: string; mode?: TransportMode };
type Line = [number, number]; // [lat, lng]

// Force English place labels on OpenMapTiles-schema vector styles, falling back
// to the Latin transliteration and then the local name when English is absent.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ENGLISH_LABEL: any = ["coalesce", ["get", "name:en"], ["get", "name:latin"], ["get", "name"]];

// OSRM road geometry is fetched on demand; cache so re-selecting the same
// option doesn't refetch.
const geometryCache = new Map<string, Line[]>();

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function samePoint(a: LatLng, b: LatLng): boolean {
  return Math.abs(a.lat - b.lat) < 1e-5 && Math.abs(a.lng - b.lng) < 1e-5;
}

function legEndpoints(leg: LegOption): { from: RoutePoint | null; to: RoutePoint | null } {
  const m = leg.metadata as Record<string, unknown>;
  const fLat = num(m.from_lat);
  const fLng = num(m.from_lng);
  const tLat = num(m.to_lat);
  const tLng = num(m.to_lng);
  return {
    from: fLat !== null && fLng !== null ? { lat: fLat, lng: fLng, label: leg.origin, mode: leg.mode } : null,
    to: tLat !== null && tLng !== null ? { lat: tLat, lng: tLng, label: leg.destination, mode: leg.mode } : null,
  };
}

// Origin -> intermediate stops -> destination, dropping consecutive duplicates.
function buildPoints(itinerary: ItineraryOption): RoutePoint[] {
  const points: RoutePoint[] = [];
  itinerary.legs.forEach((leg, index) => {
    const { from, to } = legEndpoints(leg);
    if (index === 0 && from) points.push(from);
    if (to) points.push(to);
  });
  return points.filter((point, index) => index === 0 || !samePoint(points[index - 1], point));
}

// Smooth curved arc (quadratic Bézier) for legs that don't follow roads, e.g.
// flights. `bend` is the perpendicular offset as a fraction of segment length.
function curvedArc(from: LatLng, to: LatLng, bend: number): Line[] {
  const dLat = to.lat - from.lat;
  const dLng = to.lng - from.lng;
  const len = Math.hypot(dLat, dLng) || 1e-6;
  const pLat = -dLng / len;
  const pLng = dLat / len;
  const off = len * bend;
  const midLat = (from.lat + to.lat) / 2 + pLat * off;
  const midLng = (from.lng + to.lng) / 2 + pLng * off;
  const pts: Line[] = [];
  for (let i = 0; i <= 40; i++) {
    const t = i / 40;
    const lat = (1 - t) ** 2 * from.lat + 2 * (1 - t) * t * midLat + t ** 2 * to.lat;
    const lng = (1 - t) ** 2 * from.lng + 2 * (1 - t) * t * midLng + t ** 2 * to.lng;
    pts.push([lat, lng]);
  }
  return pts;
}

// Fallback "road" when live routing is unavailable: a gently wavy line that
// tapers to the exact endpoints, so it reads as a road rather than a ruler line.
function wavyLine(from: LatLng, to: LatLng): Line[] {
  const dLat = to.lat - from.lat;
  const dLng = to.lng - from.lng;
  const len = Math.hypot(dLat, dLng) || 1e-6;
  const pLat = -dLng / len;
  const pLng = dLat / len;
  const amp = len * 0.06;
  const pts: Line[] = [];
  for (let i = 0; i <= 40; i++) {
    const t = i / 40;
    const baseLat = from.lat + dLat * t;
    const baseLng = from.lng + dLng * t;
    const taper = Math.sin(Math.PI * t); // 0 at ends, 1 in the middle
    const wave = Math.sin(6 * Math.PI * t) * amp * taper;
    pts.push([baseLat + pLat * wave, baseLng + pLng * wave]);
  }
  return pts;
}

// Real driving geometry from the public OSRM server (free, no key). Falls back
// to a wavy line on error/timeout so the leg still shows a road-like path.
async function roadGeometry(from: LatLng, to: LatLng): Promise<Line[]> {
  const key = `${from.lat.toFixed(5)},${from.lng.toFixed(5)};${to.lat.toFixed(5)},${to.lng.toFixed(5)}`;
  const cached = geometryCache.get(key);
  if (cached) return cached;

  let geometry: Line[];
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    const url = `https://router.project-osrm.org/route/v1/driving/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson`;
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timeout);
    const data = await res.json();
    const coords = data?.routes?.[0]?.geometry?.coordinates as [number, number][] | undefined;
    geometry = coords?.length ? coords.map(([lng, lat]) => [lat, lng] as Line) : wavyLine(from, to);
  } catch {
    geometry = wavyLine(from, to);
  }
  geometryCache.set(key, geometry);
  return geometry;
}

export function RouteMap({ itinerary }: { itinerary: ItineraryOption }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const points = buildPoints(itinerary);
  const hasRoute = points.length >= 2;

  useEffect(() => {
    if (!hasRoute || !containerRef.current) return;
    let map: import("maplibre-gl").Map | null = null;
    let cancelled = false;

    (async () => {
      const mod = await import("maplibre-gl");
      const maplibregl = mod.default ?? mod;
      if (cancelled || !containerRef.current) return;

      map = new maplibregl.Map({
        container: containerRef.current,
        // Free, keyless vector basemap (OpenMapTiles schema) so labels can be
        // switched to English worldwide.
        style: "https://tiles.openfreemap.org/styles/liberty",
        attributionControl: { compact: true },
        dragRotate: false,
      });

      map.on("load", () => {
        if (cancelled || !map) return;
        const m = map;

        // Render every place label in English worldwide.
        for (const layer of m.getStyle().layers ?? []) {
          if (layer.type !== "symbol") continue;
          const layout = layer.layout as Record<string, unknown> | undefined;
          if (layout && "text-field" in layout) {
            try {
              m.setLayoutProperty(layer.id, "text-field", ENGLISH_LABEL);
            } catch {
              /* some symbol layers (icons) have no text-field; ignore */
            }
          }
        }

        void (async () => {
          const bounds = new maplibregl.LngLatBounds();
          let index = 0;

          for (const leg of itinerary.legs) {
            const { from, to } = legEndpoints(leg);
            if (!from || !to || samePoint(from, to)) continue;

            let geometry: Line[];
            let dashed = false;
            let isRoad = false;
            if (leg.mode === "flight") {
              geometry = curvedArc(from, to, 0.18); // flights aren't roads — arc them
              dashed = true;
            } else if (ROAD_MODES.has(leg.mode)) {
              geometry = await roadGeometry(from, to); // real road path
              isRoad = true;
            } else {
              geometry = curvedArc(from, to, 0.06); // train and others: gentle curve
            }
            if (cancelled || !map) return;

            const id = `leg-${index++}`;
            m.addSource(id, {
              type: "geojson",
              data: {
                type: "Feature",
                properties: {},
                geometry: { type: "LineString", coordinates: geometry.map(([lat, lng]) => [lng, lat]) },
              },
            });
            m.addLayer({
              id,
              type: "line",
              source: id,
              layout: { "line-join": "round", "line-cap": "round" },
              paint: {
                "line-color": MODE_COLOR[leg.mode] ?? "#0f172a",
                "line-width": 4,
                "line-opacity": 0.85,
                ...(dashed ? { "line-dasharray": [1.5, 1.5] } : {}),
              },
            });
            void isRoad;
            for (const [lat, lng] of geometry) bounds.extend([lng, lat]);
          }

          if (cancelled || !map) return;

          points.forEach((point, i) => {
            const isEndpoint = i === 0 || i === points.length - 1;
            const color = isEndpoint ? "#0f172a" : MODE_COLOR[point.mode ?? "cab"] ?? "#0f172a";
            const size = isEndpoint ? 14 : 10;
            const el = document.createElement("div");
            el.style.cssText =
              `width:${size}px;height:${size}px;border-radius:9999px;background:${color};` +
              "border:2px solid #fff;box-shadow:0 0 0 1px rgba(15,23,42,0.15);cursor:pointer;";
            const marker = new maplibregl.Marker({ element: el }).setLngLat([point.lng, point.lat]).addTo(m);
            const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12 }).setText(point.label);
            el.addEventListener("mouseenter", () => popup.setLngLat([point.lng, point.lat]).addTo(m));
            el.addEventListener("mouseleave", () => popup.remove());
            void marker;
            bounds.extend([point.lng, point.lat]);
          });

          if (!cancelled && map && !bounds.isEmpty()) {
            map.fitBounds(bounds, { padding: 36, duration: 0, maxZoom: 12 });
          }
        })();
      });
    })();

    return () => {
      cancelled = true;
      map?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itinerary.itinerary_id, hasRoute]);

  if (!hasRoute) {
    return (
      <div className="flex h-48 items-center justify-center rounded-md border border-dashed border-slate-200 bg-slate-50 text-xs text-slate-400">
        Route map unavailable for this option.
      </div>
    );
  }

  return <div ref={containerRef} className="h-48 w-full overflow-hidden rounded-md border border-slate-200" />;
}
