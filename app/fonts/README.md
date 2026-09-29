# Vendored fonts

Copied here so `next build` never needs network access to a font CDN. The image therefore
builds identically offline and in air-gapped government networks. Loaded via
`next/font/local` in `app/layout.tsx`.

| File | Family | Use | Licence |
| --- | --- | --- | --- |
| `satoshi-variable.woff2` | Satoshi (variable, 300–900) — https://www.fontshare.com/fonts/satoshi | Headings, figures | Fontshare Free Font Licence (free for commercial use, self-hosting permitted) |
| `plus-jakarta-sans.ttf` | Plus Jakarta Sans (variable, 200–800) — https://fonts.google.com/specimen/Plus+Jakarta+Sans | Body text, UI | SIL Open Font License 1.1 |
| `caveat.ttf` | Caveat — https://fonts.google.com/specimen/Caveat | Handwritten accent on the AI Assistant | SIL Open Font License 1.1 |
| `gabarito-latin.woff2` | Gabarito (previous UI face, no longer loaded) | — | SIL Open Font License 1.1 |

To refresh Satoshi, download the family zip from `https://api.fontshare.com/v2/fonts/download/satoshi`
and copy `Fonts/WEB/fonts/Satoshi-Variable.woff2`. Plus Jakarta Sans comes from
`https://github.com/google/fonts/tree/main/ofl/plusjakartasans`.
