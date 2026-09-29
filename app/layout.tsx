import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Providers } from "@/components/providers";
import { THEME_SCRIPT } from "@/lib/theme-script";
import "./globals.css";

// Self-hosted so `next build` never needs to reach a font CDN — the image
// builds identically offline / in an air-gapped government network. See app/fonts/README.md.

// Display face: headings, figures, the wordmark.
const satoshi = localFont({
  variable: "--font-satoshi",
  display: "swap",
  src: "./fonts/satoshi-variable.woff2",
  weight: "300 900",
  style: "normal",
  fallback: ["ui-sans-serif", "system-ui", "sans-serif"],
});

// Text face: body copy, UI labels, tables.
const jakarta = localFont({
  variable: "--font-jakarta",
  display: "swap",
  src: "./fonts/plus-jakarta-sans.ttf",
  weight: "200 800",
  style: "normal",
  fallback: ["ui-sans-serif", "system-ui", "sans-serif"],
});

// Handwritten accent ("Ask me anything…" on the AI Assistant page).
const caveat = localFont({
  variable: "--font-caveat",
  display: "swap",
  src: "./fonts/caveat.ttf",
  weight: "400 700",
  style: "normal",
  fallback: ["cursive"],
});

export const metadata: Metadata = {
  title: { default: "Lumen", template: "%s · Lumen" },
  description: "AI-based Smart Governance & Compliance Monitoring System for Coal Mines — Ministry of Coal",
  applicationName: "Lumen",
  appleWebApp: { capable: true, title: "Lumen", statusBarStyle: "black-translucent" },
  icons: { icon: [{ url: "/icons/favicon-64.png", type: "image/png" }], apple: "/icons/apple-icon.png" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f1ea" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0b0c" },
  ],
  colorScheme: "dark light",
  width: "device-width",
  initialScale: 1,
  // Fixed scale: the layout is built to fit every phone width, so pinch/double-tap zoom is off.
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // data-theme is set by THEME_SCRIPT before hydration, so React must not flag the difference.
    <html lang="en" suppressHydrationWarning className={`${satoshi.variable} ${jakarta.variable} ${caveat.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
