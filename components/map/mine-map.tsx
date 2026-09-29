"use client";

import "leaflet/dist/leaflet.css";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Polygon, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { MinePoint } from "@/lib/types";

const STATUS_COLOR: Record<MinePoint["status"], string> = {
  compliant: "#1f9d55",
  minor_issues: "#e0a100",
  non_compliant: "#dc3a3a",
};

export interface MapMarker {
  id: string;
  latitude: number;
  longitude: number;
  color: string;
  label: string;
  href?: string;
  radius?: number;
}

function FitBounds({ points, focusId }: { points: { id: string; latitude: number; longitude: number }[]; focusId?: string | null }) {
  const map = useMap();
  useEffect(() => {
    const focus = focusId ? points.find((p) => p.id === focusId) : undefined;
    if (focus) {
      map.setView([focus.latitude, focus.longitude], 12);
      return;
    }
    if (points.length === 1) map.setView([points[0].latitude, points[0].longitude], 11);
    else if (points.length > 1) {
      map.fitBounds(points.map((p) => [p.latitude, p.longitude]) as [number, number][], { padding: [30, 30], maxZoom: 11 });
    }
  }, [map, points, focusId]);
  return null;
}

export default function MineMap({
  mines,
  extra = [],
  boundaries = [],
  focusId,
  interactive = true,
  className,
}: {
  mines: MinePoint[];
  extra?: MapMarker[];
  boundaries?: { id: string; coordinates: number[][] }[];
  focusId?: string | null;
  interactive?: boolean;
  className?: string;
}) {
  const { data: cfg } = useQuery({
    queryKey: ["public-config"],
    queryFn: () => fetch("/api/config").then((r) => r.json() as Promise<{ mapTileUrl: string; mapAttribution: string }>),
    staleTime: Infinity,
  });
  const all = [...mines.map((m) => ({ id: m.id, latitude: m.latitude, longitude: m.longitude })), ...extra];
  return (
    <MapContainer
      center={[22.5, 83.5]}
      zoom={5}
      scrollWheelZoom={interactive}
      dragging={interactive}
      zoomControl={interactive}
      className={className ?? "h-full w-full"}
      attributionControl
    >
      {cfg && <TileLayer url={cfg.mapTileUrl} attribution={cfg.mapAttribution} maxZoom={18} />}
      <FitBounds points={all} focusId={focusId} />
      {boundaries.map((b) => (
        <Polygon
          key={`b-${b.id}`}
          positions={b.coordinates.map(([lon, lat]) => [lat, lon]) as [number, number][]}
          pathOptions={{ color: "#11513c", weight: 1.5, fillOpacity: 0.06, dashArray: "4 4" }}
        />
      ))}
      {mines.map((m) => (
        <CircleMarker
          key={m.id}
          center={[m.latitude, m.longitude]}
          radius={m.id === focusId ? 11 : 8}
          pathOptions={{ color: "#ffffff", weight: 2, fillColor: STATUS_COLOR[m.status], fillOpacity: 0.95 }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            {m.name}
          </Tooltip>
          {interactive && (
            <Popup>
              <div className="min-w-48 font-sans">
                <p className="font-semibold">{m.name}</p>
                <p className="text-xs text-steel-500">
                  {m.code} · {m.subsidiary_code}
                </p>
                <ul className="mt-2 space-y-0.5 text-xs">
                  <li>Compliance: {m.compliance_rate}%</li>
                  <li>
                    Open violations: {m.open_violations} ({m.critical_violations} critical)
                  </li>
                  <li>Overdue statutory items: {m.overdue_compliance}</li>
                  <li>Risk score: {m.risk_score ?? "—"}</li>
                </ul>
                <div className="mt-2 flex gap-3 text-xs">
                  <Link href={`/violations?mine_id=${m.id}`}>Violations →</Link>
                  <Link href={`/inspections?mine_id=${m.id}`}>Inspections →</Link>
                </div>
              </div>
            </Popup>
          )}
        </CircleMarker>
      ))}
      {extra.map((p) => (
        <CircleMarker
          key={`x-${p.id}`}
          center={[p.latitude, p.longitude]}
          radius={p.radius ?? 5}
          pathOptions={{ color: p.color, weight: 1.5, fillColor: p.color, fillOpacity: 0.7 }}
        >
          <Tooltip>{p.label}</Tooltip>
          {p.href && interactive && (
            <Popup>
              <Link href={p.href}>{p.label} →</Link>
            </Popup>
          )}
        </CircleMarker>
      ))}
    </MapContainer>
  );
}

export const MAP_STATUS_COLOR = STATUS_COLOR;
