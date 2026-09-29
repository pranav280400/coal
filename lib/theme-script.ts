// Server-safe half of the theme system: the pre-paint script used by app/layout.tsx.

export const THEME_KEY = "lumen-theme";

/** Inline, render-blocking: picks the theme before the page paints, so there is no flash. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem('${THEME_KEY}');if(t!=='light'&&t!=='dark'){t=matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme='dark'}})();`;
