import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Lumen — Smarter Monitoring for Safer Mines",
    short_name: "Lumen",
    description: "AI-based governance and compliance monitoring for coal mines (Ministry of Coal)",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#121416",
    theme_color: "#121416",
    categories: ["government", "productivity", "business"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "New inspection", url: "/inspections/new" },
      { name: "Report violation", url: "/violations/new" },
      { name: "Log attendance", url: "/attendance" },
    ],
  };
}
