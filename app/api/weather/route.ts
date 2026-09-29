import { NextResponse, type NextRequest } from "next/server";

// Current conditions at a mine for the mobile greeting card (Open-Meteo: free, no API key).
// Server-side so the browser CSP stays `connect-src 'self'`; cached for 15 minutes.

const CODES: Record<number, string> = {
  0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
  51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 61: "Rain", 63: "Rain", 65: "Heavy rain",
  71: "Snow", 80: "Showers", 81: "Showers", 82: "Heavy showers", 95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
};

export async function GET(req: NextRequest) {
  const lat = Number(req.nextUrl.searchParams.get("lat"));
  const lon = Number(req.nextUrl.searchParams.get("lon"));
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    return NextResponse.json({ detail: "invalid coordinates" }, { status: 400 });
  }
  try {
    const res = await fetch(
      `https://api.open-meteo.com/v1/forecast?latitude=${lat.toFixed(3)}&longitude=${lon.toFixed(3)}&current=temperature_2m,weather_code&timezone=auto`,
      { next: { revalidate: 900 } },
    );
    if (!res.ok) throw new Error(String(res.status));
    const data = (await res.json()) as { current: { temperature_2m: number; weather_code: number } };
    return NextResponse.json(
      { temperature_c: Math.round(data.current.temperature_2m), condition: CODES[data.current.weather_code] ?? "—" },
      { headers: { "Cache-Control": "public, max-age=900" } },
    );
  } catch {
    return NextResponse.json({ detail: "weather unavailable" }, { status: 503 });
  }
}
