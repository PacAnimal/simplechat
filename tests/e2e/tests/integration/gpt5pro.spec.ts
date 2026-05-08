import { test, expect } from "@playwright/test";
import path from "path";
import { resetDB, loginWithTestProfile, createChat, sendMessage, uploadFileFromPath } from "./helpers";

const MOTORCYCLE_PDF = path.resolve(__dirname, "../fixtures/zx9000_manual.pdf");

test.beforeEach(async ({ page }) => {
  await resetDB();
  await page.goto("/");
  await loginWithTestProfile(page);
});

test("basic chat works with gpt-5-pro", async ({ page }) => {
  await createChat(page, "openai", "gpt-5-pro");
  await sendMessage(page, "Reply with just the word: tangerine");

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("tangerine", { ignoreCase: true });
});

test("gpt-5-pro reads specs from uploaded motorcycle PDF", async ({ page }) => {
  await createChat(page, "openai", "gpt-5-pro");
  await uploadFileFromPath(page, MOTORCYCLE_PDF, "application/pdf");

  await sendMessage(
    page,
    "What is the engine displacement of the motorcycle in this manual? Reply with just the number and unit.",
    120_000,
  );

  const reply = page.locator('[data-testid="message-assistant"]').first();
  await expect(reply).toContainText("742", { ignoreCase: true });
});
