"use client";

// Browser → Next.js BFF (/api/proxy) → FastAPI. Tokens live in httpOnly cookies and
// never reach JavaScript; the proxy attaches them and refreshes them transparently.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public errors?: { loc: (string | number)[]; msg: string }[],
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined | string[]>;

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((item) => params.append(k, item));
    else params.set(k, String(v));
  }
  const qs = params.toString();
  return `/api/proxy${path}${qs ? `?${qs}` : ""}`;
}

function describe(body: unknown, status: number): { message: string; errors?: ApiError["errors"] } {
  if (body && typeof body === "object") {
    const b = body as { detail?: unknown; errors?: ApiError["errors"] };
    if (b.errors?.length) {
      const first = b.errors[0];
      const field = first.loc.filter((p) => p !== "body").join(".");
      return { message: `${field ? `${field}: ` : ""}${first.msg}`, errors: b.errors };
    }
    if (typeof b.detail === "string") return { message: b.detail };
  }
  return { message: status >= 500 ? "The server could not complete the request." : `Request failed (${status})` };
}

export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown; query?: Query; form?: FormData; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (init.form) body = init.form;
  else if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.body);
  }
  const res = await fetch(buildUrl(path, init.query), {
    method: init.method ?? (body ? "POST" : "GET"),
    headers,
    body,
    credentials: "same-origin",
    signal: init.signal,
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?next=${next}`);
    throw new ApiError(401, "Session expired");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const { message, errors } = describe(data, res.status);
    throw new ApiError(res.status, message, errors);
  }
  return data as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}

/** Server-Sent Events over fetch (POST bodies + cookies), yielding {event, data}. */
export async function* sse(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<{ event: string; data: unknown }> {
  const res = await fetch(buildUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => undefined);
    throw new ApiError(res.status, describe(data, res.status).message);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) yield { event, data: JSON.parse(dataLines.join("\n")) };
    }
  }
}
