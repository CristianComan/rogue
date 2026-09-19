import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ConflictError, NotFoundError, PublishBlockedError, request } from "./client";

function mockFetchOnce(status: number, body: unknown, contentLength?: string) {
  const headers = new Headers();
  headers.set("content-length", contentLength ?? (body === undefined ? "0" : "1"));
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      headers,
      json: async () => body,
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request", () => {
  it("returns the parsed JSON body on success", async () => {
    mockFetchOnce(200, { id: "abc" });

    const result = await request<{ id: string }>("/scenarios/abc");

    expect(result).toEqual({ id: "abc" });
  });

  it("builds query params, skipping undefined values", async () => {
    mockFetchOnce(200, []);

    await request("/scenarios", { query: { owner: "alice", tag: undefined, limit: 10 } });

    const calledUrl = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(calledUrl).toContain("owner=alice");
    expect(calledUrl).toContain("limit=10");
    expect(calledUrl).not.toContain("tag=");
  });

  it("sends the Idempotency-Key header when provided", async () => {
    mockFetchOnce(201, { id: "abc" });

    await request("/scenarios", { method: "POST", body: {}, idempotencyKey: "key-1" });

    const init = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe("key-1");
  });

  it("throws ConflictError on 409", async () => {
    mockFetchOnce(409, { detail: "stale revision" });

    await expect(request("/x")).rejects.toBeInstanceOf(ConflictError);
  });

  it("throws PublishBlockedError on 422 with findings attached", async () => {
    mockFetchOnce(422, { detail: "blocked", findings: [{ code: "dangling_recording_reference" }] });

    const err = await request("/x").catch((e) => e);

    expect(err).toBeInstanceOf(PublishBlockedError);
    expect((err as PublishBlockedError).findings).toEqual([
      { code: "dangling_recording_reference" },
    ]);
  });

  it("throws NotFoundError on 404", async () => {
    mockFetchOnce(404, { detail: "not found" });

    await expect(request("/x")).rejects.toBeInstanceOf(NotFoundError);
  });

  it("throws a plain ApiError on other non-2xx statuses", async () => {
    mockFetchOnce(500, { detail: "boom" });

    await expect(request("/x")).rejects.toBeInstanceOf(ApiError);
  });

  it("treats content-length 0 as no body", async () => {
    mockFetchOnce(204, undefined, "0");

    const result = await request("/x");

    expect(result).toBeUndefined();
  });
});
