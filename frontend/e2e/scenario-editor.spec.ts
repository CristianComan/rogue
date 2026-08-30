import { expect, test, type Page } from "@playwright/test";

/**
 * Runs against the real backend (docker compose up -d, or uvicorn + a
 * migrated Postgres directly) and the real Vite dev server (started
 * automatically by playwright.config.ts's webServer). See
 * docs/architecture/implementation-plan.md's M3 phase-8 note.
 */

async function createScenarioViaLibrary(page: Page, name: string, owner: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "+ New scenario" }).click();
  const form = page.getByTestId("new-scenario-form");
  await form.getByPlaceholder("Name", { exact: true }).fill(name);
  await form.getByPlaceholder("Owner", { exact: true }).fill(owner);
  await form.getByRole("button", { name: "Create" }).click();
  await page.waitForURL(/\/scenarios\/[0-9a-f-]+$/);
}

test("create -> mission -> validate -> save -> publish -> view published version", async ({
  page,
}) => {
  await createScenarioViaLibrary(page, `E2E happy path ${Date.now()}`, "e2e");

  // Empty draft: validate reports the empty_scenario warning, not blocking.
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("empty_scenario")).toBeVisible();

  // Add a mission (default: no RF links, so no dangling-reference risk).
  await page.getByRole("button", { name: "+ Mission" }).click();
  await expect(page.getByRole("heading", { name: "Mission" })).toBeVisible();

  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/revision 1/)).toBeVisible();

  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("No findings.")).toBeVisible();

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published version 1.")).toBeVisible();

  await page.getByRole("link", { name: "View published version" }).click();
  await page.waitForURL(/\/versions\/1$/);
  await expect(page.getByText("1 mission(s), 0 receiver(s)")).toBeVisible();
});

test("publish is blocked by overlapping emissions, and resolves once fixed", async ({ page }) => {
  await createScenarioViaLibrary(page, `E2E 422 path ${Date.now()}`, "e2e");

  await page.getByRole("button", { name: "+ Mission" }).click();
  await page.getByRole("button", { name: "+ RF link" }).click();
  await page.getByRole("button", { name: "+ Emission" }).click();
  await page.getByRole("button", { name: "+ Emission" }).click();

  const emission0 = page.getByTestId("emission-0");
  const emission1 = page.getByTestId("emission-1");
  const recordingId = "00000000-0000-4000-8000-000000000001";

  // Both emissions point at the same made-up recording id via the "Custom
  // UUID…" fallback — there's no catalogue-existence check, only overlap
  // matters here.
  await emission0.getByLabel("Recording").selectOption({ label: "Custom UUID…" });
  await emission0.getByPlaceholder("recording UUID").fill(recordingId);
  await emission0.getByLabel(/Duration/).fill("PT10S");

  await emission1.getByLabel("Recording").selectOption({ label: "Custom UUID…" });
  await emission1.getByPlaceholder("recording UUID").fill(recordingId);
  await emission1.getByLabel("Start offset").fill("PT5S");
  await emission1.getByLabel(/Duration/).fill("PT10S");

  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/revision 1/)).toBeVisible();

  await page.getByRole("button", { name: "Publish" }).click();
  const dialog = page.getByRole("dialog", { name: "Publish blocked" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("overlapping_emissions")).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();

  // Fix it: move the second emission to start right after the first ends.
  await emission1.getByLabel("Start offset").fill("PT10S");

  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/revision 2/)).toBeVisible();

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published version 1.")).toBeVisible();
});

test("a stale revision produces a 409 conflict banner on save", async ({ page, request }) => {
  await createScenarioViaLibrary(page, `E2E 409 path ${Date.now()}`, "e2e");
  await expect(page.getByRole("button", { name: "Save" })).toBeVisible();

  // React StrictMode double-invokes the draft-loading effect in dev, which
  // can create two drafts; the UI deterministically ends up bound to
  // whichever one resolves *last* (see the `cancelled` flag in
  // ScenarioEditorPage.tsx). Reading `data-draft-id` off the root element
  // reflects that bound state directly, rather than guessing which of two
  // concurrent network responses arrived last (their arrival order isn't
  // guaranteed even though effect ordering is).
  const draftId = await page.locator("[data-draft-id]").getAttribute("data-draft-id");
  const scenarioId = new URL(page.url()).pathname.split("/").pop();

  // Simulate a concurrent editor saving the same draft "elsewhere",
  // bumping its revision out from under this page's in-memory state.
  const externalSave = await request.put(
    `http://localhost:8000/scenarios/${scenarioId}/drafts/${draftId}`,
    {
      data: {
        author: "someone-else",
        expected_revision: 0,
        zones: [],
        missions: [],
        receivers: [],
        timeline_events: [],
      },
    },
  );
  expect(externalSave.ok()).toBe(true);

  // This page still thinks it's at revision 0; any local edit + Save now
  // races against the bumped server-side revision and must 409.
  await page.getByRole("button", { name: "+ Zone" }).click();
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByText(/revision mismatch/)).toBeVisible();
  await expect(page.getByText(/revision 0/)).toBeVisible(); // local state never advanced
});
