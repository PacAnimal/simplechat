import { test, expect } from "@playwright/test";
import path from "path";
import {
  resetDB,
  applySession,
  createProfileAndGetToken,
  apiCreateDataset,
  apiUploadDatasetFile,
  apiCreateChat,
  getOllamaModel,
  sendMessage,
} from "./helpers";

// Fictional ZX-9000 manual - values are completely made up and not in any LLM training data.
// Spark plug gap 1.23 mm and displacement 742 cc are the canary facts tested against.
const ZX9000_TXT = path.resolve(__dirname, "../fixtures/zx9000_manual.txt");
const ZX9000_PDF = path.resolve(__dirname, "../fixtures/zx9000_manual.pdf");

test.beforeEach(async () => {
  await resetDB();
});

async function runRagTest(
  page: Parameters<Parameters<typeof test>[1]>[0],
  fixture: string,
  mimeType: string,
  label: string,
) {
  const { token, profile } = await createProfileAndGetToken();

  const model = await getOllamaModel(token);
  test.skip(!model, "No Ollama models available");

  // negative control: same model, no dataset — fictional spec must be unknown
  const bareChat = await apiCreateChat(token, "ollama", model!);
  await page.goto("/");
  await applySession(page, token, profile);
  await page.getByTestId(`chat-item-${bareChat}`).click();
  await page.getByTestId("chat-window").waitFor({ state: "visible", timeout: 10_000 });

  await sendMessage(
    page,
    "What is the spark plug gap for the Motocraft ZX-9000? Reply with just the measurement in mm.",
    60_000,
  );
  const bareReply = page.locator('[data-testid="message-assistant"]').nth(0);
  await expect(bareReply).not.toContainText("1.23");

  // positive control: dataset with the manual — fictional specs must be retrieved
  const datasetId = await apiCreateDataset(token, `ZX-9000 Manual (${label})`);
  await apiUploadDatasetFile(token, datasetId, fixture, `zx9000_manual.${label}`, mimeType);

  const ragChat = await apiCreateChat(token, "ollama", model!, datasetId);

  // reload so the frontend fetches the fresh chat + dataset lists
  await page.goto("/");
  await page.waitForSelector('[data-testid="sidebar"]', { timeout: 10_000 });

  await page.getByTestId(`chat-item-${ragChat}`).click();
  await page.getByTestId("chat-window").waitFor({ state: "visible", timeout: 10_000 });
  await expect(page.getByTestId("dataset-selector")).toContainText(`ZX-9000 Manual (${label})`);

  const replies = page.locator('[data-testid="message-assistant"]');

  await sendMessage(
    page,
    "What is the spark plug gap for the Motocraft ZX-9000? Reply with just the measurement in mm.",
    120_000,
  );
  await expect(replies.nth(0)).toContainText("1.23");

  await sendMessage(
    page,
    "What is the engine displacement in cc? Reply with just the number.",
    120_000,
  );
  await expect(replies.nth(1)).toContainText("742");

  if (mimeType === "application/pdf") {
    // PDF-only: fresh chat so history doesn't bias the RAG query toward engine-spec chunks
    const procChat = await apiCreateChat(token, "ollama", model!, datasetId);
    await page.goto("/");
    await page.waitForSelector('[data-testid="sidebar"]', { timeout: 10_000 });
    await page.getByTestId(`chat-item-${procChat}`).click();
    await page.getByTestId("chat-window").waitFor({ state: "visible", timeout: 10_000 });

    const procReplies = page.locator('[data-testid="message-assistant"]');

    // how many bolts — only in the procedure chunk, proves it was retrieved
    await sendMessage(
      page,
      "How many mounting bolts hold the water pump in place on the ZX-9000? Reply with just the number.",
      120_000,
    );
    await expect(procReplies.nth(0)).toContainText("3");

    // O-ring seal — only mentioned in the reassembly note at the end of the procedure
    await sendMessage(
      page,
      "What seal must be discarded and replaced when reinstalling the ZX-9000 water pump? Reply with just the part name.",
      120_000,
    );
    await expect(procReplies.nth(1)).toContainText("O-ring", { ignoreCase: true });
  }
}

test("Ollama RAG (txt): retrieves fictional ZX-9000 specs only when dataset is attached", async ({ page }) => {
  await runRagTest(page, ZX9000_TXT, "text/plain", "txt");
});

test("Ollama RAG (pdf): PDF is indexed and fictional ZX-9000 specs are retrieved via RAG", async ({ page }) => {
  await runRagTest(page, ZX9000_PDF, "application/pdf", "pdf");
});
