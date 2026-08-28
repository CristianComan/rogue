import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "./client";
import type { GeoPolygon } from "../domain/types";
import {
  cloneScenario,
  createDraft,
  createScenario,
  getDraft,
  getScenario,
  getVersion,
  listScenarios,
  listVersions,
  publishDraft,
  updateDraft,
  validateDraft,
} from "./scenarios";

vi.mock("./client", async () => {
  const actual = await vi.importActual<typeof client>("./client");
  return { ...actual, request: vi.fn() };
});

const AREA: GeoPolygon = { type: "Polygon", coordinates: [[[13.0, 52.0]]] };

beforeEach(() => {
  vi.mocked(client.request).mockReset().mockResolvedValue({});
});

describe("scenarios API client", () => {
  it("createScenario POSTs to /scenarios with an idempotency key", async () => {
    await createScenario({ name: "n", owner: "o", area_of_operation: AREA });

    expect(client.request).toHaveBeenCalledWith(
      "/scenarios",
      expect.objectContaining({ method: "POST", idempotencyKey: expect.any(String) }),
    );
  });

  it("listScenarios GETs /scenarios with filter params", async () => {
    await listScenarios({ owner: "alice" });

    expect(client.request).toHaveBeenCalledWith(
      "/scenarios",
      expect.objectContaining({ query: { owner: "alice" } }),
    );
  });

  it("getScenario GETs /scenarios/{id}", async () => {
    await getScenario("s1");

    expect(client.request).toHaveBeenCalledWith("/scenarios/s1");
  });

  it("createDraft fills in default empty content arrays", async () => {
    await createDraft("s1", { author: "op" });

    expect(client.request).toHaveBeenCalledWith(
      "/scenarios/s1/drafts",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          author: "op",
          zones: [],
          missions: [],
          receivers: [],
          timeline_events: [],
          recordings: [],
          base_version_id: null,
        }),
      }),
    );
  });

  it("getDraft GETs the draft path", async () => {
    await getDraft("s1", "d1");

    expect(client.request).toHaveBeenCalledWith("/scenarios/s1/drafts/d1");
  });

  it("updateDraft PUTs with expected_revision and no idempotency key", async () => {
    await updateDraft("s1", "d1", { author: "op", expected_revision: 3 });

    const [, options] = vi.mocked(client.request).mock.calls[0];
    expect(options).toMatchObject({
      method: "PUT",
      body: expect.objectContaining({ expected_revision: 3 }),
    });
    expect(options).not.toHaveProperty("idempotencyKey");
  });

  it("validateDraft POSTs to the validate path", async () => {
    await validateDraft("s1", "d1");

    expect(client.request).toHaveBeenCalledWith(
      "/scenarios/s1/drafts/d1/validate",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("publishDraft POSTs to the publish path with an idempotency key", async () => {
    await publishDraft("s1", "d1");

    expect(client.request).toHaveBeenCalledWith(
      "/scenarios/s1/drafts/d1/publish",
      expect.objectContaining({ method: "POST", idempotencyKey: expect.any(String) }),
    );
  });

  it("listVersions and getVersion GET the expected paths", async () => {
    await listVersions("s1");
    await getVersion("s1", 2);

    expect(client.request).toHaveBeenCalledWith("/scenarios/s1/versions");
    expect(client.request).toHaveBeenCalledWith("/scenarios/s1/versions/2");
  });

  it("cloneScenario POSTs to the clone path with an idempotency key", async () => {
    await cloneScenario("s1", { name: "clone", owner: "o2" });

    expect(client.request).toHaveBeenCalledWith(
      "/scenarios/s1/clone",
      expect.objectContaining({ method: "POST", idempotencyKey: expect.any(String) }),
    );
  });
});
