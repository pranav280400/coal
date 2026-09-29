import { NextResponse } from "next/server";

// Runtime (not build-time) public configuration, so one image serves every environment.
export function GET() {
  return NextResponse.json(
    {
      mapTileUrl: process.env.NEXT_PUBLIC_MAP_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      mapAttribution: process.env.NEXT_PUBLIC_MAP_ATTRIBUTION ?? "&copy; OpenStreetMap contributors",
    },
    { headers: { "Cache-Control": "public, max-age=300" } },
  );
}
