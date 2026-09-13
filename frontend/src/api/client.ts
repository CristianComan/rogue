/**
 * Thin fetch wrapper. No retry/caching logic — callers in src/api/*.ts
 * decide what to do with errors. Components must not import this directly;
 * go through src/api/scenarios.ts.
 */

// Falls back to the host-dev default so Vitest (which doesn't load
// .env.development, only .env/.env.test) never builds an invalid URL.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`API error ${status}`);
    this.status = status;
    this.body = body;
    this.name = "ApiError";
  }
}

/** 409 optimistic-concurrency / idempotency-key-reuse conflict. */
export class ConflictError extends ApiError {
  constructor(status: number, body: { detail: string }) {
    super(status, body);
    this.name = "ConflictError";
  }

  get detail(): string {
    return (this.body as { detail: string }).detail;
  }
}

/** 422 publish rejection carrying blocking validation findings. */
export class PublishBlockedError extends ApiError {
  constructor(status: number, body: { detail: string; findings: unknown[] }) {
    super(status, body);
    this.name = "PublishBlockedError";
  }

  get findings(): unknown[] {
    return (this.body as { findings: unknown[] }).findings;
  }
}

/** 404 not found. */
export class NotFoundError extends ApiError {
  constructor(status: number, body: { detail: string }) {
    super(status, body);
    this.name = "NotFoundError";
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  query?: object;
  idempotencyKey?: string;
}

function buildUrl(path: string, query?: object): string {
  const url = new URL(BASE_URL + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const contentLength = response.headers.get("content-length");
  const body = contentLength === "0" ? undefined : await response.json().catch(() => undefined);

  if (!response.ok) {
    if (response.status === 409) throw new ConflictError(response.status, body);
    if (response.status === 422) throw new PublishBlockedError(response.status, body);
    if (response.status === 404) throw new NotFoundError(response.status, body);
    throw new ApiError(response.status, body);
  }

  return body as T;
}

/** RFC 4122 v4 UUID, used as the client-generated Idempotency-Key. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
