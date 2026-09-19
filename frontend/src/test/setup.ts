import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest doesn't run in "globals" mode here (tests import from "vitest"
// explicitly), so @testing-library/react's automatic afterEach-based
// cleanup never registers itself — without this, DOM from one test leaks
// into the next and testid/role queries start matching multiple elements.
afterEach(() => {
  cleanup();
});
